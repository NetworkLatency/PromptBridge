from __future__ import annotations

from abc import ABC, abstractmethod
import json
import time
from urllib import request as urllib_request
from urllib.error import HTTPError, URLError

from promptbridge.translation.types import TranslationRequest, TranslationResult


class TranslationProvider(ABC):
    name: str

    @abstractmethod
    def translate(self, request: TranslationRequest) -> TranslationResult:
        raise NotImplementedError


class NoTranslationProvider(TranslationProvider):
    name = "none"

    def translate(self, request: TranslationRequest) -> TranslationResult:
        return TranslationResult(
            provider=self.name,
            model=None,
            source_language=request.source_language,
            target_language=request.target_language,
            translated_text="",
            prompt_sent=None,
            latency_ms=0,
            diagnostics={"status": "skipped"},
        )


class OllamaTranslationProvider(TranslationProvider):
    name = "ollama"

    def __init__(
        self,
        model: str,
        endpoint: str = "http://127.0.0.1:11434",
        timeout_seconds: int = 60,
    ):
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def translate(self, request: TranslationRequest) -> TranslationResult:
        prompt = build_translation_prompt(request)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a local translation and prompt rewrite engine."},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "options": {"temperature": 0.1},
        }
        started = time.perf_counter()
        response = _post_json(f"{self.endpoint}/api/chat", payload, self.timeout_seconds)
        elapsed = int((time.perf_counter() - started) * 1000)
        content = response.get("message", {}).get("content", "").strip()
        return TranslationResult(
            provider=self.name,
            model=self.model,
            source_language=request.source_language,
            target_language=request.target_language,
            translated_text=content,
            prompt_sent=prompt,
            latency_ms=elapsed,
            diagnostics={"endpoint": self.endpoint},
        )


class OpenAICompatibleTranslationProvider(TranslationProvider):
    name = "openai-compatible"

    def __init__(
        self,
        model: str,
        endpoint: str = "http://127.0.0.1:1234/v1",
        timeout_seconds: int = 60,
        api_key: str = "local",
    ):
        self.model = model
        self.endpoint = endpoint.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.api_key = api_key

    def translate(self, request: TranslationRequest) -> TranslationResult:
        prompt = build_translation_prompt(request)
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": "You are a local translation and prompt rewrite engine."},
                {"role": "user", "content": prompt},
            ],
            "temperature": 0.1,
        }
        started = time.perf_counter()
        response = _post_json(
            f"{self.endpoint}/chat/completions",
            payload,
            self.timeout_seconds,
            headers={"Authorization": f"Bearer {self.api_key}"},
        )
        elapsed = int((time.perf_counter() - started) * 1000)
        choices = response.get("choices", [])
        content = ""
        if choices:
            content = choices[0].get("message", {}).get("content", "").strip()
        return TranslationResult(
            provider=self.name,
            model=self.model,
            source_language=request.source_language,
            target_language=request.target_language,
            translated_text=content,
            prompt_sent=prompt,
            latency_ms=elapsed,
            diagnostics={"endpoint": self.endpoint},
        )


def build_translation_prompt(request: TranslationRequest) -> str:
    locked_terms = ", ".join(request.locked_terms) if request.locked_terms else "none"
    return "\n".join(
        [
            "Rewrite the user request for a strong downstream model.",
            "",
            f"Source language: {request.source_language}",
            f"Target language: {request.target_language}",
            f"Task type: {request.task_type}",
            f"Target surface: {request.target_surface}",
            f"Locked technical terms: {locked_terms}",
            "",
            "Requirements:",
            "- Preserve code, file paths, commands, API names, and locked technical terms exactly.",
            "- Translate the user's intent into concise, professional English.",
            "- Keep constraints, preferences, and uncertainty explicit.",
            "- Do not answer the user task; only produce the rewritten downstream prompt content.",
            "- Return only the rewritten text, with no preface.",
            "",
            "User request:",
            "```text",
            request.source_text,
            "```",
        ]
    )


def get_translation_provider(
    provider: str,
    model: str | None,
    endpoint: str | None,
    timeout_seconds: int,
    api_key: str = "local",
) -> TranslationProvider:
    if provider == "none":
        return NoTranslationProvider()
    if provider == "ollama":
        if not model:
            raise ValueError("--model is required when --translator ollama is used")
        return OllamaTranslationProvider(
            model=model,
            endpoint=endpoint or "http://127.0.0.1:11434",
            timeout_seconds=timeout_seconds,
        )
    if provider == "openai-compatible":
        if not model:
            raise ValueError("--model is required when --translator openai-compatible is used")
        return OpenAICompatibleTranslationProvider(
            model=model,
            endpoint=endpoint or "http://127.0.0.1:1234/v1",
            timeout_seconds=timeout_seconds,
            api_key=api_key,
        )
    raise ValueError(f"Unknown translation provider: {provider}")


def _post_json(
    url: str,
    payload: dict,
    timeout_seconds: int,
    headers: dict[str, str] | None = None,
) -> dict:
    data = json.dumps(payload).encode("utf-8")
    request_headers = {"Content-Type": "application/json", **(headers or {})}
    req = urllib_request.Request(url, data=data, headers=request_headers, method="POST")
    try:
        with urllib_request.urlopen(req, timeout=timeout_seconds) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Translation provider HTTP error {exc.code}: {detail}") from exc
    except URLError as exc:
        raise RuntimeError(f"Cannot reach local translation provider at {url}: {exc}") from exc

