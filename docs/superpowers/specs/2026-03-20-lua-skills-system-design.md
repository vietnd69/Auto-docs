# Lua Skills System — Design Spec

**Date:** 2026-03-20
**Branch:** feat/chunk-pipeline-quality-fixes
**Status:** Approved

---

## Overview

Extract hardcoded domain knowledge from `prompt.py` and `chunked_prompt.py` into reusable Markdown skill files. A Python loader reads `docs_SKILL.md` as an index, loads the right skill content, and injects it into LLM prompts via module-level variables (load-once at import time, no per-call I/O).

**Goal:** Single source of truth for DST conventions, function format spec, quality rules, and few-shot examples — edit one `.md` file, all prompts update.

---

## File Structure

```
d:\code\mod-document\
├── docs_SKILL.md              # skill registry — YAML frontmatter + ## section per skill
├── skills_loader.py           # parse index, load .md content by name or prompt target
└── skills\
    ├── dst_conventions.md     # DST ECS, events, tags, network, stategraphs, brains, prefabs (enriched)
    ├── function_format.md     # function & dependency format spec (verbatim _FUNCTION_FORMAT_SPEC)
    ├── quality_rules.md       # critical documentation rules + MDX compat (enriched)
    └── few_shot.md            # SampleComp full-document few-shot example (from prompt.py only)
```

`docs_SKILL.md` sits at the project root. All `file:` paths in it are relative to the project root.
`skills/` is a subdirectory of the project root (same level as `docs_SKILL.md`).

---

## docs_SKILL.md — Index Format

Complete example (all 4 skills):

```markdown
---
version: 1
---
## dst_conventions
file: skills/dst_conventions.md
inject_into: [chunk_prompt, merge_prompt, single_prompt]

## function_format
file: skills/function_format.md
inject_into: [merge_prompt, single_prompt]

## quality_rules
file: skills/quality_rules.md
inject_into: [merge_prompt, single_prompt]

## few_shot
file: skills/few_shot.md
inject_into: [single_prompt]
```

**Parsing strategy:**
1. Split the entire file on `\n## ` to get the YAML preamble + per-skill blocks
2. Parse the preamble with PyYAML to get `version`
3. For each skill block: first line is the skill name; remaining lines are parsed as YAML key-value pairs (`file:` and `inject_into:`)
4. `inject_into` is always a YAML inline list `[a, b, c]`
5. Each skill section is independent — no nesting, no shared YAML context between sections

**Parsing rules:**
- YAML frontmatter block (between `---` delimiters) for document-level metadata
- Each `## <skill_name>` heading starts a new skill entry
- `file:` — path to skill Markdown file, relative to project root
- `inject_into:` — YAML inline list of target identifiers (see allowed values below)
- Parse with `str.split` on `## ` headings + PyYAML for YAML blocks; no regex
- All files opened with `encoding="utf-8"`

**Allowed `inject_into` values:**

| Value | Prompt function |
|---|---|
| `chunk_prompt` | `build_chunk_prompt()` in `chunked_prompt.py` |
| `merge_prompt` | `build_merge_prompt()` in `chunked_prompt.py` |
| `single_prompt` | `build_prompt()` in `prompt.py` |

`_build_merge_prompt_legacy()` and `build_intermediate_merge_prompt()` are **not** inject targets — see Excluded Functions section below.

---

## skills_loader.py — API

```python
def load_skill(name: str, *, index_path: str = "docs_SKILL.md") -> str:
    """Load a single skill by name. Returns raw markdown content (utf-8)."""

def load_skills_for(target: str, *, index_path: str = "docs_SKILL.md") -> dict[str, str]:
    """Return {name: content} for all skills whose inject_into includes target."""
```

**Error behavior (raised at call time, not import time):**
- `KeyError("Skill 'unknown' not found in docs_SKILL.md")` — name not in index
- `FileNotFoundError("Skill file 'skills/X.md' not found")` — `.md` file missing
- `ValueError("Skill 'X' in index missing 'file:' field")` — malformed index entry

Errors are raised inside `load_skill()` / `load_skills_for()` at call time. Because prompt files call these at **module scope** (see below), errors surface at import time and prevent the application from starting — this is the intended behavior (fail fast on misconfigured skills).

---

## Skill File Contents

### `skills/dst_conventions.md`

Extract current 6-line DST conventions block present in all three target f-strings, enriched with:
- Scheduler/coroutines: `DoTaskInTime`, `DoPeriodicTask`, `StartThread`, `Sleep`
- Stategraph: `StateGraph`, `State`, `EventHandler`, `TimeEvent`
- Brain/AI: `Brain`, `BehaviourNode`, `SequenceNode`, `SelectorNode`, `RunBrain`
- Prefab system: `Prefabs`, `SpawnPrefab`, `CreateEntity`, physics helpers
- Network: `net_bool`, `net_int`, `net_float`, `SendRPCToServer`, `ismastersim`
- Globals: `TUNING`, `STRINGS`, `ACTIONS`, `BufferedAction`, `TheSim`, `TheInput`

No frontmatter. Header line: `# Skill: dst_conventions`. Followed by plain Markdown.

### `skills/function_format.md`

**Verbatim copy** of `_FUNCTION_FORMAT_SPEC` from `chunked_prompt.py` (lines 19–67).
This includes its own `=== FEW-SHOT EXAMPLE ===` block (ConsoleCommandPlayer / c_spawn / c_save) — that block illustrates function-entry format only and is part of this skill, not `few_shot.md`.
Header: `# Skill: function_format`.

### `skills/quality_rules.md`

Extract **all** `=== CRITICAL INSTRUCTIONS ===` bullets from both prompt files (they are identical) and enrich with:
- Overview writing guidance (component purpose + ECS context + key relationships)
- Usage example guidelines (realistic Lua, show `AddComponent` + primary functions)
- Incomplete function handling (chunk boundary cuts: keep with note)
- Properties table rules (empty JSON → header row only, no invented rows)

Header: `# Skill: quality_rules`.

### `skills/few_shot.md`

**Verbatim copy** of the `SampleComp` complete document example from `prompt.py` (lines 154–212). This illustrates full document output format. Header: `# Skill: few_shot`.

**Distinction from `function_format.md`:** `few_shot.md` = full doc example; `function_format.md` = function-entry format example. Two separate skills, two separate inject targets.

---

## Prompt Integration

### Module-level variable pattern

Both prompt files use this pattern (load at module scope = effectively once per process):

```python
from skills_loader import load_skill

_DST_CONV  = load_skill("dst_conventions")   # module-level variable
_FUNC_FMT  = load_skill("function_format")   # module-level variable
```

Inside f-strings these are referenced as `{_DST_CONV}`, `{_FUNC_FMT}`, etc.

### `chunked_prompt.py` changes

1. Add imports after existing imports:
   ```python
   from skills_loader import load_skill
   _FUNCTION_FORMAT_SPEC = load_skill("function_format")  # replaces inline constant; same name preserved for test compat
   _DST_CONV             = load_skill("dst_conventions")
   ```

2. **Remove** inline `_FUNCTION_FORMAT_SPEC` constant definition (lines 19–67).

3. **Replace** the 6-line DST conventions block in **3 functions**:
   - `build_chunk_prompt()` (line ~184)
   - `build_merge_prompt()` (line ~323)
   - `_build_merge_prompt_legacy()` (line ~479)

   Replace pattern (in each f-string):
   ```
   # Before:
   5. DST CODING CONVENTIONS
      - DST uses an Entity Component System...
      ...6 bullet lines...

   # After:
   5. DST CODING CONVENTIONS
   {_DST_CONV}
   ```

### `prompt.py` changes

1. Add imports after existing imports:
   ```python
   from skills_loader import load_skill
   _DST_CONV = load_skill("dst_conventions")
   _FEW_SHOT = load_skill("few_shot")
   ```

2. Replace the 6-line DST conventions block in `build_prompt()` f-string (lines ~62–68) → `{_DST_CONV}`.

3. Replace `=== FEW-SHOT EXAMPLE ===` block in `build_prompt()` f-string (lines ~154–212) → `{_FEW_SHOT}`.

---

## Excluded Functions (explicitly out of scope)

| Function | Reason |
|---|---|
| `build_intermediate_merge_prompt()` | Does not contain DST conventions block — no change needed |
| `_build_merge_prompt_legacy()` | **Is in scope** — contains DST conventions block, gets the same replacement as the other two |

Note: `_build_merge_prompt_legacy` IS one of the 3 target f-strings; it is **not** excluded.

**Existing TODO comment:** `chunked_prompt.py` line 430 has a `# TODO(format-consistency): apply _FUNCTION_FORMAT_SPEC here when legacy path is retired` comment. That TODO refers to applying `_FUNCTION_FORMAT_SPEC` to the legacy prompt's function section — a separate concern from the DST conventions block. The DST conventions replacement in `_build_merge_prompt_legacy` is in scope and the TODO comment should be left as-is (it still tracks the unrelated `_FUNCTION_FORMAT_SPEC` injection into that legacy path).

---

## Affected Callers (no behavior change, verify no regression)

| File | How affected |
|---|---|
| `test_chunk_prompts.py` | Imports `_FUNCTION_FORMAT_SPEC` from `chunked_prompt` — preserved as module-level var, test continues to pass |
| `validator/fix_format.py` | Calls `build_prompt()` — function signature unchanged, behavior identical |
| `chunked_olm.py` | Calls all four chunked functions — no signature changes |

---

## Data Flow

```
docs_SKILL.md (index)
       │
       ▼ (parse at load_skill() call, called at module import)
skills_loader.py  ──reads (utf-8)──▶  skills/*.md
       │
       ▼
chunked_prompt.py  module vars: _FUNCTION_FORMAT_SPEC, _DST_CONV
prompt.py          module vars: _DST_CONV, _FEW_SHOT
       │
       ▼
f-string prompt → Ollama LLM API
```

---

## Out of Scope

- Hot-reload of skills at runtime
- Skill versioning / rollback
- Per-skill token counting
- New skills beyond the 4 listed above
- Changing `build_intermediate_merge_prompt()` or `_build_merge_prompt_legacy()` (except DST block replacement in legacy)
