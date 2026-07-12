from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
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


_ARTIFACT_SUFFIXES = (".prompt.md", ".response.md")


@dataclass(frozen=True)
class StorageGroup:
    trace_id: str
    paths: tuple[Path, ...]
    modified_at: datetime
    has_trace: bool

    @property
    def bytes(self) -> int:
        return sum(path.stat().st_size for path in self.paths if path.exists())


@dataclass(frozen=True)
class StorageStatus:
    home: Path
    home_exists: bool
    artifact_files: int
    artifact_bytes: int
    trace_files: int
    trace_bytes: int
    managed_groups: int
    orphan_artifacts: int
    unmanaged_files: int
    oldest: datetime | None
    newest: datetime | None

    @property
    def total_files(self) -> int:
        return self.artifact_files + self.trace_files

    @property
    def total_bytes(self) -> int:
        return self.artifact_bytes + self.trace_bytes


@dataclass(frozen=True)
class CleanupPlan:
    cutoff: datetime
    groups: tuple[StorageGroup, ...]

    @property
    def files(self) -> int:
        return sum(len(group.paths) for group in self.groups)

    @property
    def bytes(self) -> int:
        return sum(group.bytes for group in self.groups)


@dataclass(frozen=True)
class CleanupResult:
    deleted_files: int
    deleted_bytes: int


class StorageMaintenance:
    """Inspect and remove only trace-linked runtime files."""

    def __init__(self, paths: AppPaths):
        self.paths = paths

    def status(self) -> StorageStatus:
        groups, artifact_files, trace_files, managed_paths = self._collect()
        all_files = artifact_files + trace_files
        timestamps = [_modified_at(path) for path in all_files]
        trace_ids = {group.trace_id for group in groups if group.has_trace}
        orphan_artifacts = sum(
            1
            for path in artifact_files
            if (trace_id := _artifact_trace_id(path)) is not None and trace_id not in trace_ids
        )
        return StorageStatus(
            home=self.paths.home,
            home_exists=self.paths.home.exists(),
            artifact_files=len(artifact_files),
            artifact_bytes=sum(path.stat().st_size for path in artifact_files),
            trace_files=len(trace_files),
            trace_bytes=sum(path.stat().st_size for path in trace_files),
            managed_groups=len(groups),
            orphan_artifacts=orphan_artifacts,
            unmanaged_files=len(set(all_files) - managed_paths),
            oldest=min(timestamps) if timestamps else None,
            newest=max(timestamps) if timestamps else None,
        )

    def cleanup_plan(
        self,
        older_than_days: int,
        *,
        now: datetime | None = None,
    ) -> CleanupPlan:
        if older_than_days < 0:
            raise ValueError("older_than_days cannot be negative.")
        reference = now or datetime.now(timezone.utc)
        if reference.tzinfo is None:
            raise ValueError("now must include timezone information.")
        cutoff = reference.astimezone(timezone.utc) - timedelta(days=older_than_days)
        groups, _, _, _ = self._collect()
        candidates = tuple(group for group in groups if group.modified_at < cutoff)
        return CleanupPlan(cutoff=cutoff, groups=candidates)

    def apply(self, plan: CleanupPlan) -> CleanupResult:
        allowed_directories = set(self._validated_storage_directories())
        deleted_files = 0
        deleted_bytes = 0
        for group in plan.groups:
            for path in group.paths:
                if path.parent.resolve() not in allowed_directories:
                    raise ValueError(f"Refusing to delete outside PromptBridge storage: {path}")
                managed_trace_id = _trace_file_id(path) or _artifact_trace_id(path)
                if managed_trace_id != group.trace_id:
                    raise ValueError(f"Refusing to delete an unmanaged storage file: {path}")
                if not path.exists():
                    continue
                deleted_bytes += path.stat().st_size
                path.unlink()
                deleted_files += 1
        return CleanupResult(deleted_files=deleted_files, deleted_bytes=deleted_bytes)

    def _collect(
        self,
    ) -> tuple[tuple[StorageGroup, ...], tuple[Path, ...], tuple[Path, ...], set[Path]]:
        self._validated_storage_directories()
        artifact_files = _directory_files(self.paths.artifacts_dir)
        trace_files = _directory_files(self.paths.traces_dir)
        members: dict[str, list[Path]] = {}
        trace_ids: set[str] = set()
        managed_paths: set[Path] = set()

        for path in trace_files:
            trace_id = _trace_file_id(path)
            if trace_id is None:
                continue
            members.setdefault(trace_id, []).append(path)
            trace_ids.add(trace_id)
            managed_paths.add(path)

        for path in artifact_files:
            trace_id = _artifact_trace_id(path)
            if trace_id is None:
                continue
            members.setdefault(trace_id, []).append(path)
            managed_paths.add(path)

        groups = tuple(
            StorageGroup(
                trace_id=trace_id,
                paths=tuple(sorted(paths, key=lambda path: path.name)),
                modified_at=max(_modified_at(path) for path in paths),
                has_trace=trace_id in trace_ids,
            )
            for trace_id, paths in sorted(members.items())
        )
        return groups, artifact_files, trace_files, managed_paths

    def _validated_storage_directories(self) -> tuple[Path, Path]:
        home = self.paths.home.resolve()
        directories = (self.paths.artifacts_dir.resolve(), self.paths.traces_dir.resolve())
        for directory in directories:
            if not directory.is_relative_to(home):
                raise ValueError(f"Storage directory escapes PromptBridge home: {directory}")
        return directories


def _directory_files(directory: Path) -> tuple[Path, ...]:
    if not directory.exists():
        return ()
    if not directory.is_dir():
        raise ValueError(f"Expected a storage directory: {directory}")
    return tuple(
        sorted((path for path in directory.iterdir() if path.is_file()), key=lambda path: path.name)
    )


def _trace_file_id(path: Path) -> str | None:
    name = path.name
    if name.startswith("trace_") and name.endswith(".json"):
        return name[: -len(".json")]
    return None


def _artifact_trace_id(path: Path) -> str | None:
    name = path.name
    for suffix in _ARTIFACT_SUFFIXES:
        if name.startswith("trace_") and name.endswith(suffix):
            return name[: -len(suffix)]
    return None


def _modified_at(path: Path) -> datetime:
    return datetime.fromtimestamp(path.stat().st_mtime, timezone.utc)
