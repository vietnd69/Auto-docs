---
name: validator_writer
description: Patch format rules, anchoring examples, and common repeated patterns for documentation fixes
inject_into: [writer_full, writer_typed]
---

# Validator Writer

## Format Rules

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
- When adding a missing function entry, use the last line of the preceding ### block
  as old_text anchor, then append the new entry after it
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

  WRONG — will be skipped (appears 5–11 times):
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

  RIGHT — anchored to a specific function (unique):
    "old_text": "### `SomeFunction`\n* **Parameters:**\n  - `inst` (entity) -- Entity instance"

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

## Additional Rules

- old_text in each patch must be a MINIMAL substring sufficient for UNIQUENESS —
  include enough lines to make it unique, but not the entire function block
- Never use a bare type-only pattern like `* **Returns:** \`boolean\`` or `* **Returns:** \`nil\``
  as old_text when multiple functions share that exact Returns line
