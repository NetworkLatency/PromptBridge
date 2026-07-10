from __future__ import annotations

from dataclasses import dataclass
import re

from promptbridge.memory.files import GlossaryTerm
from promptbridge.utils import estimate_tokens


@dataclass(frozen=True)
class ReconstructedResponse:
    text: str
    token_estimate: int
    preserved_code_blocks: int
    locked_terms: list[str]


def reconstruct_response(
    response_text: str,
    target_language: str,
    glossary_terms: list[GlossaryTerm],
) -> ReconstructedResponse:
    code_blocks = re.findall(r"```.*?```", response_text, flags=re.DOTALL)
    locked_terms = [
        term.term for term in glossary_terms
        if term.term and term.term.lower() in response_text.lower()
    ]
    header = [
        "# PromptBridge Reconstructed Response",
        "",
        f"- target_language: `{target_language}`",
        f"- preserved_code_blocks: `{len(code_blocks)}`",
        f"- locked_terms_detected: `{', '.join(locked_terms) if locked_terms else 'none'}`",
        "",
        "> v0 reconstruction is deterministic: it preserves code blocks and locked terms, but does not call a remote translation model.",
        "",
        "## Response",
        "",
    ]
    text = "\n".join(header) + response_text.strip() + "\n"
    return ReconstructedResponse(
        text=text,
        token_estimate=estimate_tokens(text),
        preserved_code_blocks=len(code_blocks),
        locked_terms=locked_terms,
    )

