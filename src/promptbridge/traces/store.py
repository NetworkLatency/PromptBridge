from __future__ import annotations

from pathlib import Path

from promptbridge.utils import read_json, write_json


class TraceStore:
    def __init__(self, traces_dir: Path):
        self.traces_dir = traces_dir
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    def save(self, trace_id: str, payload: dict) -> Path:
        path = self.traces_dir / f"{trace_id}.json"
        write_json(path, payload)
        return path

    def latest(self) -> tuple[Path, dict] | None:
        traces = sorted(self.traces_dir.glob("*.json"), key=lambda path: path.stat().st_mtime)
        if not traces:
            return None
        path = traces[-1]
        return path, read_json(path)

    def load(self, trace_id: str) -> tuple[Path, dict]:
        path = self.traces_dir / f"{trace_id}.json"
        return path, read_json(path)


def format_trace_summary(path: Path, trace: dict) -> str:
    retrieval = trace.get("retrieval", {})
    hits = retrieval.get("hits", [])
    kernel = trace.get("kernel", {})
    compiled = trace.get("compiled_prompt", {})
    translation = trace.get("translation", {})
    target = trace.get("target_package", {})
    lines = [
        f"Trace: {path.name}",
        f"- command: {trace.get('command')}",
        f"- created_at: {trace.get('created_at')}",
        f"- task_type: {kernel.get('task_type')}",
        f"- source_language: {kernel.get('source_language')}",
        f"- translation_provider: {translation.get('provider')}",
        f"- translation_model: {translation.get('model')}",
        f"- target: {target.get('target')}",
        f"- segment_count: {len(kernel.get('segments', []))}",
        f"- retrieval_hits: {len(hits)}",
        f"- compiled_prompt_tokens_estimate: {compiled.get('token_estimate')}",
    ]
    if hits:
        lines.append("- top_hits:")
        for hit in hits[:5]:
            lines.append(
                f"  - [{hit.get('strategy')}] {hit.get('title')} ({hit.get('score')})"
            )
    return "\n".join(lines)
