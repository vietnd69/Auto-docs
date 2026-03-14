# Chunk Pipeline Quality Fixes — Design Spec

**Date:** 2026-03-14
**Status:** Approved
**Scope:** `chunked_prompt.py`, `pre_synthesis.py`, `chunked_olm.py`

---

## Problem Statement

The chunked documentation pipeline produces output with 4 quality defects, all confirmed in `actions.md`:

1. **YAML `tags` bloat** — 100+ raw game-engine tags (e.g. `CLASSIFIED`, `abigail_flower`) appear in the YAML frontmatter instead of 2-5 doc-search categories.
2. **Wrong `system_scope`** — Majority-voted from chunk LLM guesses, locked before the merge LLM sees the full picture. `actions.lua` receives `inventory` instead of a representative scope.
3. **Missing External dependencies** — `_FUNCTION_FORMAT_SPEC` has no `External dependencies` slot. `require()` calls and DST globals (`TheWorld`, `TheNet`, etc.) are not captured anywhere in the output.
4. **Missing `## Events & listeners`** — When pre-extracted events JSON is empty, the merge LLM silently drops the required section.

### Root cause

`pre_synthesis.py` conflates two different concepts:
- **Game tags** (`HasTag`/`AddTag`/`RemoveTag` calls in Lua) — belong in the Dependencies section body.
- **Doc-category tags** (2-5 search keywords for YAML frontmatter) — should be written by the merge LLM from the Overview.

Both currently flow into `presynthesis.tags` → YAML frontmatter, and the merge LLM is instructed to copy them verbatim.

---

## Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Fix layer | Schema-level (chunked_prompt + pre_synthesis) | Prompt-only fixes are unreliable for structural issues |
| Backward compat for checkpoints | None (delete manually) | Checkpoints are transient dev artifacts |
| Doc-category tags source | Merge LLM writes freely from Overview | Simpler than chunk-level suggestion; merge LLM has full context |
| External deps taxonomy | Flat `{name, usage}` — captures `require()` + DST globals | Richer type taxonomy causes chunk LLM classification errors |
| Events section guarantee | Python post-processor in `chunked_olm.py` | 100% reliable; no LLM re-call needed |

---

## Design

### Data flow (after)

```
Chunk LLM → JSON {
  game_tags: [{name, operation}],
  external_deps: [{name, usage}]
}
              ↓
pre_synthesis → presynthesis.game_tags   (→ Dependencies body only)
                presynthesis.external_deps
                presynthesis.system_scope  (advisory hint, not lock)
                // presynthesis.tags REMOVED
              ↓
build_merge_prompt →
  YAML tags: <WRITE 2-5 from Overview>
  system_scope: <REVIEW hint, set best value>
  external_deps JSON → ## Dependencies & tags
  game_tags JSON    → ## Dependencies & tags
              ↓
merge LLM output
              ↓
_ensure_events_section() → guarantee ## Events & listeners present
              ↓
write to disk
```

---

## File Changes

### 1. `chunked_prompt.py` — `build_chunk_prompt()`

**JSON schema: rename field**
```
"tags" → "game_tags"
```
Structure unchanged: `[{"name": "<tag_name>", "operation": "<add|remove|check>"}]`

**JSON schema: add field**
```json
"external_deps": [
  {"name": "<module or global name>", "usage": "<how it is used in this chunk>"}
]
```

**Extraction rule added to chunk prompt:**
> Capture `require("module")` calls AND any reference to DST globals: `TheWorld`, `TheNet`, `ThePlayer`, `GLOBAL`, `AllPlayers`, `TheSim`, `TheInput`, `TheCamera`. For each, write a short description of how it is used in this chunk. Use empty array `[]` if none found.

**Field rules update:**
- Remove rule for `tags`
- Add rule for `game_tags`: same extraction logic as old `tags`
- Add rule for `external_deps`: as above

---

### 2. `chunked_prompt.py` — `build_merge_prompt()`

**Remove:**
```python
tags_yaml = ", ".join(presynthesis.tags)
```

**Add:**
```python
game_tags_json    = json.dumps(presynthesis.game_tags, indent=2, ensure_ascii=False)
external_deps_json = json.dumps(presynthesis.external_deps, indent=2, ensure_ascii=False)
```

**YAML frontmatter template change:**
```
# Before
tags: [{tags_yaml}]
system_scope: {presynthesis.system_scope}

# After
tags: <WRITE: 2-5 lowercase tags categorizing this component for docs search. Choose domain terms (e.g. [actions, combat, player]). Do NOT list game entity tags. Maximum 5 entries.>
system_scope: <REVIEW hint "{presynthesis.system_scope}" — set the most accurate value from the allowed list based on the Overview you are writing>
```

**`_FUNCTION_FORMAT_SPEC` dependency section change:**

```
# Before
=== DEPENDENCY SECTION FORMAT ===
**Components used:**
- `component_name` -- how it is used

**Tags:**
- `tag_name` -- add / remove / check

# After
=== DEPENDENCY SECTION FORMAT ===
**External dependencies:**
- `name` -- usage description
(Omit this bullet entirely if external_deps JSON is empty)

**Components used:**
- `component_name` -- how it is used

**Tags:**
- `tag_name` -- add / remove / check
```

**New JSON blocks passed to merge LLM — insertion point:**

Insert immediately after the existing `=== DEPENDENCIES (pre-extracted) ===` block (after `{deps_json}`), before `=== PROPERTIES (pre-extracted) ===`:

```
=== GAME TAGS (pre-extracted) ===
{game_tags_json}

=== EXTERNAL DEPENDENCIES (pre-extracted) ===
{external_deps_json}
```

**Instruction update:**
- Remove: `"The tags and system_scope in YAML are PRE-FILLED. Copy them exactly. Do NOT change them."`
- Add: `"Write YAML tags freely (2-5 doc-category keywords from the Overview). Review the system_scope hint and set the most accurate value."`

**Task list update** (YOUR TASKS section):
- Update task 7 to cover External dependencies as part of the same section:
  `"7. Format ## Dependencies & tags using EXACTLY the DEPENDENCY SECTION FORMAT, including External dependencies from EXTERNAL DEPENDENCIES JSON (omit External dependencies bullet if empty)."`

---

### 3. `pre_synthesis.py` — `PreSynthesisResult` + `_aggregate()`

**Updated `PreSynthesisResult` dataclass (full field order):**
```python
@dataclass
class PreSynthesisResult:
    game_tags: list[dict]              # [{name, operation}] — dedup by "name"
    external_deps: list[dict]          # [{name, usage}]     — dedup by "name"
    system_scope: str                  # majority vote, format-validated
    dependencies: list[dict]           # dedup by "component"
    partial_descriptions: list[str]    # 1 per chunk, for merge LLM
    functions: list[dict]              # flat, incomplete=False only
    events_listens: list[dict]         # dedup by "event"
    events_pushes: list[dict]          # dedup by "event"
    constructor_properties: list[dict] # dedup by "name"
```

**`_aggregate()` changes:**
```python
# Remove
tags = sorted({
    t["name"] for c in chunks
    for t in c.get("tags", [])
    if t.get("name") and t["name"] != "None"
})

# Add
game_tags = _dedup_by_key(
    [t for c in chunks for t in c.get("game_tags", []) if t.get("name") and t["name"] != "None"],
    "name"
)
external_deps = _dedup_by_key(
    [d for c in chunks for d in c.get("external_deps", []) if d.get("name") and d["name"] != "None"],
    "name"
)
```

**Updated `_aggregate()` return statement:**
```python
return PreSynthesisResult(game_tags, external_deps, scope, deps, descs, funcs, listens, pushes, props)
```

**Updated `_empty_result()` (complete call):**
```python
def _empty_result() -> PreSynthesisResult:
    return PreSynthesisResult(
        game_tags=[], external_deps=[], system_scope="entity",
        dependencies=[], partial_descriptions=[], functions=[],
        events_listens=[], events_pushes=[], constructor_properties=[]
    )
```

**`system_scope` field:** No change to `_majority_vote` logic. The value remains a majority-vote hint; only the merge prompt instruction changes to allow override.

---

### 4. `chunked_olm.py` — post-processor

**New function (module-level):**
```python
def _ensure_events_section(doc: str) -> str:
    """
    Guarantee ## Events & listeners is present in merge LLM output.
    If the section heading is absent, append a fallback block.
    """
    if "## Events & listeners" not in doc:
        doc = doc.rstrip() + "\n\n## Events & listeners\nThis file is not event-driven.\n"
    return doc
```

**Call site:** Applied inside `generate_merged_doc()`, after the empty-check guard (`if not md_content: ... continue`) and before `f.write(md_content)` (line 281 of `chunked_olm.py`). It must go AFTER the empty guard — if placed before, an empty LLM response would receive the fallback block, turn non-empty, bypass the retry, and write a malformed document.

```python
md_content = clean_model_output(md_content)

# ... existing empty-check guard (if not md_content: ... continue) ...

md_content = _ensure_events_section(md_content)   # ← correct position
with open(md_filepath, "w", encoding="utf-8") as f:
    f.write(md_content)
```

**Additional required change in `chunked_olm.py`:** The log line at line 709 references `presynthesis.tags`, which is removed by this spec:

```python
# Before (line 709)
print(f"  [PRE-SYNTHESIS] OK — {len(presynthesis.tags)} tags, "
      f"{len(presynthesis.functions)} functions, "
      f"scope={presynthesis.system_scope}")

# After
print(f"  [PRE-SYNTHESIS] OK — {len(presynthesis.game_tags)} game_tags, "
      f"{len(presynthesis.external_deps)} external_deps, "
      f"{len(presynthesis.functions)} functions, "
      f"scope={presynthesis.system_scope}")
```

---

## Out of Scope

- `prompt.py` / `olm.py` — standard (non-chunked) pipeline is unaffected
- `main.py`, `get_docs.py`, `chunked.py`, `config.py` — no changes
- Checkpoint migration — old `.checkpoint` files should be deleted manually before the next run
- `build_intermediate_merge_prompt()` — legacy function, not used in JSON pipeline; no changes
- `_build_merge_prompt_legacy()` — legacy function; no changes

---

## Acceptance Criteria

1. `actions.md` YAML `tags:` contains 2-5 domain keywords, not 100+ game tags.
2. `actions.md` YAML `system_scope:` reflects the merge LLM's assessment of the full component.
3. `actions.md` `## Dependencies & tags` includes an `**External dependencies:**` bullet listing `require()` calls and DST globals used.
4. `actions.md` ends with a `## Events & listeners` section (even if body is "This file is not event-driven.").
5. Running the chunked pipeline on a file that is under 32K tokens (standard pipeline path) produces output identical to before these changes — because `prompt.py`, `olm.py`, and `main.py` are untouched.
6. `PreSynthesisResult` has no `tags` field; has `game_tags` and `external_deps`.
