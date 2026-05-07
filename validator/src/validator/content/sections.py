from __future__ import annotations

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
    """Reassemble document from frontmatter and section list.

    Each section text is normalized to end with a newline before joining so that
    adjacent section headings never merge onto the same line (e.g. when the writer
    returns update_section content without a trailing newline).
    """
    parts = []
    for s in sections:
        text = s.text
        if text and not text.endswith('\n'):
            text += '\n'
        parts.append(text)
    return frontmatter + "".join(parts)


def normalize_fn_headings(text: str) -> str:
    """Ensure every ### heading starts on its own line.

    The merge stage sometimes emits `* **Error states:** None### \`Fn\`` with no
    newline between the field value and the next function heading.  This makes
    `(?m)^### ` anchors fail in split_section_blocks, _extract_target_text, and
    apply_typed_ops, causing silent no-ops.  Insert a newline before any `### `
    that immediately follows a non-newline character.
    """
    return re.sub(r'([^\n])(### )', r'\1\n\2', text)


def split_section_blocks(section_text: str) -> tuple[str, list[str]]:
    """Split a ## section into (preamble, fn_blocks).

    preamble: ## heading line + all content before the first line-anchored ### line.
              Always non-empty (contains at least the ## heading).
    fn_blocks: list[str], each starts with a ### line. Empty if no ### found.

    Round-trip invariant: preamble + "".join(fn_blocks) == section_text
    """
    section_text = normalize_fn_headings(section_text)
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
        rf'^### `?{escaped}(?=[^a-zA-Z0-9_.])[^\n]*\n'   # heading line
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

        # Extract full name from backtick-quoted heading (e.g. `onenter (fishing_nibble)`)
        m_full = re.match(r'^### `([^`\n]+)`', heading)
        if m_full:
            full_name = m_full.group(1).strip()
        else:
            m = re.match(r'^### `?([^`\n]+)', heading)
            if not m:
                kept.append(block)  # unparseable heading — keep as fail-safe
                continue
            full_name = m.group(1).strip()

        # For "base (state_name)" compound names (space before paren = state variant),
        # check both base function and state name exist in Lua source.
        m_compound = re.match(r'^([\w.:]+)\s+\(([^)]+)\)', full_name)
        if m_compound:
            base_name = m_compound.group(1)
            state_name = m_compound.group(2)
            if not any(p.search(lua_source) for p in _def_patterns(base_name)):
                stripped.append(full_name)
                continue
            # State name not in Lua source → the whole state variant is hallucinated
            if state_name not in lua_source:
                stripped.append(full_name)
                continue
            if classification.get(base_name) == "local":
                stripped.append(full_name)
                continue
        else:
            # Simple name — strip params (e.g. "GetState(inst)" → "GetState")
            name = re.match(r'^[\w.:]+', full_name)
            if not name:
                kept.append(block)
                continue
            name = name.group(0)
            if not any(p.search(lua_source) for p in _def_patterns(name)):
                stripped.append(name)
                continue
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


# ── Apply engine ──────────────────────────────────────────────────────────────

def _canonical_fn_name(raw: str) -> str:
    """Return canonical function name for precise heading matching.

    Strips trailing (params) when a state-name group also exists, preserving
    the state name so stategraph handlers match precisely:
      "onupdate (attack_recoil)(inst)" → "onupdate (attack_recoil)"
      "onenter (idle)"                 → "onenter (idle)"
      "GetState(inst)"                 → "GetState"
    """
    groups = re.findall(r'\([^)]*\)', raw)
    if len(groups) >= 2:
        return raw[:raw.rfind('(')].rstrip()
    if len(groups) == 1:
        idx = raw.rfind('(')
        if idx > 0 and raw[idx - 1] == ' ':
            return raw.strip()
        return raw[:idx].rstrip()
    return raw.strip()


def _update_field_in_text(text: str, field: str, value: str) -> str:
    """Replace single-line '* **{field}:** ...' with '* **{field}:** {value}'.

    Only replaces the first match. Multi-line fields (nested bullets) are not
    targeted — use update_section or rewrite_function for those.
    """
    if not field:
        return text
    pattern = re.compile(rf'^\* \*\*{re.escape(field)}:\*\*.*$', re.MULTILINE)
    return pattern.sub(f"* **{field}:** {value}", text, count=1)


def apply_typed_ops(
    sections: list[DocSection],
    ops: list,  # list[TypedOp] — late import to avoid circular dep
    frontmatter: str,
    intentionally_removed: set[str] | None = None,
) -> list[DocSection]:
    """Apply typed operations to sections. Returns new list (no mutation).

    intentionally_removed: names pre-stripped by prefilter_fn_blocks; any
    delete_function op targeting these names is silently skipped.
    """
    from validator.content.writer import TypedOp  # local import avoids circular dep at module load

    result = [DocSection(heading=s.heading, text=s.text) for s in sections]
    removed = intentionally_removed or set()

    for op in ops:
        if not isinstance(op, TypedOp):
            continue
        idx = next((i for i, s in enumerate(result) if s.heading.strip().lower() == op.section.strip().lower()), None)
        if idx is None:
            continue  # section not found — silent no-op
        section = result[idx]

        if op.op == "update_section":
            if not op.content:
                continue  # null/empty content — no-op to avoid wiping the section
            section.text = normalize_fn_headings(op.content)

        elif op.op == "update_field" and op.function:
            preamble, fn_blocks = split_section_blocks(section.text)
            op_fn_name = _canonical_fn_name(op.function)
            for j, block in enumerate(fn_blocks):
                m = re.match(r'^### `([^`\n]+)`', block.split("\n", 1)[0]) or re.match(r'^### `?([^`\n]+)', block.split("\n", 1)[0])
                if m and _canonical_fn_name(m.group(1)) == op_fn_name:
                    fn_blocks[j] = _update_field_in_text(block, op.field or "", op.value or "")
                    break
            section.text = preamble + "".join(fn_blocks)

        elif op.op == "update_field":
            section.text = _update_field_in_text(section.text, op.field or "", op.value or "")

        elif op.op == "rewrite_function" and op.function:
            if not op.content:
                continue  # null/empty content — no-op to avoid wiping the function block
            preamble, fn_blocks = split_section_blocks(section.text)
            op_fn_name = _canonical_fn_name(op.function)
            for j, block in enumerate(fn_blocks):
                m = re.match(r'^### `([^`\n]+)`', block.split("\n", 1)[0]) or re.match(r'^### `?([^`\n]+)', block.split("\n", 1)[0])
                if m and _canonical_fn_name(m.group(1)) == op_fn_name:
                    fn_blocks[j] = normalize_fn_headings(op.content)
                    break
            # If function not found: no-op (loop completes without modifying)
            section.text = preamble + "".join(fn_blocks)

        elif op.op == "delete_function" and op.function:
            if op.function in removed:
                continue  # already pre-stripped — silent no-op
            section.text = delete_fn_block(section.text, op.function)

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


def _is_stategraph(lua_source: str) -> bool:
    """Return True if lua_source defines a StateGraph."""
    return bool(re.search(r'\bStateGraph\s*\(', lua_source))


def extract_stategraph_event_names(lua_source: str) -> list[str]:
    """Return event names from all EventHandler("name", fn) entries in lua_source."""
    return re.findall(r'EventHandler\s*\(\s*"([^"]+)"', lua_source)


def check_stategraph_events_null(section_text: str, lua_source: str) -> bool:
    """True if doc claims no events but source has EventHandler entries.

    Only applies to stategraph files. Guards against the pattern where the
    validator approves 'Listens to: None' despite N EventHandlers in source.
    Known limitation: does not detect all phrasings — 'None.' or '**None**'
    without period are not caught; the LLM loop with improved context handles those.
    """
    if not _is_stategraph(lua_source):
        return False
    if not extract_stategraph_event_names(lua_source):
        return False
    text_lower = section_text.lower()
    # "listens to:" followed by any combination of bold markers/whitespace then "none"
    listens_to_none = bool(re.search(r'listens to:[\s*]*none\b', text_lower))
    bold_none = "**none.**" in text_lower and "eventhandler" not in text_lower
    return listens_to_none or bold_none


def extract_section_lua_context(
    section_heading: str,
    lua_source: str,
    max_tokens: int,
) -> str:
    """Return a Lua excerpt tailored to the section being reviewed.

    Each heading type receives a different extraction strategy.
    Returns "" for unknown section types.
    """
    lines = lua_source.splitlines(keepends=True)

    if section_heading == "## Overview":
        # Lines up to (not including) the first function definition
        module_lines: list[str] = []
        for line in lines:
            if re.match(r'^(local\s+)?function\b', line):
                break
            module_lines.append(line.rstrip("\n"))
        blocks = ["\n".join(module_lines)] if module_lines else []

    elif section_heading == "## Usage example":
        # Public function signatures: definition line only, no body
        sig_lines = [
            line.rstrip("\n")
            for line in lines
            if re.match(r'^function\s+\w+', line)
        ]
        blocks = sig_lines  # one item per signature line

    elif section_heading == "## Dependencies & tags":
        dep_lines = [
            line.rstrip("\n")
            for line in lines
            if re.search(r'require\(|\.components\.|:HasTag\(|:AddTag\(|:RemoveTag\(', line)
        ]
        blocks = ["\n".join(dep_lines)] if dep_lines else []

    elif section_heading == "## Properties":
        if _is_stategraph(lua_source):
            # Stategraph: file-scope constants + CommonStates/character-specific injections
            # + StateGraph call header + synthesized state name list.
            # Known limitation: character-specific injection modules without 'SG' prefix
            # (e.g. WillowCommon) are not matched by SG\w+Common pattern.
            sg_lines: list[str] = []
            for line in lines:
                stripped = line.rstrip("\n")
                if (re.match(r'^local\s+[A-Z_]+\s*=', stripped)
                        or re.search(r'CommonStates\.\w+\s*\(', stripped)
                        or re.search(r'SG\w+Common\.\w+\s*\(', stripped)
                        or re.search(r'\bStateGraph\s*\(', stripped)):
                    sg_lines.append(stripped)
            state_names = re.findall(r'\bState\s*\{\s*name\s*=\s*"([^"]+)"', lua_source)
            if state_names:
                sg_lines.append(f"-- States defined inline: {', '.join(state_names)}")
            blocks = ["\n".join(sg_lines)] if sg_lines else []
        else:
            # existing Class() constructor + utility fallback (unchanged)
            class_match = re.search(r'\bClass\s*\(', lua_source)
            if class_match:
                # Extract constructor body: from the Class( line to the closing end)
                # The constructor argument is function(self, inst) ... end)
                # Find the closing end) that closes the Class( call, then capture
                # everything from the start of the Class line up to that point.
                start = lua_source.rfind("\n", 0, class_match.start()) + 1
                tail = lua_source[class_match.end():]
                # Find the constructor's closing 'end)' — first occurrence after Class(
                end_paren_match = re.search(r'\bend\s*\)', tail)
                if end_paren_match:
                    end = class_match.end() + end_paren_match.end()
                else:
                    # Fallback: up to next top-level function after skipping one fn keyword
                    after_first_fn = re.sub(r'function\b', '', tail, count=1)
                    end_match = re.search(r'(?m)^(local\s+)?function\b', after_first_fn)
                    end = class_match.end() + end_match.start() if end_match else len(lua_source)
                blocks = [lua_source[start:end]]
            else:
                # Utility module fallback: module-level constants + table assignments
                prop_lines = [
                    line.rstrip("\n")
                    for line in lines
                    if re.match(r'^local\s+[A-Z_]+\s*=', line)
                    or re.match(r'^\w+\.\w+\s*=', line)
                ]
                blocks = ["\n".join(prop_lines)] if prop_lines else []

    elif section_heading == "## Events & listeners":
        ctx_parts: list[str] = []
        for i, line in enumerate(lines):
            if re.search(r'ListenForEvent|PushEvent|EventHandler\s*\(', line):
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                ctx_parts.extend(l.rstrip("\n") for l in lines[start:end])
                ctx_parts.append("---")
        blocks = ["\n".join(ctx_parts)] if ctx_parts else []

    elif section_heading == "## Action Handlers":
        ctx_parts: list[str] = []
        for i, line in enumerate(lines):
            if re.search(r'ActionHandler\s*\(', line):
                start = max(0, i - 1)
                end = min(len(lines), i + 4)
                ctx_parts.extend(l.rstrip("\n") for l in lines[start:end])
                ctx_parts.append("---")
        blocks = ["\n".join(ctx_parts)] if ctx_parts else []

    else:
        return ""

    return _truncate_blocks_to_lua_limit(blocks, max_tokens)


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
