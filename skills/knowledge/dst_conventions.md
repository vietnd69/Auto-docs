---
name: dst_conventions
description: DST engine conventions — ECS, events, tags, network replication, stategraphs, brains, prefabs, scheduler
inject_into: [analyst, analyst_chunk, analyst_merge, analyst_intermediate, analyst_merge_legacy, reviewer_full, reviewer_typed]
---

ENTITY COMPONENT SYSTEM (ECS):
- Components attach to entities: `inst:AddComponent("name")` / access via `inst.components.name`.
- `self.inst` — the entity instance that owns this component.
- Constructor: `Class(function(self, ...) ... end)` — NOT `_ctor`. First param after `self` varies
  (commonly `inst` for components, `data` for utility classes).
- Every component is a Lua table; methods are functions stored in that table.

EVENT SYSTEM:
- `inst:ListenForEvent(event, fn)` — subscribe to event on entity.
- `inst:PushEvent(event, data)` — fire event on entity; data is an optional table.
- `inst:RemoveEventCallback(event, fn)` — unsubscribe a specific listener.
- World-level events: `TheWorld:ListenForEvent` / `TheWorld:PushEvent`.

TAG SYSTEM:
- `inst:AddTag("tag")` / `inst:RemoveTag("tag")` / `inst:HasTag("tag")`.
- Tags affect targeting (`FindEntities`, `FindClosestEntityWithTag`) and combat exclusions.
- Common tags: "player", "monster", "structure", "fire", "invisible", "notarget".

NETWORK REPLICATION:
- `self.inst.replica.X` — client-side replica of component X (read-only on client).
- NetVars: `net_bool`, `net_int`, `net_float`, `net_string`, `net_entity` synchronize state.
- `TheWorld.ismastersim` — true only on the server; guards server-only logic.
- `TheNet:GetIsClient()` / `TheNet:GetIsServer()` — runtime environment checks.
- `SendRPCToServer(RPC.Name, ...)` / `SendRPCToClient(client, RPC.Name, ...)` — RPCs.

GLOBAL REFERENCES:
- `TheWorld` — world entity; holds components like `map`, `weather`, `season`.
- `TheNet` — networking and lobby interface.
- `ThePlayer` — local player entity (client); may be nil on server before join.
- `AllPlayers` — list of all connected player entities (server).
- `TheSim` — simulation: `GetTick()`, `GetGameID()`, file I/O, scheduling.
- `TheInput` — keyboard/mouse input handling.
- `TUNING` — global balance constants table (damage, durations, quantities).
- `STRINGS` — localization string table.
- `ACTIONS` / `BufferedAction` — action system for player verb interactions.

STATEGRAPHS:
- `StateGraph(name, states, events, defaultstate, actionhandlers)` defines animation state machines.
- `State{name, onenter, onexit, ontimeout, events, timeline}` — individual state.
- `EventHandler(event, fn)` — handles events inside a stategraph.
- `TimeEvent(time, fn)` — fires function at specific animation frame.

BRAINS (AI):
- `Brain:new(inst)` creates a behavior tree for AI entities.
- Nodes: `SequenceNode`, `SelectorNode`, `ConditionNode`, `WaitNode`, `DoAction`.
- `RunBrain(inst, brain)` attaches and starts a brain.
- Brains are paused automatically when the entity is far from players.

PREFAB SYSTEM:
- `Prefabs["name"] = Prefab(name, fn, assets, deps)` registers a spawnable entity.
- Inside the prefab function: `CreateEntity()` -> attach components -> return inst.
- `SpawnPrefab("name")` — instantiates a prefab at runtime.
- `MakePlanarPhysics`, `MakeInventoryPhysics` — common physics helpers.

SCHEDULER / COROUTINES:
- `inst:DoTaskInTime(delay, fn)` — one-shot delayed task.
- `inst:DoPeriodicTask(period, fn, initial_delay)` — repeating task.
- `inst:StartThread(fn)` — coroutine attached to entity lifecycle.
- `Sleep(seconds)` inside a coroutine yields execution (non-blocking).
- `inst:ClearScheduledTask(task)` — cancel a pending task.
