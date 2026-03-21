# Validator Restructure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure `validator/` into content validation (LLM-based review loop) and format validation (no-LLM), with a unified pipeline.

**Architecture:** Three sub-packages (`content/`, `format/`, `update/`) under `validator/src/validator/`, orchestrated by `pipeline.py`. Content loop uses LLM2 reviewer → feedback → LLM1 patch-based writer cycle. Format uses existing autofix strategies with structured `ValidationError` types.

**Tech Stack:** Python 3.11, uv workspace, Ollama Cloud API (via `llm` package), `rag` package for connected content, `tiktoken` for token counting, Node.js for MDX validation.

**Spec:** `docs/superpowers/specs/2026-03-21-validator-restructure-design.md`

---

## File Structure

**New files to create:**
- `validator/src/validator/utils.py` — Shared utilities: `resolve_lua_path()`, `resolve_connected_content()`
- `validator/src/validator/format/__init__.py`
- `validator/src/validator/format/checks.py` — `ValidationError` dataclass + all check functions
- `validator/src/validator/format/mdx.py` — MDX validation wrapper
- `validator/src/validator/format/autofix.py` — `FixResult` + auto-fix strategies
- `validator/src/validator/content/__init__.py`
- `validator/src/validator/content/prompts.py` — Prompt templates for writer & reviewer
- `validator/src/validator/content/reviewer.py` — `ReviewResult` + `review_document()`
- `validator/src/validator/content/writer.py` — `Patch` + `rewrite_document()`
- `validator/src/validator/content/loop.py` — `ContentLoopConfig/Result` + `run_content_loop()`
- `validator/src/validator/content/chunked.py` — Placeholder for future chunked strategy
- `validator/src/validator/update/__init__.py`
- `validator/src/validator/pipeline.py` — `PipelineConfig`, `FileResult`, `process_file()`, `process_batch()`

**Files to move:**
- `validate_mdx.mjs` → `format/validate_mdx.mjs`
- `validate_update.py` → `update/validate_update.py` (with import changes)

**Files to modify:**
- `validator/pyproject.toml` — Add `mod-document-llm` and `mod-document-rag` workspace dependencies
- `validator/src/validator/__main__.py` — Full rewrite with CLI args
- `validator/src/validator/constants.py` — Add content loop constants

**Files to delete (after migration verified):**
- `validator/src/validator/validator.py`
- `validator/src/validator/autofix_mdx.py`
- `validator/src/validator/fix_format.py`

**Test files:**
- Rename: `tests/test.py` → `tests/test_smoke.py`
- Rename: `tests/test_logic.py` → `tests/test_format_checks.py`
- Rename: `tests/test_fix_ref.py` → `tests/test_format_autofix.py`
- New: `tests/test_utils.py`
- New: `tests/test_content_reviewer.py`
- New: `tests/test_content_writer.py`
- New: `tests/test_content_loop.py`
- New: `tests/test_pipeline.py`

---

## Chunk 1: Format Package

### Task 1: Create `format/checks.py` — ValidationError + check functions

**Files:**
- Create: `validator/src/validator/format/__init__.py`
- Create: `validator/src/validator/format/checks.py`
- Create: `validator/tests/test_format_checks.py`

- [x] **Step 1: Create format package init**

Create empty `validator/src/validator/format/__init__.py`.

- [x] **Step 2: Write failing tests for ValidationError and check functions**

Create `validator/tests/test_format_checks.py`:

```python
import pytest
from validator.format.checks import (
    ValidationError,
    check_frontmatter,
    check_required_headings,
    check_duplication,
    check_emoji,
    check_filler_text,
)


def test_validation_error_dataclass():
    err = ValidationError(category="mdx", severity="error", message="test")
    assert err.category == "mdx"
    assert err.severity == "error"
    assert err.message == "test"
    assert err.line is None

    err_with_line = ValidationError(category="yaml", severity="warning", message="x", line=5)
    assert err_with_line.line == 5


# --- check_frontmatter ---

VALID_FRONTMATTER = """\
---
id: test
title: Test
description: A valid description
tags: [test]
sidebar_position: 1
last_updated: 2026-03-21
build_version: 714014
change_status: new
category_type: component
source_hash: abc12345
system_scope: client
---

# Test
"""


def test_check_frontmatter_valid():
    errors = check_frontmatter(VALID_FRONTMATTER)
    assert errors == []


def test_check_frontmatter_missing_field():
    text = VALID_FRONTMATTER.replace("system_scope: client\n", "")
    errors = check_frontmatter(text)
    assert len(errors) == 1
    assert errors[0].category == "yaml"
    assert "system_scope" in errors[0].message


def test_check_frontmatter_empty_tags():
    text = VALID_FRONTMATTER.replace("tags: [test]", "tags: []")
    errors = check_frontmatter(text)
    assert any("tags is empty" in e.message for e in errors)


def test_check_frontmatter_missing_delimiters():
    text = "id: test\ntitle: Test\n"
    errors = check_frontmatter(text)
    assert any("frontmatter delimiters" in e.message for e in errors)


# --- check_required_headings ---

VALID_BODY = """\
---
id: test
title: Test
---

## Overview

content

## Usage example

content

## Dependencies & tags

content

## Properties

content

## Main functions

content

## Events & listeners

content
"""


def test_check_required_headings_valid():
    errors = check_required_headings(VALID_BODY)
    assert errors == []


def test_check_required_headings_missing():
    text = VALID_BODY.replace("## Properties\n", "")
    errors = check_required_headings(text)
    assert len(errors) == 1
    assert errors[0].category == "format"
    assert "Properties" in errors[0].message


def test_check_required_headings_out_of_order():
    text = VALID_BODY.replace("## Overview", "## PLACEHOLDER").replace(
        "## Events & listeners", "## Overview"
    ).replace("## PLACEHOLDER", "## Events & listeners")
    errors = check_required_headings(text)
    assert any("out of order" in e.message for e in errors)


# --- check_duplication ---

def test_check_duplication_multiple_h1():
    text = "---\nid: x\n---\n# Title\nContent\n# Title\n"
    errors = check_duplication(text)
    assert len(errors) >= 1
    assert any("H1" in e.message for e in errors)


def test_check_duplication_clean():
    text = "---\nid: x\n---\n# Title\nContent\n"
    errors = check_duplication(text)
    assert errors == []


def test_check_duplication_frontmatter_in_body():
    text = "---\nid: x\n---\n# Title\nid: duplicate\n"
    errors = check_duplication(text)
    assert any("body" in e.message.lower() for e in errors)


# --- check_emoji ---

def test_check_emoji_found():
    text = "Hello 🌍 world"
    errors = check_emoji(text)
    assert len(errors) == 1
    assert errors[0].severity == "warning"
    assert errors[0].category == "format"


def test_check_emoji_clean():
    text = "Hello world, no emojis here."
    errors = check_emoji(text)
    assert errors == []


# --- check_filler_text ---

def test_check_filler_text_found():
    text = "Content\n(End of documentation)\n"
    errors = check_filler_text(text)
    assert len(errors) == 1
    assert errors[0].category == "format"


def test_check_filler_text_example():
    text = "Content\n(End of example)\n"
    errors = check_filler_text(text)
    assert len(errors) == 1


def test_check_filler_text_clean():
    text = "Content\nMore content\n"
    errors = check_filler_text(text)
    assert errors == []
```

- [x] **Step 3: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_format_checks.py -v`
Expected: FAIL with ImportError (format.checks doesn't exist yet)

- [x] **Step 4: Implement `format/checks.py`**

Create `validator/src/validator/format/checks.py`. This migrates logic from `validator/src/validator/validator.py` with these changes:
- Returns `list[ValidationError]` instead of `list[str]`
- Each check is an independent function
- `check_emoji` and `check_filler_text` extracted from inline logic in `validate_full()`
- `validate_all()` aggregates all checks

```python
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

    if not re.search(r'system_scope:\s*[a-z][a-z0-9\-]*\s*$', fm, re.MULTILINE):
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
```

- [x] **Step 5: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_format_checks.py -v`
Expected: All tests PASS (note: `validate_all` tests come later since `mdx.py` doesn't exist yet)

- [x] **Step 6: Commit**

```bash
git add validator/src/validator/format/__init__.py validator/src/validator/format/checks.py validator/tests/test_format_checks.py
git commit -m "feat(validator): add format/checks.py with ValidationError dataclass"
```

---

### Task 2: Create `format/mdx.py` — MDX validation wrapper

**Files:**
- Create: `validator/src/validator/format/mdx.py`

- [x] **Step 1: Write failing test for validate_mdx**

Append to `validator/tests/test_format_checks.py`:

```python
# --- validate_mdx (via mdx.py) ---

def test_validate_mdx_returns_validation_errors(tmp_path):
    """validate_mdx should return list[ValidationError], not raw strings."""
    md_file = tmp_path / "test.md"
    md_file.write_text("---\nid: test\n---\n# Title\nValid content\n")
    from validator.format.mdx import validate_mdx
    errors = validate_mdx(str(md_file))
    assert isinstance(errors, list)
    for e in errors:
        assert isinstance(e, ValidationError)
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest validator/tests/test_format_checks.py::test_validate_mdx_returns_validation_errors -v`
Expected: FAIL (mdx module doesn't exist)

- [x] **Step 3: Implement `format/mdx.py`**

Create `validator/src/validator/format/mdx.py`:

```python
"""MDX validation via Node.js subprocess."""

import json
import shutil
import subprocess
from pathlib import Path

from validator.constants import MDX_NODE_TIMEOUT
from validator.format.checks import ValidationError


def validate_mdx(filepath: str) -> list[ValidationError]:
    """Validate MDX by calling validate_mdx.mjs via Node.js subprocess."""
    if not shutil.which("node"):
        return [ValidationError("mdx", "error", "Node.js không tìm thấy — hãy cài Node.js")]

    script = Path(__file__).parent / "validate_mdx.mjs"
    if not script.exists():
        return [ValidationError("mdx", "error", f"Không tìm thấy {script}")]

    try:
        result = subprocess.run(
            ["node", "--experimental-vm-modules", str(script), filepath],
            capture_output=True,
            text=True,
            timeout=MDX_NODE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        return [ValidationError("mdx", "error", f"MDX validation timeout ({MDX_NODE_TIMEOUT}s)")]

    if result.returncode != 0 and not result.stdout:
        return [ValidationError("mdx", "error", f"Node error: {result.stderr.strip()}")]

    try:
        data = json.loads(result.stdout)
        return [
            ValidationError("mdx", "error", e)
            for e in data.get("errors", [])
        ]
    except json.JSONDecodeError:
        return [ValidationError("mdx", "error", f"Unexpected output: {result.stdout[:200]}")]
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest validator/tests/test_format_checks.py::test_validate_mdx_returns_validation_errors -v`
Expected: PASS

- [x] **Step 5: Commit**

```bash
git add validator/src/validator/format/mdx.py validator/tests/test_format_checks.py
git commit -m "feat(validator): add format/mdx.py — MDX validation wrapper"
```

---

### Task 3: Move `validate_mdx.mjs` to `format/`

**Files:**
- Move: `validator/src/validator/validate_mdx.mjs` → `validator/src/validator/format/validate_mdx.mjs`

- [x] **Step 1: Move the file**

```bash
git mv validator/src/validator/validate_mdx.mjs validator/src/validator/format/validate_mdx.mjs
```

- [x] **Step 2: Run tests to verify mdx.py finds the script**

Run: `uv run pytest validator/tests/test_format_checks.py -v`
Expected: PASS (mdx.py uses `Path(__file__).parent / "validate_mdx.mjs"` which now resolves to `format/`)

- [x] **Step 3: Commit**

```bash
git commit -m "refactor(validator): move validate_mdx.mjs to format/"
```

---

### Task 4: Create `format/autofix.py` — FixResult + auto-fix strategies

**Files:**
- Create: `validator/src/validator/format/autofix.py`
- Create: `validator/tests/test_format_autofix.py`

- [x] **Step 1: Write failing tests**

Create `validator/tests/test_format_autofix.py`:

```python
import pytest
from validator.format.autofix import (
    FixResult,
    remove_pure_emojis,
    remove_extra_dividers,
    fix_frontmatter_delimiters,
    fix_split_frontmatter,
    fix_yaml_mapping_colon_in_description,
    fix_reference_errors,
    fix_bare_curly_braces,
    fix_table_pipes,
    remove_filler_text,
)
from validator.format.checks import ValidationError


def test_fix_result_dataclass():
    result = FixResult(changes=["fix1"], remaining_errors=[])
    assert result.changes == ["fix1"]
    assert result.remaining_errors == []


def test_fix_result_with_errors():
    err = ValidationError("mdx", "error", "test")
    result = FixResult(changes=[], remaining_errors=[err])
    assert len(result.remaining_errors) == 1


def test_emoji_removal():
    text = "Hello 🌍! This is a test ↔ with symbols."
    fixed, count = remove_pure_emojis(text)
    assert "🌍" not in fixed
    assert "↔" in fixed
    assert count == 1


def test_emoji_removal_no_emoji():
    text = "Hello world, no emojis."
    fixed, count = remove_pure_emojis(text)
    assert fixed == text
    assert count == 0


def test_divider_removal_trailing():
    text = "---\nid: test\n---\nContent\n\n---\n"
    fixed, count = remove_extra_dividers(text)
    assert count == 1
    assert fixed == "---\nid: test\n---\nContent\n"


def test_divider_removal_middle_kept():
    text = "---\nid: test\n---\nBefore\n\n---\n\nAfter\n"
    fixed, count = remove_extra_dividers(text)
    assert count == 0
    assert "\n\n---\n\n" in fixed


def test_divider_removal_multiple():
    text = "---\nid: test\n---\nContent\n---\n---\n"
    fixed, count = remove_extra_dividers(text)
    assert count == 2


def test_frontmatter_delimiters_missing_opening():
    text = "id: test\ntitle: Test\n---\n# Content\n"
    fixed, changed = fix_frontmatter_delimiters(text)
    assert changed is True
    assert fixed.startswith("---\n")


def test_frontmatter_delimiters_already_correct():
    text = "---\nid: test\n---\n# Content\n"
    fixed, changed = fix_frontmatter_delimiters(text)
    assert changed is False


def test_split_frontmatter_orphaned_keys():
    text = "---\nid: test\n---\nlast_updated: 2026-03-21\n\n# Content\n"
    fixed, changed = fix_split_frontmatter(text)
    assert changed is True
    assert "last_updated" not in fixed.split("---\n", 2)[-1].split("---")[0] or "last_updated" in fixed.split("---")[1]


def test_yaml_mapping_colon():
    text = "---\ndescription: test: colon\n---\n"
    fixed, changed = fix_yaml_mapping_colon_in_description(text)
    assert changed is True
    assert 'description: "test: colon"' in fixed


def test_yaml_mapping_colon_already_quoted():
    text = '---\ndescription: "test: colon"\n---\n'
    fixed, changed = fix_yaml_mapping_colon_in_description(text)
    assert changed is False


def test_filler_text_removal():
    text = "Content\n(End of documentation)\n"
    fixed, changed = remove_filler_text(text)
    assert changed is True
    assert "(End of documentation)" not in fixed


def test_fix_bare_curly_braces():
    text = "The type is {number, number} in the API.\n"
    fixed, count = fix_bare_curly_braces(text)
    assert count == 1
    assert "`{number, number}`" in fixed


def test_fix_bare_curly_braces_in_code_block():
    text = "```\n{number, number}\n```\n"
    fixed, count = fix_bare_curly_braces(text)
    assert count == 0


def test_fix_reference_errors():
    text = "| `bar` | {number, number} | `{0.7}` |\n"
    fixed, count = fix_reference_errors(text, "number")
    assert count >= 1
    assert "`{number, number}`" in fixed


def test_fix_reference_errors_preserves_backticked():
    text = "* **Parameters:** `data` (`{ resistance = number }`) -- Saved.\n"
    fixed, count = fix_reference_errors(text, "number")
    assert count == 0


def test_fix_table_pipes():
    text = "| col | `a|b` | col |\n"
    fixed, count = fix_table_pipes(text)
    assert count >= 1
    assert "\\|" in fixed


# --- Additional functions: import + basic behavior tests ---

def test_fix_empty_tags_and_placeholders():
    from validator.format.autofix import fix_empty_tags_and_placeholders
    text = "---\ntags: []\n---\n"
    fixed, applied = fix_empty_tags_and_placeholders(text)
    assert len(applied) > 0
    assert "tags: [stub]" in fixed


def test_fix_tags_format():
    from validator.format.autofix import fix_tags_format
    text = "---\ntags: tag1, tag2\n---\n"
    fixed, changed = fix_tags_format(text)
    assert changed is True
    assert "tags: [tag1, tag2]" in fixed


def test_fix_malformed_multiline_backticks():
    from validator.format.autofix import fix_malformed_multiline_backticks
    text = "  `{\n    `{abc=1}`,\n  }`\n"
    fixed, count = fix_malformed_multiline_backticks(text)
    assert count == 1
    assert "```lua" in fixed


def test_prune_duplicated_content():
    from validator.format.autofix import prune_duplicated_content
    text = "---\nid: x\n---\n# Title\nContent\n# Title\nContent\n"
    fixed, pruned = prune_duplicated_content(text)
    assert pruned is True


def test_fix_all_bare_operators():
    from validator.format.autofix import fix_all_bare_operators
    text = "The value x <= 5 is checked.\n"
    fixed = fix_all_bare_operators(text)
    assert "`" in fixed


def test_get_mdx_errors_exists():
    from validator.format.autofix import get_mdx_errors
    assert callable(get_mdx_errors)


def test_is_inside_backticks():
    from validator.format.autofix import is_inside_backticks
    assert is_inside_backticks("`hello`", 3) is True
    assert is_inside_backticks("hello", 3) is False


def test_fix_bare_operator_on_line():
    from validator.format.autofix import fix_bare_operator_on_line
    line = "value <= 5 in the range"
    fixed = fix_bare_operator_on_line(line, 6, "<=")
    assert "`" in fixed
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_format_autofix.py -v`
Expected: FAIL (format.autofix doesn't exist)

- [x] **Step 3: Implement `format/autofix.py`**

Create `validator/src/validator/format/autofix.py` by copying the ENTIRE content of `validator/src/validator/autofix_mdx.py` (all ~810 lines, 16 functions), then applying these specific changes:

**Migration instructions (exact edits to apply after copying):**

1. **Add `FixResult` dataclass** — insert after the existing imports at the top:
```python
from dataclasses import dataclass
from validator.format.checks import ValidationError

@dataclass
class FixResult:
    """Result of an autofix run."""
    changes: list[str]
    remaining_errors: list[ValidationError]
```

2. **`get_mdx_errors()` script path** — no change needed. It uses `Path(__file__).parent / "validate_mdx.mjs"` which resolves correctly since both `autofix.py` and `validate_mdx.mjs` are now in `format/`.

3. **`autofix_file()` return type** — change the function signature and ending:
```python
# Change signature from:
def autofix_file(filepath: str, dry_run: bool = False) -> list[str]:
# To:
def autofix_file(filepath: str, dry_run: bool = False) -> FixResult:
```
Then replace the final `return applied` (last line of the function) with:
```python
    # Get remaining errors via unified validate_all()
    from validator.format.checks import validate_all
    remaining = validate_all(filepath) if not dry_run else []
    return FixResult(changes=applied, remaining_errors=remaining)
```

4. **Phase 2 MDX loop** — `get_mdx_errors()` stays as-is internally for the iterative fix loop. It needs structured error dicts with `line`, `col`, `identifier`, `unclosed_tag` that `validate_all()` doesn't provide. The `checks.validate_all()` call is only for the final `remaining_errors` in `FixResult`.

5. **Preserve ALL imports** from `autofix_mdx.py` including `unicodedata` and `emoji` (lines 48-49), which are needed by `remove_pure_emojis`.

6. **All 16 helper functions** are copied verbatim — do not modify their logic:
   - `get_mdx_errors`, `remove_pure_emojis`, `fix_frontmatter_delimiters`, `fix_split_frontmatter`
   - `fix_yaml_mapping_colon_in_description`, `remove_filler_text`, `remove_extra_dividers`
   - `fix_empty_tags_and_placeholders`, `fix_tags_format`, `is_inside_backticks`
   - `fix_bare_operator_on_line`, `fix_bare_curly_braces`, `fix_reference_errors`
   - `fix_table_pipes`, `fix_malformed_multiline_backticks`, `prune_duplicated_content`
   - `fix_all_bare_operators`

7. **Update `if __name__ == "__main__"` block** at the bottom to handle `FixResult`:
```python
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
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_format_autofix.py -v`
Expected: All tests PASS

- [x] **Step 5: Run all format tests together**

Run: `uv run pytest validator/tests/test_format_checks.py validator/tests/test_format_autofix.py -v`
Expected: All PASS

- [x] **Step 6: Commit**

```bash
git add validator/src/validator/format/autofix.py validator/tests/test_format_autofix.py
git commit -m "feat(validator): add format/autofix.py with FixResult return type"
```

---

## Chunk 2: Shared Utilities + Dependencies

### Task 5: Update `pyproject.toml` — Add workspace dependencies

**Files:**
- Modify: `validator/pyproject.toml`

- [x] **Step 1: Add workspace dependencies**

Update `validator/pyproject.toml` to add `mod-document-llm` and `mod-document-rag` to the dependencies list. The root `pyproject.toml` already has `[tool.uv.sources]` mapping these as workspace packages, so no `[tool.uv.sources]` section is needed in the member package.

```toml
[project]
name = "mod-document-validator"
version = "0.1.0"
requires-python = ">=3.11"
dependencies = ["python-frontmatter", "emoji", "mod-document-llm", "mod-document-rag"]

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [x] **Step 2: Sync dependencies**

Run: `uv sync`
Expected: Success, no errors

- [x] **Step 3: Commit**

```bash
git add validator/pyproject.toml uv.lock
git commit -m "chore(validator): add llm and rag workspace dependencies"
```

---

### Task 6: Create `utils.py` — Shared utilities

**Files:**
- Create: `validator/src/validator/utils.py`
- Create: `validator/tests/test_utils.py`

- [x] **Step 1: Write failing tests**

Create `validator/tests/test_utils.py`:

```python
import pytest
from pathlib import Path
from validator.utils import resolve_lua_path, DOCS_DIR, LUA_DIR


def test_docs_dir_exists():
    """DOCS_DIR should point to dst-api-webdocs/docs."""
    assert DOCS_DIR.exists(), f"DOCS_DIR not found: {DOCS_DIR}"
    assert DOCS_DIR.name == "docs"


def test_lua_dir_exists():
    """LUA_DIR should point to dst-scripts."""
    assert LUA_DIR.exists(), f"LUA_DIR not found: {LUA_DIR}"
    assert LUA_DIR.name == "dst-scripts"


def test_resolve_lua_path_valid():
    """Known .md file should resolve to .lua file if it exists."""
    md_files = list(DOCS_DIR.glob("*.md"))
    if not md_files:
        pytest.skip("No .md files in DOCS_DIR")
    for md_file in md_files[:10]:
        result = resolve_lua_path(str(md_file))
        if result is not None:
            assert result.endswith(".lua")
            assert Path(result).exists()
            return
    pytest.skip("No .md files with matching .lua found")


def test_resolve_lua_path_nonexistent():
    """Non-existent file should return None."""
    result = resolve_lua_path("/fake/path/docs/nonexistent_xyz_999.md")
    assert result is None


def test_resolve_lua_path_no_docs_in_path():
    """Path without 'docs' segment should return None."""
    result = resolve_lua_path("/some/random/path/file.md")
    assert result is None
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_utils.py -v`
Expected: FAIL (utils module doesn't exist)

- [x] **Step 3: Implement `utils.py`**

Create `validator/src/validator/utils.py`:

```python
"""Shared utilities for validator package.

Provides path resolution between .md docs and .lua source files,
and connected content extraction for the content validation loop.
"""

import os
from pathlib import Path

from llm.paths import BASE_LUA_DIR, BASE_DOCS_DIR
from rag.docs import extract_lua_references, format_connected_section, safe_read_lua
from rag.content import extract_connected_content

DOCS_DIR = Path(BASE_DOCS_DIR)
LUA_DIR = Path(BASE_LUA_DIR)


def resolve_lua_path(md_filepath: str) -> str | None:
    """
    Map .md doc path to corresponding .lua source path.
    e.g. dst-api-webdocs/docs/map/rooms/four.md -> dst-scripts/map/rooms/four.lua
    Returns None if Lua file doesn't exist or path can't be resolved.
    """
    path = Path(md_filepath)
    try:
        docs_parts = path.parts
        docs_idx = docs_parts.index("docs")
        rel_parts = docs_parts[docs_idx + 1:]
        lua_rel_path = "/".join(rel_parts).replace(".md", ".lua")
        lua_filepath = os.path.join(str(LUA_DIR), lua_rel_path)
        if os.path.exists(lua_filepath):
            return lua_filepath
        return None
    except ValueError:
        return None


def resolve_connected_content(lua_filepath: str) -> tuple[str, str]:
    """
    Extract connected section + connected content from Lua source.
    Calls rag.docs.extract_lua_references() + rag.docs.format_connected_section()
    + rag.content.extract_connected_content()
    Returns (connected_section, connected_content).
    """
    lua_code = safe_read_lua(lua_filepath)
    if lua_code is None:
        return "", ""
    comp_name = Path(lua_filepath).stem
    lua_refs = extract_lua_references(lua_code, comp_name + ".lua")
    connected_section = format_connected_section(lua_refs)
    connected_content = extract_connected_content(lua_refs, max_lines_per_file=100)
    return connected_section, connected_content
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_utils.py -v`
Expected: All tests PASS ✅ (5/5 passed, full suite 52/52 passed)

- [x] **Step 5: Commit**

```bash
git add validator/src/validator/utils.py validator/tests/test_utils.py
git commit -m "feat(validator): add utils.py with resolve_lua_path and resolve_connected_content"
```

---

## Chunk 3: Content Validation Loop

### Task 7: Create `content/prompts.py` — Prompt templates

**Files:**
- Create: `validator/src/validator/content/__init__.py`
- Create: `validator/src/validator/content/prompts.py`

- [x] **Step 1: Create content package init**

Create empty `validator/src/validator/content/__init__.py`.

- [x] **Step 2: Implement prompts.py**

Create `validator/src/validator/content/prompts.py`:

```python
"""Prompt templates for content validation writer and reviewer."""


def build_reviewer_prompt(
    md_content: str,
    lua_source: str,
    connected_content: str,
) -> str:
    """Build prompt for LLM2 (reviewer) to review documentation accuracy."""
    connected_block = connected_content if connected_content else "(none)"
    return f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API documentation.

Review the following markdown documentation against its Lua source code. Check for:
1. Function signatures and parameters match the Lua source — detect hallucination
2. Code examples match actual API usage
3. Descriptions are accurate and complete
4. Connected references are mentioned correctly

## Lua Source Code
```lua
{lua_source}
```

## Connected Content (referenced files)
{connected_block}

## Documentation to Review
{md_content}

## Response Format
Respond in JSON only:
```json
{{
    "approved": true/false,
    "issues": ["list of specific problems found"],
    "suggestions": ["list of specific fix suggestions"]
}}
```

If the documentation is accurate and complete, set approved=true with empty lists.
If there are problems, set approved=false and list each issue with a specific suggestion to fix it."""


def build_writer_prompt(
    md_content: str,
    lua_source: str,
    connected_content: str,
    issues: list[str],
    suggestions: list[str],
) -> str:
    """Build prompt for LLM1 (writer) to fix documentation based on review feedback."""
    feedback = ""
    for i, issue in enumerate(issues, 1):
        suggestion = suggestions[i - 1] if i - 1 < len(suggestions) else ""
        feedback += f"{i}. Issue: {issue}\n"
        if suggestion:
            feedback += f"   Suggestion: {suggestion}\n"

    connected_block = connected_content if connected_content else "(none)"
    return f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.

Fix the following documentation based on reviewer feedback. Return ONLY targeted patches, not the entire document.

## Lua Source Code (ground truth)
```lua
{lua_source}
```

## Connected Content
{connected_block}

## Current Documentation
{md_content}

## Reviewer Feedback
{feedback}

## Response Format
Return a JSON array of patches. Each patch replaces a specific text segment:
```json
[
    {{
        "old_text": "exact text to find in the document",
        "new_text": "replacement text",
        "reason": "why this change is needed"
    }}
]
```

Rules:
- old_text must be an EXACT substring of the current document
- Keep patches minimal — only change what's needed to fix the issues
- Do NOT modify YAML frontmatter
- Preserve markdown formatting and structure"""
```

- [x] **Step 3: Commit**

```bash
git add validator/src/validator/content/__init__.py validator/src/validator/content/prompts.py
git commit -m "feat(validator): add content/prompts.py — writer and reviewer prompt templates"
```

---

### Task 8: Create `content/reviewer.py` — ReviewResult + review_document()

**Files:**
- Create: `validator/src/validator/content/reviewer.py`
- Create: `validator/tests/test_content_reviewer.py`

- [x] **Step 1: Write failing tests**

Create `validator/tests/test_content_reviewer.py`:

```python
import pytest
import json
from validator.content.reviewer import ReviewResult, parse_review_response


def test_review_result_approved():
    result = ReviewResult(approved=True, issues=[], suggestions=[])
    assert result.approved is True
    assert result.issues == []


def test_review_result_rejected():
    result = ReviewResult(
        approved=False,
        issues=["Wrong param name"],
        suggestions=["Change 'foo' to 'bar'"],
    )
    assert result.approved is False
    assert len(result.issues) == 1


def test_parse_review_response_valid_json():
    raw = json.dumps({
        "approved": False,
        "issues": ["issue1"],
        "suggestions": ["fix1"],
    })
    result = parse_review_response(raw)
    assert result.approved is False
    assert result.issues == ["issue1"]
    assert result.suggestions == ["fix1"]


def test_parse_review_response_approved():
    raw = json.dumps({"approved": True, "issues": [], "suggestions": []})
    result = parse_review_response(raw)
    assert result.approved is True


def test_parse_review_response_with_markdown_fence():
    raw = '```json\n{"approved": true, "issues": [], "suggestions": []}\n```'
    result = parse_review_response(raw)
    assert result.approved is True


def test_parse_review_response_with_think_block():
    raw = '<think>reasoning here</think>\n{"approved": false, "issues": ["x"], "suggestions": ["y"]}'
    result = parse_review_response(raw)
    assert result.approved is False
    assert result.issues == ["x"]


def test_parse_review_response_invalid_json():
    raw = "This is not JSON at all"
    result = parse_review_response(raw)
    assert result.approved is False
    assert len(result.issues) >= 1  # Should contain parse error info
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_content_reviewer.py -v`
Expected: FAIL

- [x] **Step 3: Implement `content/reviewer.py`**

Create `validator/src/validator/content/reviewer.py`:

```python
"""LLM2 reviewer: reviews documentation against Lua source code."""

import json
import re
from dataclasses import dataclass

from llm.client import ollama_chat
from validator.content.prompts import build_reviewer_prompt


@dataclass
class ReviewResult:
    """Structured result from LLM2 review."""
    approved: bool
    issues: list[str]
    suggestions: list[str]


def parse_review_response(raw: str) -> ReviewResult:
    """Parse LLM2 response into ReviewResult. Handles JSON in markdown fences."""
    # Strip markdown code fence if present
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    # Remove <think>...</think> blocks (Qwen model)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()

    try:
        data = json.loads(cleaned)
        return ReviewResult(
            approved=bool(data.get("approved", False)),
            issues=list(data.get("issues", [])),
            suggestions=list(data.get("suggestions", [])),
        )
    except (json.JSONDecodeError, TypeError):
        return ReviewResult(
            approved=False,
            issues=[f"Failed to parse reviewer response: {raw[:200]}"],
            suggestions=[],
        )


def review_document(
    md_content: str,
    lua_source: str,
    connected_content: str,
    model: str,
) -> ReviewResult:
    """Send document to LLM2 for review. Returns structured ReviewResult."""
    prompt = build_reviewer_prompt(md_content, lua_source, connected_content)
    response = ollama_chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response["message"]["content"]
    return parse_review_response(raw)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_content_reviewer.py -v`
Expected: All tests PASS

- [x] **Step 5: Commit**

```bash
git add validator/src/validator/content/reviewer.py validator/tests/test_content_reviewer.py
git commit -m "feat(validator): add content/reviewer.py — LLM2 document review"
```

---

### Task 9: Create `content/writer.py` — Patch + rewrite_document()

**Files:**
- Create: `validator/src/validator/content/writer.py`
- Create: `validator/tests/test_content_writer.py`

- [x] **Step 1: Write failing tests**

Create `validator/tests/test_content_writer.py`:

```python
import pytest
import json
from validator.content.writer import Patch, apply_patches, parse_writer_response


def test_patch_dataclass():
    p = Patch(old_text="foo", new_text="bar", reason="test")
    assert p.old_text == "foo"
    assert p.new_text == "bar"
    assert p.reason == "test"


def test_apply_patches_success():
    content = "Hello world. Goodbye world."
    patches = [
        Patch(old_text="Hello", new_text="Hi", reason="greeting"),
        Patch(old_text="Goodbye", new_text="Bye", reason="farewell"),
    ]
    result, failed = apply_patches(content, patches)
    assert result == "Hi world. Bye world."
    assert failed == 0


def test_apply_patches_partial_failure():
    content = "Hello world."
    patches = [
        Patch(old_text="Hello", new_text="Hi", reason="ok"),
        Patch(old_text="NONEXISTENT", new_text="X", reason="fail"),
    ]
    result, failed = apply_patches(content, patches)
    assert result == "Hi world."
    assert failed == 1


def test_apply_patches_empty():
    content = "Hello"
    result, failed = apply_patches(content, [])
    assert result == "Hello"
    assert failed == 0


def test_apply_patches_first_occurrence_only():
    content = "foo foo foo"
    patches = [Patch(old_text="foo", new_text="bar", reason="test")]
    result, failed = apply_patches(content, patches)
    assert result == "bar foo foo"
    assert failed == 0


def test_parse_writer_response_valid():
    raw = json.dumps([
        {"old_text": "foo", "new_text": "bar", "reason": "test"},
    ])
    patches = parse_writer_response(raw)
    assert len(patches) == 1
    assert patches[0].old_text == "foo"


def test_parse_writer_response_multiple():
    raw = json.dumps([
        {"old_text": "a", "new_text": "b", "reason": "1"},
        {"old_text": "c", "new_text": "d", "reason": "2"},
    ])
    patches = parse_writer_response(raw)
    assert len(patches) == 2


def test_parse_writer_response_with_fence():
    raw = '```json\n[{"old_text": "a", "new_text": "b", "reason": "c"}]\n```'
    patches = parse_writer_response(raw)
    assert len(patches) == 1


def test_parse_writer_response_with_think():
    raw = '<think>thinking</think>\n[{"old_text": "a", "new_text": "b", "reason": "c"}]'
    patches = parse_writer_response(raw)
    assert len(patches) == 1


def test_parse_writer_response_invalid():
    raw = "Not valid JSON"
    patches = parse_writer_response(raw)
    assert patches == []


def test_parse_writer_response_empty_old_text_skipped():
    raw = json.dumps([
        {"old_text": "", "new_text": "bar", "reason": "empty"},
        {"old_text": "valid", "new_text": "ok", "reason": "good"},
    ])
    patches = parse_writer_response(raw)
    assert len(patches) == 1
    assert patches[0].old_text == "valid"
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_content_writer.py -v`
Expected: FAIL

- [x] **Step 3: Implement `content/writer.py`**

Create `validator/src/validator/content/writer.py`:

```python
"""LLM1 writer: applies patch-based fixes based on reviewer feedback."""

import json
import re
from dataclasses import dataclass

from llm.client import ollama_chat
from validator.content.prompts import build_writer_prompt
from validator.content.reviewer import ReviewResult


@dataclass
class Patch:
    """A targeted text replacement."""
    old_text: str
    new_text: str
    reason: str


def apply_patches(content: str, patches: list[Patch]) -> tuple[str, int]:
    """Apply patches to content via str.replace(). Returns (new_content, failed_count)."""
    failed = 0
    for patch in patches:
        if patch.old_text in content:
            content = content.replace(patch.old_text, patch.new_text, 1)
        else:
            failed += 1
    return content, failed


def parse_writer_response(raw: str) -> list[Patch]:
    """Parse LLM1 response into list of Patch objects."""
    # Strip markdown code fence if present
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    # Remove <think>...</think> blocks (Qwen model)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()

    try:
        data = json.loads(cleaned)
        if not isinstance(data, list):
            return []
        return [
            Patch(
                old_text=str(item.get("old_text", "")),
                new_text=str(item.get("new_text", "")),
                reason=str(item.get("reason", "")),
            )
            for item in data
            if isinstance(item, dict) and item.get("old_text")
        ]
    except (json.JSONDecodeError, TypeError):
        return []


def rewrite_document(
    md_content: str,
    lua_source: str,
    connected_content: str,
    review_feedback: ReviewResult,
    model: str,
) -> list[Patch]:
    """Ask LLM1 to generate patches based on reviewer feedback."""
    prompt = build_writer_prompt(
        md_content, lua_source, connected_content,
        review_feedback.issues, review_feedback.suggestions,
    )
    response = ollama_chat(
        model=model,
        messages=[{"role": "user", "content": prompt}],
    )
    raw = response["message"]["content"]
    return parse_writer_response(raw)
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_content_writer.py -v`
Expected: All tests PASS

- [x] **Step 5: Commit**

```bash
git add validator/src/validator/content/writer.py validator/tests/test_content_writer.py
git commit -m "feat(validator): add content/writer.py — patch-based document rewriting"
```

---

### Task 10: Create `content/loop.py` — Content loop orchestrator

**Files:**
- Create: `validator/src/validator/content/loop.py`
- Create: `validator/tests/test_content_loop.py`

- [x] **Step 1: Write failing tests**

Create `validator/tests/test_content_loop.py`:

```python
import pytest
from validator.content.loop import ContentLoopConfig, ContentLoopResult


def test_content_loop_config_defaults():
    config = ContentLoopConfig()
    assert config.max_iterations == 3
    assert config.writer_model == "qwen3.5:cloud"
    assert config.reviewer_model == "qwen3.5:cloud"


def test_content_loop_config_custom():
    config = ContentLoopConfig(max_iterations=5, writer_model="a", reviewer_model="b")
    assert config.max_iterations == 5
    assert config.writer_model == "a"
    assert config.reviewer_model == "b"


def test_content_loop_result_approved():
    result = ContentLoopResult(approved=True, iterations=1, final_issues=[])
    assert result.approved is True
    assert result.iterations == 1
    assert result.final_issues == []


def test_content_loop_result_rejected():
    result = ContentLoopResult(approved=False, iterations=3, final_issues=["issue"])
    assert result.approved is False
    assert result.final_issues == ["issue"]
```

- [x] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_content_loop.py -v`
Expected: FAIL

- [x] **Step 3: Implement `content/loop.py`**

Create `validator/src/validator/content/loop.py`:

```python
"""Orchestrates the content validation loop: review -> fix -> review -> approve."""

from dataclasses import dataclass
from pathlib import Path

from rag.docs import safe_read_lua
from validator.content.reviewer import review_document
from validator.content.writer import rewrite_document, apply_patches
from validator.utils import resolve_connected_content


@dataclass
class ContentLoopConfig:
    """Configuration for the content validation loop."""
    max_iterations: int = 3
    writer_model: str = "qwen3.5:cloud"
    reviewer_model: str = "qwen3.5:cloud"


@dataclass
class ContentLoopResult:
    """Result of a content validation loop run."""
    approved: bool
    iterations: int
    final_issues: list[str]


def run_content_loop(
    md_filepath: str,
    lua_filepath: str,
    config: ContentLoopConfig,
) -> ContentLoopResult:
    """
    Run the content validation loop:
    1. LLM2 reviews doc against Lua source
    2. If approved -> done
    3. If not -> LLM1 patches doc based on feedback
    4. Repeat until approved or max_iterations reached
    """
    md_content = Path(md_filepath).read_text(encoding="utf-8")
    lua_source = safe_read_lua(lua_filepath)
    if lua_source is None:
        return ContentLoopResult(
            approved=False, iterations=0,
            final_issues=[f"Cannot read Lua source: {lua_filepath}"],
        )

    _, connected_content = resolve_connected_content(lua_filepath)

    for i in range(config.max_iterations):
        # LLM2 review
        review = review_document(
            md_content, lua_source, connected_content, config.reviewer_model,
        )

        if review.approved:
            return ContentLoopResult(approved=True, iterations=i + 1, final_issues=[])

        # LLM1 fix
        patches = rewrite_document(
            md_content, lua_source, connected_content, review, config.writer_model,
        )

        if not patches:
            # LLM1 returned no patches — can't fix
            return ContentLoopResult(
                approved=False, iterations=i + 1, final_issues=review.issues,
            )

        md_content, failed = apply_patches(md_content, patches)

        # Fallback warning if too many patches failed
        if patches and failed > len(patches) / 2:
            print(f"  [content] Warning: {failed}/{len(patches)} patches failed to apply")

        # Write updated content to disk
        Path(md_filepath).write_text(md_content, encoding="utf-8")

    # Max iterations reached — do final review to get current status
    final_review = review_document(
        md_content, lua_source, connected_content, config.reviewer_model,
    )
    return ContentLoopResult(
        approved=final_review.approved,
        iterations=config.max_iterations,
        final_issues=final_review.issues,
    )
```

- [x] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_content_loop.py -v`
Expected: All tests PASS

- [x] **Step 5: Commit**

```bash
git add validator/src/validator/content/loop.py validator/tests/test_content_loop.py
git commit -m "feat(validator): add content/loop.py — review-fix-approve orchestrator"
```

---

### Task 11: Create `content/chunked.py` — Placeholder

**Files:**
- Create: `validator/src/validator/content/chunked.py`

- [x] **Step 1: Create placeholder file**

Create `validator/src/validator/content/chunked.py`:

```python
"""Chunked file content validation strategy.

Files >= 32K tokens cannot fit in a single LLM context for review.
The content loop (loop.py) only handles standard-size files.
This module will define a separate strategy for large files —
likely section-by-section review or chunk-level review with
cross-chunk consistency checks.

NOT IMPLEMENTED — pipeline.py skips content validation for chunked files
and logs them as "skipped_chunked".
"""
```

- [x] **Step 2: Commit**

```bash
git add validator/src/validator/content/chunked.py
git commit -m "feat(validator): add content/chunked.py placeholder for future strategy"
```

---

## Chunk 4: Pipeline, Entry Point, and Cleanup

### Task 12: Create `pipeline.py` — Full pipeline orchestrator

**Files:**
- Create: `validator/src/validator/pipeline.py`
- Create: `validator/tests/test_pipeline.py`

- [x] **Step 1: Write failing tests**

Create `validator/tests/test_pipeline.py`:

```python
import pytest
from validator.pipeline import PipelineConfig, FileResult


def test_pipeline_config_defaults():
    config = PipelineConfig()
    assert config.content_max_iterations == 3
    assert config.writer_model == "qwen3.5:cloud"
    assert config.reviewer_model == "qwen3.5:cloud"
    assert config.skip_content is False
    assert config.skip_format is False


def test_pipeline_config_custom():
    config = PipelineConfig(
        content_max_iterations=5,
        writer_model="model-a",
        reviewer_model="model-b",
        skip_content=True,
    )
    assert config.content_max_iterations == 5
    assert config.skip_content is True


def test_file_result_ok():
    result = FileResult(
        filepath="test.md",
        content_result=None,
        format_result=None,
        final_status="ok",
    )
    assert result.final_status == "ok"


def test_file_result_statuses():
    for status in ["ok", "content_failed", "format_failed", "skipped_chunked"]:
        result = FileResult(
            filepath="test.md",
            content_result=None,
            format_result=None,
            final_status=status,
        )
        assert result.final_status == status
```

- [x] **Step 2: Run test to verify it fails**

Run: `uv run pytest validator/tests/test_pipeline.py -v`
Expected: FAIL

- [x] **Step 3: Implement `pipeline.py`**

Create `validator/src/validator/pipeline.py`:

```python
"""Full pipeline: content loop -> format fix, per file."""

from dataclasses import dataclass
from pathlib import Path

from llm.tokens import count_tokens
from rag.docs import safe_read_lua
from validator.content.loop import ContentLoopConfig, ContentLoopResult, run_content_loop
from validator.format.autofix import FixResult, autofix_file
from validator.format.checks import validate_all, ValidationError
from validator.utils import resolve_lua_path


@dataclass
class PipelineConfig:
    """Configuration for the full validation pipeline."""
    content_max_iterations: int = 3
    writer_model: str = "qwen3.5:cloud"
    reviewer_model: str = "qwen3.5:cloud"
    skip_content: bool = False
    skip_format: bool = False


@dataclass
class FileResult:
    """Result of processing a single file."""
    filepath: str
    content_result: ContentLoopResult | None
    format_result: FixResult | None
    final_status: str   # "ok", "content_failed", "format_failed", "skipped_chunked"


CHUNKED_TOKEN_THRESHOLD = 32_000


def process_file(md_filepath: str, config: PipelineConfig) -> FileResult:
    """Process a single .md file through content loop then format fix."""
    content_result = None
    format_result = None

    # --- Content validation ---
    if not config.skip_content:
        lua_filepath = resolve_lua_path(md_filepath)

        if lua_filepath is None:
            print(f"  [pipeline] No Lua source found for {Path(md_filepath).name}, skipping content")
        else:
            # Check if Lua source is too large for single-context LLM review
            # (token count is on Lua source since that's what must fit in LLM context)
            lua_code = safe_read_lua(lua_filepath)
            if lua_code and count_tokens(lua_code) >= CHUNKED_TOKEN_THRESHOLD:
                print(f"  [pipeline] File is chunked (>={CHUNKED_TOKEN_THRESHOLD} tokens), skipping content")
                return FileResult(
                    filepath=md_filepath,
                    content_result=None,
                    format_result=None,
                    final_status="skipped_chunked",
                )

            content_config = ContentLoopConfig(
                max_iterations=config.content_max_iterations,
                writer_model=config.writer_model,
                reviewer_model=config.reviewer_model,
            )
            content_result = run_content_loop(md_filepath, lua_filepath, content_config)

            if not content_result.approved:
                print(f"  [pipeline] Content not approved after {content_result.iterations} iterations")

    # --- Format validation ---
    if not config.skip_format:
        errors = validate_all(md_filepath)
        if errors:
            print(f"  [pipeline] {len(errors)} format errors found, running autofix")
            format_result = autofix_file(md_filepath)
        else:
            format_result = FixResult(changes=[], remaining_errors=[])

    # --- Determine final status ---
    if content_result and not content_result.approved:
        final_status = "content_failed"
    elif format_result and format_result.remaining_errors:
        final_status = "format_failed"
    else:
        final_status = "ok"

    return FileResult(
        filepath=md_filepath,
        content_result=content_result,
        format_result=format_result,
        final_status=final_status,
    )


def process_batch(target: str, config: PipelineConfig) -> list[FileResult]:
    """Process a batch of .md files through the pipeline."""
    target_path = Path(target)

    if target_path.is_file():
        files = [target_path]
    else:
        files = sorted(target_path.rglob("*.md"))

    print(f"Processing {len(files)} file(s)...")
    results: list[FileResult] = []

    try:
        for i, filepath in enumerate(files, 1):
            print(f"[{i}/{len(files)}] {filepath.name}")
            result = process_file(str(filepath), config)
            results.append(result)
            print(f"  -> {result.final_status}")
    except KeyboardInterrupt:
        print(f"\n[Ctrl+C] Stopped after {len(results)}/{len(files)} files")

    # Summary
    ok = sum(1 for r in results if r.final_status == "ok")
    failed = sum(1 for r in results if "failed" in r.final_status)
    skipped = sum(1 for r in results if r.final_status == "skipped_chunked")

    print(f"\n{'='*40}")
    print(f"  OK: {ok} | Failed: {failed} | Skipped (chunked): {skipped}")
    print(f"{'='*40}")

    return results
```

- [x] **Step 4: Run test to verify it passes**

Run: `uv run pytest validator/tests/test_pipeline.py -v`
Expected: All PASS

- [x] **Step 5: Commit**

```bash
git add validator/src/validator/pipeline.py validator/tests/test_pipeline.py
git commit -m "feat(validator): add pipeline.py — full content+format orchestrator"
```

---

### Task 13: Move `update/validate_update.py`

**Files:**
- Create: `validator/src/validator/update/__init__.py`
- Create: `validator/src/validator/update/validate_update.py` (adapted copy)

- [x] **Step 1: Create update package init**

Create empty `validator/src/validator/update/__init__.py`.

- [x] **Step 2: Copy and adapt validate_update.py**

Copy `validator/src/validator/validate_update.py` to `validator/src/validator/update/validate_update.py`.

Apply these changes:

**Line 7** — change the import:
```python
# Old:
from .validator import validate_full

# New:
from validator.format.checks import validate_all
```

**Lines 17-19** — change how validate_full result is used:
```python
# Old:
    errors = validate_full(filepath)
    if errors == ["OK"]:
        errors = []

# New:
    validation_errors = validate_all(filepath)
    # Convert to strings for compatibility with existing action-specific checks
    errors = [f"[{e.category}] {e.message}" for e in validation_errors]
```

**Line 95** — change the return contract (no more `["OK"]`):
```python
# Old:
    return errors if errors else ["OK"]

# New:
    return errors  # empty list = no errors (replaces old ["OK"] contract)
```

All other code stays the same. Note: callers that check `== ["OK"]` must be updated to check `== []` or `not errors`. Check `watcher/` package for any such callers.

- [x] **Step 3: Verify import works**

Run: `uv run python -c "from validator.update.validate_update import validate_update; print('OK')"`
Expected: prints "OK"

- [x] **Step 4: Commit**

```bash
git add validator/src/validator/update/__init__.py validator/src/validator/update/validate_update.py
git commit -m "refactor(validator): move validate_update.py to update/ package"
```

---

### Task 14: Rewrite `__main__.py` — New CLI entry point

**Files:**
- Modify: `validator/src/validator/__main__.py`

- [x] **Step 1: Rewrite `__main__.py`**

Replace entire content of `validator/src/validator/__main__.py`:

```python
"""Validator CLI entry point."""

import argparse
import sys

from validator.pipeline import PipelineConfig, process_batch
from validator.utils import DOCS_DIR


def main():
    parser = argparse.ArgumentParser(description="Validate DST API documentation")
    parser.add_argument(
        "target", nargs="?", default=str(DOCS_DIR),
        help="File or directory to validate (default: docs dir)",
    )
    parser.add_argument("--content-only", action="store_true", help="Run content validation only")
    parser.add_argument("--format-only", action="store_true", help="Run format validation only")
    parser.add_argument("--max-iterations", type=int, default=3, help="Max content loop iterations")
    parser.add_argument("--writer-model", default="qwen3.5:cloud", help="LLM model for writer")
    parser.add_argument("--reviewer-model", default="qwen3.5:cloud", help="LLM model for reviewer")

    args = parser.parse_args()

    config = PipelineConfig(
        content_max_iterations=args.max_iterations,
        writer_model=args.writer_model,
        reviewer_model=args.reviewer_model,
        skip_content=args.format_only,
        skip_format=args.content_only,
    )

    try:
        process_batch(args.target, config)
    except KeyboardInterrupt:
        print("\n[Ctrl+C] Exiting safely.")
        sys.exit(0)


if __name__ == "__main__":
    main()
```

- [x] **Step 2: Verify CLI help works**

Run: `uv run python -m validator --help`
Expected: Shows usage with `--content-only`, `--format-only`, `--max-iterations`, etc.

- [x] **Step 3: Commit**

```bash
git add validator/src/validator/__main__.py
git commit -m "refactor(validator): rewrite __main__.py with CLI args for new pipeline"
```

---

### Task 15: Update constants and add smoke test

**Files:**
- Modify: `validator/src/validator/constants.py`
- Create: `validator/tests/test_smoke.py`

- [x] **Step 1: Add content loop constants**

Update `validator/src/validator/constants.py`:

```python
MDX_NODE_TIMEOUT = 20

DEFAULT_MAX_ITERATIONS = 3
DEFAULT_MODEL = "qwen3.5:cloud"

__all__ = ["MDX_NODE_TIMEOUT", "DEFAULT_MAX_ITERATIONS", "DEFAULT_MODEL"]
```

- [x] **Step 2: Create smoke test**

Create `validator/tests/test_smoke.py`:

```python
"""Smoke test: verify all new modules import correctly."""


def test_import_format_checks():
    from validator.format.checks import ValidationError, validate_all
    assert ValidationError is not None


def test_import_format_mdx():
    from validator.format.mdx import validate_mdx
    assert validate_mdx is not None


def test_import_format_autofix():
    from validator.format.autofix import FixResult, autofix_file
    assert FixResult is not None


def test_import_content_reviewer():
    from validator.content.reviewer import ReviewResult, parse_review_response
    assert ReviewResult is not None


def test_import_content_writer():
    from validator.content.writer import Patch, apply_patches, parse_writer_response
    assert Patch is not None


def test_import_content_loop():
    from validator.content.loop import ContentLoopConfig, ContentLoopResult
    assert ContentLoopConfig is not None


def test_import_pipeline():
    from validator.pipeline import PipelineConfig, FileResult, process_file
    assert PipelineConfig is not None


def test_import_utils():
    from validator.utils import resolve_lua_path, DOCS_DIR, LUA_DIR
    assert resolve_lua_path is not None


def test_import_update():
    from validator.update.validate_update import validate_update
    assert validate_update is not None


def test_import_constants():
    from validator.constants import MDX_NODE_TIMEOUT, DEFAULT_MAX_ITERATIONS
    assert MDX_NODE_TIMEOUT == 20
    assert DEFAULT_MAX_ITERATIONS == 3
```

- [x] **Step 3: Run all new tests**

Run: `uv run pytest validator/tests/test_smoke.py -v`
Expected: All PASS

- [x] **Step 4: Commit**

```bash
git add validator/src/validator/constants.py validator/tests/test_smoke.py
git commit -m "chore(validator): update constants and add smoke test for all new modules"
```

---

### Task 16: Delete old files and run final verification

**Files to delete:**
- `validator/src/validator/validator.py`
- `validator/src/validator/autofix_mdx.py`
- `validator/src/validator/fix_format.py`
- `validator/src/validator/validate_update.py` (moved to `update/`)
- `validator/tests/test.py` (replaced by `test_smoke.py`)
- `validator/tests/test_logic.py` (replaced by `test_format_checks.py`)
- `validator/tests/test_fix_ref.py` (replaced by `test_format_autofix.py`)

**Important notes:**
- The old `test_logic.py` contains an `AssertionError` typo (line 72: `except AssertionError`). This is resolved by the complete rewrite — the new `test_format_checks.py` uses proper `pytest` assertions instead of manual try/except.
- After Task 3 (moving `validate_mdx.mjs`), the old `autofix_mdx.py` and `validator.py` will be broken. Tasks 1-16 should be executed as a single migration — the old code is not expected to work mid-migration.
- The old `validate_full()` returned `["OK"]` on success. The new `validate_all()` returns an empty list `[]`. Any callers in `watcher/` or other packages that check `== ["OK"]` need to be updated.

- [x] **Step 1: Run all NEW tests to confirm everything works before deletion**

Run: `uv run pytest validator/tests/test_smoke.py validator/tests/test_format_checks.py validator/tests/test_format_autofix.py validator/tests/test_utils.py validator/tests/test_content_reviewer.py validator/tests/test_content_writer.py validator/tests/test_content_loop.py validator/tests/test_pipeline.py -v`
Expected: All PASS

- [x] **Step 2: Delete old source files**

```bash
git rm validator/src/validator/validator.py
git rm validator/src/validator/autofix_mdx.py
git rm validator/src/validator/fix_format.py
git rm validator/src/validator/validate_update.py
```

- [x] **Step 3: Delete old test files**

```bash
git rm validator/tests/test.py
git rm validator/tests/test_logic.py
git rm validator/tests/test_fix_ref.py
```

- [x] **Step 4: Run ALL remaining tests**

Run: `uv run pytest validator/tests/ -v`
Expected: All PASS — no import errors, no broken references

- [x] **Step 5: Verify CLI still works**

Run: `uv run python -m validator --help`
Expected: Shows help text with all CLI options

- [x] **Step 6: Commit**

```bash
git add -A
git commit -m "refactor(validator): remove old files — restructure migration complete"
```

---

## Post-Implementation Verification

After all tasks are complete, verify the full restructure:

1. **Directory structure matches spec:**
   ```
   validator/src/validator/
   ├── __init__.py
   ├── __main__.py
   ├── constants.py
   ├── utils.py
   ├── pipeline.py
   ├── content/
   │   ├── __init__.py
   │   ├── reviewer.py
   │   ├── writer.py
   │   ├── loop.py
   │   ├── chunked.py
   │   └── prompts.py
   ├── format/
   │   ├── __init__.py
   │   ├── checks.py
   │   ├── autofix.py
   │   ├── mdx.py
   │   └── validate_mdx.mjs
   └── update/
       ├── __init__.py
       └── validate_update.py
   ```

2. **All tests pass:** `uv run pytest validator/tests/ -v`

3. **CLI works:** `uv run python -m validator --help`

4. **No old files remain:**
   - `validator.py` — deleted
   - `autofix_mdx.py` — deleted
   - `fix_format.py` — deleted
   - `validate_mdx.mjs` at root level — moved to `format/`
