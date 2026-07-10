from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class TranslationRequest:
    trace_id: str
    source_text: str
    source_language: str
    target_language: str
    task_type: str
    locked_terms: list[str]
    target_surface: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TranslationResult:
    provider: str
    model: str | None
    source_language: str
    target_language: str
    translated_text: str
    prompt_sent: str | None
    latency_ms: int
    diagnostics: dict

    def to_dict(self) -> dict:
        return asdict(self)

