# Skill: few_shot

=== FEW-SHOT EXAMPLE ===
Below is a short example of the expected output format for a simple component. Use this as a reference for structure and tone — do NOT copy the content.

---
id: samplecomp
title: SampleComp
description: Manages a simple timer-based buff on an entity.
tags: [combat, buff]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: components
source_hash: abc123
system_scope: entity
---

# SampleComp

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SampleComp` applies a timed damage buff to an entity. It is typically added to combat-capable prefabs and works alongside the `combat` component to modify outgoing damage for a fixed duration.

## Usage example
```lua
local inst = CreateEntity()
inst:AddComponent("samplecomp")
inst.components.samplecomp:SetDuration(10)
inst.components.samplecomp:Activate()
```

## Dependencies & tags
**Components used:** `combat`
**Tags:** Adds `buffed`; checks `debuffed`.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `duration` | number | `0` | How long the buff lasts in seconds. |
| `active` | boolean | `false` | Whether the buff is currently running. |

## Main functions
### `SetDuration(seconds)`
*   **Description:** Sets the total duration of the buff.
*   **Parameters:** `seconds` (number) - duration in seconds.
*   **Returns:** Nothing.

### `Activate()`
*   **Description:** Starts the buff timer and adds the `buffed` tag.
*   **Parameters:** None.
*   **Returns:** Nothing.
*   **Error states:** Returns early with no effect if `duration` is `<= 0`.

## Events & listeners
- **Listens to:** `onhitother` - refreshes the buff timer on hit.
- **Pushes:** `buff_expired` - fired when the timer reaches zero.
(End of example)
