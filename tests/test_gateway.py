from __future__ import annotations

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest

from promptbridge.config import ProfileStore, ProviderProfile
from promptbridge.gateway import PromptBridge
from promptbridge.providers import LLMClient, ProviderError
from promptbridge.utils import read_json


class _Secrets:
    def __init__(self, values: dict[str, str]):
        self.values = values

    def get(self, profile: ProviderProfile) -> str | None:
        return self.values.get(profile.name)


class _MockHandler(BaseHTTPRequestHandler):
    requests: list[dict] = []
    transient_failures = 0
    fail_chat = False

    def do_POST(self) -> None:  # noqa: N802
        size = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(size).decode("utf-8"))
        type(self).requests.append(
            {"path": self.path, "headers": dict(self.headers.items()), "body": body}
        )
        if type(self).transient_failures:
            type(self).transient_failures -= 1
            self._send(429, {"error": {"message": "retry"}}, retry_after="0")
            return
        if self.path.endswith("/responses"):
            self._send(
                200,
                {
                    "id": "resp_compile",
                    "status": "completed",
                    "model": "compiler-model",
                    "output": [
                        {
                            "type": "message",
                            "content": [
                                {
                                    "type": "output_text",
                                    "text": json.dumps(
                                        {
                                            "source_language": "Simplified Chinese",
                                            "objective": "Review the architecture.",
                                            "context": [],
                                            "input_material": [],
                                            "constraints": [],
                                            "expected_deliverable": None,
                                            "output_preferences": [],
                                        }
                                    ),
                                }
                            ],
                        }
                    ],
                    "usage": {"input_tokens": 10, "output_tokens": 4},
                },
            )
            return
        if type(self).fail_chat:
            self._send(400, {"error": {"message": "invalid request"}})
            return
        self._send(
            200,
            {
                "id": "chat_execute",
                "model": "runner-model",
                "choices": [
                    {
                        "message": {"content": "Architecture review completed."},
                        "finish_reason": "stop",
                    }
                ],
                "usage": {"prompt_tokens": 20, "completion_tokens": 6},
            },
        )

    def _send(self, status: int, body: dict, retry_after: str | None = None) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.send_header("x-request-id", "req_test")
        if retry_after is not None:
            self.send_header("Retry-After", retry_after)
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, format: str, *args) -> None:
        return


class GatewayIntegrationTest(unittest.TestCase):
    def setUp(self) -> None:
        _MockHandler.requests = []
        _MockHandler.transient_failures = 0
        _MockHandler.fail_chat = False
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), _MockHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def test_two_stage_run_uses_independent_provider_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)
            profiles = ProfileStore(home / "providers.json")
            base_url = f"http://127.0.0.1:{self.server.server_port}/v1"
            profiles.add(ProviderProfile("compiler", "responses", base_url, "compiler-model"))
            profiles.add(ProviderProfile("runner", "chat", base_url, "runner-model"))
            gateway = PromptBridge(
                home,
                profile_store=profiles,
                secret_store=_Secrets({"compiler": "compile-key", "runner": "run-key"}),  # type: ignore[arg-type]
            )

            result = gateway.run(
                "请评审这个架构",
                provider="runner",
                compiler_provider="compiler",
                max_retries=0,
            )

            self.assertEqual(result.answer, "Architecture review completed.")
            self.assertNotIn("Response Language", result.prompt.text)
            self.assertEqual([item["path"] for item in _MockHandler.requests], [
                "/v1/responses",
                "/v1/chat/completions",
            ])
            self.assertEqual(_MockHandler.requests[0]["headers"]["Authorization"], "Bearer compile-key")
            self.assertEqual(_MockHandler.requests[1]["headers"]["Authorization"], "Bearer run-key")
            trace = read_json(result.trace_path)
            self.assertEqual(trace["schema_version"], 2)
            self.assertEqual(trace["status"], "completed")
            self.assertEqual(trace["compiler"]["provider"], "compiler")
            self.assertEqual(trace["execution"]["provider"], "runner")
            self.assertEqual(trace["context"]["source_language"], "Simplified Chinese")
            self.assertEqual(trace["context"]["prompt_language"], "English")
            trace_text = result.trace_path.read_text(encoding="utf-8")
            self.assertNotIn("compile-key", trace_text)
            self.assertNotIn("run-key", trace_text)
            self.assertNotIn("请评审这个架构", trace_text)

            _MockHandler.fail_chat = True
            with self.assertRaises(ProviderError):
                gateway.run(
                    "再次评审",
                    provider="runner",
                    compiler_provider="compiler",
                    max_retries=0,
                )
            _, failed_trace = gateway.traces.latest()  # type: ignore[misc]
            self.assertEqual(failed_trace["status"], "failed")
            self.assertEqual(failed_trace["failed_stage"], "execute")
            self.assertEqual(failed_trace["compiler"]["provider"], "compiler")

    def test_retry_after_is_honored(self) -> None:
        _MockHandler.transient_failures = 1
        profile = ProviderProfile(
            "runner",
            "chat",
            f"http://127.0.0.1:{self.server.server_port}/v1",
            "runner-model",
        )
        client = LLMClient(profile, api_key="key", max_retries=1, sleep=lambda _: None)
        response = client.generate(instructions="Test", input_text="Test", stage="retry")
        self.assertEqual(response.text, "Architecture review completed.")
        self.assertEqual(len(_MockHandler.requests), 2)


if __name__ == "__main__":
    unittest.main()
