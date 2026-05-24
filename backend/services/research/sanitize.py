"""Strip characters PostgreSQL text/JSONB cannot store (e.g. NUL from PDF extracts)."""
from __future__ import annotations

import re
from typing import Any

# PDF/HTML binary extracts often include NUL and C0 control bytes.
_CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def sanitize_text(text: str | None, *, max_len: int | None = None) -> str:
    if not text:
        return ""
    cleaned = _CONTROL_CHARS.sub("", text)
    if max_len is not None and len(cleaned) > max_len:
        cleaned = cleaned[:max_len]
    return cleaned.strip()


def sanitize_payload(value: Any) -> Any:
    """Recursively clean strings inside dicts/lists before DB or JSON persistence."""
    if isinstance(value, str):
        return sanitize_text(value)
    if isinstance(value, dict):
        return {k: sanitize_payload(v) for k, v in value.items()}
    if isinstance(value, list):
        return [sanitize_payload(v) for v in value]
    return value
