# Fix Reviewer-Writer Oscillation in Chunked Validation

**Date:** 2026-03-28
**Status:** Approved
**Scope:** `validator/src/validator/content/` — chunked review-fix loop

---

## Problem

The chunked content validation loop oscillates instead of converging. Root causes identified from `run_2026-03-28_05-00-04.log` analyzing `componentutil.lua` (1907 lines, 112 functions):

### Root Cause 1: Reviewer mixes content and format concerns

The reviewer prompt combines content accuracy checks (hallucination, wrong params) with format compliance checks (bullet style, heading notation, field structure). When the writer fixes a content issue, the fix often introduces a new format surface that the reviewer catches next iteration. This creates an unbounded cycle:

- Iter 1: "add Internal notation" → writer adds `{Internal}`
- Iter 2: "`{Internal}` format wrong, use Description field" → writer moves it
- Iter 3: new format nits from the moved text → ...

**Evidence:** Section 6 batch 2 (oscillation at iter 2), batch 4 (oscillation at iter 3), batch 5 (oscillation at iter 3).

### Root Cause 2: Writer fails to complete removals

Reviewer flags hallucinated functions (e.g., `CLOSEINSPECTORUTIL.IsValidTarget`, `CLOSEINSPECTORUTIL.IsValidPos`, `CLOSEINSPECTORUTIL.CanCloseInspect`) but they persist across iterations because:
- Writer generates a patch but `old_text` doesn't match (count=0 → skipped)
- Writer omits the deletion patch entirely
- No fallback mechanism forces the removal

**Evidence:** Batch 2 iter 1 and iter 2 both flag the same 3 `CLOSEINSPECTORUTIL.*` functions.

### Root Cause 3: Heading loss during patching

Writer patches sometimes merge or delete `### ` function blocks. Current `restore_lost_blocks()` runs **after all batches complete** (line 482), but by then subsequent iterations have already reviewed the damaged text.

**Evidence:** Section 6 batch 4: "WARNING: block count changed 25 → 21" — 4 function entries lost mid-loop.

---

## Solution: Two-Part Fix (A + C)

### Part A: Content-Only Reviewer

Strip format rules from the reviewer prompt. Format compliance is already handled by the separate `validator/src/validator/format/` pipeline (autofix.py, checks.py, mdx.py) that runs after content validation.

#### Reviewer keeps (content + structural guards):
- Hallucinated functions (documented but not in Lua source)
- Missing functions (in Lua source but not documented)
- Wrong parameters (name, type, default value mismatch)
- Wrong return values
- Wrong descriptions (misrepresent actual behavior)
- Structural guard: "Do NOT rename or remove ### headings in your review suggestions unless the function is hallucinated"

#### Reviewer drops:
- FORMAT CONTRACT block (heading structure, bullet labels)
- Single-param inline vs multi-param sub-bullet rules
- `_FN_FORMAT` skill injection (function format reference)
- Any mention of "format compliance" in review checklist
- Notation style preferences (`{Internal}` placement, etc.)

#### `_QUALITY_RULES` format leakage

`skills/quality_rules.md` contains both content and format directives. Format directives that would leak into the "content-only" reviewer:
- OUTPUT FORMAT (lines 9-12): Markdown structure
- YAML FRONTMATTER (lines 14-19): Field rules
- HEADING RULES (lines 33-35): Sentence case, heading levels
- PROPERTIES TABLE (lines 56-59): Column structure

**Fix:** Do NOT split the quality_rules file. Instead, add an explicit override instruction in the reviewer system prompt that takes precedence: "From the quality rules below, apply ONLY the content accuracy rules (CONTENT RULES, COMPLETENESS, FILE TYPE CLASSIFICATION, CONSTRUCTOR RULE). IGNORE format rules (OUTPUT FORMAT, YAML FRONTMATTER, HEADING RULES, PROPERTIES TABLE column structure, MDX COMPATIBILITY)."

#### File changes:

**`skills/validator_reviewer.md`:**
- Remove `=== FORMAT CONTRACT ===` section (lines 11-24)
- Remove "CHECK BOTH: content + format" → replace with "CHECK: content accuracy only"
- Remove "Flag format violations as issues" directive
- Add: "Do NOT flag formatting, bullet style, or structural notation — only flag content errors (wrong/missing/hallucinated information)."
- Keep all `=== SECTION ... ===` blocks but strip format-specific rules within them

**`validator/src/validator/content/prompts.py` → `build_section_reviewer_prompt()`:**
- Remove `fn_format_block` injection (lines 163-165: `_FN_FORMAT` reference when `is_main_fns`)
- Keep `batch_scope_note` (still needed to prevent false "missing section" flags)
- Keep `_QUALITY_RULES` injection but add override instruction before it: "From the quality rules below, apply ONLY content accuracy rules. IGNORE format/structural rules."
- Add to system prompt: "You are reviewing CONTENT ACCURACY ONLY. Do not flag formatting, bullet style, or structural notation issues."

### Part C: Writer Verification + Diff Guard

Three guards added to `chunked.py`, all running after `apply_patches()` within each iteration.

**Applies to BOTH code paths:** The large-section sub-chunked batch loop (lines 355-479) AND the small-section loop (lines 528-606) must both receive Guards 1-3. The iteration body is structurally identical in both paths.

#### New functions in `sections.py`

**`extract_fn_headings_from_text(text: str) -> set[str]`** (NEW):
```python
def extract_fn_headings_from_text(text: str) -> set[str]:
    """Extract normalized function names from ### headings in raw text.

    Parses headings like: ### `CLOSEINSPECTORUTIL.IsValidTarget(inst)`
    Returns: {"CLOSEINSPECTORUTIL.IsValidTarget", "FuncName", ...}
    Strips backticks, parameters, and trailing whitespace.
    """
    headings = re.findall(r'^### `?([^`(\n]+)', text, re.MULTILINE)
    return {h.strip() for h in headings}
```

Unlike existing `extract_fn_headings(fn_blocks: list[str])` which takes pre-split blocks, this operates on raw text (needed because `batch_text` is a string, not a block list).

**`delete_fn_block(text: str, fn_name: str) -> str`** (NEW):
```python
def delete_fn_block(text: str, fn_name: str) -> str:
    """Delete the ### function block for fn_name from text.

    Block boundary: from the `### ` heading line containing fn_name
    to the next `### ` heading (exclusive) or end-of-string.

    Name matching: fn_name is matched against the heading text with
    optional backticks, dots, and parameters stripped. For example,
    fn_name="CLOSEINSPECTORUTIL.IsValidTarget" matches heading
    `### \`CLOSEINSPECTORUTIL.IsValidTarget(inst)\``.

    Trailing blank lines after deletion are collapsed to one newline.
    Returns text unchanged if fn_name not found in any heading.
    """
```

#### Guard 1: Immediate Heading Integrity

Move heading check from end-of-batch (line 482) to **per-iteration**, right after `apply_patches()`:

```python
# After apply_patches() in the iteration loop:
before_headings = extract_fn_headings_from_text(batch_text_before_patches)
after_headings = extract_fn_headings_from_text(batch_text)
lost = before_headings - after_headings

# Only restore headings that were NOT flagged for removal by reviewer
removal_targets = _extract_removal_targets(review.issues)
accidental_loss = lost - removal_targets

if accidental_loss:
    batch_text = restore_lost_blocks_immediate(batch_text, accidental_loss, backup_blocks)
    print(f"  [content/chunked] Restored {len(accidental_loss)} accidentally lost headings")
```

**Execution order:** Guard 1 runs BEFORE Guard 2. Guard 1 restores headings NOT in `removal_targets`. Guard 2 then deletes headings IN `removal_targets`. These sets are disjoint by construction — Guard 1 explicitly excludes `removal_targets`. If `_extract_removal_targets()` has a false negative (fails to parse a reviewer-flagged name), that heading will be restored by Guard 1 and persist — a safe failure mode (content preserved, reviewer can flag again next iteration).

Keep the existing end-of-batch `restore_lost_blocks()` as a final safety net.

#### Guard 2: Hallucination Delete Enforcement

When reviewer flags functions as hallucinated/non-existent but they survive `apply_patches()`:

```python
def _enforce_removals(batch_text: str, issues: list[str]) -> str:
    """Auto-remove function blocks that reviewer flagged as hallucinated
    but writer failed to delete."""
    targets = _extract_removal_targets(issues)
    if not targets:
        return batch_text

    current_headings = extract_fn_headings_from_text(batch_text)
    for fn_name in targets:
        if fn_name in current_headings:
            batch_text = delete_fn_block(batch_text, fn_name)
            print(f"  [content/chunked] Auto-removed hallucinated: {fn_name}")
    return batch_text
```

**`_extract_removal_targets(issues: list[str]) -> set[str]`** — safe extraction strategy:

The function parses reviewer issues in TWO steps to minimize false positives:

1. **Filter issues:** Only issues matching removal-intent phrases are considered:
   - "does not exist in the Lua source"
   - "hallucinated"
   - "not present in the provided Lua"
   - "should be removed"
   - "not found in"
   - "fabricated"
   - "doesn't appear in source"
   - "not defined in the Lua"

2. **Extract names:** From matching issues, extract function names using backtick-quoted patterns first (most precise), then CamelCase as fallback:
   ```python
   # Primary: backtick-quoted names (e.g., "`CLOSEINSPECTORUTIL.IsValidTarget`")
   backtick_names = re.findall(r'`([A-Z][\w.]+?)(?:\([^)]*\))?`', issue_text)

   # Fallback: dot-qualified CamelCase (e.g., "CLOSEINSPECTORUTIL.IsValidTarget")
   dotted_names = re.findall(r'\b([A-Z][\w]*(?:\.[A-Z][\w]*)+)\b', issue_text)

   # Last resort: CamelCase (only if no backtick/dotted names found)
   if not backtick_names and not dotted_names:
       camel_names = _CAMEL_RE.findall(issue_text)
   ```

3. **Cross-reference:** Only return names that actually exist as headings in `batch_text`. This prevents false positives from type names, class names, or other CamelCase words in the issue text.

```python
def _extract_removal_targets(issues: list[str], batch_text: str = "") -> set[str]:
    """Parse reviewer issues for hallucination flags, return function names to remove.

    If batch_text is provided, cross-references against actual headings to prevent
    false positives from CamelCase type/class names."""
```

#### Guard 3: Patch Scope Validation

Pre-filter patches before applying. **Only applies the field check to `## Main functions` sections** (other sections like `## Dependencies & tags` use different field structures like `**External dependencies:**`, `**Components used:**`, `**Tags:**`).

```python
def _validate_patch_scope(patches: list[Patch], section_heading: str = "") -> list[Patch]:
    """Filter out patches that would violate structural constraints."""
    is_main_fns = section_heading == "## Main functions"
    valid = []
    for patch in patches:
        # Reject patches that delete ### headings (unless reason says remove/hallucinate)
        if re.search(r'^### ', patch.old_text, re.MULTILINE) and \
           not re.search(r'^### ', patch.new_text, re.MULTILINE):
            is_removal = any(kw in patch.reason.lower()
                           for kw in ("remove", "hallucin", "not exist", "delete"))
            if not is_removal:
                print(f"  [content/chunked] Patch rejected: would delete heading without removal reason")
                continue

        # Reject patches that introduce non-standard fields (Main functions only)
        if is_main_fns:
            new_fields = re.findall(r'^\* \*\*(\w[\w ]*?):\*\*', patch.new_text, re.MULTILINE)
            allowed = {"Description", "Parameters", "Returns", "Error states"}
            invalid_fields = [f for f in new_fields if f not in allowed]
            if invalid_fields:
                print(f"  [content/chunked] Patch rejected: introduces non-standard field(s): {invalid_fields}")
                continue

        valid.append(patch)
    return valid
```

#### New flow per batch iteration:

```
for i in range(max_iterations):
    # 1. Content-only review (no format)
    review = review_section(batch_text, lua_ctx, ...)
    if review.approved: break

    # 2. Oscillation check (unchanged)
    if oscillation_detected: break

    # 3. Writer generates patches
    patches = write_section_patches(batch_text, review, ...)
    if not patches: break

    # 4. NEW — Pre-filter patches (Guard 3)
    patches = _validate_patch_scope(patches, section.heading)
    if not patches: break

    # 5. Apply patches
    batch_text_before = batch_text
    batch_text, failed, ambiguous = apply_patches(batch_text, patches)

    # 6. NEW — Heading integrity per-iteration (Guard 1)
    #    Runs FIRST: restores accidental losses (excludes removal targets)
    removal_targets = _extract_removal_targets(review.issues, batch_text_before)
    before_headings = extract_fn_headings_from_text(batch_text_before)
    after_headings = extract_fn_headings_from_text(batch_text)
    accidental_loss = (before_headings - after_headings) - removal_targets
    if accidental_loss:
        batch_text = restore_lost_blocks_immediate(batch_text, accidental_loss, backup)

    # 7. NEW — Hallucination enforcement (Guard 2)
    #    Runs SECOND: deletes confirmed hallucinations that survived patching
    batch_text = _enforce_removals(batch_text, review.issues)

    # 8. Consecutive fail check (unchanged)
```

**Both code paths** (large-section batch loop at line 383 and small-section loop at line 528) receive identical guard logic. Extract a helper `_apply_guarded_patches(batch_text, patches, review, section_heading, backup)` to avoid duplication.

---

## File Change Summary

| File | Change |
|------|--------|
| `skills/validator_reviewer.md` | Remove FORMAT CONTRACT, format checking directives. Keep content checklist + structural guard note. |
| `validator/src/validator/content/prompts.py` | `build_section_reviewer_prompt()`: remove `fn_format_block`, add "content accuracy only" directive, add quality_rules override instruction. |
| `validator/src/validator/content/chunked.py` | Add `_validate_patch_scope()`, `_enforce_removals()`, `_extract_removal_targets()`, `_apply_guarded_patches()`. Move heading restore into per-iteration. Apply guards to BOTH large-section and small-section code paths. |
| `validator/src/validator/content/sections.py` | Add `extract_fn_headings_from_text(text)` and `delete_fn_block(text, fn_name)` utilities. |

## Files NOT Changed

| File | Reason |
|------|--------|
| `skills/validator_writer.md` | Structural rules already correct — keep as-is. |
| `skills/quality_rules.md` | Not split. Override instruction in prompt suppresses format rules contextually. |
| `llm/src/llm/settings.py` | No new config needed. |
| `validator/src/validator/pipeline.py` | Flow trigger unchanged. |
| `validator/src/validator/format/*` | Format pipeline runs separately, untouched. |
| `validator/src/validator/content/writer.py` | Patch apply logic unchanged. |
| `validator/src/validator/content/reviewer.py` | Parse logic unchanged. |

## Expected Impact

Using the log's batch examples as reference:

| Batch | Before (current) | After (expected) |
|-------|-------------------|------------------|
| Section 6 batch 2 | 2 iter → oscillation (CLOSEINSPECTORUTIL persists) | 1-2 iter → approved (no format surface, Guard 2 removes hallucinations) |
| Section 6 batch 4 | 3 iter → oscillation + 4 blocks lost | 1-2 iter → approved (no format cascade, Guard 1 prevents block loss) |
| Section 6 batch 5 | 3 iter → oscillation | 1-2 iter → approved (no format nits) |

Total API calls for Section 6: ~24 calls → estimated ~14 calls (42% reduction).
