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


def _content_body(heading: str, content: str) -> str:
    """Accept the common model response containing its own leading heading exactly once."""
    content = content.strip()
    first, _, rest = content.partition("\n")
    if first.strip() == heading.strip():
        content = rest.lstrip("\n")
    level = len(heading) - len(heading.lstrip("#"))
    if any(h.level <= level for h in headings(content)):
        raise ValueError("content must not contain sibling/ancestor headings; write each section separately")
    return content


def _parent_bounds(body: str, heading: str, parent: str | None) -> tuple[int, int] | None:
    if parent is None:
        return None
    level = len(heading) - len(heading.lstrip("#"))
    canonical = parent.strip() if parent.lstrip().startswith("#") else f"{'#' * (level - 1)} {parent.strip()}"
    bounds = find_section(body, canonical)
    if bounds is None or len(canonical) - len(canonical.lstrip("#")) >= level:
        raise ValueError(f"parent {parent!r} must name an existing ancestor section")
    return bounds


def upsert_section(body: str, heading: str, content: str, parent: str | None = None) -> str:
    """Replace the section ``heading`` (whole subtree) or insert it.

    New sections go at the end of a validated parent, or the document when omitted.
    A repeated leading heading in content is removed; sibling sections are rejected.
    """
    lines = body.rstrip("\n").split("\n")
    content = _content_body(heading, content)
    parent_bounds = _parent_bounds(body, heading, parent)
    block = [heading.strip(), "", *content.split("\n"), ""]
    bounds = find_section(body, heading)
    if bounds is not None:
        lines[bounds[0] : bounds[1]] = block
    else:
        insert_at = parent_bounds[1] if parent_bounds else len(lines)
        if insert_at > 0 and lines[insert_at - 1].strip():
            block.insert(0, "")
        lines[insert_at:insert_at] = block
    return "\n".join(lines).rstrip("\n") + "\n"
