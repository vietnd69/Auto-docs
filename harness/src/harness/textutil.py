"""Small text helpers: token estimation, truncation, hashing."""

from __future__ import annotations

import hashlib
import math

CHARS_PER_TOKEN = 3.5


def estimate_tokens(text: str) -> int:
    """Cheap, deterministic token estimate (≈3.5 chars per token for Lua/Markdown)."""
    return math.ceil(len(text) / CHARS_PER_TOKEN)


def truncate(text: str, max_chars: int, hint: str = "") -> str:
    """Cut ``text`` to ``max_chars`` and append a marker telling the caller how to continue."""
    if len(text) <= max_chars:
        return text
    marker = f"\n…[truncated {len(text) - max_chars} chars]{(' ' + hint) if hint else ''}"
    return text[:max_chars] + marker


def short_hash(text: str, length: int = 12) -> str:
    """Stable short SHA-256 hex digest."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:length]
