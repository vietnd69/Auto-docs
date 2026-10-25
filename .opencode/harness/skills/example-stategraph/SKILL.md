---
name: example-stategraph
description: Model documentation page for a stategraph file.
---

<!-- ported from skills/knowledge/few_shot_stategraph.md -->

## Few-Shot Example: Stategraph File

HOW TO DETECT: source file calls `StateGraph(name, states, events, defaultstate, actionhandlers)` at top level
and defines `State{...}` entries → use this example.

Stategraphs are NOT components. Do NOT use `CreateEntity()` + `AddComponent()` patterns.
Mirror the structure below — do NOT copy the content.

```md
---
id: sgsample
title: SGSample
description: Animation state machine for the sample creature, defining locomotion, combat, and death states.
tags: [stategraph, ai, animation]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: stategraphs
source_hash: abc123
system_scope: entity
---

# SGSample

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SGSample` is an animation state machine attached to the `sample` prefab. It governs idle, walk, attack, and death animations and reacts to engine events such as `attacked`, `death`, and `locomote`. Stategraphs are accessed via `StartStateGraph()` on the entity, not called as utility functions. Major state categories: locomotion (idle, walk, run), combat (attack, hit), and lifecycle (death, taunt).

## Usage example
```lua
-- Stategraphs are attached to a prefab during construction:
inst:SetStateGraph("SGsample")

-- Trigger a state from external code:
inst.sg:GoToState("attack")

-- Query state-tag membership:
if inst.sg:HasStateTag("busy") then
    return
end

-- Listen for stategraph events from a component:
inst:ListenForEvent("attacked", function(inst, data)
    inst.sg:GoToState("hit")
end)
```

## Dependencies & tags
**External dependencies:**
- `stategraphs/commonstates` -- shared locomotion/death state factories

**Components used:**
- `combat` -- read attack damage and target
- `locomotor` -- queried for movement state during transitions
- `health` -- checked in `death` onenter to play final animation

**Tags:**
- `busy` -- added in attack/hit states to block other transitions
- `attack` -- added on attack onenter, removed on attack onexit

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `ATTACK_PROP_MUST_TAGS` | constant (local) | `{"_combat"}` | Tag filter passed to FindEntities when searching for attack targets. |
| `START_FACE_DIST` | constant (local) | `20` | Maximum distance at which the entity begins facing a player. |
| `KEEP_FACE_DIST` | constant (local) | `25` | Distance threshold beyond which face-tracking stops. |

## Main functions
### `onenter (attack)`
*   **Description:** Plays the attack animation, adds `busy` and `attack` tags, and locks the entity facing toward `inst.components.combat.target` for the duration of the swing.
*   **Parameters:** `inst` -- entity owning the stategraph
*   **Returns:** nil
*   **Error states:** Errors if `inst.components.combat` is nil — no nil guard before `inst.components.combat.target` access.

### `ontimeout (attack)`
*   **Description:** Triggered after the attack timer expires. Transitions to `idle` if the target is still alive, or `taunt` if the target was killed by the swing.
*   **Parameters:** `inst` -- entity owning the stategraph
*   **Returns:** nil
*   **Error states:** None.

### `onexit (death)`
*   **Description:** Removes the `busy` tag and clears any pending DoTaskInTime callbacks scheduled in onenter.
*   **Parameters:** `inst` -- entity owning the stategraph
*   **Returns:** nil
*   **Error states:** None.

## Events & listeners
- **Listens to:** `attacked` -- transition to `hit` state if not already busy.
- **Listens to:** `death` -- transition to `death` state.
- **Listens to:** `locomote` -- transition to `walk` or `idle` based on the locomotor's `wantstomove` flag.
```
```
