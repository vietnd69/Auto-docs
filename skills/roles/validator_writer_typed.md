---
name: validator_writer_typed
description: TypedOp selection rules and behavioral constraints for the typed writer (chunked validation path)
inject_into: [writer_typed]
---

# Validator Writer — Typed Mode

## Op Selection by rule_id

Choose the op type based on the finding's rule_id:

| rule_id | Correct op | Notes |
|---------|-----------|-------|
| WRONG_DESCRIPTION | `rewrite_function` | Rewrite the full ### block with corrected description |
| WRONG_ERROR_STATE | `update_field` field=`Error states` | Replace only the Error states line |
| MISPLACED_ERROR_STATE | `rewrite_function` | Move content from Error states into Description, keep `Error states: None` |
| WRONG_VALUE | `update_field` | Replace the specific field value |
| MISSING_PARAM / EXTRA_PARAM | `rewrite_function` | Rewrite the full ### block to fix the Parameters list |
| MISSING_ENTRY / EXTRA_ENTRY | `update_section` | Add or remove an entry in Dependencies & tags or Events |
| WRONG_FILE_TYPE | `update_section` section=`## Overview` | Rewrite the Overview section |
| INACCURATE_DESCRIPTION | `rewrite_function` OR `update_field` field=`Description` | Prefer `update_field` when only the description text is wrong |

**NEVER use `delete_function` for any of the above rule_ids.**
`delete_function` is ONLY for functions that do not exist anywhere in the Lua source (genuine hallucinations). The reviewer does NOT emit a hallucination rule_id — if the reviewer reports WRONG_DESCRIPTION or WRONG_ERROR_STATE, the function exists and must be fixed, not deleted.

## Behavioral Constraints

- NEVER rename or reformat `### `` headings
- NEVER rename standard field labels: Description, Parameters, Returns, Error states
- NEVER delete the `* **Error states:**` line entirely — if reviewer asks to remove an error state, update the value to `None`
- NEVER add a new `### ` function block unless the reviewer explicitly says a function is missing
- NEVER use `update_section` for `## Main functions` to fix a single function — emit a `rewrite_function` per function instead

## rewrite_function Content Rules

When emitting `rewrite_function`, the `content` field MUST:
- Start with the `### `` heading line (verbatim, unchanged)
- Include ALL standard fields: Description, Parameters, Returns, Error states
- Match the Lua source exactly for signatures and behavior
- Preserve surrounding functions — content contains ONLY the single ### block being replaced
