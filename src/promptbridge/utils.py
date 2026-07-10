from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import json
import re
import uuid


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def detect_language(text: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", text):
        return "zh"
    if re.search(r"[\u0600-\u06ff]", text):
        return "ar"
    if re.search(r"[áéíóúñãõç]", text, re.IGNORECASE):
        return "romance"
    return "en"


def estimate_tokens(text: str) -> int:
    ascii_chars = sum(1 for char in text if ord(char) < 128)
    non_ascii_chars = max(0, len(text) - ascii_chars)
    estimate = int(ascii_chars / 4 + non_ascii_chars * 0.75)
    return max(1, estimate)


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def first_heading(markdown: str, fallback: str) -> str:
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped.startswith("#"):
            return stripped.lstrip("#").strip() or fallback
    return fallback


def compact_snippet(text: str, query: str, radius: int = 180) -> str:
    if not text:
        return ""
    lower_text = text.lower()
    lower_query = query.lower()
    index = lower_text.find(lower_query) if lower_query else -1
    if index < 0:
        return text[: radius * 2].strip()
    start = max(0, index - radius)
    end = min(len(text), index + len(query) + radius)
    prefix = "..." if start else ""
    suffix = "..." if end < len(text) else ""
    return f"{prefix}{text[start:end].strip()}{suffix}"


def split_terms(query: str) -> list[str]:
    ascii_terms = re.findall(r"[A-Za-z0-9_\-]{2,}", query.lower())
    cjk_terms = re.findall(r"[\u4e00-\u9fff]{2,}", query)
    return ascii_terms + cjk_terms

