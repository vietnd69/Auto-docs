"""Format validation checks. Each function detects errors without modifying files."""

import re
from dataclasses import dataclass
from pathlib import Path

import frontmatter


@dataclass
class ValidationError:
    """Structured validation error."""
    category: str      # "mdx", "yaml", "format", "frontmatter"
    severity: str      # "error", "warning"
    message: str
    line: int | None = None


REQUIRED_FIELDS = [
    'id', 'title', 'description', 'tags', 'sidebar_position',
    'last_updated', 'build_version', 'change_status',
    'category_type', 'source_hash', 'system_scope',
]


def check_frontmatter(text: str) -> list[ValidationError]:
    """Validate YAML frontmatter structure and required fields."""
    errors: list[ValidationError] = []

    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n', text)
    if not fm_match:
        errors.append(ValidationError("yaml", "error", "Missing or malformed frontmatter delimiters"))
        return errors

    fm = fm_match.group(1)

    for field in REQUIRED_FIELDS:
        if not re.search(rf'^{field}:', fm, re.MULTILINE):
            errors.append(ValidationError("yaml", "error", f"Missing required field: {field}"))

    if re.search(r'description:\s*(<.*?>|\[\]|automatically generated)', fm):
        errors.append(ValidationError("yaml", "error", "description is placeholder"))

    if re.search(r'tags:\s*\[\s*\]', fm):
        errors.append(ValidationError("yaml", "error", "tags is empty"))

    if re.search(r'^tags:\s*[^\[\s\n].*$', fm, re.MULTILINE):
        errors.append(ValidationError("yaml", "error", "tags missing square brackets []"))

    if re.search(r'last_updated:\s*\{today_date\}', fm):
        errors.append(ValidationError("yaml", "error", "last_updated not filled"))

    if re.search(r'^system_scope:', fm, re.MULTILINE) and not re.search(r'system_scope:\s*[a-z][a-z0-9\-]*\s*$', fm, re.MULTILINE):
        errors.append(ValidationError("yaml", "error", "system_scope missing or invalid format"))

    if re.search(r'<[^>]+>|\[\]', fm):
        errors.append(ValidationError("yaml", "error", "Unfilled placeholder found in frontmatter"))

    body = text[fm_match.end():]
    if re.search(r'^---$', body, re.MULTILINE):
        errors.append(ValidationError("yaml", "error", "Extra '---' divider found in document body"))

    # Detect orphaned YAML keys after closing ---
    post_fm = text[fm_match.end():]
    orphaned_lines = []
    for line in post_fm.splitlines():
        if line.strip() == '':
            continue
        if re.match(r'^[a-z_]+:', line):
            orphaned_lines.append(line.strip())
        else:
            break
    if orphaned_lines:
        errors.append(ValidationError(
            "yaml", "error",
            f"YAML keys outside frontmatter (split): {', '.join(orphaned_lines)}"
        ))

    return errors


def check_id_matches_filename(text: str, filepath: str) -> list[ValidationError]:
    """Check that id field value matches the filename stem (= Lua filename stem)."""
    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n?', text)
    if not fm_match:
        return []
    fm = fm_match.group(1)
    id_match = re.search(r'^id:\s*(.+)$', fm, re.MULTILINE)
    if not id_match:
        return []  # missing id already reported by check_frontmatter
    current_id = id_match.group(1).strip().strip('"\'')
    expected_id = Path(filepath).stem
    if current_id != expected_id:
        return [ValidationError(
            "yaml", "error",
            f"id '{current_id}' does not match filename '{expected_id}' (must match Lua filename stem)"
        )]
    return []


def check_required_headings(text: str, accepted_headings: set[str] | None = None) -> list[ValidationError]:
    """Validate required section headings exist in correct order.

    accepted_headings: standard headings whose absence is jury-accepted (replaced by a non-standard name).
    Only those specific headings are skipped; all others are still validated.
    """
    accepted_headings = accepted_headings or set()
    required_headings = [
        "## Overview",
        "## Usage example",
        "## Dependencies & tags",
        "## Properties",
        "## Main functions",
        "## Events & listeners",
    ]
    errors: list[ValidationError] = []
    last_index = -1
    last_heading = None

    for heading in required_headings:
        if heading in accepted_headings:
            # Jury accepted this heading is replaced by a non-standard name — skip check
            continue
        match = re.search(rf'^{re.escape(heading)}\s*$', text, re.MULTILINE)
        if not match:
            errors.append(ValidationError("format", "error", f"Missing required heading: {heading}"))
        else:
            current_index = match.start()
            if last_heading and current_index < last_index:
                errors.append(ValidationError(
                    "format", "error",
                    f"Heading '{heading}' is out of order (must appear after '{last_heading}')"
                ))
            last_index = max(last_index, current_index)
            last_heading = heading

    return errors


def check_duplication(text: str) -> list[ValidationError]:
    """Check for duplicated content (multiple H1, frontmatter keys in body)."""
    errors: list[ValidationError] = []

    h1_headers = re.findall(r'^#\s+.+$', text, re.MULTILINE)
    if len(h1_headers) > 1:
        errors.append(ValidationError(
            "format", "error",
            f"Multiple H1 headers found ({len(h1_headers)}). Document might be duplicated."
        ))

    fm_match = re.match(r'^---\n([\s\S]*?)\n---\n', text)
    if fm_match:
        body = text[fm_match.end():]
        duplicated_keys = []
        for key in ['id', 'title', 'description', 'category_type']:
            if re.search(rf'^{key}:', body, re.MULTILINE):
                duplicated_keys.append(key)
        if duplicated_keys:
            errors.append(ValidationError(
                "format", "error",
                f"Frontmatter keys found in body (possible duplication): {', '.join(duplicated_keys)}"
            ))

    return errors



def check_unclosed_code_fences(text: str) -> list[ValidationError]:
    """Detect ## headings that fall inside an unclosed code fence block.

    An unclosed fence is valid MDX syntax — the compiler accepts it without error,
    but Docusaurus renders everything after the opening ``` as raw code, making all
    following headings and sections invisible on the page.
    """
    errors: list[ValidationError] = []
    in_fence = False
    fence_start_line: int | None = None

    for lineno, line in enumerate(text.splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("```"):
            if not in_fence:
                in_fence = True
                fence_start_line = lineno
            else:
                in_fence = False
                fence_start_line = None
        elif in_fence and re.match(r"^#{2,3}\s+", line):
            errors.append(ValidationError(
                "format", "error",
                f"Heading '{stripped}' at line {lineno} is inside an unclosed code fence "
                f"(opened at line {fence_start_line}). Add closing ``` before this heading.",
                line=lineno,
            ))

    if in_fence and fence_start_line is not None:
        errors.append(ValidationError(
            "format", "error",
            f"Unclosed code fence opened at line {fence_start_line} — never closed before end of file.",
            line=fence_start_line,
        ))

    return errors


def check_filler_text(text: str) -> list[ValidationError]:
    """Check for filler text like '(End of documentation)'."""
    if re.search(r'\(End of (documentation|example)\)', text, re.IGNORECASE):
        return [ValidationError(
            "format", "error",
            "Chứa text rác: (End of documentation) hoặc (End of example)"
        )]
    return []


def validate_all(filepath: str, accepted_headings: set[str] | None = None) -> list[ValidationError]:
    """Run all format checks on a file. Returns list of ValidationError.

    accepted_headings: standard heading names whose absence is jury-accepted (e.g. {"## Main functions"}).
    Only those specific heading checks are skipped; all others are validated normally.
    """
    accepted_headings = accepted_headings or set()
    raw = Path(filepath).read_text(encoding="utf-8")
    errors: list[ValidationError] = []

    # Frontmatter parse check
    try:
        frontmatter.loads(raw)
    except Exception as e:
        errors.append(ValidationError("frontmatter", "error", str(e)))

    # YAML structure checks
    errors.extend(check_frontmatter(raw))
    errors.extend(check_id_matches_filename(raw, filepath))

    # Required headings (jury-accepted headings are skipped individually)
    errors.extend(check_required_headings(raw, accepted_headings))

    # Duplication
    errors.extend(check_duplication(raw))

    # Filler text
    errors.extend(check_filler_text(raw))

    # Unclosed code fences (headings inside open fences render as invisible code)
    errors.extend(check_unclosed_code_fences(raw))

    # MDX validation
    from validator.format.mdx import validate_mdx
    errors.extend(validate_mdx(filepath))

    return errors
