"""Format validation checks. Each function detects errors without modifying files."""

import re
from dataclasses import dataclass
from pathlib import Path

import emoji
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


def check_required_headings(text: str) -> list[ValidationError]:
    """Validate required section headings exist in correct order."""
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


def check_emoji(text: str) -> list[ValidationError]:
    """Check for emoji characters in document."""
    found_emojis = emoji.emoji_list(text)
    if found_emojis:
        details = ", ".join([f"'{e['emoji']}' at {e['match_start']}" for e in found_emojis])
        return [ValidationError(
            "format", "warning",
            f"Chứa emoji hoặc unicode symbol: {details}"
        )]
    return []


def check_filler_text(text: str) -> list[ValidationError]:
    """Check for filler text like '(End of documentation)'."""
    if re.search(r'\(End of (documentation|example)\)', text, re.IGNORECASE):
        return [ValidationError(
            "format", "error",
            "Chứa text rác: (End of documentation) hoặc (End of example)"
        )]
    return []


def validate_all(filepath: str) -> list[ValidationError]:
    """Run all format checks on a file. Returns list of ValidationError."""
    raw = Path(filepath).read_text(encoding="utf-8")
    errors: list[ValidationError] = []

    # Emoji check
    errors.extend(check_emoji(raw))

    # Frontmatter parse check
    try:
        frontmatter.loads(raw)
    except Exception as e:
        errors.append(ValidationError("frontmatter", "error", str(e)))

    # YAML structure checks
    errors.extend(check_frontmatter(raw))

    # Required headings
    errors.extend(check_required_headings(raw))

    # Duplication
    errors.extend(check_duplication(raw))

    # Filler text
    errors.extend(check_filler_text(raw))

    # MDX validation
    from validator.format.mdx import validate_mdx
    errors.extend(validate_mdx(filepath))

    return errors
