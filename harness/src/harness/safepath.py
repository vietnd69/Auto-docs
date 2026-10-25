"""Path confinement (ISO/IEC 27034: input validation against path traversal)."""

from __future__ import annotations

from pathlib import Path, PurePosixPath


class PathOutsideRootError(ValueError):
    """Raised when a user-supplied path escapes its allowed root."""


def normalize_rel(rel: str) -> str:
    """Normalise a repository-relative POSIX path and reject traversal."""
    candidate = PurePosixPath(rel.replace("\\", "/").lstrip("/"))
    if any(part == ".." for part in candidate.parts) or not candidate.parts:
        raise PathOutsideRootError(f"invalid relative path: {rel!r}")
    return candidate.as_posix()


def confine(root: Path, rel: str) -> Path:
    """Join ``rel`` onto ``root`` and guarantee the result stays inside ``root``."""
    resolved_root = root.resolve()
    target = (resolved_root / normalize_rel(rel)).resolve()
    if resolved_root != target and resolved_root not in target.parents:
        raise PathOutsideRootError(f"path escapes root: {rel!r}")
    return target
