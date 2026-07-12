from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from promptbridge.utils import read_json, write_json


@dataclass(frozen=True)
class AppPaths:
    home: Path

    @property
    def providers_file(self) -> Path:
        return self.home / "providers.json"

    @property
    def glossary_file(self) -> Path:
        return self.home / "glossary.json"

    @property
    def artifacts_dir(self) -> Path:
        return self.home / "artifacts"

    @property
    def traces_dir(self) -> Path:
        return self.home / "traces"

    def ensure(self) -> None:
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)
        self.traces_dir.mkdir(parents=True, exist_ok=True)
        if not self.glossary_file.exists():
            write_json(self.glossary_file, {"schema_version": 1, "terms": []})


@dataclass(frozen=True)
class GlossaryTerm:
    term: str
    translation: str = ""
    note: str = ""

    def __post_init__(self) -> None:
        if not self.term.strip():
            raise ValueError("Glossary term cannot be empty.")
        if "[[PB_" in self.term.upper():
            raise ValueError("Glossary terms cannot use PromptBridge's reserved placeholder prefix.")
        object.__setattr__(self, "term", self.term.strip())
        object.__setattr__(self, "translation", self.translation.strip())
        object.__setattr__(self, "note", self.note.strip())

    def to_dict(self) -> dict[str, str]:
        return asdict(self)


class GlossaryStore:
    def __init__(self, path: Path):
        self.path = path

    def list(self) -> list[GlossaryTerm]:
        document = self._load()
        return [GlossaryTerm(**item) for item in document["terms"]]

    def add(self, term: GlossaryTerm) -> None:
        document = self._load()
        folded = term.term.casefold()
        document["terms"] = [
            item for item in document["terms"]
            if str(item.get("term", "")).casefold() != folded
        ]
        document["terms"].append(term.to_dict())
        document["terms"].sort(key=lambda item: str(item["term"]).casefold())
        write_json(self.path, document)

    def remove(self, term: str) -> None:
        document = self._load()
        folded = term.casefold()
        remaining = [
            item for item in document["terms"]
            if str(item.get("term", "")).casefold() != folded
        ]
        if len(remaining) == len(document["terms"]):
            raise ValueError(f"Unknown glossary term: {term}")
        document["terms"] = remaining
        write_json(self.path, document)

    def matching(self, text: str) -> list[GlossaryTerm]:
        folded = text.casefold()
        return [term for term in self.list() if term.term.casefold() in folded]

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            write_json(self.path, {"schema_version": 1, "terms": []})
        document = read_json(self.path)
        if not isinstance(document, dict) or not isinstance(document.get("terms"), list):
            raise ValueError(f"Invalid glossary file: {self.path}")
        document.setdefault("schema_version", 1)
        return document


class TraceStore:
    def __init__(self, directory: Path):
        self.directory = directory
        self.directory.mkdir(parents=True, exist_ok=True)

    def save(self, trace_id: str, payload: dict[str, Any]) -> Path:
        path = self.directory / f"{trace_id}.json"
        write_json(path, payload)
        return path

    def latest(self) -> tuple[Path, dict[str, Any]] | None:
        paths = sorted(self.directory.glob("*.json"), key=lambda path: path.stat().st_mtime)
        if not paths:
            return None
        path = paths[-1]
        return path, read_json(path)

    def summary(self) -> str:
        latest = self.latest()
        if latest is None:
            return "No traces found."
        path, trace = latest
        compiler = trace.get("compiler", {})
        execution = trace.get("execution", {})
        error = trace.get("error")
        lines = [
            f"Trace: {path.name}",
            f"- command: {trace.get('command')}",
            f"- status: {trace.get('status')}",
            f"- created_at: {trace.get('created_at')}",
            f"- input_chars: {trace.get('input', {}).get('characters')}",
            f"- context_chars: {trace.get('input', {}).get('page_context_characters')}",
            f"- compiler: {compiler.get('provider')} / {compiler.get('model')}",
            f"- compiler_latency_ms: {compiler.get('latency_ms')}",
        ]
        if execution:
            lines.extend(
                [
                    f"- execution: {execution.get('provider')} / {execution.get('model')}",
                    f"- execution_latency_ms: {execution.get('latency_ms')}",
                    f"- execution_usage: {execution.get('usage')}",
                ]
            )
        if error:
            lines.append(f"- error: {error.get('type')}: {error.get('message')}")
        return "\n".join(lines)
