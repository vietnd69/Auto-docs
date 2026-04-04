"""Auto-fix strategies for format validation. Returns FixResult with changes and remaining errors."""
import json
import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from llm.settings import MDX_NODE_TIMEOUT
from validator.format.checks import ValidationError

@dataclass
class FixResult:
    """Result of an autofix run."""
    changes: list[str]
    remaining_errors: list[ValidationError]

# ── 1. Chạy validate để lấy errors ────────────────────────────────
def get_mdx_errors(filepath: str) -> list[dict]:
    """Trả về list errors có line/col info.

    Sử dụng --experimental-vm-modules để evaluate compiled MDX output,
    bắt được cả ReferenceError (bare identifiers trong {…}).
    """
    script = Path(__file__).parent / "validate_mdx.mjs"
    result = subprocess.run(
        ["node", "--experimental-vm-modules", str(script), filepath],
        capture_output=True, text=True, timeout=MDX_NODE_TIMEOUT
    )
    # stdout chứa JSON, stderr có thể có ExperimentalWarning → bỏ qua
    data = json.loads(result.stdout)
    errors = []
    for e in data.get("errors", []):
        # 1. Parse tag errors: "Expected a closing tag for `<string>` (54:24-54:32)"
        tag_match = re.search(r'Expected a closing tag for `<([^>]+)>` \((\d+):(\d+)', e)
        # Parse: "[mdx] ... (line 61, col 99)"
        match = re.search(r'line (-?\d+), col (-?\d+)', e)
        # Parse identifier từ ReferenceError nếu có
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
    """Tự động thêm --- ở đầu/cuối block YAML nếu bị thiếu."""
    lines = text.splitlines(keepends=True)
    if not lines:
        return text, False

    changed = False

    # 1. Kiểm tra nếu bắt đầu bằng key chuẩn (id:, title:) thay vì ---
    if re.match(r'^[a-z_]+:', lines[0]):
        lines.insert(0, "---\n")
        changed = True

    # 2. Tìm điểm kết thúc YAML (dòng trống, hoặc bắt đầu markdown #)
    # Thường frontmatter sẽ kết thúc bằng ---, nếu thiếu thì tự chèn vào.
    if lines[0] == "---\n":
        has_end_delimiter = False
        end_idx = -1
        for i in range(1, len(lines)):
            if lines[i] == "---\n":
                has_end_delimiter = True
                break
            # Nếu gặp markdown heading (#) hoặc blockquote (>), chắc chắn hết YAML
            if lines[i].startswith("#") or lines[i].startswith("> "):
                end_idx = i
                break
            # Nếu gặp dòng trống, kiểm tra dòng tiếp theo có phải YAML key không
            if lines[i].strip() == "":
                # Lookahead: nếu dòng kế tiếp vẫn là YAML key (ví dụ: "last_updated:")
                # thì bỏ qua dòng trống này và tiếp tục quét
                if i + 1 < len(lines) and re.match(r'^[a-z_]+:', lines[i + 1]):
                    continue
                end_idx = i
                break

        if not has_end_delimiter and end_idx != -1:
            lines.insert(end_idx, "---\n")
            changed = True

    return "".join(lines), changed

def fix_split_frontmatter(text: str) -> tuple[str, bool]:
    """Sửa lỗi do autofix cũ gây ra: --- bị chèn giữa chừng,
    khiến các YAML key bị rơi ra ngoài frontmatter.

    Pattern cần detect:
      ---
      key1: val1
      ---           <- closing quá sớm
      (blank?)
      key2: val2    <- orphaned YAML keys
      key3: val3
      (blank)
      # Heading     <- actual content

    Fix: gom orphaned keys vào bên trong frontmatter, trước ---.
    """
    lines = text.splitlines(keepends=True)
    if len(lines) < 3:
        return text, False

    # Tìm vị trí closing --- của frontmatter
    if lines[0].strip() != '---':
        return text, False

    close_idx = -1
    for i in range(1, len(lines)):
        if lines[i].strip() == '---':
            close_idx = i
            break

    if close_idx == -1:
        return text, False

    # Quét sau closing --- để tìm orphaned YAML keys
    orphaned_keys = []
    scan_start = close_idx + 1
    i = scan_start

    while i < len(lines):
        line = lines[i]
        # Bỏ qua dòng trống
        if line.strip() == '':
            i += 1
            continue
        # Nếu là YAML key (ví dụ: "last_updated: 2026-03-03")
        if re.match(r'^[a-z_]+:', line):
            orphaned_keys.append(line)
            i += 1
            continue
        # Gặp non-YAML content (markdown heading, text, etc.) -> dừng
        break

    if not orphaned_keys:
        return text, False

    # Gom orphaned keys vào trước closing ---
    # Xây dựng lại file: [opening --- ... existing keys] + [orphaned keys] + [---] + [rest]
    before_close = lines[:close_idx]
    rest_after_orphans = lines[i:]  # phần content thực sự

    new_lines = before_close + orphaned_keys + ['---\n'] + rest_after_orphans

    return ''.join(new_lines), True

def fix_yaml_mapping_colon_in_description(text: str) -> tuple[str, bool]:
    """
    Sửa lỗi `mapping values are not allowed` do có dấu `:` giữa dòng description.
    Ví dụ: `description: ABCD: EFGH`
    Sẽ wrap nguyên block value của description trong nháy kép `"..."`.
    """
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match:
        return text, False

    fm = fm_match.group(1)

    changed = False
    new_lines = []

    for line in fm.splitlines():
        if line.startswith("description:"):
            # Lấy phần value
            val = line[len("description:"):].strip()
            # Nếu value đã được bọc trong nháy kép rồi thì bỏ qua
            if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                new_lines.append(line)
            elif ':' in val: # Nếu có dấu ':' trong chuỗi không được bọc
                # Đổi double quotes bên trong thành single quote trước khi bọc
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
    """Xóa các đoạn text rác cuối file như (End of documentation)."""
    pattern = re.compile(r'\n*\**\(End of [^)]*(?:documentation|example)[^)]*\)\**\s*$', re.IGNORECASE)
    if pattern.search(text):
        new_text = pattern.sub('\n', text)
        return new_text, True
    return text, False

def remove_extra_dividers(text: str) -> tuple[str, int]:
    """Xóa các dòng --- dư thừa ở cuối body (sau frontmatter), tương tự filler text."""
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match:
        return text, 0

    fm_end_idx = fm_match.end()
    frontmatter_part = text[:fm_end_idx]
    body_part = text[fm_end_idx:]

    lines = body_part.splitlines(keepends=True)
    count = 0

    # Walk backwards: bỏ qua blank lines, xóa --- ở cuối body
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
    Sửa lỗi frontmatter:
    - `tags: []` -> `tags: [stub]`
    - Các giá trị placeholder kiểu `<...>` hoặc `[]` sẽ được thay bằng "TODO".
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
            applied.append("Thay thế `tags: []` thành `tags: [stub]`")

        # 2. Xóa hoặc thay thế placeholder <...> (cẩn thận không dính vào các key hợp lệ)
        elif bool(re.search(r'<[^>]+>|\[\]', line)):
            # Tạm thời thay placeholder thành "TODO" (với ngoặc kép cho an toàn YAML)
            line = re.sub(r'<[^>]+>|\[\]', '"TODO"', line)
            applied.append("Thay thế placeholder `<...>` hoặc `[]` thành `\"TODO\"`")

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

# ── 2. Fix logic theo từng loại lỗi ───────────────────────────────
def is_inside_backticks(line: str, col: int) -> bool:
    """Kiểm tra position col có nằm trong `...` không"""
    inside = False
    for i, ch in enumerate(line):
        if ch == '`':
            inside = not inside
        if i == col and inside:
            return True
    return False


def fix_bare_operator_on_line(line: str, col: int, char: str) -> str:
    """
    Tìm expression chứa char tại col (hoặc overlap col) và wrap bằng backtick.
    Ví dụ: '., <= 0.05 in' -> '., `<= 0.05` in'
    """
    if is_inside_backticks(line, col):
        return line

    # Tìm expression chứa operator. Hỗ trợ bắt qua khoảng trắng và ký tự alphanumeric
    pattern = re.compile(
        r'([a-zA-Z0-9_.]*\s*(?:<=|>=|!=|==|<->|->|<-|<|>|=)\s*[a-zA-Z0-9_.]*)'
    )

    def wrap(m):
        start, end = m.start(), m.end()
        if start <= col <= end:
            val = m.group(0)
            # Giữ lại khoảng trắng 2 đầu nếu regex bắt dính
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
    """Fix ReferenceError bằng cách wrap {…} chứa identifier bằng backtick.

    Khi MDX gặp {x,z} hoặc {number, number} trong prose, nó compile thành
    JavaScript reference tới biến x, z, number… gây ReferenceError.
    Hàm này tìm tất cả {…} chứa identifier cụ thể và wrap bằng backtick.

    Args:
        text: Nội dung file
        identifier: Tên biến gây ReferenceError (e.g., 'x', 'number', 'Entity')

    Returns:
        (text_mới, số_lượng_fix)
    """
    lines = text.splitlines(keepends=True)
    count = 0
    in_code_block = False

    # Pattern: tìm {…} chứa identifier, không nằm trong backtick
    brace_pattern = re.compile(
        r'(?<!`)\{([^{}`\n]*\b' + re.escape(identifier) + r'\b[^{}`\n]*)\}(?!`)'
    )

    for idx, line in enumerate(lines):
        stripped = line.strip()

        # Track code blocks
        if stripped.startswith('```'):
            in_code_block = not in_code_block
            continue
        if in_code_block:
            continue

        # Split dòng theo inline backtick để không đụng vào code inline
        parts = re.split(r'(`[^`\n]+`)', line)
        new_parts = []
        line_changed = False

        for j, part in enumerate(parts):
            if j % 2 == 1:  # inline code → giữ nguyên
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
    Sửa lỗi LLM generate code block nhiều dòng nhưng dùng ` (inline backtick) thay vì ```lua.
    Đồng thời xoá lồng backtick bên trong.
    Ví dụ:
      `{
        `{abc=1}`,
      }`
    Thành:
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

def fix_empty_properties_section(text: str) -> tuple[str, bool]:
    """
    Nếu ## Properties section không có data rows, tự động thêm row None.
    Xử lý 2 case:
    - Không có table nào → inject full table (header + separator + None row)
    - Có header + separator nhưng không có data rows → thêm None row sau separator
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
        # Case 1: không có table — inject full table
        none_table = (
            "\n"
            "| Property | Type | Default Value | Description |\n"
            "|----------|------|---------------|-------------|\n"
            f"{none_row}\n"
        )
        return text[:after_start] + none_table + text[after_start:], True

    # Case 2: có table rows — kiểm tra data rows (non-separator, non-header)
    is_separator = lambda row: bool(re.match(r'^\|[\s\-:|]+\|$', row.strip()))
    non_separator = [r for r in table_lines if not is_separator(r)]

    # non_separator[0] = header row; non_separator[1:] = data rows
    if len(non_separator) > 1:
        return text, False  # Đã có data rows, không cần fix

    # Chỉ có header (hoặc chỉ separator) — thêm None row sau separator cuối cùng
    sep_match = re.search(r'^\|[\s\-:|]+\|[^\n]*\n', section_body, re.MULTILINE)
    if sep_match:
        insert_pos = after_start + sep_match.end()
        return text[:insert_pos] + f"{none_row}\n" + text[insert_pos:], True

    # Fallback: separator không tìm thấy — inject full table
    none_table = (
        "\n"
        "| Property | Type | Default Value | Description |\n"
        "|----------|------|---------------|-------------|\n"
        f"{none_row}\n"
    )
    return text[:after_start] + none_table + text[after_start:], True


def prune_duplicated_content(text: str) -> tuple[str, bool]:
    """
    Phát hiện và cắt bỏ nội dung bị lặp lại (ví dụ: toàn bộ file bị append thêm n lần).
    Dựa trên việc tìm thấy tiêu đề H1 thứ hai hoặc cụm frontmatter keys lặp lại.
    """
    # 1. Tìm tiêu đề H1 đầu tiên
    h1_match = re.search(r'^#\s+(.+)$', text, re.MULTILINE)
    if not h1_match:
        return text, False

    h1_text = h1_match.group(0)
    h1_start = h1_match.start()

    # Tìm H1 tiếp theo giống hệt (thường là bắt đầu block lặp)
    # Tìm kiếm bắt đầu sau H1 đầu tiên một khoảng (tránh match chính nó)
    second_h1_match = re.search(re.escape(h1_text), text[h1_start + len(h1_text):], re.MULTILINE)

    split_point = -1

    if second_h1_match:
        # Kiểm tra ngược lên một chút xem có cụm YAML keys không (id:, title:)
        # Vì thường block lặp bắt đầu bằng phần YAML bị lỗi/rơi ra ngoài
        potential_start = h1_start + len(h1_text) + second_h1_match.start()

        # Nhìn ngược tối đa 500 ký tự để tìm cụm 'id:' hoặc 'title:'
        search_back_area = text[max(0, potential_start-500):potential_start]
        yaml_start_match = re.search(r'^(id|title|description|category_type):', search_back_area, re.MULTILINE)

        if yaml_start_match:
            # Điểm cắt là vị trí của YAML key đầu tiên trong cụm lặp
            split_point = max(0, potential_start - 500) + yaml_start_match.start()
        else:
            # Điểm cắt chính là tiêu đề H1 thứ hai
            split_point = potential_start

    if split_point != -1:
        # Cắt tài liệu tại điểm phát hiện lặp
        pruned_text = text[:split_point]
        # Đảm bảo kết thúc bằng một dòng trống hoặc giữ nguyên newline cuối
        return pruned_text.rstrip() + "\n", True

    return text, False

# ── 3. Apply fix vào file ──────────────────────────────────────────
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
            applied.append(f"Đã thêm {field}: {value}")

    return text, applied


def autofix_file(filepath: str, dry_run: bool = False, skip_heading_check: bool = False) -> FixResult:
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

    # Recover missing source_hash from Lua source
    new_text, recovered_hash = _fix_missing_source_hash(filepath, text)
    if recovered_hash is not None:
        text = new_text
        applied.append(f"Đã thêm source_hash: {recovered_hash} (khôi phục từ file Lua).")

    # Fix --- delimiter
    new_text, changed_delim = fix_frontmatter_delimiters(text)
    if changed_delim:
        text = new_text
        applied.append("Đã thêm `---` cho YAML frontmatter.")

    # Fix split frontmatter (lỗi do autofix cũ gây ra)
    new_text, changed_split = fix_split_frontmatter(text)
    if changed_split:
        text = new_text
        applied.append("Đã gom YAML keys bị rơi ra ngoài frontmatter.")

    # Fix filler text
    new_text, changed_filler = remove_filler_text(text)
    if changed_filler:
        text = new_text
        applied.append("Đã xoá đoạn text rác cuối file.")

    # Fix extra dividers
    new_text, removed_dividers = remove_extra_dividers(text)
    if removed_dividers > 0:
        text = new_text
        applied.append(f"Đã xoá {removed_dividers} dòng `---` dư thừa.")

    # Fix | inside backtick expressions in table rows
    new_text, pipe_count = fix_table_pipes(text)
    if pipe_count > 0:
        text = new_text
        applied.append(f"Đã escape {pipe_count} dấu | trong backtick expression (table rows).")

    # Fix bare {…} expressions in prose (MDX treats as JSX)
    new_text, brace_count = fix_bare_curly_braces(text)
    if brace_count > 0:
        text = new_text
        applied.append(f"Đã wrap {brace_count} bare {{...}} expression(s) bằng backtick.")

    # Fix description with colons causing YAML mapping errors
    new_text, desc_changed = fix_yaml_mapping_colon_in_description(text)
    if desc_changed:
        text = new_text
        applied.append("Đã wrap `description` chứa dấu hai chấm (:) vào nháy kép để sửa lỗi YAML.")

    # Fix empty tags and unfilled placeholders
    new_text, placeholder_fixes = fix_empty_tags_and_placeholders(text)
    if placeholder_fixes:
        text = new_text
        applied.extend(placeholder_fixes)

    # Fix tags missing []
    new_text, changed_tags = fix_tags_format(text)
    if changed_tags:
        text = new_text
        applied.append("Đã thêm `[]` cho `tags` trong frontmatter.")

    # Fix malformed multiline inline backticks into ```lua blocks
    new_text, malformed_count = fix_malformed_multiline_backticks(text)
    if malformed_count > 0:
        text = new_text
        applied.append(f"Đã convert {malformed_count} block(s) multi-line backtick lỗi thành codeblock ```lua.")

    # Prune duplicated content (catcoonden.md case)
    new_text, pruned = prune_duplicated_content(text)
    if pruned:
        text = new_text
        applied.append("Đã phát hiện và cắt bỏ nội dung bị lặp lại trong file.")

    # Fix empty ## Properties section (add None table)
    new_text, props_fixed = fix_empty_properties_section(text)
    if props_fixed:
        text = new_text
        applied.append("Đã thêm bảng None vào ## Properties section trống.")

    # Fix missing blank line before ## / ### headings
    new_text, heading_fixes = fix_missing_blank_line_before_headings(text)
    if heading_fixes > 0:
        text = new_text
        applied.append(f"Đã thêm blank line trước {heading_fixes} heading(s) bị thiếu.")

    # Ghi file một lần duy nhất cho Phase 1 nếu có thay đổi
    if not dry_run and text != original_text:
        path.write_text(text, encoding="utf-8")

    # --- PHASE 2: MDX Loop (Iterative write for Node validator) ---

    lines = text.splitlines(keepends=True)

    # Loop: fix → re-validate → fix tiếp cho đến khi hết lỗi
    for attempt in range(10):  # max 10 vòng tránh loop vô hạn
        errors = get_mdx_errors(filepath)
        if not errors:
            break

        for err in errors:
            line_no = err["line"] - 1  # 0-indexed
            col_no  = err["col"] - 1

            # ReferenceError: identifier is not defined
            # → wrap {…identifier…} bằng backtick
            if err.get("identifier"):
                current_text = "".join(lines)
                new_text, ref_count = fix_reference_errors(current_text, err["identifier"])
                if ref_count > 0:
                    lines = new_text.splitlines(keepends=True)
                    applied.append(
                        f"Đã wrap {ref_count} bare {{...{err['identifier']}...}} expression(s) bằng backtick."
                    )
                    if not dry_run:
                        path.write_text(new_text, encoding="utf-8")
                    text = new_text
                continue

            # Unclosed expected tag: `<tag>`
            # → wrap `<tag>` bằng backtick
            if err.get("unclosed_tag"):
                tag = err["unclosed_tag"]
                if line_no >= 0 and line_no < len(lines):
                    original = lines[line_no]
                    # Simply try replacing `<tag>` with `` `<tag>` ``
                    fixed = original.replace(f"<{tag}>", f"`<{tag}>`")
                    if fixed != original:
                        lines[line_no] = fixed
                        applied.append(f"Line {line_no+1}: Wrapped unclosed tag `<{tag}>` in backticks.")
                        if not dry_run:
                            path.write_text("".join(lines), encoding="utf-8")
                continue

            if line_no >= len(lines) or line_no < 0:
                continue

            original = lines[line_no]
            fixed    = fix_bare_operator_on_line(original, col_no, "")

            if fixed != original:
                lines[line_no] = fixed
                applied.append(
                    f"Line {err['line']}: {original.strip()!r}\n"
                    f"          -> {fixed.strip()!r}"
                )
                # Ghi file ngay để vòng sau validate lại
                if not dry_run:
                    path.write_text("".join(lines), encoding="utf-8")

    # Get remaining errors via unified validate_all()
    from validator.format.checks import validate_all
    remaining = validate_all(filepath, skip_heading_check=skip_heading_check) if not dry_run else []
    return FixResult(changes=applied, remaining_errors=remaining)


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


# ── 4. Fallback: fix thô toàn bộ file ─────────────────────────────
def fix_all_bare_operators(text: str) -> str:
    """
    Fallback nếu line/col không đủ chính xác.
    Wrap tất cả expression dạng 'word op word' nằm ngoài backtick/codeblock.
    """
    # Tách code blocks ra, chỉ xử lý prose
    parts = re.split(r'(```[\s\S]*?```|`[^`\n]+`)', text)
    result = []
    for i, part in enumerate(parts):
        if i % 2 == 1:  # code block/inline code → giữ nguyên
            result.append(part)
        else:
            fixed = re.sub(
                r'(?<![`\w])([\w.]+\s*(?:<=|>=|!=|==|<|>|=)\s*[\w.]+)(?![`\w])',
                r'`\1`',
                part
            )
            result.append(fixed)
    return "".join(result)  # trả về đã fix


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
