from __future__ import annotations

import re


EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<!\d)(?:\+?\d[\d\-\s]{7,}\d)(?!\d)")


def redact_pii(text: str) -> tuple[str, list[dict]]:
    findings: list[dict] = []

    def replace_email(match: re.Match[str]) -> str:
        findings.append({"type": "email", "value": match.group(0)})
        return "[REDACTED_EMAIL]"

    def replace_phone(match: re.Match[str]) -> str:
        findings.append({"type": "phone", "value": match.group(0)})
        return "[REDACTED_PHONE]"

    redacted = EMAIL_RE.sub(replace_email, text)
    redacted = PHONE_RE.sub(replace_phone, redacted)
    return redacted, findings

