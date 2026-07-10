from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from promptbridge.compiler.reconstruct import ReconstructedResponse, reconstruct_response
from promptbridge.compiler.renderer import CompiledPrompt, PromptCompiler
from promptbridge.context.kernel import ContextKernel, build_context_kernel
from promptbridge.memory.dream_compactor import DreamCompactor, DreamPatch
from promptbridge.memory.files import MemoryWorkspace
from promptbridge.memory.ledger import MemoryEvent, MemoryLedger
from promptbridge.retrieval.router import RetrievalRouter
from promptbridge.retrieval.types import RetrievalResult
from promptbridge.safety.pii import redact_pii
from promptbridge.targets.adapters import TargetPackage, package_for_target
from promptbridge.translation.providers import get_translation_provider
from promptbridge.translation.types import TranslationRequest, TranslationResult
from promptbridge.traces.store import TraceStore
from promptbridge.utils import new_id, now_iso, read_text, write_text


@dataclass(frozen=True)
class CompileResult:
    trace_id: str
    prompt_path: Path
    trace_path: Path
    target_package: TargetPackage
    kernel: ContextKernel
    retrieval: RetrievalResult
    compiled_prompt: CompiledPrompt
    translation_result: TranslationResult
    pii_findings: list[dict]


@dataclass(frozen=True)
class ReconstructionResult:
    trace_id: str
    output_path: Path
    trace_path: Path
    response: ReconstructedResponse


class PromptBridgeOrchestrator:
    def __init__(self, workspace_root: str | Path = "workspace"):
        self.workspace = MemoryWorkspace.from_path(workspace_root)
        self.compiler = PromptCompiler()

    def init_workspace(self) -> MemoryWorkspace:
        self.workspace.ensure_defaults()
        return self.workspace

    def compile(
        self,
        user_input: str,
        project_id: str = "promptbridge",
        max_tokens: int = 6000,
        translator: str = "none",
        model: str | None = None,
        endpoint: str | None = None,
        target: str = "stdout",
        translation_timeout: int = 60,
        api_key: str = "local",
    ) -> CompileResult:
        self.workspace.ensure_defaults()
        trace_id = new_id("trace")
        redacted_input, pii_findings = redact_pii(user_input)
        router = RetrievalRouter(self.workspace)
        retrieval = router.search(redacted_input)
        kernel = build_context_kernel(
            trace_id=trace_id,
            user_input=redacted_input,
            project_id=project_id,
            retrieval_hits=retrieval.hits,
            max_tokens=max_tokens,
        )
        translation_result = self._translate_for_downstream(
            kernel=kernel,
            translator=translator,
            model=model,
            endpoint=endpoint,
            target=target,
            translation_timeout=translation_timeout,
            api_key=api_key,
        )
        compiled = self.compiler.render(
            kernel,
            translation=translation_result,
            target_surface=target,
        )
        prompt_path = self.workspace.compiled_dir / f"{trace_id}.md"
        write_text(prompt_path, compiled.text)
        target_package = package_for_target(
            target=target,
            workspace=self.workspace,
            kernel=kernel,
            compiled=compiled,
            translation=translation_result,
        )

        ledger = MemoryLedger(self.workspace.ledger_path)
        ledger.append(
            MemoryEvent.create(
                event_type="compile_request",
                project_id=project_id,
                source="cli",
                text=redacted_input,
                metadata={
                    "trace_id": trace_id,
                    "pii_redacted": bool(pii_findings),
                    "task_type": kernel.task_type,
                    "translator": translator,
                    "translation_model": model,
                    "target": target,
                },
            )
        )

        trace_payload = {
            "trace_id": trace_id,
            "created_at": now_iso(),
            "command": "compile",
            "input": {"text": redacted_input, "pii_findings": pii_findings},
            "retrieval": retrieval.to_dict(),
            "kernel": kernel.to_dict(),
            "translation": translation_result.to_dict(),
            "compiled_prompt": {
                "path": str(prompt_path),
                "token_estimate": compiled.token_estimate,
                "stats": compiled.stats,
            },
            "target_package": target_package.to_dict(),
        }
        trace_path = TraceStore(self.workspace.traces_dir).save(trace_id, trace_payload)
        return CompileResult(
            trace_id=trace_id,
            prompt_path=prompt_path,
            trace_path=trace_path,
            target_package=target_package,
            kernel=kernel,
            retrieval=retrieval,
            compiled_prompt=compiled,
            translation_result=translation_result,
            pii_findings=pii_findings,
        )

    def search_memory(self, query: str, limit: int = 8) -> RetrievalResult:
        self.workspace.ensure_defaults()
        return RetrievalRouter(self.workspace).search(query, limit=limit)

    def reconstruct(
        self,
        response_path: str | Path,
        target_language: str = "zh",
        project_id: str = "promptbridge",
    ) -> ReconstructionResult:
        self.workspace.ensure_defaults()
        trace_id = new_id("trace")
        response_text = read_text(Path(response_path))
        reconstructed = reconstruct_response(
            response_text,
            target_language,
            self.workspace.read_glossary_terms(),
        )
        output_path = self.workspace.reconstructed_dir / f"{trace_id}.md"
        write_text(output_path, reconstructed.text)

        ledger = MemoryLedger(self.workspace.ledger_path)
        ledger.append(
            MemoryEvent.create(
                event_type="response_reconstructed",
                project_id=project_id,
                source="cli",
                text=f"Reconstructed response from {response_path}",
                metadata={
                    "trace_id": trace_id,
                    "target_language": target_language,
                    "output_path": str(output_path),
                },
            )
        )
        trace_payload = {
            "trace_id": trace_id,
            "created_at": now_iso(),
            "command": "reconstruct",
            "input": {"response_path": str(response_path), "target_language": target_language},
            "reconstructed_response": {
                "path": str(output_path),
                "token_estimate": reconstructed.token_estimate,
                "preserved_code_blocks": reconstructed.preserved_code_blocks,
                "locked_terms": reconstructed.locked_terms,
            },
        }
        trace_path = TraceStore(self.workspace.traces_dir).save(trace_id, trace_payload)
        return ReconstructionResult(
            trace_id=trace_id,
            output_path=output_path,
            trace_path=trace_path,
            response=reconstructed,
        )

    def dream(self, project_id: str = "promptbridge") -> DreamPatch:
        self.workspace.ensure_defaults()
        return DreamCompactor(self.workspace).propose_patch(project_id)

    def _translate_for_downstream(
        self,
        *,
        kernel: ContextKernel,
        translator: str,
        model: str | None,
        endpoint: str | None,
        target: str,
        translation_timeout: int,
        api_key: str,
    ) -> TranslationResult:
        user_segment = next(
            segment for segment in kernel.segments
            if segment.segment_type == "user_instruction"
        )
        locked_terms = [
            segment.title for segment in kernel.segments
            if segment.segment_type == "technical_term"
        ]
        provider = get_translation_provider(
            provider=translator,
            model=model,
            endpoint=endpoint,
            timeout_seconds=translation_timeout,
            api_key=api_key,
        )
        request = TranslationRequest(
            trace_id=kernel.trace_id,
            source_text=user_segment.text,
            source_language=kernel.source_language,
            target_language=kernel.target_reasoning_language,
            task_type=kernel.task_type,
            locked_terms=locked_terms,
            target_surface=target,
        )
        return provider.translate(request)

    def latest_trace_summary(self) -> str:
        from promptbridge.traces.store import format_trace_summary

        self.workspace.ensure_defaults()
        latest = TraceStore(self.workspace.traces_dir).latest()
        if latest is None:
            return "No traces found."
        path, trace = latest
        return format_trace_summary(path, trace)
