# Design: Chunked Validator — Format Protection & Section Sub-chunking

**Date:** 2026-03-23
**Status:** Approved
**Branch:** feat/monorepo-restructure

---

## Problem Statement

Two independent bugs in `run_chunked_content_loop` (large-file content validation):

### Bug 1 — Format destruction loop

The reviewer/writer prompts contain **no format constraints**. The reviewer flags content
issues; the writer patches them but silently breaks structural format (e.g. rewrites
`### \`FuncName\`` heading style, changes `* **Parameters:**` bullets to numbered lists,
wraps entire function blocks as `old_text`). The next reviewer finds the new format
violations; the writer patches again, introducing more drift. The loop never converges —
sections accumulate issues across iterations rather than reducing them.

Observed: `## Dependencies & tags` ran 9 iterations, each applying patches, but was never
approved. The writer eventually gave up with no patches.

### Bug 2 — Token imbalance causing timeouts

`split_md_sections` splits only on `##` boundaries. `## Main functions` with 109 functions
becomes a single 16K-token section. The reviewer prompt for that section is 16,142 tokens,
causing timeouts. Meanwhile `## Overview` has a 286-token reviewer prompt — extreme
imbalance.

Observed: `[TIMEOUT] Account 6 timeout sau 200s` on the second iteration of
`## Main functions`.

---

## Approach: Prompt injection + generic section sub-chunking

**Approach A** was selected over:
- **B** (regex format guard): deterministic but brittle if format conventions evolve
- **C** (two-phase format→content validation): clean separation but doubles LLM calls

---

## Architecture

Three files change; no new pipeline stages, no extra LLM calls for format checking:

```
validator/src/validator/content/
├── sections.py   ← Add: split_section_blocks(), sub_chunk_section(),
│                         extract_fn_headings(), restore_lost_blocks()
├── prompts.py    ← Edit: inject FORMAT CONTRACT into both section prompts
└── chunked.py    ← Edit: 2-path dispatch (large vs small) in section loop
```

New constants in `llm/src/llm/settings.py` (loaded from `config.toml`):

```toml
SECTION_TOKEN_THRESHOLD = 4000   # triggers sub-chunking for any ## section
BATCH_TOKEN_LIMIT = 3000         # max tokens per fn-block batch (section text only)
```

---

## Section 1: Format Protection (fixes Bug 1)

### Reviewer prompt — add FORMAT CONTRACT block

Injected into `build_section_reviewer_prompt` before the response format instructions:

```
## FORMAT CONTRACT
Each function entry MUST follow this exact structure:
### `FunctionName(params)`
* **Description:** one-line summary
* **Parameters:**
  - `name` (type) -- description
* **Returns:** description
* **Error states:** description  ← only if applicable

CHECK BOTH:
1. Content accuracy (params match Lua source, descriptions correct)
2. Format compliance (structure matches FORMAT CONTRACT above)

Flag format violations as issues just like content errors.
```

### Writer prompt — add FORMAT RULES block

Injected into `build_section_writer_prompt` before the response format instructions:

```
## FORMAT RULES — NEVER VIOLATE
- NEVER rename or reformat ### headings (lines starting with "### `")
- NEVER change "* **Description:**", "* **Parameters:**",
  `* **Returns:**`, `* **Error states:**` bullet labels
- NEVER convert bullet lists to numbered lists or tables
- NEVER add or remove ### function entries
- ONLY modify the TEXT CONTENT within the existing structure
- old_text in each patch must be a MINIMAL substring (a single line or short phrase) —
  never use an entire function block as old_text
```

The last rule ("minimal old_text") prevents the root failure mode: writer using a full
function block as `old_text`, causing the replacement to subtly reformat the entire entry.

Note: both prompts already have "Do NOT modify YAML frontmatter". The `##`-level section
heading is excluded from `batch_text` via the preamble split (see Section 2), so no
additional protection for `##` headings is needed in the FORMAT RULES.

---

## Section 2: Section Sub-chunking (fixes Bug 2)

### Trigger

Any `##` section where `count_tokens(section.text) > SECTION_TOKEN_THRESHOLD` (4000)
**AND** the section contains at least one line-anchored `### ` sub-heading.

The `has_subheadings` guard uses `re.search(r'(?m)^### ', section.text)` (anchored to
line start) to match exactly what `split_section_blocks` will split on. A plain `"### " in
section.text` would give a false positive if `### ` appears inside a Lua code fence, which
would cause `fn_blocks` to come out empty and silently destroy the section on reassembly.

- Sections above threshold **without** line-start `### ` → small-section path (log warning,
  accept large prompt; no fix possible in this design — known limitation).
- Sections below threshold → small-section path regardless of `### ` presence.

This trigger applies to **any section name** — not hardcoded to `## Main functions`.

### `split_section_blocks(section_text)` — new function in `sections.py`

Splits a section into `(preamble, fn_blocks)`:

- **preamble**: the `##` heading line plus all content up to (not including) the first
  `### ` line. Always non-empty (contains at least the `##` heading).
- **fn_blocks**: `list[str]`, each element starts with a `### ` line and extends to
  (not including) the next `### ` line. Split using `re.split(r'(?m)^(?=### )', text)`.

Round-trip invariant: `preamble + "".join(fn_blocks) == section_text`.

### Batch grouping — `sub_chunk_section(fn_blocks, limit)` in `sections.py`

```python
def sub_chunk_section(fn_blocks: list[str], limit: int) -> list[list[str]]:
    """Group fn_blocks into batches where each batch's token count <= limit."""
    batches, current, current_tokens = [], [], 0
    for block in fn_blocks:
        block_tokens = count_tokens(block)
        if current and current_tokens + block_tokens > limit:
            batches.append(current)
            current, current_tokens = [block], block_tokens
        else:
            current.append(block)
            current_tokens += block_tokens
    if current:
        batches.append(current)
    return batches
```

With `BATCH_TOKEN_LIMIT = 3000` and `LUA_CONTEXT_TOKENS = 8000` cap, the total reviewer
prompt per batch is approximately `3000 + lua_context_tokens`. The lua_context for 20–25
functions from a complex Lua file may approach the 8K cap, giving a worst-case prompt of
~11K tokens per batch — well below the timeout threshold observed at 16K+. The 5–7K
estimate in success criteria is approximate; actual size depends on function complexity.

### Patched-batch writeback

After the review/patch loop runs on a batch, the patched `batch_text` is re-split on
`### ` boundaries to recover updated individual blocks:

```python
updated_blocks = re.split(r'(?m)^(?=### )', patched_batch_text)
updated_blocks = [b for b in updated_blocks if b]  # drop empty strings
```

These updated blocks replace the original blocks in the master `fn_blocks` list using
tracked start/end indices:

```python
# before the batch loop, track cumulative index into fn_blocks
offset = 0
for batch in batches:
    batch_size = len(batch)
    batch_text = "".join(batch)
    # ... review/patch loop produces patched_batch_text ...
    updated = [b for b in re.split(r'(?m)^(?=### )', patched_batch_text) if b]
    fn_blocks[offset : offset + batch_size] = updated
    offset += len(updated)
```

### Reassembly

After all batches are processed:

```python
section.text = preamble + "".join(fn_blocks)
```

File write timing: the file is written **once after the entire section completes** (not
after each batch). If a crash occurs mid-section, the file on disk reflects the state
before that section's validation began (earlier sections' patches are already persisted).
This matches acceptable recovery behaviour — restarting validation replays the section
from its pre-validation state. No checkpoint within a section is added by this design.

---

## Section 3: Completeness Pre-check

Applies only to sections that take the large-section path (sub-chunked).

### Purpose

Each batch reviewer sees only its ~20–25 function entries and cannot detect if the writer
in another batch deleted a `### FuncName(params)` entry. The snapshot+restore mechanism
ensures no entries are silently lost across the full batch loop.

### `extract_fn_headings(fn_blocks)` — new function in `sections.py`

```python
def extract_fn_headings(fn_blocks: list[str]) -> set[str]:
    """Return the set of first-line headings (e.g. '### `Foo(x)`') from fn_blocks."""
    return {block.split("\n", 1)[0].strip() for block in fn_blocks if block.strip()}
```

The snapshot uses the **full first line** of each block (e.g. `### \`GetLuckFactor(inst)\``)
as the key — including parameters. This avoids ambiguity between overloaded names and
matches how the writer would reference a heading in `old_text`.

### `restore_lost_blocks(fn_blocks, snapshot, backup_fn_blocks)` — new in `sections.py`

```python
def restore_lost_blocks(
    fn_blocks: list[str],
    snapshot: set[str],
    backup_fn_blocks: list[str],
) -> int:
    """Reinsert fn_blocks whose heading was in snapshot but is now missing.
    Restores at the original position from backup_fn_blocks, preserving order.
    Returns number of blocks restored."""
    current = extract_fn_headings(fn_blocks)
    lost_headings = snapshot - current
    if not lost_headings:
        return 0

    # Build current heading → position map
    current_headings_list = [b.split("\n", 1)[0].strip() for b in fn_blocks]

    # Walk backup in original order; reinsert each lost block at its original index
    restored = 0
    for orig_idx, block in enumerate(backup_fn_blocks):
        heading = block.split("\n", 1)[0].strip()
        if heading not in lost_headings:
            continue
        # Find insertion point: position of the first backup heading after orig_idx
        # that still exists in fn_blocks, or append at end if none found
        insert_pos = len(fn_blocks)
        for later_idx in range(orig_idx + 1, len(backup_fn_blocks)):
            later_heading = backup_fn_blocks[later_idx].split("\n", 1)[0].strip()
            if later_heading in current_headings_list:
                insert_pos = current_headings_list.index(later_heading)
                break
        fn_blocks.insert(insert_pos, block)
        current_headings_list.insert(insert_pos, heading)  # keep map in sync
        restored += 1
    return restored
```

Matching is exact (full heading string). If the writer reformatted a heading (e.g. removed
backticks), it will appear as "lost" and the original is restored — which is the correct
behaviour given the FORMAT RULES prohibition on heading changes.

Order is preserved: each restored block is inserted at the position immediately before
the first subsequent backup entry that still exists in `fn_blocks`, or appended at the
end if no such anchor exists.

### Batch-level writer gave up → batch failed, loop continues

When the writer returns no patches for a batch (same as current section-level behaviour),
the batch is marked as failed and `all_failed_issues` is extended with the last review's
issues. The loop **continues to the next batch** — it does not abort the entire section.
This means a section with one stuck batch can still have other batches approved, giving
the best possible partial result.

---

## Updated Flow in `run_chunked_content_loop`

```python
for idx, section in enumerate(sections, 1):
    tokens = count_tokens(section.text)
    has_subheadings = bool(re.search(r'(?m)^### ', section.text))

    if tokens > SECTION_TOKEN_THRESHOLD and has_subheadings:
        # ── Large section path ──────────────────────────────────────────
        preamble, fn_blocks = split_section_blocks(section.text)
        snapshot = extract_fn_headings(fn_blocks)
        backup = list(fn_blocks)   # shallow copy; block strings are immutable
        batches = sub_chunk_section(fn_blocks, BATCH_TOKEN_LIMIT)

        offset = 0
        for batch_idx, batch in enumerate(batches, 1):
            if config.stop_check():
                return ContentLoopResult(
                    approved=False, iterations=total_iterations,
                    final_issues=["Interrupted by user"],
                )

            batch_size = len(batch)
            batch_text = "".join(batch)
            lua_ctx = extract_lua_context(lua_source, extract_function_names(batch_text))

            print(f"  [content/chunked] Section {idx} batch {batch_idx}/{len(batches)} "
                  f"— {batch_size} fn(s), {count_tokens(batch_text):,} tokens")

            # Standard review/patch loop — mirrors small-section path including for/else
            batch_approved = False
            batch_last_review: ReviewResult | None = None

            for i in range(config.max_iterations):
                if config.stop_check():
                    return ContentLoopResult(
                        approved=False, iterations=total_iterations,
                        final_issues=["Interrupted by user"],
                    )
                total_iterations += 1
                batch_last_review = review_section(batch_text, lua_ctx,
                                                   config.reviewer_model)
                if batch_last_review.approved:
                    batch_approved = True
                    break
                patches = write_section_patches(batch_text, lua_ctx, batch_last_review,
                                                config.writer_model)
                if not patches:
                    break   # writer gave up — batch stays failed, continue to next batch
                batch_text, _ = apply_patches(batch_text, patches)
            else:
                # max_iterations exhausted — run one final review on post-patch text
                total_iterations += 1
                batch_last_review = review_section(batch_text, lua_ctx,
                                                   config.reviewer_model)
                batch_approved = batch_last_review.approved

            if not batch_approved and batch_last_review is not None:
                all_failed_issues.extend(batch_last_review.issues)

            # Write patched blocks back into fn_blocks via tracked offset
            updated = [b for b in re.split(r'(?m)^(?=### )', batch_text) if b]
            if len(updated) != batch_size:
                # Writer violated FORMAT RULES and added/removed ### entries.
                # Log a warning; restore_lost_blocks below will recover deletions.
                # Spurious additions are left in place (harmless extra entries).
                print(f"  [content/chunked] WARNING: batch {batch_idx} block count "
                      f"changed {batch_size} → {len(updated)}")
            fn_blocks[offset : offset + batch_size] = updated
            offset += len(updated)   # advance by actual updated count, not batch_size

        # Restore any function entries lost during patching
        restored = restore_lost_blocks(fn_blocks, snapshot, backup)
        if restored:
            print(f"  [content/chunked] Restored {restored} lost fn entries")

        # Reassemble section.text once, after completeness restore
        section.text = preamble + "".join(fn_blocks)
        Path(md_filepath).write_text(join_md_sections(frontmatter, sections),
                                     encoding="utf-8")

    else:
        # ── Small section path — existing logic, unchanged ───────────────
        if tokens > SECTION_TOKEN_THRESHOLD:
            print(f"  [content/chunked] WARNING: section {idx!r} is {tokens:,} tokens "
                  "but has no ### sub-headings — cannot sub-chunk, proceeding as-is")
        # ... existing review/patch loop (unchanged from current chunked.py) ...
```

---

## What Does NOT Change

- `split_md_sections` / `join_md_sections` — unchanged, still splits on `##`
- `DocSection` dataclass — unchanged
- `review_section` / `write_section_patches` call signatures — unchanged
- `run_content_loop` (standard non-chunked path) — unchanged
- `ContentLoopConfig` / `ContentLoopResult` contracts — unchanged
- All format/autofix checks — unchanged

---

## Files to Create / Modify

| File | Change |
|------|--------|
| `validator/src/validator/content/sections.py` | Add `split_section_blocks()`, `sub_chunk_section()`, `extract_fn_headings()`, `restore_lost_blocks()` |
| `validator/src/validator/content/prompts.py` | Add FORMAT CONTRACT to `build_section_reviewer_prompt`; add FORMAT RULES to `build_section_writer_prompt` |
| `validator/src/validator/content/chunked.py` | Replace section loop body with 2-path dispatch; add `import re` |
| `llm/src/llm/settings.py` + `config.toml` | Add `SECTION_TOKEN_THRESHOLD = 4000`, `BATCH_TOKEN_LIMIT = 3000` |

---

## Known Limitations

- Sections above `SECTION_TOKEN_THRESHOLD` without `### ` sub-headings (e.g. a very large
  `## Overview`) cannot be sub-chunked. They receive a warning log and proceed as a single
  large unit. This is acceptable because such sections are rare in practice.
- The lua_context token budget (`LUA_CONTEXT_TOKENS = 8000`) is shared between all
  functions in a batch. For batches where many functions have complex bodies, context may
  be truncated — the same behaviour as the current full-section path, now across fewer
  functions.

---

## Success Criteria

1. `## Dependencies & tags` (28 fns, ~1.3K tokens) → below threshold, uses small-section
   path with new format-aware prompts → converges in ≤ 3 iterations without format drift
2. `## Main functions` (109 fns, 16K tokens) → sub-chunked into ~5 batches → no timeout,
   reviewer prompts well below the 16K level that caused timeout
3. After full validation run on `componentutil.lua`, the generated doc structure matches
   the few_shot format convention (`### ` headings, bullet structure intact)
4. No `### FuncName` entries present before validation are missing after validation
