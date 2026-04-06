---
name: function_format
description: Function documentation format spec, dependency section format, and few-shot contrast examples
inject_into: [analyst, analyst_merge, analyst_merge_legacy]
---

=== FUNCTION FORMAT ===
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

=== DEPENDENCY SECTION FORMAT ===
Use EXACTLY these labels in ## Dependencies & tags:

**External dependencies:**
- `name` -- usage description
(Omit this bullet entirely if external_deps JSON is empty)

**Components used:**
- `component_name` -- how it is used (methods called, properties accessed)

**Tags:**
- `tag_name` -- add / remove / check
(Write `None` if game_tags JSON is empty)

=== FEW-SHOT EXAMPLE ===
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

=== ERROR STATES CONTRAST ===
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
