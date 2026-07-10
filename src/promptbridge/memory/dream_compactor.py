from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from promptbridge.memory.files import MemoryWorkspace
from promptbridge.memory.ledger import MemoryLedger, MemoryEvent
from promptbridge.utils import now_iso, write_text


NINE_SECTIONS = [
    "Primary User Goal",
    "Current Task",
    "Project Decisions",
    "Translation Policy",
    "Glossary",
    "User Corrections",
    "Failure Cases",
    "Open Threads",
    "Next Action Hints",
]


@dataclass(frozen=True)
class DreamPatch:
    path: Path
    text: str


class DreamCompactor:
    def __init__(self, workspace: MemoryWorkspace):
        self.workspace = workspace
        self.ledger = MemoryLedger(workspace.ledger_path)

    def propose_patch(self, project_id: str) -> DreamPatch:
        self.workspace.ensure_defaults()
        events = [
            event for event in self.ledger.read_events(limit=80)
            if event.project_id == project_id and not event.type.startswith("dream_")
        ]
        memory_files = self.workspace.read_memory_files()
        patch_text = self._render_patch(project_id, events, memory_files)
        safe_time = now_iso().replace(":", "").replace("+", "p")
        path = self.workspace.patches_dir / f"memory_patch_{project_id}_{safe_time}.md"
        write_text(path, patch_text)
        self.ledger.append(
            MemoryEvent.create(
                event_type="dream_patch_proposed",
                project_id=project_id,
                source="dream_compactor",
                text=f"Generated memory patch proposal: {path.name}",
                metadata={"patch_path": str(path), "event_count": len(events)},
            )
        )
        return DreamPatch(path=path, text=patch_text)

    def _render_patch(
        self,
        project_id: str,
        events: list[MemoryEvent],
        memory_files: dict[str, str],
    ) -> str:
        grouped = {section: [] for section in NINE_SECTIONS}
        for event in events:
            section = self._classify_event(event)
            grouped[section].append(event)

        lines = [
            f"# MemoryPatch Proposal: {project_id}",
            "",
            f"Generated: {now_iso()}",
            "",
            "This file is a proposal only. Review it before editing files under `workspace/memory`.",
            "",
            "## Existing Memory Files Reviewed",
            "",
        ]
        for path in sorted(memory_files):
            lines.append(f"- `{path}`")

        lines.extend(["", "## Proposed 9-Section Consolidation", ""])
        for section in NINE_SECTIONS:
            lines.append(f"### {section}")
            lines.append("")
            unique_events = self._unique_events(grouped[section])
            if unique_events:
                for event in unique_events[-8:]:
                    short_text = event.text.replace("\n", " ").strip()
                    lines.append(f"+ {short_text}")
                    lines.append(
                        f"  - source: `{event.source}`, event: `{event.event_id}`, time: `{event.timestamp}`"
                    )
            else:
                lines.append("- No new proposal from recent events.")
            lines.append("")

        lines.extend(
            [
                "## Suggested Manual Application",
                "",
                "- Move stable decisions into `workspace/memory/decisions.md`.",
                "- Move user-level preferences into `workspace/memory/user_profile.md`.",
                "- Move recurring terminology into `workspace/memory/glossary.yaml`.",
                "- Keep uncertain or incomplete items in `workspace/memory/open_threads.md`.",
                "- Do not delete raw ledger events.",
                "",
            ]
        )
        return "\n".join(lines)

    def _unique_events(self, events: list[MemoryEvent]) -> list[MemoryEvent]:
        seen: set[tuple[str, str]] = set()
        unique: list[MemoryEvent] = []
        for event in events:
            key = (event.type, event.text.strip())
            if key in seen:
                continue
            seen.add(key)
            unique.append(event)
        return unique

    def _classify_event(self, event: MemoryEvent) -> str:
        text = event.text.lower()
        if event.type == "user_correction" or "correction" in text:
            return "User Corrections"
        if "translate" in text or "translation" in text or "术语" in event.text:
            return "Translation Policy"
        if "failure" in text or "avoid" in text or "不要" in event.text:
            return "Failure Cases"
        if "decision" in text or "must" in text or "should" in text or "必须" in event.text:
            return "Project Decisions"
        if "next" in text or "todo" in text or "后续" in event.text:
            return "Next Action Hints"
        if "goal" in text or "resume" in text or "求职" in event.text:
            return "Primary User Goal"
        if "open" in text or "unclear" in text or "待" in event.text:
            return "Open Threads"
        return "Current Task"
