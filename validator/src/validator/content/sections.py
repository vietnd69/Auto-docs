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


def split_section_blocks(section_text: str) -> tuple[str, list[str]]:
    """Split a ## section into (preamble, fn_blocks).

    preamble: ## heading line + all content before the first line-anchored ### line.
              Always non-empty (contains at least the ## heading).
    fn_blocks: list[str], each starts with a ### line. Empty if no ### found.

    Round-trip invariant: preamble + "".join(fn_blocks) == section_text
    """
    match = re.search(r'(?m)^### ', section_text)
    if not match:
        return section_text, []
    preamble = section_text[: match.start()]
    rest = section_text[match.start():]
    fn_blocks = [b for b in re.split(r'(?m)^(?=### )', rest) if b]
    return preamble, fn_blocks


def sub_chunk_section(fn_blocks: list[str], limit: int) -> list[list[str]]:
    """Group fn_blocks into batches where each batch's token count <= limit.

    A single block that exceeds limit is placed in its own batch (never split).
    """
    batches: list[list[str]] = []
    current: list[str] = []
    current_tokens = 0
    for block in fn_blocks:
        block_tokens = count_tokens(block)
        if current and current_tokens + block_tokens > limit:
            batches.append(current)
            current = [block]
            current_tokens = block_tokens
        else:
            current.append(block)
            current_tokens += block_tokens
    if current:
        batches.append(current)
    return batches


def sub_chunk_section_lua_aware(
    fn_blocks: list[str],
    lua_source: str,
    lua_token_limit: int,
    doc_token_limit: int,
) -> list[list[str]]:
    """Group fn_blocks into batches respecting both Lua context and doc token budgets.

    Primary constraint: cumulative Lua source tokens for the batch ≤ lua_token_limit.
    Secondary constraint: cumulative doc tokens ≤ doc_token_limit.
    A block exceeding either limit on its own goes into its own batch (never split).

    Using Lua budget as primary constraint guarantees extract_lua_context never
    truncates — each batch's source context fits within the allowed token window.
    Functions not found in the source (hallucinated) have lua_tokens=0 and don't
    consume Lua budget.
    """
    batches: list[list[str]] = []
    current: list[str] = []
    current_lua_tokens = 0
    current_doc_tokens = 0

    for block in fn_blocks:
        fn_names = extract_function_names(block)
        lua_ctx = extract_lua_context(lua_source, fn_names, max_tokens=lua_token_limit)
        lua_tokens = count_tokens(lua_ctx) if lua_ctx else 0
        doc_tokens = count_tokens(block)

        would_exceed_lua = lua_tokens > 0 and current_lua_tokens + lua_tokens > lua_token_limit
        would_exceed_doc = current_doc_tokens + doc_tokens > doc_token_limit
        if current and (would_exceed_lua or would_exceed_doc):
            batches.append(current)
            current = [block]
            current_lua_tokens = lua_tokens
            current_doc_tokens = doc_tokens
        else:
            current.append(block)
            current_lua_tokens += lua_tokens
            current_doc_tokens += doc_tokens

    if current:
        batches.append(current)
    return batches


def extract_fn_headings(fn_blocks: list[str]) -> set[str]:
    """Return the first-line heading of each non-empty block.

    Example: '### `GetOwner(inst)`' for a block starting with that line.
    Used to snapshot which function entries exist before a patch loop.
    """
    return {block.split("\n", 1)[0].strip() for block in fn_blocks if block.strip()}


def extract_fn_headings_from_text(text: str) -> set[str]:
    """Extract normalized function names from ### headings in raw text.

    Parses headings like: ### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`
    Returns: {"CLOSEINSPECTORUTIL.IsValidTarget", "FuncName", ...}
    Strips backticks, parameters, and trailing whitespace.
    """
    headings = re.findall(r'^### `?([^`(\n]+)', text, re.MULTILINE)
    return {h.strip() for h in headings}


def delete_fn_block(text: str, fn_name: str) -> str:
    """Delete the ### function block for fn_name from text.

    Block boundary: from the `### ` heading line containing fn_name
    to the next `### ` heading (exclusive) or end-of-string.

    Name matching: fn_name is matched against the heading text with
    optional backticks, dots, and parameters stripped. For example,
    fn_name="CLOSEINSPECTORUTIL.IsValidTarget" matches heading
    `### \\`CLOSEINSPECTORUTIL.IsValidTarget(inst)\\``.

    Trailing blank lines after deletion are collapsed to one newline.
    Returns text unchanged if fn_name not found in any heading.
    """
    escaped = re.escape(fn_name)
    pattern = re.compile(
        rf'^### `?{escaped}\b[^\n]*\n'   # heading line
        rf'(?:(?!^##(?:#)? ).*\n?)*',    # body lines until next ## or ### or EOF
        re.MULTILINE,
    )
    result = pattern.sub('', text)
    if result == text:
        return text
    # Collapse multiple blank lines to at most one
    result = re.sub(r'\n{3,}', '\n\n', result)
    return result


def _normalize_fn_heading(heading: str) -> str:
    """Strip marker suffixes like *(Internal)*, *(Deprecated)* and backticks.

    Used to detect when a lost heading is just a marked variant of an entry
    that still exists (e.g. writer intentionally removed a duplicate).
    """
    h = re.sub(r'\s*\*\([^)]*\)\*', '', heading)
    return h.replace('`', '').strip()


def restore_lost_blocks(
    fn_blocks: list[str],
    snapshot: set[str],
    backup_fn_blocks: list[str],
    excluded_fn_names: set[str] | None = None,
) -> int:
    """Reinsert fn_blocks whose heading was in snapshot but is now missing.

    Preserves original order: each restored block is inserted immediately before
    the first subsequent backup entry that still exists in fn_blocks.
    If no such anchor exists, the block is appended at the end.

    Skips restoration when a normalized-equivalent heading already exists
    (e.g. writer intentionally removed ``*(Internal)*`` duplicate).

    excluded_fn_names: function names that were intentionally removed (e.g. by
    Guard 2 hallucination enforcement) and must not be restored.

    Returns the number of blocks restored.
    """
    current = extract_fn_headings(fn_blocks)
    lost_headings = snapshot - current
    if not lost_headings:
        return 0

    # Normalized current headings — detect intentional duplicate removal
    current_normalized = {_normalize_fn_heading(h) for h in current}

    current_headings_list = [b.split("\n", 1)[0].strip() for b in fn_blocks]
    restored = 0
    skipped = 0

    for orig_idx, block in enumerate(backup_fn_blocks):
        heading = block.split("\n", 1)[0].strip()
        if heading not in lost_headings:
            continue

        # Skip blocks that were intentionally removed by hallucination enforcement
        if excluded_fn_names:
            fn_match = re.match(r'^### `?([^`(\n]+)', heading)
            if fn_match and fn_match.group(1).strip() in excluded_fn_names:
                skipped += 1
                continue

        # Skip if a normalized-equivalent heading still exists
        if _normalize_fn_heading(heading) in current_normalized:
            skipped += 1
            continue

        # Find insertion point: before the first later backup heading still present
        insert_pos = len(fn_blocks)
        for later_idx in range(orig_idx + 1, len(backup_fn_blocks)):
            later_heading = backup_fn_blocks[later_idx].split("\n", 1)[0].strip()
            if later_heading in current_headings_list:
                insert_pos = current_headings_list.index(later_heading)
                break

        fn_blocks.insert(insert_pos, block)
        current_headings_list.insert(insert_pos, heading)
        current_normalized.add(_normalize_fn_heading(heading))
        restored += 1

    if skipped:
        print(f"  [content/chunked] Skipped {skipped} duplicate-equivalent entries")

    return restored


_FN_PATTERNS: list[tuple[str, int]] = [
    (r'^###\s+`?([\w.]+)',  re.MULTILINE),  # ### FunctionName or ### TABLE.Method heading
    (r'`(\w+)\s*\(',        0),             # `FuncName(
    (r'[\w.]+:(\w+)\s*\(',  0),            # inst:Method(
    (r'`([A-Z][A-Za-z_]\w*)`', 0),         # `CapitalizedName` (no parens)
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


# ── Pre-filter: locality classification ──────────────────────────────────────

_LOCAL_FN_RE = re.compile(r'^local\s+function\s+(\w+)')
_LOCAL_ASSIGN_RE = re.compile(r'^local\s+(\w+)\s*=\s*function')
_GLOBAL_FN_RE = re.compile(r'^function\s+([\w.:]+)\s*\(')


def classify_lua_functions(lua_source: str) -> dict[str, str]:
    """Return {'name': 'local'|'global'} for each function defined in lua_source.

    Classification is line-prefix based. Last definition wins — correct for Lua
    scoping where a public wrapper function follows an inner local closure.
    """
    result: dict[str, str] = {}
    for line in lua_source.splitlines():
        m = _LOCAL_FN_RE.match(line)
        if m:
            result[m.group(1)] = "local"
            continue
        m = _LOCAL_ASSIGN_RE.match(line)
        if m:
            result[m.group(1)] = "local"
            continue
        m = _GLOBAL_FN_RE.match(line)
        if m:
            result[m.group(1)] = "global"
    return result


_REQUIRED_FIELDS = ("Description", "Parameters", "Returns")


def prefilter_fn_blocks(
    fn_blocks: list[str],
    lua_source: str,
) -> tuple[list[str], list[str]]:
    """Strip local and hallucinated function blocks.

    Returns (kept_blocks, stripped_names) where stripped_names contains the
    raw function names that were removed. Pass stripped_names to the review
    loop as intentionally_removed so apply_typed_ops silently skips any
    delete_function op targeting those names.
    """
    classification = classify_lua_functions(lua_source)
    kept: list[str] = []
    stripped: list[str] = []

    for block in fn_blocks:
        heading = block.split("\n", 1)[0]
        m = re.match(r'^### `?([^`(\n]+)', heading)
        if not m:
            kept.append(block)  # unparseable heading — keep as fail-safe
            continue
        name = m.group(1).strip()

        # Existence check (hallucination filter)
        patterns = _def_patterns(name)
        if not any(p.search(lua_source) for p in patterns):
            stripped.append(name)
            continue

        # Locality check
        if classification.get(name) == "local":
            stripped.append(name)
            continue

        kept.append(block)

    return kept, stripped


def ensure_required_fields(fn_blocks: list[str]) -> list[str]:
    """Ensure every fn_block has Description, Parameters, Returns fields.

    If a field is absent, appends a skeleton line so the reviewer always
    has a target. Pure function — never mutates input blocks.
    """
    result: list[str] = []
    for block in fn_blocks:
        updated = block
        for field in _REQUIRED_FIELDS:
            if f"* **{field}:**" not in block:
                updated = updated.rstrip("\n") + f"\n* **{field}:** TODO\n"
        result.append(updated)
    return result


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


def _truncate_blocks_to_lua_limit(blocks: list[str], limit: int = LUA_CONTEXT_TOKENS) -> str:
    """Return the longest prefix of blocks whose token count stays ≤ limit."""
    kept: list[str] = []
    for block in blocks:
        candidate = "\n".join(kept + [block])
        if count_tokens(candidate) > limit:
            break
        kept.append(block)
    result = "\n".join(kept)
    if result:
        result += "\n-- [truncated]"
    return result


def extract_lua_context(
    lua_source: str,
    fn_names: list[str],
    max_tokens: int | None = None,
) -> str:
    """Extract Lua function bodies for the given names from lua_source.

    Returns a single string (blocks joined by "\\n"), or "" if no names / no matches.
    Truncates to max_tokens (default: LUA_CONTEXT_TOKENS from settings).
    """
    if not fn_names:
        return ""

    limit = max_tokens if max_tokens is not None else LUA_CONTEXT_TOKENS
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
    if token_count != -1 and token_count > limit:
        result = _truncate_blocks_to_lua_limit(blocks, limit)

    return result
