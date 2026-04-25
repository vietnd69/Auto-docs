---
name: function_format
description: Function documentation format spec, dependency section format, and few-shot contrast examples
inject_into: [analyst, analyst_chunk, analyst_merge, analyst_merge_legacy, reviewer_full, reviewer_typed, writer_full, writer_typed]
---

## Function Format

Use EXACTLY this structure for every entry in ## Main functions:

### `FunctionName(params)`
* **Description:** What this function does and when it is called.
* **Parameters:** For a single param: `param` -- type and purpose.
  For multiple params, use sub-bullets:
  - `param1` -- description
  - `param2` -- description
  Write `None` if the function takes no parameters.
* **Returns:** Return value description, or `nil` if nothing is returned.
* **Error states:** Runtime failures that can crash or silently corrupt state when
  preconditions are unmet — e.g. nil dereference with no guard, missing required
  component, invalid state transition. Do NOT list expected nil returns, normal
  conditional branches, or optional parameter fallbacks — those belong in Description
  or Returns. Write `None` ONLY when all parameters are nil-checked or the function
  handles nil gracefully.

  **Verification protocol — required before writing `None`:**
  Scan every line of the function body for:
  - `self.inst.components.X:Method()` — if there is NO `if X ~= nil` guard immediately
    before this call, it IS an error state. Document it.
  - `inst.components.X` accessed on a parameter entity — same rule applies.
  - Any chained access like `a.b.c` where `a.b` could be nil.
  A false `None` (claiming no error when an unguarded nil dereference exists) is scored
  as a critical inaccuracy. A false error (claiming crash when nil guard exists in code)
  is equally wrong — always verify the guard is absent before listing an error state.

## Multi-Path Functions

If a function has multiple meaningfully distinct code paths controlled by flags or
conditions (e.g., `recipe.manufactured`, `recipe.dropitem`, `recipe.placer`, `recipe.override_numtogive_fn`),
document EACH major branch in the Description using a sub-list:

* **Description:** [General action]. Behavior depends on recipe flags:
  - `recipe.manufactured = true` — prototyper spawns the prefab; this function only removes ingredients and returns early.
  - `recipe.dropitem = true` — crafted item is dropped on the ground instead of placed in inventory.
  - `recipe.override_numtogive_fn` set — quantity given is determined by calling this function instead of the recipe default.

Do NOT collapse multi-path functions into a single generic sentence. Missing branches
are scored as significant omissions (typically 0.5d–1d penalty per missed path).

Also document important pre-condition checks that determine early exit vs normal flow —
e.g., `PREFAB_SKINS_SHOULD_NOT_SELECT` check that causes `return nil` (not `return false`).

## Dependency Section Format

Use EXACTLY these labels in ## Dependencies & tags:

**External dependencies:**
- `name` -- usage description
(Omit this bullet entirely if external_deps JSON is empty)

**Components used:**
- `component_name` -- how it is used (methods called, properties accessed)

**Tags:**
- `tag_name` -- add / remove / check
(Write `None` if game_tags JSON is empty)

## Heading & Receiver Convention

- Function entry heading uses `### \`Name(params)\`` regardless of whether the function is
  declared as `function MyClass:Method(...)` or `function MyClass.Method(...)` in source.
- Do NOT include `self:` or `MyClass:` in the heading. The owning class is implied by the
  document's `## Main functions` section.
- For local helper functions in brain files, include the `(local)` marker AFTER the parens:
  `### \`GetWanderPoint(inst)\` (local)`.
- For functions named exactly `_ctor` (Widget/Screen/Behaviour constructors), keep the
  underscore: `### \`_ctor(prompt, on_confirm)\``.

## Constructors

- Component constructors are passed to `Class(function(self, inst) ... end)` — they are
  documented as Properties (the `self.X = value` assignments), NOT as a function entry.
- Widget/Screen/Behaviour constructors are explicit `_ctor` methods — they ARE documented as
  function entries in `## Main functions` with the parameter list.
- Brain constructors are typically empty/inherited — do NOT document them.

## Async / Coroutine Functions

- If a function is started via `inst:StartThread(...)` or contains `Sleep(...)` calls, prefix
  the Description with "**Coroutine.**" so readers know the function yields:
  `* **Description:** **Coroutine.** Periodically polls X and yields via Sleep(0.5)...`
- DoTaskInTime / DoPeriodicTask callbacks are NOT coroutines — do not mark them.

## Few-Shot Example

Mirror this format only. Do NOT copy the content:

### `ConsoleCommandPlayer()`
* **Description:** Returns the currently selected debug entity, the local player, or the first valid player in AllPlayers.
* **Parameters:** None
* **Returns:** Player instance or `nil` if no valid player found.

### `c_spawn(prefab, count, dontselect)`
* **Description:** Spawns `count` instances of `prefab` at console position. Auto-selects first spawned unless `dontselect`.
* **Parameters:**
  - `prefab` -- string prefab name
  - `count` -- number of instances (default `1`)
  - `dontselect` -- boolean to skip auto-selection
* **Returns:** Last spawned instance, or `nil`.

### `c_save()`
* **Description:** Triggers a save on master sim.
* **Parameters:** None
* **Returns:** None

## Error States Contrast

Mirror these two examples to understand the Error states field:

### `GetItem(inst, slot)`
* **Description:** Returns the item in `slot` from inst's inventory. Returns `nil` if
  the slot is empty (expected empty-slot result, not an error).
* **Parameters:**
  - `inst` -- entity with inventory component
  - `slot` -- integer slot index
* **Returns:** Entity instance, or `nil` if slot is empty.
* **Error states:** Errors if `inst` has no `inventory` component (nil dereference on
  `inst.components.inventory` — no guard present in source).

### `SetOwner(inst)`
* **Description:** Assigns `inst` as the owner. Clears existing owner if `inst` is nil.
* **Parameters:** `inst` -- entity or nil to clear
* **Returns:** None
* **Error states:** None