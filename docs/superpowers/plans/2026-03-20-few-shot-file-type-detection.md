# Few-Shot File Type Detection Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Inject the correct few-shot documentation example (component vs data config) into each LLM prompt based on the Lua file's directory, eliminating irrelevant token usage.

**Architecture:** `prompt.py` detects file type from `display_filepath` at call time, loads one of two pre-loaded skill strings (`_FEW_SHOT_COMPONENT` or `_FEW_SHOT_DATA`), and injects it. The skill content lives in two separate files. All 4 skill/prompt file changes land in one atomic commit so there is never a moment without a valid few-shot.

**Tech Stack:** Python 3, existing `skills_loader.load_skill()` API, project-local test runner (`python test_<name>.py`).

---

## Chunk 1: Detection Logic (TDD)

### Task 1: Write failing tests for `_detect_file_type`

**Files:**
- Create: `test_file_type_detection.py`

- [ ] **Step 1: Create the test file**

```python
# test_file_type_detection.py
"""
Tests for _detect_file_type() in prompt.py.
Run: .venv/Scripts/python test_file_type_detection.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

passed = 0
failed = 0

def test(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} -- {msg}")
        failed += 1

from prompt import _detect_file_type

print("=== _detect_file_type ===")

# Root-level files (no subdir) → data_config
test("root ./achievements.lua",     _detect_file_type("./achievements.lua")     == "data_config")
test("root ./actions.lua",          _detect_file_type("./actions.lua")          == "data_config")
test("root no-prefix achievements", _detect_file_type("achievements.lua")       == "data_config")

# map/ tree → data_config
test("map top-level",               _detect_file_type("./map/archive_worldgen.lua") == "data_config")
test("map nested levels/",          _detect_file_type("./map/levels/caves.lua")     == "data_config")
test("map nested tasks/",           _detect_file_type("./map/tasks/caves.lua")      == "data_config")
test("map nested static_layouts/",  _detect_file_type("./map/static_layouts/abandonedboat.lua") == "data_config")

# languages/ and util/ → data_config
test("languages/",                  _detect_file_type("./languages/language.lua") == "data_config")
test("util/",                       _detect_file_type("./util/emoji.lua")          == "data_config")

# Component-like dirs → component
test("components/",                 _detect_file_type("./components/combat.lua")       == "component")
test("brains/",                     _detect_file_type("./brains/abigailbrain.lua")     == "component")
test("prefabs/",                    _detect_file_type("./prefabs/abigail.lua")         == "component")
test("stategraphs/",                _detect_file_type("./stategraphs/SGabigail.lua")   == "component")
test("screens/",                    _detect_file_type("./screens/bigpopupdialog.lua")  == "component")
test("widgets/",                    _detect_file_type("./widgets/animbutton.lua")      == "component")
test("behaviours/",                 _detect_file_type("./behaviours/approach.lua")     == "component")
test("scenarios/",                  _detect_file_type("./scenarios/archive_cookpot.lua") == "component")
test("screens redux/",              _detect_file_type("./screens/redux/achievementspopup.lua") == "component")

# Windows backslash paths
test("backslash components/",       _detect_file_type(".\\components\\combat.lua")   == "component")
test("backslash map/",              _detect_file_type(".\\map\\levels\\caves.lua")   == "data_config")
test("backslash root",              _detect_file_type(".\\achievements.lua")         == "data_config")

print(f"\n{passed} passed, {failed} failed")
if failed:
    sys.exit(1)
```

- [ ] **Step 2: Run tests — expect ImportError (function not defined yet)**

```
.venv/Scripts/python test_file_type_detection.py
```

Expected: `ImportError: cannot import name '_detect_file_type' from 'prompt'`

---

### Task 2: Atomic implementation — all 4 file changes in one commit

**Files:**
- Create:  `skills/few_shot_data.md`
- Modify:  `skills/few_shot.md` (revert to component-only)
- Modify:  `docs_SKILL.md` (register few_shot_data)
- Modify:  `prompt.py` (detection function + conditional load)

> **Critical:** All 4 files must be committed together. Do not commit any subset.

- [ ] **Step 3: Create `skills/few_shot_data.md`**

```markdown
# Skill: few_shot_data

=== FEW-SHOT EXAMPLE (DATA CONFIG FILE) ===
Use this structure when the source file defines a static data table with no constructor. Mirror this format only — do NOT copy the content.

---
id: sampleregistry
title: SampleRegistry
description: A static registry mapping internal names to platform-specific identifiers for all sample entries.
tags: [config, data]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: root
source_hash: abc123
system_scope: world
---

# SampleRegistry

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`sampleregistry.lua` defines a global array-indexed table `SampleRegistry` containing all entries. It uses a helper function `ENTRY(id, name)` to construct records with both a human-readable name and platform-specific identifiers. This file is a configuration source — it is not a component and does not attach to entities; it is required by other systems that need to resolve entry identifiers.

## Usage example
```lua
local SampleRegistry = require "sampleregistry"
-- Access an entry by its array index
local first = SampleRegistry[1]
print(first.name)        -- "entry_alpha"
print(first.id.platform) -- "1_entry_alpha"
print(first.id.numeric)  -- 1
```

## Dependencies & tags
**Components used:** None identified
**Tags:** None identified

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `SampleRegistry` | table | — | Array-indexed global table of record tables; position corresponds to numeric ID order. |
| `name` | string | — | Internal lowercase underscore-separated name used in code (e.g., `"entry_alpha"`). |
| `id.platform` | string | — | Platform string identifier, formatted as `<id>_<name>`. |
| `id.numeric` | number | — | Platform numeric identifier from the platform definition file. |

## Main functions
### `ENTRY(id, name)`
*   **Description:** Factory function that constructs a registry record with platform-specific IDs.
*   **Parameters:**
    *   `id` (string or number) — base identifier; converted to string for the platform string field and kept as number for the numeric field.
    *   `name` (string) — internal name used in code.
*   **Returns:** `{ name = name, id = { platform = tostring(id).."_"..name, numeric = id } }`
*   **Error states:** None.

## Events & listeners
None.
(End of data config example)
```

- [ ] **Step 4: Revert `skills/few_shot.md` to component-only**

Remove everything from line 62 onward (the `(End of component example)` line stays, delete from the blank line after it to end of file). Final file must end with:

```
...
## Events & listeners
- **Listens to:** `onhitother` - refreshes the buff timer on hit.
- **Pushes:** `buff_expired` - fired when the timer reaches zero.
(End of component example)
```

No trailing blank line needed after `(End of component example)`.

- [ ] **Step 5: Register `few_shot_data` in `docs_SKILL.md`**

Append after the existing `## few_shot` block:

```yaml
## few_shot_data
file: skills/few_shot_data.md
inject_into: [single_prompt]
```

- [ ] **Step 6: Update `prompt.py`**

Replace lines 17-18:
```python
_DST_CONV = load_skill("dst_conventions")
_FEW_SHOT = load_skill("few_shot")
```

With:
```python
_DST_CONV           = load_skill("dst_conventions")
_FEW_SHOT_COMPONENT = load_skill("few_shot")
_FEW_SHOT_DATA      = load_skill("few_shot_data")

_DATA_CONFIG_DIRS = {"map", "languages", "util"}


def _detect_file_type(display_filepath: str) -> str:
    """Returns 'component' or 'data_config' based on directory path.

    Detection relies on display_filepath being a relative path (e.g. ./map/a.lua).
    If an absolute path is passed, parts[0] will not match _DATA_CONFIG_DIRS and
    the function safely falls back to 'component'.
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

Then update `build_prompt()` to select the correct few-shot before the `return`. The function body opens directly with `return f"""` at line 39 — insert the local variable between the docstring closing `"""` and the `return`.

**Before** (lines 37-39):
```python
    All config (version, date, tree...) is passed in via parameters.
    """
    return f"""You are an expert technical writer...
```

**After**:
```python
    All config (version, date, tree...) is passed in via parameters.
    """
    _few_shot = (
        _FEW_SHOT_DATA
        if _detect_file_type(display_filepath) == "data_config"
        else _FEW_SHOT_COMPONENT
    )
    return f"""You are an expert technical writer...
```

Also replace `{_FEW_SHOT}` → `{_few_shot}` inside the f-string body (line 153).

- [ ] **Step 7: Run tests — expect all PASS**

```
.venv/Scripts/python test_file_type_detection.py
```

Expected:
```
=== _detect_file_type ===
  [PASS] root ./achievements.lua
  [PASS] root ./actions.lua
  ...
21 passed, 0 failed
```

- [ ] **Step 8: Run existing test suite to verify no regressions**

```
.venv/Scripts/python test_skills_loader.py
.venv/Scripts/python test_chunk_prompts.py
```

Expected: all PASS.

- [ ] **Step 9: Atomic commit — all 4 skill/prompt files together**

```bash
git add skills/few_shot.md skills/few_shot_data.md docs_SKILL.md prompt.py test_file_type_detection.py
git commit -m "feat: conditional few-shot injection by file type

- Add _detect_file_type() to prompt.py: root/map/languages/util → data_config, rest → component
- Extract data config few-shot example to skills/few_shot_data.md
- Revert skills/few_shot.md to component-only
- Register few_shot_data in docs_SKILL.md
- Add test_file_type_detection.py (23 cases)"
```

---

## Chunk 2: Quality Rules Update

### Task 3: Add data config variants to `quality_rules.md`

**Files:**
- Modify: `skills/quality_rules.md`

- [ ] **Step 10: Update OVERVIEW WRITING section**

Find in `skills/quality_rules.md`:
```
OVERVIEW WRITING:
- State: what this component does + its role in the ECS system.
- Mention key relationships with other components (from Connected Files context).
- 2-5 sentences. No padding.
```

Replace with:
```
OVERVIEW WRITING:
- [Component] State: what this component does + its role in the ECS system.
  Mention key relationships with other components (from Connected Files context).
- [Data config] State: what static data this file defines, how it is structured,
  and how other systems access it via require(). Do NOT describe it as a component
  or reference the ECS system.
- 2-5 sentences. No padding.
```

- [ ] **Step 11: Update USAGE EXAMPLE WRITING section**

Find in `skills/quality_rules.md`:
```
USAGE EXAMPLE WRITING:
- Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.
- 5-15 lines. Use the component's actual function names from the documentation.
- No generic placeholder names.
```

Replace with:
```
USAGE EXAMPLE WRITING:
- [Component] Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.
- [Data config] Show `require()` followed by index access to the returned table (e.g., `Table[1]`).
  Do NOT use `CreateEntity()`, `AddComponent`, or `inst.components`.
- 5-15 lines. Use the component's actual function names from the documentation. No generic placeholder names.
```

- [ ] **Step 12: Commit**

```bash
git add skills/quality_rules.md
git commit -m "docs(skills): add data config variants to quality_rules OVERVIEW and USAGE sections"
```

---

## Quick Sanity Check (manual, optional)

After both commits, verify end-to-end by inspecting what `build_prompt()` would inject for two representative files:

```python
# Run in Python REPL inside .venv
from prompt import _detect_file_type, _FEW_SHOT_COMPONENT, _FEW_SHOT_DATA

print(_detect_file_type("./achievements.lua"))       # data_config
print(_detect_file_type("./components/combat.lua"))  # component

# Confirm the right skill is non-empty
assert "SampleRegistry" in _FEW_SHOT_DATA
assert "SampleComp" in _FEW_SHOT_COMPONENT
assert "SampleRegistry" not in _FEW_SHOT_COMPONENT  # no cross-contamination
assert "SampleComp" not in _FEW_SHOT_DATA
print("All assertions passed")
```
