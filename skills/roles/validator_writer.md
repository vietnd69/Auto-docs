---
name: validator_writer
description: Patch format rules, anchoring examples, and common repeated patterns for documentation fixes
inject_into: [writer_full]
---

# Validator Writer

## Input Contract

The writer receives a reviewer response. Before generating any patches:

1. **If `approved: true` AND `need_special_case: false`** → Output an empty patch list `[]`. Do NOT generate any patches.
2. **If `approved: true` AND `need_special_case: true`** → Output an empty patch list `[]`. Do NOT patch the disputed section — wait for jury resolution before any changes.
3. **If `approved: false`** → Generate patches for each entry in `findings` only. Do NOT patch sections not mentioned in findings.
4. **If `need_special_case: true` AND `approved: false`** → Generate patches for each entry in `findings` only. Do NOT patch sections not mentioned in findings.

## Patch Output Schema

Output a JSON array of patch objects. Each patch MUST have exactly these fields:
```json
[
  {
    "old_text": "exact substring to find in the document (unique match)",
    "new_text": "replacement text",
    "reason": "one sentence explaining what is being fixed"
  }
]
```
- `old_text`: must match EXACTLY ONE location in the document (see Patch old_text Rules below)
- `new_text`: the corrected replacement; must preserve all surrounding structure not being changed
- `reason`: cites the reviewer finding it addresses

## Patch Ordering Rule

Patches MUST be ordered top-to-bottom by their position in the document.
The first patch targets the earliest-appearing text; the last patch targets the latest.
This ensures sequential application does not corrupt earlier anchors.

- NEVER rename or reformat ### headings (lines starting with "### `")
- NEVER change "* **Description:**", "* **Parameters:**",
  "* **Returns:**", "* **Error states:**" bullet labels
- NEVER rename a standard field (Description, Parameters, Returns, Error states) to a
  non-standard name (e.g. Notes, Behavior). If reviewer asks you to rename Error states,
  incorporate the relevant content into Description instead — do not create a new field label
- NEVER delete the `* **Error states:**` bullet line entirely. If reviewer says to move
  content from Error states to Description, move the text AND keep the field as
  `* **Error states:** None`. Removing the line will be rejected by the patch guard.
- NEVER convert bullet lists to numbered lists or tables
- Do NOT add or remove ### function entries UNLESS reviewer feedback explicitly says
  a function is missing or should be removed
- When adding a missing function entry:
  - If there is a preceding ### block: use the last line of that block as old_text anchor, then append the new entry after it.
  - If the function should be the FIRST entry in the section (no preceding ### block): use the section heading line (e.g. `## Main functions`) as the old_text anchor and insert the new entry immediately after it.
- ONLY modify the TEXT CONTENT within the existing structure (unless adding/removing
  is explicitly required by reviewer feedback)

## Patch old_text Rules

old_text MUST match EXACTLY ONE location in the section.
Before writing any old_text, mentally count how many times it appears in the section.
If it appears 2 or more times, you MUST include additional context lines to make it unique.

RULE: Include the ### function heading (and enough lines below it) as prefix context
whenever the target line is repeated across functions.

## Common Patterns (Always Repeated — Must Be Anchored)

These strings appear in nearly every function that takes common arguments.
Using them alone as old_text will ALWAYS fail. You MUST anchor them:

  WRONG — will be skipped (appears 5–24 times):
    "old_text": "  - `inst` (entity) -- Entity instance"
    "old_text": "  - `inst` -- entity instance"
    "old_text": "  - `self` -- component instance"
    "old_text": "  - `x` (number) -- X coordinate"
    "old_text": "  - `y` (number) -- Y coordinate"
    "old_text": "  - `z` (number) -- Z coordinate"
    "old_text": "  - `pt` -- Target position"
    "old_text": "  - `ent` -- entity instance"
    "old_text": "  - `prefab` (string) -- Prefab name string"
    "old_text": "* **Parameters:** `inst` (Entity) -- Entity instance"
    "old_text": "* **Returns:** boolean"
    "old_text": "* **Returns:** nil"
    "old_text": "* **Returns:** number"
    "old_text": "* **Returns:** string"
    "old_text": "* **Returns:** string (sound path)"
    "old_text": "* **Error states:** None."
    "old_text": "* **Error states:** None"

  RIGHT — anchored to a specific function (unique):
    "old_text": "### `SomeFunction`\n* **Parameters:**\n  - `inst` (entity) -- Entity instance"

  RIGHT — Error states anchored via the preceding Returns line (always adjacent):
    "old_text": "* **Returns:** nil\n* **Error states:** None"  ← if unique in document
    OR include more context if Returns line is also repeated:
    "old_text": "### `SomeFunction`\n* **Description:** ...\n* **Parameters:** ...\n* **Returns:** nil\n* **Error states:** None"

## CRITICAL: old_text Must Be Contiguous

old_text is a SUBSTRING match — it must appear verbatim as consecutive characters in the document.
You CANNOT skip lines. Every line between your start and end lines MUST be included.

WRONG — heading + Error states with lines skipped in between:
  "old_text": "### `onenter (spawn)`\n* **Error states:** None"

This FAILS because the document has Description, Parameters, Returns BETWEEN the heading and
Error states. The heading is NOT immediately followed by Error states.

RIGHT — use the line that immediately precedes Error states as the anchor:
  "old_text": "* **Returns:** nil\n* **Error states:** None"

OR include the full block if Returns line is repeated:
  "old_text": "### `onenter (spawn)`\n* **Description:** ...\n* **Parameters:** ...\n* **Returns:** nil\n* **Error states:** None"

## Anchoring Example

You want to fix the `inst` parameter description in function `GetNearestPlayer`.
The section has 10 functions, all with `  - `inst` (entity) -- Entity instance`.

WRONG patch (skipped — 10 matches):
  {
    "old_text": "  - `inst` (entity) -- Entity instance",
    "new_text": "  - `inst` (entity) -- The entity querying for nearby players",
    "reason": "Clarify inst description for GetNearestPlayer"
  }

RIGHT patch (unique — anchored to the function heading):
  {
    "old_text": "### `GetNearestPlayer`\n* **Parameters:**\n  - `inst` (entity) -- Entity instance",
    "new_text": "### `GetNearestPlayer`\n* **Parameters:**\n  - `inst` (entity) -- The entity querying for nearby players",
    "reason": "Clarify inst description for GetNearestPlayer"
  }

## Handling Duplicate Function Entries

When the reviewer reports a **duplicate function entry** (same `### ` heading appearing twice in the document):

**RULE: DELETE the wrong duplicate — NEVER rename it.**

Renaming the wrong duplicate to match the correct one creates TWO entries with identical signatures. This makes both entries permanently AMBIGUOUS — future patches can never uniquely target either. The validator loop cannot recover from this state.

**Step-by-step:**
1. Identify which entry has the WRONG signature by comparing to the Lua source
2. Delete the WRONG entry using `new_text: ""` with `"allow_drops": true`
3. Do NOT modify the CORRECT entry

**Correct pattern — delete the wrong duplicate:**
```json
{
  "old_text": "### `DoEatSound(inst, isheavy)`\n* **Description:** Plays sound effects for eating actions.\n* **Parameters:**\n  - `inst` -- Entity instance owning the stategraph\n  - `isheavy` -- Boolean indicating if heavy lifting is active\n* **Returns:** nil\n* **Error states:** None",
  "new_text": "",
  "reason": "Remove duplicate DoEatSound with wrong signature — source defines overrideexisting, not isheavy",
  "allow_drops": true
}
```

**Wrong pattern — renames the wrong duplicate (DO NOT DO THIS):**
```json
{
  "old_text": "### `DoEatSound(inst, isheavy)`",
  "new_text": "### `DoEatSound(inst, overrideexisting)`",
  "reason": "Fix parameter name"
}
```
This makes both entries identical → both become AMBIGUOUS → loop cannot fix them → document stuck forever.

**Identifying which is correct:** Compare the parameter names against the Lua source provided in context. The entry whose `params` matches the source function definition is the correct one. Delete the other.

**old_text must span the full function block:** To delete a function entry, `old_text` must be the entire `### ` block (heading + all bullet fields). Use `allow_drops: true`. Anchor the old_text with the function heading and include at least 3 lines of content to ensure uniqueness.

## Additional Rules

- old_text in each patch must be a MINIMAL substring sufficient for UNIQUENESS —
  include enough lines to make it unique, but not the entire function block
- Never use a bare type-only pattern like `* **Returns:** \`boolean\`` or `* **Returns:** \`nil\``
  as old_text when multiple functions share that exact Returns line