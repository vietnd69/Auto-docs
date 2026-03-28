# Fix Reviewer-Writer Oscillation — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Eliminate reviewer-writer oscillation in chunked content validation by making the reviewer content-only and adding 3 writer guards.

**Architecture:** Two-part fix: (A) strip format rules from reviewer prompt so it only flags content errors, (B) add 3 guards in chunked.py — heading integrity, hallucination enforcement, patch scope validation — applied after every `apply_patches()` call in both code paths.

**Tech Stack:** Python 3.11, pytest, regex, uv workspace

**Spec:** [2026-03-28-fix-reviewer-oscillation-design.md](../specs/2026-03-28-fix-reviewer-oscillation-design.md)

---

## File Structure

| File | Action | Responsibility |
|------|--------|----------------|
| `validator/src/validator/content/sections.py` | Modify | Add `extract_fn_headings_from_text()`, `delete_fn_block()` |
| `validator/tests/test_sections.py` | Modify | Tests for new section utilities |
| `validator/src/validator/content/chunked.py` | Modify | Add `_extract_removal_targets()`, `_enforce_removals()`, `_validate_patch_scope()`, `_apply_guarded_patches()`. Wire guards into both code paths. |
| `validator/tests/test_content_chunked.py` | Modify | Tests for guard functions + integration |
| `skills/validator_reviewer.md` | Modify | Remove FORMAT CONTRACT, format directives |
| `validator/src/validator/content/prompts.py` | Modify | Remove `fn_format_block`, add content-only directive + quality_rules override |
| `validator/tests/test_content_chunked.py` | Modify | Update test that asserts FORMAT CONTRACT |

---

## Chunk 1: Section Utilities

### Task 1: `extract_fn_headings_from_text()` in sections.py

**Files:**
- Modify: `validator/src/validator/content/sections.py`
- Modify: `validator/tests/test_sections.py`

- [ ] **Step 1: Write failing tests for `extract_fn_headings_from_text`**

Add to `validator/tests/test_sections.py`:

```python
from validator.content.sections import extract_fn_headings_from_text


def test_extract_fn_headings_from_text_backtick():
    """Extracts function names from ### `FuncName(params)` headings."""
    text = "## Main functions\n\n### `GetOwner(inst)`\n* **Description:** gets owner\n\n### `SetOwner(inst, owner)`\n* **Description:** sets owner\n"
    result = extract_fn_headings_from_text(text)
    assert result == {"GetOwner", "SetOwner"}


def test_extract_fn_headings_from_text_no_backtick():
    """Extracts function names from ### FuncName headings (no backticks)."""
    text = "### GetOwner\nsome content\n### SetOwner\nmore content\n"
    result = extract_fn_headings_from_text(text)
    assert result == {"GetOwner", "SetOwner"}


def test_extract_fn_headings_from_text_dotted():
    """Extracts dotted names like CLOSEINSPECTORUTIL.IsValidTarget."""
    text = "### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`\ncontent\n### `CLOSEINSPECTORUTIL.IsValidPos(pos)`\ncontent\n"
    result = extract_fn_headings_from_text(text)
    assert result == {"CLOSEINSPECTORUTIL.IsValidTarget", "CLOSEINSPECTORUTIL.IsValidPos"}


def test_extract_fn_headings_from_text_empty():
    """Empty text returns empty set."""
    assert extract_fn_headings_from_text("") == set()


def test_extract_fn_headings_from_text_no_headings():
    """Text with no ### headings returns empty set."""
    assert extract_fn_headings_from_text("## Overview\nSome text\n") == set()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_sections.py::test_extract_fn_headings_from_text_backtick -v`
Expected: FAIL with `ImportError: cannot import name 'extract_fn_headings_from_text'`

- [ ] **Step 3: Implement `extract_fn_headings_from_text`**

Add to `validator/src/validator/content/sections.py` after the `extract_fn_headings()` function (after line 103):

```python
def extract_fn_headings_from_text(text: str) -> set[str]:
    """Extract normalized function names from ### headings in raw text.

    Parses headings like: ### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`
    Returns: {"CLOSEINSPECTORUTIL.IsValidTarget", "FuncName", ...}
    Strips backticks, parameters, and trailing whitespace.
    """
    headings = re.findall(r'^### `?([^`(\n]+)', text, re.MULTILINE)
    return {h.strip() for h in headings}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_sections.py -k "extract_fn_headings_from_text" -v`
Expected: All 5 tests PASS

- [ ] **Step 5: Commit**

```bash
git add validator/src/validator/content/sections.py validator/tests/test_sections.py
git commit -m "feat(validator): add extract_fn_headings_from_text utility"
```

---

### Task 2: `delete_fn_block()` in sections.py

**Files:**
- Modify: `validator/src/validator/content/sections.py`
- Modify: `validator/tests/test_sections.py`

- [ ] **Step 1: Write failing tests for `delete_fn_block`**

Add to `validator/tests/test_sections.py`:

```python
from validator.content.sections import delete_fn_block


def test_delete_fn_block_middle():
    """Deletes a middle function block, preserving neighbors."""
    text = (
        "### `Foo(x)`\n* **Description:** foo\n\n"
        "### `Bar(y)`\n* **Description:** bar\n\n"
        "### `Baz(z)`\n* **Description:** baz\n"
    )
    result = delete_fn_block(text, "Bar")
    assert "### `Foo(x)`" in result
    assert "### `Bar(y)`" not in result
    assert "### `Baz(z)`" in result


def test_delete_fn_block_last():
    """Deletes the last function block."""
    text = "### `Foo(x)`\ncontent foo\n\n### `Bar(y)`\ncontent bar\n"
    result = delete_fn_block(text, "Bar")
    assert "### `Foo(x)`" in result
    assert "### `Bar(y)`" not in result


def test_delete_fn_block_dotted_name():
    """Deletes block with dotted name like CLOSEINSPECTORUTIL.IsValidTarget."""
    text = (
        "### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`\n* **Description:** check target\n\n"
        "### `CLOSEINSPECTORUTIL.GetRange(inst)`\n* **Description:** get range\n"
    )
    result = delete_fn_block(text, "CLOSEINSPECTORUTIL.IsValidTarget")
    assert "IsValidTarget" not in result
    assert "GetRange" in result


def test_delete_fn_block_not_found():
    """Returns text unchanged if fn_name not found."""
    text = "### `Foo(x)`\ncontent\n"
    assert delete_fn_block(text, "NonExistent") == text


def test_delete_fn_block_first():
    """Deletes the first function block, preserving subsequent blocks."""
    text = "### `Foo(x)`\ncontent foo\n\n### `Bar(y)`\ncontent bar\n"
    result = delete_fn_block(text, "Foo")
    assert "### `Foo(x)`" not in result
    assert "### `Bar(y)`" in result
    assert result.lstrip("\n").startswith("### `Bar(y)`")


def test_delete_fn_block_collapses_blank_lines():
    """Trailing blank lines after deletion are collapsed to one newline."""
    text = "### `Foo(x)`\ncontent foo\n\n\n### `Bar(y)`\ncontent bar\n"
    result = delete_fn_block(text, "Foo")
    assert not result.startswith("\n\n")
    assert "### `Bar(y)`" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_sections.py::test_delete_fn_block_middle -v`
Expected: FAIL with `ImportError: cannot import name 'delete_fn_block'`

- [ ] **Step 3: Implement `delete_fn_block`**

Add to `validator/src/validator/content/sections.py` after `extract_fn_headings_from_text()`:

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_sections.py -k "delete_fn_block" -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add validator/src/validator/content/sections.py validator/tests/test_sections.py
git commit -m "feat(validator): add delete_fn_block utility"
```

---

## Chunk 2: Guard Functions

### Task 3: `_extract_removal_targets()` in chunked.py

**Files:**
- Modify: `validator/src/validator/content/chunked.py`
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing tests for `_extract_removal_targets`**

Add to `validator/tests/test_content_chunked.py`:

```python
from validator.content.chunked import _extract_removal_targets


def test_extract_removal_targets_backtick_names():
    """Extracts backtick-quoted names from hallucination issues."""
    issues = [
        "`CLOSEINSPECTORUTIL.IsValidTarget` does not exist in the Lua source",
        "`CLOSEINSPECTORUTIL.IsValidPos` is hallucinated",
    ]
    batch_text = (
        "### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`\ncontent\n"
        "### `CLOSEINSPECTORUTIL.IsValidPos(pos)`\ncontent\n"
        "### `RealFunction(x)`\ncontent\n"
    )
    result = _extract_removal_targets(issues, batch_text)
    assert "CLOSEINSPECTORUTIL.IsValidTarget" in result
    assert "CLOSEINSPECTORUTIL.IsValidPos" in result
    assert "RealFunction" not in result


def test_extract_removal_targets_no_hallucination_phrases():
    """Issues without removal-intent phrases are ignored."""
    issues = ["Wrong parameter type for `GetOwner`"]
    result = _extract_removal_targets(issues, "### `GetOwner(inst)`\ncontent\n")
    assert result == set()


def test_extract_removal_targets_empty_issues():
    """Empty issues list returns empty set."""
    assert _extract_removal_targets([], "") == set()


def test_extract_removal_targets_cross_reference_filters():
    """Names not present as headings in batch_text are excluded."""
    issues = ["`FakeFunc` does not exist in the Lua source"]
    batch_text = "### `RealFunc(x)`\ncontent\n"
    result = _extract_removal_targets(issues, batch_text)
    assert result == set()  # FakeFunc not in headings


def test_extract_removal_targets_dotted_no_backtick():
    """Dotted CamelCase names extracted even without backticks."""
    issues = ["CLOSEINSPECTORUTIL.IsValidTarget is not found in the Lua source"]
    batch_text = "### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`\ncontent\n"
    result = _extract_removal_targets(issues, batch_text)
    assert "CLOSEINSPECTORUTIL.IsValidTarget" in result


def test_extract_removal_targets_camelcase_fallback():
    """CamelCase last-resort fallback when no backtick or dotted names."""
    issues = ["GetOwner is hallucinated"]
    batch_text = "### `GetOwner(inst)`\ncontent\n"
    result = _extract_removal_targets(issues, batch_text)
    assert "GetOwner" in result
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_content_chunked.py::test_extract_removal_targets_backtick_names -v`
Expected: FAIL with `ImportError: cannot import name '_extract_removal_targets'`

- [ ] **Step 3: Implement `_extract_removal_targets`**

Add to `validator/src/validator/content/chunked.py` after all module-level imports (after line 148, where `Patch` is imported). This avoids `NameError` since `_validate_patch_scope` uses `Patch` in its type annotation:

```python
_REMOVAL_PHRASES = (
    "does not exist in the lua source",
    "hallucinated",
    "not present in the provided lua",
    "should be removed",
    "not found in",
    "fabricated",
    "doesn't appear in source",
    "not defined in the lua",
)


def _extract_removal_targets(issues: list[str], batch_text: str = "") -> set[str]:
    """Parse reviewer issues for hallucination flags, return function names to remove.

    If batch_text is provided, cross-references against actual headings to prevent
    false positives from CamelCase type/class names.
    """
    from validator.content.sections import extract_fn_headings_from_text

    candidates: set[str] = set()
    for issue in issues:
        lower = issue.lower()
        if not any(phrase in lower for phrase in _REMOVAL_PHRASES):
            continue
        # Primary: backtick-quoted names
        backtick_names = re.findall(r'`([A-Z][\w.]+?)(?:\([^)]*\))?`', issue)
        # Fallback: dot-qualified CamelCase
        dotted_names = re.findall(r'\b([A-Z][\w]*(?:\.[A-Z][\w]*)+)\b', issue)
        found = set(backtick_names) | set(dotted_names)
        if not found:
            # Last resort: CamelCase
            found = set(_CAMEL_RE.findall(issue))
        candidates |= found

    if not candidates:
        return set()

    # Cross-reference against actual headings in batch_text
    if batch_text:
        actual_headings = extract_fn_headings_from_text(batch_text)
        return candidates & actual_headings

    return candidates
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_content_chunked.py -k "extract_removal_targets" -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "feat(validator): add _extract_removal_targets for hallucination detection"
```

---

### Task 4: `_enforce_removals()` in chunked.py

**Files:**
- Modify: `validator/src/validator/content/chunked.py`
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing tests for `_enforce_removals`**

Add to `validator/tests/test_content_chunked.py`:

```python
from validator.content.chunked import _enforce_removals


def test_enforce_removals_deletes_hallucinated():
    """Removes function blocks flagged as hallucinated."""
    batch_text = (
        "### `RealFunc(x)`\n* **Description:** real\n\n"
        "### `FakeFunc(y)`\n* **Description:** fake\n\n"
        "### `AnotherReal(z)`\n* **Description:** another\n"
    )
    issues = ["`FakeFunc` does not exist in the Lua source"]
    result = _enforce_removals(batch_text, issues)
    assert "### `RealFunc(x)`" in result
    assert "### `FakeFunc(y)`" not in result
    assert "### `AnotherReal(z)`" in result


def test_enforce_removals_no_targets():
    """No hallucination issues → text unchanged."""
    batch_text = "### `Foo(x)`\ncontent\n"
    issues = ["Wrong parameter type"]
    result = _enforce_removals(batch_text, issues)
    assert result == batch_text


def test_enforce_removals_already_removed():
    """Function already absent → text unchanged."""
    batch_text = "### `Foo(x)`\ncontent\n"
    issues = ["`Bar` does not exist in the Lua source"]
    result = _enforce_removals(batch_text, issues)
    assert result == batch_text
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_content_chunked.py::test_enforce_removals_deletes_hallucinated -v`
Expected: FAIL with `ImportError: cannot import name '_enforce_removals'`

- [ ] **Step 3: Implement `_enforce_removals`**

Add to `validator/src/validator/content/chunked.py` after `_extract_removal_targets`:

```python
def _enforce_removals(batch_text: str, issues: list[str]) -> str:
    """Auto-remove function blocks that reviewer flagged as hallucinated
    but writer failed to delete."""
    from validator.content.sections import extract_fn_headings_from_text, delete_fn_block

    targets = _extract_removal_targets(issues, batch_text)
    if not targets:
        return batch_text
    current_headings = extract_fn_headings_from_text(batch_text)
    for fn_name in targets:
        if fn_name in current_headings:
            batch_text = delete_fn_block(batch_text, fn_name)
            print(f"  [content/chunked] Auto-removed hallucinated: {fn_name}")
    return batch_text
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_content_chunked.py -k "enforce_removals" -v`
Expected: All 3 tests PASS

- [ ] **Step 5: Commit**

```bash
git add validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "feat(validator): add _enforce_removals guard for hallucination cleanup"
```

---

### Task 5: `_validate_patch_scope()` in chunked.py

**Files:**
- Modify: `validator/src/validator/content/chunked.py`
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing tests for `_validate_patch_scope`**

Add to `validator/tests/test_content_chunked.py`:

```python
from validator.content.chunked import _validate_patch_scope
from validator.content.writer import Patch


def test_validate_patch_scope_rejects_heading_deletion():
    """Patch that deletes a ### heading without removal reason is rejected."""
    patches = [
        Patch(
            old_text="### `Foo(x)`\n* **Description:** foo\n",
            new_text="* **Description:** foo\n",
            reason="reformat entry",
        )
    ]
    result = _validate_patch_scope(patches, "## Main functions")
    assert len(result) == 0


def test_validate_patch_scope_allows_heading_deletion_with_removal_reason():
    """Patch that deletes heading with 'remove' reason is allowed."""
    patches = [
        Patch(
            old_text="### `Foo(x)`\n* **Description:** foo\n",
            new_text="",
            reason="remove hallucinated function",
        )
    ]
    result = _validate_patch_scope(patches, "## Main functions")
    assert len(result) == 1


def test_validate_patch_scope_rejects_nonstandard_fields():
    """Patch introducing non-standard field in Main functions is rejected."""
    patches = [
        Patch(
            old_text="* **Description:** old\n",
            new_text="* **Description:** new\n* **Note:** extra info\n",
            reason="add note",
        )
    ]
    result = _validate_patch_scope(patches, "## Main functions")
    assert len(result) == 0


def test_validate_patch_scope_allows_standard_fields():
    """Patch using standard fields (Description, Parameters, Returns, Error states) is allowed."""
    patches = [
        Patch(
            old_text="* **Description:** old\n",
            new_text="* **Description:** new\n* **Returns:** value\n",
            reason="fix return",
        )
    ]
    result = _validate_patch_scope(patches, "## Main functions")
    assert len(result) == 1


def test_validate_patch_scope_skips_field_check_for_non_main():
    """Non-Main-functions sections do not check for standard fields."""
    patches = [
        Patch(
            old_text="**External dependencies:** none\n",
            new_text="**External dependencies:** math\n* **Components used:** none\n",
            reason="add deps",
        )
    ]
    result = _validate_patch_scope(patches, "## Dependencies & tags")
    assert len(result) == 1


def test_validate_patch_scope_allows_normal_patches():
    """Normal patches that don't touch headings or add fields pass through."""
    patches = [
        Patch(
            old_text="* **Description:** wrong desc\n",
            new_text="* **Description:** correct desc\n",
            reason="fix description",
        )
    ]
    result = _validate_patch_scope(patches, "## Main functions")
    assert len(result) == 1
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest validator/tests/test_content_chunked.py::test_validate_patch_scope_rejects_heading_deletion -v`
Expected: FAIL with `ImportError: cannot import name '_validate_patch_scope'`

- [ ] **Step 3: Implement `_validate_patch_scope`**

Add to `validator/src/validator/content/chunked.py` after `_enforce_removals`:

```python
def _validate_patch_scope(patches: list[Patch], section_heading: str = "") -> list[Patch]:
    """Filter out patches that would violate structural constraints."""
    is_main_fns = section_heading == "## Main functions"
    valid = []
    for patch in patches:
        # Reject patches that delete ### headings (unless reason says remove/hallucinate)
        if re.search(r'^### ', patch.old_text, re.MULTILINE) and \
           not re.search(r'^### ', patch.new_text, re.MULTILINE):
            is_removal = any(kw in patch.reason.lower()
                           for kw in ("remove", "hallucin", "not exist", "delete"))
            if not is_removal:
                print(f"  [content/chunked] Patch rejected: would delete heading without removal reason")
                continue

        # Reject patches that introduce non-standard fields (Main functions only)
        if is_main_fns:
            new_fields = re.findall(r'^\* \*\*(\w[\w ]*?):\*\*', patch.new_text, re.MULTILINE)
            allowed = {"Description", "Parameters", "Returns", "Error states"}
            invalid_fields = [f for f in new_fields if f not in allowed]
            if invalid_fields:
                print(f"  [content/chunked] Patch rejected: introduces non-standard field(s): {invalid_fields}")
                continue

        valid.append(patch)
    return valid
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_content_chunked.py -k "validate_patch_scope" -v`
Expected: All 6 tests PASS

- [ ] **Step 5: Commit**

```bash
git add validator/src/validator/content/chunked.py validator/tests/test_content_chunked.py
git commit -m "feat(validator): add _validate_patch_scope guard for structural integrity"
```

---

## Chunk 3: Prompt Changes (Part A)

### Task 6: Update `skills/validator_reviewer.md`

**Files:**
- Modify: `skills/validator_reviewer.md`

- [ ] **Step 1: Replace the full skill file content**

Replace `skills/validator_reviewer.md` with:

```markdown
# Skill: validator_reviewer

=== REVIEWER CHECKLIST ===
Check CONTENT ACCURACY ONLY:
1. Function signatures and params match Lua source exactly — no hallucinated names/types
2. Descriptions are accurate (not vague/wrong about what the function actually does)
3. Usage example uses real function names and correct call patterns
4. Section contains required content (see requirements below)
5. No invented properties, events, or dependencies not present in Lua source

Do NOT flag formatting, bullet style, or structural notation issues — only flag content errors (wrong/missing/hallucinated information).

STRUCTURAL GUARD: Do NOT rename or remove ### headings in your review suggestions unless the function is hallucinated (not in the Lua source).

=== SECTION ## Overview ===
[Component] 2-5 sentences: what this component does + its role in ECS.
Mention key relationships with other components.
[Data config] 2-5 sentences: what static data this file defines, how it is structured,
and how other systems access it via require(). Do NOT reference ECS or AddComponent.

=== SECTION ## Usage example ===
5-15 lines of realistic Lua using actual function names from this file.
[Component] Show CreateEntity(), AddComponent(), then call 2-3 primary functions.
[Data config] Show require() followed by table index access (e.g. Table[1]).
No CreateEntity(), AddComponent(), or inst.components.

=== SECTION ## Dependencies & tags ===
Must contain EXACTLY these labels (in order):
**External dependencies:** — list each `name` -- usage, or omit if none
**Components used:** — list each `component_name` -- methods/properties accessed
**Tags:** — list each `tag_name` -- add/remove/check, or 'None' if no game tags

=== SECTION ## Properties ===
Table with columns: Property | Type | Default Value | Description.
If no properties exist, write header + separator row only (no data rows).
Do NOT invent properties not in the constructor.
Data config files: document the top-level container + each record field.

=== SECTION ## Main functions ===
Each entry uses a ### heading with function name.
Keep ALL functions — never drop trivial getters/setters.

=== SECTION ## Events & listeners ===
- **Listens to:** events registered via inst:ListenForEvent(event, fn)
- **Pushes:** events fired via inst:PushEvent(event, data)
Omit this section entirely if the component has no events.
```

- [ ] **Step 2: Verify the file was written correctly**

Run: `uv run pytest validator/tests/test_content_chunked.py::test_section_reviewer_prompt_returns_tuple -v`
Expected: PASS (prompt still loads and returns a tuple)

- [ ] **Step 3: Commit**

```bash
git add skills/validator_reviewer.md
git commit -m "refactor(skills): strip format rules from validator_reviewer, content-only"
```

---

### Task 7: Update `prompts.py` — content-only reviewer

**Files:**
- Modify: `validator/src/validator/content/prompts.py`
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Remove `_FN_FORMAT` import and `fn_format_block` injection**

In `validator/src/validator/content/prompts.py`:

Remove line 8:
```python
_FN_FORMAT = load_skill("function_format")
```

In `build_section_reviewer_prompt()`, remove lines 162-165:
```python
    is_main_fns = section_heading == "## Main functions"
    fn_format_block = (
        f"\n=== FUNCTION FORMAT REFERENCE ===\n{_FN_FORMAT}\n"
    ) if is_main_fns else ""
```

Replace with:
```python
    is_main_fns = section_heading == "## Main functions"
```

Remove `{fn_format_block}` from the system_prompt f-string (line 211, after `{_QUALITY_RULES}`).

- [ ] **Step 2: Add content-only directive to system prompt**

In `build_section_reviewer_prompt()`, update the system prompt string. After the `=== TARGET ===` block (line 198), before `=== LUA CONTEXT ===`, add:

```python
You are reviewing CONTENT ACCURACY ONLY. Do not flag formatting, bullet style, or structural notation issues.
```

Before the `=== QUALITY RULES ===` block, add the override instruction:

```python
From the quality rules below, apply ONLY content accuracy rules (CONTENT RULES, COMPLETENESS, FILE TYPE CLASSIFICATION, CONSTRUCTOR RULE). IGNORE format rules (OUTPUT FORMAT, YAML FRONTMATTER, HEADING RULES, PROPERTIES TABLE column structure, MDX COMPATIBILITY).
```

The updated system prompt should look like:

```python
    system_prompt = f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API docs.
You are reviewing CONTENT ACCURACY ONLY. Do not flag formatting, bullet style, or structural notation issues.

=== TARGET ===
File type: {file_type} ({file_desc})
Section:   {section_heading or "(preamble)"}

=== LUA CONTEXT (ground truth) ===
{lua_instruction}
{lua_block}
{batch_scope_note}
=== REVIEW RULES ===
{section_ctx}{_REVIEWER_SKILL}

=== QUALITY RULES ===
From the quality rules below, apply ONLY content accuracy rules (CONTENT RULES, COMPLETENESS, FILE TYPE CLASSIFICATION, CONSTRUCTOR RULE). IGNORE format rules (OUTPUT FORMAT, YAML FRONTMATTER, HEADING RULES, PROPERTIES TABLE column structure, MDX COMPATIBILITY).
{_QUALITY_RULES}

=== RESPONSE FORMAT ===
Respond in JSON only with keys "approved" (boolean) and "findings" (array of objects with "issue" and "suggestion").
approved=true with empty findings if accurate. approved=false with paired issue+suggestion for each problem."""
```

- [ ] **Step 3: Update the test that asserts FORMAT CONTRACT**

In `validator/tests/test_content_chunked.py`, update `test_section_reviewer_prompt_contains_format_contract` (line 183):

Replace:
```python
def test_section_reviewer_prompt_contains_format_contract():
    system, user = build_section_reviewer_prompt("## Functions\n### `Foo(x)`\n* **Description:** x\n", "")
    combined = system + user
    assert "FORMAT CONTRACT" in combined or "REVIEW RULES" in combined
    assert "* **Description:**" in user
```

With:
```python
def test_section_reviewer_prompt_content_only():
    """Reviewer prompt focuses on content accuracy, not format."""
    system, user = build_section_reviewer_prompt("## Functions\n### `Foo(x)`\n* **Description:** x\n", "")
    assert "CONTENT ACCURACY ONLY" in system
    assert "FORMAT CONTRACT" not in system
    assert "FUNCTION FORMAT REFERENCE" not in system
    assert "QUALITY RULES" in system
    assert "IGNORE format rules" in system
    assert "* **Description:**" in user
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest validator/tests/test_content_chunked.py -k "reviewer_prompt" -v`
Expected: Both `test_section_reviewer_prompt_returns_tuple` and `test_section_reviewer_prompt_content_only` PASS

- [ ] **Step 5: Commit**

```bash
git add validator/src/validator/content/prompts.py validator/tests/test_content_chunked.py
git commit -m "refactor(validator): make reviewer content-only, remove format injection"
```

---

## Chunk 4: Wire Guards Into Both Code Paths

### Task 8: Extract `_apply_guarded_patches()` helper and wire into large-section path

**Files:**
- Modify: `validator/src/validator/content/chunked.py`

- [ ] **Step 1: Add import for new section utilities**

In `validator/src/validator/content/chunked.py`, update the imports from `validator.content.sections` (lines 137-147) to also import `extract_fn_headings_from_text` and `delete_fn_block`:

```python
from validator.content.sections import (
    DocSection,
    extract_fn_headings,
    extract_fn_headings_from_text,
    extract_function_names,
    extract_lua_context,
    join_md_sections,
    restore_lost_blocks,
    split_md_sections,
    split_section_blocks,
    sub_chunk_section,
)
```

- [ ] **Step 2: Add `_apply_guarded_patches()` helper**

Add after `_validate_patch_scope()`:

```python
def _apply_guarded_patches(
    batch_text: str,
    patches: list[Patch],
    review_issues: list[str],
    section_heading: str,
    backup_blocks: list[str],
) -> tuple[str, int, list[Patch] | None]:
    """Apply patches with all 3 guards. Returns (text, failed, ambiguous).

    Guard 3 (pre-filter) → apply_patches → Guard 1 (heading integrity) → Guard 2 (enforce removals).
    """
    # Guard 3: pre-filter patches
    patches = _validate_patch_scope(patches, section_heading)
    if not patches:
        return batch_text, 0, None

    batch_text_before = batch_text
    batch_text, failed, ambiguous = apply_patches(batch_text, patches)

    # Guard 1: restore accidentally lost headings
    removal_targets = _extract_removal_targets(review_issues, batch_text_before)
    before_headings = extract_fn_headings_from_text(batch_text_before)
    after_headings = extract_fn_headings_from_text(batch_text)
    accidental_loss = (before_headings - after_headings) - removal_targets

    if accidental_loss:
        # Restore lost blocks in original order using backup_blocks sequence.
        # For each lost block, find the correct insertion point by looking for
        # the first subsequent backup block that still exists in batch_text.
        current_heading_list = [
            b.split("\n", 1)[0].strip()
            for b in re.split(r'(?m)^(?=### )', batch_text) if b.strip()
        ]
        restored = 0
        for orig_idx, block in enumerate(backup_blocks):
            # Extract fn_name from block heading using same regex as extract_fn_headings_from_text
            heading_match = re.match(r'^### `?([^`(\n]+)', block)
            if not heading_match:
                continue
            block_fn = heading_match.group(1).strip()
            if block_fn not in accidental_loss:
                continue
            # Find insertion anchor: first later backup entry still present
            insert_pos = len(current_heading_list)
            for later_idx in range(orig_idx + 1, len(backup_blocks)):
                later_match = re.match(r'^### `?([^`(\n]+)', backup_blocks[later_idx])
                if later_match:
                    later_fn = later_match.group(1).strip()
                    if later_fn in after_headings:
                        # Find position of this heading in current text
                        later_heading_line = backup_blocks[later_idx].split("\n", 1)[0].strip()
                        if later_heading_line in current_heading_list:
                            insert_pos = current_heading_list.index(later_heading_line)
                        break
            # Insert block into batch_text at the correct position
            parts = [b for b in re.split(r'(?m)^(?=### )', batch_text) if b]
            parts.insert(insert_pos, block)
            batch_text = "".join(parts)
            current_heading_list.insert(insert_pos, block.split("\n", 1)[0].strip())
            restored += 1
        if restored:
            print(f"  [content/chunked] Restored {restored} accidentally lost headings")

    # Guard 2: enforce removal of hallucinated functions
    batch_text = _enforce_removals(batch_text, review_issues)

    return batch_text, failed, ambiguous if ambiguous else None
```

- [ ] **Step 3: Wire into large-section path (lines 383-456)**

In the large-section batch loop (`for i in range(config.max_iterations):`), replace the patch application block. Find lines 425-455 (from `patches, writer_msgs = write_section_patches(...)` through `if consecutive_fail >= _MAX_FAIL_STREAK:`) and replace the patch application section.

Replace lines 439-440:
```python
                    batch_text, failed, ambiguous = apply_patches(batch_text, patches)
                    last_ambiguous = ambiguous if ambiguous else None
```

With:
```python
                    batch_text, failed, ambiguous = _apply_guarded_patches(
                        batch_text, patches, batch_last_review.issues,
                        section.heading, backup,
                    )
                    last_ambiguous = ambiguous
```

- [ ] **Step 4: Run existing tests to verify no regression**

Run: `uv run pytest validator/tests/test_content_chunked.py -v`
Expected: All existing tests PASS

- [ ] **Step 5: Commit**

```bash
git add validator/src/validator/content/chunked.py
git commit -m "feat(validator): add _apply_guarded_patches helper, wire into large-section path"
```

---

### Task 9: Wire guards into small-section path

**Files:**
- Modify: `validator/src/validator/content/chunked.py`

- [ ] **Step 1: Wire into small-section path (lines 528-603)**

First, add backup creation **before** the iteration loop. Find line 526 (`last_ambiguous: list[Patch] | None = None`) and add after it:

```python
            _, small_backup = split_section_blocks(section.text)
```

This ensures backup reflects the original pre-patching state (same pattern as large-section path's `backup = list(fn_blocks)` at line 345).

Then inside the iteration loop, replace the patch application. Find line 586:
```python
                section.text, failed, ambiguous = apply_patches(section.text, patches)
                last_ambiguous = ambiguous if ambiguous else None
```

Replace with:
```python
                section.text, failed, ambiguous = _apply_guarded_patches(
                    section.text, patches, last_review.issues,
                    section.heading, small_backup,
                )
                last_ambiguous = ambiguous
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest validator/tests/test_content_chunked.py -v`
Expected: All tests PASS

- [ ] **Step 3: Commit**

```bash
git add validator/src/validator/content/chunked.py
git commit -m "feat(validator): wire guards into small-section code path"
```

---

### Task 10: Integration test — guards in action

**Files:**
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write integration test for hallucination enforcement**

Add to `validator/tests/test_content_chunked.py`:

```python
@patch("validator.content.chunked.SECTION_TOKEN_THRESHOLD", 1)
@patch("validator.content.chunked.BATCH_TOKEN_LIMIT", 5000)
def test_guard2_removes_hallucinated_fn(tmp_path):
    """Guard 2: hallucinated function flagged by reviewer is auto-removed even if writer fails."""
    md_content = (
        "---\ntitle: Test\n---\n## Main functions\n\n"
        + _make_fn_block("RealFunc")
        + _make_fn_block("HallucinatedFunc")
    )
    lua_content = "function RealFunc(arg) end\n"
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    md_path.write_text(md_content, encoding="utf-8")
    lua_path.write_text(lua_content, encoding="utf-8")

    call_count = 0
    def _mock_chat(model, messages, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # Reviewer flags HallucinatedFunc
            return _rejected(["`HallucinatedFunc` does not exist in the Lua source"])
        if call_count == 2:
            # Writer returns empty patches (fails to delete)
            return _no_patches()
        return _approved()

    with patch("validator.content.chunked.ollama_chat", side_effect=_mock_chat):
        run_chunked_content_loop(str(md_path), str(lua_path), _config(max_iterations=3))

    result_md = md_path.read_text(encoding="utf-8")
    assert "### `RealFunc(arg)`" in result_md
    assert "HallucinatedFunc" not in result_md
```

- [ ] **Step 2: Write integration test for patch scope guard**

Add to `validator/tests/test_content_chunked.py`:

```python
@patch("validator.content.chunked.SECTION_TOKEN_THRESHOLD", 1)
@patch("validator.content.chunked.BATCH_TOKEN_LIMIT", 5000)
def test_guard3_rejects_heading_deleting_patch(tmp_path):
    """Guard 3: patch that deletes a heading without removal reason is rejected."""
    md_content = (
        "---\ntitle: Test\n---\n## Main functions\n\n"
        + _make_fn_block("Foo")
        + _make_fn_block("Bar")
    )
    lua_content = "function Foo(arg) end\nfunction Bar(arg) end\n"
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    md_path.write_text(md_content, encoding="utf-8")
    lua_path.write_text(lua_content, encoding="utf-8")

    original_block = _make_fn_block("Bar")
    call_count = 0
    def _mock_chat(model, messages, **kw):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return _rejected(["Wrong description for Bar"])
        if call_count == 2:
            # Writer tries to delete Bar heading (no removal reason)
            body = json.dumps([{
                "old_text": original_block,
                "new_text": "* **Description:** bar fixed\n",
                "reason": "reformat entry",
            }])
            return {"message": {"content": body}}
        return _approved()

    with patch("validator.content.chunked.ollama_chat", side_effect=_mock_chat):
        run_chunked_content_loop(str(md_path), str(lua_path), _config(max_iterations=3))

    result_md = md_path.read_text(encoding="utf-8")
    # Bar heading should still exist (guard rejected the patch)
    assert "### `Bar(arg)`" in result_md
```

- [ ] **Step 3: Run all tests**

Run: `uv run pytest validator/tests/test_content_chunked.py -v`
Expected: All tests PASS (including the 2 new integration tests)

- [ ] **Step 4: Commit**

```bash
git add validator/tests/test_content_chunked.py
git commit -m "test(validator): add integration tests for guards 2 and 3"
```

---

### Task 11: Run full test suite

- [ ] **Step 1: Run all validator tests**

Run: `uv run pytest validator/tests/ -v`
Expected: All tests PASS

- [ ] **Step 2: Run full workspace tests**

Run: `uv run pytest`
Expected: All tests PASS

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat(validator): fix reviewer-writer oscillation with content-only reviewer and 3 guards

- Part A: strip format rules from reviewer, content accuracy only
- Part C: Guard 1 (heading integrity), Guard 2 (hallucination enforcement), Guard 3 (patch scope)
- Apply guards to both large-section and small-section code paths"
```
