from __future__ import annotations

from promptbridge.memory.files import MemoryWorkspace
from promptbridge.retrieval.types import RetrievalHit
from promptbridge.utils import compact_snippet, first_heading, read_text, split_terms


def grep_search(query: str, workspace: MemoryWorkspace, limit: int = 8) -> list[RetrievalHit]:
    terms = split_terms(query)
    if not terms:
        terms = [query.lower()]
    hits: list[RetrievalHit] = []
    for idx, path in enumerate(workspace.iter_memory_files()):
        body = read_text(path)
        lower_body = body.lower()
        score = 0
        for term in terms:
            score += lower_body.count(term.lower())
        if score <= 0:
            continue
        hits.append(
            RetrievalHit(
                ref_id=f"grep:{idx}",
                strategy="grep_like",
                source="memory_file",
                path=str(path),
                title=first_heading(body, path.name),
                snippet=compact_snippet(body, terms[0]),
                score=min(0.95, 0.25 + score * 0.1),
                metadata={"matched_terms": terms},
            )
        )
    hits.sort(key=lambda hit: hit.score, reverse=True)
    return hits[:limit]

