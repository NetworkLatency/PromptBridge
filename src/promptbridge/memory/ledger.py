from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path
import json

from promptbridge.utils import new_id, now_iso, write_text


@dataclass(frozen=True)
class MemoryEvent:
    event_id: str
    type: str
    project_id: str
    source: str
    text: str
    timestamp: str
    metadata: dict

    @classmethod
    def create(
        cls,
        event_type: str,
        project_id: str,
        source: str,
        text: str,
        metadata: dict | None = None,
    ) -> "MemoryEvent":
        return cls(
            event_id=new_id("evt"),
            type=event_type,
            project_id=project_id,
            source=source,
            text=text,
            timestamp=now_iso(),
            metadata=metadata or {},
        )

    def to_dict(self) -> dict:
        return asdict(self)


class MemoryLedger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            write_text(self.path, "")

    def append(self, event: MemoryEvent) -> None:
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")

    def read_events(self, limit: int | None = None) -> list[MemoryEvent]:
        if not self.path.exists():
            return []
        rows: list[MemoryEvent] = []
        for line in self.path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            payload = json.loads(line)
            rows.append(MemoryEvent(**payload))
        if limit is None:
            return rows
        return rows[-limit:]

