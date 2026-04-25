---
name: few_shot_behaviour
description: Behaviour node few-shot example — expected output for files in behaviours/ that extend BehaviourNode
inject_into: [analyst, analyst_chunk]
---

## Few-Shot Example: Behaviour File

HOW TO DETECT: file in `behaviours/` declares `MyBehaviour = Class(BehaviourNode, ...)`.
Behaviour files define a single AI node, not a full tree. They expose `Visit()`, `Reset()`,
`DBString()` and are consumed by Brain files via SelectorNode/SequenceNode composition.

Mirror the structure — do NOT copy the content.

```md
---
id: samplenode
title: SampleNode
description: BehaviourNode that runs a custom action while a predicate holds; reports SUCCESS once the action completes.
tags: [behaviour, ai, behaviour-tree]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: behaviours
source_hash: abc123
system_scope: brain
---

# SampleNode

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SampleNode` is a custom BehaviourNode that runs a target-driven action while a user-supplied predicate returns true. Returns READY/RUNNING/SUCCESS/FAILED in the standard BehaviourNode contract. Used by brains as a reusable subtree fragment composed inside SelectorNode/SequenceNode.

## Usage example
```lua
-- Embed inside a brain's behaviour tree:
local SampleNode = require("behaviours/samplenode")

local function ShouldRun(inst)
    return inst.components.hunger:GetPercent() < 0.5
end

local root = SelectorNode{
    SampleNode(self.inst, ShouldRun, 5),  -- run while predicate true, max 5s
    Wander(self.inst, GetHomePos, WANDER_DIST),
}
```

## Dependencies & tags
**External dependencies:**
- `behaviourtree` -- BehaviourNode base class, status constants (READY, RUNNING, SUCCESS, FAILED)

**Components used:**
- `combat` -- queried in Visit() for current target

**Tags:** None.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `inst` | entity | --- | Entity owning the behaviour. Set by constructor. |
| `predicate` | function | --- | Function `(inst) -> boolean`; node runs only while it returns true. |
| `maxtime` | number | `nil` | Optional time-out in seconds; node returns FAILED if exceeded. |
| `starttime` | number | `nil` | Internal: timestamp when Visit() first transitioned to RUNNING. |

## Main functions
### `_ctor(inst, predicate, maxtime)`
*   **Description:** Initialises a SampleNode bound to `inst`, gated by `predicate`, with optional `maxtime`. Calls `BehaviourNode._ctor(self, "SampleNode")`.
*   **Parameters:**
    - `inst` -- entity owning the behaviour
    - `predicate` -- function `(inst) -> boolean`
    - `maxtime` -- optional number, seconds before forced FAILED
*   **Returns:** nil
*   **Error states:** None — accepts nil maxtime and nil predicate (treats nil predicate as always-true).

### `Visit()`
*   **Description:** Called each tick by the parent node. Transitions status: READY → RUNNING when predicate true; RUNNING → SUCCESS when predicate goes false; RUNNING → FAILED when maxtime exceeded.
*   **Parameters:** None (uses self.inst, self.predicate, self.maxtime)
*   **Returns:** nil — sets self.status as side effect
*   **Error states:** Errors if `self.inst` is nil — no nil guard before predicate invocation.

### `Reset()`
*   **Description:** Called by the parent when the node is preempted. Clears `self.starttime` so the next Visit() starts fresh.
*   **Parameters:** None
*   **Returns:** nil
*   **Error states:** None.

### `DBString()`
*   **Description:** Debug string used by the brain debugger overlay; returns predicate state and elapsed time.
*   **Parameters:** None
*   **Returns:** string
*   **Error states:** None.

## Events & listeners
None.
```
