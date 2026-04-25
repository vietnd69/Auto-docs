---
name: few_shot_brain
description: Brain file few-shot example — expected output for AI behavior tree documentation with local helper functions and file-scope constants
inject_into: [analyst, analyst_chunk]
---

## Few-Shot Example: Brain File

HOW TO DETECT: source file extends `Brain` class via `Class(Brain, ...)` or defines a Brain subclass that overrides `OnStart()` to return a `BehaviourTree`.

Brain files differ from components: they have NO Class(function(self, inst) ...) constructor that
defines self.X properties. Instead they have a small constructor + `OnStart()` returning a behaviour tree.
Local helper functions passed to behaviour nodes ARE part of the documented API — they encode AI logic.
File-scope constants ARE properties — they gate behaviour thresholds.

Mirror the structure below — do NOT copy the content.

```md
---
id: samplebrain
title: SampleBrain
description: AI brain for the sample creature, choosing between flee, eat, and idle behaviours based on player proximity and hunger state.
tags: [brain, ai, behaviour-tree]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: brains
source_hash: abc123
system_scope: brain
---

# SampleBrain

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SampleBrain` is the AI behaviour tree for the `sample` prefab. It selects between fleeing players within `SEE_PLAYER_DIST`, eating from nearby food sources, and idle wandering. Brains are paused when the entity is far from any player and resume automatically on player proximity. Brain trees are attached via `RunBrain(inst, SampleBrain)`.

## Usage example
```lua
-- Brains are attached during prefab construction:
local brain = require("brains/samplebrain")
inst:SetBrain(brain)

-- The framework calls OnStart() to obtain the behaviour tree.
-- Manual access to the running tree:
if inst.brain ~= nil and inst.brain.bt ~= nil then
    -- inspect or reset the running behaviour tree
end
```

## Dependencies & tags
**External dependencies:**
- `behaviourtree` -- BehaviourTree, SequenceNode, SelectorNode, etc.
- `behaviours/wander` -- Wander behaviour node factory
- `behaviours/runaway` -- RunAway behaviour node factory

**Components used:**
- `combat` -- read current target via `inst.components.combat.target`
- `hunger` -- queried for hunger threshold in EatFood node
- `locomotor` -- driven indirectly by Wander/RunAway nodes

**Tags:**
- `busy` -- checked before triggering the eat sequence (skip if entity is busy)

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `SEE_PLAYER_DIST` | constant (local) | `8` | Range in tiles within which the brain triggers the flee branch. |
| `WANDER_DIST` | constant (local) | `20` | Maximum wander radius from the entity's current home position. |
| `MIN_FOLLOW_DIST` | constant (local) | `3` | Minimum follow distance used by the FollowLeader node. |

## Main functions
### `OnStart()` (Brain method)
*   **Description:** Constructs the root SelectorNode of the behaviour tree: prioritises flee over eat over wander. Called once when the brain is attached and on resume after pause.
*   **Parameters:** `self` -- the brain instance (implicit via method syntax)
*   **Returns:** BehaviourTree root node
*   **Error states:** Errors if `self.inst` is nil at the moment OnStart fires (engine guarantees non-nil; included for completeness).

### `GetWanderPoint(inst)` (local)
*   **Description:** Helper passed to the Wander node. Returns the entity's home position table `{x, y, z}` so wandering recenters around its spawn point instead of drifting.
*   **Parameters:** `inst` -- entity owning the brain
*   **Returns:** position table `{x, y, z}` or `nil` if the entity has no recorded home
*   **Error states:** None.

### `ShouldRunAway(target)` (local)
*   **Description:** Helper passed to the RunAway node. Returns true if `target` is a player within `SEE_PLAYER_DIST` and the entity is not currently in a `busy` state.
*   **Parameters:** `target` -- candidate threat entity
*   **Returns:** boolean
*   **Error states:** None — guards `target == nil` and `target.HasTag` access internally.

## Events & listeners
None — brain trees react to component state, not engine events directly. Event handling is done in the brain's host stategraph or via component subscriptions.
```
```