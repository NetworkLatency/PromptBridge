from __future__ import annotations

from promptbridge.memory.files import MemoryWorkspace
from promptbridge.retrieval.exact import exact_lookup
from promptbridge.retrieval.fts import search_fts
from promptbridge.retrieval.grep import grep_search
from promptbridge.retrieval.types import RetrievalHit, RetrievalResult


class RetrievalRouter:
    def __init__(self, workspace: MemoryWorkspace):
        self.workspace = workspace

    def search(self, query: str, limit: int = 8) -> RetrievalResult:
        self.workspace.ensure_defaults()
        diagnostics: dict = {"strategies": []}

        exact_hits = exact_lookup(query, self.workspace, limit=limit)
        diagnostics["strategies"].append({"name": "exact_lookup", "hits": len(exact_hits)})

        fts_hits, fts_diagnostics = search_fts(query, self.workspace, limit=limit)
        diagnostics["strategies"].append(
            {"name": "sqlite_fts5", "hits": len(fts_hits), **fts_diagnostics}
        )

        grep_hits = grep_search(query, self.workspace, limit=limit)
        diagnostics["strategies"].append({"name": "grep_like", "hits": len(grep_hits)})

        if any(hit.source == "glossary" for hit in exact_hits):
            fts_hits = self._drop_glossary_file_hits(fts_hits)
            grep_hits = self._drop_glossary_file_hits(grep_hits)

        merged = self._dedupe(exact_hits + fts_hits + grep_hits)
        merged.sort(key=lambda hit: hit.score, reverse=True)
        return RetrievalResult(hits=merged[:limit], diagnostics=diagnostics)

    def _dedupe(self, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        seen: set[tuple[str, str]] = set()
        deduped: list[RetrievalHit] = []
        for hit in hits:
            key = (hit.path, hit.title)
            if key in seen:
                continue
            seen.add(key)
            deduped.append(hit)
        return deduped

    def _drop_glossary_file_hits(self, hits: list[RetrievalHit]) -> list[RetrievalHit]:
        return [
            hit for hit in hits
            if not hit.path.replace("\\", "/").endswith("/glossary.yaml")
        ]
