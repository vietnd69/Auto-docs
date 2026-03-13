# Chunked Prompt Format Consistency Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 3 format inconsistencies in `build_merge_prompt()` so chunked pipeline output matches the `consolecommands.md` / `prompt.py` project standard.

**Architecture:** Single-file change to `chunked_prompt.py`: fix one-line tag quote bug, add a `_FUNCTION_FORMAT_SPEC` module-level constant, inject it into `build_merge_prompt()` at 4 locations. New pytest file `test_chunked_prompt.py` covers all 3 changes with pure string assertions (no LLM calls).

**Tech Stack:** Python 3.x, pytest

**Spec:** `docs/superpowers/specs/2026-03-13-chunked-prompt-format-consistency-design.md`

---

## Files

| File | Action | Responsibility |
|------|--------|----------------|
| `chunked_prompt.py` | Modify | Apply Changes 1, 2, 3 from spec |
| `test_chunked_prompt.py` | Create | Pytest unit tests — no LLM calls, pure string assertions |

---

## Chunk 1: Setup + Task 1 (Tag Quote Bug)

### Task 1: Fix YAML tag quote bug

**Files:**
- Create: `test_chunked_prompt.py`
- Modify: `chunked_prompt.py` (one line)

- [ ] **Step 1.1: Install pytest if not present**

```bash
pip install pytest
```

Expected: `Successfully installed pytest-...` or `Requirement already satisfied`.

- [ ] **Step 1.2: Create `test_chunked_prompt.py` with test helpers and tag tests**

Create file `test_chunked_prompt.py` at the project root with this content:

```python
"""Unit tests for chunked_prompt.py format consistency.

Tests are pure string assertions — no LLM calls required.
"""

import pytest
from pre_synthesis import PreSynthesisResult
from chunked_prompt import build_merge_prompt


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_presynthesis(**overrides):
    """Factory: minimal PreSynthesisResult for testing."""
    defaults = dict(
        tags=["combat", "player"],
        system_scope="player",
        dependencies=[{"component": "health", "usage": "DoDelta"}],
        partial_descriptions=["Manages player health."],
        functions=[{
            "name": "Heal",
            "params": "amount",
            "description": "Heals the player.",
            "returns": "nil",
            "error_states": "None",
            "incomplete": False,
        }],
        events_listens=[{"event": "onhit", "description": "when hit"}],
        events_pushes=[],
        constructor_properties=[{
            "name": "maxhealth",
            "type": "number",
            "default": "100",
            "description": "Max health value.",
        }],
    )
    defaults.update(overrides)
    return PreSynthesisResult(**defaults)


def _build(presynthesis=None, **kwargs):
    """Call build_merge_prompt with test defaults."""
    ps = presynthesis or _make_presynthesis()
    return build_merge_prompt(
        comp_name="health",
        comp_title="Health",
        display_filepath="components/health.lua",
        presynthesis=ps,
        source_hash="abc123",
        today_date="2026-03-13",
        version="714014",
        category_type="components",
        **kwargs,
    )


def _tags_line(prompt: str) -> str:
    """Extract the YAML 'tags:' line from prompt."""
    for line in prompt.splitlines():
        if line.startswith("tags:"):
            return line
    raise AssertionError("No 'tags:' line found in prompt")


# ── Task 1: Tag quote fix ─────────────────────────────────────────────────────

class TestTagQuoteFix:

    def test_tags_no_double_quotes(self):
        prompt = _build()
        tags_line = _tags_line(prompt)
        assert '"' not in tags_line, (
            f"YAML tags should not contain double quotes, got: {tags_line}"
        )

    def test_tags_format_is_unquoted_flow_sequence(self):
        ps = _make_presynthesis(tags=["combat", "player"])
        prompt = _build(presynthesis=ps)
        tags_line = _tags_line(prompt)
        assert tags_line == "tags: [combat, player]", (
            f"Expected 'tags: [combat, player]', got: {tags_line}"
        )

    def test_empty_tags_produces_empty_sequence(self):
        ps = _make_presynthesis(tags=[])
        prompt = _build(presynthesis=ps)
        tags_line = _tags_line(prompt)
        assert tags_line == "tags: []", f"Expected 'tags: []', got: {tags_line}"

    def test_tag_values_appear_unquoted(self):
        ps = _make_presynthesis(tags=["combat", "player"])
        prompt = _build(presynthesis=ps)
        tags_line = _tags_line(prompt)
        assert "combat" in tags_line
        assert "player" in tags_line
        assert '"combat"' not in tags_line
        assert '"player"' not in tags_line
```

- [ ] **Step 1.3: Run Task 1 tests — verify they FAIL**

```bash
pytest test_chunked_prompt.py::TestTagQuoteFix -v
```

Expected: all 4 tests FAIL with `AssertionError` — `'"'` is present in the `tags:` line.

- [ ] **Step 1.4: Apply Change 1 — fix tag quote bug in `chunked_prompt.py`**

In `build_merge_prompt()`, find the line:
```python
    tags_yaml = ", ".join(f'"{t}"' for t in presynthesis.tags)
```

Replace with:
```python
    tags_yaml = ", ".join(presynthesis.tags)
```

- [ ] **Step 1.5: Run Task 1 tests — verify they PASS**

```bash
pytest test_chunked_prompt.py::TestTagQuoteFix -v
```

Expected: all 4 tests PASS.

- [ ] **Step 1.6: Commit**

```bash
git add chunked_prompt.py test_chunked_prompt.py
git commit -m "fix: remove erroneous double-quotes from YAML tags in build_merge_prompt"
```

---

## Chunk 2: Task 2 (_FUNCTION_FORMAT_SPEC constant)

### Task 2: Add `_FUNCTION_FORMAT_SPEC` module-level constant

**Files:**
- Modify: `test_chunked_prompt.py` (add test class)
- Modify: `chunked_prompt.py` (add constant)

- [ ] **Step 2.1: Add Task 2 test class to `test_chunked_prompt.py`**

Add the following import at the top of `test_chunked_prompt.py`, alongside the existing imports:

```python
from chunked_prompt import build_merge_prompt, _FUNCTION_FORMAT_SPEC
```

Then append this class at the end of the file:

```python
# ── Task 2: _FUNCTION_FORMAT_SPEC constant ───────────────────────────────────

class TestFunctionFormatSpec:

    def test_constant_exists_and_is_string(self):
        assert isinstance(_FUNCTION_FORMAT_SPEC, str)
        assert len(_FUNCTION_FORMAT_SPEC) > 50

    def test_constant_has_function_heading_syntax(self):
        assert "### `FunctionName" in _FUNCTION_FORMAT_SPEC, (
            "Constant must show backtick-wrapped function heading"
        )

    def test_constant_has_description_bullet(self):
        assert "* **Description:**" in _FUNCTION_FORMAT_SPEC

    def test_constant_has_parameters_bullet(self):
        assert "* **Parameters:**" in _FUNCTION_FORMAT_SPEC

    def test_constant_has_returns_bullet(self):
        assert "* **Returns:**" in _FUNCTION_FORMAT_SPEC

    def test_constant_has_components_used_label(self):
        assert "**Components used:**" in _FUNCTION_FORMAT_SPEC

    def test_constant_has_tags_label(self):
        assert "**Tags:**" in _FUNCTION_FORMAT_SPEC

    def test_constant_has_no_curly_braces(self):
        assert "{" not in _FUNCTION_FORMAT_SPEC, (
            "Constant must not contain '{' — it would break f-string interpolation"
        )
        assert "}" not in _FUNCTION_FORMAT_SPEC, (
            "Constant must not contain '}' — it would break f-string interpolation"
        )
```

- [ ] **Step 2.2: Run Task 2 tests — verify collection fails**

```bash
pytest test_chunked_prompt.py::TestFunctionFormatSpec -v
```

Expected: pytest aborts at collection with `ImportError: cannot import name '_FUNCTION_FORMAT_SPEC' from 'chunked_prompt'` — no tests run. This confirms the constant does not yet exist.

- [ ] **Step 2.3: Add `_FUNCTION_FORMAT_SPEC` constant to `chunked_prompt.py`**

Insert after the import block (after `from pre_synthesis import PreSynthesisResult`, before `def build_intermediate_merge_prompt`):

```python
_FUNCTION_FORMAT_SPEC = """
=== FUNCTION FORMAT ===
Use EXACTLY this structure for every entry in ## Main functions:

### `FunctionName(params)`
* **Description:** What this function does and when it is called.
* **Parameters:** For a single param: `param` -- type and purpose.
  For multiple params, use sub-bullets:
  - `param1` -- description
  - `param2` -- description
  Write `None` if the function takes no parameters.
* **Returns:** Return value description, or `nil` if nothing is returned.
* **Error states:** Edge cases or early returns. Omit this bullet entirely if none.

=== DEPENDENCY SECTION FORMAT ===
Use EXACTLY these labels in ## Dependencies & tags:

**Components used:**
- `component_name` -- how it is used (methods called, properties accessed)

**Tags:**
- `tag_name` -- add / remove / check

=== FEW-SHOT EXAMPLE ===
Mirror this format only. Do NOT copy the content:

### `ConsoleCommandPlayer()`
* **Description:** Returns the currently selected debug entity, the local player, or the first valid player in AllPlayers.
* **Parameters:** None
* **Returns:** Player instance or `nil` if no valid player found.

### `c_spawn(prefab, count, dontselect)`
* **Description:** Spawns `count` instances of `prefab` at console position. Auto-selects first spawned unless `dontselect`.
* **Parameters:**
  - `prefab` -- string prefab name
  - `count` -- number of instances (default `1`)
  - `dontselect` -- boolean to skip auto-selection
* **Returns:** Last spawned instance, or `nil`.

### `c_save()`
* **Description:** Triggers a save on master sim.
* **Parameters:** None
* **Returns:** None
"""
```

Note: the constant uses `--` (double dash) not em dash `—`, and contains no `{` or `}` characters.

- [ ] **Step 2.4: Run Task 2 tests — verify they PASS**

```bash
pytest test_chunked_prompt.py::TestFunctionFormatSpec -v
```

Expected: all 8 tests PASS.

- [ ] **Step 2.5: Run all tests to confirm no regressions**

```bash
pytest test_chunked_prompt.py -v
```

Expected: all 12 tests PASS (4 from Task 1 + 8 from Task 2).

- [ ] **Step 2.6: Commit**

```bash
git add chunked_prompt.py test_chunked_prompt.py
git commit -m "feat: add _FUNCTION_FORMAT_SPEC constant for consistent merge prompt format"
```

---

## Chunk 3: Task 3 (Inject into build_merge_prompt) + TODO comments

### Task 3: Inject `_FUNCTION_FORMAT_SPEC` into `build_merge_prompt()`

**Files:**
- Modify: `test_chunked_prompt.py` (add test class)
- Modify: `chunked_prompt.py` (4 edits to the f-string + 2 TODO comments)

- [ ] **Step 3.1: Add Task 3 test class to `test_chunked_prompt.py`**

Append this class at the end of `test_chunked_prompt.py`:

```python
# ── Task 3: Format spec injection into build_merge_prompt ────────────────────

class TestMergePromptFormatInjection:

    def test_prompt_contains_format_spec(self):
        prompt = _build()
        assert _FUNCTION_FORMAT_SPEC.strip() in prompt, (
            "build_merge_prompt output must contain _FUNCTION_FORMAT_SPEC"
        )

    def test_prompt_has_components_used_label(self):
        prompt = _build()
        assert "**Components used:**" in prompt

    def test_prompt_has_tags_label(self):
        prompt = _build()
        assert "**Tags:**" in prompt

    def test_prompt_has_function_heading_format(self):
        prompt = _build()
        assert "### `FunctionName" in prompt

    def test_prompt_has_description_bullet(self):
        prompt = _build()
        assert "* **Description:**" in prompt
```

- [ ] **Step 3.2: Run Task 3 tests — verify they FAIL**

```bash
pytest test_chunked_prompt.py::TestMergePromptFormatInjection -v
```

Expected: all 5 tests FAIL — the format spec is not yet injected into the prompt.

- [ ] **Step 3.3: Apply Change 3a — update task 5 text in `build_merge_prompt()`**

In `chunked_prompt.py`, inside `build_merge_prompt()`'s f-string, find:

```
5. Format `## Main functions` — deduplicate functions by name (prefer longer description), format as ### headings with Description/Parameters/Returns.
```

Replace with:

```
5. Format `## Main functions` using EXACTLY the FUNCTION FORMAT defined in the FORMAT SPECIFICATION section below.
   Deduplicate by function name; prefer the entry with more parameter/return detail.
```

- [ ] **Step 3.4: Apply Change 3b — update task 7 text in `build_merge_prompt()`**

In the same f-string, find:

```
7. Write `## Dependencies & tags` — list components and tags from the pre-extracted data.
```

Replace with:

```
7. Format `## Dependencies & tags` using EXACTLY the DEPENDENCY SECTION FORMAT defined in the FORMAT SPECIFICATION section below.
```

- [ ] **Step 3.5: Apply Change 3c — update template body placeholder**

In the f-string template body, find the line under `## Dependencies & tags`:

```
<FORMAT from pre-extracted data>
```

Replace with:

```
<FORMAT using EXACTLY the DEPENDENCY SECTION FORMAT from the FORMAT SPECIFICATION below>
```

- [ ] **Step 3.6: Apply Change 3d — inject format spec into f-string**

In the f-string, find the block that ends task 7 and starts the template separator. The exact text to find:

```
7. Format `## Dependencies & tags` using EXACTLY the DEPENDENCY SECTION FORMAT defined in the FORMAT SPECIFICATION section below.

---
id: {comp_name}
```

Replace with:

```
7. Format `## Dependencies & tags` using EXACTLY the DEPENDENCY SECTION FORMAT defined in the FORMAT SPECIFICATION section below.

=== FORMAT SPECIFICATION ===
{_FUNCTION_FORMAT_SPEC}
---
id: {comp_name}
```

- [ ] **Step 3.7: Add TODO comments above legacy functions**

In `chunked_prompt.py`, find the line:

```python
def _build_merge_prompt_legacy(
```

Add this comment immediately above it:

```python
# TODO(format-consistency): apply _FUNCTION_FORMAT_SPEC here when legacy path is retired
def _build_merge_prompt_legacy(
```

Then find:

```python
def build_intermediate_merge_prompt(
```

Add this comment immediately above it:

```python
# TODO(format-consistency): apply _FUNCTION_FORMAT_SPEC here when legacy path is retired
def build_intermediate_merge_prompt(
```

- [ ] **Step 3.8: Run Task 3 tests — verify they PASS**

```bash
pytest test_chunked_prompt.py::TestMergePromptFormatInjection -v
```

Expected: all 5 tests PASS.

- [ ] **Step 3.9: Run full test suite — verify no regressions**

```bash
pytest test_chunked_prompt.py -v
```

Expected: all 17 tests PASS (4 + 8 + 5).

- [ ] **Step 3.10: Commit**

```bash
git add chunked_prompt.py test_chunked_prompt.py
git commit -m "feat: inject _FUNCTION_FORMAT_SPEC into build_merge_prompt for format consistency"
```

---

## Verification

After all 3 tasks complete, verify the full fix by running the manual test script and inspecting the output:

- [ ] **Step V.1: Run chunked_test.py to regenerate test_merge.md**

```bash
python chunked_test.py
```

Expected: generates `test_merge.md`.

- [ ] **Step V.2: Inspect test_merge.md — check 5 success criteria**

Open `test_merge.md` and verify:

1. The `tags:` line contains no `"` character
2. Each function entry starts with `` ### ` `` (backtick immediately after `### `)
3. Each function body contains `* **Description:**` (asterisk + one space)
4. `## Dependencies & tags` section contains `**Components used:**`
5. `## Dependencies & tags` section contains `**Tags:**`
