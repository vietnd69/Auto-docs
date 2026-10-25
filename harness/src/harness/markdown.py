"""Markdown section utilities (ATX headings, fenced code aware)."""

from __future__ import annotations

import re
from dataclasses import dataclass

_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
_FENCE_RE = re.compile(r"^\s*(```|~~~)")


@dataclass(frozen=True)
class Heading:
    level: int
    text: str
    line: int  # 0-based index into the body lines


def split_frontmatter(doc: str) -> tuple[str, str]:
    """Return (frontmatter block including fences, body)."""
    if doc.startswith("---\n"):
        end = doc.find("\n---", 4)
        if end != -1:
            cut = doc.find("\n", end + 4)
            cut = len(doc) if cut == -1 else cut + 1
            return doc[:cut], doc[cut:]
    return "", doc


def headings(body: str) -> list[Heading]:
    """All headings outside fenced code blocks."""
    found: list[Heading] = []
    in_fence = False
    for i, line in enumerate(body.split("\n")):
        if _FENCE_RE.match(line):
            in_fence = not in_fence
            continue
        match = None if in_fence else _HEADING_RE.match(line)
        if match:
            found.append(Heading(len(match.group(1)), match.group(2).strip(), i))
    return found


def normalize_heading(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lstrip("#").strip())


def _section_bounds(lines_count: int, heads: list[Heading], idx: int) -> tuple[int, int]:
    head = heads[idx]
    end = lines_count
    for nxt in heads[idx + 1 :]:
        if nxt.level <= head.level:
            end = nxt.line
            break
    return head.line, end


def find_section(body: str, heading: str) -> tuple[int, int] | None:
    """Line bounds ``[start, end)`` of the section whose heading equals ``heading``."""
    level = len(heading) - len(heading.lstrip("#"))
    wanted = normalize_heading(heading)
    heads = headings(body)
    for idx, head in enumerate(heads):
        if head.level == level and normalize_heading(head.text) == wanted:
            return _section_bounds(len(body.split("\n")), heads, idx)
    return None


def section_text(body: str, heading: str) -> str | None:
    bounds = find_section(body, heading)
    if bounds is None:
        return None
    return "\n".join(body.split("\n")[bounds[0] : bounds[1]]).rstrip() + "\n"


def upsert_section(body: str, heading: str, content: str, parent: str | None = None) -> str:
    """Replace the section ``heading`` (whole subtree) or insert it.

    New sections go at the end of ``parent`` when given and present, else at the end.
    ``content`` is the section body without its heading line.
    """
    lines = body.rstrip("\n").split("\n")
    block = [heading.strip(), "", *content.strip("\n").split("\n"), ""]
    bounds = find_section(body, heading)
    if bounds is not None:
        lines[bounds[0] : bounds[1]] = block
    else:
        parent_bounds = find_section(body, parent) if parent else None
        insert_at = parent_bounds[1] if parent_bounds else len(lines)
        if insert_at > 0 and lines[insert_at - 1].strip():
            block.insert(0, "")
        lines[insert_at:insert_at] = block
    return "\n".join(lines).rstrip("\n") + "\n"
