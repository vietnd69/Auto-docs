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
- Apply to both prompt builders that use type-specific skills: `standard.py` and `chunked.py` (the update pipeline uses `standard.py` and is covered automatically)

## Chosen Approach: Single `detect_lua_type()` + exclude-list

Directory-based detection, with filename-suffix check for `*_replica.lua`. One canonical function replaces two overlapping ones (`_detect_file_type` in `standard.py` and `get_category_type` in `update/docs.py`). Skill files are not modified (except adding HTML comment markers to `writing_guide.md`).

---

## Section 1 — Type Detection

**New file: `prompts/src/prompts/type_detect.py`**

Single public function:

```python
def detect_lua_type(filepath: str) -> str:
    ...
```

Returns one of 10 type strings. Detection order:
1. **Filename suffix check first**: if basename ends with `_replica.lua` → return `"replica"` (regardless of directory)
2. **Directory check**: based on first directory component of the normalized path

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
| unknown directories | `"data_config"` (fallback) |

Handles `./` prefix and backslash normalization (same conventions as the existing `_detect_file_type`).

**Semantic note:** Root-level `.lua` files previously used `category_type = "root"`. The new function returns `"data_config"` for these — a more accurate label since they are static data/config tables, not ECS components.

---

## Section 2 — Skill Selection

**Changes in `prompts/src/prompts/skills_loader.py`** — two new public functions added, existing API unchanged.

### `few_shot_excludes(lua_type: str) -> list[str]`

Returns an exclude list for `combine_skills()` — all 8 few-shot skill names except the one relevant to `lua_type`.

**`replica_pattern` is never excluded** — it is a convention guide (not a few-shot example) that is relevant to all component and replica files. It is not in the `_ALL_FEW_SHOTS` set.

| lua_type | Keep | Exclude (7 others) |
|----------|------|--------------------|
| `"brains"` | `few_shot_brain` | all others |
| `"behaviours"` | `few_shot_behaviour` | all others |
| `"stategraphs"` | `few_shot_stategraph` | all others |
| `"widgets"` | `few_shot_widget` | all others |
| `"screens"` | `few_shot_screen` | all others |
| `"prefabs"` | `few_shot_prefab` | all others |
| `"components"` | `few_shot` | all others |
| `"replica"` | `few_shot` (general component fallback) | all others |
| `"cameras"` | `few_shot` (fallback) | all others |
| `"data_config"` | `few_shot_data` | all others |

The 8 few-shot skill names tracked in `_ALL_FEW_SHOTS`:
`few_shot`, `few_shot_brain`, `few_shot_behaviour`, `few_shot_stategraph`, `few_shot_widget`, `few_shot_screen`, `few_shot_prefab`, `few_shot_data`

### `load_trimmed_writing_guide(lua_type: str) -> str`

Loads `writing_guide` content from registry, strips all `<!-- type:X -->...<!-- /type -->` blocks except the one matching `lua_type`. For types with no dedicated section (`"components"`, `"cameras"`, `"data_config"`), strips all type blocks.

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
Types covered by markers: `brains`, `behaviours`, `widgets`, `screens`, `prefabs`, `replica`.

### Usage pattern in prompt builders

```python
lua_type = detect_lua_type(display_filepath)
exclude = [*few_shot_excludes(lua_type), "writing_guide"]  # exclude wg to avoid duplicate
skills_block = combine_skills("analyst", exclude=exclude)
skills_block += "\n\n=== SKILL: writing_guide ===\n" + load_trimmed_writing_guide(lua_type)
```

`writing_guide` is explicitly excluded from `combine_skills()` then re-injected as the trimmed version. This avoids the full content appearing twice.

---

## Section 3 — Integration

### `prompts/src/prompts/standard.py`
- Remove `_detect_file_type()` and old `exclude` logic
- Add `lua_type = detect_lua_type(display_filepath)` at top of `build_prompt()`
- Apply new skill selection pattern

### `prompts/src/prompts/chunked.py`

Add `lua_type: str = ""` to the following functions and apply skill selection pattern:

| Function | Target | Few-shots that inject | Action |
|----------|--------|----------------------|--------|
| `build_chunk_prompt()` | `analyst_chunk` | all 8 | full `few_shot_excludes` + trimmed `writing_guide` |
| `build_merge_prompt()` | `analyst_merge` | `few_shot_data` only | exclude `few_shot_data` for non-data + trimmed `writing_guide` |
| `build_deps_props_prompt()` | `analyst_merge` | `few_shot_data` only | same |
| `build_functions_batch_prompt()` | `analyst_merge` | `few_shot_data` only | same |
| `build_events_prompt()` | `analyst_merge` | `few_shot_data` only | same |
| `build_prose_prompt()` | `analyst_merge` | `few_shot_data` only | same |
| `_build_merge_prompt_legacy()` | `analyst_merge_legacy` | none | trimmed `writing_guide` only — **currently unreachable** (`hierarchical_merge` is dead code); add `lua_type` param for completeness so it is ready when wired up |

**Not modified:**
- `build_intermediate_merge_prompt()` — uses `analyst_intermediate`; `writing_guide` does NOT inject into this target, and no few-shots inject here. No change needed.
- `rolling_merge_to_one()` — calls `build_intermediate_merge_prompt()` only. No `lua_type` needed.

### `core/src/core/pipeline/chunked.py`

Add `lua_type: str = ""` to the following orchestration functions and thread it down:

- **`process_chunked_file()`** — receives `lua_type` from `main.py`. Two live code paths:
  1. large function count → calls `multipass_merge(lua_type=lua_type)`
  2. small function count → calls `build_merge_prompt(lua_type=lua_type)` directly then `generate_merged_doc()`
- **`multipass_merge()`** — passes `lua_type` to `build_merge_prompt()`, `build_deps_props_prompt()`, `build_functions_batch_prompt()`, `build_events_prompt()`, `build_prose_prompt()`

**Not modified:**
- `rolling_merge_to_one()` — uses `analyst_intermediate` target only. No change needed.
- `hierarchical_merge()` — dead code (not called from `process_chunked_file` or any other live path). Not modified; `_build_merge_prompt_legacy()` is only reachable through it, so that function also remains unchanged for now.

`lua_type` is computed once in `main.py` via `detect_lua_type(display_filepath)` and passed to `process_chunked_file()` alongside the existing `category_type` parameter.

### `prompts/src/prompts/update.py`
No change. `build_update_prompt()` does not use `combine_skills()` and has no skills block. The update pipeline calls `build_prompt()` from `standard.py` directly — fixing `standard.py` covers the update path.

### `core/src/core/main.py`
- Remove `CATEGORY_TYPE = "root"` constant (hardcoded pre-loop)
- Inside the file processing loop: `category_type = detect_lua_type(display_filepath)`
- Pass per-file `category_type` to `build_prompt()` and `process_chunked_file()` as before
- Also pass `lua_type` (same value) down to chunked pipeline

### `core/src/core/update/docs.py`
- Replace `get_category_type(lua_rel_path)` with `detect_lua_type()` imported from `prompts.type_detect`
- Delete the old `get_category_type` function

---

## Section 4 — Tests & Backward Compatibility

### New test file: `prompts/tests/test_type_detect.py`

Cases:
- `"./brains/pigbrain.lua"` → `"brains"`
- `"./components/combat.lua"` → `"components"`
- `"./components/combat_replica.lua"` → `"replica"` (filename suffix wins)
- `"./map/something.lua"` → `"data_config"`
- `"achievements.lua"` → `"data_config"` (root-level)
- `"./cameras/followcamera.lua"` → `"cameras"`
- `"./stategraphs/SGBeefalo.lua"` → `"stategraphs"`
- `"./widgets/badge.lua"` → `"widgets"`
- `"./screens/DebugMenuScreen.lua"` → `"screens"`
- `"./prefabs/abigail.lua"` → `"prefabs"`
- `"./behaviours/chaseandattack.lua"` → `"behaviours"`

### Updates to `prompts/tests/test_skills_loader.py`

- `few_shot_excludes("brains")` → contains all 7 others, does NOT contain `"few_shot_brain"`, does NOT contain `"replica_pattern"`
- `few_shot_excludes("data_config")` → contains all 7 others, does NOT contain `"few_shot_data"`
- `few_shot_excludes("replica")` → contains all 7 others, does NOT contain `"few_shot"` (general kept)
- `load_trimmed_writing_guide("brains")` → contains Brain section, does NOT contain Behaviour/Widget/Screen/Prefab/Replica sections
- `load_trimmed_writing_guide("replica")` → contains Replica section only
- `load_trimmed_writing_guide("cameras")` → no type-specific sections

### Backward compatibility

| Item | Action |
|------|--------|
| `_detect_file_type()` in `standard.py` | Deleted (private, not exported) |
| `get_category_type()` in `update/docs.py` | Replaced by `detect_lua_type()` import |
| `combine_skills()`, `load_skill()` APIs | Unchanged |
| `writing_guide.md` | Modified in-place (comment markers added, content unchanged) |
| Existing skill `inject_into` fields | Unchanged |
| `category_type` for root-level files | Changes from `"root"` to `"data_config"` (semantic improvement) |

---

## Files Changed

| File | Change |
|------|--------|
| `prompts/src/prompts/type_detect.py` | **New** |
| `prompts/src/prompts/skills_loader.py` | Add `few_shot_excludes()`, `load_trimmed_writing_guide()` |
| `prompts/src/prompts/standard.py` | Use new type detection + skill selection |
| `prompts/src/prompts/chunked.py` | Add `lua_type` param to 7 prompt-building functions (not `build_intermediate_merge_prompt`) |
| `core/src/core/pipeline/chunked.py` | Add `lua_type` param to `process_chunked_file`, `multipass_merge`, `hierarchical_merge` |
| `skills/rules/writing_guide.md` | Add `<!-- type:X -->` markers |
| `core/src/core/main.py` | Per-file `category_type` + pass `lua_type` to chunked pipeline |
| `core/src/core/update/docs.py` | Replace `get_category_type` with `detect_lua_type` |
| `prompts/tests/test_type_detect.py` | **New** |
| `prompts/tests/test_skills_loader.py` | Add new test cases |

## Token Impact

For a typical brain file (`brains/pigbrain.lua`):
- Before: all 7 irrelevant few-shots included ≈ +21KB
- After: only `few_shot_brain` ≈ +4KB
- `writing_guide` trim: ~4 irrelevant type sections removed ≈ -2KB
- **Net: ~22KB reduction per prompt** (from ~62K to ~40K chars)
