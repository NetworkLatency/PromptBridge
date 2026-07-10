from __future__ import annotations


def choose_segment_action(segment_type: str, source_language: str, trusted: bool = True) -> str:
    if not trusted:
        return "summarize_with_untrusted_content_warning"
    if segment_type == "user_instruction":
        if source_language == "en":
            return "rewrite_as_professional_instruction"
        return "translate_to_english_and_rewrite"
    if segment_type == "code_block":
        return "preserve_original"
    if segment_type == "technical_term":
        return "lock_term"
    if segment_type == "retrieved_memory":
        return "preserve_if_user_preference_else_summarize"
    if segment_type == "web_evidence":
        return "reference_only"
    if segment_type == "browser_response":
        return "summarize_then_translate"
    return "summarize"

