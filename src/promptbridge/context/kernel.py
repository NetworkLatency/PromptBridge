from __future__ import annotations

from dataclasses import dataclass, asdict

from promptbridge.context.segment_policy import choose_segment_action
from promptbridge.retrieval.types import RetrievalHit
from promptbridge.utils import detect_language, estimate_tokens, now_iso


@dataclass(frozen=True)
class TokenBudget:
    max_tokens: int = 6000
    reserved_for_user_task: int = 2500
    reserved_for_memory: int = 1000
    reserved_for_glossary: int = 600
    reserved_for_retrieval: int = 1200
    reserved_for_output_constraints: int = 300

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ContextSegment:
    segment_id: str
    segment_type: str
    source: str
    title: str
    text: str
    action: str
    token_estimate: int
    ref_id: str | None = None
    trust_level: str = "trusted"
    reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class OmittedContext:
    source: str
    reason: str
    token_estimate: int

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ContextKernel:
    trace_id: str
    created_at: str
    current_user_input: str
    task_type: str
    source_language: str
    target_reasoning_language: str
    target_output_language: str
    active_project: str
    segments: list[ContextSegment]
    omitted_context: list[OmittedContext]
    token_budget: TokenBudget

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["segments"] = [segment.to_dict() for segment in self.segments]
        payload["omitted_context"] = [item.to_dict() for item in self.omitted_context]
        payload["token_budget"] = self.token_budget.to_dict()
        return payload


def build_context_kernel(
    *,
    trace_id: str,
    user_input: str,
    project_id: str,
    retrieval_hits: list[RetrievalHit],
    max_tokens: int = 6000,
) -> ContextKernel:
    source_language = detect_language(user_input)
    token_budget = TokenBudget(max_tokens=max_tokens)
    segments: list[ContextSegment] = []
    omitted: list[OmittedContext] = []

    segments.append(
        ContextSegment(
            segment_id="seg_user_input",
            segment_type="user_instruction",
            source="current_user_input",
            title="Current User Input",
            text=user_input,
            action=choose_segment_action("user_instruction", source_language),
            token_estimate=estimate_tokens(user_input),
            reason="Primary task request for this compile call.",
        )
    )

    retrieval_tokens = 0
    for idx, hit in enumerate(retrieval_hits):
        segment_type = "technical_term" if hit.source == "glossary" else "retrieved_memory"
        token_estimate = estimate_tokens(hit.snippet)
        if retrieval_tokens + token_estimate > token_budget.reserved_for_retrieval:
            omitted.append(
                OmittedContext(
                    source=hit.path,
                    reason="retrieval token budget exceeded",
                    token_estimate=token_estimate,
                )
            )
            continue
        retrieval_tokens += token_estimate
        segments.append(
            ContextSegment(
                segment_id=f"seg_retrieved_{idx}",
                segment_type=segment_type,
                source=hit.source,
                title=hit.title,
                text=hit.snippet,
                action=choose_segment_action(segment_type, source_language),
                token_estimate=token_estimate,
                ref_id=hit.ref_id,
                reason=f"Selected by {hit.strategy} with score {hit.score:.2f}.",
            )
        )

    return ContextKernel(
        trace_id=trace_id,
        created_at=now_iso(),
        current_user_input=user_input,
        task_type=_classify_task(user_input),
        source_language=source_language,
        target_reasoning_language="en",
        target_output_language=source_language,
        active_project=project_id,
        segments=segments,
        omitted_context=omitted,
        token_budget=token_budget,
    )


def _classify_task(text: str) -> str:
    lowered = text.lower()
    if any(
        term in lowered
        for term in ["architecture", "架构", "design", "设计", "优化", "agent", "mcp"]
    ):
        return "architecture_design"
    if any(term in lowered for term in ["code", "implement", "实现", "代码"]):
        return "coding"
    if any(term in lowered for term in ["research", "paper", "论文", "调研"]):
        return "research"
    if any(term in lowered for term in ["translate", "翻译"]):
        return "translation"
    return "general_assistance"
