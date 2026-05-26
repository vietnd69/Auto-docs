"""Auto-fix strategies for format validation. Returns FixResult with changes and remaining errors."""
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from llm.settings import MDX_NODE_TIMEOUT
from validator.format.checks import ValidationError


def _print(msg: str) -> None:
    """Print safely on narrow Windows terminals (e.g. CP1252) by replacing unencodable chars."""
    try:
        print(msg)
    except UnicodeEncodeError:
        enc = sys.stdout.encoding or "utf-8"
        print(msg.encode(enc, errors="replace").decode(enc, errors="replace"))

@dataclass
class FixResult:
    """Result of an autofix run."""
    changes: list[str]
    remaining_errors: list[ValidationError]

# ── 1. Run validate to get errors ─────────────────────────────────
def get_mdx_errors(filepath: str) -> list[dict]:
    """Return list of errors with line/col info.

    Uses --experimental-vm-modules to evaluate compiled MDX output,
    catching ReferenceError (bare identifiers inside {…}) as well.
    """
    script = Path(__file__).parent / "validate_mdx.mjs"
    result = subprocess.run(
        ["node", "--experimental-vm-modules", str(script), filepath],
        capture_output=True, text=True, timeout=MDX_NODE_TIMEOUT
    )
    # stdout contains JSON; stderr may have ExperimentalWarning → ignore
    data = json.loads(result.stdout)
    errors = []
    for e in data.get("errors", []):
        # 1. Parse tag errors: "Expected a closing tag for `<string>` (54:24-54:32)"
        tag_match = re.search(r'Expected a closing tag for `<([^>]+)>` \((\d+):(\d+)', e)
        # Parse: "[mdx] ... (line 61, col 99)"
        match = re.search(r'line (-?\d+), col (-?\d+)', e)
        # Parse identifier from ReferenceError if present
        ref_match = re.search(r'ReferenceError: (\w+) is not defined', e)

        if tag_match:
            errors.append({
                "message": e,
                "line": int(tag_match.group(2)),
                "col": int(tag_match.group(3)),
                "unclosed_tag": tag_match.group(1),
            })
        elif match:
            errors.append({
                "message": e,
                "line": int(match.group(1)),
                "col": int(match.group(2)),
                "identifier": ref_match.group(1) if ref_match else None,
            })
    return errors



def fix_frontmatter_delimiters(text: str) -> tuple[str, bool]:
    """Automatically add --- at the start/end of the YAML block if missing."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return text, False

    changed = False

    # 1. Check if the file starts with a standard key (id:, title:) instead of ---
    if re.match(r'^[a-z_]+:', lines[0]):
        lines.insert(0, "---\n")
        changed = True

    # 2. Find the end of the YAML block (blank lines, or start of markdown #)
    # Frontmatter should end with ---; if missing, insert it automatically.
    if lines[0] == "---\n":
        has_end_delimiter = False
        end_idx = -1
        for i in range(1, len(lines)):
            if lines[i] == "---\n":
                has_end_delimiter = True
                break
            # If we hit a markdown heading (#) or blockquote (>), YAML has definitely ended
            if lines[i].startswith("#") or lines[i].startswith("> "):
                end_idx = i
                break
            # If we hit a blank line, check whether the next line is still a YAML key
            if lines[i].strip() == "":
                # Lookahead: if the next line is still a YAML key (e.g. "last_updated:")
                # skip this blank line and continue scanning
                if i + 1 < len(lines) and re.match(r'^[a-z_]+:', lines[i + 1]):
                    continue
                end_idx = i
                break

        if not has_end_delimiter and end_idx != -1:
            lines.insert(end_idx, "---\n")
            changed = True

    return "".join(lines), changed

def fix_split_frontmatter(text: str) -> tuple[str, bool]:
    """Fix a bug caused by old autofix: --- inserted mid-file,
    causing YAML keys to fall outside the frontmatter block.

    Pattern to detect:
      ---
      key1: val1
      ---           <- closing too early
      (blank?)
      key2: val2    <- orphaned YAML keys
      key3: val3
      (blank)
      # Heading     <- actual content

    Fix: merge orphaned keys back inside the frontmatter, before ---.
    """
    lines = text.splitlines(keepends=True)
    if len(lines) < 3:
        return text, False

    # Find the position of the closing --- of the frontmatter
    if lines[0].strip() != '---':
        return text, False

    close_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            close_idx = i
            break

    if close_idx == -1:
        return text, False

    # Scan after closing --- to find orphaned YAML keys
    orphaned_keys = []
    scan_start = close_idx + 1
    i = scan_start

    while i < len(lines):
        line = lines[i]
        # Skip blank lines
        if line.strip() == '':
            i += 1
            continue
        # If it is a YAML key (e.g. "last_updated: 2026-03-03")
        if re.match(r'^[a-z_]+:', line):
            orphaned_keys.append(line)
            i += 1
            continue
        # Hit non-YAML content (markdown heading, text, etc.) -> stop
        break

    if not orphaned_keys:
        return text, False

    # Merge orphaned keys before closing ---
    # Rebuild file: [opening --- ... existing keys] + [orphaned keys] + [---] + [rest]
    before_close = lines[:close_idx]
    rest_after_orphans = lines[i:]  # actual content section

    new_lines = before_close + orphaned_keys + ['---\n'] + rest_after_orphans

    return ''.join(new_lines), True

def fix_yaml_mapping_colon_in_description(text: str) -> tuple[str, bool]:
    """
    Fix `mapping values are not allowed` errors caused by a `:` inside the description value.
    Example: `description: ABCD: EFGH`
    Wraps the entire description value in double quotes `"..."`.
    """
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match:
        return text, False

    fm = fm_match.group(1)

    changed = False
    new_lines = []

    for line in fm.splitlines():
        if line.startswith("description:"):
            # Get the value part
            val = line[len("description:"):].strip()
            # If the value is already wrapped in quotes, leave it alone
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                new_lines.append(line)
            elif ':' in val: # If there is a ':' in the unquoted string
                # Replace internal double quotes with single quotes before wrapping
                safe_val = val.replace('"', "'")
                new_line = f'description: "{safe_val}"'
                new_lines.append(new_line)
                changed = True
            else:
                new_lines.append(line)
        else:
            new_lines.append(line)

    if changed:
        new_fm = "\n".join(new_lines)
        new_text = f"---\n{new_fm}\n---\n" + text[fm_match.end():]
        return new_text, True

    return text, False

def remove_filler_text(text: str) -> tuple[str, bool]:
    """Remove filler text at the end of the file such as (End of documentation)."""
    pattern = re.compile(r'\n*\**\(End of [^)]*(?:documentation|example)[^)]*\)\**\s*$', re.IGNORECASE)
    if pattern.search(text):
        new_text = pattern.sub('\n', text)
        return new_text, True
    return text, False

def remove_extra_dividers(text: str) -> tuple[str, int]:
    """Remove extra --- lines at the end of the body (after frontmatter), similar to filler text."""
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match:
        return text, 0

    fm_end_idx = fm_match.end()
    frontmatter_part = text[:fm_end_idx]
    body_part = text[fm_end_idx:]

    lines = body_part.splitlines(keepends=True)
    count = 0

    # Walk backwards: skip blank lines, remove --- at the end of the body
    while lines:
        stripped = lines[-1].strip()
        if stripped == '':
            lines.pop()
            continue
        if stripped == '---':
            lines.pop()
            count += 1
            continue
        break

    if count > 0:
        body = "".join(lines)
        if body and not body.endswith('\n'):
            body += '\n'
        return frontmatter_part + body, count

    return text, 0

def fix_empty_tags_and_placeholders(text: str) -> tuple[str, list[str]]:
    """
    Fix frontmatter issues:
    - `tags: []` -> `tags: [stub]`
    - Placeholder values of the form `<...>` or `[]` are replaced with "TODO".
    """
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match:
        return text, []

    fm = fm_match.group(1)
    new_lines = []
    applied = []

    for line in fm.splitlines():
        # 1. tags: []
        if re.match(r'^tags:\s*\[\s*\]\s*$', line):
            line = "tags: [stub]"
            applied.append("Replaced `tags: []` with `tags: [stub]`")

        # 2. Remove or replace placeholder <...> (be careful not to touch valid keys)
        elif bool(re.search(r'<[^>]+>|\[\]', line)):
            # Temporarily replace placeholder with "TODO" (double-quoted for YAML safety)
            line = re.sub(r'<[^>]+>|\[\]', '"TODO"', line)
            applied.append("Replaced placeholder `<...>` or `[]` with `\"TODO\"`")

        new_lines.append(line)

    if applied:
        new_fm = "\n".join(new_lines)
        new_text = f"---\n{new_fm}\n---\n" + text[fm_match.end():]
        return new_text, list(set(applied))

    return text, []

def fix_tags_format(text: str) -> tuple[str, bool]:
    """Wrap tags in square brackets if they are missing."""
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match:
        return text, False
    fm = fm_match.group(1)
    new_lines = []
    changed = False
    for line in fm.splitlines():
        # Match tags: tag1, tag2... (no brackets)
        tag_match = re.match(r'^tags:\s*([^\[\s\n].*)$', line)
        if tag_match:
            tags_content = tag_match.group(1).strip()
            # If it's already a list or placeholder, skip
            if not tags_content.startswith('[') and not tags_content.endswith(']'):
                line = f"tags: [{tags_content}]"
                changed = True
        new_lines.append(line)
    if changed:
        new_fm = "\n".join(new_lines)
        return f"---\n{new_fm}\n---\n" + text[fm_match.end():], True
    return text, False

# ── 2. Fix logic per error type ───────────────────────────────────
def is_inside_backticks(line: str, col: int) -> bool:
    """Check whether column position col is inside `...`"""
    inside = False
    for i, ch in enumerate(line):
        if ch == '`':
            inside = not inside
        if i == col and inside:
            return True
    return False


def fix_bare_operator_on_line(line: str, col: int, char: str) -> str:
    """
    Find the expression containing char at col (or overlapping col) and wrap it in backticks.
    Example: '., <= 0.05 in' -> '., `<= 0.05` in'
    """
    if is_inside_backticks(line, col):
        return line

    # Find the expression containing the operator. Supports matching across whitespace and alphanumeric chars
    pattern = re.compile(
        r'([a-zA-Z0-9_.]*\s*(?:<=|>=|!=|==|<->|->|<-|<|>|=)\s*[a-zA-Z0-9_.]*)'
    )

    def wrap(m):
        start, end = m.start(), m.end()
        if start <= col <= end:
            val = m.group(0)
            # Preserve leading/trailing whitespace if the regex captured it
            prefix = val[:len(val) - len(val.lstrip())]
            suffix = val[len(val.rstrip()):]
            return f'{prefix}`{val.strip()}`{suffix}'
        return m.group(0)

    fixed = pattern.sub(wrap, line)
    return fixed


def fix_bare_curly_braces(text: str) -> tuple[str, int]:
    """Wrap bare {…} expressions in prose with backticks.

    MDX treats { } as JSX expressions. When type annotations like
    { thrall_type: string } appear in prose (outside backticks/code blocks),
    acorn fails to parse them. This wraps such expressions in backticks.
    """
    # Split by code blocks and inline code to avoid touching them
    parts = re.split(r'(```[\s\S]*?```|`[^`\n]+`)', text)
    count = 0

    # Pattern: { ... } that is NOT already inside backticks
    # Match { followed by non-empty content (no nested braces for simplicity), then }
    brace_pattern = re.compile(r'(?<!`)\{([^{}`\n]+)\}(?!`)')

    for i in range(len(parts)):
        if i % 2 == 1:  # code block/inline code → skip
            continue

        def wrap_brace(m):
            nonlocal count
            count += 1
            return f'`{m.group(0)}`'

        parts[i] = brace_pattern.sub(wrap_brace, parts[i])

    return "".join(parts), count


def fix_reference_errors(text: str, identifier: str) -> tuple[str, int]:
    """Fix ReferenceError by wrapping {…} expressions containing the identifier in backticks.

    When MDX encounters {x,z} or {number, number} in prose, it compiles them as
    JavaScript references to variables x, z, number… causing a ReferenceError.
    This function finds all {…} expressions containing the specific identifier and wraps them in backticks.

    Args:
        text: File content
        identifier: Variable name causing the ReferenceError (e.g., 'x', 'number', 'Entity')

    Returns:
        (updated_text, fix_count)
    """
    lines = text.splitlines(keepends=True)
    count = 0
    in_code_block = False

    # Pattern: find {…} containing the identifier, not inside backticks.
    # Allows one level of nested {} (e.g. { staticdecorations = {} }).
    _inner = r'(?:[^{}`\n]|\{[^{}`\n]*\})'
    brace_pattern = re.compile(
        r'(?<!`)' + r'\{(' + _inner + r'*\b' + re.escape(identifier) + r'\b' + _inner + r'*)\}(?!`)'
    )

    for idx, line in enumerate(lines):
        stripped = line.strip()

        # Track code blocks
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Split lines on inline backticks to avoid touching inline code
        parts = re.split(r'(`[^`\n]+`)', line)
        new_parts = []
        line_changed = False

        for j, part in enumerate(parts):
            if j % 2 == 1:  # inline code → keep as-is
                new_parts.append(part)
                continue

            def wrap_fn(m):
                nonlocal count, line_changed
                count += 1
                line_changed = True
                return f'`{m.group(0)}`'

            new_parts.append(brace_pattern.sub(wrap_fn, part))

        if line_changed:
            lines[idx] = ''.join(new_parts)

    return ''.join(lines), count


def fix_table_pipes(text: str) -> tuple[str, int]:
    r"""Escape | inside backtick expressions within markdown table rows.

    In markdown tables, | is the column separator. If a backtick expression
    like `(r<<24)|(g<<16)` contains |, it breaks the cell boundary and
    exposes operators like << as bare < to MDX.

    Fix: replace | with \| inside backtick spans on table rows.
    """
    lines = text.splitlines(keepends=True)
    count = 0
    in_code_block = False

    for idx, line in enumerate(lines):
        stripped = line.strip()

        # Track code blocks
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Only process table rows (start with |)
        if not stripped.startswith('|'):
            continue

        # Find backtick spans and escape | inside them
        result = []
        i = 0
        line_str = line
        while i < len(line_str):
            if line_str[i] == '`':
                # Find the closing backtick
                end = line_str.find('`', i + 1)
                if end != -1:
                    # Extract content between backticks
                    inner = line_str[i+1:end]
                    if '|' in inner and '\\|' not in inner:
                        escaped = inner.replace('|', '\\|')
                        result.append('`' + escaped + '`')
                        pipes_fixed = inner.count('|')
                        count += pipes_fixed
                    else:
                        result.append(line_str[i:end+1])
                    i = end + 1
                    continue
            result.append(line_str[i])
            i += 1

        new_line = ''.join(result)
        if new_line != line:
            lines[idx] = new_line

    return ''.join(lines), count


def fix_malformed_multiline_backticks(text: str) -> tuple[str, int]:
    """
    Fix cases where the LLM generates a multi-line code block using ` (inline backtick) instead of ```lua.
    Also removes nested backticks inside the block.
    Example:
      `{
        `{abc=1}`,
      }`
    Becomes:
      ```lua
      {
        {abc=1},
      }
      ```
    """
    lines = text.splitlines(keepends=True)
    count = 0
    i = 0
    while i < len(lines):
        line = lines[i]
        # Detect start of malformed block: e.g. "  `{  \n" or "  `[  \n"
        if re.match(r'^\s*`[\{\[]\s*$', line):
            # Scan down to find the matching closing tag "  }`\n" or "  ]`\n"
            end_idx = -1
            for j in range(i + 1, min(i + 30, len(lines))):
                if re.match(r'^\s*[\}\]]`\s*$', lines[j]):
                    end_idx = j
                    break

            if end_idx != -1:
                count += 1
                # Get the indentation and bracket types
                indent_match = re.match(r'^(\s*)', line)
                indent = indent_match.group(1) if indent_match else ""

                bracket_match = re.search(r'([\{\[])', line)
                bracket = bracket_match.group(1) if bracket_match else "{"

                end_bracket_match = re.search(r'([\}\]])', lines[end_idx])
                end_bracket = end_bracket_match.group(1) if end_bracket_match else "}"

                # Replace start with ```lua and bracket
                lines[i] = f"{indent}```lua\n{indent}{bracket}\n"

                # Replace end with bracket and ```
                lines[end_idx] = f"{indent}{end_bracket}\n{indent}```\n"

                # Clean up inner lines: remove internal backticks
                for k in range(i + 1, end_idx):
                    lines[k] = lines[k].replace('`', '')

                i = end_idx
        i += 1
    return "".join(lines), count

def fix_unclosed_code_fence_before_heading(text: str) -> tuple[str, int]:
    """Close unclosed code fences immediately before ## / ### headings.

    When a ## heading appears inside an open code fence (missing closing ```),
    Docuafterrus renders the entire following section as raw code — headings become invisible.
    Fix: insert a closing ``` + blank line before the affected heading.
    """
    lines = text.splitlines(keepends=True)
    in_fence = False
    insertions = 0
    i = 0
    while i < len(lines):
        stripped = lines[i].strip()
        if stripped.startswith("```"):
            in_fence = not in_fence
        elif in_fence and re.match(r"^#{2,3}\s+", lines[i]):
            lines.insert(i, "```\n")
            in_fence = False
            insertions += 1
            i += 1  # skip the ``` we just inserted; next iteration sees the heading
        i += 1
    return "".join(lines), insertions


def fix_empty_properties_section(text: str) -> tuple[str, bool]:
    """
    If the ## Properties section has no data rows, automatically add a None row.
    Handles 2 cases:
    - No table at all → inject full table (header + separator + None row)
    - Header + separator present but no data rows → add None row after separator
    """
    prop_match = re.search(r'^## Properties\s*$', text, re.MULTILINE)
    if not prop_match:
        return text, False

    after_start = prop_match.end()
    next_heading = re.search(r'^##\s', text[after_start:], re.MULTILINE)
    section_end = after_start + next_heading.start() if next_heading else len(text)
    section_body = text[after_start:section_end]

    table_lines = [l for l in section_body.splitlines() if l.strip().startswith('|')]
    none_row = "| None | | | No properties are defined. |"

    if not table_lines:
        # Case 1: no table — inject full table
        none_table = (
            "\n"
            "| Property | Type | Default Value | Description |\n"
            "|----------|------|---------------|-------------|\n"
            f"{none_row}\n"
        )
        return text[:after_start] + none_table + text[after_start:], True

    # Case 2: table rows present — check for data rows (non-separator, non-header)
    is_separator = lambda row: bool(re.match(r'^\|[\s\-:|]+\|$', row.strip()))
    non_separator = [r for r in table_lines if not is_separator(r)]

    # non_separator[0] = header row; non_separator[1:] = data rows
    if len(non_separator) > 1:
        return text, False  # Data rows already exist, no fix needed

    # Only a header row (or just a separator) — add None row after the last separator
    sep_match = re.search(r'^\|[\s\-:|]+\|[^\n]*\n', section_body, re.MULTILINE)
    if sep_match:
        insert_pos = after_start + sep_match.end()
        return text[:insert_pos] + f"{none_row}\n" + text[insert_pos:], True

    # Fallback: separator not found — inject full table
    none_table = (
        "\n"
        "| Property | Type | Default Value | Description |\n"
        "|----------|------|---------------|-------------|\n"
        f"{none_row}\n"
    )
    return text[:after_start] + none_table + text[after_start:], True


def prune_duplicated_content(text: str) -> tuple[str, bool]:
    """
    Detect and remove duplicated content (e.g. the entire file appended n times).
    Based on finding a second H1 heading or a repeated cluster of frontmatter keys.
    """
    # 1. Find the first H1 heading
    h1_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    if not h1_match:
        return text, False

    h1_text = h1_match.group(0)
    h1_start = h1_match.start()

    # Find the next identical H1 (usually the start of the duplicated block)
    # Search starts after the first H1 by an offset (to avoid matching itself)
    second_h1_match = re.search(re.escape(h1_text), text[h1_start + len(h1_text):], re.MULTILINE)

    split_point = -1

    if second_h1_match:
        # Look backwards a little to check for a cluster of YAML keys (id:, title:)
        # because the duplicated block usually starts with orphaned/broken YAML
        potential_start = h1_start + len(h1_text) + second_h1_match.start()

        # Look back up to 500 characters to find a cluster of 'id:' or 'title:'
        search_back_area = text[max(0, potential_start-500):potential_start]
        yaml_start_match = re.search(r'^(id|title|description|category_type):', search_back_area, re.MULTILINE)

        if yaml_start_match:
            # The cut point is the position of the first YAML key in the duplicated cluster
            split_point = max(0, potential_start - 500) + yaml_start_match.start()
        else:
            # The cut point is the second H1 heading itself
            split_point = potential_start

    if split_point != -1:
        # Truncate the document at the detected duplication point
        pruned_text = text[:split_point]
        # Ensure the file ends with a single newline
        return pruned_text.rstrip() + "\n", True

    return text, False

# ── 3. Apply fixes to file ────────────────────────────────────────
def _fix_missing_source_hash(filepath: str, text: str) -> tuple[str, str | None]:
    """Recover source_hash from the corresponding Lua file if missing in frontmatter.
    Returns (updated_text, hash_value_or_None)."""
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match or re.search(r'^source_hash:', fm_match.group(1), re.MULTILINE):
        return text, None

    from validator.utils import resolve_lua_path
    from rag.docs import safe_read_lua, compute_source_hash, inject_frontmatter_field
    lua_path = resolve_lua_path(filepath)
    if not lua_path:
        return text, None
    lua_code = safe_read_lua(lua_path)
    if not lua_code:
        return text, None
    hash_val = compute_source_hash(lua_code)
    return inject_frontmatter_field(text, "source_hash", hash_val), hash_val


def fix_wrong_id(filepath: str, text: str) -> tuple[str, str | None]:
    """Fix id field if it exists but doesn't match the filename stem (= Lua filename stem).

    Returns (updated_text, old_id) if fixed, or (text, None) if no change needed.
    """
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match:
        return text, None

    expected_id = Path(filepath).stem
    fm_body = fm_match.group(1)

    id_match = re.search(r'^id:\s*(.+)$', fm_body, re.MULTILINE)
    if not id_match:
        return text, None  # missing id handled by _fix_missing_frontmatter_fields

    current_id = id_match.group(1).strip().strip('"\'')
    if current_id == expected_id:
        return text, None

    new_fm_body = re.sub(r'^id:\s*.+$', f'id: {expected_id}', fm_body, flags=re.MULTILINE)
    new_text = f"---\n{new_fm_body}\n---\n" + text[fm_match.end():]
    return new_text, current_id


def _fix_missing_frontmatter_fields(filepath: str, text: str) -> tuple[str, list[str]]:
    """Inject deterministic frontmatter fields that are missing and can be derived from context.

    Handles: id, title, sidebar_position, last_updated, build_version, change_status, category_type.
    Returns (updated_text, list_of_applied_descriptions).
    """
    from datetime import datetime
    from pathlib import Path as _Path
    from rag.docs import inject_frontmatter_field
    from llm.settings import BUILD_VERSION

    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match:
        return text, []

    md_path = _Path(filepath)
    stem = md_path.stem  # filename without .md

    # Derive category_type: first subdir after 'docs/' in the path, or "root" for top-level files
    try:
        parts = md_path.parts
        docs_idx = parts.index("docs")
        rel_parts = parts[docs_idx + 1:]
        category_type = rel_parts[0] if len(rel_parts) > 1 else "root"
    except (ValueError, IndexError):
        category_type = "root"

    defaults = {
        "id":              stem,
        "title":           stem.replace("_", " ").title(),
        "sidebar_position": "10",
        "last_updated":    datetime.now().strftime("%Y-%m-%d"),
        "build_version":   BUILD_VERSION,
        "change_status":   "stable",
        "category_type":   category_type,
    }

    applied = []
    fm_body = fm_match.group(1)
    for field, value in defaults.items():
        if not re.search(rf'^{re.escape(field)}:', fm_body, re.MULTILINE):
            text = inject_frontmatter_field(text, field, str(value))
            fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
            fm_body = fm_match.group(1) if fm_match else fm_body
            applied.append(f"Added {field}: {value}")

    return text, applied


def autofix_file(filepath: str, dry_run: bool = False, accepted_headings: set[str] | None = None) -> FixResult:
    path = Path(filepath)
    original_text = path.read_text(encoding="utf-8")
    text = original_text
    applied = []

    # --- PHASE 1: Static Fixes (In-memory batch) ---

    # Recover missing deterministic frontmatter fields
    new_text, field_fixes = _fix_missing_frontmatter_fields(filepath, text)
    if field_fixes:
        text = new_text
        applied.extend(field_fixes)

    # Fix wrong id (must match filename stem = Lua filename stem)
    new_text, old_id = fix_wrong_id(filepath, text)
    if old_id is not None:
        text = new_text
        applied.append(f"Fixed id: '{old_id}' → '{Path(filepath).stem}' (must match Lua filename stem).")

    # Recover missing source_hash from Lua source
    new_text, recovered_hash = _fix_missing_source_hash(filepath, text)
    if recovered_hash is not None:
        text = new_text
        applied.append(f"Added source_hash: {recovered_hash} (recovered from Lua source file).")

    # Fix --- delimiter
    new_text, changed_delim = fix_frontmatter_delimiters(text)
    if changed_delim:
        text = new_text
        applied.append("Added `---` delimiters for YAML frontmatter.")

    # Fix split frontmatter (bug caused by old autofix)
    new_text, changed_split = fix_split_frontmatter(text)
    if changed_split:
        text = new_text
        applied.append("Merged YAML keys that had fallen outside the frontmatter block.")

    # Fix filler text
    new_text, changed_filler = remove_filler_text(text)
    if changed_filler:
        text = new_text
        applied.append("Removed filler text at the end of the file.")

    # Fix extra dividers
    new_text, removed_dividers = remove_extra_dividers(text)
    if removed_dividers > 0:
        text = new_text
        applied.append(f"Removed {removed_dividers} extra `---` line(s).")

    # Fix | inside backtick expressions in table rows
    new_text, pipe_count = fix_table_pipes(text)
    if pipe_count > 0:
        text = new_text
        applied.append(f"Escaped {pipe_count} | character(s) inside backtick expressions (table rows).")

    # Fix bare {…} expressions in prose (MDX treats as JSX)
    new_text, brace_count = fix_bare_curly_braces(text)
    if brace_count > 0:
        text = new_text
        applied.append(f"Wrapped {brace_count} bare {{...}} expression(s) in backticks.")

    # Fix description with colons causing YAML mapping errors
    new_text, desc_changed = fix_yaml_mapping_colon_in_description(text)
    if desc_changed:
        text = new_text
        applied.append("Wrapped `description` containing a colon (:) in double quotes to fix YAML error.")

    # Fix empty tags and unfilled placeholders
    new_text, placeholder_fixes = fix_empty_tags_and_placeholders(text)
    if placeholder_fixes:
        text = new_text
        applied.extend(placeholder_fixes)

    # Fix tags missing []
    new_text, changed_tags = fix_tags_format(text)
    if changed_tags:
        text = new_text
        applied.append("Added `[]` brackets to `tags` in frontmatter.")

    # Fix malformed multiline inline backticks into ```lua blocks
    new_text, malformed_count = fix_malformed_multiline_backticks(text)
    if malformed_count > 0:
        text = new_text
        applied.append(f"Converted {malformed_count} malformed multi-line backtick block(s) to ```lua codeblocks.")

    # Prune duplicated content (catcoonden.md case)
    new_text, pruned = prune_duplicated_content(text)
    if pruned:
        text = new_text
        applied.append("Detected and removed duplicated content in the file.")

    # Fix empty ## Properties section (add None table)
    new_text, props_fixed = fix_empty_properties_section(text)
    if props_fixed:
        text = new_text
        applied.append("Added None table to empty ## Properties section.")

    # Collapse excessive blank lines (3+ → 2) in prose sections
    new_text, excess_blank_count = fix_excessive_blank_lines(text)
    if excess_blank_count > 0:
        text = new_text
        applied.append(f"Collapsed {excess_blank_count} run(s) of excess blank lines (3+ → 2).")

    # Fix missing blank line before ## / ### headings
    new_text, heading_fixes = fix_missing_blank_line_before_headings(text)
    if heading_fixes > 0:
        text = new_text
        applied.append(f"Added missing blank line before {heading_fixes} heading(s).")

    # Fix unclosed code fences that swallow ## headings (renders sections invisible in Docuafterrus)
    new_text, fence_fixes = fix_unclosed_code_fence_before_heading(text)
    if fence_fixes > 0:
        text = new_text
        applied.append(f"Closed {fence_fixes} unclosed code fence(s) missing ``` before a heading.")

    # Write file once for Phase 1 if any changes were made
    if not dry_run and text != original_text:
        path.write_text(text, encoding="utf-8")

    # Log Phase 1 fixes
    for fix in applied:
        print(f"  [autofix] {fix}")

    # --- PHASE 2: MDX Loop (Iterative write for Node validator) ---

    lines = text.splitlines(keepends=True)

    # Loop: fix → re-validate → fix again until no errors remain
    last_mdx_errors: list[dict] = []
    for attempt in range(10):  # max 10 passes to avoid infinite loop
        last_mdx_errors = get_mdx_errors(filepath)
        if not last_mdx_errors:
            if attempt > 0:
                print(f"  [autofix/mdx] Clean after {attempt} pass(es)")
            break
        print(f"  [autofix/mdx] Pass {attempt + 1}: {len(last_mdx_errors)} error(s)")

        for err in last_mdx_errors:
            line_no = err["line"] - 1  # 0-indexed
            col_no  = err["col"] - 1

            # ReferenceError: identifier is not defined
            # → wrap {…identifier…} in backticks
            if err.get("identifier"):
                current_text = "".join(lines)
                new_text, ref_count = fix_reference_errors(current_text, err["identifier"])
                if ref_count > 0:
                    lines = new_text.splitlines(keepends=True)
                    msg = f"Wrapped {ref_count} bare {{...{err['identifier']}...}} expression(s) in backticks."
                    applied.append(msg)
                    if not dry_run:
                        path.write_text(new_text, encoding="utf-8")
                    text = new_text
                    _print(f"  [autofix] {msg}")
                else:
                    _print(f"  [autofix/mdx] Cannot fix ReferenceError: '{err['identifier']}' not found in any {{...}} expression")
                continue

            # Unclosed expected tag: `<tag>`
            # → wrap `<tag>` in backticks
            if err.get("unclosed_tag"):
                tag = err["unclosed_tag"]
                if line_no >= 0 and line_no < len(lines):
                    original = lines[line_no]
                    fixed = original.replace(f"<{tag}>", f"`<{tag}>`")
                    if fixed != original:
                        lines[line_no] = fixed
                        msg = f"Line {line_no+1}: Wrapped unclosed tag `<{tag}>` in backticks."
                        applied.append(msg)
                        if not dry_run:
                            path.write_text("".join(lines), encoding="utf-8")
                        _print(f"  [autofix] {msg}")
                    else:
                        _print(f"  [autofix/mdx] Cannot fix unclosed tag <{tag}> at line {line_no+1}: pattern not found")
                else:
                    _print(f"  [autofix/mdx] Cannot fix unclosed tag <{tag}>: line {err['line']} out of range")
                continue

            if line_no >= len(lines) or line_no < 0:
                _print(f"  [autofix/mdx] Cannot fix line {err['line']}: out of range (file has {len(lines)} lines)")
                continue

            original = lines[line_no]
            fixed    = fix_bare_operator_on_line(original, col_no, "")

            if fixed != original:
                lines[line_no] = fixed
                msg = (
                    f"Line {err['line']}: {original.strip()!r}\n"
                    f"           -> {fixed.strip()!r}"
                )
                applied.append(msg)
                # Write file immediately so the next pass re-validates it
                if not dry_run:
                    path.write_text("".join(lines), encoding="utf-8")
                _print(f"  [autofix] {msg}")
            else:
                _print(f"  [autofix/mdx] Cannot fix line {err['line']}: no operator match at col {err['col']}")
    else:
        # for-else: loop exhausted all 10 passes without break
        print(f"  [autofix/mdx] Gave up after 10 passes, {len(last_mdx_errors)} MDX error(s) unfixed:")
        for e in last_mdx_errors:
            print(f"  [autofix/mdx]   {e['message'][:120]}")

    # Get remaining errors via unified validate_all()
    from validator.format.checks import validate_all
    remaining = validate_all(filepath, accepted_headings=accepted_headings) if not dry_run else []
    return FixResult(changes=applied, remaining_errors=remaining)


def fix_excessive_blank_lines(text: str) -> tuple[str, int]:
    """Collapse runs of 3+ consecutive blank lines to 2 in prose sections.

    Code blocks (``` fences) are left untouched.
    Returns (fixed_text, number_of_collapsed_runs).
    """
    # Split on fenced code blocks to avoid touching them
    parts = re.split(r'(```[\s\S]*?```)', text)
    count = 0

    for i in range(len(parts)):
        if i % 2 == 1:  # inside a code block → skip
            continue
        fixed, n = re.subn(r'\n{3,}', '\n\n', parts[i])
        parts[i] = fixed
        count += n

    return "".join(parts), count


def fix_missing_blank_line_before_headings(text: str) -> tuple[str, int]:
    """Ensure a blank line before every ## and ### heading.

    Fixes cases like:
        - `tag` -- check
        ## Properties        ← no blank line
    by inserting \\n between the preceding non-blank line and the heading.
    Does not affect headings that already have a blank line before them.
    """
    fixed, count = re.subn(r'([^\n])\n(#{2,3} )', r'\1\n\n\2', text)
    return fixed, count


# ── 4. Fallback: rough fix for the entire file ────────────────────
def fix_all_bare_operators(text: str) -> str:
    """
    Fallback when line/col info is not accurate enough.
    Wrap all 'word op word' expressions outside backticks/codeblocks in backticks.
    """
    # Split out code blocks, process only prose sections
    parts = re.split(r'(```[\s\S]*?```|`[^`\n]+`)', text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # code block/inline code → keep as-is
            result.append(part)
        else:
            fixed = re.sub(
                r'(?<![`\w])([\w.]+\s*(?:<=|>=|!=|==|<|>|=)\s*[\w.]+)(?![`\w])',
                r'`\1`',
                part
            )
            result.append(fixed)
    return "".join(result)  # return fixed text


# ── 5. CLI ─────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    filepath = sys.argv[1]
    dry_run = "--dry-run" in sys.argv
    print(f"Fixing: {filepath}")
    result = autofix_file(filepath, dry_run=dry_run)
    if result.changes:
        print(f"\n{len(result.changes)} fix(es) applied:")
        for c in result.changes:
            print(f"  {c}")
    else:
        print("No changes needed.")
    if result.remaining_errors:
        print(f"\n{len(result.remaining_errors)} remaining errors:")
        for e in result.remaining_errors:
            print(f"  [{e.category}] {e.message}")
    else:
        print("\nAll errors resolved.")
