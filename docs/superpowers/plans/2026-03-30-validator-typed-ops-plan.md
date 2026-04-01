# Validator Typed Operations Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the 3-guard + free-text-patch validation loop with a deterministic pre-filter + typed operations pipeline that eliminates oscillation.

**Architecture:** Deterministic pre-filter (classify local/hallucinated functions, ensure required fields) runs before any LLM call. The reviewer emits typed `Finding` objects with structured identifiers instead of free-text issues. The writer receives one `Finding` at a time and returns one `TypedOp` that targets by name, not text anchor. `apply_typed_ops` applies ops deterministically; convergence = `findings == []`.

**Tech Stack:** Python 3.11, uv workspace, pytest. No new dependencies. All changes inside `validator/src/validator/content/`.

**Spec:** `docs/superpowers/specs/2026-03-30-validator-typed-ops-design.md`

---

## File Map

| File | Action | Responsibility after change |
|---|---|---|
| `validator/src/validator/content/sections.py` | Modify | Add `classify_lua_functions`, `prefilter_fn_blocks`, `ensure_required_fields`, `extract_section_lua_context`, `_update_field_in_text`, `apply_typed_ops` |
| `validator/src/validator/content/reviewer.py` | Modify | Add `Finding` dataclass + `parse_findings_response` / `parse_findings_json`; keep existing `ReviewResult` for `loop.py` |
| `validator/src/validator/content/writer.py` | Modify | Add `TypedOp` dataclass + `parse_typed_op_response` / `parse_typed_op_json`; keep existing `Patch`/`apply_patches` for `loop.py` |
| `validator/src/validator/content/schemas.py` | Modify | Add `FINDINGS_SCHEMA`, `TYPED_OP_SCHEMA`; keep old schemas for `loop.py` |
| `validator/src/validator/content/prompts.py` | Modify | Add `build_typed_reviewer_prompt`, `build_typed_writer_prompt` |
| `validator/src/validator/content/chunked.py` | Rewrite | Remove all guard logic; implement `_run_typed_loop`, `_call_reviewer`, `_call_writer`, `_extract_target_text`; update `run_chunked_content_loop` |
| `validator/tests/test_content_chunked.py` | Modify | Remove guard/oscillation tests; add new tests for pre-filter, apply engine, typed loop |

**Files NOT changed:** `format/checks.py`, `format/autofix.py`, `pipeline.py`, `loop.py`, `update/validate_update.py`

**Import dependency order (no circular deps):**
```
sections.py → writer.py → reviewer.py → prompts.py
chunked.py  → all of the above
loop.py     → reviewer.py, writer.py (unchanged — still uses Patch/ReviewResult)
```

---

## Chunk 1: Data Types + Pre-filter Engine

### Task 1: Add `TypedOp` to `writer.py` and `Finding` to `reviewer.py`

Pure dataclasses only — no logic changes, no test failures introduced.

**Files:**
- Modify: `validator/src/validator/content/writer.py`
- Modify: `validator/src/validator/content/reviewer.py`

- [ ] **Step 1: Add `TypedOp` dataclass to `writer.py`**

Add after the existing `Patch` dataclass (around line 27):

```python
@dataclass
class TypedOp:
    """A semantically typed operation targeting a structural element by name."""
    op: str                # "update_section" | "update_field" | "rewrite_function" | "delete_function"
    section: str           # target section heading, e.g. "## Main functions"
    function: str | None = None   # target fn name (None for section-level ops)
    field: str | None = None      # target field name (None for whole-section/function ops)
    value: str | None = None      # new inline value (single-line), used by update_field
    content: str | None = None    # full replacement content, used by update_section/rewrite_function
```

Also add parse functions after the existing `parse_writer_json`:

```python
def parse_typed_op_response(raw: str) -> "TypedOp | None":
    """Parse writer response for a single TypedOp. Returns None on failure."""
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
    try:
        data = json.loads(cleaned)
        return parse_typed_op_json(data)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_typed_op_json(data: dict) -> "TypedOp | None":
    """Parse pre-validated JSON dict into TypedOp. Returns None if op field missing."""
    if not isinstance(data, dict) or not data.get("op"):
        return None
    return TypedOp(
        op=str(data["op"]),
        section=str(data.get("section", "")),
        function=data.get("function") or None,
        field=data.get("field") or None,
        value=data.get("value") or None,
        content=data.get("content") or None,
    )
```

- [ ] **Step 2: Add `Finding` dataclass to `reviewer.py`**

Add after the existing `ReviewResult` dataclass (around line 30):

```python
@dataclass
class Finding:
    """One content accuracy issue targeting a specific (section, function, field)."""
    section: str           # e.g. "## Overview", "## Main functions"
    function: str | None   # None for non-function sections
    field: str | None      # e.g. "Returns", "Description", None = whole section/function
    rule_id: str           # typed identifier from allowed set for the section
    issue: str             # human-readable description
```

Also add parse functions after the existing `parse_review_json`:

```python
def parse_findings_response(raw: str) -> list["Finding"]:
    """Parse LLM reviewer response into list of Finding objects."""
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
    try:
        data = json.loads(cleaned)
        return parse_findings_json(data)
    except (json.JSONDecodeError, TypeError):
        return []


def parse_findings_json(data: dict) -> list["Finding"]:
    """Parse pre-validated JSON dict into Finding list."""
    if not isinstance(data, dict):
        return []
    findings_data = data.get("findings") or []
    result = []
    for f in findings_data:
        if isinstance(f, dict) and f.get("rule_id") and f.get("issue"):
            result.append(Finding(
                section=str(f.get("section", "")),
                function=f.get("function") or None,
                field=f.get("field") or None,
                rule_id=str(f["rule_id"]),
                issue=str(f["issue"]),
            ))
    return result
```

- [ ] **Step 3: Verify import chain — no circular deps**

```bash
cd d:/code/mod-document && uv run python -c "from validator.content.writer import TypedOp; from validator.content.reviewer import Finding; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd d:/code/mod-document && git add validator/src/validator/content/writer.py validator/src/validator/content/reviewer.py && git commit -m "feat(validator): add TypedOp and Finding dataclasses with parse functions"
```

---

### Task 2: Add pre-filter functions to `sections.py`

**Files:**
- Modify: `validator/src/validator/content/sections.py`
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing tests**

Add to `validator/tests/test_content_chunked.py`:

```python
# ── Task 2: classify_lua_functions ───────────────────────────────────────────

from validator.content.sections import (
    classify_lua_functions,
    prefilter_fn_blocks,
    ensure_required_fields,
)


def test_classify_local_function_keyword():
    lua = "local function _ispassable(x, y) return true end\n"
    result = classify_lua_functions(lua)
    assert result["_ispassable"] == "local"


def test_classify_local_assignment():
    lua = "local MyFn = function(x) return x end\n"
    result = classify_lua_functions(lua)
    assert result["MyFn"] == "local"


def test_classify_global_function():
    lua = "function GetOwner(inst) return inst.owner end\n"
    result = classify_lua_functions(lua)
    assert result["GetOwner"] == "global"


def test_classify_last_definition_wins():
    """Local closure followed by global wrapper → last definition (global) wins."""
    lua = (
        "local function GetOwner(inst) return nil end\n"
        "function GetOwner(inst) return inst.owner end\n"
    )
    result = classify_lua_functions(lua)
    assert result["GetOwner"] == "global"


def test_classify_empty_source():
    assert classify_lua_functions("") == {}


# ── Task 2: prefilter_fn_blocks ──────────────────────────────────────────────

def test_prefilter_removes_local_fn():
    lua = "local function _helper() end\nfunction RealFn(x) end\n"
    blocks = [
        "### `_helper()`\n* **Description:** internal\n",
        "### `RealFn(x)`\n* **Description:** public\n",
    ]
    kept, stripped = prefilter_fn_blocks(blocks, lua)
    assert len(kept) == 1
    assert kept[0].startswith("### `RealFn")
    assert "_helper" in stripped


def test_prefilter_removes_hallucinated():
    lua = "function RealFn(x) end\n"
    blocks = [
        "### `FakeFunc(x)`\n* **Description:** fake\n",
        "### `RealFn(x)`\n* **Description:** real\n",
    ]
    kept, stripped = prefilter_fn_blocks(blocks, lua)
    assert len(kept) == 1
    assert "FakeFunc" in stripped


def test_prefilter_backtick_stripping_snake_case():
    """Backtick-quoted snake_case name extracted correctly before lookup."""
    lua = "local function _ispassable(x, y, sim) return true end\n"
    blocks = ["### `_ispassable(x, y, sim)`\n* **Description:** check\n"]
    kept, stripped = prefilter_fn_blocks(blocks, lua)
    assert kept == []
    assert "_ispassable" in stripped


def test_prefilter_all_local_returns_empty_kept():
    """All functions local → kept_blocks empty, loop should skip review."""
    lua = "local function Foo() end\nlocal function Bar() end\n"
    blocks = ["### `Foo()`\n...", "### `Bar()`\n..."]
    kept, stripped = prefilter_fn_blocks(blocks, lua)
    assert kept == []
    assert len(stripped) == 2


def test_prefilter_unrecognized_heading_kept():
    """Block with unparseable ### heading is kept (fail-safe)."""
    blocks = ["### (no name here)\ncontent\n"]
    kept, stripped = prefilter_fn_blocks(blocks, "function Foo() end\n")
    assert len(kept) == 1
    assert stripped == []


# ── Task 2: ensure_required_fields ───────────────────────────────────────────

def test_ensure_required_fields_adds_missing():
    block = "### `Foo(x)`\n* **Description:** does stuff\n"
    result = ensure_required_fields([block])
    assert "* **Parameters:**" in result[0]
    assert "* **Returns:**" in result[0]


def test_ensure_required_fields_no_duplicate():
    block = (
        "### `Foo(x)`\n"
        "* **Description:** x\n"
        "* **Parameters:** None\n"
        "* **Returns:** nil\n"
    )
    result = ensure_required_fields([block])
    assert result[0].count("* **Parameters:**") == 1


def test_ensure_required_fields_pure_function():
    """ensure_required_fields must not mutate its input."""
    block = "### `Foo()`\n* **Description:** x\n"
    original = block
    ensure_required_fields([block])
    assert block == original
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/test_content_chunked.py -k "classify or prefilter or ensure_required" -v 2>&1 | tail -20
```
Expected: `ImportError` or `AttributeError` (functions not yet defined)

- [ ] **Step 3: Implement in `sections.py`**

Add after the existing `_def_patterns` function (around line 305):

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/test_content_chunked.py -k "classify or prefilter or ensure_required" -v
```
Expected: All green

- [ ] **Step 5: Run full test suite to check no regressions**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/ -v 2>&1 | tail -30
```
Expected: No new failures

- [ ] **Step 6: Commit**

```bash
cd d:/code/mod-document && git add validator/src/validator/content/sections.py validator/tests/test_content_chunked.py && git commit -m "feat(validator): add classify_lua_functions, prefilter_fn_blocks, ensure_required_fields"
```

---

### Task 3: Add `apply_typed_ops` to `sections.py`

**Files:**
- Modify: `validator/src/validator/content/sections.py`
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing tests**

Add to `validator/tests/test_content_chunked.py`:

```python
# ── Task 3: apply_typed_ops ──────────────────────────────────────────────────

from validator.content.sections import apply_typed_ops, DocSection
from validator.content.writer import TypedOp


def _section(heading: str, text: str) -> DocSection:
    return DocSection(heading=heading, text=text)


def test_apply_update_section():
    sections = [_section("## Overview", "## Overview\nOld text.\n")]
    op = TypedOp(op="update_section", section="## Overview", content="## Overview\nNew text.\n")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert result[0].text == "## Overview\nNew text.\n"


def test_apply_update_field_in_section():
    sections = [_section("## Overview", "## Overview\n* **Description:** wrong\n")]
    op = TypedOp(op="update_field", section="## Overview", field="Description", value="correct")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert "* **Description:** correct" in result[0].text
    assert "wrong" not in result[0].text


def test_apply_update_field_in_function():
    fn_block = "### `Foo(x)`\n* **Returns:** wrong\n"
    sections = [_section("## Main functions", "## Main functions\n" + fn_block)]
    op = TypedOp(op="update_field", section="## Main functions", function="Foo", field="Returns", value="entity")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert "* **Returns:** entity" in result[0].text
    assert "wrong" not in result[0].text


def test_apply_rewrite_function():
    fn_block = "### `Foo(x)`\n* **Description:** old\n"
    sections = [_section("## Main functions", "## Main functions\n" + fn_block)]
    new_block = "### `Foo(x)`\n* **Description:** new\n"
    op = TypedOp(op="rewrite_function", section="## Main functions", function="Foo", content=new_block)
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert "new" in result[0].text
    assert "old" not in result[0].text


def test_apply_rewrite_function_not_found_no_exception():
    """Rewrite op for non-existent function → silent no-op, no exception."""
    sections = [_section("## Main functions", "## Main functions\n### `Bar()`\ncontent\n")]
    op = TypedOp(op="rewrite_function", section="## Main functions", function="NonExistent", content="x")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert "Bar" in result[0].text  # original preserved


def test_apply_delete_function():
    sections = [_section("## Main functions",
        "## Main functions\n### `Foo()`\nfoo\n\n### `Bar()`\nbar\n")]
    op = TypedOp(op="delete_function", section="## Main functions", function="Foo")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert "### `Foo()`" not in result[0].text
    assert "### `Bar()`" in result[0].text


def test_apply_delete_function_intentionally_removed_noop():
    """delete_function for already-stripped name → silent no-op."""
    sections = [_section("## Main functions",
        "## Main functions\n### `Bar()`\nbar\n")]
    op = TypedOp(op="delete_function", section="## Main functions", function="_helper")
    result = apply_typed_ops(
        sections, [op], frontmatter="",
        intentionally_removed={"_helper"}
    )
    assert result[0].text == sections[0].text  # unchanged


def test_apply_section_not_found_noop():
    """Op targeting missing section → no exception, other sections unchanged."""
    sections = [_section("## Overview", "## Overview\ncontent\n")]
    op = TypedOp(op="update_section", section="## NonExistent", content="new")
    result = apply_typed_ops(sections, [op], frontmatter="")
    assert result[0].text == "## Overview\ncontent\n"


def test_apply_does_not_mutate_input():
    """apply_typed_ops must return new sections, not modify input."""
    original_text = "## Overview\noriginal\n"
    sections = [_section("## Overview", original_text)]
    op = TypedOp(op="update_section", section="## Overview", content="## Overview\nnew\n")
    apply_typed_ops(sections, [op], frontmatter="")
    assert sections[0].text == original_text  # input unchanged
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/test_content_chunked.py -k "apply_" -v 2>&1 | tail -20
```
Expected: `ImportError: cannot import name 'apply_typed_ops'`

- [ ] **Step 3: Implement in `sections.py`**

Add the following at the **top** of `sections.py`, after the existing imports:

```python
from __future__ import annotations
```

Then add after `ensure_required_fields` (at the end of the file):

```python
# ── Apply engine ──────────────────────────────────────────────────────────────

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
        idx = next((i for i, s in enumerate(result) if s.heading == op.section), None)
        if idx is None:
            continue  # section not found — silent no-op
        section = result[idx]

        if op.op == "update_section":
            section.text = op.content or ""

        elif op.op == "update_field" and op.function:
            preamble, fn_blocks = split_section_blocks(section.text)
            for j, block in enumerate(fn_blocks):
                bm = re.match(r'^### `?([^`(\n]+)', block.split("\n", 1)[0])
                if bm and bm.group(1).strip() == op.function:
                    fn_blocks[j] = _update_field_in_text(block, op.field or "", op.value or "")
                    break
            section.text = preamble + "".join(fn_blocks)

        elif op.op == "update_field":
            section.text = _update_field_in_text(section.text, op.field or "", op.value or "")

        elif op.op == "rewrite_function" and op.function:
            preamble, fn_blocks = split_section_blocks(section.text)
            for j, block in enumerate(fn_blocks):
                bm = re.match(r'^### `?([^`(\n]+)', block.split("\n", 1)[0])
                if bm and bm.group(1).strip() == op.function:
                    fn_blocks[j] = op.content or ""
                    break
            # If function not found: no-op (loop completes without modifying)
            section.text = preamble + "".join(fn_blocks)

        elif op.op == "delete_function" and op.function:
            if op.function in removed:
                continue  # already pre-stripped — silent no-op
            section.text = delete_fn_block(section.text, op.function)

    return result
```

- [ ] **Step 4: Run apply tests**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/test_content_chunked.py -k "apply_" -v
```
Expected: All green

- [ ] **Step 5: Run full validator tests**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/ -v 2>&1 | tail -20
```
Expected: No new failures

- [ ] **Step 6: Commit**

```bash
cd d:/code/mod-document && git add validator/src/validator/content/sections.py validator/tests/test_content_chunked.py && git commit -m "feat(validator): add apply_typed_ops and _update_field_in_text to sections.py"
```

---

## Chunk 2: Section Lua Context + Schemas

### Task 4: Add `extract_section_lua_context` to `sections.py`

**Files:**
- Modify: `validator/src/validator/content/sections.py`
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing tests**

Add to `validator/tests/test_content_chunked.py`:

```python
# ── Task 4: extract_section_lua_context ──────────────────────────────────────

from validator.content.sections import extract_section_lua_context


_LUA_MODULE = """\
local MYCONST = 42
local DEFAULT_VAL = "hello"
require("mymodule")
inst.components.combat:SetHurtSound("dontstarve/creatures/hurt")
inst:AddTag("monster")

function GetOwner(inst)
    return inst.owner
end

function SetTarget(inst, target)
    inst.target = target
end

ListenForEvent("death", inst, OnDeath)
PushEvent("attacked", inst, {attacker = attacker})
"""


def test_extract_overview_stops_at_first_function():
    result = extract_section_lua_context("## Overview", _LUA_MODULE, max_tokens=8000)
    assert "MYCONST" in result
    assert "GetOwner" not in result  # function body not included


def test_extract_usage_example_signatures_only():
    result = extract_section_lua_context("## Usage example", _LUA_MODULE, max_tokens=8000)
    assert "GetOwner" in result
    assert "SetTarget" in result
    # Function bodies not included (only the definition line)
    assert "inst.owner" not in result


def test_extract_dependencies_tags_patterns():
    result = extract_section_lua_context("## Dependencies & tags", _LUA_MODULE, max_tokens=8000)
    assert "require" in result
    assert "AddTag" in result
    assert "combat" in result


def test_extract_properties_class_constructor():
    lua = (
        "local MyClass = Class(function(self, inst)\n"
        "    self.value = 0\n"
        "    self.name = ''\n"
        "end)\n"
        "\n"
        "function MyClass:Method()\n"
        "    return self.value\n"
        "end\n"
    )
    result = extract_section_lua_context("## Properties", lua, max_tokens=8000)
    assert "self.value" in result
    assert "self.name" in result


def test_extract_properties_utility_fallback():
    """Utility module (no Class()) uses constants + table assignments."""
    lua = "local MAX_SIZE = 100\nlocal MIN_VAL = 0\nfunction Foo() end\n"
    result = extract_section_lua_context("## Properties", lua, max_tokens=8000)
    assert "MAX_SIZE" in result


def test_extract_events_listeners():
    result = extract_section_lua_context("## Events & listeners", _LUA_MODULE, max_tokens=8000)
    assert "ListenForEvent" in result
    assert "PushEvent" in result


def test_extract_unknown_section_returns_empty():
    result = extract_section_lua_context("## Unknown Section", _LUA_MODULE, max_tokens=8000)
    assert result == ""


def test_extract_respects_max_tokens():
    """Result token count must not exceed max_tokens limit."""
    from llm.tokens import count_tokens
    lua = "\n".join(f"require('module_{i}')" for i in range(500))
    result = extract_section_lua_context("## Dependencies & tags", lua, max_tokens=100)
    tokens = count_tokens(result)
    if tokens != -1:
        assert tokens <= 110  # allow small margin for truncation marker
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/test_content_chunked.py -k "extract_section_lua" -v 2>&1 | tail -10
```
Expected: `ImportError: cannot import name 'extract_section_lua_context'`

- [ ] **Step 3: Implement in `sections.py`**

Add after `_truncate_blocks_to_lua_limit` (around line 346):

```python
def extract_section_lua_context(
    section_heading: str,
    lua_source: str,
    max_tokens: int,
) -> str:
    """Return a Lua excerpt tailored to the section being reviewed.

    Each heading type receives a different extraction strategy — see spec
    for the rationale. All extraction is additive regex over lua_source lines.
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
        class_match = re.search(r'\bClass\s*\(', lua_source)
        if class_match:
            # Extract constructor body: from Class( to next top-level function
            start = lua_source.rfind("\n", 0, class_match.start()) + 1
            tail = lua_source[class_match.end():]
            end_match = re.search(r'(?m)^(local\s+)?function\b', tail)
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
            if re.search(r'ListenForEvent|PushEvent', line):
                start = max(0, i - 2)
                end = min(len(lines), i + 3)
                ctx_parts.extend(l.rstrip("\n") for l in lines[start:end])
                ctx_parts.append("---")
        blocks = ["\n".join(ctx_parts)] if ctx_parts else []

    else:
        return ""

    return _truncate_blocks_to_lua_limit(blocks, max_tokens)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/test_content_chunked.py -k "extract_section_lua" -v
```
Expected: All green

- [ ] **Step 5: Commit**

```bash
cd d:/code/mod-document && git add validator/src/validator/content/sections.py validator/tests/test_content_chunked.py && git commit -m "feat(validator): add extract_section_lua_context with per-section extraction strategies"
```

---

### Task 5: Update `schemas.py`

Add typed schemas for the new Finding and TypedOp formats.

**Files:**
- Modify: `validator/src/validator/content/schemas.py`

- [ ] **Step 1: Add `FINDINGS_SCHEMA` and `TYPED_OP_SCHEMA`**

Append to `validator/src/validator/content/schemas.py` (keep existing `REVIEW_SCHEMA` and `PATCHES_SCHEMA` — used by `loop.py`):

```python
# ── Typed schemas for chunked validator (replaces REVIEW_SCHEMA / PATCHES_SCHEMA in chunked path) ──

FINDINGS_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "approved": {"type": "boolean"},
        "findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "section":   {"type": "string"},
                    "function":  {"type": ["string", "null"]},
                    "field":     {"type": ["string", "null"]},
                    "rule_id":   {"type": "string"},
                    "issue":     {"type": "string"},
                },
                "required": ["section", "rule_id", "issue"],
            },
        },
    },
    "required": ["approved", "findings"],
}

TYPED_OP_SCHEMA: dict = {
    "type": "object",
    "properties": {
        "op":       {"type": "string",
                     "enum": ["update_section", "update_field", "rewrite_function", "delete_function"]},
        "section":  {"type": "string"},
        "function": {"type": ["string", "null"]},
        "field":    {"type": ["string", "null"]},
        "value":    {"type": ["string", "null"]},
        "content":  {"type": ["string", "null"]},
    },
    "required": ["op", "section"],
}
```

- [ ] **Step 2: Verify import**

```bash
cd d:/code/mod-document && uv run python -c "from validator.content.schemas import FINDINGS_SCHEMA, TYPED_OP_SCHEMA; print('OK')"
```
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd d:/code/mod-document && git add validator/src/validator/content/schemas.py && git commit -m "feat(validator): add FINDINGS_SCHEMA and TYPED_OP_SCHEMA"
```

---

## Chunk 3: Typed Prompts

### Task 6: Add `parse_findings_response` and `parse_typed_op_response` unit tests

These functions were already added in Task 1. Add the tests now.

> **Pre-condition:** Chunk 1 (Tasks 1–3) must be committed before running these tests.
> `Finding` and `TypedOp` must be importable from `reviewer.py` and `writer.py` respectively.
> If they are not, this task will fail on import — go back and complete Tasks 1–3 first.

**Files:**
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Verify pre-condition**

```bash
cd d:/code/mod-document && uv run python -c "from validator.content.reviewer import Finding; from validator.content.writer import TypedOp; print('Pre-condition OK')"
```
Expected: `Pre-condition OK` — if this fails, complete Chunk 1 first.

- [ ] **Step 2: Write and run tests for `parse_findings_response`**

Add to `validator/tests/test_content_chunked.py`:

```python
# ── Task 6: parse_findings_response / parse_typed_op_response ────────────────

from validator.content.reviewer import Finding, parse_findings_response, parse_findings_json
from validator.content.writer import TypedOp, parse_typed_op_response, parse_typed_op_json


def test_parse_findings_response_approved():
    raw = '{"approved": true, "findings": []}'
    findings = parse_findings_response(raw)
    assert findings == []


def test_parse_findings_response_with_finding():
    raw = json.dumps({
        "approved": False,
        "findings": [{
            "section": "## Main functions",
            "function": "GetOwner",
            "field": "Returns",
            "rule_id": "WRONG_VALUE",
            "issue": "Returns description is wrong",
        }]
    })
    findings = parse_findings_response(raw)
    assert len(findings) == 1
    assert findings[0].rule_id == "WRONG_VALUE"
    assert findings[0].function == "GetOwner"


def test_parse_findings_response_strips_think_tags():
    raw = '<think>thinking...</think>{"approved": true, "findings": []}'
    findings = parse_findings_response(raw)
    assert findings == []


def test_parse_findings_response_malformed_returns_empty():
    assert parse_findings_response("not json") == []


def test_parse_findings_json_missing_rule_id_skipped():
    """Findings without rule_id are silently skipped."""
    data = {"approved": False, "findings": [{"section": "## Overview", "issue": "bad"}]}
    findings = parse_findings_json(data)
    assert findings == []


def test_parse_typed_op_response_update_field():
    raw = json.dumps({
        "op": "update_field",
        "section": "## Main functions",
        "function": "GetOwner",
        "field": "Returns",
        "value": "entity or nil",
        "content": None,
    })
    op = parse_typed_op_response(raw)
    assert op is not None
    assert op.op == "update_field"
    assert op.value == "entity or nil"


def test_parse_typed_op_response_missing_op_returns_none():
    raw = json.dumps({"section": "## Overview"})
    assert parse_typed_op_response(raw) is None


def test_parse_typed_op_response_malformed_returns_none():
    assert parse_typed_op_response("broken") is None
```

- [ ] **Step 3: Run tests**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/test_content_chunked.py -k "parse_findings or parse_typed_op" -v
```
Expected: All green

- [ ] **Step 4: Commit**

```bash
cd d:/code/mod-document && git add validator/tests/test_content_chunked.py && git commit -m "test(validator): add unit tests for parse_findings_response and parse_typed_op_response"
```

---

### Task 7: Add typed prompt builders to `prompts.py`

**Files:**
- Modify: `validator/src/validator/content/prompts.py`
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Write failing tests**

Add to `validator/tests/test_content_chunked.py`:

```python
# ── Task 7: typed prompt builders ────────────────────────────────────────────

from validator.content.prompts import build_typed_reviewer_prompt, build_typed_writer_prompt


def test_build_typed_reviewer_prompt_returns_tuple():
    system, user = build_typed_reviewer_prompt(
        "## Main functions\n### `Foo(x)`\n* **Description:** x\n",
        "function Foo(x) end",
        section_heading="## Main functions",
    )
    assert isinstance(system, str)
    assert isinstance(user, str)


def test_build_typed_reviewer_prompt_includes_rule_ids():
    system, _ = build_typed_reviewer_prompt(
        "## Main functions\n### `Foo(x)`\n* **Description:** x\n",
        "",
        section_heading="## Main functions",
        rule_ids=["WRONG_VALUE", "MISSING_PARAM"],
    )
    assert "WRONG_VALUE" in system
    assert "MISSING_PARAM" in system


def test_build_typed_reviewer_prompt_scope_note_for_main_functions():
    """Reviewer for Main functions must include scope note to avoid false positives."""
    system, _ = build_typed_reviewer_prompt(
        "### `Foo(x)`\n* **Description:** x\n",
        "",
        section_heading="## Main functions",
    )
    assert "SCOPE" in system or "scope" in system


def test_build_typed_reviewer_prompt_no_scope_note_for_overview():
    system, _ = build_typed_reviewer_prompt("## Overview\nSome text.\n", "", "## Overview")
    # Overview review should NOT include the Main-functions batch restriction
    assert "SCOPE NOTE" not in system


def test_build_typed_writer_prompt_returns_tuple():
    finding = Finding(
        section="## Main functions",
        function="Foo",
        field="Returns",
        rule_id="WRONG_VALUE",
        issue="Returns nil but should return entity",
    )
    system, user = build_typed_writer_prompt(
        "### `Foo(x)`\n* **Returns:** nil\n",
        "function Foo(x) end",
        finding=finding,
    )
    assert isinstance(system, str)
    assert isinstance(user, str)


def test_build_typed_writer_prompt_includes_issue():
    finding = Finding(
        section="## Main functions", function="Foo", field="Returns",
        rule_id="WRONG_VALUE", issue="Returns nil but should return entity",
    )
    _, user = build_typed_writer_prompt("### `Foo(x)`\n* **Returns:** nil\n", "", finding=finding)
    assert "Returns nil but should return entity" in user


def test_build_typed_writer_prompt_includes_op_choices():
    finding = Finding(section="## Overview", function=None, field=None, rule_id="INACCURATE_DESCRIPTION", issue="x")
    system, _ = build_typed_writer_prompt("## Overview\ntext\n", "", finding=finding)
    assert "update_section" in system
    assert "update_field" in system
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/test_content_chunked.py -k "typed_reviewer_prompt or typed_writer_prompt" -v 2>&1 | tail -10
```
Expected: `ImportError`

- [ ] **Step 3: Implement in `prompts.py`**

Append to `validator/src/validator/content/prompts.py`:

```python
# ── Typed prompt builders (used by chunked.py typed-ops path) ─────────────────

# rule_id sets per section heading — controls what rule_ids the reviewer emits
_RULE_IDS_BY_SECTION: dict[str, list[str]] = {
    "## Overview":             ["WRONG_FILE_TYPE", "INACCURATE_DESCRIPTION", "MISSING_KEY_INFO"],
    "## Usage example":        ["WRONG_FUNCTION_CALL", "USES_INVALID_API", "UNREALISTIC_EXAMPLE"],
    "## Dependencies & tags":  ["MISSING_ENTRY", "EXTRA_ENTRY", "WRONG_USAGE_DESC"],
    "## Properties":           ["WRONG_TYPE", "WRONG_DEFAULT", "MISSING_PROPERTY", "EXTRA_PROPERTY"],
    "## Main functions":       ["WRONG_VALUE", "MISSING_PARAM", "EXTRA_PARAM", "WRONG_DESCRIPTION"],
    "## Events & listeners":   ["MISSING_EVENT", "WRONG_EVENT_NAME"],
}


_FILE_TYPE_DESC = {
    "component": "component with Class() constructor and self.inst",
    "data_config": "data config — returns a plain table/array, no Class() constructor",
    "utility": (
        "utility module — standalone functions accessed via require('modulename'), "
        "NOT via inst.components.X"
    ),
}


def build_typed_reviewer_prompt(
    section_text: str,
    lua_context: str,
    section_heading: str = "",
    rule_ids: list[str] | None = None,
    file_type: str = "component",
) -> tuple[str, str]:
    """Reviewer prompt that emits typed Finding objects.

    Returns (system_prompt, user_content) for multi-role conversation.
    """
    section_ctx = _section_context(section_heading)  # returns "" for unknown headings
    effective_rule_ids = rule_ids or _RULE_IDS_BY_SECTION.get(section_heading, [])
    rule_ids_str = ", ".join(effective_rule_ids) if effective_rule_ids else "WRONG_VALUE"
    file_desc = _FILE_TYPE_DESC.get(file_type, _FILE_TYPE_DESC["component"])

    is_main_fns = section_heading == "## Main functions"
    batch_scope_note = (
        "\n=== SCOPE NOTE ===\n"
        f"You are reviewing a BATCH of ### function entries from '{section_heading}'. "
        "Do NOT flag missing ## sections (## Overview, ## Usage example, etc.) — "
        "they exist elsewhere in the document and are out of scope here.\n"
        if is_main_fns else ""
    )

    lua_block = f"```lua\n{lua_context}\n```" if lua_context else "(none)"

    system_prompt = f"""You are a documentation reviewer for Don't Starve Together (DST) Lua API docs.
Review CONTENT ACCURACY ONLY. Do not flag formatting or structural notation issues.

=== TARGET ===
Section:   {section_heading or "(preamble)"}
File type: {file_type} ({file_desc})

=== LUA CONTEXT (ground truth) ===
{lua_block}
{batch_scope_note}
=== SECTION REQUIREMENTS ===
{section_ctx}{_REVIEWER_SKILL}

=== ALLOWED rule_id VALUES ===
{rule_ids_str}

=== RESPONSE FORMAT ===
Respond in JSON only:
{{
    "approved": true/false,
    "findings": [
        {{
            "section": "{section_heading}",
            "function": "FunctionName or null",
            "field": "FieldName or null",
            "rule_id": "one of the allowed rule_ids above",
            "issue": "specific problem description"
        }}
    ]
}}
approved=true with empty findings if accurate. One Finding per (function, field) problem."""

    user_content = f"=== SECTION TO REVIEW ===\n{section_text}"
    return system_prompt, user_content


def build_typed_writer_prompt(
    target_text: str,
    lua_context: str,
    finding: object,  # Finding — forward ref to avoid import cycle
    section_heading: str = "",
    file_type: str = "component",
) -> tuple[str, str]:
    """Writer prompt that fixes ONE Finding and returns ONE TypedOp.

    Returns (system_prompt, user_content) for multi-role conversation.
    Prompt is kept small (≤ 6K tokens) — target_text is the fn_block or
    section snippet, not the full document.
    """
    lua_block = f"```lua\n{lua_context}\n```" if lua_context else "(none)"

    system_prompt = f"""You are a documentation writer for Don't Starve Together (DST) Lua API docs.
Fix ONE specific issue by returning ONE typed operation. Return JSON only.

=== FORMAT RULES ===
{_WRITER_SKILL}

=== OPERATION TYPES ===
- update_section:   replace the full section text (Overview, Usage example rewrites)
- update_field:     replace one field's inline value (single-line field label only)
- rewrite_function: replace the entire ### function block for the named function
- delete_function:  remove the ### function block (use for hallucinated functions)

=== RESPONSE FORMAT ===
Return a single JSON object:
{{
    "op": "update_section | update_field | rewrite_function | delete_function",
    "section": "## Section heading",
    "function": "FunctionName or null",
    "field": "FieldName or null",
    "value": "new single-line field value or null",
    "content": "full replacement content or null"
}}"""

    # finding may be a Finding dataclass — access via attribute
    fn_val = getattr(finding, "function", None)
    fld_val = getattr(finding, "field", None)
    rule_val = getattr(finding, "rule_id", "")
    issue_val = getattr(finding, "issue", "")
    section_val = getattr(finding, "section", section_heading)

    user_content = f"""=== LUA CONTEXT (ground truth) ===
{lua_block}

=== ISSUE TO FIX ===
section:  {section_val}
function: {fn_val or "(none)"}
field:    {fld_val or "(none)"}
rule_id:  {rule_val}
issue:    {issue_val}

=== TARGET TEXT ===
{target_text}"""

    return system_prompt, user_content
```

- [ ] **Step 4: Run prompt tests**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/test_content_chunked.py -k "typed_reviewer_prompt or typed_writer_prompt" -v
```
Expected: All green

- [ ] **Step 5: Run full validator tests**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/ -v 2>&1 | tail -20
```
Expected: No new failures

- [ ] **Step 6: Commit**

```bash
cd d:/code/mod-document && git add validator/src/validator/content/prompts.py validator/tests/test_content_chunked.py && git commit -m "feat(validator): add build_typed_reviewer_prompt and build_typed_writer_prompt"
```

---

## Chunk 4: Chunked Loop Rewrite + Test Cleanup

### Task 8: Rewrite `chunked.py`

Replace all guard logic with the typed-ops loop. Keep `run_chunked_content_loop` signature unchanged for `pipeline.py` compatibility.

**Files:**
- Rewrite: `validator/src/validator/content/chunked.py`

- [ ] **Step 1: Read the current `run_chunked_content_loop` to understand what to preserve**

```bash
cd d:/code/mod-document && uv run python -c "import inspect; from validator.content.chunked import run_chunked_content_loop; print(inspect.getsource(run_chunked_content_loop)[:200])"
```

- [ ] **Step 2: Write the new `chunked.py`**

Replace the entire file content:

```python
"""Section-by-section content validation for large Lua files (≥32K tokens).

Typed-ops pipeline: deterministic pre-filter → typed LLM review → typed ops apply.
No guards. No free-text patches. Convergence = findings == [].
"""

import re
import time
from pathlib import Path
from typing import Callable

from llm.client import ollama_chat
from llm.paths import PROJECT_ROOT
from llm.settings import (
    BAD_RESPONSE_RETRIES, DEBUG_PROMPTS,
    REVIEWER_TEMPERATURE, WRITER_TEMPERATURE, WRITER_THINK,
    VALIDATOR_CALL_SLEEP,
)
from llm.tokens import count_tokens
from rag.docs import safe_read_lua
from validator.content.loop import ContentLoopConfig, ContentLoopResult
from validator.content.prompts import (
    build_typed_reviewer_prompt,
    build_typed_writer_prompt,
    _RULE_IDS_BY_SECTION,
)
from validator.content.reviewer import Finding, parse_findings_json
from validator.content.schemas import FINDINGS_SCHEMA, TYPED_OP_SCHEMA
from validator.content.sections import (
    DocSection,
    apply_typed_ops,
    classify_lua_functions,
    ensure_required_fields,
    extract_function_names,
    extract_lua_context,
    extract_section_lua_context,
    join_md_sections,
    prefilter_fn_blocks,
    split_md_sections,
    split_section_blocks,
    sub_chunk_section_lua_aware,
)
from validator.content.writer import TypedOp, parse_typed_op_json

_DATA_CONFIG_DIRS = {"map", "languages", "util"}
_DEBUG_DIR = PROJECT_ROOT / ".cache" / "debug_prompts"


def _sleep(stop_check: Callable[[], bool], seconds: int) -> None:
    for _ in range(seconds):
        if stop_check():
            break
        time.sleep(1)


def _dump_prompt(label: str, text: str) -> None:
    _DEBUG_DIR.mkdir(parents=True, exist_ok=True)
    ts = int(time.time())
    path = _DEBUG_DIR / f"{label}_{ts}.txt"
    path.write_text(text, encoding="utf-8")
    print(f"  [debug] Prompt dumped → {path}")


def _detect_file_type(lua_filepath: str, lua_source: str = "") -> str:
    """Returns 'component', 'data_config', or 'utility'."""
    from pathlib import Path as _Path
    parts = _Path(lua_filepath).parts
    try:
        dst_idx = next(i for i, p in enumerate(parts) if p == "dst-scripts")
        rel = parts[dst_idx + 1:]
    except StopIteration:
        rel = parts
    if rel and rel[0].lower() in _DATA_CONFIG_DIRS:
        return "data_config"
    if lua_source and not re.search(r'\bClass\s*\(', lua_source):
        return "utility"
    return "component"


def _try_parse_json(raw: str) -> dict | None:
    """Strip fences and think-tags then parse JSON. Returns None on failure."""
    cleaned = re.sub(r'^```(?:json)?\s*\n?', '', raw.strip())
    cleaned = re.sub(r'\n?```\s*$', '', cleaned)
    cleaned = re.sub(r'<think>[\s\S]*?</think>', '', cleaned).strip()
    try:
        import json
        return json.loads(cleaned)
    except Exception:
        return None


def _call_reviewer(
    text: str,
    lua_ctx: str,
    section_heading: str,
    config: ContentLoopConfig,
    file_type: str,
) -> list[Finding]:
    """Call the reviewer LLM and return structured findings."""
    rule_ids = _RULE_IDS_BY_SECTION.get(section_heading)
    system_prompt, user_content = build_typed_reviewer_prompt(
        text, lua_ctx, section_heading, rule_ids=rule_ids, file_type=file_type
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    token_count = count_tokens(system_prompt + user_content)
    print(f"  [content/chunked] Reviewer prompt: {token_count:,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_reviewer", system_prompt + "\n\n" + user_content)

    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        resp = ollama_chat(
            model=config.reviewer_model,
            messages=messages,
            format=FINDINGS_SCHEMA,
            options={"temperature": REVIEWER_TEMPERATURE},
        )
        raw = resp["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("chunked_reviewer_response", raw)
        data = _try_parse_json(raw)
        if data is None:
            continue
        approved = bool(data.get("approved", False))
        findings = parse_findings_json(data)
        if approved:
            return []
        if findings is not None:
            return findings
    return []


def _extract_target_text(text: str, finding: Finding) -> str:
    """Extract the specific text snippet that a finding targets.

    For function-level findings: returns the fn_block for finding.function.
    For section-level findings: returns the full section text.
    Falls back to full text if the function is not found.
    """
    if finding.function:
        _, fn_blocks = split_section_blocks(text)
        for block in fn_blocks:
            m = re.match(r'^### `?([^`(\n]+)', block.split("\n", 1)[0])
            if m and m.group(1).strip() == finding.function:
                return block
    return text


def _call_writer(
    target_text: str,
    lua_ctx: str,
    finding: Finding,
    config: ContentLoopConfig,
    file_type: str,
) -> TypedOp | None:
    """Call the writer LLM for one Finding and return a TypedOp. Returns None on failure."""
    system_prompt, user_content = build_typed_writer_prompt(
        target_text, lua_ctx, finding, finding.section, file_type
    )
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_content},
    ]
    token_count = count_tokens(system_prompt + user_content)
    print(f"  [content/chunked] Writer prompt: {token_count:,} tokens")
    if DEBUG_PROMPTS:
        _dump_prompt("chunked_writer", system_prompt + "\n\n" + user_content)

    for attempt in range(BAD_RESPONSE_RETRIES + 1):
        resp = ollama_chat(
            model=config.writer_model,
            messages=messages,
            format=TYPED_OP_SCHEMA,
            options={"temperature": WRITER_TEMPERATURE, "think": WRITER_THINK},
        )
        raw = resp["message"]["content"]
        if DEBUG_PROMPTS:
            _dump_prompt("chunked_writer_response", raw)
        data = _try_parse_json(raw)
        if data is None:
            continue
        op = parse_typed_op_json(data)
        if op and op.op:
            return op
    return None


def _run_typed_loop(
    text: str,
    lua_ctx: str,
    section_heading: str,
    intentionally_removed: set[str],
    config: ContentLoopConfig,
    file_type: str,
) -> tuple[str, list[str], int]:
    """Review + fix loop for one section or batch.

    Returns (updated_text, remaining_issues, iterations_used).
    remaining_issues is [] when all findings resolved within max_iterations.
    max_iterations is capped at 3 per spec (beyond 3 adds noise, not signal).
    """
    max_iters = min(config.max_iterations, 3)
    last_findings: list[Finding] = []

    for i in range(max_iters):
        findings = _call_reviewer(text, lua_ctx, section_heading, config, file_type)
        if not findings:
            return text, [], i + 1
        last_findings = findings

        for finding in findings:
            target_text = _extract_target_text(text, finding)
            op = _call_writer(target_text, lua_ctx, finding, config, file_type)
            if op is None:
                continue
            dummy = DocSection(heading=section_heading, text=text)
            updated = apply_typed_ops(
                [dummy], [op], frontmatter="",
                intentionally_removed=intentionally_removed,
            )
            text = updated[0].text

        _sleep(config.stop_check, VALIDATOR_CALL_SLEEP)

    return text, [f.issue for f in last_findings], max_iters


def run_chunked_content_loop(
    md_filepath: str,
    lua_filepath: str,
    config: ContentLoopConfig,
) -> ContentLoopResult:
    """Per-section typed-ops validation loop for large files.

    Phase 1 (pre-filter): classify local functions, strip hallucinations,
    ensure required fields — deterministic, no LLM.
    Phase 2–4 (typed loop): reviewer emits Finding objects, writer produces
    TypedOp per finding, apply_typed_ops applies by name — no guards.
    Convergence: findings == [] or max 3 iterations per section/batch.
    """
    if config.stop_check():
        return ContentLoopResult(
            approved=False, iterations=0, final_issues=["Interrupted by user"]
        )

    lua_source = safe_read_lua(lua_filepath)
    if lua_source is None:
        return ContentLoopResult(
            approved=False, iterations=0,
            final_issues=[f"Cannot read Lua source: {lua_filepath}"],
        )

    md_path = Path(md_filepath)
    md_content = md_path.read_text(encoding="utf-8")
    frontmatter, sections = split_md_sections(md_content)

    if not sections:
        return ContentLoopResult(approved=True, iterations=0, final_issues=[])

    file_type = _detect_file_type(lua_filepath, lua_source)
    total_iterations = 0
    all_issues: list[str] = []

    for sec_idx, section in enumerate(sections, 1):
        if config.stop_check():
            return ContentLoopResult(
                approved=False, iterations=total_iterations,
                final_issues=["Interrupted by user"],
            )
        if not section.heading:
            continue  # skip preamble

        print(f"  [content/chunked] Section {sec_idx}/{len(sections)} '{section.heading}'", end="")

        lua_ctx = extract_section_lua_context(
            section.heading, lua_source, max_tokens=8000
        )

        if section.heading == "## Main functions":
            preamble, fn_blocks = split_section_blocks(section.text)

            # Pre-filter: strip local and hallucinated functions
            fn_blocks, stripped_names = prefilter_fn_blocks(fn_blocks, lua_source)
            intentionally_removed = set(stripped_names)

            if not fn_blocks:
                print(f" — skipped (all functions pre-filtered)")
                section.text = preamble
                continue

            # Ensure required fields present before review
            fn_blocks = ensure_required_fields(fn_blocks)

            # Dynamic batching: Lua token budget 8K, doc token budget 4K
            batches = sub_chunk_section_lua_aware(
                fn_blocks, lua_source, lua_token_limit=8000, doc_token_limit=4000
            )
            n_batches = len(batches)
            print(f" — {len(fn_blocks)} fn(s) in {n_batches} batch(es) [typed-ops]")

            all_updated_blocks: list[str] = []
            for bi, batch in enumerate(batches, 1):
                batch_text = "".join(batch)
                batch_lua_ctx = extract_lua_context(
                    lua_source, extract_function_names(batch_text), max_tokens=8000
                )
                print(f"  [content/chunked] Section {sec_idx} batch {bi}/{n_batches} — reviewing...")
                batch_text, issues, iters = _run_typed_loop(
                    batch_text, batch_lua_ctx, section.heading,
                    intentionally_removed, config, file_type,
                )
                total_iterations += iters
                all_issues.extend(issues)
                # Split updated batch back into individual fn_blocks
                updated_blocks = [b for b in re.split(r'(?m)^(?=### )', batch_text) if b]
                all_updated_blocks.extend(updated_blocks)

            section.text = preamble + "".join(all_updated_blocks)

        else:
            fn_count = len(re.findall(r'(?m)^### ', section.text))
            label = f"{fn_count} fn(s)" if fn_count else "structure only"
            print(f" — {label} found")

            if fn_count == 0 and not lua_ctx:
                print(f"  [content/chunked] Section {sec_idx} — skipped (no content to validate)")
                continue

            section.text, issues, iters = _run_typed_loop(
                section.text, lua_ctx, section.heading,
                intentionally_removed=set(), config=config, file_type=file_type,
            )
            total_iterations += iters
            all_issues.extend(issues)

    md_path.write_text(join_md_sections(frontmatter, sections), encoding="utf-8")

    n_issues = len(all_issues)
    if n_issues:
        print(f"  [content/chunked] Final: {n_issues} issue(s) across failed sections, "
              f"total {total_iterations} iterations")
        print(f"  [pipeline] Content not approved after {total_iterations} iterations")
    else:
        print(f"  [content/chunked] All sections approved ({total_iterations} total iterations)")

    return ContentLoopResult(
        approved=n_issues == 0,
        iterations=total_iterations,
        final_issues=all_issues,
    )
```

- [ ] **Step 3: Verify the module imports without errors**

```bash
cd d:/code/mod-document && uv run python -c "from validator.content.chunked import run_chunked_content_loop; print('OK')"
```
Expected: `OK`

- [ ] **Step 4: Commit**

```bash
cd d:/code/mod-document && git add validator/src/validator/content/chunked.py && git commit -m "feat(validator): rewrite chunked.py — remove all guards, implement typed-ops loop"
```

---

### Task 9: Update `test_content_chunked.py`

Remove tests for deleted guard functions; add new integration tests for the typed-ops loop.

**Files:**
- Modify: `validator/tests/test_content_chunked.py`

- [ ] **Step 1: Identify tests to delete**

These tests reference functions/behavior being eliminated. Delete them entirely:

| Test name | Reason for deletion |
|---|---|
| `test_patches_applied_and_written_to_disk` | Old patch format |
| `test_section_fails_no_patches` | Replaced by `test_section_fails_no_op` (new format) |
| `test_max_iterations_triggers_final_review` | Old final-review behavior removed |
| `test_large_section_all_batches_approved` | Patches `BATCH_TOKEN_LIMIT` constant (removed) |
| `test_large_section_preserves_all_fn_entries` | Same |
| `test_large_section_restores_deleted_fn_entry` | Tests Guard 1 (eliminated) |
| `test_small_section_uses_existing_path` | Patches `SECTION_TOKEN_THRESHOLD` (removed) |
| `test_guard2_removes_hallucinated_fn` | Tests Guard 2 (eliminated) |
| `test_guard3_rejects_heading_deleting_patch` | Tests Guard 3 (eliminated) |
| `test_fingerprint_issues_normalizes` | `_fingerprint_issues` removed |
| `test_fingerprint_issues_empty` | Same |
| `test_oscillation_detected` | `_fingerprint_issues` removed |
| `test_oscillation_breaks_loop` | Oscillation detection removed |
| `test_compact_messages_under_budget` | `_compact_messages` removed |
| `test_compact_messages_over_token_budget` | Same |
| `test_compact_messages_over_turn_limit` | Same |
| `test_compact_messages_*` any remaining | Same |
| `test_extract_removal_targets_*` (6 tests) | `_extract_removal_targets` removed |
| `test_enforce_removals_*` (3 tests) | `_enforce_removals` removed |
| `test_validate_patch_scope_*` (8 tests) | `_validate_patch_scope` removed |
| `test_section_reviewer_prompt_returns_tuple` | Tests `build_section_reviewer_prompt` (old path, replaced by typed prompts) |
| `test_section_reviewer_prompt_content_only` | Same |
| `test_section_writer_prompt_returns_tuple` | Tests `build_section_writer_prompt` (old path, replaced) |
| `test_section_writer_prompt_contains_format_rules` | Same |

- [ ] **Step 2: Update surviving integration test helpers**

Update the mock response helpers at the top of the test file to use the new typed format:

```python
# ── response helpers (typed-ops format) ──────────────────────────────────────

def _approved():
    body = json.dumps({"approved": True, "findings": []})
    return {"message": {"content": body}}


def _rejected(section: str, fn: str | None, field: str | None, rule_id: str, issue: str):
    body = json.dumps({"approved": False, "findings": [{
        "section": section, "function": fn, "field": field,
        "rule_id": rule_id, "issue": issue,
    }]})
    return {"message": {"content": body}}


def _op(op: str, section: str, fn: str | None = None, field: str | None = None,
        value: str | None = None, content: str | None = None):
    body = json.dumps({"op": op, "section": section, "function": fn,
                        "field": field, "value": value, "content": content})
    return {"message": {"content": body}}


def _no_op():
    """Writer returns an empty / invalid response."""
    return {"message": {"content": "{}"}}
```

- [ ] **Step 3: Update surviving integration tests**

Replace the body of these tests to use the new format (keep test names where behavior is equivalent):

```python
def test_all_sections_approved(tmp_path):
    """Reviewer approves every section → result.approved True."""
    md, lua = _write_fixtures(tmp_path)
    with patch("validator.content.chunked.ollama_chat", return_value=_approved()):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is True
    assert result.final_issues == []
    assert result.iterations >= 1


def test_section_fails_no_op(tmp_path):
    """Reviewer rejects + writer returns invalid op → section remains failed."""
    md, lua = _write_fixtures(tmp_path)
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _rejected("## Functions", None, None, "INACCURATE_DESCRIPTION", "Wrong text"),
            _no_op(),  # writer fails
        ],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is False
    assert "Wrong text" in result.final_issues


def test_typed_op_applied_and_written_to_disk(tmp_path):
    """Writer's update_field op is applied and persisted."""
    md, lua = _write_fixtures(tmp_path)
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _rejected("## Functions", "GetOwner", "Returns", "WRONG_VALUE", "Returns wrong type"),
            _op("update_field", "## Functions", fn="GetOwner", field="Returns", value="entity"),
            _approved(),
        ],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is True


def test_stop_check_fires_before_first_review(tmp_path):
    """stop_check() True on entry → approved=False, no LLM calls."""
    md, lua = _write_fixtures(tmp_path)
    with patch("validator.content.chunked.ollama_chat") as mock_chat:
        result = run_chunked_content_loop(md, lua, _config(stop_check=lambda: True))
    assert result.approved is False
    assert result.final_issues == ["Interrupted by user"]
    mock_chat.assert_not_called()


def test_lua_unreadable_returns_failed(tmp_path):
    """Missing Lua file → approved=False with descriptive message."""
    md = tmp_path / "test.md"
    md.write_text(SIMPLE_MD, encoding="utf-8")
    result = run_chunked_content_loop(
        str(md), str(tmp_path / "missing.lua"), _config()
    )
    assert result.approved is False
    assert any("Cannot read Lua source" in issue for issue in result.final_issues)


def test_empty_sections_approved(tmp_path):
    """Markdown with no ## sections is trivially approved."""
    md, lua = _write_fixtures(tmp_path, md_content="---\ntitle: T\n---\n")
    result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is True
    assert result.iterations == 0


def test_multiple_sections_partial_failure(tmp_path):
    """Two sections: first approved, second failed → overall approved=False."""
    md_content = (
        "---\ntitle: T\n---\n"
        "## SectionA\n`Alpha()` docs.\n"
        "## SectionB\n`Beta()` docs.\n"
    )
    lua_content = "function Alpha() return 1 end\nfunction Beta() return 2 end\n"
    md, lua = _write_fixtures(tmp_path, md_content, lua_content)
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _approved(),
            _rejected("## SectionB", None, None, "INACCURATE_DESCRIPTION", "Beta wrong"),
            _no_op(),
        ],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    assert result.approved is False
    assert "Beta wrong" in result.final_issues
```

- [ ] **Step 4: Add new integration tests for pre-filter behavior**

```python
# ── New: pre-filter integration tests ────────────────────────────────────────

def test_prefilter_local_fns_never_reviewed(tmp_path):
    """Local functions are stripped before review — reviewer never called for them."""
    md_content = (
        "---\ntitle: T\n---\n## Main functions\n\n"
        + _make_fn_block("_helper")
        + _make_fn_block("PublicFn")
    )
    lua_content = "local function _helper() end\nfunction PublicFn(arg) end\n"
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    md_path.write_text(md_content, encoding="utf-8")
    lua_path.write_text(lua_content, encoding="utf-8")

    call_count = 0
    def _mock(model, messages, **kw):
        nonlocal call_count
        call_count += 1
        # Check that _helper is NOT in the reviewed content
        full = " ".join(m["content"] for m in messages)
        assert "_helper" not in full, "_helper was passed to reviewer"
        return _approved()

    with patch("validator.content.chunked.ollama_chat", side_effect=_mock):
        result = run_chunked_content_loop(str(md_path), str(lua_path), _config())

    result_md = md_path.read_text(encoding="utf-8")
    assert "### `_helper()`" not in result_md  # stripped by pre-filter


def test_intentionally_removed_not_readded(tmp_path):
    """delete_function op for a pre-stripped name → no-op, document unchanged.

    _ispassable appears in both the md (as a ### block) AND in the Lua as a
    local function. Pre-filter strips it into intentionally_removed. Then if
    the reviewer (wrongly) emits a delete_function op for it, apply_typed_ops
    must silently no-op — not crash or re-add it.
    """
    md_content = (
        "---\ntitle: T\n---\n## Main functions\n\n"
        + _make_fn_block("_ispassable")   # present in md — will be stripped by pre-filter
        + _make_fn_block("PublicFn")
    )
    lua_content = (
        "local function _ispassable(x, y) return true end\n"
        "function PublicFn(arg) end\n"
    )
    md_path = tmp_path / "doc.md"
    lua_path = tmp_path / "doc.lua"
    md_path.write_text(md_content, encoding="utf-8")
    lua_path.write_text(lua_content, encoding="utf-8")

    # Pre-filter strips _ispassable; if reviewer still emits a finding for it
    # and writer responds with delete_function, apply_typed_ops must no-op.
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _rejected("## Main functions", "_ispassable", None, "EXTRA_PARAM", "should not exist"),
            _op("delete_function", "## Main functions", fn="_ispassable"),
            _approved(),
        ],
    ):
        result = run_chunked_content_loop(str(md_path), str(lua_path), _config())

    # No exception; PublicFn still present; _ispassable not in final doc (stripped by pre-filter)
    result_md = md_path.read_text(encoding="utf-8")
    assert "### `PublicFn(arg)`" in result_md
    assert "### `_ispassable(arg)`" not in result_md


def test_writer_op_for_missing_section_no_crash(tmp_path):
    """Writer returns op targeting a non-existent section → no exception."""
    md, lua = _write_fixtures(tmp_path)
    with patch(
        "validator.content.chunked.ollama_chat",
        side_effect=[
            _rejected("## Functions", None, None, "INACCURATE_DESCRIPTION", "issue"),
            _op("update_section", "## NonExistent", content="something"),
            _approved(),
        ],
    ):
        result = run_chunked_content_loop(md, lua, _config())
    # Should complete without exception
    assert isinstance(result.approved, bool)
```

- [ ] **Step 5: Run the full test suite**

```bash
cd d:/code/mod-document && uv run pytest validator/tests/test_content_chunked.py -v 2>&1 | tail -40
```
Expected: All new tests green; deleted tests gone; prompt tests and pre-filter tests all passing

- [ ] **Step 6: Run the full workspace tests**

```bash
cd d:/code/mod-document && uv run pytest -v 2>&1 | tail -30
```
Expected: No failures outside of `test_content_chunked.py`

- [ ] **Step 7: Commit**

```bash
cd d:/code/mod-document && git add validator/tests/test_content_chunked.py && git commit -m "test(validator): remove guard tests, add typed-ops integration tests"
```

---

## Final Verification

- [ ] **Run full test suite one last time**

```bash
cd d:/code/mod-document && uv run pytest -v 2>&1 | tail -30
```
Expected: All green

- [ ] **Verify old guard imports no longer needed**

```bash
cd d:/code/mod-document && uv run python -c "
from validator.content.chunked import run_chunked_content_loop
from validator.content.sections import apply_typed_ops, classify_lua_functions, prefilter_fn_blocks, ensure_required_fields, extract_section_lua_context
from validator.content.reviewer import Finding, parse_findings_json
from validator.content.writer import TypedOp, parse_typed_op_json
from validator.content.schemas import FINDINGS_SCHEMA, TYPED_OP_SCHEMA
print('All imports OK')
"
```
Expected: `All imports OK`

- [ ] **Run a dry-run validation against an existing doc to check runtime behavior**

```bash
cd d:/code/mod-document && uv run python -m validator dst-api-webdocs/docs/componentutil.md --content-only --dry-run 2>&1 | head -40
```

---

## What Gets Eliminated

| Removed | Replaced by |
|---|---|
| `_extract_removal_targets` | Pre-filter: `prefilter_fn_blocks` checks Lua source |
| `_enforce_removals` | Same |
| `_validate_patch_scope` (Guard 3) | Impossible: `TypedOp` schema has no structure-deleting op |
| `_apply_guarded_patches` | `apply_typed_ops` |
| `_fingerprint_issues` | Unnecessary: convergence = `findings == []` |
| `_check_oscillation` | Same |
| `_compact_messages` | No multi-turn conversation in new loop |
| `restore_lost_blocks` call | Impossible: typed ops target by name |
| `Patch` / `apply_patches` in `chunked.py` | `TypedOp` / `apply_typed_ops` |
| `_REMOVAL_PHRASES` list | Eliminated entirely |
| `_CAMEL_RE` | Eliminated entirely |
| `_named_in_issues` pattern | Eliminated entirely |

`Patch`, `apply_patches`, `ReviewResult` still exist in `writer.py` / `reviewer.py` for use by the unchanged `loop.py` (small-file path).
