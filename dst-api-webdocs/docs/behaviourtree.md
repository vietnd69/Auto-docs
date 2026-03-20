---
id: behaviourtree
title: Behaviourtree
description: Provides a behavior tree system for AI entity decision-making with various node types for sequencing, selection, and event handling.
tags: [ai, brain, behaviour, decision]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: 5126e164
system_scope: brain
---

# Behaviourtree

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
`Behaviourtree` provides a behavior tree implementation for AI entity decision-making in Don't Starve Together. It defines a hierarchical node system where entities can evaluate conditions, execute actions, wait for timers, and respond to events. The system is used by brain components to control mob AI behavior patterns. The tree evaluates nodes in a depth-first manner, with each node reporting status as `SUCCESS`, `FAILED`, `READY`, or `RUNNING`.

## Usage example
```lua
local root = SequenceNode({
    ConditionNode(function() return inst.components.hunger:Percent() < 0.5 end, "IsHungry"),
    ActionNode(function() inst.components.locomotor:GoToTarget(food) end, "FindFood")
})

local bt = BT(inst, root)
bt:Update()
bt:Reset()
```

## Dependencies & tags
**Components used:** None directly (accesses `inst` passed to constructor)
**Tags:** None identified.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `inst` | Entity | `nil` | The entity instance that owns this behaviour tree. |
| `root` | BehaviourNode | `nil` | The root node of the behaviour tree. |
| `forceupdate` | boolean | `false` | Forces the tree to update on the next tick when `true`. |
| `status` | string | `READY` | Current execution status of a node (`SUCCESS`, `FAILED`, `READY`, `RUNNING`). |
| `children` | table | `nil` | Array of child nodes for composite node types. |
| `parent` | BehaviourNode | `nil` | Reference to the parent node in the tree hierarchy. |
| `idx` | number | `1` | Current child index for sequence/selector iteration. |
| `period` | number | `1` | Evaluation period for `PriorityNode` in seconds. |

## Main functions
### `BT(inst, root)`
*   **Description:** Constructor that creates a new behaviour tree attached to an entity.
*   **Parameters:** `inst` (Entity) - the entity instance; `root` (BehaviourNode) - the root node of the tree.
*   **Returns:** New `BT` instance.

### `Update()`
*   **Description:** Executes one tick of the behaviour tree, visiting all nodes and advancing the tree state.
*   **Parameters:** None.
*   **Returns:** Nothing.

### `Reset()`
*   **Description:** Resets the entire tree back to `READY` state, clearing all node progress.
*   **Parameters:** None.
*   **Returns:** Nothing.

### `Stop()`
*   **Description:** Stops all running nodes and triggers `OnStop` callbacks if defined.
*   **Parameters:** None.
*   **Returns:** Nothing.

### `ForceUpdate()`
*   **Description:** Marks the tree to force update on the next tick, bypassing sleep time optimization.
*   **Parameters:** None.
*   **Returns:** Nothing.

### `GetSleepTime()`
*   **Description:** Returns the time in seconds until the tree should next update, used for optimization.
*   **Parameters:** None.
*   **Returns:** `number` - seconds until next update, or `0` if force update is pending.

### `BehaviourNode(name, children)`
*   **Description:** Base constructor for all behaviour tree nodes.
*   **Parameters:** `name` (string) - optional node name; `children` (table) - optional array of child nodes.
*   **Returns:** New `BehaviourNode` instance.

### `ConditionNode(fn, name)`
*   **Description:** Creates a node that evaluates a condition function, returning `SUCCESS` or `FAILED`.
*   **Parameters:** `fn` (function) - condition function returning boolean; `name` (string) - optional node name.
*   **Returns:** New `ConditionNode` instance.

### `ActionNode(action, name)`
*   **Description:** Creates a node that executes an action function and returns `SUCCESS`.
*   **Parameters:** `action` (function) - action to execute; `name` (string) - optional node name.
*   **Returns:** New `ActionNode` instance.

### `WaitNode(time)`
*   **Description:** Creates a node that waits for a specified duration before returning `SUCCESS`.
*   **Parameters:** `time` (number or function) - wait duration in seconds.
*   **Returns:** New `WaitNode` instance.

### `SequenceNode(children)`
*   **Description:** Creates a node that executes children in order, failing if any child fails.
*   **Parameters:** `children` (table) - array of child nodes.
*   **Returns:** New `SequenceNode` instance.

### `SelectorNode(children)`
*   **Description:** Creates a node that executes children until one succeeds, failing if all fail.
*   **Parameters:** `children` (table) - array of child nodes.
*   **Returns:** New `SelectorNode` instance.

### `PriorityNode(children, period, noscatter)`
*   **Description:** Creates a node that periodically evaluates children by priority, executing the first successful one.
*   **Parameters:** `children` (table) - array of child nodes; `period` (number) - evaluation interval; `noscatter` (boolean) - disables random time offset.
*   **Returns:** New `PriorityNode` instance.

### `ParallelNode(children, name)`
*   **Description:** Creates a node that runs all children in parallel, succeeding when all complete.
*   **Parameters:** `children` (table) - array of child nodes; `name` (string) - optional node name.
*   **Returns:** New `ParallelNode` instance.

### `EventNode(inst, event, child, priority)`
*   **Description:** Creates a node that listens for an entity event and executes a child when triggered.
*   **Parameters:** `inst` (Entity) - entity to listen on; `event` (string) - event name; `child` (BehaviourNode) - node to execute; `priority` (number) - optional priority value.
*   **Returns:** New `EventNode` instance.

### `WhileNode(cond, name, node)`
*   **Description:** Helper function creating a `ParallelNode` that checks condition every update.
*   **Parameters:** `cond` (function) - condition function; `name` (string) - node name; `node` (BehaviourNode) - node to execute while condition holds.
*   **Returns:** `ParallelNode` instance.

### `IfNode(cond, name, node)`
*   **Description:** Helper function creating a `SequenceNode` that checks condition once before executing.
*   **Parameters:** `cond` (function) - condition function; `name` (string) - node name; `node` (BehaviourNode) - node to execute if condition passes.
*   **Returns:** `SequenceNode` instance.

### `LatchNode(inst, latchduration, child)`
*   **Description:** Creates a node that only executes its child after a latch duration has elapsed.
*   **Parameters:** `inst` (Entity) - entity instance; `latchduration` (number or function) - duration before execution; `child` (BehaviourNode) - node to execute after latch.
*   **Returns:** New `LatchNode` instance.

## Events & listeners
- **Listens to:** `EventNode` registers listeners via `inst:ListenForEvent(event, fn)` for the specified event name passed to constructor.
- **Pushes:** None directly (delegates event pushing to entity via `inst:PushEvent`).