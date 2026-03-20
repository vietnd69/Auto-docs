---
id: bufferedaction
title: Bufferedaction
description: Represents a queued action request, validating entity states and inventory ownership before execution.
tags: [action, input, inventory]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: 8caba818
system_scope: player
---

# Bufferedaction

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
`BufferedAction` is a utility class that encapsulates a player action request before it is executed. It stores references to the doer, target, inventory object, and action definition, performing validation checks to ensure entities are valid and ownership states are correct. This buffering system prevents actions from executing if conditions change (e.g., item dropped, target removed) between the input request and the execution tick.

## Usage example
```lua
local action = BufferedAction(doer, target, ACTIONS.CHOP, axe, pos)
action:AddSuccessAction(function() 
    print("Action completed successfully") 
end)
local success, reason = action:Do()
if not success then
    print("Action failed:", reason)
end
```

## Dependencies & tags
**Components used:** `inventoryitem` (accessed via `target.components.inventoryitem` and `invobject.replica.inventoryitem`)
**Tags:** None identified.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `doer` | Entity | `nil` | The entity performing the action. |
| `target` | Entity | `nil` | The entity being acted upon. |
| `action` | Table | `nil` | The action definition (e.g., `ACTIONS.CHOP`). |
| `invobject` | Entity | `nil` | The inventory item used to perform the action. |
| `pos` | DynamicPosition | `nil` | The target position for the action. |
| `recipe` | String | `nil` | Crafting recipe identifier if applicable. |
| `distance` | Number | `action.distance` | Required distance to perform the action. |
| `arrivedist` | Number | `action.arrivedist` | Distance considered "arrived" for navigation. |
| `forced` | Boolean | `nil` | If true, bypasses certain walkability checks. |
| `rotation` | Number | `0` | Target rotation angle in radians. |
| `onsuccess` | Table | `{}` | List of callbacks to run on success. |
| `onfail` | Table | `{}` | List of callbacks to run on failure. |
| `autoequipped` | Boolean | `nil` | True if the inventory object was auto-equipped. |
| `reason` | String | `nil` | Stores the failure reason after `Do()` executes. |

## Main functions
### `Do()`
*   **Description:** Executes the buffered action if validation passes. Triggers success or failure callbacks accordingly.
*   **Parameters:** None.
*   **Returns:** `success` (boolean), `reason` (string/nil).
*   **Error states:** Returns `false` immediately if `IsValid()` fails.

### `IsValid()`
*   **Description:** Checks if the action is still permissible. Validates entity existence, inventory ownership, and platform walkability.
*   **Parameters:** None.
*   **Returns:** `boolean` - `true` if the action can proceed.
*   **Error states:** Returns `false` if the doer, target, or inventory object is invalid or ownership has changed.

### `GetActionString()`
*   **Description:** Retrieves the localized string name for the action, handling overrides from the doer or action definition.
*   **Parameters:** None.
*   **Returns:** `string` - The action name.

### `AddSuccessAction(fn)`
*   **Description:** Registers a callback function to execute when the action succeeds.
*   **Parameters:** `fn` (function) - The callback to invoke.
*   **Returns:** Nothing.

### `AddFailAction(fn)`
*   **Description:** Registers a callback function to execute when the action fails.
*   **Parameters:** `fn` (function) - The callback to invoke.
*   **Returns:** Nothing.

### `GetActionPoint()`
*   **Description:** Returns the world coordinates of the action target.
*   **Parameters:** None.
*   **Returns:** `Vector3` or `nil`.

### `SetActionPoint(pt)`
*   **Description:** Updates the target position for the action.
*   **Parameters:** `pt` (Vector3 or DynamicPosition) - The new position.
*   **Returns:** Nothing.

### `Fail()`
*   **Description:** Manually triggers the failure state, executing all `onfail` callbacks and clearing queues.
*   **Parameters:** None.
*   **Returns:** Nothing.

### `Succeed()`
*   **Description:** Manually triggers the success state, executing all `onsuccess` callbacks and clearing queues.
*   **Parameters:** None.
*   **Returns:** Nothing.

## Events & listeners
None identified. This class uses internal callback tables (`onsuccess`, `onfail`) rather than the entity event system.