---
id: brain
title: Brain
description: Manages the lifecycle, scheduling, and event handling of AI behavior trees for entities.
tags: [ai, brain, entity, scheduling]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: fdb4d2f6
system_scope: brain
---

# Brain

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
The `brain.lua` file defines the core architecture for AI behavior management in Don't Starve Together. It introduces two primary classes: `Brain` and `BrainWrangler` (instantiated as `BrainManager`).

The `Brain` class is attached to individual entities to control their behavior tree (`bt`) execution. It handles states such as paused, stopped, and sleeping, and provides an event system for internal behavior logic. The `BrainManager` acts as a global scheduler that dictates when specific entity brains should update, hibernate, or wake based on simulation ticks. This system optimizes performance by suspending AI updates for entities that are asleep or far from players.

## Usage example
```lua
-- Accessing an existing brain on an entity (inst)
local brain = inst.brain

-- Pause the brain to stop AI updates temporarily
if brain then
    brain:Pause()
end

-- Resume AI updates
if brain then
    brain:Resume()
end

-- Register a local event handler within the brain
brain:AddEventHandler("on_alert", function(data)
    print("Alert received:", data)
end)
```

## Dependencies & tags
**Components used:** None directly added by this script. It expects the entity (`inst`) to have valid entity methods (e.g., `IsAsleep`, `entity:IsValid`).
**Tags:** None identified.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `inst` | Entity | `nil` | The entity instance that owns this brain. |
| `paused` | boolean | `false` | Indicates if the brain is temporarily suspended. |
| `stopped` | boolean | `true` | Indicates if the brain has been fully stopped. |
| `events` | table | `{}` | Registry of local event callbacks. |
| `bt` | BehaviorTree | `nil` | The behavior tree object attached to this brain. |
| `updaters` | table | `{}` | (BrainManager) List of brains currently updating. |
| `hibernaters` | table | `{}` | (BrainManager) List of brains currently hibernating. |
| `tickwaiters` | table | `{}` | (BrainManager) Map of tick times to brains waking up. |

## Main functions
### `Pause()`
*   **Description:** Suspends the brain's update loop without marking it as stopped. Removes the brain from the `BrainManager` update list.
*   **Parameters:** None.
*   **Returns:** Nothing.

### `Resume()`
*   **Description:** Resumes the brain's update loop. Re-adds the brain to the `BrainManager` update list if it is not stopped.
*   **Parameters:** None.
*   **Returns:** Nothing.

### `AddEventHandler(event, fn)`
*   **Description:** Registers a callback function for a specific local event string.
*   **Parameters:** `event` (string) - The event name. `fn` (function) - The callback to execute when the event is pushed.
*   **Returns:** Nothing.

### `PushEvent(event, data)`
*   **Description:** Triggers a local event, executing the registered handler if one exists.
*   **Parameters:** `event` (string) - The event name. `data` (table) - Optional data passed to the handler.
*   **Returns:** Nothing.

### `ForceUpdate()`
*   **Description:** Wakes the brain via `BrainManager` and forces an immediate update on the behavior tree.
*   **Parameters:** None.
*   **Returns:** Nothing.

### `GetSleepTime()`
*   **Description:** Queries the attached behavior tree (`bt`) for the recommended sleep duration.
*   **Parameters:** None.
*   **Returns:** `number` - Time in seconds, or `0` if no behavior tree is attached.

### `BrainManager:Wake(inst)`
*   **Description:** Moves the brain associated with `inst` from hibernation to the active updater list.
*   **Parameters:** `inst` (Entity) - The entity whose brain should wake.
*   **Returns:** Nothing.

### `BrainManager:Hibernate(inst)`
*   **Description:** Moves the brain associated with `inst` from the active updater list to hibernation.
*   **Parameters:** `inst` (Entity) - The entity whose brain should hibernate.
*   **Returns:** Nothing.

### `BrainManager:Sleep(inst, time_to_wait)`
*   **Description:** Schedules the brain to wake up after a specific duration.
*   **Parameters:** `inst` (Entity) - The entity whose brain should sleep. `time_to_wait` (number) - Duration in seconds.
*   **Returns:** Nothing.
*   **Error states:** If `time_to_wait` results in `0` ticks, it defaults to `1` tick.

## Events & listeners
- **Listens to:** None identified via global event system. Internal logic checks `inst:IsAsleep()` during updates.
- **Pushes:** Local events via `PushEvent(event, data)` trigger handlers registered with `AddEventHandler`.