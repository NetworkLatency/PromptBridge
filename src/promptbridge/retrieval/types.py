from __future__ import annotations

from dataclasses import dataclass, asdict


@dataclass(frozen=True)
class RetrievalHit:
    ref_id: str
    strategy: str
    source: str
    path: str
    title: str
    snippet: str
    score: float
    metadata: dict

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalResult:
    hits: list[RetrievalHit]
    diagnostics: dict

    def to_dict(self) -> dict:
        return {
            "hits": [hit.to_dict() for hit in self.hits],
            "diagnostics": self.diagnostics,
        }

