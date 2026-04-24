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
- Events & listeners may be omitted if the component has none.

## Properties Table

- Columns: Property | Type | Default Value | Description
- If no properties exist, the table MUST include a None data row:
  | None | | | No properties are defined. |
  Do NOT leave the table with header + separator only and no data rows — that is incorrect.
- Do NOT invent properties not in the constructor.

### Metafunction / Dynamic Properties

If a constructor uses `metafn()`, a loop over a global table (e.g., `TechTree.BONUS_TECH`,
`TUNING.BONUS_LIST`), or any pattern that programmatically generates `self[key] = value`
entries — document the full dynamic property set as a group row in the Properties table.
Format:
  | `<prefix>_bonus` (dynamic) | type | `default` | One row per `TechTree.BONUS_TECH` entry. Generated by `metafn()`: e.g. `science_bonus`, `magic_bonus`, `science_tempbonus`. |
Do NOT omit these properties even if none are listed explicitly in the source — the generation
loop IS the definition. Readers cannot understand downstream accessors (e.g., `self[string.lower(v).."_bonus"]`) without this.

### File-Scope Local Constants

Local constants defined at the top of a file that directly control function behavior MUST appear in the Properties table.
This applies to all file types (components, brains, data configs, stategraphs).

Detection: scan for `local NAME = <literal>` at file scope (outside any function body), where the constant is referenced inside a function to gate behavior (distance thresholds, count limits, time windows, multipliers).

Format in Properties table:
| `START_FACE_DIST` | constant (local) | `20` | Maximum distance at which the entity begins facing a player. |

Do NOT omit these — readers cannot understand function behavior limits without them.
Do NOT include constants that are only used internally and not referenced by documented functions.

### Late-Assigned and Hook Properties

- Properties assigned OUTSIDE the constructor (in event callbacks, OnLoad, or helper
  functions) must still appear in the Properties table.
- Callback hook properties (`self.onXxx`) set by external prefabs are part of the public API
  and must be listed even if always `nil` by default.

### Copy-Paste Artifacts

If a function body contains a comment referencing a clearly wrong entity or context
(e.g., "to determine the current beefalo state" in a beard component), add a **Code note**
inline in that function's description:
  > **Code note:** `OnLoad` contains the comment "to determing the current beefalo state" — apparent copy-paste from beefalo component; no functional impact.
This matters for maintainers debugging unexpected behavior.

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