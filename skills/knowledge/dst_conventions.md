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

### Class Constructor Third Parameter — Property Dirty Callbacks

`Class(constructor_fn, nil, {propname = callback_fn, ...})` — the optional third parameter is a **property watch table**. When any listed property is assigned on the component instance, the mapped callback fires automatically.

```lua
local Channelable = Class(
    function(self, inst) ... end,
    nil,  -- base class (unused here)
    {
        enabled = onsetenabled,      -- fires onsetenabled(self, value) when self.enabled is assigned
        channeler = onsetchanneler,  -- fires onsetchanneler(self, value) when self.channeler is assigned
    }
)
```

**Documentation rule:** When the third parameter is present, document each property in the Properties table with a note that assignment triggers a watcher:
| `enabled` | boolean | `true` | Controls activation state. Assignment fires `onsetenabled` to sync replica. |

The watcher callback functions themselves (e.g., `onsetenabled`) are file-scope locals. Document them using the "Property Watcher Callbacks" rule from `content_rules`.

## Event System

- `inst:ListenForEvent(event, fn)` — subscribe to event on entity.
- `inst:PushEvent(event, data)` — fire event on entity; data is an optional table.
- `inst:RemoveEventCallback(event, fn)` — unsubscribe a specific listener.
- World-level events: `TheWorld:ListenForEvent` / `TheWorld:PushEvent`.

## WorldState Watchers

`inst:WatchWorldState("varname", fn)` — subscribe to a TheWorld.state variable change. **This is NOT the same as ListenForEvent.**

- Watches TheWorld.state keys: `"season"`, `"israining"`, `"isday"`, `"precipitationrate"`, etc.
- Fires `fn(inst, newvalue)` whenever the watched state variable changes value.
- The callback receives the **new value** as the second argument (unlike event data tables).
- Watchers are stored separately from events — `RemoveEventCallback` does NOT remove them.
- Cleanup: call `inst:StopWatchingWorldState("varname", fn)` in `OnRemoveFromEntity`.

**Documentation rule:** In Events & Listeners, worldstate watchers go under a distinct label:
```
**World state watchers:**
- `israining` — triggers OnIsRaining; enables/disables the frog spawn update task
- `season` — triggers OnSeasonChanged; recalculates spawning parameters
```
Do NOT list worldstate watchers under **Listens to:** — that label is for `ListenForEvent` only.

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

### NetVar Dirty Callback Pattern (in non-replica components)

When a component declares netvars directly (not in a `*_replica.lua` file), the dirty event pattern is:

```lua
-- Constructor: declare netvars + dirty event name (3rd param)
self.enabled = net_bool(inst.GUID, "aoecharging.enabled", "enableddirty")
self.ischarging = net_bool(inst.GUID, "aoecharging.ischarging", "ischargingdirty")

-- Client-only: register listeners for dirty events
if not TheWorld.ismastersim then
    inst:ListenForEvent("enableddirty", OnEnabledDirty)
    inst:ListenForEvent("ischargingdirty", OnIsCharging)
end
```

Key rules:
- The **3rd parameter** to `net_*()` is the dirty event name — it fires when the value changes.
- Use `:set(value)` on master to update + fire the dirty event.
- Use `:value()` on both sides to read the current value.
- `net_event` is different — no value storage, fires via `:push()`, no `:value()`.
- Dirty listeners are registered **on the client only** (`if not TheWorld.ismastersim`).

**Documentation rule:** NetVar properties belong in the Properties table with their dirty event name:
| `enabled` | net_bool | `true` | Dirty event: `enableddirty`. Synced to clients; controls AOE charging activation. |

Multiple netvars may share the **same dirty event name** (e.g., `"seasondirty"`) — one event fires for multiple variable changes. Document this shared trigger in each property's description.

### Master/Client Constructor Split

Components with netvars often split initialization:

```lua
local MyComponent = Class(function(self, inst)
    self.ismastersim = TheWorld.ismastersim   -- cache once; cheaper than repeated global access
    
    self.value = net_int(inst.GUID, "mycomp.value", "valuedirty")
    
    if self.ismastersim then
        self._tracker = {}                    -- server-only state
        self.inittask = inst:DoStaticTaskInTime(0, OnInit, self)
    else
        inst:ListenForEvent("valuedirty", OnValueDirty)  -- client-only
    end
end)
```

**Documentation rule:** When a constructor has `if self.ismastersim then ... else ... end` blocks:
1. Document server-only properties (inside `if ismastersim`) with `(master only)` note in Description.
2. Document client-only listeners in Events & Listeners under **Listens to:** with `(client only)` note.
3. The `ismastersim` property itself should appear in Properties — it gates all server-side behavior.

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
The Properties section MUST begin with a state reference table (see `writing_guide` stategraph rules).

**Main functions — State Handlers:** Document state handler functions grouped by state name.
Use the format: `### onenter (statename)` / `### onexit (statename)` / `### ontimeout (statename)`.
- Only document states with non-trivial logic (more than a simple animation play or tag add/remove).
- Skip states whose onenter/onexit is a one-liner (e.g., `inst.sg:SetTimeout(1)`).
- If a file has 100+ states, document representative groups: death states, transformation states,
  combat states, and any state with error-prone logic. Note omissions explicitly.
- Do NOT document `TimeEvent` callbacks as separate functions — describe them in the parent state's entry.

**Timeline events — `TimeEvent` vs `FrameEvent` vs `SoundFrameEvent`:**
- `TimeEvent(n * FRAMES, fn)` — fires `fn` at frame `n` of the current animation. Uses the `FRAMES` constant.
- `FrameEvent(n, fn)` — identical behavior but takes a raw integer frame number (no `* FRAMES`).
- `SoundFrameEvent(n, sound_path)` — shorthand that plays a sound at frame `n`; no callback function.
When documenting a state's `onenter`, mention significant timeline events inline: "At frame 14, spawns impact FX and enables hitboxes."

**State memory — `inst.sg.mem` vs `inst.sg.statemem`:**
- `inst.sg.statemem` — state-local table, **cleared on every state exit**. Use for within-state tracking.
- `inst.sg.mem` — stategraph-level table, **persists across state transitions**. Use for multi-state tracking.
When documenting `onenter` or `onexit`, always specify which memory scope is being written to:
  - ✅ "Stores attack start time in `inst.sg.statemem.starttime` (cleared on exit)."
  - ✅ "Increments `inst.sg.mem.attack_count` (persists until stategraph is reset)."

**Dynamic state tag modification:** Tags declared in `State{tags = {...}}` can be changed mid-state via `inst.sg:AddStateTag("tag")` / `inst.sg:RemoveStateTag("tag")`. When a timeline event removes a tag (e.g., removing "busy" at frame 20 to allow interruption), document it in the state's description: "Busy flag removed at frame 20 via RemoveStateTag."

**Events:** Document `EventHandler` entries that react to engine events (not state-internal handlers).
These are stategraph-level event listeners, not component event listeners.

## Brains (AI)

- `Brain:new(inst)` creates a behavior tree for AI entities.
- Nodes: `SequenceNode`, `SelectorNode`, `ConditionNode`, `WaitNode`, `DoAction`.
- `RunBrain(inst, brain)` attaches and starts a brain.
- Brains are paused automatically when the entity is far from players.

## SourceModifierList

`SourceModifierList(inst, base, combinefn, ondirty)` — DST's modifier stacking system. Manages multiple named modifiers from different sources that combine into a single value.

```lua
local SourceModifierList = require("util/sourcemodifierlist")

self._mults = SourceModifierList(inst, 1, nil, OnDirty)  -- base=1 (multiplicative identity)

-- Add modifier from a specific source (source is the key):
self._mults:SetModifier(source_entity, multiplier_value, "source_key")

-- Remove modifier from a source:
self._mults:RemoveModifier(source_entity, "source_key")

-- Read the combined result (all modifiers multiplied/added together):
local combined = self._mults:Get()
```

**Documentation rule:** When a component uses `SourceModifierList`, document in Properties:
| `_mults` | SourceModifierList | base `1` | Tracks per-source speed multipliers; combined via multiplication. Call `Get()` for effective value. |

Document the `SetModifier` / `RemoveModifier` / `Get` functions as Main functions when exposed in the component's public API. The `ondirty` callback fires whenever the combined value changes — document it as a Property Watcher Callback (see `content_rules`).

## Prefab System

- `Prefabs["name"] = Prefab(name, fn, assets, deps)` registers a spawnable entity.
- Inside the prefab function: `CreateEntity()` -> attach components -> return inst.
- `SpawnPrefab("name")` — instantiates a prefab at runtime.
- `MakePlanarPhysics`, `MakeInventoryPhysics` — common physics helpers.

### MakePlayerCharacter Macro

Player character prefabs (Wilson, Wendy, WX-78, etc.) use `MakePlayerCharacter` instead of raw `Prefab()`:

```lua
local MakePlayerCharacter = require("prefabs/player_common")

local function common_postinit(inst)   -- runs on BOTH client and master
    inst:AddTag("scientist")
end

local function master_postinit(inst)   -- runs on master only
    inst.starting_inventory = start_inv.default
    inst:AddComponent("beard")
end

return MakePlayerCharacter("wilson", prefabs, assets, common_postinit, master_postinit)
```

**HOW TO DETECT:** File contains `require("prefabs/player_common")` and the return is `MakePlayerCharacter(...)`.

**Documentation rules:**
- The primary functions are `common_postinit(inst)` and `master_postinit(inst)` — document both.
- `common_postinit` = client + master; `master_postinit` = server only. Mark clearly.
- Do NOT write `fn()` in the Main functions heading — use the actual function names.
- Overview: "Uses `MakePlayerCharacter` wrapper — the base player skeleton (physics, health, hunger, sanity) is provided by `player_common.lua`, not defined here."
- Properties section lists tags added in `common_postinit` and key TUNING constants from `master_postinit`.

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
