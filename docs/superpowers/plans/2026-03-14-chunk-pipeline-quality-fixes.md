# Chunk Pipeline Quality Fixes — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix 4 output quality defects in the chunked LLM documentation pipeline: YAML tags bloat, wrong `system_scope`, missing External dependencies section, and missing `## Events & listeners` section.

**Architecture:** Schema-level fix — rename `tags` → `game_tags` and add `external_deps` to chunk JSON; remove `presynthesis.tags` from YAML; let merge LLM write YAML tags and review scope; add a Python post-processor that guarantees the Events section is present.

**Tech Stack:** Python 3, dataclasses, json stdlib. No new dependencies. Tests use project's custom test runner (`python test_*.py`).

**Spec:** `docs/superpowers/specs/2026-03-14-chunk-pipeline-quality-fixes-design.md`

---

## File Map

**Modified:**
- `pre_synthesis.py` — `PreSynthesisResult` dataclass (remove `tags`, add `game_tags`/`external_deps`), `_aggregate()`, `_empty_result()`
- `chunked_olm.py` — log line at line 709, new `_ensure_events_section()` function, call site in `generate_merged_doc()`
- `chunked_prompt.py` — chunk JSON schema in `build_chunk_prompt()`, `_FUNCTION_FORMAT_SPEC`, `build_merge_prompt()` variables + template

**Created:**
- `test_pre_synthesis.py` — unit tests for aggregation changes
- `test_events_section.py` — unit tests for `_ensure_events_section()`
- `test_chunk_prompts.py` — structural verification of prompt string changes

---

## Chunk 1: `pre_synthesis.py` — Dataclass and aggregation

### Task 1: Write failing tests for `pre_synthesis.py`

**Files:**
- Create: `test_pre_synthesis.py`

- [ ] **Step 1: Create `test_pre_synthesis.py`**

```python
"""
Tests for pre_synthesis.py schema changes:
- tags field removed, game_tags + external_deps added
- _aggregate() reads from game_tags / external_deps keys
- _empty_result() has correct defaults
Run: python test_pre_synthesis.py
"""
import sys, os, json
sys.path.insert(0, os.path.dirname(__file__))

from pre_synthesis import pre_synthesize, _empty_result

passed = 0
failed = 0

def test(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} — {msg}")
        failed += 1


def _chunk(**kwargs):
    """Build a minimal valid chunk JSON dict."""
    base = {
        "partial_description": "test chunk",
        "suggested_scope": "entity",
        "constructor_properties": [],
        "functions": [],
        "events": {"listens_to": [], "pushes": []},
        "dependencies": [],
        "game_tags": [],
        "external_deps": [],
    }
    base.update(kwargs)
    return json.dumps(base)


# ── _empty_result ──────────────────────────────────────────────
print("\n── _empty_result() ──")

result = _empty_result()

test("no 'tags' attribute",
     not hasattr(result, "tags"),
     "PreSynthesisResult still has deprecated 'tags' field")

test("has 'game_tags' attribute",
     hasattr(result, "game_tags"),
     "game_tags field missing")

test("has 'external_deps' attribute",
     hasattr(result, "external_deps"),
     "external_deps field missing")

test("game_tags default is []",
     result.game_tags == [],
     f"got {result.game_tags!r}")

test("external_deps default is []",
     result.external_deps == [],
     f"got {result.external_deps!r}")

test("system_scope default is 'entity'",
     result.system_scope == "entity",
     f"got {result.system_scope!r}")


# ── pre_synthesize: game_tags ──────────────────────────────────
print("\n── pre_synthesize: game_tags ──")

chunks_game_tags = {
    1: _chunk(game_tags=[
        {"name": "player", "operation": "check"},
        {"name": "fire", "operation": "check"},
    ]),
    2: _chunk(game_tags=[
        {"name": "fire", "operation": "add"},   # duplicate name — should be deduped
        {"name": "heavy", "operation": "check"},
    ]),
}
r, malformed = pre_synthesize(chunks_game_tags)

test("no malformed chunks", malformed == [], f"malformed: {malformed}")

names = {t["name"] for t in r.game_tags}
test("game_tags: all unique names collected",
     names == {"player", "fire", "heavy"},
     f"got names {names}")

fire_entries = [t for t in r.game_tags if t["name"] == "fire"]
test("game_tags: 'fire' deduped to one entry",
     len(fire_entries) == 1,
     f"got {len(fire_entries)} entries for 'fire'")

test("game_tags: first-seen operation preserved for 'fire'",
     fire_entries[0]["operation"] == "check",
     f"got {fire_entries[0]['operation']!r}")


# ── pre_synthesize: external_deps ─────────────────────────────
print("\n── pre_synthesize: external_deps ──")

chunks_ext = {
    1: _chunk(external_deps=[
        {"name": "TheWorld", "usage": "TheWorld:HasTag() — checks world state"},
        {"name": "class",    "usage": "Class() constructor"},
    ]),
    2: _chunk(external_deps=[
        {"name": "TheWorld", "usage": "duplicate — should be discarded"},
        {"name": "TheNet",   "usage": "TheNet:GetIsServer()"},
    ]),
}
r2, malformed2 = pre_synthesize(chunks_ext)

test("no malformed chunks", malformed2 == [], f"malformed: {malformed2}")

ext_names = {d["name"] for d in r2.external_deps}
test("external_deps: all unique names collected",
     ext_names == {"TheWorld", "class", "TheNet"},
     f"got {ext_names}")

theworld = next((d for d in r2.external_deps if d["name"] == "TheWorld"), None)
test("external_deps: first-seen usage preserved for TheWorld",
     theworld is not None and theworld["usage"].startswith("TheWorld:HasTag()"),
     f"got {theworld!r}")


# ── pre_synthesize: old 'tags' key silently ignored ────────────
print("\n── pre_synthesize: backward compatibility ──")

chunk_old_format = {
    "partial_description": "old format chunk",
    "suggested_scope": "entity",
    "constructor_properties": [],
    "functions": [],
    "events": {"listens_to": [], "pushes": []},
    "dependencies": [],
    "game_tags": [],
    "external_deps": [],
    "tags": [{"name": "legacy_tag", "operation": "check"}],  # old key
}
r3, m3 = pre_synthesize({1: json.dumps(chunk_old_format)})

test("old 'tags' key in chunk JSON does not populate game_tags",
     r3.game_tags == [],
     f"game_tags unexpectedly populated: {r3.game_tags}")


# ── pre_synthesize: None-filtered entries ─────────────────────
print("\n── pre_synthesize: None filtering ──")

chunks_none = {
    1: _chunk(
        game_tags=[{"name": "None", "operation": "check"}],
        external_deps=[{"name": "None", "usage": "None"}],
    ),
}
r4, _ = pre_synthesize(chunks_none)
test("game_tags: 'None' string filtered out",
     r4.game_tags == [],
     f"got {r4.game_tags}")
test("external_deps: 'None' string filtered out",
     r4.external_deps == [],
     f"got {r4.external_deps}")


# ── summary ───────────────────────────────────────────────────
print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd d:/code/mod-document && .venv/Scripts/python test_pre_synthesis.py
```

Expected: multiple `[FAIL]` lines including "no 'tags' attribute", "has 'game_tags' attribute", "has 'external_deps' attribute". The script may also raise `AttributeError`. That is correct — the tests are failing because the code hasn't been changed yet.

---

### Task 2: Update `pre_synthesis.py`

**Files:**
- Modify: `pre_synthesis.py`

- [ ] **Step 1: Update `PreSynthesisResult` dataclass**

In `pre_synthesis.py`, replace lines 23-31:

```python
# BEFORE
@dataclass
class PreSynthesisResult:
    tags: list[str]                    # dedup, sorted
    system_scope: str                  # majority vote, format-validated
    dependencies: list[dict]           # dedup by "component"
    partial_descriptions: list[str]    # 1 per chunk, for merge LLM
    functions: list[dict]              # flat, incomplete=False only
    events_listens: list[dict]         # dedup by "event"
    events_pushes: list[dict]          # dedup by "event"
    constructor_properties: list[dict] # dedup by "name"
```

```python
# AFTER
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

- [ ] **Step 2: Update `_aggregate()`**

In `_aggregate()`, replace the `tags = sorted({...})` block:

```python
# BEFORE (remove this block)
tags = sorted({
    t["name"] for c in chunks
    for t in c.get("tags", [])
    if t.get("name") and t["name"] != "None"
})
```

```python
# AFTER (replace with these two lines)
game_tags = _dedup_by_key(
    [t for c in chunks for t in c.get("game_tags", [])
     if t.get("name") and t["name"] != "None"],
    "name"
)
external_deps = _dedup_by_key(
    [d for c in chunks for d in c.get("external_deps", [])
     if d.get("name") and d["name"] != "None"],
    "name"
)
```

- [ ] **Step 3: Update `_aggregate()` return statement**

Replace the `return PreSynthesisResult(...)` line at the end of `_aggregate()`:

```python
# BEFORE
return PreSynthesisResult(tags, scope, deps, descs, funcs, listens, pushes, props)
```

```python
# AFTER
return PreSynthesisResult(game_tags, external_deps, scope, deps, descs, funcs, listens, pushes, props)
```

- [ ] **Step 4: Update `_empty_result()`**

Replace the entire `_empty_result()` function body:

```python
# BEFORE
def _empty_result() -> PreSynthesisResult:
    return PreSynthesisResult(
        tags=[], system_scope="entity", dependencies=[],
        partial_descriptions=[], functions=[],
        events_listens=[], events_pushes=[], constructor_properties=[]
    )
```

```python
# AFTER
def _empty_result() -> PreSynthesisResult:
    return PreSynthesisResult(
        game_tags=[], external_deps=[], system_scope="entity",
        dependencies=[], partial_descriptions=[], functions=[],
        events_listens=[], events_pushes=[], constructor_properties=[]
    )
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
cd d:/code/mod-document && .venv/Scripts/python test_pre_synthesis.py
```

Expected output:
```
── _empty_result() ──
  [PASS] no 'tags' attribute
  [PASS] has 'game_tags' attribute
  [PASS] has 'external_deps' attribute
  [PASS] game_tags default is []
  [PASS] external_deps default is []
  [PASS] system_scope default is 'entity'
...
Results: 16 passed, 0 failed
```

If any test fails, read the `[FAIL]` message and fix the corresponding code in `pre_synthesis.py` before continuing.

- [ ] **Step 6: Commit**

```bash
cd d:/code/mod-document && git add pre_synthesis.py test_pre_synthesis.py && git commit -m "$(cat <<'EOF'
feat: replace tags with game_tags + external_deps in PreSynthesisResult

Removes the conflated `tags` field (game-engine tags) from the
dataclass and YAML pipeline. Adds `game_tags` (for the Dependencies
body) and `external_deps` (for External dependencies bullet).
Fixes YAML tags bloat defect in chunked pipeline output.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 2: `chunked_olm.py` — Log line and post-processor

### Task 3: Fix log line referencing removed `presynthesis.tags`

**Files:**
- Modify: `chunked_olm.py:709`

- [ ] **Step 1: Update the log line**

In `chunked_olm.py`, find and replace line 709:

```python
# BEFORE (line 709)
print(f"  [PRE-SYNTHESIS] OK — {len(presynthesis.tags)} tags, "
      f"{len(presynthesis.functions)} functions, "
      f"scope={presynthesis.system_scope}")
```

```python
# AFTER
print(f"  [PRE-SYNTHESIS] OK — {len(presynthesis.game_tags)} game_tags, "
      f"{len(presynthesis.external_deps)} external_deps, "
      f"{len(presynthesis.functions)} functions, "
      f"scope={presynthesis.system_scope}")
```

- [ ] **Step 2: Verify import chain still works**

```bash
cd d:/code/mod-document && .venv/Scripts/python -c "from chunked_olm import generate_merged_doc; print('OK')"
```

Expected: `OK`

---

### Task 4: Write failing tests for `_ensure_events_section()`

**Files:**
- Create: `test_events_section.py`

- [ ] **Step 1: Create `test_events_section.py`**

```python
"""
Tests for _ensure_events_section() in chunked_olm.py.
Run: python test_events_section.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from chunked_olm import _ensure_events_section

passed = 0
failed = 0

def test(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} — {msg}")
        failed += 1


print("\n── _ensure_events_section() ──")

# Case 1: section already present — document unchanged
doc_with_section = (
    "## Overview\nfoo\n\n"
    "## Events & listeners\n- **Listens to:** x\n"
)
result = _ensure_events_section(doc_with_section)
test("section present: document unchanged",
     result == doc_with_section,
     f"document was modified unexpectedly")

test("section present: no double-append",
     result.count("## Events & listeners") == 1,
     f"section appears {result.count('## Events & listeners')} times")

# Case 2: section absent — fallback appended
doc_without = "## Overview\nfoo\n\n## Main functions\nbar\n"
result2 = _ensure_events_section(doc_without)
test("section absent: heading appended",
     "## Events & listeners" in result2,
     "heading not found in output")
test("section absent: fallback body appended",
     "This file is not event-driven." in result2,
     "fallback body not found in output")
test("section absent: appended at end (after original content)",
     result2.startswith(doc_without.rstrip()),
     f"start of result unexpected: {result2[:60]!r}")

# Case 3: empty string — fallback appended
result3 = _ensure_events_section("")
test("empty input: heading appended",
     "## Events & listeners" in result3,
     "heading not found")
test("empty input: fallback body appended",
     "This file is not event-driven." in result3,
     "body not found")

# Case 4: heading present at very start of document
doc_at_start = "## Events & listeners\nsome content\n"
result4 = _ensure_events_section(doc_at_start)
test("section at start: document unchanged",
     result4 == doc_at_start,
     "document was modified")

# Case 5: heading present but with empty body — still unchanged
doc_empty_body = "## Overview\nfoo\n\n## Events & listeners\n\n## Properties\n"
result5 = _ensure_events_section(doc_empty_body)
test("section with empty body: document unchanged",
     result5 == doc_empty_body,
     "document was modified")


print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd d:/code/mod-document && .venv/Scripts/python test_events_section.py
```

Expected: `ImportError: cannot import name '_ensure_events_section' from 'chunked_olm'`. That is correct — the function doesn't exist yet.

---

### Task 5: Implement `_ensure_events_section()` and call site

**Files:**
- Modify: `chunked_olm.py`

- [ ] **Step 1: Add `_ensure_events_section()` as a module-level function**

Add this function near the top of `chunked_olm.py`, after the imports and before the first function definition:

```python
def _ensure_events_section(doc: str) -> str:
    """
    Guarantee ## Events & listeners is present in merge LLM output.
    If the heading is absent, append a minimal fallback block.
    Must be called AFTER the empty-content guard in generate_merged_doc().
    """
    if "## Events & listeners" not in doc:
        doc = doc.rstrip() + "\n\n## Events & listeners\nThis file is not event-driven.\n"
    return doc
```

- [ ] **Step 2: Run tests — expect PASS**

```bash
cd d:/code/mod-document && .venv/Scripts/python test_events_section.py
```

Expected: all `[PASS]`, `Results: 10 passed, 0 failed`.

- [ ] **Step 3: Add the call site in `generate_merged_doc()`**

In `generate_merged_doc()`, locate the section (around line 262-282):

```python
md_content = response["message"]["content"]
md_content = clean_model_output(md_content)

# Guard: model returned empty (only a thinking block or error)
if not md_content:
    print(f"    [Merge] Attempt {attempt}/{max_retries} — model returned empty")
    if attempt < max_retries:
        print(f"    Waiting {retry_delay} seconds before retry...")
        time.sleep(retry_delay)
    continue

# Sanity check
if not md_content.startswith("---"):
    print(f"    [Warning] Merge output does not start with YAML frontmatter!")

dir_name = os.path.dirname(md_filepath)
if dir_name:
    os.makedirs(dir_name, exist_ok=True)

with open(md_filepath, "w", encoding="utf-8") as f:
    f.write(md_content)
```

Insert `_ensure_events_section()` call AFTER the empty-content guard and BEFORE the `open()` write:

```python
md_content = response["message"]["content"]
md_content = clean_model_output(md_content)

# Guard: model returned empty (only a thinking block or error)
if not md_content:
    print(f"    [Merge] Attempt {attempt}/{max_retries} — model returned empty")
    if attempt < max_retries:
        print(f"    Waiting {retry_delay} seconds before retry...")
        time.sleep(retry_delay)
    continue

md_content = _ensure_events_section(md_content)   # ← NEW

# Sanity check
if not md_content.startswith("---"):
    print(f"    [Warning] Merge output does not start with YAML frontmatter!")

dir_name = os.path.dirname(md_filepath)
if dir_name:
    os.makedirs(dir_name, exist_ok=True)

with open(md_filepath, "w", encoding="utf-8") as f:
    f.write(md_content)
```

- [ ] **Step 4: Verify import chain still works**

```bash
cd d:/code/mod-document && .venv/Scripts/python -c "from chunked_olm import _ensure_events_section, generate_merged_doc; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd d:/code/mod-document && git add chunked_olm.py test_events_section.py && git commit -m "$(cat <<'EOF'
feat: add _ensure_events_section() post-processor and fix log line

Adds a Python-level guarantee that ## Events & listeners is always
present in merge LLM output, preventing silent omission on empty
events data. Also fixes AttributeError on removed presynthesis.tags
in the pre-synthesis log line.

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Chunk 3: `chunked_prompt.py` — Schema and merge prompt

### Task 6: Write verification tests for `chunked_prompt.py`

**Files:**
- Create: `test_chunk_prompts.py`

- [ ] **Step 1: Create `test_chunk_prompts.py`**

```python
"""
Structural verification of chunked_prompt.py changes.
Checks that prompt strings contain expected patterns after edits.
Run: python test_chunk_prompts.py
"""
import sys, os
sys.path.insert(0, os.path.dirname(__file__))

from chunked_prompt import build_chunk_prompt, build_merge_prompt, _FUNCTION_FORMAT_SPEC
from pre_synthesis import PreSynthesisResult

passed = 0
failed = 0

def test(name, condition, msg=""):
    global passed, failed
    if condition:
        print(f"  [PASS] {name}")
        passed += 1
    else:
        print(f"  [FAIL] {name} — {msg}")
        failed += 1


def _make_presynthesis(**kwargs):
    defaults = dict(
        game_tags=[{"name": "fire", "operation": "check"}],
        external_deps=[{"name": "TheWorld", "usage": "world checks"}],
        system_scope="entity",
        dependencies=[{"component": "health", "usage": "DoDelta"}],
        partial_descriptions=["test description"],
        functions=[],
        events_listens=[],
        events_pushes=[],
        constructor_properties=[],
    )
    defaults.update(kwargs)
    return PreSynthesisResult(**defaults)


# ── build_chunk_prompt ──────────────────────────────────────────
print("\n── build_chunk_prompt() schema ──")

chunk_prompt = build_chunk_prompt(
    "testcomp", "TestComp", "scripts/test.lua", "-- lua code", 1, 2
)

test("chunk prompt: 'game_tags' field in schema",
     '"game_tags"' in chunk_prompt,
     "game_tags not found in prompt")

test("chunk prompt: 'external_deps' field in schema",
     '"external_deps"' in chunk_prompt,
     "external_deps not found in prompt")

test("chunk prompt: old 'tags' field removed from schema",
     '"tags"' not in chunk_prompt,
     "old 'tags' field still present")

test("chunk prompt: extraction rule mentions TheWorld",
     "TheWorld" in chunk_prompt,
     "TheWorld not mentioned in extraction rules")

test("chunk prompt: extraction rule mentions TheNet",
     "TheNet" in chunk_prompt,
     "TheNet not mentioned in extraction rules")

test("chunk prompt: extraction rule mentions require()",
     "require" in chunk_prompt,
     "require not mentioned in extraction rules")


# ── _FUNCTION_FORMAT_SPEC ──────────────────────────────────────
print("\n── _FUNCTION_FORMAT_SPEC ──")

test("format spec: 'External dependencies' bullet present",
     "External dependencies" in _FUNCTION_FORMAT_SPEC,
     "External dependencies section missing from format spec")

test("format spec: still has 'Components used'",
     "Components used" in _FUNCTION_FORMAT_SPEC,
     "Components used section missing")

test("format spec: still has 'Tags'",
     "Tags" in _FUNCTION_FORMAT_SPEC,
     "Tags section missing")


# ── build_merge_prompt ─────────────────────────────────────────
print("\n── build_merge_prompt() ──")

presynthesis = _make_presynthesis()
merge_prompt = build_merge_prompt(
    "testcomp", "TestComp", "scripts/test.lua",
    presynthesis,
    today_date="2026-03-14", version="714014",
    category_type="root",
)

test("merge prompt: old 'copy them exactly' instruction removed",
     "Copy them exactly" not in merge_prompt,
     "old lock instruction still present")

test("merge prompt: YAML tags is a write instruction",
     "WRITE" in merge_prompt,
     "WRITE instruction for YAML tags not found")

test("merge prompt: system_scope has REVIEW hint",
     "REVIEW" in merge_prompt,
     "REVIEW hint for system_scope not found")

test("merge prompt: GAME TAGS section present",
     "GAME TAGS" in merge_prompt,
     "GAME TAGS section not found")

test("merge prompt: EXTERNAL DEPENDENCIES section present",
     "EXTERNAL DEPENDENCIES" in merge_prompt,
     "EXTERNAL DEPENDENCIES section not found")

test("merge prompt: game_tags data injected (fire tag visible)",
     '"fire"' in merge_prompt,
     "fire tag not found in merge prompt")

test("merge prompt: external_deps data injected (TheWorld visible)",
     "TheWorld" in merge_prompt,
     "TheWorld not found in merge prompt")

test("merge prompt: GAME TAGS block appears after DEPENDENCIES block",
     merge_prompt.index("GAME TAGS") > merge_prompt.index("DEPENDENCIES (pre-extracted)"),
     "GAME TAGS not positioned after DEPENDENCIES")

test("merge prompt: GAME TAGS block appears before PROPERTIES block",
     merge_prompt.index("GAME TAGS") < merge_prompt.index("PROPERTIES (pre-extracted)"),
     "GAME TAGS not positioned before PROPERTIES")


# ── empty external_deps ────────────────────────────────────────
print("\n── build_merge_prompt() with empty external_deps ──")

presynthesis_no_ext = _make_presynthesis(external_deps=[])
merge_prompt_no_ext = build_merge_prompt(
    "testcomp", "TestComp", "scripts/test.lua",
    presynthesis_no_ext,
    today_date="2026-03-14", version="714014",
    category_type="root",
)
test("empty external_deps: prompt still generated (no crash)",
     len(merge_prompt_no_ext) > 100,
     "prompt unexpectedly short or empty")


# ── ordering and structural completeness ──────────────────────
print("\n── merge prompt ordering ──")

# Confirm EXTERNAL DEPENDENCIES is positioned between GAME TAGS and PROPERTIES
test("merge prompt: EXTERNAL DEPENDENCIES between GAME TAGS and PROPERTIES",
     merge_prompt.index("EXTERNAL DEPENDENCIES") > merge_prompt.index("GAME TAGS") and
     merge_prompt.index("EXTERNAL DEPENDENCIES") < merge_prompt.index("PROPERTIES (pre-extracted)"),
     "EXTERNAL DEPENDENCIES not positioned between GAME TAGS and PROPERTIES")

# Confirm bare system_scope line (old format: "system_scope: entity") is gone.
# New format: system_scope: <REVIEW hint "entity" — ...> which does NOT match "system_scope: entity\n"
test("merge prompt: bare pre-filled system_scope line removed",
     f"system_scope: {presynthesis.system_scope}\n" not in merge_prompt,
     "bare pre-filled system_scope line still present")

# Confirm task 7 in YOUR TASKS section references External dependencies.
# "Copy them exactly" exact casing confirmed from source line 383: "Copy them exactly."
test("merge prompt: 'Copy them exactly' instruction removed",
     "Copy them exactly" not in merge_prompt,
     "old lock instruction still present (casing: 'Copy them exactly')")

test("merge prompt: task 7 references External dependencies",
     "External dependencies" in merge_prompt and "EXTERNAL DEPENDENCIES JSON" in merge_prompt,
     "task 7 not updated to reference External dependencies")


print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
if failed:
    sys.exit(1)
```

- [ ] **Step 2: Run tests — expect FAIL**

```bash
cd d:/code/mod-document && .venv/Scripts/python test_chunk_prompts.py
```

Expected: the script crashes with `TypeError: PreSynthesisResult.__init__() got an unexpected keyword argument 'game_tags'` because `_make_presynthesis()` uses the new field names. This is correct if Chunk 1 has already been applied. If Chunk 1 has not been applied yet, apply it first before running these tests.

---

### Task 7: Update chunk JSON schema in `build_chunk_prompt()`

**Files:**
- Modify: `chunked_prompt.py`

This task updates the JSON schema definition and field rules inside `build_chunk_prompt()`.

- [ ] **Step 1: Replace `"tags"` with `"game_tags"` in the JSON schema block**

In `build_chunk_prompt()`, find the schema section and replace:

```python
# BEFORE
  "tags": [
    {{"name": "<tag_name>", "operation": "<add|remove|check>"}}
  ]
}}
```

```python
# AFTER
  "game_tags": [
    {{"name": "<tag_name>", "operation": "<add|remove|check>"}}
  ],
  "external_deps": [
    {{"name": "<module or global name>", "usage": "<how it is used in this chunk>"}}
  ]
}}
```

- [ ] **Step 2: Replace `tags` field rule with `game_tags` + `external_deps` rules**

Find the `=== FIELD RULES ===` section in `build_chunk_prompt()`. Replace the tags rule:

```
# BEFORE
- tags: All `AddTag`, `RemoveTag`, `HasTag` calls. Use empty array [] if none.
```

```
# AFTER
- game_tags: All `AddTag`, `RemoveTag`, `HasTag` calls. Use empty array [] if none found.
- external_deps: All `require("module")` calls AND any reference to DST globals:
  `TheWorld`, `TheNet`, `ThePlayer`, `GLOBAL`, `AllPlayers`, `TheSim`, `TheInput`, `TheCamera`.
  For each, write a short description of how it is used in this chunk.
  Use empty array [] if none found.
```

- [ ] **Step 3: Update the `CRITICAL INSTRUCTIONS` reference to tags**

In `build_chunk_prompt()`, find:
```
- tags: All `AddTag`, `RemoveTag`, `HasTag` calls. Use empty array [] if none.
```
If this line appears in a second place (CRITICAL INSTRUCTIONS), update it to reference `game_tags` as well.

- [ ] **Step 4: Run chunk schema tests**

```bash
cd d:/code/mod-document && .venv/Scripts/python test_chunk_prompts.py 2>&1 | head -20
```

Expected: the chunk schema tests (`game_tags field`, `external_deps field`, `old tags removed`, `TheWorld`, `TheNet`, `require`) should now pass. Merge prompt tests will still fail.

---

### Task 8: Update `_FUNCTION_FORMAT_SPEC`

**Files:**
- Modify: `chunked_prompt.py`

- [ ] **Step 1: Add `External dependencies` bullet to `_FUNCTION_FORMAT_SPEC`**

Find the `=== DEPENDENCY SECTION FORMAT ===` block inside `_FUNCTION_FORMAT_SPEC` (lines 33-41):

```python
# BEFORE
=== DEPENDENCY SECTION FORMAT ===
Use EXACTLY these labels in ## Dependencies & tags:

**Components used:**
- `component_name` -- how it is used (methods called, properties accessed)

**Tags:**
- `tag_name` -- add / remove / check
```

```python
# AFTER
=== DEPENDENCY SECTION FORMAT ===
Use EXACTLY these labels in ## Dependencies & tags:

**External dependencies:**
- `name` -- usage description
(Omit this bullet entirely if external_deps JSON is empty)

**Components used:**
- `component_name` -- how it is used (methods called, properties accessed)

**Tags:**
- `tag_name` -- add / remove / check
```

- [ ] **Step 2: Verify format spec test passes**

```bash
cd d:/code/mod-document && .venv/Scripts/python test_chunk_prompts.py 2>&1 | grep "format spec"
```

Expected: all three `format spec:` tests show `[PASS]`.

---

### Task 9: Update `build_merge_prompt()`

**Files:**
- Modify: `chunked_prompt.py`

- [ ] **Step 1: Remove `tags_yaml` and add new JSON variables**

In `build_merge_prompt()`, find and replace:

```python
# BEFORE
    # Pre-filled YAML tags
    tags_yaml = ", ".join(presynthesis.tags)

    # Partial descriptions — numbered list
```

```python
# AFTER
    # Game tags and external deps for Dependencies section body
    game_tags_json    = json.dumps(presynthesis.game_tags, indent=2, ensure_ascii=False)
    external_deps_json = json.dumps(presynthesis.external_deps, indent=2, ensure_ascii=False)

    # Partial descriptions — numbered list
```

- [ ] **Step 2: Update YAML `tags:` line in the f-string template**

Find the line in the f-string:
```
tags: [{tags_yaml}]
```

Replace with:
```
tags: <WRITE: 2-5 lowercase tags categorizing this component for docs search. Choose domain terms (e.g. [actions, combat, player]). Do NOT list game entity tags. Maximum 5 entries.>
```

- [ ] **Step 3: Update `system_scope:` line in the f-string template**

Find:
```
system_scope: {presynthesis.system_scope}
```

Replace with:
```
system_scope: <REVIEW hint "{presynthesis.system_scope}" — set the most accurate value from the allowed list based on the Overview you are writing>
```

- [ ] **Step 4: Insert new JSON blocks after `deps_json` section**

Find this block in the f-string:
```
=== DEPENDENCIES (pre-extracted) ===
{deps_json}

=== PROPERTIES (pre-extracted) ===
```

Replace with:
```
=== DEPENDENCIES (pre-extracted) ===
{deps_json}

=== GAME TAGS (pre-extracted) ===
{game_tags_json}

=== EXTERNAL DEPENDENCIES (pre-extracted) ===
{external_deps_json}

=== PROPERTIES (pre-extracted) ===
```

- [ ] **Step 5: Remove locked-scope instruction, add free-write instruction**

Find and remove:
```
- The tags and system_scope in YAML are PRE-FILLED. Copy them exactly. Do NOT change them.
```

Add after the last bullet in CRITICAL INSTRUCTIONS (or replace the removed line):
```
- Write YAML tags freely (2-5 doc-category keywords from the Overview). Review the system_scope hint and set the most accurate value from the allowed list.
```

- [ ] **Step 6: Update task 7 in YOUR TASKS section**

Find the task 7 line:
```
7. Format `## Dependencies & tags` using EXACTLY the DEPENDENCY SECTION FORMAT defined in the FORMAT SPECIFICATION section below.
```

Replace with:
```
7. Format `## Dependencies & tags` using EXACTLY the DEPENDENCY SECTION FORMAT defined in the FORMAT SPECIFICATION section below, including External dependencies from EXTERNAL DEPENDENCIES JSON (omit External dependencies bullet if empty).
```

- [ ] **Step 7: Run all prompt tests**

```bash
cd d:/code/mod-document && .venv/Scripts/python test_chunk_prompts.py
```

Expected: all tests pass. `Results: N passed, 0 failed`.

If any test fails, re-read the corresponding section of `chunked_prompt.py` and fix the exact string that's wrong.

- [ ] **Step 8: Run the full test suite**

```bash
cd d:/code/mod-document && .venv/Scripts/python test_pre_synthesis.py && .venv/Scripts/python test_events_section.py && .venv/Scripts/python test_chunk_prompts.py
```

Expected: all three scripts exit with 0 failures. If any fail, fix before continuing.

- [ ] **Step 9: Commit**

```bash
cd d:/code/mod-document && git add chunked_prompt.py test_chunk_prompts.py && git commit -m "$(cat <<'EOF'
feat: update chunk schema and merge prompt for quality fixes

- Renames tags->game_tags, adds external_deps to chunk JSON schema
- Adds External dependencies to _FUNCTION_FORMAT_SPEC
- Merge LLM now writes YAML tags freely and reviews system_scope hint
- Injects game_tags_json and external_deps_json into merge prompt

Co-Authored-By: Claude Sonnet 4.6 <noreply@anthropic.com>
EOF
)"
```

---

## Acceptance Verification

After all tasks complete, run this final check:

- [ ] **All tests green**

```bash
cd d:/code/mod-document && .venv/Scripts/python test_pre_synthesis.py && .venv/Scripts/python test_events_section.py && .venv/Scripts/python test_chunk_prompts.py
```

Expected: 0 failures across all three test files.

- [ ] **Import sanity check**

```bash
cd d:/code/mod-document && .venv/Scripts/python -c "
from pre_synthesis import PreSynthesisResult, pre_synthesize, _empty_result
from chunked_olm import _ensure_events_section, generate_merged_doc
from chunked_prompt import build_chunk_prompt, build_merge_prompt, _FUNCTION_FORMAT_SPEC
r = _empty_result()
assert not hasattr(r, 'tags')
assert hasattr(r, 'game_tags')
assert hasattr(r, 'external_deps')
print('All imports and assertions OK')
"
```

Expected: `All imports and assertions OK`

- [ ] **Verify `chunked_olm.py` log line has no reference to `presynthesis.tags`**

```bash
cd d:/code/mod-document && grep -n "presynthesis\.tags" chunked_olm.py
```

Expected: no output (the line has been updated).

- [ ] **Verify `tags_yaml` variable removed from `chunked_prompt.py`**

```bash
cd d:/code/mod-document && grep -n "tags_yaml" chunked_prompt.py
```

Expected: no output (the variable has been removed and must not linger as a stale reference).
