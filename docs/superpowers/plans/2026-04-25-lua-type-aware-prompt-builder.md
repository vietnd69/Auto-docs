# Lua-Type-Aware Prompt Builder Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the coarse "component vs data_config" skill selection with per-file-type injection so each prompt includes only 1 relevant few-shot example and the matching `writing_guide` section, reducing prompt size by ~22KB per file.

**Architecture:** New `type_detect.py` module provides canonical `detect_lua_type()` used by all prompt builders. Two new helpers in `skills_loader.py` (`few_shot_excludes`, `load_trimmed_writing_guide`) handle the exclusion logic. All prompt-building functions gain a `lua_type` parameter and apply the new pattern instead of the old `exclude=["few_shot_data"]` logic.

**Tech Stack:** Python 3.11, pytest (`.venv/Scripts/pytest`), `re` module (stdlib), `yaml` (already in project).

**Spec:** `docs/superpowers/specs/2026-04-25-lua-type-aware-prompt-builder-design.md`

---

## Chunk 1: Type Detection + Skill Selection Helpers

### Task 1: `type_detect.py` — canonical Lua file type detection

**Files:**
- Create: `prompts/src/prompts/type_detect.py`
- Create: `prompts/tests/test_type_detect.py`

- [ ] **Step 1: Write the failing test**

Create `prompts/tests/test_type_detect.py`:

```python
"""
Tests for type_detect.py
Run: .venv/Scripts/pytest prompts/tests/test_type_detect.py -v
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

passed = 0
failed = 0

def check(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} -- {msg}")
        failed += 1


def run_tests():
    from prompts.type_detect import detect_lua_type

    # Directory-based detection
    check("brains dir", detect_lua_type("./brains/pigbrain.lua") == "brains")
    check("behaviours dir", detect_lua_type("./behaviours/chaseandattack.lua") == "behaviours")
    check("stategraphs dir", detect_lua_type("./stategraphs/SGBeefalo.lua") == "stategraphs")
    check("widgets dir", detect_lua_type("./widgets/badge.lua") == "widgets")
    check("screens dir", detect_lua_type("./screens/DebugMenuScreen.lua") == "screens")
    check("prefabs dir", detect_lua_type("./prefabs/abigail.lua") == "prefabs")
    check("components dir", detect_lua_type("./components/combat.lua") == "components")
    check("cameras dir", detect_lua_type("./cameras/followcamera.lua") == "cameras")

    # Data-config directories
    check("map dir", detect_lua_type("./map/something.lua") == "data_config")
    check("languages dir", detect_lua_type("./languages/strings.lua") == "data_config")
    check("util dir", detect_lua_type("./util/helper.lua") == "data_config")

    # Root-level → data_config
    check("root level", detect_lua_type("achievements.lua") == "data_config")
    check("root level dotslash", detect_lua_type("./achievements.lua") == "data_config")

    # Unknown directory → data_config fallback
    check("unknown dir fallback", detect_lua_type("./unknowndir/foo.lua") == "data_config")

    # Replica suffix wins over directory
    check("replica suffix in components", detect_lua_type("./components/combat_replica.lua") == "replica")
    check("replica suffix in root", detect_lua_type("./container_replica.lua") == "replica")

    # Backslash normalization
    check("backslash normalized", detect_lua_type(".\\brains\\pigbrain.lua") == "brains")

    # Case insensitive directory
    check("uppercase dir", detect_lua_type("./Brains/pigbrain.lua") == "brains")


if __name__ == "__main__":
    print("\n=== type_detect tests ===")
    run_tests()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Run test to verify it fails**

```
.venv/Scripts/pytest prompts/tests/test_type_detect.py -v
```
Expected: `ModuleNotFoundError: No module named 'prompts.type_detect'`

- [ ] **Step 3: Create `prompts/src/prompts/type_detect.py`**

```python
_DIR_TO_TYPE: dict[str, str] = {
    "brains": "brains",
    "behaviours": "behaviours",
    "stategraphs": "stategraphs",
    "widgets": "widgets",
    "screens": "screens",
    "prefabs": "prefabs",
    "components": "components",
    "cameras": "cameras",
}
_DATA_CONFIG_DIRS: frozenset[str] = frozenset({"map", "languages", "util"})


def detect_lua_type(filepath: str) -> str:
    """Return the DST file type for a Lua path.

    Detection order:
    1. Filename ends with '_replica.lua' → 'replica' (regardless of directory)
    2. First directory component maps to a known type
    3. Unknown/root-level/data dirs → 'data_config'

    Accepts paths as produced by main.py: './dir/file.lua' or 'file.lua'.
    Handles backslashes and leading slashes.
    """
    normalized = filepath.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    elif normalized.startswith("/"):
        normalized = normalized.lstrip("/")

    basename = normalized.rsplit("/", 1)[-1]
    if basename.endswith("_replica.lua"):
        return "replica"

    parts = normalized.split("/")
    if len(parts) == 1:
        return "data_config"

    dir_name = parts[0].lower()
    if dir_name in _DATA_CONFIG_DIRS:
        return "data_config"
    return _DIR_TO_TYPE.get(dir_name, "data_config")
```

- [ ] **Step 4: Run test to verify it passes**

```
.venv/Scripts/pytest prompts/tests/test_type_detect.py -v
```
Expected: all tests PASS

- [ ] **Step 5: Commit**

```bash
git add prompts/src/prompts/type_detect.py prompts/tests/test_type_detect.py
git commit -m "feat(prompts): add detect_lua_type() canonical file type detection"
```

---

### Task 2: `writing_guide.md` markers + `skills_loader.py` helpers

**Files:**
- Modify: `skills/rules/writing_guide.md`
- Modify: `prompts/src/prompts/skills_loader.py`
- Modify: `prompts/tests/test_skills_loader.py`

- [ ] **Step 1: Add `<!-- type:X -->` markers to `writing_guide.md`**

Wrap each type-specific subsection in `skills/rules/writing_guide.md` with HTML comment markers. The section content stays **identical** — only the wrapping markers are added.

The 6 subsections to wrap (identified by their `###` headings):

```
### Brain Files — Main Functions        → <!-- type:brains -->
### Behaviour Files — Main Functions    → <!-- type:behaviours -->
### Widget Files — Main Functions       → <!-- type:widgets -->
### Screen Files — Main Functions       → <!-- type:screens -->
### Prefab Files — Main Functions       → <!-- type:prefabs -->
### Replica Files — Main Functions      → <!-- type:replica -->
```

Each block becomes:
```markdown
<!-- type:brains -->
### Brain Files — Main Functions

For brain files (files that call `Brain:new()` or extend Brain):
...
<!-- /type -->
```

The marker `<!-- /type -->` goes immediately before the next `###` heading (or before `### Non-Trivial Mechanics` for the last type block).

Verify: the file should still parse as valid Markdown. Run:
```
.venv/Scripts/python -c "from prompts.skills_loader import load_skill, _clear_cache; _clear_cache(); s = load_skill('writing_guide'); print(len(s), 'chars loaded')"
```
Expected: prints a char count > 4000.

- [ ] **Step 2: Write failing tests for new `skills_loader` functions**

Add the following test functions to `prompts/tests/test_skills_loader.py` (add before the `if __name__ == "__main__":` block, and add calls to them in the `__main__` block):

```python
# -- few_shot_excludes tests -----------------------------------------------

def run_few_shot_excludes_tests():
    from prompts.skills_loader import few_shot_excludes

    ALL_FEW_SHOTS = {
        "few_shot", "few_shot_brain", "few_shot_behaviour",
        "few_shot_stategraph", "few_shot_widget", "few_shot_screen",
        "few_shot_prefab", "few_shot_data",
    }

    # T-FS1: brains type keeps only few_shot_brain
    excl = set(few_shot_excludes("brains"))
    check("few_shot_excludes brains: excludes 7",
          len(excl) == 7, f"got {len(excl)}")
    check("few_shot_excludes brains: few_shot_brain NOT excluded",
          "few_shot_brain" not in excl, "few_shot_brain was excluded")
    check("few_shot_excludes brains: replica_pattern NOT in excludes",
          "replica_pattern" not in excl, "replica_pattern should never be excluded")

    # T-FS2: data_config keeps only few_shot_data
    excl = set(few_shot_excludes("data_config"))
    check("few_shot_excludes data_config: few_shot_data NOT excluded",
          "few_shot_data" not in excl, "few_shot_data was excluded")
    check("few_shot_excludes data_config: few_shot_brain excluded",
          "few_shot_brain" in excl, "few_shot_brain should be excluded")

    # T-FS3: replica keeps few_shot (general)
    excl = set(few_shot_excludes("replica"))
    check("few_shot_excludes replica: few_shot NOT excluded",
          "few_shot" not in excl, "few_shot was excluded for replica")

    # T-FS4: unknown type keeps few_shot (general fallback)
    excl = set(few_shot_excludes("nonexistent"))
    check("few_shot_excludes unknown: few_shot NOT excluded",
          "few_shot" not in excl, "few_shot was excluded for unknown type")

    # T-FS5: returns a list (not set)
    result = few_shot_excludes("brains")
    check("few_shot_excludes returns list",
          isinstance(result, list), f"got {type(result)}")


# -- load_trimmed_writing_guide tests ----------------------------------------

def run_trimmed_writing_guide_tests():
    from prompts.skills_loader import load_trimmed_writing_guide, _clear_cache
    _clear_cache()

    # T-WG1: brains type contains Brain section
    result = load_trimmed_writing_guide("brains")
    check("writing_guide brains: has Brain section",
          "Brain Files" in result or "brain files" in result.lower(),
          f"Brain section missing")

    # T-WG2: brains type does NOT contain other type sections
    check("writing_guide brains: no Behaviour section",
          "Behaviour Files" not in result, "Behaviour section present for brains")
    check("writing_guide brains: no Widget section",
          "Widget Files" not in result, "Widget section present for brains")
    check("writing_guide brains: no Screen section",
          "Screen Files" not in result, "Screen section present for brains")
    check("writing_guide brains: no Prefab section",
          "Prefab Files" not in result, "Prefab section present for brains")
    check("writing_guide brains: no Replica section",
          "Replica Files" not in result, "Replica section present for brains")

    # T-WG3: replica type contains Replica section only
    result = load_trimmed_writing_guide("replica")
    check("writing_guide replica: has Replica section",
          "Replica Files" in result, "Replica section missing")
    check("writing_guide replica: no Brain section",
          "Brain Files" not in result, "Brain section present for replica")

    # T-WG4: cameras type has no type-specific sections
    result = load_trimmed_writing_guide("cameras")
    for section in ["Brain Files", "Behaviour Files", "Widget Files", "Screen Files", "Prefab Files", "Replica Files"]:
        check(f"writing_guide cameras: no {section}",
              section not in result, f"{section} present for cameras")

    # T-WG5: common content is always present
    result = load_trimmed_writing_guide("brains")
    check("writing_guide brains: Constructor Rule present",
          "Constructor Rule" in result, "Constructor Rule missing")
    check("writing_guide brains: Non-Trivial Mechanics present",
          "Non-Trivial Mechanics" in result, "Non-Trivial Mechanics missing")

    # T-WG6: markers stripped from output (not visible to LLM)
    check("writing_guide markers stripped",
          "<!-- type:" not in result and "<!-- /type -->" not in result,
          "Markers visible in output")
```

Add to the `__main__` block:
```python
    print("\n=== few_shot_excludes tests ===")
    run_few_shot_excludes_tests()
    print("\n=== load_trimmed_writing_guide tests ===")
    run_trimmed_writing_guide_tests()
```

Run:
```
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
```
Expected: new tests FAIL with `AttributeError: module 'prompts.skills_loader' has no attribute 'few_shot_excludes'`

- [ ] **Step 3: Implement `few_shot_excludes` and `load_trimmed_writing_guide` in `skills_loader.py`**

Add after the existing imports in `prompts/src/prompts/skills_loader.py`:

```python
import re as _re
```

Add the following at the end of the file (after `combine_skills`):

```python
_ALL_FEW_SHOTS: frozenset[str] = frozenset({
    "few_shot",
    "few_shot_brain",
    "few_shot_behaviour",
    "few_shot_stategraph",
    "few_shot_widget",
    "few_shot_screen",
    "few_shot_prefab",
    "few_shot_data",
})

_FEW_SHOT_FOR_TYPE: dict[str, str] = {
    "brains": "few_shot_brain",
    "behaviours": "few_shot_behaviour",
    "stategraphs": "few_shot_stategraph",
    "widgets": "few_shot_widget",
    "screens": "few_shot_screen",
    "prefabs": "few_shot_prefab",
    "components": "few_shot",
    "replica": "few_shot",
    "cameras": "few_shot",
    "data_config": "few_shot_data",
}

_TYPE_BLOCK_RE = _re.compile(
    r"<!-- type:(\w+) -->\n?(.*?)<!-- /type -->",
    _re.DOTALL,
)


def few_shot_excludes(lua_type: str) -> list[str]:
    """Return exclude list for combine_skills() — all few-shots except the one for lua_type."""
    keep = _FEW_SHOT_FOR_TYPE.get(lua_type, "few_shot")
    return sorted(_ALL_FEW_SHOTS - {keep})


def load_trimmed_writing_guide(
    lua_type: str,
    *,
    _registry_override: dict | None = None,
) -> str:
    """Return writing_guide content with only the type-specific section for lua_type.

    Strips all <!-- type:X -->...<!-- /type --> blocks except the one matching lua_type.
    For types with no dedicated section, strips all type blocks.
    HTML comment markers are removed from the output.
    """
    reg = _get_registry(_override=_registry_override)
    if "writing_guide" not in reg:
        return ""
    content = reg["writing_guide"]["content"]

    def _keep_or_strip(m: _re.Match) -> str:
        return m.group(2).rstrip("\n") if m.group(1) == lua_type else ""

    result = _TYPE_BLOCK_RE.sub(_keep_or_strip, content)
    result = _re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
```

- [ ] **Step 4: Run tests to verify they pass**

```
.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
```
Expected: all tests PASS including new `few_shot_excludes` and `load_trimmed_writing_guide` tests.

- [ ] **Step 5: Commit**

```bash
git add skills/rules/writing_guide.md prompts/src/prompts/skills_loader.py prompts/tests/test_skills_loader.py
git commit -m "feat(prompts): add few_shot_excludes + load_trimmed_writing_guide helpers"
```

---

## Chunk 2: Prompt Builder Updates

### Task 3: `standard.py` — use type-aware skill selection

**Files:**
- Modify: `prompts/src/prompts/standard.py`

- [ ] **Step 1: Replace imports and remove `_detect_file_type`**

In `prompts/src/prompts/standard.py`, replace the top of the file:

**Before:**
```python
from prompts.skills_loader import combine_skills

_DATA_CONFIG_DIRS = {"map", "languages", "util"}


def _detect_file_type(display_filepath: str) -> str:
    """Returns 'component' or 'data_config' based on directory path.
    ...
    """
    normalized = display_filepath.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    elif normalized.startswith("/"):
        normalized = normalized.lstrip("/")
    parts = normalized.split("/")
    if len(parts) == 1:
        return "data_config"
    if parts[0].lower() in _DATA_CONFIG_DIRS:
        return "data_config"
    return "component"
```

**After:**
```python
from prompts.skills_loader import combine_skills, few_shot_excludes, load_trimmed_writing_guide
from prompts.type_detect import detect_lua_type
```

- [ ] **Step 2: Replace skill selection logic in `build_prompt()`**

In `build_prompt()`, replace:
```python
    file_type = _detect_file_type(display_filepath)
    exclude = ["few_shot_data"] if file_type == "component" else ["few_shot"]
    skills_block = combine_skills("analyst", exclude=exclude)
```

With:
```python
    lua_type = detect_lua_type(display_filepath)
    exclude = [*few_shot_excludes(lua_type), "writing_guide"]
    skills_block = combine_skills("analyst", exclude=exclude)
    skills_block += "\n\n=== SKILL: writing_guide ===\n" + load_trimmed_writing_guide(lua_type)
```

- [ ] **Step 3: Verify no import errors and smoke test**

```
.venv/Scripts/python -c "
from prompts.standard import build_prompt
p = build_prompt('combat', 'Combat', './components/combat.lua', 'print(1)', '', version='1.0', today_date='2026-01-01', category_type='components')
assert 'few_shot' in p
assert 'Brain Files' not in p
assert 'Constructor Rule' in p
print('OK — combat prompt:', len(p), 'chars')
p2 = build_prompt('pigbrain', 'Pigbrain', './brains/pigbrain.lua', 'print(1)', '', version='1.0', today_date='2026-01-01', category_type='brains')
assert 'Brain Files' in p2
assert 'Widget Files' not in p2
print('OK — brain prompt:', len(p2), 'chars')
"
```
Expected: both print OK with char counts.

- [ ] **Step 4: Run existing prompt tests (if any)**

```
.venv/Scripts/pytest prompts/tests/ -v
```
Expected: all existing tests PASS.

- [ ] **Step 5: Commit**

```bash
git add prompts/src/prompts/standard.py
git commit -m "feat(prompts): standard.py uses type-aware skill selection"
```

---

### Task 4: `prompts/chunked.py` — add `lua_type` to 7 prompt-building functions

**Files:**
- Modify: `prompts/src/prompts/chunked.py`

All 7 functions follow the same pattern. The `combine_skills()` call is currently **inline in the f-string** (e.g., `{combine_skills("analyst_chunk")}`). It must be extracted to a local variable first.

- [ ] **Step 1: Update imports in `chunked.py`**

In `prompts/src/prompts/chunked.py`, add to the existing `from prompts.skills_loader import combine_skills` line:

```python
from prompts.skills_loader import combine_skills, few_shot_excludes, load_trimmed_writing_guide
```

- [ ] **Step 2: Update `build_chunk_prompt()`**

Add `lua_type: str = ""` as a keyword argument (after `category_type`):

```python
def build_chunk_prompt(
    ...
    category_type: str = "",
    lua_type: str = "",        # ← add this
) -> str:
```

Before the `return f"""...` line, add:
```python
    _exclude = [*few_shot_excludes(lua_type), "writing_guide"]
    _skills = combine_skills("analyst_chunk", exclude=_exclude)
    _skills += "\n\n=== SKILL: writing_guide ===\n" + load_trimmed_writing_guide(lua_type)
```

Replace the inline call in the f-string:
```python
# Before:
{combine_skills("analyst_chunk")}

# After:
{_skills}
```

- [ ] **Step 3: Update `build_merge_prompt()`**

Add `lua_type: str = ""` after `category_type`. Extract and replace `combine_skills("analyst_merge")`:

```python
    _exclude = [*few_shot_excludes(lua_type), "writing_guide"]
    _skills = combine_skills("analyst_merge", exclude=_exclude)
    _skills += "\n\n=== SKILL: writing_guide ===\n" + load_trimmed_writing_guide(lua_type)
```
Replace `{combine_skills("analyst_merge")}` → `{_skills}` in the f-string.

- [ ] **Step 4: Update `build_deps_props_prompt()`**

Add `lua_type: str = ""` as last parameter. Extract before f-string:
```python
    _exclude = [*few_shot_excludes(lua_type), "writing_guide"]
    _skills = combine_skills("analyst_merge", exclude=_exclude)
    _skills += "\n\n=== SKILL: writing_guide ===\n" + load_trimmed_writing_guide(lua_type)
```
Replace `{combine_skills("analyst_merge")}` → `{_skills}`.

- [ ] **Step 5: Update `build_functions_batch_prompt()`**

Same pattern as Step 4. Add `lua_type: str = ""`, extract `_skills`, replace inline call.

- [ ] **Step 6: Update `build_events_prompt()`**

Same pattern. Note: `build_events_prompt` currently has no `category_type` param; add `lua_type: str = ""` directly.

- [ ] **Step 7: Update `build_prose_prompt()`**

Same pattern. `build_prose_prompt` already has `category_type`; add `lua_type: str = ""` after it.

- [ ] **Step 8: Update `_build_merge_prompt_legacy()`**

Add `lua_type: str = ""` after `category_type`. Extract:
```python
    _exclude = [*few_shot_excludes(lua_type), "writing_guide"]
    _skills = combine_skills("analyst_merge_legacy", exclude=_exclude)
    _skills += "\n\n=== SKILL: writing_guide ===\n" + load_trimmed_writing_guide(lua_type)
```
Replace `{combine_skills("analyst_merge_legacy")}` → `{_skills}`.

- [ ] **Step 9: Smoke test**

```
.venv/Scripts/python -c "
from prompts.chunked import build_chunk_prompt
p = build_chunk_prompt('pigbrain', 'Pigbrain', './brains/pigbrain.lua', 'print(1)', 1, 3, lua_type='brains')
assert 'Brain Files' in p, 'Brain section missing'
assert 'Widget Files' not in p, 'Widget section present'
print('OK — chunk prompt brains:', len(p), 'chars')
"
```

- [ ] **Step 10: Run tests**

```
.venv/Scripts/pytest prompts/tests/ -v
```
Expected: all PASS.

- [ ] **Step 11: Commit**

```bash
git add prompts/src/prompts/chunked.py
git commit -m "feat(prompts): chunked.py prompt builders use type-aware skill selection"
```

---

## Chunk 3: Core Pipeline + main.py + update/docs.py

### Task 5: Thread `lua_type` through core pipeline, fix `category_type` in `main.py`, replace `get_category_type`

**Files:**
- Modify: `core/src/core/pipeline/chunked.py`
- Modify: `core/src/core/main.py`
- Modify: `core/src/core/update/docs.py`

#### Part A — `core/src/core/pipeline/chunked.py`

- [ ] **Step 1: Add import of `detect_lua_type`**

In `core/src/core/pipeline/chunked.py`, find the existing imports block and add:

```python
from prompts.type_detect import detect_lua_type
```

- [ ] **Step 2: Add `lua_type` to `multipass_merge()` signature**

In `def multipass_merge(...)`, add `lua_type: str = ""` after `category_type: str = ""`.

Pass it to all 5 prompt-builder calls inside the function:
- `build_deps_props_prompt(comp_name, display_filepath, ..., lua_type=lua_type)` — add as kwarg
- `build_functions_batch_prompt(comp_name, display_filepath, batch, batch_idx, total_batches, lua_type=lua_type)` — add as kwarg (currently called as positional at line 448)
- `build_events_prompt(comp_name, display_filepath, events_json, lua_type=lua_type)` — add as kwarg (line 466)
- `build_prose_prompt(..., lua_type=lua_type)` — add as kwarg (line 480+)
- `build_merge_prompt(...)` is not called from `multipass_merge` — the merge prompt for multipass is assembled differently.

The call at line 448 currently passes positional args and must be converted to keyword syntax:
```python
# Before (line 448 — positional):
prompt = build_functions_batch_prompt(comp_name, display_filepath, batch, batch_idx, total_batches)

# After (keyword for lua_type):
prompt = build_functions_batch_prompt(
    comp_name, display_filepath, batch, batch_idx, total_batches,
    lua_type=lua_type,
)
```

- [ ] **Step 3: Add `lua_type` to `process_chunked_file()` signature**

Add `lua_type: str = ""` after `category_type: str = ""` in the signature.

Thread `lua_type` to all calls inside:

1. `build_chunk_prompt(...)` calls (lines ~850 and ~925) — add `lua_type=lua_type`
2. `multipass_merge(...)` call (line ~1013) — add `lua_type=lua_type`
3. `build_merge_prompt(...)` call (line ~1032) — add `lua_type=lua_type`

- [ ] **Step 4: Smoke test the import**

```
.venv/Scripts/python -c "from core.pipeline.chunked import process_chunked_file; print('import OK')"
```
Expected: `import OK`

#### Part B — `core/src/core/main.py`

- [ ] **Step 5: Remove hardcoded `CATEGORY_TYPE` constant**

Find line:
```python
    CATEGORY_TYPE = "root"
```
Delete it.

- [ ] **Step 6: Add `detect_lua_type` import**

At the top of `main.py` with the other imports, add:
```python
from prompts.type_detect import detect_lua_type
```

- [ ] **Step 7: Compute `category_type` per file inside the loop**

In the main processing loop, **after** `display_filepath` is computed (around line 202), add:

```python
        category_type = detect_lua_type(display_filepath)
```

- [ ] **Step 8: Pass `lua_type` to `process_chunked_file()`**

The existing `process_chunked_file()` call already passes `category_type=CATEGORY_TYPE`. After removing the constant, update both the `build_prompt()` call and the `process_chunked_file()` call to use the local `category_type` variable.

For `process_chunked_file()`, also add `lua_type=category_type` (same value):

```python
result = process_chunked_file(
    ...
    category_type=category_type,
    lua_type=category_type,    # ← add this
    ...
)
```

- [ ] **Step 9: Update `build_prompt()` call to use the local `category_type` variable**

The `build_prompt()` call at line ~243 still uses `category_type=CATEGORY_TYPE` (the deleted constant). Change it to:
```python
        prompt_text = build_prompt(
            ...
            category_type=category_type,    # ← local variable computed per-file in Step 7
        )
```
`CATEGORY_TYPE` and `category_type` are distinct names in Python — the constant deletion in Step 5 will cause a `NameError` here if this is not updated explicitly.

#### Part C — `core/src/core/update/docs.py`

- [ ] **Step 10: Replace `get_category_type` with `detect_lua_type`**

In `core/src/core/update/docs.py`:

Add import at top:
```python
from prompts.type_detect import detect_lua_type
```

Delete the function `get_category_type`:
```python
def get_category_type(lua_rel_path: str) -> str:
    parts = lua_rel_path.split("/")
    return parts[0] if len(parts) > 1 else "root"
```

Replace all calls to `get_category_type(path)` with `detect_lua_type(path)`. Find them:
```
grep -n "get_category_type" core/src/core/update/docs.py
```

- [ ] **Step 11: Run the full test suite**

```
.venv/Scripts/pytest -v
```
Expected: all tests PASS. If there are test failures due to `CATEGORY_TYPE` references or `get_category_type` being removed, fix them.

- [ ] **Step 12: Final smoke test — verify prompt token savings**

```
.venv/Scripts/python -c "
from prompts.standard import build_prompt
p_brain = build_prompt('pigbrain', 'Pigbrain', './brains/pigbrain.lua', 'local x = 1', '', version='1.0', today_date='2026-01-01', category_type='brains')
p_widget = build_prompt('badge', 'Badge', './widgets/badge.lua', 'local x = 1', '', version='1.0', today_date='2026-01-01', category_type='widgets')
print('brain prompt:', len(p_brain), 'chars')
print('widget prompt:', len(p_widget), 'chars')
# Verify cross-contamination is gone
assert 'Widget Files' not in p_brain, 'Widget section leaked into brain prompt'
assert 'Brain Files' not in p_widget, 'Brain section leaked into widget prompt'
assert 'Brain Files' in p_brain, 'Brain section missing from brain prompt'
assert 'Widget Files' in p_widget, 'Widget section missing from widget prompt'
print('All assertions passed')
"
```

- [ ] **Step 13: Commit**

```bash
git add core/src/core/pipeline/chunked.py core/src/core/main.py core/src/core/update/docs.py
git commit -m "feat(core): thread lua_type through chunked pipeline; fix per-file category_type in main"
```
