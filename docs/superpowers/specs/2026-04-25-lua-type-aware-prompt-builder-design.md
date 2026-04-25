# Lua-Type-Aware Prompt Builder

**Date:** 2026-04-25
**Status:** Approved

## Problem

The `analyst` prompt currently injects all 8 few-shot skill files (~24KB) and the full `writing_guide.md` (~7KB) regardless of which Lua file is being documented. For a file like `brains/pigbrain.lua`, only `few_shot_brain` is relevant — the other 7 few-shots (behaviour, widget, screen, prefab, stategraph, general, data) add noise and bloat. This caused the analyst prompt to reach ~62K chars covering all 9 DST file types simultaneously.

Additionally, `category_type` in the YAML frontmatter output is hardcoded to `"root"` for every file — never reflecting the actual file type.

## Goal

- Reduce prompt size by ~22KB per file by injecting only the 1 relevant few-shot
- Trim `writing_guide.md` to only the type-specific section relevant to the current file
- Fix `category_type` to reflect the actual directory type per file
- Apply to all 3 prompt builders: `standard.py`, `chunked.py`, `update.py`

## Chosen Approach: Single `detect_lua_type()` + exclude-list

Directory-based detection. One canonical function replaces two overlapping ones (`_detect_file_type` in `standard.py` and `get_category_type` in `update/docs.py`). Skill files are not modified (except adding HTML comment markers to `writing_guide.md`).

---

## Section 1 — Type Detection

**New file: `prompts/src/prompts/type_detect.py`**

Single public function:

```python
def detect_lua_type(filepath: str) -> str:
    ...
```

Returns one of 9 type strings based on the first directory component of the path. Handles `./` prefix and backslash normalization (same conventions as the existing `_detect_file_type`).

| Directory | Return value |
|-----------|-------------|
| `brains/` | `"brains"` |
| `behaviours/` | `"behaviours"` |
| `stategraphs/` | `"stategraphs"` |
| `widgets/` | `"widgets"` |
| `screens/` | `"screens"` |
| `prefabs/` | `"prefabs"` |
| `components/` | `"components"` |
| `cameras/` | `"cameras"` |
| `map/`, `languages/`, `util/`, root-level | `"data_config"` |

Unknown directories fall back to `"data_config"`.

---

## Section 2 — Skill Selection

**Changes in `prompts/src/prompts/skills_loader.py`** — two new public functions added, existing API unchanged.

### `few_shot_excludes(lua_type: str) -> list[str]`

Returns exclude list for `combine_skills()` — all 8 few-shot skill names except the one relevant to `lua_type`:

| lua_type | Keep | Exclude (7 others) |
|----------|------|--------------------|
| `"brains"` | `few_shot_brain` | all others |
| `"behaviours"` | `few_shot_behaviour` | all others |
| `"stategraphs"` | `few_shot_stategraph` | all others |
| `"widgets"` | `few_shot_widget` | all others |
| `"screens"` | `few_shot_screen` | all others |
| `"prefabs"` | `few_shot_prefab` | all others |
| `"components"` | `few_shot` | all others |
| `"cameras"` | `few_shot` (fallback) | all others |
| `"data_config"` | `few_shot_data` | all others |

### `load_trimmed_writing_guide(lua_type: str) -> str`

Loads `writing_guide` content from registry, strips all `<!-- type:X -->...<!-- /type -->` blocks except the one matching `lua_type`. For types with no dedicated section (`"cameras"`, `"data_config"`), strips all type blocks.

**Markers added to `writing_guide.md`** (HTML comments, invisible to LLM):
```markdown
<!-- type:brains -->
### Brain Files — Main Functions
...
<!-- /type -->

<!-- type:behaviours -->
### Behaviour Files — Main Functions
...
<!-- /type -->
```
Types covered: `brains`, `behaviours`, `widgets`, `screens`, `prefabs`, `replica`.

### Usage pattern in prompt builders

```python
lua_type = detect_lua_type(display_filepath)
exclude = [*few_shot_excludes(lua_type), "writing_guide"]  # exclude wg to avoid duplicate
skills_block = combine_skills("analyst", exclude=exclude)
skills_block += "\n\n=== SKILL: writing_guide ===\n" + load_trimmed_writing_guide(lua_type)
```

---

## Section 3 — Integration

### `prompts/src/prompts/standard.py`
- Remove `_detect_file_type()` and old `exclude` logic
- Add `lua_type = detect_lua_type(display_filepath)` at top of `build_prompt()`
- Apply new skill selection pattern

### `prompts/src/prompts/chunked.py`
- All prompt-building functions (`build_chunk_prompt`, `build_merge_prompt`, `build_intermediate_prompt`, etc.) receive new `lua_type: str = ""` parameter
- `lua_type` computed once at call site and passed down
- Same skill selection pattern applied

### `prompts/src/prompts/update.py`
- `build_update_prompt()` receives `lua_type: str = ""` parameter
- Same pattern applied

### `core/src/core/main.py`
- Remove `CATEGORY_TYPE = "root"` constant
- Inside the file processing loop: `category_type = detect_lua_type(display_filepath)`
- Pass per-file `category_type` to `build_prompt()` and `process_chunked_file()` as before

### `core/src/core/update/docs.py`
- Replace `get_category_type(lua_rel_path)` with `detect_lua_type()` imported from `prompts.type_detect`
- Delete the old `get_category_type` function

---

## Section 4 — Tests & Backward Compatibility

### New test file: `prompts/tests/test_type_detect.py`

Cases:
- `"./brains/pigbrain.lua"` → `"brains"`
- `"./components/combat.lua"` → `"components"`
- `"./map/something.lua"` → `"data_config"`
- `"achievements.lua"` → `"data_config"` (root-level)
- `"./cameras/followcamera.lua"` → `"cameras"`
- `"./stategraphs/SGBeefalo.lua"` → `"stategraphs"`
- `"./widgets/badge.lua"` → `"widgets"`
- `"./screens/DebugMenuScreen.lua"` → `"screens"`
- `"./prefabs/abigail.lua"` → `"prefabs"`
- `"./behaviours/chaseandattack.lua"` → `"behaviours"`

### Updates to `prompts/tests/test_skills_loader.py`

- `few_shot_excludes("brains")` → contains all few-shots except `"few_shot_brain"`
- `few_shot_excludes("data_config")` → contains all few-shots except `"few_shot_data"`
- `load_trimmed_writing_guide("brains")` → contains Brain section, does NOT contain Behaviour/Widget/Screen/Prefab sections
- `load_trimmed_writing_guide("cameras")` → no type-specific sections

### Backward compatibility

| Item | Action |
|------|--------|
| `_detect_file_type()` in `standard.py` | Deleted (private, not exported) |
| `get_category_type()` in `update/docs.py` | Replaced by `detect_lua_type()` import |
| `combine_skills()`, `load_skill()` APIs | Unchanged |
| `writing_guide.md` | Modified in-place (comment markers added, content unchanged) |
| Existing skill `inject_into` fields | Unchanged |

---

## Files Changed

| File | Change |
|------|--------|
| `prompts/src/prompts/type_detect.py` | **New** |
| `prompts/src/prompts/skills_loader.py` | Add `few_shot_excludes()`, `load_trimmed_writing_guide()` |
| `prompts/src/prompts/standard.py` | Use new type detection + skill selection |
| `prompts/src/prompts/chunked.py` | Add `lua_type` param to all prompt builders |
| `prompts/src/prompts/update.py` | Add `lua_type` param |
| `skills/rules/writing_guide.md` | Add `<!-- type:X -->` markers |
| `core/src/core/main.py` | Per-file `category_type` |
| `core/src/core/update/docs.py` | Replace `get_category_type` with `detect_lua_type` |
| `prompts/tests/test_type_detect.py` | **New** |
| `prompts/tests/test_skills_loader.py` | Add new test cases |

## Token Impact

For a typical brain file (`brains/pigbrain.lua`):
- Before: all 7 irrelevant few-shots included ≈ +21KB
- After: only `few_shot_brain` ≈ +4KB
- `writing_guide` trim: ~4 irrelevant type sections removed ≈ -2KB
- **Net: ~22KB reduction per prompt** (from ~62K to ~40K chars)
