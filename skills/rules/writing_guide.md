---
name: writing_guide
description: How to write each documentation section — overview, usage examples, constructor rule, section-specific guidance
inject_into: [analyst, analyst_chunk, analyst_merge, analyst_merge_legacy]
---

# Writing Guide

## Constructor Rule

- Document `Class(function(self, ...) ... end)` constructors accordingly.
- The first parameter after `self` may be `inst`, `data`, or any other name — document as-is.

## Overview Writing

- [Component] State: what this component does + its role in the ECS system.
  Mention key relationships with other components (from Connected Files context).
- [Data config] State: what static data this file defines, how it is structured,
  and how other systems access it via require(). Do NOT describe it as a component
  or reference the ECS system.
- 2-5 sentences. No padding.

## Usage Example Writing

- [Component] Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.
- [Data config] Show `require()` followed by index access to the returned table (e.g., `Table[1]`).
  Do NOT use `CreateEntity()`, `AddComponent`, or `inst.components`.
- 5-15 lines. Use a fenced code block with `lua` syntax highlighting.
- Use the component's actual function names from the documentation. No generic placeholder names.

## Dependencies & Tags Section

Use EXACTLY these labels (see function_format skill for full format spec):
- **External dependencies:** List `require()` imports and external module usage. Omit this label entirely if there are none.
- **Components used:** List components accessed via `inst.components.X` or added via `inst:AddComponent("X")`.
- **Tags:** List any tags this component adds, removes, or checks (e.g., `inst:AddTag("tag")`).
- If none are apparent, write "None identified."

## Properties Section

- Create a Markdown table of key public variables/properties initialized in the constructor.
- Columns: `Property` | `Type` (infer if possible) | `Default Value` | `Description`.
- If no properties exist, the table MUST include a None data row: `| None | | | No properties are defined. |` — do NOT write "No public properties" as prose.

## Main Functions Section

- Document the core functional methods using the format defined in the function_format skill.
- For each function: Description, Parameters, Returns, Error states.
- Error states = crash or silent state corruption only. NOT normal conditional returns.

### Brain Files — Main Functions

For brain files (files that call `Brain:new()` or extend Brain):
- Document `OnStart()` and `OnInitializationComplete()` as the primary functions.
- Document local helper functions (e.g., `GetFaceTargetFn`, `KeepFaceTargetFn`, `LayEgg`) that are
  passed as callbacks to behavior nodes — these define the actual AI decision logic.
- Mark local functions as `(local)` in the heading: `### GetFaceTargetFn(inst) (local)`
- In Properties: document file-scope constants (e.g., `START_FACE_DIST`, `KEEP_FACE_DIST`) with
  their literal values and the behavior they gate. Without these, the `KeepFaceTargetFn` description
  is incomplete — readers cannot know the distance thresholds.

### Non-Trivial Mechanics

If a function's internal logic is non-obvious — especially arithmetic involving accumulators,
accumulator-ceiling-subtract patterns, or multi-step state transitions — describe the mechanism
explicitly in the Description. Do NOT reduce it to a vague phrase like "skill-based bonus days"
when the actual logic is `accumulator = accumulator + bonus; days = math.ceil(accumulator); accumulator = accumulator - days`.
Readers debugging growth rates or bonus calculations will be blocked without this detail.

### Return Value Accuracy

Before writing the Returns field, mentally trace the function's return statements:
- `Shave()`-style functions: if `self.bits` is never decremented inside the function but the
  delta is computed from external state (`dropbits = oldbits - self.bits`), the doc must
  reflect this — NOT claim the function "removes beard bits" internally.
- Distinguish between "returns nil implicitly" vs "returns false, 'REASON'" — they have
  different meanings for callers.
- Verify that the description of WHAT is returned matches the actual `return` statements,
  not a paraphrase of the function's intent.

## Events & Listeners Section

- **Listens to:** Events registered via `inst:ListenForEvent(event, fn)`.
- **Pushes:** Events fired via `inst:PushEvent(event, data)`.
- If there are no events or listeners, omit this entire section.
