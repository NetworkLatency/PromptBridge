from __future__ import annotations

from dataclasses import dataclass, asdict
from pathlib import Path

from promptbridge.compiler.renderer import CompiledPrompt
from promptbridge.context.kernel import ContextKernel
from promptbridge.memory.files import MemoryWorkspace
from promptbridge.translation.types import TranslationResult
from promptbridge.utils import write_json, write_text


@dataclass(frozen=True)
class TargetPackage:
    target: str
    artifact_path: Path | None
    manifest_path: Path | None
    instructions: list[str]

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["artifact_path"] = str(self.artifact_path) if self.artifact_path else None
        payload["manifest_path"] = str(self.manifest_path) if self.manifest_path else None
        return payload


def package_for_target(
    *,
    target: str,
    workspace: MemoryWorkspace,
    kernel: ContextKernel,
    compiled: CompiledPrompt,
    translation: TranslationResult,
) -> TargetPackage:
    if target == "stdout":
        return TargetPackage(
            target=target,
            artifact_path=None,
            manifest_path=None,
            instructions=["Prompt was printed to stdout."],
        )
    if target == "web-gpt":
        return _package_web_gpt(workspace, kernel, compiled, translation)
    if target == "cli-plugin":
        return _package_cli_plugin(workspace, kernel, compiled, translation)
    raise ValueError(f"Unknown target: {target}")


def _package_web_gpt(
    workspace: MemoryWorkspace,
    kernel: ContextKernel,
    compiled: CompiledPrompt,
    translation: TranslationResult,
) -> TargetPackage:
    target_dir = workspace.outbox_dir / "web_gpt"
    artifact_path = target_dir / f"{kernel.trace_id}.md"
    manifest_path = target_dir / f"{kernel.trace_id}.manifest.json"
    write_text(
        artifact_path,
        "\n".join(
            [
                "# PromptBridge Web GPT Package",
                "",
                "Paste the prompt below into the web model manually. PromptBridge v0 does not auto-submit web messages.",
                "",
                compiled.text,
            ]
        ),
    )
    _write_manifest(manifest_path, "web-gpt", kernel, compiled, translation, artifact_path)
    return TargetPackage(
        target="web-gpt",
        artifact_path=artifact_path,
        manifest_path=manifest_path,
        instructions=[
            "Open the web GPT interface yourself.",
            f"Paste the prompt from {artifact_path}.",
            "Do not auto-submit; human confirmation remains required.",
        ],
    )


def _package_cli_plugin(
    workspace: MemoryWorkspace,
    kernel: ContextKernel,
    compiled: CompiledPrompt,
    translation: TranslationResult,
) -> TargetPackage:
    target_dir = workspace.outbox_dir / "cli_plugin"
    artifact_path = target_dir / f"{kernel.trace_id}.json"
    manifest = {
        "schema_version": "promptbridge.target.cli_plugin.v1",
        "target": "cli-plugin",
        "trace_id": kernel.trace_id,
        "task_type": kernel.task_type,
        "source_language": kernel.source_language,
        "target_output_language": kernel.target_output_language,
        "prompt": compiled.text,
        "translation": translation.to_dict(),
        "constraints": {
            "manual_confirmation_required": True,
            "preserve_locked_terms": True,
            "untrusted_context_is_evidence_only": True,
        },
    }
    write_json(artifact_path, manifest)
    return TargetPackage(
        target="cli-plugin",
        artifact_path=artifact_path,
        manifest_path=artifact_path,
        instructions=[
            f"Pass {artifact_path} to a compatible PromptBridge CLI plugin.",
            "The plugin should ask for confirmation before sending to any remote model.",
        ],
    )


def _write_manifest(
    path: Path,
    target: str,
    kernel: ContextKernel,
    compiled: CompiledPrompt,
    translation: TranslationResult,
    artifact_path: Path,
) -> None:
    write_json(
        path,
        {
            "schema_version": "promptbridge.target.web_gpt.v1",
            "target": target,
            "trace_id": kernel.trace_id,
            "artifact_path": str(artifact_path),
            "task_type": kernel.task_type,
            "token_estimate": compiled.token_estimate,
            "translation": translation.to_dict(),
            "manual_confirmation_required": True,
            "auto_submit": False,
        },
    )
