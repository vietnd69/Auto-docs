# Skills Restructure Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Restructure the `skills/` directory to fix injection mismatches, content contradictions, and structural issues described in the design spec.

**Architecture:** Self-describing YAML frontmatter skills organized into `roles/`, `knowledge/`, `rules/` subdirectories. A rewritten `skills_loader.py` with `combine_skills()` API concatenates matching skills per target. Prompt builders become thin templates consuming the combined skill block.

**Tech Stack:** Python 3.11 (uv workspace, `.venv/Scripts/python`), Markdown skill files with YAML frontmatter

**Spec:** `docs/superpowers/specs/2026-04-06-skills-restructure-design.md`

---

## Quick reference — new skill files

| File | `name` | `inject_into` | Source |
|------|---------|----------------|--------|
| `roles/analyst.md` | `analyst` | `analyst, analyst_chunk, analyst_merge, analyst_intermediate, analyst_merge_legacy` | New (from inline prompts) |
| `roles/validator_reviewer.md` | `validator_reviewer` | `reviewer_full, reviewer_typed` | Moved + frontmatter |
| `roles/validator_writer.md` | `validator_writer` | `writer_full, writer_typed` | Moved + frontmatter |
| `roles/validator_jury.md` | `validator_jury` | `jury` | Moved + frontmatter |
| `knowledge/dst_conventions.md` | `dst_conventions` | `analyst, analyst_chunk, analyst_merge, analyst_intermediate, analyst_merge_legacy, reviewer_full, reviewer_typed` | Moved + frontmatter |
| `knowledge/function_format.md` | `function_format` | `analyst, analyst_merge, analyst_merge_legacy` | Moved + frontmatter |
| `knowledge/few_shot.md` | `few_shot` | `analyst` | Moved + frontmatter + fix |
| `knowledge/few_shot_data.md` | `few_shot_data` | `analyst, analyst_merge` | Moved + frontmatter |
| `rules/format_rules.md` | `format_rules` | `analyst, analyst_merge, analyst_merge_legacy` | New (from quality_rules + inline) |
| `rules/content_rules.md` | `content_rules` | `analyst, analyst_chunk, analyst_merge, analyst_intermediate, analyst_merge_legacy, reviewer_full, reviewer_typed` | New (from quality_rules) |
| `rules/writing_guide.md` | `writing_guide` | `analyst, analyst_merge, analyst_merge_legacy` | New (from quality_rules + inline) |

---

## Chunk 1: Phase 1 — Loader Rewrite

Add the new `combine_skills()` API alongside the existing old-format code. Old functions remain unchanged so existing tests pass. The new API uses a module-level registry that auto-detects format: if `skills/roles/` exists → scan subdirs with YAML frontmatter, else → bridge from `docs_SKILL.md`.

### Task 1: Add new loader API to skills_loader.py

**Files:**
- Modify: `prompts/src/prompts/skills_loader.py`

- [ ] **Step 1: Read current file and confirm baseline**

Run: `.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v`
Expected: All 8 existing tests pass.

- [ ] **Step 2: Append new functions after existing code**

Add the following code at the END of `prompts/src/prompts/skills_loader.py`, after the existing `load_skills_for()` function. Do NOT modify any existing functions.

```python
# ── New API (Phase 1) ────────────────────────────────────────────────────────

import logging as _logging

_log = _logging.getLogger(__name__)
_SKILLS_DIR = _Path(__file__).parents[3] / "skills"
_GROUP_ORDER = {"roles": 0, "knowledge": 1, "rules": 2}

# Module-level cache — populated on first call to _get_registry()
_registry: dict | None = None


def _parse_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from a skill .md file."""
    import yaml

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"Skill file {path} missing YAML frontmatter")

    end = text.index("---", 3)
    fm = yaml.safe_load(text[3:end].strip()) or {}

    if "name" not in fm:
        raise ValueError(f"Skill file {path} missing 'name' in frontmatter")
    if "inject_into" not in fm:
        raise ValueError(f"Skill file {path} missing 'inject_into' in frontmatter")

    # Extract body: strip frontmatter block + optional "# Title" header line
    body = text[end + 3:].lstrip("\n")
    lines = body.split("\n", 1)
    if lines and lines[0].startswith("# "):
        body = lines[1].lstrip("\n") if len(lines) > 1 else ""

    group_name = path.parent.name
    group = _GROUP_ORDER.get(group_name)
    if group is None:
        raise ValueError(
            f"Skill file {path} in unknown subdirectory '{group_name}'"
        )

    inject = fm["inject_into"]
    if not isinstance(inject, list):
        inject = [inject]

    return {
        "name": fm["name"],
        "description": fm.get("description", ""),
        "inject_into": inject,
        "content": body,
        "group": group,
        "path": str(path),
    }


def _build_registry_new() -> dict[str, dict]:
    """Scan skills/ subdirectories and build {name: entry} registry."""
    registry: dict[str, dict] = {}
    for subdir in ("roles", "knowledge", "rules"):
        dir_path = _SKILLS_DIR / subdir
        if not dir_path.is_dir():
            continue
        for md_file in sorted(dir_path.glob("*.md")):
            entry = _parse_frontmatter(md_file)
            name = entry["name"]
            if name in registry:
                raise ValueError(
                    f"Duplicate skill name '{name}': {entry['path']} and {registry[name]['path']}"
                )
            registry[name] = entry
    return registry


def _build_registry_legacy() -> dict[str, dict]:
    """Bridge: build registry from old-format docs_SKILL.md."""
    index_path = str(_SKILLS_DIR / "docs_SKILL.md")
    index = _parse_index(index_path)
    root = _SKILLS_DIR
    registry: dict[str, dict] = {}
    for name, entry in index.items():
        file_path = root / entry["file"]
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n", 1)
        if lines[0].startswith("# Skill:"):
            content = lines[1].lstrip("\n") if len(lines) > 1 else ""
        registry[name] = {
            "name": name,
            "description": "",
            "inject_into": entry.get("inject_into", []),
            "content": content,
            "group": 1,  # default: knowledge group
            "path": str(file_path),
        }
    return registry


def _get_registry(*, _override: dict | None = None) -> dict[str, dict]:
    """Return the skill registry, building on first call."""
    if _override is not None:
        return _override
    global _registry
    if _registry is None:
        if (_SKILLS_DIR / "roles").is_dir():
            _registry = _build_registry_new()
        else:
            _registry = _build_registry_legacy()
    return _registry


def _clear_cache() -> None:
    """Reset module-level registry cache. Call in test teardown."""
    global _registry
    _registry = None


def combine_skills(
    target: str,
    *,
    exclude: list[str] | None = None,
    _registry_override: dict | None = None,
) -> str:
    """Concatenate all skills matching target into a single string.

    Order: role (group 0) → knowledge (group 1) → rules (group 2).
    Within each group, sorted alphabetically by name.
    Separator: ``=== SKILL: {name} ===\\n`` prefix per block.
    """
    reg = _get_registry(_override=_registry_override)
    exclude_set = set(exclude) if exclude else set()

    matches = [
        e for e in reg.values()
        if target in e["inject_into"] and e["name"] not in exclude_set
    ]

    if not matches:
        _log.warning(
            "combine_skills(%r) matched 0 skills — possible typo in target name",
            target,
        )
        return ""

    matches.sort(key=lambda e: (e["group"], e["name"]))
    parts = []
    for entry in matches:
        parts.append(f"=== SKILL: {entry['name']} ===\n{entry['content']}")
    return "\n\n".join(parts)
```

- [ ] **Step 3: Run existing tests — verify no regression**

Run: `.venv/Scripts/pytest prompts/tests/test_skills_loader.py -v`
Expected: All 8 existing tests still pass (old functions are untouched).

- [ ] **Step 4: Commit**

```bash
git add prompts/src/prompts/skills_loader.py
git commit -m "feat(skills): add combine_skills() API with dual-format bridge"
```

### Task 2: Update __init__.py re-exports

**Files:**
- Modify: `prompts/src/prompts/__init__.py`

- [ ] **Step 1: Add combine_skills to re-exports**

Change line 1 of `prompts/src/prompts/__init__.py` from:
```python
from prompts.skills_loader import load_skill, load_skills_for
```
to:
```python
from prompts.skills_loader import load_skill, load_skills_for, combine_skills
```

- [ ] **Step 2: Verify import works**

Run: `.venv/Scripts/python -c "from prompts import combine_skills; print('OK')"`
Expected: prints `OK`.

- [ ] **Step 3: Commit**

```bash
git add prompts/src/prompts/__init__.py
git commit -m "feat(skills): export combine_skills from prompts package"
```

### Task 3: Write tests for new loader API

**Files:**
- Modify: `prompts/tests/test_skills_loader.py`

- [ ] **Step 1: Add new test functions at the end of the file**

Append these test functions BEFORE the `if __name__ == "__main__"` block in `prompts/tests/test_skills_loader.py`:

```python
# ── combine_skills tests (new API, uses _registry_override) ──────────────────

def run_combine_skills_tests():
    from prompts.skills_loader import combine_skills, _clear_cache

    # Build a mock registry for testing (no filesystem needed)
    mock_registry = {
        "analyst": {
            "name": "analyst",
            "inject_into": ["analyst", "analyst_chunk"],
            "content": "role content",
            "group": 0,
            "path": "roles/analyst.md",
        },
        "dst_conventions": {
            "name": "dst_conventions",
            "inject_into": ["analyst", "analyst_chunk"],
            "content": "knowledge content",
            "group": 1,
            "path": "knowledge/dst_conventions.md",
        },
        "function_format": {
            "name": "function_format",
            "inject_into": ["analyst"],
            "content": "format content",
            "group": 1,
            "path": "knowledge/function_format.md",
        },
        "content_rules": {
            "name": "content_rules",
            "inject_into": ["analyst", "analyst_chunk"],
            "content": "rules content",
            "group": 2,
            "path": "rules/content_rules.md",
        },
        "format_rules": {
            "name": "format_rules",
            "inject_into": ["analyst"],
            "content": "format rules content",
            "group": 2,
            "path": "rules/format_rules.md",
        },
    }

    # T9: combine_skills returns concatenated content in group order
    result = combine_skills("analyst", _registry_override=mock_registry)
    check("combine_skills group order: role → knowledge → rules",
          result.startswith("=== SKILL: analyst ==="),
          f"got: {result[:60]!r}")

    # T10: within-group alphabetical ordering
    check("combine_skills alphabetical within knowledge group",
          result.index("dst_conventions") < result.index("function_format"),
          "dst_conventions should come before function_format")

    check("combine_skills alphabetical within rules group",
          result.index("content_rules") < result.index("format_rules"),
          "content_rules should come before format_rules")

    # T11: exclude parameter works
    result_excl = combine_skills("analyst", exclude=["function_format"], _registry_override=mock_registry)
    check("combine_skills exclude removes skill",
          "function_format" not in result_excl and "dst_conventions" in result_excl,
          f"got: {result_excl[:80]!r}")

    # T12: unknown target returns empty string (not error)
    result_empty = combine_skills("nonexistent_target", _registry_override=mock_registry)
    check("combine_skills unknown target returns empty string",
          result_empty == "",
          f"got: {result_empty!r}")

    # T13: exclude with unknown name is silently ignored
    result_unk = combine_skills("analyst", exclude=["no_such_skill"], _registry_override=mock_registry)
    check("combine_skills exclude unknown name silently ignored",
          "analyst" in result_unk,
          "should still return results")

    # T14: separator format is correct
    check("combine_skills separator format",
          "=== SKILL: analyst ===" in result and "=== SKILL: dst_conventions ===" in result,
          "separator markers missing")

    # T15: content is included after separator
    idx = result.index("=== SKILL: analyst ===")
    after_sep = result[idx:idx+40]
    check("combine_skills content after separator",
          "role content" in after_sep,
          f"got: {after_sep!r}")

    # T16: _clear_cache resets module state
    _clear_cache()
    check("_clear_cache runs without error", True)
```

- [ ] **Step 2: Update the entry point to include new tests**

Replace the `if __name__ == "__main__"` block with:

```python
if __name__ == "__main__":
    print("\n=== load_skill tests ===")
    run_load_skill_tests()
    print("\n=== load_skills_for tests ===")
    run_load_skills_for_tests()
    print("\n=== combine_skills tests ===")
    run_combine_skills_tests()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 3: Run the updated tests**

Run: `.venv/Scripts/python prompts/tests/test_skills_loader.py`
Expected: All 16 tests pass (8 old + 8 new).

- [ ] **Step 4: Commit**

```bash
git add prompts/tests/test_skills_loader.py
git commit -m "test(skills): add tests for combine_skills() API"
```

---

## Chunk 2: Phase 2 — File Restructure

Create the new directory structure, write new skill files, move existing skills with YAML frontmatter, delete old files, and remove the old-format code path from the loader.

### Task 4: Create directory structure

**Files:**
- Create: `skills/roles/`, `skills/knowledge/`, `skills/rules/`

- [ ] **Step 1: Create subdirectories**

```bash
mkdir -p skills/roles skills/knowledge skills/rules
```

- [ ] **Step 2: Verify**

```bash
ls skills/
```
Expected: `roles/  knowledge/  rules/` directories plus existing `.md` files.

### Task 5: Create new rule files

**Files:**
- Create: `skills/rules/format_rules.md`
- Create: `skills/rules/content_rules.md`
- Create: `skills/rules/writing_guide.md`

- [ ] **Step 1: Create `skills/rules/format_rules.md`**

```markdown
---
name: format_rules
description: MDX compatibility, section order, YAML frontmatter, heading rules for generated documentation
inject_into: [analyst, analyst_merge, analyst_merge_legacy]
---

# Format Rules

=== DOCUMENTATION FORMAT RULES ===

SECTION ORDER (never change):
  ## Overview -> ## Usage example -> ## Dependencies & tags -> ## Properties -> ## Main functions -> ## Events & listeners
  Do NOT omit, reorder, or rename these sections.

OUTPUT FORMAT:
- Output ONLY valid Markdown starting with `---` (YAML frontmatter opening delimiter).
- Generate exactly ONE frontmatter block. No extra `---` dividers in the document body.
- No code fences around the entire output.

YAML FRONTMATTER:
- `description`: One real English sentence. Never leave placeholder text.
- `tags`: 2-5 lowercase domain keywords (e.g., [combat, ai, boss]). Not entity tags.
- `system_scope`: One of: world, player, entity, ui, audio, combat, environment, inventory,
  crafting, network, brain, locomotion, physics, fx. Pick the most accurate.
- `last_updated`, `build_version`, `change_status`, `category_type`, `source_hash`: copy exactly.
- Do NOT leave any `[]`, `<>`, or the words "automatically generated" in the YAML.
- The YAML frontmatter block MUST start with exactly `---` on its own line and end with exactly `---` on its own line. Do NOT omit or duplicate these delimiters.

MDX COMPATIBILITY (Docusaurus fails on bare JSX tokens):
- Wrap in backticks: `<`, `>`, `<=`, `>=`, `{{`, `}}`
- Example: write `value <= 0` not value <= 0 in prose.
- Never leave bare angle brackets or curly braces in plain text.
- Do NOT use unescaped `{{` or `}}` in regular prose.

HEADING RULES:
- Sentence case: "Main functions" not "Main Functions". Proper nouns/acronyms stay capitalized.
- Never skip heading levels. `###` only under `##`. No `####` unless absolutely necessary.

NO CODE FENCES AROUND OUTPUT: Do NOT wrap the entire output in a markdown code fence (```).
NO EMOJIS OR UNICODE SYMBOLS: Do NOT use icons or special characters. Use plain text only.
```

- [ ] **Step 2: Create `skills/rules/content_rules.md`**

```markdown
---
name: content_rules
description: Content accuracy, completeness, file type classification, properties table rules
inject_into: [analyst, analyst_chunk, analyst_merge, analyst_intermediate, analyst_merge_legacy, reviewer_full, reviewer_typed]
---

# Content Rules

=== CONTENT ACCURACY RULES ===

CONTENT RULES:
- All content must come ONLY from the source code or provided JSON. Do NOT invent APIs.
- Never repeat the same line or bullet point more than once.
- No greetings, sign-offs, meta-commentary, or filler text.
- No emojis or unicode symbols.

FILE TYPE CLASSIFICATION (determine before writing any section):
- DATA CONFIG FILE: no Class() constructor, no self.inst, returns a plain table/array.
  → MUST apply ALL [Data config] rules. Do NOT use [Component] patterns.
  → Consult the HOW TO DETECT note at the top of the data config few-shot example.
- COMPONENT FILE: has Class(function(self, ...) ... end) constructor.
  → MUST apply ALL [Component] rules. Do NOT use [Data config] patterns.
When signals are mixed (e.g., local helper functions that resemble constructors),
check: does the file's top-level return value contain a plain array/table, not a class instance?
If yes → DATA CONFIG FILE.

COMPLETENESS:
- Keep ALL functions — never drop trivial getters/setters.
- If a function appears in multiple chunks, prefer the entry with more parameter/return detail.
- Merge all events, dependencies, and tags; never drop an entry.
- If a field has no data, use "None" (string) or [] (empty array) — never omit the field.

SHORT FILES:
- If source is small or simple, keep docs proportionally short.
- If a section has no content, write "Not applicable" or "None identified" — do not invent.
- Events & listeners may be omitted if the component has none.

PROPERTIES TABLE:
- Columns: Property | Type | Default Value | Description
- If no properties exist, the table MUST include a None data row:
  | None | | | No properties are defined. |
  Do NOT leave the table with header + separator only and no data rows — that is incorrect.
- Do NOT invent properties not in the constructor.

DATA CONFIG FILE PROPERTIES:
MUST document TWO groups of rows in this order:
  1. The top-level container variable (the returned global/local table).
  2. One row per key in each record entry (e.g., name, id.steam, id.psn).
NEVER document only the container and omit the record schema.
NEVER use a real default value for record fields — always write "—" (em dash).
NEVER write "nil" as a default — that is a real default value. Use "—" only.
Nested table fields accessed via dot notation (id.steam, id.psn) MUST each be
their own property row. Never collapse them into a single parent row (e.g., id).

DATA CONFIG FILE MAIN FUNCTIONS:
Local factory/builder functions that construct record entries (e.g., ACHIEVEMENT(),
ENTRY()) MUST be documented in ## Main functions — they define the record schema
and are part of the data API. Do NOT treat them as internal implementation details
or skip them because they are local.

INCOMPLETE FUNCTION HANDLING (chunk boundary):
- If a function body is cut off at chunk boundary, keep it and note "INCOMPLETE — continues in adjacent chunk".
- Do NOT skip or drop incomplete functions.
```

- [ ] **Step 3: Create `skills/rules/writing_guide.md`**

```markdown
---
name: writing_guide
description: How to write each documentation section — overview, usage examples, constructor rule, section-specific guidance
inject_into: [analyst, analyst_merge, analyst_merge_legacy]
---

# Writing Guide

=== DOCUMENTATION WRITING GUIDE ===

CONSTRUCTOR RULE:
- Document `Class(function(self, ...) ... end)` constructors accordingly.
- The first parameter after `self` may be `inst`, `data`, or any other name — document as-is.

OVERVIEW WRITING:
- [Component] State: what this component does + its role in the ECS system.
  Mention key relationships with other components (from Connected Files context).
- [Data config] State: what static data this file defines, how it is structured,
  and how other systems access it via require(). Do NOT describe it as a component
  or reference the ECS system.
- 2-5 sentences. No padding.

USAGE EXAMPLE WRITING:
- [Component] Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.
- [Data config] Show `require()` followed by index access to the returned table (e.g., `Table[1]`).
  Do NOT use `CreateEntity()`, `AddComponent`, or `inst.components`.
- 5-15 lines. Use a fenced code block with `lua` syntax highlighting.
- Use the component's actual function names from the documentation. No generic placeholder names.

DEPENDENCIES & TAGS SECTION:
- **Components used:** List components accessed via `inst.components.X` or added via `inst:AddComponent("X")`.
- **Tags:** List any tags this component adds, removes, or checks (e.g., `inst:AddTag("tag")`).
- If none are apparent, write "None identified."

PROPERTIES SECTION:
- Create a Markdown table of key public variables/properties initialized in the constructor.
- Columns: `Property` | `Type` (infer if possible) | `Default Value` | `Description`.
- If no suitable properties, write "No public properties" instead of inventing content.

MAIN FUNCTIONS SECTION:
- Document the core functional methods using the format defined in the function_format skill.
- For each function: Description, Parameters, Returns, Error states.
- Error states = crash or silent state corruption only. NOT normal conditional returns.

EVENTS & LISTENERS SECTION:
- **Listens to:** Events registered via `inst:ListenForEvent(event, fn)`.
- **Pushes:** Events fired via `inst:PushEvent(event, data)`.
- If there are no events or listeners, omit this entire section.
```

- [ ] **Step 4: Commit**

```bash
git add skills/rules/
git commit -m "feat(skills): create format_rules, content_rules, writing_guide rule files"
```

### Task 6: Create analyst role

**Files:**
- Create: `skills/roles/analyst.md`

- [ ] **Step 1: Create `skills/roles/analyst.md`**

```markdown
---
name: analyst
description: Role definition for first-time documentation generation — analyzes Lua source to produce API reference
inject_into: [analyst, analyst_chunk, analyst_merge, analyst_intermediate, analyst_merge_legacy]
---

# Analyst Role

=== ROLE ===
You are an expert technical writer and a veteran mod developer for the game Don't Starve Together (DST).
Your task is to analyze the Lua source file provided and generate comprehensive, highly readable API reference documentation for modders and developers.
All documentation text must be written in clear, concise English.

=== INPUT ANALYSIS ===

1. IDENTIFY FILE TYPE by structure:
   - Has `Class(function(self, ...) ... end)` constructor → COMPONENT FILE
   - Returns a plain table/array, no Class() → DATA CONFIG FILE
   This classification determines which writing rules apply throughout.

2. TRACE DEPENDENCIES:
   - `require("path")` — external module imports
   - `inst.components.X:FuncName()` — component method calls
   - `inst:AddComponent("X")` — component additions
   Use the Connected Files context to understand external API signatures.

3. UNDERSTAND CONSTRUCTORS:
   - Component: `Class(function(self, inst) ... end)` — `self` is the component table, `inst` is the owning entity
   - The first parameter after `self` varies: `inst`, `data`, `owner`, etc.
   - All `self.X = value` assignments in the constructor are properties to document

4. EXTRACT COMPREHENSIVELY:
   - Document ALL functions — never skip trivial getters/setters
   - Track all events (ListenForEvent, PushEvent)
   - Track all tags (AddTag, RemoveTag, HasTag)
   - Track all component dependencies (inst.components.X)
```

- [ ] **Step 2: Commit**

```bash
git add skills/roles/analyst.md
git commit -m "feat(skills): create analyst role for documentation generation"
```

### Task 7: Move existing skills with YAML frontmatter

Move each existing skill file from `skills/` root into its subdirectory, adding YAML frontmatter and stripping the old `# Skill:` header. Apply content fixes where noted.

**Files:**
- Move: `skills/dst_conventions.md` → `skills/knowledge/dst_conventions.md`
- Move: `skills/function_format.md` → `skills/knowledge/function_format.md`
- Move: `skills/few_shot.md` → `skills/knowledge/few_shot.md` (+ fix error states)
- Move: `skills/few_shot_data.md` → `skills/knowledge/few_shot_data.md`
- Move: `skills/validator_reviewer.md` → `skills/roles/validator_reviewer.md`
- Move: `skills/validator_writer.md` → `skills/roles/validator_writer.md`
- Move: `skills/validator_jury.md` → `skills/roles/validator_jury.md`

- [ ] **Step 1: Move knowledge files with frontmatter**

For each knowledge file, prepend YAML frontmatter and strip `# Skill: xxx` header. The body content stays identical.

**`skills/knowledge/dst_conventions.md`** — prepend:
```yaml
---
name: dst_conventions
description: DST engine conventions — ECS, events, tags, network replication, stategraphs, brains, prefabs, scheduler
inject_into: [analyst, analyst_chunk, analyst_merge, analyst_intermediate, analyst_merge_legacy, reviewer_full, reviewer_typed]
---
```
Strip the `# Skill: dst_conventions` line. Keep all body content from `ENTITY COMPONENT SYSTEM (ECS):` onward.

**`skills/knowledge/function_format.md`** — prepend:
```yaml
---
name: function_format
description: Function documentation format spec, dependency section format, and few-shot contrast examples
inject_into: [analyst, analyst_merge, analyst_merge_legacy]
---
```
Strip the `# Skill: function_format` line. Keep all body content.

**`skills/knowledge/few_shot.md`** — prepend:
```yaml
---
name: few_shot
description: Component file few-shot example — expected output format for component documentation
inject_into: [analyst]
---
```
Strip the `# Skill: few_shot` line. Keep all body content.

**FIX:** Replace the Error states line on the `Activate()` function:
- OLD: `*   **Error states:** Returns early with no effect if \`duration\` is \`<= 0\`.`
- NEW: `*   **Error states:** Errors if \`self.inst\` is nil when \`Activate()\` calls \`self.inst:AddTag()\` — no nil guard present.`

This fixes the contradiction with `function_format.md` — Error states must describe crash/corruption, not normal conditional branches.

**`skills/knowledge/few_shot_data.md`** — prepend:
```yaml
---
name: few_shot_data
description: Data config file few-shot example — expected output format for data configuration documentation
inject_into: [analyst, analyst_merge]
---
```
Strip the `# Skill: few_shot_data` line. Keep all body content.

- [ ] **Step 2: Move role files with frontmatter**

**`skills/roles/validator_reviewer.md`** — prepend:
```yaml
---
name: validator_reviewer
description: Content accuracy review checklist, section requirements, special case logic for documentation validation
inject_into: [reviewer_full, reviewer_typed]
---
```
Strip the `# Skill: validator_reviewer` line. Keep all body content unchanged.

**`skills/roles/validator_writer.md`** — prepend:
```yaml
---
name: validator_writer
description: Patch format rules, anchoring examples, and common repeated patterns for documentation fixes
inject_into: [writer_full, writer_typed]
---
```
Strip the `# Skill: validator_writer` line. Keep all body content.

**`skills/roles/validator_jury.md`** — prepend:
```yaml
---
name: validator_jury
description: Jury voting instructions for section heading dispute resolution
inject_into: [jury]
---
```
Strip the `# Skill: validator_jury` line. Keep all body content.

- [ ] **Step 3: Delete old files at root**

```bash
rm skills/dst_conventions.md skills/function_format.md skills/few_shot.md skills/few_shot_data.md
rm skills/validator_reviewer.md skills/validator_writer.md skills/validator_jury.md
rm skills/docs_SKILL.md skills/quality_rules.md
```

- [ ] **Step 4: Verify directory structure**

```bash
find skills/ -name "*.md" | sort
```

Expected output:
```
skills/knowledge/dst_conventions.md
skills/knowledge/few_shot.md
skills/knowledge/few_shot_data.md
skills/knowledge/function_format.md
skills/roles/analyst.md
skills/roles/validator_jury.md
skills/roles/validator_reviewer.md
skills/roles/validator_writer.md
skills/rules/content_rules.md
skills/rules/format_rules.md
skills/rules/writing_guide.md
```

- [ ] **Step 5: Commit**

```bash
git add skills/
git commit -m "feat(skills): restructure into roles/knowledge/rules with YAML frontmatter"
```

### Task 8: Remove old-format code path from loader

**Files:**
- Modify: `prompts/src/prompts/skills_loader.py`

Now that `skills/roles/` exists, the `_build_registry_legacy()` bridge is no longer needed. The auto-detection will always take the new path. Remove the old-format code.

- [ ] **Step 1: Remove old-format functions and legacy bridge**

Delete these functions from `skills_loader.py`:
- `_parse_index()` (lines 15-59)
- The OLD `load_skill()` function (lines 62-87) — the one with `index_path` parameter
- The OLD `load_skills_for()` function (lines 90-111) — the one with `index_path` parameter
- `_build_registry_legacy()` — the bridge function added in Task 1

Replace the old `load_skill()` and `load_skills_for()` with new versions that use the registry:

```python
def load_skill(name: str, *, _registry_override: dict | None = None) -> str:
    """Load single skill by name. Raises KeyError if not found."""
    reg = _get_registry(_override=_registry_override)
    if name not in reg:
        raise KeyError(f"Skill '{name}' not found in registry")
    return reg[name]["content"]


def load_skills_for(
    target: str,
    *,
    exclude: list[str] | None = None,
    _registry_override: dict | None = None,
) -> dict[str, str]:
    """Return {name: content} for all skills matching target."""
    reg = _get_registry(_override=_registry_override)
    exclude_set = set(exclude) if exclude else set()
    return {
        name: entry["content"]
        for name, entry in reg.items()
        if target in entry["inject_into"] and name not in exclude_set
    }
```

Also clean up imports: remove `import os as _os` (no longer needed), keep `from pathlib import Path` (or use `_Path`).

- [ ] **Step 2: Simplify _get_registry — remove legacy branch**

Replace `_get_registry` with:

```python
def _get_registry(*, _override: dict | None = None) -> dict[str, dict]:
    """Return the skill registry, building on first call."""
    if _override is not None:
        return _override
    global _registry
    if _registry is None:
        _registry = _build_registry_new()
    return _registry
```

Rename `_build_registry_new` to `_build_registry` (no longer needs the `_new` suffix).

- [ ] **Step 3: Verify the new loader works with real skill files**

```bash
.venv/Scripts/python -c "
from prompts.skills_loader import combine_skills, load_skill, _clear_cache
_clear_cache()
print('analyst skills:', len(combine_skills('analyst')), 'chars')
print('reviewer_full skills:', len(combine_skills('reviewer_full')), 'chars')
print('jury skills:', len(combine_skills('jury')), 'chars')
print('load_skill dst_conventions:', len(load_skill('dst_conventions')), 'chars')
print('OK')
"
```

Expected: All calls succeed, print character counts > 0.

- [ ] **Step 4: Commit**

```bash
git add prompts/src/prompts/skills_loader.py
git commit -m "refactor(skills): remove old-format loader code, registry-only API"
```

### Task 9: Rewrite loader tests for new format

**Files:**
- Modify: `prompts/tests/test_skills_loader.py`

The old tests used `index_path` parameter and temp dirs with `docs_SKILL.md`. Rewrite to test the new registry-based API using `_registry_override` and real skill files.

- [ ] **Step 1: Rewrite test file**

Replace the entire content of `prompts/tests/test_skills_loader.py` with:

```python
"""
Tests for skills_loader.py — YAML frontmatter registry and combine_skills API.
Run: .venv/Scripts/pytest prompts/tests/test_skills_loader.py -v
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


# ── Mock registry for unit tests ────────────────────────────────────────────

MOCK_REGISTRY = {
    "analyst": {
        "name": "analyst", "inject_into": ["analyst", "analyst_chunk"],
        "content": "role: analyst content", "group": 0, "path": "roles/analyst.md",
    },
    "dst_conventions": {
        "name": "dst_conventions", "inject_into": ["analyst", "analyst_chunk"],
        "content": "knowledge: dst content", "group": 1, "path": "knowledge/dst_conventions.md",
    },
    "function_format": {
        "name": "function_format", "inject_into": ["analyst"],
        "content": "knowledge: format content", "group": 1, "path": "knowledge/function_format.md",
    },
    "content_rules": {
        "name": "content_rules", "inject_into": ["analyst", "analyst_chunk"],
        "content": "rules: content rules", "group": 2, "path": "rules/content_rules.md",
    },
    "format_rules": {
        "name": "format_rules", "inject_into": ["analyst"],
        "content": "rules: format rules", "group": 2, "path": "rules/format_rules.md",
    },
}


# ── combine_skills tests ────────────────────────────────────────────────────

def run_combine_skills_tests():
    from prompts.skills_loader import combine_skills

    # T1: returns content for matching target
    result = combine_skills("analyst", _registry_override=MOCK_REGISTRY)
    check("combine_skills returns non-empty for valid target",
          len(result) > 0, f"got empty string")

    # T2: group ordering — role (0) before knowledge (1) before rules (2)
    check("combine_skills: role before knowledge",
          result.index("analyst") < result.index("dst_conventions"),
          "role should come before knowledge")
    check("combine_skills: knowledge before rules",
          result.index("dst_conventions") < result.index("content_rules"),
          "knowledge should come before rules")

    # T3: alphabetical within group
    check("combine_skills: dst_conventions before function_format",
          result.index("dst_conventions") < result.index("function_format"),
          "alphabetical within knowledge group")
    check("combine_skills: content_rules before format_rules",
          result.index("content_rules") < result.index("format_rules"),
          "alphabetical within rules group")

    # T4: separator format
    check("combine_skills: separator present",
          "=== SKILL: analyst ===" in result,
          "separator missing")

    # T5: exclude parameter
    result_excl = combine_skills("analyst", exclude=["function_format"], _registry_override=MOCK_REGISTRY)
    check("combine_skills: exclude removes skill",
          "function_format" not in result_excl and "dst_conventions" in result_excl,
          "exclude did not work")

    # T6: unknown target returns empty string
    result_empty = combine_skills("nonexistent", _registry_override=MOCK_REGISTRY)
    check("combine_skills: unknown target returns ''",
          result_empty == "", f"got: {result_empty!r}")

    # T7: exclude unknown name silently ignored
    result_unk = combine_skills("analyst", exclude=["no_such"], _registry_override=MOCK_REGISTRY)
    check("combine_skills: unknown exclude ignored",
          "analyst" in result_unk, "should still return results")

    # T8: analyst_chunk target only gets matching skills (not function_format/format_rules)
    result_chunk = combine_skills("analyst_chunk", _registry_override=MOCK_REGISTRY)
    check("combine_skills: analyst_chunk excludes non-matching",
          "function_format" not in result_chunk and "format_rules" not in result_chunk,
          "non-matching skills included")
    check("combine_skills: analyst_chunk includes matching",
          "analyst" in result_chunk and "dst_conventions" in result_chunk and "content_rules" in result_chunk,
          "matching skills missing")


# ── load_skill tests ────────────────────────────────────────────────────────

def run_load_skill_tests():
    from prompts.skills_loader import load_skill

    # T9: returns content by name
    result = load_skill("analyst", _registry_override=MOCK_REGISTRY)
    check("load_skill returns content",
          result == "role: analyst content", f"got: {result!r}")

    # T10: unknown name raises KeyError
    try:
        load_skill("ghost", _registry_override=MOCK_REGISTRY)
        check("load_skill unknown raises KeyError", False, "no exception")
    except KeyError:
        check("load_skill unknown raises KeyError", True)


# ── load_skills_for tests ───────────────────────────────────────────────────

def run_load_skills_for_tests():
    from prompts.skills_loader import load_skills_for

    # T11: returns matching skills as dict
    result = load_skills_for("analyst_chunk", _registry_override=MOCK_REGISTRY)
    check("load_skills_for returns matching dict",
          set(result.keys()) == {"analyst", "dst_conventions", "content_rules"},
          f"keys: {set(result.keys())}")

    # T12: no match returns empty dict
    result_empty = load_skills_for("nonexistent", _registry_override=MOCK_REGISTRY)
    check("load_skills_for no match returns {}",
          result_empty == {}, f"got: {result_empty}")


# ── integration test with real skill files ──────────────────────────────────

def run_integration_tests():
    from prompts.skills_loader import combine_skills, load_skill, _clear_cache

    _clear_cache()

    # T13: combine_skills on real files returns non-empty
    result = combine_skills("analyst")
    check("integration: analyst target non-empty",
          len(result) > 100, f"got {len(result)} chars")

    # T14: analyst includes expected skill names
    check("integration: analyst has dst_conventions",
          "dst_conventions" in result, "missing dst_conventions")
    check("integration: analyst has function_format",
          "function_format" in result, "missing function_format")
    check("integration: analyst has content_rules",
          "content_rules" in result, "missing content_rules")

    # T15: load_skill on real file
    dst = load_skill("dst_conventions")
    check("integration: load_skill dst_conventions",
          "ENTITY COMPONENT SYSTEM" in dst, f"unexpected content: {dst[:40]}")

    # T16: _clear_cache works
    _clear_cache()
    check("integration: _clear_cache runs", True)


# ── entry point ─────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("\n=== combine_skills tests ===")
    run_combine_skills_tests()
    print("\n=== load_skill tests ===")
    run_load_skill_tests()
    print("\n=== load_skills_for tests ===")
    run_load_skills_for_tests()
    print("\n=== integration tests ===")
    run_integration_tests()
    print(f"\n{passed} passed, {failed} failed")
    sys.exit(1 if failed else 0)
```

- [ ] **Step 2: Run tests**

Run: `.venv/Scripts/python prompts/tests/test_skills_loader.py`
Expected: All 16 tests pass.

- [ ] **Step 3: Commit**

```bash
git add prompts/tests/test_skills_loader.py
git commit -m "test(skills): rewrite loader tests for new registry-based API"
```

### Task 10: Validation gate

Verify that `combine_skills()` returns non-empty content for every active target from the injection mapping table.

- [ ] **Step 1: Run validation gate script**

```bash
.venv/Scripts/python -c "
from prompts.skills_loader import combine_skills, _clear_cache
_clear_cache()

ACTIVE_TARGETS = [
    'analyst', 'analyst_chunk', 'analyst_merge',
    'analyst_intermediate', 'analyst_merge_legacy',
    'reviewer_full', 'reviewer_typed',
    'writer_full', 'writer_typed', 'jury',
]

EXPECTED_SKILLS = {
    'analyst': ['analyst', 'dst_conventions', 'function_format', 'few_shot', 'few_shot_data', 'content_rules', 'format_rules', 'writing_guide'],
    'analyst_chunk': ['analyst', 'dst_conventions', 'content_rules'],
    'analyst_merge': ['analyst', 'dst_conventions', 'function_format', 'few_shot_data', 'content_rules', 'format_rules', 'writing_guide'],
    'analyst_intermediate': ['analyst', 'dst_conventions', 'content_rules'],
    'analyst_merge_legacy': ['analyst', 'dst_conventions', 'function_format', 'content_rules', 'format_rules', 'writing_guide'],
    'reviewer_full': ['validator_reviewer', 'dst_conventions', 'content_rules'],
    'reviewer_typed': ['validator_reviewer', 'dst_conventions', 'content_rules'],
    'writer_full': ['validator_writer'],
    'writer_typed': ['validator_writer'],
    'jury': ['validator_jury'],
}

ok = True
for target in ACTIVE_TARGETS:
    result = combine_skills(target)
    if not result:
        print(f'FAIL: {target} returned empty')
        ok = False
        continue
    for skill_name in EXPECTED_SKILLS.get(target, []):
        if f'=== SKILL: {skill_name} ===' not in result:
            print(f'FAIL: {target} missing skill {skill_name}')
            ok = False
    print(f'OK: {target} ({len(result)} chars, {len(EXPECTED_SKILLS.get(target, []))} skills)')

# Also check few_shot is in analyst (it has both few_shot and few_shot_data)
analyst_result = combine_skills('analyst')
assert '=== SKILL: few_shot ===' in analyst_result, 'analyst missing few_shot'
assert '=== SKILL: few_shot_data ===' in analyst_result, 'analyst missing few_shot_data'
print('OK: analyst has both few_shot and few_shot_data')

if ok:
    print('\nVALIDATION GATE PASSED')
else:
    print('\nVALIDATION GATE FAILED')
    exit(1)
"
```

Expected: All targets pass with correct skill counts.

- [ ] **Step 2: Commit all Phase 2 work**

```bash
git add -A
git commit -m "feat(skills): complete Phase 2 — file restructure with validation gate"
```

---

## Chunk 3: Phase 3 — Prompt Builder Refactor

Replace inline rules and `load_skill()` calls with `combine_skills()` in all active prompt builders. Fix content contradictions. Update affected tests.

### Task 11: Exhaustive grep — identify all skill references

- [ ] **Step 1: Run grep to find all files referencing skills**

```bash
grep -rn "_FUNCTION_FORMAT_SPEC\|_QUALITY_RULES\|_DST_CONV\|_REVIEWER_SKILL\|_WRITER_SKILL\|_JURY_SKILL\|_FEW_SHOT\|load_skill\|load_skills_for" prompts/ validator/
```

Use the output as the checklist for this phase. Expected files:
- `prompts/src/prompts/standard.py` — `load_skill`, `_DST_CONV`, `_FEW_SHOT_COMPONENT`, `_FEW_SHOT_DATA`
- `prompts/src/prompts/chunked.py` — `load_skill`, `_FUNCTION_FORMAT_SPEC`, `_DST_CONV`
- `prompts/src/prompts/skills_loader.py` — definitions (already done)
- `prompts/src/prompts/__init__.py` — re-exports (already done)
- `prompts/tests/test_skills_loader.py` — tests (already done)
- `prompts/tests/test_chunk_prompts.py` — imports `_FUNCTION_FORMAT_SPEC`
- `validator/src/validator/content/prompts.py` — `load_skill`, `_QUALITY_RULES`, `_REVIEWER_SKILL`, `_WRITER_SKILL`, `_JURY_SKILL`
- `validator/tests/test_content_chunked.py` — imports `build_typed_reviewer_prompt`, `build_typed_writer_prompt`

### Task 12: Refactor standard.py

**Files:**
- Modify: `prompts/src/prompts/standard.py`

Replace the entire file. The new version is much shorter — inline rules move to skill files.

- [ ] **Step 1: Verify rag imports are unused in this file**

```bash
grep -n "extract_lua_references\|safe_read_lua\|compute_source_hash\|format_connected_section\|clean_model_output\|get_lua_files" prompts/src/prompts/standard.py
```

These appear only in the import statement (line 6-13). They are NOT used in `_detect_file_type()` or `build_prompt()`. However, check if anything imports them FROM standard.py:

```bash
grep -rn "from prompts.standard import" prompts/ core/ validator/
```

If only `build_prompt` and `build_single_prompt` are imported from this file, remove the unused rag imports. If other things are imported, keep them.

- [ ] **Step 2: Rewrite `prompts/src/prompts/standard.py`**

```python
"""
Module chứa hàm build_prompt() — tạo prompt cho LLM.
Không chứa constants, chỉ chứa template.
"""

from prompts.skills_loader import combine_skills

_DATA_CONFIG_DIRS = {"map", "languages", "util"}


def _detect_file_type(display_filepath: str) -> str:
    """Returns 'component' or 'data_config' based on directory path.

    Expects a relative path as produced by main.py (e.g. './map/a.lua',
    './components/combat.lua', './achievements.lua'). Absolute paths are
    unsupported and results are not guaranteed.
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


def build_prompt(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    lua_code: str,
    connected_section: str,
    connected_content: str = "",
    source_hash: str = "",
    *,
    file_tree: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
) -> str:
    """
    Tạo prompt đầy đủ để gửi cho LLM tạo tài liệu cho một file Lua.
    Tất cả config (version, date, tree...) được truyền vào qua tham số.
    """
    file_type = _detect_file_type(display_filepath)
    exclude = ["few_shot_data"] if file_type == "component" else ["few_shot"]
    skills_block = combine_skills("analyst", exclude=exclude)

    return f"""=== CONTEXT ===

1. PROJECT FILE TREE
{file_tree}

2. TARGET FILE: {display_filepath}

3. CONNECTED FILES AND FUNCTIONS
{connected_section or "No external references found."}

4. CONNECTED FILES — EXTRACTED SOURCE CODE
{connected_content or "No function source code available."}

=== TODAY'S DATE: {today_date} ===

=== SKILLS ===
{skills_block}

=== OUTPUT TEMPLATE ===
---
id: {comp_name}
title: {comp_title}
description:
tags: []
sidebar_position: 10
last_updated: {today_date}
build_version: {version}
change_status: stable
category_type: {category_type}
source_hash: {source_hash}
system_scope:
---

# {comp_title}

> Based on game build **{version}** | Last updated: {today_date}

=== SOURCE CODE ===
{lua_code}"""
```

Note: The rag imports are removed — Step 1 confirms nothing imports them from `standard.py`. The `load_skill` import is replaced with `combine_skills`. All module-level skill constants are removed.

**IMPORTANT — template is intentionally shorter:** The current `standard.py` has ~110 lines of inline instructions (role, per-section guidance, critical instructions). The rewrite delegates all of this to skills (`analyst` role + `writing_guide` + `format_rules` + `content_rules`). After completing this step, verify that `combine_skills("analyst")` output covers the key instructions that were previously inline — especially the detailed per-section guidance (Overview writing, Usage example format, Properties table columns, Main functions format, Events format). If `writing_guide` is insufficient, extend it before committing.

- [ ] **Step 3: Verify build_prompt still works**

```bash
.venv/Scripts/python -c "
from prompts.standard import build_prompt
result = build_prompt(
    'testcomp', 'TestComp', './components/test.lua',
    '-- lua code', 'connected section',
    file_tree='tree', today_date='2026-04-06', version='720000',
    category_type='components',
)
assert '=== SKILL: analyst ===' in result, 'missing analyst skill'
assert '=== SKILL: dst_conventions ===' in result, 'missing dst_conventions'
assert '=== SKILL: few_shot ===' in result, 'missing few_shot (component file)'
assert '=== SKILL: few_shot_data ===' not in result, 'should exclude few_shot_data for component'
assert 'testcomp' in result, 'missing comp_name in template'
print(f'OK: {len(result)} chars')
"
```

- [ ] **Step 4: Verify data config file type excludes few_shot**

```bash
.venv/Scripts/python -c "
from prompts.standard import build_prompt
result = build_prompt(
    'testdata', 'TestData', './map/test.lua',
    '-- lua code', '',
    today_date='2026-04-06', version='720000', category_type='root',
)
assert '=== SKILL: few_shot_data ===' in result, 'missing few_shot_data for data config'
assert '=== SKILL: few_shot ===' not in result, 'should exclude few_shot for data config'
print('OK: data config file type correct')
"
```

- [ ] **Step 5: Commit**

```bash
git add prompts/src/prompts/standard.py
git commit -m "refactor(prompts): standard.py uses combine_skills, removes inline rules"
```

### Task 13: Refactor chunked.py

**Files:**
- Modify: `prompts/src/prompts/chunked.py`

Replace module-level `load_skill()` calls and inline skill injections with `combine_skills()`.

- [ ] **Step 1: Replace module-level imports**

Change the top of the file. Remove:
```python
from prompts.skills_loader import load_skill

# Skill content loaded once at module import — injected into f-string prompts below.
# IMPORTANT: _FUNCTION_FORMAT_SPEC must keep this exact name — test_chunk_prompts.py
# imports it directly: `from chunked_prompt import ..., _FUNCTION_FORMAT_SPEC`
_FUNCTION_FORMAT_SPEC = load_skill("function_format")   # replaces inline constant; name preserved for test compat
_DST_CONV             = load_skill("dst_conventions")
```

Replace with:
```python
from prompts.skills_loader import combine_skills
```

- [ ] **Step 2: Refactor `build_intermediate_merge_prompt()`**

Add skills block injection. After the line `combined += f"\n--- ANALYSIS ...`:

In the return f-string, after the existing `=== MERGE RULES ===` section and before `=== OUTPUT FORMAT ===`, add:

```
=== SKILLS ===
{combine_skills("analyst_intermediate")}
```

Also remove the inline `{_DST_CONV}` that doesn't exist in intermediate merge (it wasn't there before — this function has no skill injection currently, which is correct per spec: `analyst_intermediate` gets `analyst` + `dst_conventions` + `content_rules`).

Actually, looking at the current code, `build_intermediate_merge_prompt()` does NOT inject any skills — it only has inline merge rules. Per the spec, `analyst_intermediate` should get `analyst` + `dst_conventions` + `content_rules`. Add a skills block:

After `=== MERGE RULES ===` section (before `=== OUTPUT FORMAT ===`), insert:
```python
=== SKILLS ===
{combine_skills("analyst_intermediate")}
```

- [ ] **Step 3: Refactor `build_chunk_prompt()`**

Replace `{_DST_CONV}` in the f-string with `{combine_skills("analyst_chunk")}`.

Find this section in the f-string:
```
5. DST CODING CONVENTIONS
{_DST_CONV}
```

Replace with:
```
=== SKILLS ===
{combine_skills("analyst_chunk")}
```

- [ ] **Step 4: Refactor `build_merge_prompt()`**

Replace both `{_DST_CONV}` and `{_FUNCTION_FORMAT_SPEC}` with a single skills block.

Find:
```
5. DST CODING CONVENTIONS
{_DST_CONV}
```
Replace with:
```
=== SKILLS ===
{combine_skills("analyst_merge")}
```

Find and remove the separate FORMAT SPECIFICATION section:
```
=== FORMAT SPECIFICATION ===
{_FUNCTION_FORMAT_SPEC}
```
(This content is now included in the skills block via `function_format` skill.)

- [ ] **Step 5: Refactor `_build_merge_prompt_legacy()`**

Replace `{_DST_CONV}` with a skills block.

Find:
```
5. DST CODING CONVENTIONS
{_DST_CONV}
```
Replace with:
```
=== SKILLS ===
{combine_skills("analyst_merge_legacy")}
```

- [ ] **Step 6: Verify all 4 prompt builders work**

```bash
.venv/Scripts/python -c "
from prompts.chunked import build_chunk_prompt, build_merge_prompt, build_intermediate_merge_prompt, _build_merge_prompt_legacy
from prompts.pre_synthesis import PreSynthesisResult

# build_chunk_prompt
cp = build_chunk_prompt('test', 'Test', 'scripts/test.lua', '-- code', 1, 2)
assert '=== SKILL: analyst ===' in cp, 'chunk: missing analyst'
assert '=== SKILL: dst_conventions ===' in cp, 'chunk: missing dst_conventions'
print(f'build_chunk_prompt OK: {len(cp)} chars')

# build_intermediate_merge_prompt
imp = build_intermediate_merge_prompt('test', 'scripts/test.lua', ['result1'], 1, 1)
assert '=== SKILL: analyst ===' in imp, 'intermediate: missing analyst'
print(f'build_intermediate_merge_prompt OK: {len(imp)} chars')

# build_merge_prompt
ps = PreSynthesisResult(
    game_tags=[], external_deps=[], system_scope='entity',
    dependencies=[], partial_descriptions=['desc'],
    functions=[], events_listens=[], events_pushes=[],
    constructor_properties=[],
)
mp = build_merge_prompt('test', 'Test', 'scripts/test.lua', ps, today_date='2026-04-06', version='720000', category_type='root')
assert '=== SKILL: analyst ===' in mp, 'merge: missing analyst'
assert '=== SKILL: function_format ===' in mp, 'merge: missing function_format'
assert '=== SKILL: few_shot_data ===' in mp, 'merge: missing few_shot_data'
print(f'build_merge_prompt OK: {len(mp)} chars')

# _build_merge_prompt_legacy
lmp = _build_merge_prompt_legacy('test', 'Test', 'scripts/test.lua', ['result1'], today_date='2026-04-06', version='720000', category_type='root')
assert '=== SKILL: analyst ===' in lmp, 'legacy: missing analyst'
assert '=== SKILL: function_format ===' in lmp, 'legacy: missing function_format'
print(f'_build_merge_prompt_legacy OK: {len(lmp)} chars')

print('All chunked prompt builders OK')
"
```

- [ ] **Step 7: Commit**

```bash
git add prompts/src/prompts/chunked.py
git commit -m "refactor(prompts): chunked.py uses combine_skills, removes inline skill constants"
```

### Task 14: Refactor validator/content/prompts.py

**Files:**
- Modify: `validator/src/validator/content/prompts.py`

Replace `load_skill()` calls with `combine_skills()` for the 5 active prompt builder functions. Keep module-level constants for dead code functions.

- [ ] **Step 1: Update imports and module-level constants**

Change the imports at the top of the file:

```python
"""Prompt templates for content validation writer and reviewer."""

import re
from prompts.skills_loader import load_skill, combine_skills

# Module-level constants — used by dead code functions (build_section_reviewer_prompt,
# build_section_writer_prompt). These functions are NOT refactored in this restructure.
_QUALITY_RULES = load_skill("content_rules")   # was "quality_rules" — split in restructure
_REVIEWER_SKILL = load_skill("validator_reviewer")
_WRITER_SKILL = load_skill("validator_writer")
_JURY_SKILL = load_skill("validator_jury")
```

Note: `_QUALITY_RULES` now loads `content_rules` (was `quality_rules` which is deleted). The dead code function `build_section_reviewer_prompt` references `_QUALITY_RULES` — it now gets content-only rules (the "apply ONLY content accuracy rules" filter is redundant but harmless).

- [ ] **Step 2: Refactor `build_reviewer_prompt()`**

Replace `{_REVIEWER_SKILL}` with `{combine_skills("reviewer_full")}` in the system_prompt f-string.

Find:
```python
=== REVIEW RULES ===
{_REVIEWER_SKILL}
```

Replace with:
```python
=== SKILLS ===
{combine_skills("reviewer_full")}
```

- [ ] **Step 3: Refactor `build_writer_prompt()`**

The writer prompt currently has no skill injection in the system_prompt (it inlines the patch format rules). Replace inline rules with combine_skills.

Find the system_prompt assignment. Add skills block. Replace the inline rules section:

```python
    system_prompt = f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.
Your task: fix the documentation based on reviewer feedback. Return ONLY targeted patches, not the entire document.

=== SKILLS ===
{combine_skills("writer_full")}

=== PATCH FORMAT ===
...
```

Wait — looking at the current code more carefully, `build_writer_prompt` does NOT inject `_WRITER_SKILL` currently. It has inline patch format rules. Per the spec, `writer_full` gets only `validator_writer` role skill. The role skill IS the patch format rules.

So replace the inline rules section with the skills block:

```python
    system_prompt = f"""You are a documentation writer for Don't Starve Together (DST) Lua API documentation.
Your task: fix the documentation based on reviewer feedback. Return ONLY targeted patches, not the entire document.

=== SKILLS ===
{combine_skills("writer_full")}

=== PATCH FORMAT ===
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
- Preserve markdown formatting and structure
- old_text must NOT span more than one ### function block — never include two or more ### headings in the same old_text
- To ADD a new ### function: use the last 1-2 lines of an adjacent function as the anchor, then include those lines plus the new function block in new_text
- To DELETE a function: target only that function's own block, never include surrounding functions in old_text"""
```

Note: The PATCH FORMAT with JSON schema stays inline — this is a response format contract (guarantee #4).

- [ ] **Step 4: Refactor `build_typed_reviewer_prompt()`**

Replace `{_REVIEWER_SKILL}` with `{combine_skills("reviewer_typed")}`.

Find in the system_prompt f-string:
```python
=== SECTION REQUIREMENTS ===
{section_ctx}{_REVIEWER_SKILL}
```

Replace with:
```python
=== SECTION REQUIREMENTS ===
{section_ctx}
=== SKILLS ===
{combine_skills("reviewer_typed")}
```

- [ ] **Step 5: Refactor `build_typed_writer_prompt()`**

Replace `{_WRITER_SKILL}` with `{combine_skills("writer_typed")}`.

Find:
```python
=== FORMAT RULES ===
{_WRITER_SKILL}
```

Replace with:
```python
=== SKILLS ===
{combine_skills("writer_typed")}
```

- [ ] **Step 6: Refactor `build_jury_prompt()`**

Replace `{_JURY_SKILL}` with `{combine_skills("jury")}`.

Find:
```python
=== JURY VOTING INSTRUCTIONS ===
{_JURY_SKILL}
```

Replace with:
```python
=== SKILLS ===
{combine_skills("jury")}
```

- [ ] **Step 7: Verify all 5 active prompt builders**

```bash
.venv/Scripts/python -c "
from validator.content.prompts import (
    build_reviewer_prompt, build_writer_prompt,
    build_typed_reviewer_prompt, build_typed_writer_prompt,
    build_jury_prompt,
)

# build_reviewer_prompt
sys, usr = build_reviewer_prompt('md', 'lua', 'conn')
assert '=== SKILL: validator_reviewer ===' in sys, 'reviewer: missing validator_reviewer'
assert '=== SKILL: dst_conventions ===' in sys, 'reviewer: missing dst_conventions'
assert '=== SKILL: content_rules ===' in sys, 'reviewer: missing content_rules'
# Verify JSON response format is still inline (guarantee #4)
assert '\"approved\"' in sys, 'reviewer: JSON schema missing'
print('build_reviewer_prompt OK')

# build_writer_prompt
sys, usr = build_writer_prompt('md', 'lua', 'conn', ['issue'], ['suggestion'])
assert '=== SKILL: validator_writer ===' in sys, 'writer: missing validator_writer'
assert '\"old_text\"' in sys, 'writer: JSON schema missing'
print('build_writer_prompt OK')

# build_typed_reviewer_prompt
sys, usr = build_typed_reviewer_prompt('section', 'lua', '## Main functions')
assert '=== SKILL: validator_reviewer ===' in sys, 'typed_reviewer: missing validator_reviewer'
assert '\"approved\"' in sys, 'typed_reviewer: JSON schema missing'
print('build_typed_reviewer_prompt OK')

# build_typed_writer_prompt
class FakeFinding:
    function = 'Foo'
    field = 'Returns'
    rule_id = 'WRONG_VALUE'
    issue = 'wrong return'
    section = '## Main functions'
sys, usr = build_typed_writer_prompt('text', 'lua', FakeFinding(), '## Main functions')
assert '=== SKILL: validator_writer ===' in sys, 'typed_writer: missing validator_writer'
assert '\"op\"' in sys, 'typed_writer: JSON schema missing'
print('build_typed_writer_prompt OK')

# build_jury_prompt
sys, usr = build_jury_prompt('md', 'lua', 'conn', 'reason')
assert '=== SKILL: validator_jury ===' in sys, 'jury: missing validator_jury'
assert '\"vote\"' in sys, 'jury: JSON schema missing'
print('build_jury_prompt OK')

print('All validator prompt builders OK')
"
```

- [ ] **Step 8: Commit**

```bash
git add validator/src/validator/content/prompts.py
git commit -m "refactor(validator): prompts use combine_skills, removes inline skill refs"
```

### Task 15: Update test files

**Files:**
- Modify: `prompts/tests/test_chunk_prompts.py`
- Modify: `validator/tests/test_content_chunked.py` (if assertions break)

- [ ] **Step 1: Update `test_chunk_prompts.py`**

The test imports `_FUNCTION_FORMAT_SPEC` from `prompts.chunked`, which no longer exists. Update:

Remove the import of `_FUNCTION_FORMAT_SPEC`:
```python
# OLD:
from prompts.chunked import build_chunk_prompt, build_merge_prompt, _FUNCTION_FORMAT_SPEC
# NEW:
from prompts.chunked import build_chunk_prompt, build_merge_prompt
```

Replace the `_FUNCTION_FORMAT_SPEC` test section (lines 73-86) with:

```python
# -- format spec included via skills --
print("\n-- format spec in merge prompt --")

check("merge prompt: 'External dependencies' present via skills",
     "External dependencies" in merge_prompt,
     "External dependencies section missing from skills injection")

check("merge prompt: 'Components used' present via skills",
     "Components used" in merge_prompt,
     "Components used section missing from skills injection")

check("merge prompt: 'Tags' label present via skills",
     "Tags" in merge_prompt,
     "Tags section missing from skills injection")
```

Also update any assertions that check for the old prompt structure. For example, if the test checks for `"GAME TAGS"` section positioning relative to `"DEPENDENCIES (pre-extracted)"`, these should still work if the prompt structure is preserved.

- [ ] **Step 2: Run chunk prompt tests**

Run: `.venv/Scripts/python prompts/tests/test_chunk_prompts.py`
Expected: All tests pass.

- [ ] **Step 3: Run validator content tests**

Run: `.venv/Scripts/pytest validator/tests/test_content_chunked.py -v`

If any tests fail due to changed prompt content (e.g., assertions on exact strings in the system prompt), update them to match the new skill-injected format. The key assertion changes:
- Instead of checking for `_REVIEWER_SKILL` content directly, check for `=== SKILL: validator_reviewer ===`
- Instead of checking for `_WRITER_SKILL` content directly, check for `=== SKILL: validator_writer ===`

- [ ] **Step 4: Run ALL tests**

```bash
.venv/Scripts/pytest prompts/tests/ validator/tests/ -v
```

Expected: All tests pass.

- [ ] **Step 5: Commit**

```bash
git add prompts/tests/ validator/tests/
git commit -m "test(prompts): update tests for combine_skills refactor"
```

### Task 16: Verify context preservation guarantees

- [ ] **Step 1: Verify guarantee #4 — JSON response format schemas stay inline**

```bash
.venv/Scripts/python -c "
from validator.content.prompts import (
    build_reviewer_prompt, build_writer_prompt,
    build_typed_reviewer_prompt, build_typed_writer_prompt,
    build_jury_prompt,
)

# Reviewer: JSON schema with approved, findings
sys, _ = build_reviewer_prompt('md', 'lua', '')
assert '\"approved\": true/false' in sys or '\"approved\"' in sys, 'reviewer JSON schema missing'
assert '\"findings\"' in sys, 'reviewer findings field missing'

# Writer: JSON schema with old_text, new_text, reason
sys, _ = build_writer_prompt('md', 'lua', '', ['i'], ['s'])
assert '\"old_text\"' in sys, 'writer JSON schema missing'
assert '\"new_text\"' in sys, 'writer new_text field missing'

# Typed reviewer: JSON schema with approved, findings[].rule_id
sys, _ = build_typed_reviewer_prompt('sec', 'lua', '## Overview')
assert '\"rule_id\"' in sys, 'typed reviewer rule_id missing'

# Typed writer: JSON schema with op types
sys, _ = build_typed_writer_prompt('sec', 'lua', type('F', (), {'function': None, 'field': None, 'rule_id': '', 'issue': '', 'section': ''})())
assert '\"op\"' in sys, 'typed writer op field missing'
assert 'rewrite_function' in sys, 'typed writer op choices missing'

# Jury: JSON schema with vote
sys, _ = build_jury_prompt('md', 'lua', '', 'reason')
assert '\"vote\"' in sys, 'jury vote field missing'

print('Guarantee #4 VERIFIED: all JSON schemas remain inline')
"
```

- [ ] **Step 2: Commit Phase 3**

```bash
git add -A
git commit -m "feat(skills): complete Phase 3 — all prompt builders use combine_skills"
```

---

## Chunk 4: Phase 4 — Regression Check

Compare reviewer prompt output before and after the restructure to verify no degradation.

### Task 17: Regression check on reviewer prompts

The `reviewer_full` and `reviewer_typed` targets now inject `dst_conventions` + `content_rules` alongside `validator_reviewer` — a new addition. This may change reviewer behavior (more thorough, potentially more false positives).

- [ ] **Step 1: Generate reviewer prompts for comparison**

Pick 2-3 existing documentation files and generate reviewer prompts with both old and new configurations:

```bash
.venv/Scripts/python -c "
from validator.content.prompts import build_reviewer_prompt, build_typed_reviewer_prompt

# Read a sample doc + its lua source
from pathlib import Path
import glob

# Find a doc file that has a matching lua source
docs_dir = Path('dst-api-webdocs/docs')
sample_docs = list(docs_dir.rglob('*.md'))[:3]

for doc_path in sample_docs:
    md = doc_path.read_text(encoding='utf-8')
    print(f'--- {doc_path.name} ---')

    # build_reviewer_prompt (full doc)
    sys_prompt, user_content = build_reviewer_prompt(md, '-- no lua source', '')
    print(f'  reviewer_full system prompt: {len(sys_prompt)} chars')

    # build_typed_reviewer_prompt (section)
    sys_prompt2, _ = build_typed_reviewer_prompt(
        md[:500], '-- no lua source', '## Overview'
    )
    print(f'  reviewer_typed system prompt: {len(sys_prompt2)} chars')

print('Review the prompt sizes. If significantly larger than before (>2x), content_rules or dst_conventions may be too verbose for the reviewer context.')
"
```

- [ ] **Step 2: Manual comparison (if dst-scripts/ is available)**

If Lua source files are available in `dst-scripts/`, run actual validation on 2-3 docs:

```bash
.venv/Scripts/python -m validator path/to/sample1.md --content-only
.venv/Scripts/python -m validator path/to/sample2.md --content-only
```

Compare reviewer findings with expected behavior:
- Same number of findings or fewer (not significantly more)
- No new false positives from the additional context
- Previously caught issues are still caught

If false positive rate increases noticeably, reduce the scope of `content_rules.md` for reviewer targets — consider splitting into `content_rules_generation.md` (for analyst) and `content_rules_review.md` (lighter version for reviewer).

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "chore(skills): Phase 4 regression check complete"
```

---

## Post-implementation checklist

After all 4 phases are complete, verify:

- [ ] `skills/` root contains NO `.md` files (all moved to subdirs)
- [ ] `skills/docs_SKILL.md` deleted
- [ ] `skills/quality_rules.md` deleted
- [ ] `prompts/src/prompts/skills_loader.py` has NO `_parse_index` function
- [ ] `prompts/src/prompts/skills_loader.py` has NO `index_path` parameter
- [ ] `prompts/src/prompts/standard.py` has NO `load_skill` import
- [ ] `prompts/src/prompts/chunked.py` has NO `_FUNCTION_FORMAT_SPEC` or `_DST_CONV`
- [ ] All tests pass: `.venv/Scripts/pytest prompts/tests/ validator/tests/ -v`
- [ ] Validation gate passes (Task 10 script)
