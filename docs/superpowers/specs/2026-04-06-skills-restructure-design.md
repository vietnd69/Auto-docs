# Skills Restructure Design

**Date:** 2026-04-06
**Status:** Draft (rev 6 — post user review round 4)
**Scope:** Full overhaul of `skills/` directory structure, content, loading mechanism, and prompt builder integration

---

## Problem Statement

The current skills system has critical bugs and structural issues:

### A. Skill injection mismatches (index declares X, code loads Y)

| Declared in `docs_SKILL.md` | Target | Actually loaded? |
|---|---|---|
| `function_format` → `single_prompt` | `standard.py` | NO — has inline rules instead |
| `quality_rules` → `single_prompt` | `standard.py` | NO — has inline rules instead |
| `quality_rules` → `merge_prompt` | `chunked.py:build_merge_prompt` | NO — missing entirely |
| `few_shot_data` → `merge_prompt` | `chunked.py:build_merge_prompt` | NO — missing entirely |
| (any skill) → `update_prompt` | `update.py` | ZERO skills injected (note: `build_update_prompt` is currently dead code — never imported by `core/`) |

### B. Content contradictions between inline prompts and skills

1. **Error states**: `standard.py:157` says "If this function can return nil or has known failure/edge-case conditions, document them" — but `function_format.md` says "Do NOT list expected nil returns, normal conditional branches". Directly contradictory. (The inline text is about the Error states field specifically — it encourages documenting nil returns there, while function_format forbids it.)
2. **Getters/setters**: `standard.py:151` says "Skip trivial getters/setters" — but `quality_rules.md:78` says "Keep ALL functions — never drop trivial getters/setters". Directly contradictory.
3. **Few-shot error states**: `few_shot.md:56` shows `Error states: Returns early with no effect if duration <= 0` — this is a normal conditional branch, contradicts `function_format.md:14-19`. Should be replaced with an actual crash scenario (e.g., "Errors if `self.inst` is nil when `Activate()` calls `self.inst:AddTag()` — no nil guard present").

### C. Structural issues

- `quality_rules.md` is a monolith mixing format + content rules; validator must mentally filter
- `docs_SKILL.md` index is not programmatically enforced — drifted from reality
- `standard.py` has ~80 lines of inline rules duplicating skill files with different wording
- Validator reviewer has no `dst_conventions` — cannot verify DST patterns
- `update.py` has zero skill injection — weakest prompt in the system
- No explicit role definitions — roles are implicit in prompt templates
- `build_update_prompt()` is defined but never imported — dead code

---

## Design

### 1. Skill File Format

Each skill file uses YAML frontmatter (inspired by skill-creator format) — self-describing, no external index needed:

```markdown
---
name: skill_name
description: One-line description of what this skill provides
inject_into: [target1, target2]
---

# Skill Title

[Body — instructions for LLM]
```

- `inject_into` lives in the skill file itself — cannot drift from a separate index
- `description` helps developers understand purpose without reading body
- Loader scans folder and parses frontmatter automatically

### 2. Directory Structure

```
skills/
├── roles/                     # WHO the LLM is + what approach to take
│   ├── analyst.md              # First-time doc generation from Lua source
│   ├── observer.md             # (DEFERRED) Diff-based doc update when .lua changes
│   ├── validator_reviewer.md   # Content accuracy review (refactored)
│   ├── validator_writer.md     # Patch-based fixes from review feedback
│   └── validator_jury.md       # Section heading dispute voting
│
├── knowledge/                 # Domain knowledge + examples
│   ├── dst_conventions.md      # DST engine (ECS, events, tags, network, prefabs...)
│   ├── function_format.md      # Function doc format + dependency section format
│   ├── few_shot.md             # Component file example
│   └── few_shot_data.md        # Data config file example
│
└── rules/                     # Constraints on format, content, style
    ├── format_rules.md         # MDX compat, section order, YAML frontmatter, headings
    ├── content_rules.md        # Accuracy, completeness, file type classification, properties
    ├── writing_guide.md        # Overview/usage style, constructor rule, incomplete fn handling
    └── change_notes_format.md  # (DEFERRED) Inline change notes markup (added/modified/deleted/moved)
```

**Loader location:** The loader stays at `prompts/src/prompts/skills_loader.py` (rewritten implementation). The `skills/` directory is NOT a Python package — it contains only `.md` files organized in subdirectories. The loader knows the path to `skills/` via `Path(__file__).parents[3] / "skills"` (same approach as current code).

**Files deleted:**
- `skills/docs_SKILL.md` — replaced by self-describing frontmatter in each skill
- `skills/quality_rules.md` — split into `format_rules.md` + `content_rules.md` + `writing_guide.md`

### 3. Role Definitions

Two new roles replace implicit role text in prompt templates:

**`analyst.md`** — absorbs inline text from `standard.py` + `chunked.py`:
- Role: expert technical writer + veteran DST mod developer
- Task: analyze Lua source → generate comprehensive API reference documentation
- Analysis approach: how to read the source (identify file type by structure, trace dependencies via require/components, understand Class() constructor pattern)
- Output structure guidance (section descriptions currently inline in template placeholders)
- Does NOT contain rules — delegates to format_rules, content_rules, writing_guide

**Boundary between analyst.md and writing_guide.md:** `analyst.md` covers **input analysis** (how to read and understand the Lua source), `writing_guide.md` covers **output writing** (how to write each documentation section). The constructor rule — "document `Class(function(self, ...) ... end)` constructors; first param after `self` may be `inst`, `data`, or any other name" — belongs in `writing_guide.md` because it governs how to **write** the constructor documentation, not how to identify it. `analyst.md` may reference constructor patterns when explaining how to identify file types (Class() present → component file), but the formatting rule lives in `writing_guide.md`.

**`observer.md`** (DEFERRED — created when `build_update_prompt` is activated):
- Role: documentation maintainer for version updates
- Task: update existing docs based on version diff
- Action-specific behavior: added → generate new, modified → inline notes, deleted → deprecation notice, moved → path update ± content changes
- How to read unified diffs, what to update vs what NOT to touch
- Does NOT contain change notes format — delegates to change_notes_format.md

### 4. Injection Mapping

#### 4a. Prompt function → target mapping

Every prompt builder function in the codebase maps to exactly one target name:

| Python function | File | Target |
|---|---|---|
| `build_prompt()` | `prompts/standard.py` | `analyst` |
| `build_chunk_prompt()` | `prompts/chunked.py` | `analyst_chunk` |
| `build_merge_prompt()` | `prompts/chunked.py` | `analyst_merge` |
| `build_intermediate_merge_prompt()` | `prompts/chunked.py` | `analyst_intermediate` |
| `_build_merge_prompt_legacy()` | `prompts/chunked.py` | `analyst_merge_legacy` |
| `build_reviewer_prompt()` | `validator/content/prompts.py` | `reviewer_full` |
| `build_writer_prompt()` | `validator/content/prompts.py` | `writer_full` |
| `build_typed_reviewer_prompt()` | `validator/content/prompts.py` | `reviewer_typed` |
| `build_typed_writer_prompt()` | `validator/content/prompts.py` | `writer_typed` |
| `build_jury_prompt()` | `validator/content/prompts.py` | `jury` |

**Dead code / deferred / out of scope** (not refactored in this restructure):

| Python function | File | Status |
|---|---|---|
| `build_update_prompt()` | `prompts/update.py` | Deferred — target `observer` reserved for future activation |
| `build_section_reviewer_prompt()` | `validator/content/prompts.py` | Dead code — never imported, superseded by typed variant |
| `build_section_writer_prompt()` | `validator/content/prompts.py` | Dead code — never imported, superseded by typed variant |
| `build_changelog_prompt()` | `core/changelog/prompts.py` | Out of scope — different domain (changelog, not API docs) |

**Out of scope:** `build_changelog_prompt()` is a different domain (changelog, not API docs) and does not use skills. Not changed in this restructure.

**Dead code — deferred:** `build_update_prompt()` is defined but never imported by `core/`. The `observer` role and `change_notes_format` skill are **out of scope** for this restructure. They will be created when `core/update/docs.py` is refactored to use the update-specific prompt instead of re-rendering via standard pipeline. Until then, `build_update_prompt()` remains as-is (no skill injection, no refactor). The `observer` target name is reserved in the injection mapping for future use.

#### 4b. Target → skills injection

| Target | Role | Knowledge | Rules |
|--------|------|-----------|-------|
| `analyst` | analyst | dst_conventions, function_format, few_shot OR few_shot_data ¹ | format_rules, content_rules, writing_guide |
| `analyst_chunk` | analyst | dst_conventions | content_rules |
| `analyst_merge` | analyst | dst_conventions, function_format, few_shot_data | format_rules, content_rules, writing_guide |
| `analyst_intermediate` | analyst | dst_conventions | content_rules |
| `analyst_merge_legacy` | analyst | dst_conventions, function_format | format_rules, content_rules, writing_guide |
| `reviewer_full` | validator_reviewer | dst_conventions | content_rules |
| `reviewer_typed` | validator_reviewer | dst_conventions | content_rules |
| `writer_full` | validator_writer | — | — |
| `writer_typed` | validator_writer | — | — |
| `jury` | validator_jury | — | — |

**Dead code / deferred targets** (not implemented in this restructure):

| Target | Role | Knowledge | Rules | Status |
|--------|------|-----------|-------|--------|
| `observer` | observer | dst_conventions, function_format | format_rules, content_rules, writing_guide, change_notes_format | Deferred |
| `reviewer` | validator_reviewer | dst_conventions | content_rules | Dead code |
| `writer` | validator_writer | — | — | Dead code |

**Notes:**
- `analyst_chunk` outputs JSON, not markdown — no format_rules, writing_guide, or few_shot needed
- `analyst_merge` always gets `few_shot_data` (merge = large file, always has data to reference)
- `analyst_merge_legacy` is the legacy text-based merge — actively called from `core/pipeline/chunked.py:427`. Gets same skills as `analyst_merge` minus `few_shot_data` (legacy path doesn't use pre-synthesized data). Retirement of the legacy path is tracked separately — not in scope for this restructure
- `analyst_intermediate` intentionally excludes `function_format` — intermediate output is consumed by final merge, not published. Has existing TODO comment to add format spec when legacy path is retired
- ¹ `few_shot` vs `few_shot_data` selection mechanism:
  - `few_shot.md` declares `inject_into: [analyst]` only (component example, not needed in merge)
  - `few_shot_data.md` declares `inject_into: [analyst, analyst_merge]` (data config example, also useful as format reference during merge)
  - For the `analyst` target (where both match), the prompt builder uses `combine_skills("analyst", exclude=["few_shot_data"])` for component files or `exclude=["few_shot"]` for data config files, based on `_detect_file_type()`. This is exclude-based selection within a single target
  - For `analyst_merge`, only `few_shot_data` matches (no exclude needed)
- `reviewer` / `reviewer_full` / `reviewer_typed` all get `dst_conventions` and `content_rules`. This is a **new addition** for `reviewer_full` (currently `build_reviewer_prompt` only injects `_REVIEWER_SKILL`) and `reviewer_typed` (currently `build_typed_reviewer_prompt` only injects `_REVIEWER_SKILL`). For `reviewer` (`build_section_reviewer_prompt`) it replaces the `_QUALITY_RULES` injection — the "apply ONLY content accuracy rules" filter is no longer needed because `content_rules.md` contains only content-relevant rules
- **Regression risk for reviewer_full / reviewer_typed:** These are working prompts that currently produce acceptable output with only `_REVIEWER_SKILL`. Adding `dst_conventions` + `content_rules` changes the prompt content and may change reviewer behavior (more thorough but potentially more false positives). Implementation must include a before/after comparison: run validation on 2-3 existing docs with the old and new prompt, diff the reviewer outputs to confirm no regression
- `writer` / `writer_typed` only receive their role skill — **intentionally no knowledge or rules**. The writer receives the Lua source code + reviewer feedback as context in the prompt itself. Its job is to apply targeted patches (old_text → new_text), not to judge correctness. Adding `dst_conventions` or `content_rules` risks the writer second-guessing the reviewer or making unsolicited changes beyond the feedback. The reviewer is the authority on what to fix; the writer is the executor. If a patch is wrong because the writer lacks DST knowledge, the fix is to improve the reviewer's feedback specificity, not to add knowledge to the writer.
- `jury` only receives its role skill — voting instructions are self-contained

### 5. Loader API (`prompts/src/prompts/skills_loader.py` — rewritten)

The loader stays in the `prompts` package (importable as `prompts.skills_loader`). Implementation is fully rewritten to scan `skills/` subdirectories instead of parsing `docs_SKILL.md`.

```python
# Primary API
combine_skills(target: str, *, exclude: list[str] | None = None) -> str
    # Returns single concatenated string of all skills matching target
    # Ordered deterministically: role → knowledge → rules
    # exclude: skip specific skills by name

# Lower-level API (for advanced use cases)
load_skills_for(target: str, *, exclude: list[str] | None = None) -> dict[str, str]
    # Returns {name: content} for all skills matching target

load_skill(name: str) -> str
    # Load single skill by name (backward compat)
```

**Implementation:**
- On first call, scan `skills/roles/`, `skills/knowledge/`, `skills/rules/` directories
- Parse YAML frontmatter from each `.md` file
- Build registry: `{name: {content, inject_into, path, group}}`
- `group` derived from subdirectory: `roles/` → 0, `knowledge/` → 1, `rules/` → 2
- Cache at module level (scan once per process)
- `combine_skills()` concatenates in deterministic order: role (0) → knowledge (1) → rules (2)
- **Within-group ordering:** sorted alphabetically by `name` field from frontmatter. This ensures identical output regardless of filesystem scan order (ext4 vs NTFS vs APFS). Example for `analyst` target: `analyst` (role) → `dst_conventions`, `few_shot`, `function_format` (knowledge, alphabetical) → `content_rules`, `format_rules`, `writing_guide` (rules, alphabetical)
- **Separator between skills:** each skill block is preceded by `=== SKILL: {name} ===\n` and followed by `\n\n`. This provides clear visual separation for the LLM and makes it easy to grep prompt output for debugging
- **Content extraction:** strip the entire YAML frontmatter block (`---\n...\n---\n`) from raw file content before injection. The frontmatter contains `inject_into`, `description`, etc. — metadata for the loader, not for the LLM. After stripping frontmatter, also strip the `# Skill Title` header line if present (same as current loader behavior with `# Skill:`). The remaining body text is the skill content that gets wrapped with the separator above
- `exclude` uses `None` default (not mutable `[]`) — internally `exclude = exclude or []`

**Name resolution:** Lookup is path-agnostic — `load_skill("dst_conventions")` resolves by `name` field in frontmatter regardless of which subdirectory the file lives in. No path prefix needed.

**Error behavior:**
- `combine_skills("unknown_target")` → returns empty string `""` **and logs `WARNING`**: `"combine_skills('unknown_target') matched 0 skills — possible typo in target name"`. A typo in target name would silently degrade LLM output with no error; the warning makes this visible in logs without breaking the call chain
- `combine_skills("analyst", exclude=["nonexistent"])` → silently ignores unknown exclude names (no error)
- `load_skill("nonexistent_name")` → raises `KeyError` (same as current behavior)
- Duplicate `name` values across files → raises `ValueError` at scan time with both file paths (fail fast, don't silently shadow)

**Cache and test isolation:**
- Module-level `_registry: dict | None = None` — populated on first call, reused thereafter
- Expose `_clear_cache()` for test isolation — resets `_registry = None` so next call re-scans
- `combine_skills()` and `load_skills_for()` also accept `_registry_override: dict | None = None` (underscore-prefixed = test-only) to inject a mock registry without touching the module cache
- Tests must call `_clear_cache()` in teardown (or use `_registry_override`) to prevent cross-test leakage

**Backward compatibility:**
- `prompts/__init__.py` continues to re-export `load_skill` and `load_skills_for` — no import breakage
- `load_skill(name)` still works for individual skill access
- New `combine_skills()` is the recommended API for prompt builders

### 6. Prompt Builder Changes

Prompt builders become thin templates — only context sections + output skeleton + `{skills_block}`:

**What stays inline in prompt templates:**
- Context sections: file tree, target file, connected files, source code (dynamic data)
- Output YAML skeleton with dynamic values (id, title, version, date, hash)
- Response format JSON schema for reviewer/writer/jury (structural contract)

**What moves entirely to skills (deleted from inline):**
- All rules (MDX, section order, headings, completeness, error states definition...)
- Role definitions and task descriptions
- Few-shot examples
- Function format spec
- Change notes format
- DST conventions

**Example — `standard.py` after refactor:**

```python
from prompts.skills_loader import combine_skills

def build_prompt(
    comp_name, comp_title, display_filepath, lua_code,
    connected_section, connected_content="", source_hash="",
    *, file_tree="", today_date="", version="", category_type="",
) -> str:
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

=== SOURCE CODE ===
{lua_code}"""
```

### 7. Content Corrections

When splitting `quality_rules.md` and resolving contradictions, these are the authoritative decisions:

| Contradiction | Resolution | Goes into |
|---|---|---|
| Error states: "document nil returns" vs "do NOT list nil returns" | `function_format.md` wins — Error states = crash/corruption only | `knowledge/function_format.md` |
| Getters/setters: "skip trivial" vs "keep ALL" | `quality_rules.md` wins — Keep ALL functions | `rules/content_rules.md` |
| Few-shot error states example contradicts definition | Fix: replace `Returns early with no effect if duration <= 0` with actual crash scenario, e.g. `Errors if self.inst is nil when Activate() calls self.inst:AddTag() — no nil guard present` | `knowledge/few_shot.md` |

**`content_rules.md` eliminates the need for filtering instructions:** Currently `build_section_reviewer_prompt` (dead code — not refactored, see Files Changed) injects `_QUALITY_RULES` with the inline instruction "apply ONLY content accuracy rules... IGNORE format rules." This filter existed because `quality_rules.md` mixed format and content rules. After the split, `content_rules.md` contains ONLY content-relevant rules — no format rules to ignore. The active reviewer functions (`build_reviewer_prompt`, `build_typed_reviewer_prompt`) that are being refactored will inject `content_rules` directly, with no filtering instruction needed. Adding `content_rules` to `reviewer_typed` is a deliberate new addition — `build_typed_reviewer_prompt` currently only uses `_REVIEWER_SKILL`.

**`validator_reviewer.md` deduplication:** The current reviewer skill has overlap with `quality_rules.md` in areas like "Keep ALL functions" and section content requirements. After the split:
- Content completeness rules (keep all functions, merge entries, etc.) → `content_rules.md`
- Reviewer-specific checklist, response format guidance, special_case logic → stays in `validator_reviewer.md`
- Section-specific requirements (`=== SECTION ## Heading ===` blocks) → stays in `validator_reviewer.md` (these are reviewer instructions, not general content rules)

### 8. Context Preservation Guarantees

The restructure must NOT degrade LLM context quality:

1. **No information loss** — every rule/instruction in current inline prompts must exist in a skill file. **Verification:** after implementation, diff the output of each prompt builder (old vs new) on a reference input to confirm all instructions are present. Create a test that calls each prompt builder and asserts key phrases from the old inline rules appear in the combined output.
2. **Deterministic ordering** — `combine_skills()` always returns: role → knowledge → rules (matching current implicit order in prompts)
3. **Contradiction resolution** — when inline and skill conflict, skill file is source of truth (see section 7)
4. **Response format contracts preserved** — JSON schemas for reviewer/writer/jury stay inline in prompt builders

### 9. Implementation Order

The restructure touches many files simultaneously. To avoid leaving the system in a broken state if interrupted:

1. **Phase 1 — Loader rewrite (no breaking changes):** Rewrite `skills_loader.py` to support both old format and new format. Add `combine_skills()` API. Add `_clear_cache()`. Update `__init__.py` re-exports. Run existing tests — they must pass against the old skill files. **Detection logic:** check if `skills/roles/` directory exists → if yes, use new format (scan subdirs for YAML frontmatter). If no, fallback to old format (parse `docs_SKILL.md`). No merge of both — exactly one path runs. **Why dual-format:** The sole purpose is to keep existing tests and prompt builders working during the transition window (Phase 1 → Phase 2). This is a temporary bridge — do not over-engineer. In Phase 2, creating `skills/roles/` flips the switch, and old-format code path + `docs_SKILL.md` are deleted together in Phase 2's cleanup.
2. **Phase 2 — Create new skill files + move existing ones:** Create `skills/roles/`, `skills/knowledge/`, `skills/rules/` directories. Move existing files into subdirs with YAML frontmatter added. Create new files (`analyst.md`, `format_rules.md`, `content_rules.md`, `writing_guide.md`). Delete `docs_SKILL.md` and `quality_rules.md`. Delete old-format code path from loader. **Validation gate before proceeding to Phase 3:** assert `combine_skills(target)` returns non-empty for every active target (`analyst`, `analyst_chunk`, `analyst_merge`, `analyst_intermediate`, `analyst_merge_legacy`, `reviewer_full`, `reviewer_typed`, `writer_full`, `writer_typed`, `jury`) and that each result contains the expected skill names from the injection mapping table 4b. This catches partial-state bugs (e.g., Phase 2 interrupted after creating `roles/` but before moving knowledge files).
3. **Phase 3 — Refactor prompt builders:** Before starting, run `grep -r "_FUNCTION_FORMAT_SPEC\|_QUALITY_RULES\|_DST_CONV\|_REVIEWER_SKILL\|_WRITER_SKILL\|_JURY_SKILL\|_FEW_SHOT\|load_skill\|load_skills_for" prompts/ validator/` to get an exhaustive list of all files that reference skills. Use this as the checklist — no surprises in CI. Then update each prompt builder one at a time to use `combine_skills()`. After each builder, run its tests to verify output. Fix content contradictions (error states, getters/setters, few-shot example). **Verify guarantee #4:** for reviewer/writer/jury builders, assert the JSON response format schema still appears verbatim in the prompt output (these schemas must stay inline, not be moved to skills).
4. **Phase 4 — Regression check on reviewer prompts:** Run validation on 2-3 existing docs with old and new reviewer prompts. Diff outputs. Adjust `content_rules.md` if false positive rate increases.

Each phase is independently testable. If interrupted after phase N, phases 1..N are complete and the system works.

---

## Files Changed

### New files (create)
- `skills/roles/analyst.md`
- `skills/rules/format_rules.md`
- `skills/rules/content_rules.md`
- `skills/rules/writing_guide.md`

### New files (deferred — created when build_update_prompt is activated)
- `skills/roles/observer.md`
- `skills/rules/change_notes_format.md`

### Modified files (refactor)
- `prompts/src/prompts/skills_loader.py` — **full rewrite**: scan `skills/` subdirs + parse YAML frontmatter instead of parsing `docs_SKILL.md`. Add `combine_skills()` API. Keep `load_skill()` and `load_skills_for()` for backward compat.
- `prompts/src/prompts/__init__.py` — add `combine_skills` to re-exports
- `skills/roles/validator_reviewer.md` — remove duplicated content rules, add frontmatter, keep section-specific requirements and special_case logic
- `skills/roles/validator_writer.md` — add frontmatter
- `skills/roles/validator_jury.md` — add frontmatter
- `skills/knowledge/dst_conventions.md` — add frontmatter
- `skills/knowledge/function_format.md` — add frontmatter, fix error states definition clarity
- `skills/knowledge/few_shot.md` — add frontmatter, fix error states example
- `skills/knowledge/few_shot_data.md` — add frontmatter
- `prompts/src/prompts/standard.py` — replace inline rules with `combine_skills("analyst")`
- `prompts/src/prompts/chunked.py` — replace inline in `build_chunk_prompt` with `combine_skills("analyst_chunk")`, `build_merge_prompt` with `combine_skills("analyst_merge")`, `build_intermediate_merge_prompt` with `combine_skills("analyst_intermediate")`, `_build_merge_prompt_legacy` with `combine_skills("analyst_merge_legacy")`
- `prompts/src/prompts/update.py` — **(deferred)** no changes until `build_update_prompt` is activated
- `validator/src/validator/content/prompts.py` — replace cherry-pick `load_skill()` calls with `combine_skills()` for 5 active prompt builder functions: `build_reviewer_prompt`, `build_writer_prompt`, `build_typed_reviewer_prompt`, `build_typed_writer_prompt`, `build_jury_prompt`. Remove "apply ONLY content accuracy rules, IGNORE format rules" filtering instruction (no longer needed after split). **Do NOT touch** `build_section_reviewer_prompt` and `build_section_writer_prompt` — they are dead code (never imported) and touching them creates diff noise and regression risk for no benefit.

### Deleted files
- `skills/docs_SKILL.md` — replaced by self-describing frontmatter
- `skills/quality_rules.md` — split into format_rules + content_rules + writing_guide

### Moved files (into subdirectories)
- `skills/dst_conventions.md` → `skills/knowledge/dst_conventions.md`
- `skills/function_format.md` → `skills/knowledge/function_format.md`
- `skills/few_shot.md` → `skills/knowledge/few_shot.md`
- `skills/few_shot_data.md` → `skills/knowledge/few_shot_data.md`
- `skills/validator_reviewer.md` → `skills/roles/validator_reviewer.md`
- `skills/validator_writer.md` → `skills/roles/validator_writer.md`
- `skills/validator_jury.md` → `skills/roles/validator_jury.md`

### Test files (update)
- `prompts/tests/test_skills_loader.py` — rewrite to test new loader (scan dirs + YAML frontmatter + `combine_skills()`, `_clear_cache()`, error behavior, within-group ordering)
- Update test files for **all** refactored prompt builders — any test that asserts on prompt output content will need updating since inline rules are replaced by skill injection. Known files: `prompts/tests/test_chunk_prompts.py` (imports `_FUNCTION_FORMAT_SPEC`), and any test files under `prompts/tests/` or `validator/tests/` that call prompt builder functions or assert on their output strings
