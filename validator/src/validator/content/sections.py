# validator/src/validator/content/sections.py
"""Markdown section splitting and Lua context extraction for chunked content validation."""

import re
from dataclasses import dataclass


@dataclass
class DocSection:
    """A ## section from a markdown document (or the preamble before the first ##).

    heading: first line of the section (e.g. "## Functions"), empty for preamble.
    text:    full text including heading line; invariant: join produces original content.
    """
    heading: str
    text: str


def split_md_sections(md_content: str) -> tuple[str, list[DocSection]]:
    """Split markdown into (frontmatter, sections). Normalises CRLF → LF.

    frontmatter: the "---\\n...\\n---\\n" block (empty string if absent).
    sections:    one DocSection per ## heading, plus a preamble section (heading="")
                 if there is content before the first ##. Empty if nothing remains.

    Round-trip invariant: join_md_sections(*split_md_sections(x)) == x.replace("\\r\\n", "\\n")
    """
    content = md_content.replace("\r\n", "\n")

    # Extract YAML frontmatter — same pattern as checks.py:check_frontmatter
    fm_match = re.match(r'^---\n[\s\S]*?\n---\n', content)
    frontmatter = fm_match.group(0) if fm_match else ""
    remaining = content[len(frontmatter):]

    # Split on ## heading boundaries (exactly two hashes + space)
    chunks = re.split(r'(?m)^(?=## )', remaining)

    sections: list[DocSection] = []
    for chunk in chunks:
        if not chunk:
            continue
        first_line = chunk.split("\n", 1)[0]
        heading = first_line if first_line.startswith("## ") else ""
        sections.append(DocSection(heading=heading, text=chunk))

    return frontmatter, sections


def join_md_sections(frontmatter: str, sections: list[DocSection]) -> str:
    """Reassemble document from frontmatter and section list."""
    return frontmatter + "".join(s.text for s in sections)


_FN_PATTERNS: list[tuple[str, int]] = [
    (r'^###\s+`?(\w+)`?', re.MULTILINE),  # ### FunctionName heading
    (r'`(\w+)\s*\(',      0),             # `FuncName(
    (r'[\w.]+:(\w+)\s*\(', 0),           # inst:Method(
    (r'`([A-Z][A-Za-z_]\w*)`', 0),       # `CapitalizedName` (no parens)
]


def extract_function_names(section_text: str) -> list[str]:
    """Extract Lua function names mentioned in a markdown section.

    Runs four regex patterns; results deduplicated and ordered by first occurrence.
    """
    matches: list[tuple[int, str]] = []
    for pattern, flags in _FN_PATTERNS:
        for m in re.finditer(pattern, section_text, flags):
            matches.append((m.start(), m.group(1)))

    matches.sort(key=lambda x: x[0])
    seen: set[str] = set()
    result: list[str] = []
    for _, name in matches:
        if name not in seen:
            seen.add(name)
            result.append(name)
    return result
