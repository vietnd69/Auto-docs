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

<!-- type:brains -->
### Brain Files — Main Functions

For brain files (files that call `Brain:new()` or extend Brain):
- Document `OnStart()` and `OnInitializationComplete()` as the primary functions.
- Document local helper functions (e.g., `GetFaceTargetFn`, `KeepFaceTargetFn`, `LayEgg`) that are
  passed as callbacks to behavior nodes — these define the actual AI decision logic.
- Mark local functions as `(local)` in the heading: `### GetFaceTargetFn(inst) (local)`
- In Properties: document file-scope constants (e.g., `START_FACE_DIST`, `KEEP_FACE_DIST`) with
  their literal values and the behavior they gate. Without these, the `KeepFaceTargetFn` description
  is incomplete — readers cannot know the distance thresholds.
<!-- /type -->
<!-- type:behaviours -->
### Behaviour Files — Main Functions

For files in `behaviours/` extending `BehaviourNode`:
- Document `_ctor`, `Visit`, `Reset`, `DBString` as the primary functions.
- Properties section MUST list the constructor parameters as widget-style state (e.g., `inst`, `predicate`, `maxtime`)
  AND any internal cursor state (`starttime`, `running_action`).
- Usage example shows the node embedded inside a SelectorNode/SequenceNode tree, NOT instantiated standalone.
- Do NOT use `CreateEntity()` + `AddComponent()` patterns.
<!-- /type -->
<!-- type:widgets -->
### Widget Files — Main Functions

For files in `widgets/` extending `Widget`:
- Document `_ctor` first, then layout/state methods (`SetValue`, `SetEnabled`, etc.), then lifecycle hooks
  (`OnGainFocus`, `OnLoseFocus`, `OnHide`, `OnShow`, `OnUpdate`, `OnControl`).
- Properties section lists child widgets created in `_ctor` (e.g., `icon`, `label`, `bg`) PLUS state values.
- Usage example shows `screen:AddChild(MyWidget(...))` followed by 1-2 method calls.
- Do NOT mention `inst.components` or ECS — widgets are pure UI.
<!-- /type -->
<!-- type:screens -->
### Screen Files — Main Functions

For files in `screens/` extending `Screen`:
- Document `_ctor`, `OnControl`, `OnUpdate`, plus user-facing methods (`OnConfirm`, `OnCancel`, navigation).
- Properties section lists child widgets and screen-state values (selection index, mode flags).
- Usage example shows `TheFrontEnd:PushScreen(MyScreen(...))`.
- Mention modal vs non-modal behaviour and which controls the screen captures.
<!-- /type -->
<!-- type:prefabs -->
### Prefab Files — Main Functions

For files in `prefabs/` returning `Prefab(...)`:
- Document `fn()` (client-side constructor) and `master_postinit(inst)` (server-only init) as primary functions.
- If the file defines `OnSave`, `OnLoad`, `OnEntityWake`, `OnEntitySleep`, document them as separate entries.
- Properties section lists `assets`, `prefabs` arrays + key `TUNING.*` constants the prefab consumes.
- Usage example shows `SpawnPrefab("name")` and the assets array.
- Dependencies & tags MUST list every component attached, every stategraph/brain set, every tag added.
<!-- /type -->
<!-- type:replica -->
### Replica Files — Main Functions

For files matching `*_replica.lua`:
- Document the constructor (declares netvars), each `Get*` accessor (read-only on client), and any
  `Set*` methods that route to the master via netvar assignment.
- Properties section lists every netvar (`net_bool`, `net_int`, `net_string`, etc.) with its default
  value and what state it mirrors from the master component.
- Usage example shows client-side access: `if inst.replica.combat:CanTarget(other) then ... end`.
- Mark methods that ONLY run on master with `(master only)` and methods that ONLY run on client with `(client only)`.
<!-- /type -->
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
