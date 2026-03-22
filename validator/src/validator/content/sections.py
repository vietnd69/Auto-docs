# validator/src/validator/content/sections.py
"""Markdown section splitting and Lua context extraction for chunked content validation."""

import re
from dataclasses import dataclass

from llm.tokens import count_tokens
from llm.settings import LUA_CONTEXT_TOKENS


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


# Lua keyword regexes for depth tracking
_LUA_DEPTH_UP = re.compile(
    r'^\s*(function|if|for|while|do)\b|^\s*local\s+function\b'
)
_LUA_REPEAT = re.compile(r'^\s*repeat\b')
_LUA_UNTIL  = re.compile(r'^\s*until\b')
_LUA_END    = re.compile(r'^\s*end\b')


def _def_patterns(name: str) -> list[re.Pattern[str]]:
    """Return compiled patterns that match a Lua definition of `name`."""
    n = re.escape(name)
    return [re.compile(p) for p in [
        rf'function\s+\w+:{n}\s*\(',       # Entity:Name(
        rf'function\s+{n}\s*\(',            # function Name(
        rf'\w+\.{n}\s*=\s*function\s*\(',  # Tbl.Name = function(
        rf'\b{n}\s*=\s*function\s*\(',     # Name = function(
    ]]


def _extract_block(lines: list[str], def_idx: int) -> str:
    """Extract the full Lua function block starting at def_idx."""
    def_line = lines[def_idx]

    # Single-line function: 'end' on the same line as the definition
    if _LUA_END.match(def_line):
        return def_line.rstrip("\n")

    # Multi-line: depth scan (depth starts at 1 for the definition line)
    block: list[str] = [def_line.rstrip("\n")]
    depth = 1
    for line in lines[def_idx + 1:]:
        if _LUA_UNTIL.match(line):
            depth -= 1
            block.append(line.rstrip("\n"))
            if depth == 0:
                break
        elif _LUA_END.match(line):
            depth -= 1
            block.append(line.rstrip("\n"))
            if depth == 0:
                break
        else:
            if _LUA_DEPTH_UP.match(line) or _LUA_REPEAT.match(line):
                depth += 1
            block.append(line.rstrip("\n"))

    return "\n".join(block)


def _truncate_blocks_to_lua_limit(blocks: list[str]) -> str:
    """Return the longest prefix of blocks whose token count stays ≤ LUA_CONTEXT_TOKENS."""
    kept: list[str] = []
    for block in blocks:
        candidate = "\n".join(kept + [block])
        if count_tokens(candidate) > LUA_CONTEXT_TOKENS:
            break
        kept.append(block)
    result = "\n".join(kept)
    if result:
        result += "\n-- [truncated]"
    return result


def extract_lua_context(lua_source: str, fn_names: list[str]) -> str:
    """Extract Lua function bodies for the given names from lua_source.

    Returns a single string (blocks joined by "\\n"), or "" if no names / no matches.
    Truncates to 8K tokens if count_tokens is available (returns -1 → skip guard).
    """
    if not fn_names:
        return ""

    lines = lua_source.splitlines(keepends=True)
    blocks: list[str] = []

    for name in fn_names:
        patterns = _def_patterns(name)
        def_idx: int | None = None
        for i, line in enumerate(lines):
            if any(p.search(line) for p in patterns):
                def_idx = i
                break
        if def_idx is None:
            continue
        blocks.append(_extract_block(lines, def_idx))

    if not blocks:
        return ""

    result = "\n".join(blocks)

    # Token guard
    token_count = count_tokens(result)
    if token_count != -1 and token_count > LUA_CONTEXT_TOKENS:
        result = _truncate_blocks_to_lua_limit(blocks)

    return result
