---
name: content_rules
description: Content accuracy, completeness, file type classification, properties table rules
inject_into: [analyst, analyst_chunk, analyst_merge, analyst_intermediate, analyst_merge_legacy, reviewer_full, reviewer_typed]
---

# Content Rules

## Content Accuracy

- All content must come ONLY from the source code or provided JSON. Do NOT invent APIs.
- Never repeat the same line or bullet point more than once.
- No greetings, sign-offs, meta-commentary, or filler text.
- No emojis or unicode symbols.
- **No speculative language.** Do NOT write phrases like "may be legacy", "possibly unused", "might be for future use", "appears to be", or any other hedging about code purpose. If the usage is unclear from source, omit the note entirely rather than guess.

## Task Callback Functions

If a component starts a periodic or deferred task (via `DoPeriodicTask`, `DoTaskInTime`, or equivalent) and passes a named callback function, that callback MUST be documented as a Main function entry — even if it is declared as a local function inside the component.

Detection: look for patterns like:
- `inst:DoPeriodicTask(PERIOD, UpdateFoo)` — `UpdateFoo` must be documented
- `self.decaytask = inst:DoPeriodicTask(period, function(inst) self:UpdateDomestication() end)` — `UpdateDomestication` must be documented

These callbacks define the component's core periodic behavior. Omitting them means the decay/update logic is invisible to readers.

## Property Watcher Callbacks and Event Listener Locals

File-scope local functions registered as property watchers or event listeners in the constructor MUST appear as Main function entries if they perform non-trivial logic.

Detection: scan for these patterns at **file scope** (outside any Class body):
- `local function onXxx(self, value)` then referenced in constructor as `inst:WatchWorldState(...)` or registered via a property change system — document this function
- `local function OnSomething(inst)` then used in `inst:ListenForEvent("event", OnSomething)` inside the class body or `SetPreventUnequipping` — document this function

**What qualifies:**
- Any file-scope `local function` that syncs state to replica components (e.g., `onequipslot` calling `self.inst.replica.equippable:setequipslot(equipslot)`)
- Any `local function` that modifies entity state in response to a property change
- The callback registered in `SetPreventUnequipping`-style methods that hooks `onremove`

**What does NOT require documentation:**
- Trivial one-liner lambdas passed inline: `inst:ListenForEvent("x", function(inst) inst:Remove() end)` — too simple, already clear from the function that registers it
- File-scope functions that are only called from a single, already-documented function and do no additional side-effects beyond what that function describes

Describe the callback in its own `### OnXxx(...)` entry, mark it `(local)` in the heading, and note which event/property triggers it.

## File Type Classification

Determine before writing any section:

- **DATA CONFIG FILE**: no Class() constructor, no self.inst, returns a plain table/array.
  HOW TO DETECT: source file has NO `Class()` constructor, no `self.inst`, and returns
  a plain table/array at top level → DATA CONFIG FILE.
  → MUST apply ALL [Data config] rules. Use few_shot_data.

- **COMPONENT FILE**: has `Class(function(self, ...) ... end)` constructor and is in `components/` or attaches via `inst:AddComponent`.
  → MUST apply ALL [Component] rules. Use few_shot.

- **REPLICA FILE**: filename ends in `_replica.lua`, defines a Class with `net_*` netvar properties and `SetupRPCs`-style RPC registration.
  HOW TO DETECT: file in `components/` ends with `_replica.lua` AND constructor declares `self.X = net_bool(...)` or similar netvars.
  → Treat like a Component but document the master/replica relationship explicitly. See replica_pattern skill.

- **STATEGRAPH FILE**: calls `StateGraph(name, states, events, defaultstate, actionhandlers)`.
  HOW TO DETECT: file contains `StateGraph(` at top level and defines `State{...}` entries.
  → MUST apply STATEGRAPH rules (see dst_conventions). Use few_shot_stategraph.

- **BRAIN FILE**: defines a Brain class or returns a BehaviourTree via `Brain:new()` / `Class(Brain, ...)`.
  HOW TO DETECT: file in `brains/` extends `Brain` or imports `behaviourtree`.
  → Treat like a Component but with no constructor Properties; document local helper functions
  and file-scope constants. Use few_shot_brain.

- **BEHAVIOUR FILE**: file in `behaviours/` defines a single behavior node by extending `BehaviourNode`.
  HOW TO DETECT: file in `behaviours/` declares `MyBehaviour = Class(BehaviourNode, ...)`.
  → Document `Visit()`, `Reset()`, `DBString()` as Main functions. Usage example shows the node
  embedded in a SelectorNode/SequenceNode tree, not standalone. Use few_shot_behaviour.

- **WIDGET FILE**: file in `widgets/` extends `Widget` via `Class(Widget, ...)`.
  HOW TO DETECT: file imports `Widget` from `widgets/widget` and constructor calls `Widget._ctor(self, ...)`.
  → Document `_ctor`, `AddChild`-built children, event handlers (`OnGainFocus`, `OnLoseFocus`,
  `OnControl`). Usage example shows `screen:AddChild(MyWidget(...))`. Use few_shot_widget.

- **SCREEN FILE**: file in `screens/` extends `Screen` via `Class(Screen, ...)`.
  HOW TO DETECT: file imports `Screen` and is in `screens/` (or root-level screen file).
  → Document `_ctor`, `OnControl`, `OnUpdate`, navigation methods. Usage example shows
  `TheFrontEnd:PushScreen(MyScreen(...))`. Use few_shot_screen.

- **PREFAB FILE**: file in `prefabs/` calls `return Prefab(name, fn, assets, deps)` (or `MakePlayerCharacter`).
  HOW TO DETECT: top-level `return Prefab(...)` or wrapper macro returning a Prefab table.
  → Document `fn()` (the constructor entry point), `master_postinit`, the assets table,
  and the prefab table itself. Usage example: `SpawnPrefab("name")`. Use few_shot_prefab.

  **PLAYER CHARACTER PREFAB**: file calls `return MakePlayerCharacter(name, prefabs, assets, common_postinit, master_postinit)`.
  HOW TO DETECT: `require("prefabs/player_common")` at top + `MakePlayerCharacter(...)` as the return value.
  → Document `common_postinit(inst)` and `master_postinit(inst)` as the primary functions (NOT `fn()`).
  → Overview MUST state that the base player skeleton comes from `player_common.lua`, not this file.
  → See `dst_conventions` MakePlayerCharacter section for full rules.

When signals are mixed (e.g., a brain file that also defines a local Widget), classify by the
file's primary export — what does the top-level `return` produce?

When in doubt, prefer the more specific classification (REPLICA over COMPONENT, BEHAVIOUR over
BRAIN) since their few-shots/rules are stricter subsets.

## Completeness

- Keep ALL functions — never drop trivial getters/setters.
- If a function appears in multiple chunks, prefer the entry with more parameter/return detail.
- Merge all events, dependencies, and tags; never drop an entry.
- If a field has no data, use "None" (string) or [] (empty array) — never omit the field.

## Short Files

- If source is small or simple, keep docs proportionally short.
- If a section has no content, write "Not applicable" or "None identified" — do not invent.
- If a file has no events, listeners, or watchers, write `**None.**` in the Events & listeners section — NEVER omit the `## Events & listeners` heading.

## Properties Table

- Columns: Property | Type | Default Value | Description
- If no properties exist, the table MUST include a None data row:
  | None | | | No properties are defined. |
  Do NOT leave the table with header + separator only and no data rows — that is incorrect.
  Exception: stategraph files may use a state reference table instead of a None row when there
  are no file-scope constants/properties to list.
- Do NOT invent properties not in the constructor.

### Metafunction / Dynamic Properties

If a constructor uses `metafn()`, a loop over a global table (e.g., `TechTree.BONUS_TECH`,
`TUNING.BONUS_LIST`), or any pattern that programmatically generates `self[key] = value`
entries — document the full dynamic property set as a single group row in the Properties table.
Format:
  | `<prefix>_bonus` (dynamic group) | type | `default` | Generated by `metafn()` / loop over `TechTree.BONUS_TECH`; representative keys include `science_bonus`, `magic_bonus`, `science_tempbonus`. |
Do NOT omit these properties even if none are listed explicitly in the source — the generation
loop IS the definition. Readers cannot understand downstream accessors (e.g., `self[string.lower(v).."_bonus"]`) without this.

### File-Scope Local Constants

Local constants defined at the top of a file that directly control function behavior MUST appear in the Properties table.
This applies to all file types (components, brains, data configs, stategraphs).

Detection: scan for `local NAME = <literal>` at file scope (outside any function body), where the constant is referenced inside a function to gate behavior (distance thresholds, count limits, time windows, multipliers, scheduler periods).

This explicitly includes:
- Scheduler period constants (e.g., `local DECAY_TASK_PERIOD = 60`) — even if the period value is passed to `DoPeriodicTask` and not visible in individual function signatures, readers cannot understand update frequency without it.

Format in Properties table:
| `START_FACE_DIST` | constant (local) | `20` | Maximum distance at which the entity begins facing a player. |
| `DECAY_TASK_PERIOD` | constant (local) | `60` | Interval in seconds between periodic decay ticks. |

Do NOT omit these — readers cannot understand function behavior limits without them.
Do NOT include constants that are only used internally and not referenced by documented functions.

### Late-Assigned and Hook Properties

- Properties assigned OUTSIDE the constructor (in event callbacks, OnLoad, or helper
  functions) must still appear in the Properties table.
- Callback hook properties (`self.onXxx`) set by external prefabs are part of the public API
  and must be listed even if always `nil` by default.

### Component Callback Hooks — Public API Surface

Many components define hook properties as `self.onXxx = nil` in the constructor, explicitly expecting external code (prefab files) to assign them. These are the component's **callback API** — not internal implementation details.

Detection: scan the constructor for `self.onXxx = nil` or `self.onXxx = false` patterns where `onXxx` is later checked as `if self.onXxx ~= nil then self.onXxx(self.inst, ...) end` inside the component's own methods.

Common examples: `self.onturnon`, `self.onturnoff`, `self.onactivate`, `self.onrepaired`, `self.oncalculatehitfn`, `self.onattackotherfn`.

**Documentation rule:** Document every hook property in the Properties table with:
1. Its type: `function` (or `function | nil`)
2. Default: `nil`
3. Description explaining the callback signature and when it fires:

| `onturnon` | function | `nil` | Called when prototype is turned on. Signature: `fn(inst)`. Set by owning prefab. |
| `oncalculatehitfn` | function | `nil` | Override damage calculation. Signature: `fn(inst, target, damage) → number`. |

Do NOT omit hook properties simply because they are `nil` by default — they define the component's integration surface with prefab code.

### Copy-Paste Artifacts

If a function body contains a comment referencing a clearly wrong entity or context
(e.g., "to determine the current beefalo state" in a beard component), add a **Code note**
inline in that function's description:
  > **Code note:** `OnLoad` contains the comment "to determing the current beefalo state" — apparent copy-paste from beefalo component; no functional impact.
This matters for maintainers debugging unexpected behavior.

## Multiple Prefab Returns

A prefab file may return multiple `Prefab()` values in a comma-separated list, or use factory functions that return additional prefabs:

```lua
-- All of these register separate, independently spawnable prefabs:
return Prefab("abigail", fn, assets, prefabs),
       Prefab("abigail_retaliation", retaliationattack_fn, {}),
       CreateDebuff("abigail_vex_debuff"),
       CreateDebuff("abigail_vex_shadow_debuff")
```

**Documentation rule:** When a file returns multiple prefabs, the document MUST cover ALL of them. Either:
1. Document each prefab as its own `### fn() (prefabname)` subsection in Main functions, OR
2. Note in Overview that the file registers N prefabs and name them all

Do NOT document only the first/primary prefab and silently omit the others. The Overview must list all registered prefab names even if some share the same constructor logic (factory functions).

Detection: scan the last `return` statement of the file for comma-separated `Prefab(...)` calls or calls to factory functions that return `Prefab(...)`.

## Prefab Helper Macro Functions

In prefab files, standalone helper functions called inside `fn()` or `master_postinit()` (e.g., `MakeInventoryPhysics`, `MakeSmallBurnable`, `MakeDeployableFertilizer`, `MakeHauntableLaunchAndPerish`) are NOT components. Do NOT list them under **Components used:**.

These functions are called to apply a bundle of setup logic and are external to the prefab file. List them under **External dependencies:** with their purpose:
```
**External dependencies:**
- `MakeInventoryPhysics` -- applies physics and floatable behavior for inventory items
- `MakeSmallBurnable` -- registers burnable/smoldering behavior for small entities
```

A function belongs under **Components used:** ONLY if it is accessed via `inst.components.X` or `inst:AddComponent("X")`.

## Data Config File Properties

MUST document TWO groups of rows in this order:
  1. The top-level container variable (the returned global/local table).
  2. One row per key in each record entry (e.g., name, id.steam, id.psn).
NEVER document only the container and omit the record schema.
NEVER use a real default value for record fields — always write "---" (em dash).
NEVER write "nil" as a default — that is a real default value. Use "---" only.
Nested table fields accessed via dot notation (id.steam, id.psn) MUST each be
their own property row. Never collapse them into a single parent row (e.g., id).

## Data Config File Main Functions

Local factory/builder functions that construct record entries (e.g., ACHIEVEMENT(),
ENTRY()) MUST be documented in ## Main functions — they define the record schema
and are part of the data API. Do NOT treat them as internal implementation details
or skip them because they are local.

## Incomplete Function Handling

At chunk boundary: if a function body is cut off, keep it and note "INCOMPLETE — continues in adjacent chunk".
Do NOT skip or drop incomplete functions.