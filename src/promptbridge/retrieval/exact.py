from __future__ import annotations

from promptbridge.memory.files import MemoryWorkspace
from promptbridge.retrieval.types import RetrievalHit


def exact_lookup(query: str, workspace: MemoryWorkspace, limit: int = 5) -> list[RetrievalHit]:
    query_lower = query.lower()
    hits: list[RetrievalHit] = []
    for index, term in enumerate(workspace.read_glossary_terms()):
        term_lower = term.term.lower()
        zh_lower = term.zh.lower()
        if term_lower in query_lower or (zh_lower and term.zh in query):
            hits.append(
                RetrievalHit(
                    ref_id=f"glossary:{index}",
                    strategy="exact_lookup",
                    source="glossary",
                    path=term.source_path,
                    title=term.term,
                    snippet=f"{term.term} / {term.zh}: {term.note}",
                    score=1.0,
                    metadata={"term": term.term, "zh": term.zh},
                )
            )
    return hits[:limit]

