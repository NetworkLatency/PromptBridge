from __future__ import annotations

from dataclasses import asdict, dataclass
import json
import socket
import time
from typing import Callable
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from promptbridge.config import ProviderProfile


_RETRYABLE_STATUS_CODES = {408, 409, 429, 500, 502, 503, 504}


class ProviderError(RuntimeError):
    """Raised when an OpenAI-compatible provider request fails."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id


@dataclass(frozen=True)
class LLMResponse:
    provider: str
    protocol: str
    model: str
    text: str
    usage: dict
    request_id: str | None
    response_id: str | None
    finish_reason: str | None
    latency_ms: int

    def to_dict(self) -> dict:
        return asdict(self)


class LLMClient:
    """Small client for Responses API and OpenAI-compatible Chat Completions."""

    def __init__(
        self,
        profile: ProviderProfile,
        *,
        api_key: str | None,
        timeout_seconds: int = 60,
        max_retries: int = 2,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        if profile.auth == "bearer" and not api_key:
            raise ValueError(f"Provider {profile.name!r} requires an API key.")
        if timeout_seconds <= 0:
            raise ValueError("timeout_seconds must be greater than zero.")
        if max_retries < 0:
            raise ValueError("max_retries cannot be negative.")
        self.profile = profile
        self.api_key = api_key
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self._sleep = sleep

    def generate(
        self,
        *,
        instructions: str,
        input_text: str,
        model: str | None = None,
        max_output_tokens: int | None = None,
        stage: str = "generate",
    ) -> LLMResponse:
        resolved_model = (model or self.profile.default_model).strip()
        if not resolved_model:
            raise ValueError("Model name cannot be empty.")
        if not input_text.strip():
            raise ValueError("Provider input cannot be empty.")
        if max_output_tokens is not None and max_output_tokens <= 0:
            raise ValueError("max_output_tokens must be greater than zero.")

        if self.profile.protocol == "responses":
            endpoint = f"{self.profile.base_url}/responses"
            payload = {
                "model": resolved_model,
                "instructions": instructions,
                "input": input_text,
                "store": False,
            }
            if max_output_tokens is not None:
                payload["max_output_tokens"] = max_output_tokens
        else:
            endpoint = f"{self.profile.base_url}/chat/completions"
            payload = {
                "model": resolved_model,
                "messages": [
                    {"role": "system", "content": instructions},
                    {"role": "user", "content": input_text},
                ],
            }
            if max_output_tokens is not None:
                payload["max_tokens"] = max_output_tokens

        started = time.perf_counter()
        body, request_id = self._post_json(endpoint, payload, stage=stage)
        latency_ms = int((time.perf_counter() - started) * 1000)
        if self.profile.protocol == "responses":
            return self._parse_responses(body, request_id, resolved_model, latency_ms, stage)
        return self._parse_chat(body, request_id, resolved_model, latency_ms, stage)

    def _post_json(self, url: str, payload: dict, *, stage: str) -> tuple[dict, str | None]:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "promptbridge/0.4.0",
        }
        if self.profile.auth == "bearer":
            headers["Authorization"] = f"Bearer {self.api_key}"

        opener = urllib_request.build_opener(_RejectRedirects())
        label = f"{self.profile.name} {stage}"
        for attempt in range(self.max_retries + 1):
            request = urllib_request.Request(url, data=data, headers=headers, method="POST")
            try:
                with opener.open(request, timeout=self.timeout_seconds) as response:
                    request_id = response.headers.get("x-request-id")
                    raw = response.read().decode("utf-8")
                    try:
                        parsed = json.loads(raw)
                    except json.JSONDecodeError as exc:
                        raise ProviderError(
                            f"{label} returned invalid JSON.",
                            status_code=response.status,
                            request_id=request_id,
                        ) from exc
                    if not isinstance(parsed, dict):
                        raise ProviderError(
                            f"{label} returned an unexpected JSON shape.",
                            status_code=response.status,
                            request_id=request_id,
                        )
                    return parsed, request_id
            except HTTPError as exc:
                request_id = exc.headers.get("x-request-id") if exc.headers else None
                detail = _read_error_detail(exc)
                if exc.code in _RETRYABLE_STATUS_CODES and attempt < self.max_retries:
                    self._sleep(_retry_delay(exc.headers, attempt))
                    continue
                raise ProviderError(
                    f"{label} HTTP {exc.code}: {detail}",
                    status_code=exc.code,
                    request_id=request_id,
                ) from exc
            except (URLError, TimeoutError, socket.timeout) as exc:
                if attempt < self.max_retries:
                    self._sleep(min(0.5 * (2**attempt), 4.0))
                    continue
                raise ProviderError(f"Cannot reach {label} at {url}: {exc}") from exc
        raise ProviderError(f"{label} exhausted retries.")

    def _parse_responses(
        self,
        body: dict,
        request_id: str | None,
        model: str,
        latency_ms: int,
        stage: str,
    ) -> LLMResponse:
        status = body.get("status")
        if isinstance(status, str) and status != "completed":
            details = body.get("incomplete_details") or body.get("error") or "no details"
            raise ProviderError(
                f"{self.profile.name} {stage} ended with status {status}: {details}",
                request_id=request_id,
            )
        text = _extract_responses_text(body)
        if not text:
            raise ProviderError(
                f"{self.profile.name} {stage} returned no output text.",
                request_id=request_id,
            )
        return LLMResponse(
            provider=self.profile.name,
            protocol=self.profile.protocol,
            model=body.get("model") if isinstance(body.get("model"), str) else model,
            text=text,
            usage=body.get("usage") if isinstance(body.get("usage"), dict) else {},
            request_id=request_id,
            response_id=body.get("id") if isinstance(body.get("id"), str) else None,
            finish_reason=status if isinstance(status, str) else None,
            latency_ms=latency_ms,
        )

    def _parse_chat(
        self,
        body: dict,
        request_id: str | None,
        model: str,
        latency_ms: int,
        stage: str,
    ) -> LLMResponse:
        choices = body.get("choices")
        if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
            raise ProviderError(
                f"{self.profile.name} {stage} returned no chat choices.",
                request_id=request_id,
            )
        choice = choices[0]
        message = choice.get("message")
        content = message.get("content") if isinstance(message, dict) else None
        text = _extract_chat_text(content)
        if not text:
            raise ProviderError(
                f"{self.profile.name} {stage} returned empty chat content.",
                request_id=request_id,
            )
        finish_reason = choice.get("finish_reason")
        return LLMResponse(
            provider=self.profile.name,
            protocol=self.profile.protocol,
            model=body.get("model") if isinstance(body.get("model"), str) else model,
            text=text,
            usage=body.get("usage") if isinstance(body.get("usage"), dict) else {},
            request_id=request_id,
            response_id=body.get("id") if isinstance(body.get("id"), str) else None,
            finish_reason=finish_reason if isinstance(finish_reason, str) else None,
            latency_ms=latency_ms,
        )


class _RejectRedirects(urllib_request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Never forward a provider credential to a different URL implicitly.
        return None


def _extract_responses_text(response: dict) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str) and direct.strip():
        return direct.strip()

    pieces: list[str] = []
    output = response.get("output")
    if not isinstance(output, list):
        return ""
    for item in output:
        if not isinstance(item, dict) or not isinstance(item.get("content"), list):
            continue
        for block in item["content"]:
            if not isinstance(block, dict) or block.get("type") != "output_text":
                continue
            text = block.get("text")
            if isinstance(text, str) and text.strip():
                pieces.append(text.strip())
    return "\n".join(pieces)


def _extract_chat_text(content: object) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    pieces: list[str] = []
    for part in content:
        if not isinstance(part, dict):
            continue
        text = part.get("text")
        if isinstance(text, str) and text.strip():
            pieces.append(text.strip())
    return "\n".join(pieces)


def _read_error_detail(exc: HTTPError) -> str:
    raw = exc.read().decode("utf-8", errors="replace")
    if not raw:
        return str(exc.reason or "request failed")
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return raw[:1000]
    if isinstance(parsed, dict):
        error = parsed.get("error")
        if isinstance(error, dict) and isinstance(error.get("message"), str):
            return error["message"][:1000]
    return raw[:1000]


def _retry_delay(headers, attempt: int) -> float:
    if headers:
        retry_after = headers.get("retry-after")
        if retry_after:
            try:
                return min(max(float(retry_after), 0.0), 30.0)
            except ValueError:
                pass
    return min(0.5 * (2**attempt), 4.0)
