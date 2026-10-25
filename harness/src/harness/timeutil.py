"""ISO 8601 date/time helpers (UTC everywhere)."""

from __future__ import annotations

from datetime import UTC, datetime


def now_iso() -> str:
    """Current UTC timestamp as ``YYYY-MM-DDTHH:MM:SSZ``."""
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def today_iso() -> str:
    """Current UTC date as ``YYYY-MM-DD``."""
    return datetime.now(UTC).strftime("%Y-%m-%d")
