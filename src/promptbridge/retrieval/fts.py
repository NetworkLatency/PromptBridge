from __future__ import annotations

from pathlib import Path
import sqlite3

from promptbridge.memory.files import MemoryWorkspace
from promptbridge.retrieval.types import RetrievalHit
from promptbridge.utils import compact_snippet, first_heading, read_text


def search_fts(query: str, workspace: MemoryWorkspace, limit: int = 8) -> tuple[list[RetrievalHit], dict]:
    workspace.ensure_defaults()
    db_path = workspace.index_dir / "memory_fts.sqlite"
    diagnostics = {"fts5_enabled": True, "fallback": None}
    try:
        conn = sqlite3.connect(db_path)
        _rebuild_index(conn, workspace)
        hits = _query_fts(conn, query, limit)
        conn.close()
        return hits, diagnostics
    except sqlite3.OperationalError as exc:
        diagnostics["fts5_enabled"] = False
        diagnostics["fallback"] = f"like_scan: {exc}"
        return _like_scan(query, workspace, limit), diagnostics


def _rebuild_index(conn: sqlite3.Connection, workspace: MemoryWorkspace) -> None:
    conn.execute(
        "CREATE VIRTUAL TABLE IF NOT EXISTS memory_fts "
        "USING fts5(ref_id UNINDEXED, path UNINDEXED, title, body)"
    )
    conn.execute("DELETE FROM memory_fts")
    for idx, path in enumerate(workspace.iter_memory_files()):
        body = read_text(path)
        title = first_heading(body, path.name)
        conn.execute(
            "INSERT INTO memory_fts(ref_id, path, title, body) VALUES (?, ?, ?, ?)",
            (f"memory:{idx}", str(path), title, body),
        )
    conn.commit()


def _query_fts(conn: sqlite3.Connection, query: str, limit: int) -> list[RetrievalHit]:
    try:
        rows = conn.execute(
            "SELECT ref_id, path, title, body, bm25(memory_fts) AS rank "
            "FROM memory_fts WHERE memory_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (query, limit),
        ).fetchall()
    except sqlite3.OperationalError:
        like = f"%{query}%"
        rows = conn.execute(
            "SELECT ref_id, path, title, body, 0.0 AS rank "
            "FROM memory_fts WHERE body LIKE ? OR title LIKE ? LIMIT ?",
            (like, like, limit),
        ).fetchall()

    hits: list[RetrievalHit] = []
    for ref_id, path, title, body, rank in rows:
        score = 1.0 / (1.0 + abs(float(rank)))
        hits.append(
            RetrievalHit(
                ref_id=ref_id,
                strategy="sqlite_fts5",
                source="memory_file",
                path=path,
                title=title,
                snippet=compact_snippet(body, query),
                score=score,
                metadata={},
            )
        )
    return hits


def _like_scan(query: str, workspace: MemoryWorkspace, limit: int) -> list[RetrievalHit]:
    hits: list[RetrievalHit] = []
    query_lower = query.lower()
    for idx, path in enumerate(workspace.iter_memory_files()):
        body = read_text(path)
        if query_lower not in body.lower():
            continue
        hits.append(
            RetrievalHit(
                ref_id=f"memory_like:{idx}",
                strategy="sqlite_like_fallback",
                source="memory_file",
                path=str(Path(path)),
                title=first_heading(body, path.name),
                snippet=compact_snippet(body, query),
                score=0.55,
                metadata={},
            )
        )
        if len(hits) >= limit:
            break
    return hits

