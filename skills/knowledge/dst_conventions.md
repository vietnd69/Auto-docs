---
name: dst_conventions
description: DST engine conventions — ECS, events, tags, network replication, stategraphs, brains, prefabs, scheduler
inject_into: [analyst, analyst_chunk, analyst_merge, analyst_intermediate, analyst_merge_legacy, reviewer_full, reviewer_typed]
---

## Entity Component System

- Components attach to entities: `inst:AddComponent("name")` / access via `inst.components.name`.
- `self.inst` — the entity instance that owns this component.
- Constructor: `Class(function(self, ...) ... end)` — NOT `_ctor`. First param after `self` varies
  (commonly `inst` for components, `data` for utility classes).
- Every component is a Lua table; methods are functions stored in that table.

## Event System

- `inst:ListenForEvent(event, fn)` — subscribe to event on entity.
- `inst:PushEvent(event, data)` — fire event on entity; data is an optional table.
- `inst:RemoveEventCallback(event, fn)` — unsubscribe a specific listener.
- World-level events: `TheWorld:ListenForEvent` / `TheWorld:PushEvent`.

## Tag System

- `inst:AddTag("tag")` / `inst:RemoveTag("tag")` / `inst:HasTag("tag")`.
- Tags affect targeting (`FindEntities`, `FindClosestEntityWithTag`) and combat exclusions.
- Common tags: "player", "monster", "structure", "fire", "invisible", "notarget".

## Network Replication

- `self.inst.replica.X` — client-side replica of component X (read-only on client).
- NetVars: `net_bool`, `net_int`, `net_float`, `net_string`, `net_entity` synchronize state.
- `TheWorld.ismastersim` — true only on the server; guards server-only logic.
- `TheNet:GetIsClient()` / `TheNet:GetIsServer()` — runtime environment checks.
- `SendRPCToServer(RPC.Name, ...)` / `SendRPCToClient(client, RPC.Name, ...)` — RPCs.

## Global References

- `TheWorld` — world entity; holds components like `map`, `weather`, `season`.
- `TheNet` — networking and lobby interface.
- `ThePlayer` — local player entity (client); may be nil on server before join.
- `AllPlayers` — list of all connected player entities (server).
- `TheSim` — simulation: `GetTick()`, `GetGameID()`, file I/O, scheduling.
- `TheInput` — keyboard/mouse input handling.
- `TUNING` — global balance constants table (damage, durations, quantities).
- `STRINGS` — localization string table.
- `ACTIONS` / `BufferedAction` — action system for player verb interactions.

## Stategraphs

- `StateGraph(name, states, events, defaultstate, actionhandlers)` defines animation state machines.
- `State{name, onenter, onexit, ontimeout, events, timeline}` — individual state.
- `EventHandler(event, fn)` — handles events inside a stategraph.
- `TimeEvent(time, fn)` — fires function at specific animation frame.

### Stategraph Documentation Rules

Stategraphs are NOT component files. Do NOT use component patterns when documenting them.

**Overview:** Describe the stategraph as an animation state machine, not as a set of utility functions.
Explicitly state: "Stategraphs are accessed via `StartStateGraph()`, not called as utility functions."
List the major state categories (locomotion, combat, tool use, etc.) and key component integrations.

**Usage example:** Show `player.sg:GoToState()`, `player.sg:HasStateTag()`, and `ListenForEvent` on the entity.
Do NOT show `CreateEntity()` + `AddComponent()` — stategraphs are not components.

**Properties:** Document only file-scope local tables and constants used across multiple states
(e.g., `ATTACK_PROP_MUST_TAGS`, `START_FACE_DIST`). Do NOT list state-local variables.

**Main functions — State Handlers:** Document state handler functions grouped by state name.
Use the format: `### onenter (statename)` / `### onexit (statename)` / `### ontimeout (statename)`.
- Only document states with non-trivial logic (more than a simple animation play or tag add/remove).
- Skip states whose onenter/onexit is a one-liner (e.g., `inst.sg:SetTimeout(1)`).
- If a file has 100+ states, document representative groups: death states, transformation states,
  combat states, and any state with error-prone logic. Note omissions explicitly.
- Do NOT document `TimeEvent` callbacks as separate functions — describe them in the parent state's entry.

**Events:** Document `EventHandler` entries that react to engine events (not state-internal handlers).
These are stategraph-level event listeners, not component event listeners.

## Brains (AI)

- `Brain:new(inst)` creates a behavior tree for AI entities.
- Nodes: `SequenceNode`, `SelectorNode`, `ConditionNode`, `WaitNode`, `DoAction`.
- `RunBrain(inst, brain)` attaches and starts a brain.
- Brains are paused automatically when the entity is far from players.

## Prefab System

- `Prefabs["name"] = Prefab(name, fn, assets, deps)` registers a spawnable entity.
- Inside the prefab function: `CreateEntity()` -> attach components -> return inst.
- `SpawnPrefab("name")` — instantiates a prefab at runtime.
- `MakePlanarPhysics`, `MakeInventoryPhysics` — common physics helpers.

## Scheduler / Coroutines

- `inst:DoTaskInTime(delay, fn)` — one-shot delayed task.
- `inst:DoPeriodicTask(period, fn, initial_delay)` — repeating task.
- `inst:StartThread(fn)` — coroutine attached to entity lifecycle.
- `Sleep(seconds)` inside a coroutine yields execution (non-blocking).
- `inst:ClearScheduledTask(task)` — cancel a pending task.

## Save / Load Lifecycle

- `OnSave(self)` — return a table of state to persist; called when world saves.
- `OnLoad(self, data)` — restore state from the saved table on world load.
- `OnEntityWake(self)` — called when entity becomes active (player nearby).
- `OnEntitySleep(self)` — called when entity goes idle (no players nearby).
- `OnRemoveEntity(self)` / `OnRemoveFromEntity(self)` — cleanup when entity is removed.

These are component-level hooks. Document them as Main functions when present.

## AnimState

- `inst.AnimState:PlayAnimation(name, loop)` — start an animation (single play unless loop=true).
- `inst.AnimState:PushAnimation(name, loop)` — queue after current animation finishes.
- `inst.AnimState:SetBank(bank)` / `SetBuild(build)` — switch animation bank/build at runtime.
- `inst.AnimState:OverrideSymbol(symbol, build, src)` — swap a single symbol for skin/customisation.
- Heavily used in stategraphs (`onenter`/`ontimeout`) and prefab fn().

## SoundEmitter

- `inst.SoundEmitter:PlaySound(path, name, volume, ...)` — play a one-shot or looping sound.
- `inst.SoundEmitter:KillSound(name)` — stop a named looping sound.
- `inst.SoundEmitter:SetParameter(name, param, value)` — adjust a live FMOD parameter.
- Common in stategraphs and combat reactions.

## Action System

- `ACTIONS.X` — action enum entries; consumed by ActionHandler.
- `ActionHandler(ACTIONS.X, "statename")` — stategraph action binding; routes a player verb to a state.
- `BufferedAction(doer, target, action, invobject)` — runtime instantiation of an action.
- `inst.components.X:GetValidActions(target, right)` — component hook returning available actions.

## Skin System

- `inst.skinname` — string identifier for the active skin.
- `inst.AnimState:OverrideSymbol(...)` driven by skin data is the typical render path.
- `Prefabs[name].SkinFn` — function applied during prefab construction to apply a skin.

## Replica / Master

- Replica filename pattern: `<componentname>_replica.lua`.
- Replicas mirror master state via netvars (`net_*`) and expose read-only Get*/Has* accessors on the client.
- Master-only methods MUST guard with `if not TheWorld.ismastersim then return end`.
- See `replica_pattern` skill for full replica file documentation conventions.
