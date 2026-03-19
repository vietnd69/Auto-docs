# Design: Few-Shot File Type Detection

**Date:** 2026-03-20
**Status:** Approved
**Branch:** feat/chunk-pipeline-quality-fixes

---

## Problem

`prompt.py` loads `few_shot.md` once at module import and injects it into every
`build_prompt()` call regardless of file type. The few-shot example is written for
ECS components. When the LLM processes data config files (e.g., `achievements.lua`,
`map/` worldgen files), it receives a component-style example that:

1. Wastes tokens — the example is irrelevant to the output being generated.
2. Misleads the model — it may produce `CreateEntity()` usage examples or describe
   the file as "a component in the ECS system" instead of a static data registry.

`quality_rules.md` has the same issue: two sections (`OVERVIEW WRITING` and
`USAGE EXAMPLE WRITING`) use component-centric language that conflicts with
data config documentation.

---

## File Type Classification

Detection is based on `display_filepath` (already available in `build_prompt()`).

| Directory pattern | Type | Example files |
|---|---|---|
| Root level (no subdir) | `data_config` | `achievements.lua`, `actions.lua` (~217 files) |
| `map/` and all subdirs | `data_config` | `archive_worldgen.lua`, `levels/caves.lua` (~295 files) |
| `languages/` | `data_config` | `language.lua`, `loc.lua` |
| `util/` | `data_config` | `emoji.lua`, `hitbox.lua` |
| Everything else | `component` | `components/`, `brains/`, `prefabs/`, `stategraphs/`, `screens/`, `widgets/`... |

**Total scope:** ~520 data config files, ~3400 component files.

---

## Design

### 1. `skills/few_shot.md` — revert to component-only

Remove the data config example added in the previous session. File returns to its
original state: one example showing a component (timer-based buff).

> **Sequencing:** This step must be done **atomically with Step 4** (conditional
> load in `prompt.py`). Removing the data config content from `few_shot.md` before
> `prompt.py` is updated to load `few_shot_data.md` would leave data config files
> with no relevant few-shot example. Implement Steps 1–4 in a single commit.

### 2. `skills/few_shot_data.md` — new file

Contains exactly one few-shot example demonstrating the expected documentation
output for a data config file: a static global array table with a factory function
(e.g., registry-style file). Mirrors the structure of `few_shot.md` but without
`CreateEntity()`, `AddComponent`, or ECS references.

Key differences from component example:
- `## Overview` describes a static data registry, not an ECS component.
- `## Usage example` shows `require()` + index access (`SampleRegistry[1]`).
- `## Properties` documents both the container table AND individual record fields.
- `## Events & listeners` is `None.`

### 3. `docs_SKILL.md` — register new skill

```yaml
## few_shot_data
file: skills/few_shot_data.md
inject_into: [single_prompt]
```

`inject_into: [single_prompt]` matches `few_shot` for structural consistency.
**Note:** `prompt.py` loads skills by name directly via `load_skill()`, not via
`load_skills_for()`. The `inject_into` field has no runtime effect today — it is
documentary only. The actual injection is wired in Step 4 (`prompt.py`).

### 4. `prompt.py` — detection function + conditional load

**Detection logic:**

```python
_DATA_CONFIG_DIRS = {"map", "languages", "util"}

def _detect_file_type(display_filepath: str) -> str:
    """Returns 'component' or 'data_config' based on directory path."""
    normalized = display_filepath.replace("\\", "/")
    # Use explicit prefix removal (not lstrip which strips char-by-char)
    if normalized.startswith("./"):
        normalized = normalized[2:]
    elif normalized.startswith("/"):
        normalized = normalized.lstrip("/")
    parts = normalized.split("/")
    if len(parts) == 1:
        return "data_config"                          # root-level file
    if parts[0].lower() in _DATA_CONFIG_DIRS:
        return "data_config"
    return "component"                                # default
```

> **Note:** Detection relies on `display_filepath` always being relative (e.g., `./components/combat.lua`). This holds for all current callers (`main.py`, `olm.py`, `validator/fix_format.py`) as long as `BASE_LUA_DIR` in `config.py` produces a path containing `./dst-scripts`. If `LUA_DIR` is ever set to an absolute path that does not contain `./dst-scripts`, the `.replace("./dst-scripts", ".")` in callers will silently produce an absolute path — `parts[0]` will be `"C:"` on Windows or `"home"` on Unix — and all files fall back to `"component"`. This is a known limitation, not a blocker for current use.

**Skill loading:**

```python
# Replace single _FEW_SHOT constant with two typed loads
_FEW_SHOT_COMPONENT = load_skill("few_shot")
_FEW_SHOT_DATA      = load_skill("few_shot_data")
```

**Injection in `build_prompt()`:**

```python
_few_shot = (
    _FEW_SHOT_DATA
    if _detect_file_type(display_filepath) == "data_config"
    else _FEW_SHOT_COMPONENT
)
# inject {_few_shot} in place of {_FEW_SHOT}
```

No changes to `build_prompt()` signature — callers (`main.py`, `olm.py`) are
unaffected.

### 5. `skills/quality_rules.md` — add data config variants

Replace the two component-centric sections with labeled variants. Keep all
universal rules unchanged.

**OVERVIEW WRITING** — add after existing bullet:
```
- [Data config] State: what static data this file defines, how it is structured,
  and how other systems access it via require(). Do NOT describe it as a component
  or reference the ECS system.
```

**USAGE EXAMPLE WRITING** — add after existing bullet:
```
- [Data config] Show require() followed by index or key access to the returned
  table. Do NOT use CreateEntity(), AddComponent, or inst.components.
```

> **Known limitation:** `quality_rules.md` is injected into every prompt regardless
> of file type. The LLM sees both component and data config variants simultaneously
> and must infer which applies from context and the few-shot example. The few-shot
> provides the concrete signal; the labeled variants reinforce it. Conditional
> injection of `quality_rules.md` by file type is deferred (same as `dst_conventions.md`).

No changes to `build_prompt()` signature — callers (`main.py`, `olm.py`,
`validator/fix_format.py`) are unaffected.

---

## Files Changed

| File | Action |
|---|---|
| `skills/few_shot.md` | Revert — remove data config section |
| `skills/few_shot_data.md` | Create — data config few-shot example |
| `docs_SKILL.md` | Update — register `few_shot_data` |
| `prompt.py` | Update — detection function + conditional skill load |
| `skills/quality_rules.md` | Update — labeled variants for 2 sections |

## Files NOT Changed

| File | Reason |
|---|---|
| `skills_loader.py` | No API change needed |
| `chunked_prompt.py` | Data config files are never chunked |
| `skills/function_format.md` | Function format rules are universal |
| `skills/dst_conventions.md` | Known token waste for data config, deferred to future optimization |
| `main.py`, `olm.py`, `validator/fix_format.py` | `build_prompt()` signature unchanged |

---

## Out of Scope

- Conditional injection of `dst_conventions.md` for data config files — valid
  future optimization but requires additional detection plumbing.
- Additional file types beyond `component` and `data_config` (e.g., separate
  few-shots for `stategraph`, `brain`, `prefab`) — not enough quality evidence
  yet to justify the split.
