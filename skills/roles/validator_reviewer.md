---
name: validator_reviewer
description: Content accuracy review checklist, section requirements, special case logic for documentation validation
inject_into: [reviewer_full, reviewer_typed]
---

## Checklist

Check CONTENT ACCURACY ONLY:
1. Function signatures and params match Lua source exactly — no hallucinated names/types
2. Descriptions are accurate (not vague/wrong about what the function actually does)
3. Usage example uses real function names and correct call patterns
4. All required sections are present — flag as a finding if any required section is missing entirely
5. Section contains required content (see requirements below)
6. No invented properties, events, or dependencies not present in Lua source
7. Dynamic/metafunction-generated property groups are documented in Properties if source
   uses `metafn()` or a loop that writes `self[key] = value` programmatically
8. Multi-branch functions document ALL major code paths, not just the happy path
9. Error states `None` is verified — `None` is only valid when every component access
   in the function body has a nil guard immediately before it

MISSING SECTION RULE: If a required section (## Overview, ## Usage example, ## Dependencies & tags,
## Properties, ## Main functions) is completely absent from the document, flag it as a finding:
{"issue": "Required section '## X' is missing entirely.", "suggestion": "Add the missing section following the standard format."}

Do NOT flag formatting, bullet style, or structural notation issues — only flag content errors (wrong/missing/hallucinated information).

STRUCTURAL GUARD: Do NOT rename or remove ### headings in your review suggestions unless the function is hallucinated (not in the Lua source).

## Section: Overview

[Component] 2-5 sentences: what this component does + its role in ECS.
Mention key relationships with other components.
[Data config] 2-5 sentences: what static data this file defines, how it is structured,
and how other systems access it via require(). Do NOT reference ECS or AddComponent.

## Section: Usage example

5-15 lines of realistic Lua using actual function names from this file.
[Component] Show CreateEntity(), AddComponent(), then call 2-3 primary functions.
[Data config] Show require() followed by table index access (e.g. Table[1]).
No CreateEntity(), AddComponent(), or inst.components.

REQUIRE PATH RULE: The require() path must match the actual source FILE NAME, not the class name.
Example: if the file is `brains/crittersbrain.lua` and the class is `CritterBrain`,
the correct path is require("brains/crittersbrain") — NOT require("brains/critterbrain").
Do NOT flag a require path as wrong solely because it differs from the class name.

## Section: Dependencies & tags

Must contain EXACTLY these labels (in order):
**External dependencies:** — list each `name` -- usage. Omit this label entirely if there are no external dependencies.
**Components used:** — list each `component_name` -- methods/properties accessed. Write `None identified` if none.
**Tags:** — list each `tag_name` -- add/remove/check. Write `None` if no game tags.

NOTE: "EXACTLY these labels" means the two mandatory labels (**Components used:** and **Tags:**) must
always be present. **External dependencies:** is the only label that may be omitted when empty.

UNUSED IMPORT RULE: If `local X = require("X")` appears in the file but the returned value is
never called or indexed in any function body, it is an **unused import**.
- Prefer listing it under **External dependencies:** with usage description `"imported but not referenced (unused import)"`.
- Do NOT flag the documentation as wrong for listing an unused import — the listing is correct.
- Do NOT flag the documentation as wrong for NOT listing an unused import — omission is also acceptable.
- The ONLY valid finding: if the listed usage description is factually inaccurate (e.g., says the
  module is actively used when it is never called in the file).
- NEVER oscillate between "it must be listed" and "it must be removed" for the same unused import across iterations.

## Section: Properties

Table with columns: Property | Type | Default Value | Description.
If no properties exist, the table MUST include a None data row:
| None | | | No properties are defined. |
Do NOT leave the table with header + separator only and no data rows — that is incorrect.
Do NOT invent properties not in the constructor.
Data config files: document the top-level container + each record field.

NETVAR CHECK: Scan the constructor for `net_bool(...)`, `net_int(...)`, `net_float(...)`, `net_string(...)`, `net_event(...)` declarations. If found in a non-replica component file:
1. Each netvar must appear in the Properties table with its dirty event name.
2. If the constructor has `if self.ismastersim then ... else ... end`, the `ismastersim` property must be documented.
3. `net_event` has no `:value()` — if the doc describes reading a `net_event` with `:value()`, flag it.
{"issue": "net_bool 'enabled' declared on line N has dirty event 'enableddirty' but the Properties table omits the dirty event name.", "suggestion": "Add dirty event name to the property description: 'Dirty event: enableddirty'."}

CALLBACK HOOK CHECK: Scan the constructor for `self.onXxx = nil` or `self.onXxx = false` where `onXxx` is later invoked inside the component with `if self.onXxx ~= nil then self.onXxx(...) end`. If such hooks exist but are absent from the Properties table, flag each one:
{"issue": "Component defines callback hook self.onturnon = nil (line N) but it is not documented in the Properties table.", "suggestion": "Add self.onturnon to Properties with type 'function', default 'nil', and description of when it fires and its signature."}

DYNAMIC PROPERTY CHECK: Scan the Lua constructor for any of these patterns:
- `metafn()` call that generates `self[key]` entries
- `for i, v in ipairs(SomeGlobalTable) do self[...] = ... end` (property-generating loop)
If found, verify the Properties table contains a group row documenting the generated
property set (e.g., `science_bonus`, `magic_bonus` generated from `TechTree.BONUS_TECH`).
If the group row is absent, flag it:
{"issue": "Dynamic properties generated by metafn()/loop over TechTree.BONUS_TECH are not documented in the Properties table. Readers cannot understand downstream accessors like self[string.lower(v)..'_bonus'] without this.", "suggestion": "Add a group row describing the generated property set and naming representative examples."}

## Section: Main functions

Each entry uses a ### heading with function name.
Keep ALL functions — never drop trivial getters/setters.

FIELD RULES:
- **Error states:** must describe only real failure paths (crash, nil access without guard,
  or silent corruption risk). Do NOT suggest renaming it to Notes, Behavior, or any other name.
- If content inside **Error states:** is non-error behavior (e.g. pure conditional logic with
  no failure path), suggest moving that content into **Description:** instead.
- `* **Error states:** None` is a valid, correct value — do NOT flag it unless verification fails.
- Do NOT introduce new field names. Only use: Description, Parameters, Returns, Error states.

ERROR STATES BOUNDARY TEST (apply before flagging anything in this field):
  Ask: "Would calling this function with this input CRASH or SILENTLY CORRUPT state,
  given no guard exists in the Lua source?" If YES → valid Error states entry.
  If NO (it returns a defined value, falls back, or is an optional param) → belongs in
  Description or Returns, NOT Error states.

ERROR STATES — VERIFICATION PROTOCOL (required before accepting `None`):
  Scan every line of the function body in the Lua source for:
  - `self.inst.components.X:Method()` with NO `if X ~= nil` guard immediately before → crash path
  - `inst.components.X` on a parameter entity with no nil guard → crash path
  - Chained access `a.b.c` where `a.b` could be nil → crash path
  If ANY unguarded access exists and the doc writes `Error states: None`, flag it:
  {"issue": "Error states: None is incorrect. self.inst.components.X:Method() on line N has no nil guard — crashes if X is missing.", "suggestion": "Document the crash condition: 'Errors if inst.components.X is nil (no nil guard present).'"}
  Symmetric rule: if the doc claims an error state but the Lua source has a clear nil guard
  immediately before the access, flag the false error state and suggest removing it.

INLINE NIL GUARD PATTERNS — all of these are valid guards; do NOT flag the wrapped call as "unguarded":
- `if X ~= nil then X:Method() end` — explicit if-block guard
- `X ~= nil and X:Method()` — short-circuit AND expression (guard and call on same line)
- `X and X:Method()` — truthy short-circuit guard
- `if X then X:Method() end` — truthy if-block guard
- `local y = X ~= nil and X:Method()` — guarded assignment
If ANY of these patterns wraps a method call, the call is guarded — do NOT report it as an unguarded access.
This applies even when the guard and the method call appear on the SAME line.

ERROR STATES — WHAT DOES NOT BELONG THERE (move to Description):
  BAD: "Returns false if entity is on specific island" — normal conditional return path
  BAD: "If inst is nil, falls back to default behavior" — optional parameter handling
  BAD: "Behavior changes if SPECIAL_EVENTS.X is active" — conditional logic branch
  BAD: "Returns standard result if entity lacks tag Y" — else branch of an if statement
  BAD: "Returns nil if no entity found" — expected empty-result return path
  GOOD: "Errors if inst is nil (no nil guard before member access)" — actual crash path
  GOOD: "Returns nil if required component missing (inventory, luckuser)" — missing dependency

MULTI-PATH FUNCTION CHECK: For any function whose body contains conditional branches that
produce meaningfully different outcomes (e.g., `if recipe.manufactured then ... return end`,
`if recipe.dropitem then ...`), check that the Description documents each major branch.
A single generic sentence that omits alternate execution paths is a WRONG_DESCRIPTION finding.
Flag each missed branch separately:
{"issue": "DoBuild() description omits the recipe.manufactured branch: when true, the prototyper spawns the prefab and this function only removes ingredients then returns early.", "suggestion": "Add a branch note in Description for the recipe.manufactured path."}

## Section: Events & listeners

- **Listens to:** events registered via inst:ListenForEvent(event, fn)
- **Pushes:** events fired via inst:PushEvent(event, data)
- **World state watchers:** variables watched via inst:WatchWorldState("varname", fn) — separate label from Listens to
If the component has no events, listeners, or watchers, the section content MUST be exactly `**None.**` — NEVER suggest removing the `## Events & listeners` heading. Suggest replacing the section body with `**None.**` instead.

WORLDSTATE WATCHER CHECK: Scan the source for `inst:WatchWorldState(...)` calls. If found and absent from the doc, flag it:
{"issue": "Component calls inst:WatchWorldState('israining', OnIsRaining) but the Events & listeners section has no World state watchers label.", "suggestion": "Add a **World state watchers:** subsection listing the watched variable and what the callback does."}

**Event data structure check:** For every event entry, verify that the data payload is documented. Check the `inst:PushEvent(event, data)` call in source to determine what fields `data` contains. If the doc says `Data: {owner = entity}` but source passes `{owner = owner, from_ground = from_ground}`, flag the missing field. If the source passes a simple value (not a table), note that too: `Data: isacidsizzling (boolean direct param)` — not all event callbacks receive a `data` table.

Flag inconsistent event patterns:
{"issue": "Event 'acidsizzlingchange' listener receives a direct boolean parameter, not a data table. Doc should note: 'Data: direct boolean param (isacidsizzling)' instead of implying a table.", "suggestion": "Update event data format to match actual callback signature in source."}

## Typed Checks per File Type

Apply these AFTER the generic checklist. The file type is determined by the rules in
`content_rules` (DATA CONFIG / COMPONENT / REPLICA / STATEGRAPH / BRAIN / BEHAVIOUR / WIDGET /
SCREEN / PREFAB).

### Stategraph file checks
- Main functions headings follow `### \`onenter (statename)\`` / `### \`ontimeout (statename)\`` /
  `### \`onexit (statename)\``. Flag if a state's onenter contains non-trivial logic but no entry exists.
- Properties section lists ONLY file-scope locals (e.g., `ATTACK_PROP_MUST_TAGS`). State-local
  variables MUST NOT appear.
- **STATE LIST TABLE required:** Properties section MUST begin with a state reference table listing every state defined in the `StateGraph(...)` call plus any states injected by `CommonStates.AddXxxStates(...)`. If this table is absent, flag it:
  {"issue": "Properties section is missing the state reference table. The stategraph defines N states but there is no consolidated table listing them with their tags and roles.", "suggestion": "Add a state reference table at the top of ## Properties before any constant rows, with columns: State name | Tags | Description."}
- Events & listeners lists EventHandler entries that react to ENGINE events, not state-internal handlers.
- Usage example uses `inst.sg:GoToState(...)` / `inst.sg:HasStateTag(...)`, NOT `CreateEntity()` + `AddComponent()`.

STATEGRAPH CONTEXT GUARANTEES — do NOT flag these as potential nil error states in state handler functions (onenter/onexit/ontimeout/timeline callbacks):
- `inst.sg`, `inst.sg.statemem`, `inst.sg.mem` — initialized by the stategraph engine before any handler runs; always non-nil when a state handler executes.
- `inst.AnimState`, `inst.Physics`, `inst.SoundEmitter`, `inst.Transform` — DST entity built-ins set up at entity creation, not via AddComponent. Never nil for a living entity with these built-ins active.
- Entity built-ins are NOT components — do not apply component nil-guard checks to them. The component pattern `inst.components.X` requires a nil guard; entity built-ins (`inst.AnimState`, etc.) do not.

**OSCILLATION GUARD — Stategraph built-in error states:** Do NOT oscillate between iterations on whether `inst.AnimState`, `inst.sg`, `inst.Physics`, `inst.SoundEmitter`, or `inst.Transform` require nil-guard error state documentation. Per STATEGRAPH CONTEXT GUARANTEES above, these are always non-nil in state handlers — once this was accepted or corrected in any prior iteration, do NOT re-raise it. `inst.components.X` still requires nil-guard checks; only entity built-ins are exempt.

STATEGRAPH EVENTS RULE: For `## Events & listeners`, enumerate ALL `EventHandler("event_name", fn)` entries in the `events = {...}` table of the `StateGraph(...)` call. Each event name MUST appear in the doc. The section for a stategraph lists EventHandler entries (engine events the stategraph reacts to) — NOT `ListenForEvent` calls.
If the doc says 'Listens to: None' but source has N EventHandlers, flag each missing event:
{"issue": "EventHandler 'death' is defined in source events table but absent from ## Events & listeners.", "suggestion": "Add 'death' under EventHandlers in the Events & listeners section."}

INJECTED STATES RULE: Calls like `CommonStates.AddSinkAndWashAshoreStates(states, ...)`, `CommonStates.AddVoidFallStates(states, ...)`, `SGWX78Common.AddWX78SpinStates(states)` inject additional states not defined inline in the StateGraph call. The state reference table in `## Properties` MUST include these injected states. Common injection mappings:
- `AddSinkAndWashAshoreStates` → sink, washashore
- `AddVoidFallStates`          → abyss_fall, voiddrop
- `AddRowStates`               → rowing states (hop variants)
- `AddHopStates`               → hop_pre, hop_loop, hop_pst
- `AddWX78SpinStates`          → wx_spin_start, wx_spin
- `AddWX78ShieldStates`        → wx_shield_pre, wx_shield_pst
- `AddWX78ScreechStates`       → wx_screech_pre, wx_screech_pst
- `AddWX78BakeState`           → wx bake state
If any injection call exists in source but the resulting states are absent from the Properties state table, flag each missing state group:
{"issue": "CommonStates.AddVoidFallStates injects 'abyss_fall' and 'voiddrop' states but neither appears in the ## Properties state reference table.", "suggestion": "Add abyss_fall and voiddrop rows to the state reference table in ## Properties."}

ACTION HANDLERS SECTION RULE: If the stategraph defines `ActionHandler(ACTIONS.XXX, fn)` entries in the `actionhandlers = {}` argument to `StateGraph(...)`, the doc MUST have a `## Action Handlers` section listing each `ACTIONS` constant and what state it transitions to or behavior it triggers. If ActionHandler entries exist in source but `## Action Handlers` is absent:
{"issue": "Stategraph defines N ActionHandler entries (ACTIONS.TOGGLEWXSCREECH, ...) but ## Action Handlers section is absent from the document.", "suggestion": "Add ## Action Handlers section listing each ACTIONS constant and its handler behavior."}

### Brain file checks
- `OnStart()` is documented and the description names the root SelectorNode/SequenceNode children.
- Local helper functions passed as callbacks to behaviour nodes are documented with `(local)` marker.
- File-scope constants gating behaviour (e.g., `START_FACE_DIST = 20`) appear in the Properties table.
- Events & listeners section is typically `None` — flag only if source actually has ListenForEvent.

### Behaviour file checks
- `Visit`, `Reset`, `DBString` are documented (they form the BehaviourNode contract).
- `_ctor` is documented as a function entry with parameter list.
- Usage example shows the node embedded inside a SelectorNode/SequenceNode tree, not a standalone
  call.

### Widget file checks
- `_ctor` is documented and lists every constructor parameter.
- Child widgets created via `self:AddChild(...)` appear in the Properties table.
- **Conditional children:** If source creates child widgets inside `if` blocks (e.g., based on `item:HasTag(...)`), ALL such conditional children must appear in Properties with their creation condition noted. If a child widget is created in source but absent from the Properties table, flag it:
  {"issue": "Child widget `rechargeframe` created conditionally (when item has 'rechargeable' tag) is missing from the Properties table.", "suggestion": "Add a row for `rechargeframe` noting it is created only when item has the 'rechargeable' tag."}
- Usage example uses `screen:AddChild(MyWidget(...))`. NEVER `CreateEntity` or `AddComponent`.
- No mention of `inst.components` (widgets do not interact with ECS).

### Screen file checks
- `_ctor`, `OnControl` documented; `OnUpdate` documented if present.
- Usage example shows `TheFrontEnd:PushScreen(MyScreen(...))`.
- Properties section lists child widgets and screen state.

### Prefab file checks
- `fn()` and `master_postinit(inst)` documented as separate function entries.
- **Properties table — INCLUDE these and ONLY these categories (in order):**
  - `assets` and `prefabs` arrays (the Prefab() call arguments) — type: `table`
  - File-scope `local NAME = <literal>` constants that gate function behavior (e.g., `local PHYSICS_RADIUS = 0.5`) — type: `constant`
  - Key TUNING table references consumed by the prefab (e.g., `TUNING.SKILLS.WX78.BACKUPBODY_WORK_REQUIRED`). These are external globals, NOT file-scope locals, but for prefab files they ARE documented so API consumers know which tuning parameters govern behavior — type: `constant`. **This is an intentional prefab-specific exception to `content_rules`'s general "do not list external globals" principle.**
- **Properties table — DO NOT include these:**
  - Instance methods assigned onto `inst` in `fn()` (e.g., `inst.TryToAttachToOwner = TryToAttachToOwner`) — these are functions, not properties; they belong in Main functions
  - Child entity handles set onto `inst` at runtime (e.g., `inst.wx78_classified`, `inst.wx78_backupbody_inventory`) — runtime entity references, not file-scope properties
  - DST engine globals (e.g., `TheWorld`, `TheNet`, `STRINGS`, `ACTIONS`, `GLOBAL`) — engine globals, not prefab properties
- **OSCILLATION GUARD — Properties section:** Do NOT oscillate between iterations about whether TUNING constants or instance methods belong in Properties. The rules are settled: TUNING constants MUST be listed (type: `constant`); instance methods MUST NOT be listed (they go in Main functions). These decisions are final — if a prior iteration told you otherwise, ignore it and follow these rules.
- **OSCILLATION GUARD — Function heading `inst` param:** Do NOT oscillate between iterations about whether `inst` appears in a function heading. Apply the call-site rule from `function_format` skill ONCE and keep it: if the call site is `inst:X(args)` (method assignment) → no `inst` in heading; if the call site is `X(inst, args)` (callback/task) → `inst` IS in heading. Do not re-flag a heading that was already corrected to match the call-site rule.
- Dependencies & tags lists every component attached, the stategraph set, the brain set,
  and every tag added in fn() or master_postinit.
- Usage example uses `SpawnPrefab("name")`.
- **MakePlayerCharacter check:** If source calls `MakePlayerCharacter(...)`, the primary functions are `common_postinit` and `master_postinit` — NOT a generic `fn()`. Flag if the doc uses `fn()` as the entry point heading for player character prefabs.
- **Multiple prefab returns check:** Scan the source file's last `return` statement for comma-separated `Prefab(...)` calls. If N > 1 prefabs are returned but the doc only covers 1, flag it:
  {"issue": "Source file returns N prefabs but only 1 is documented. Missing: prefab_name_2, prefab_name_3.", "suggestion": "Add subsections or an Overview note for each additional prefab registered by this file."}

### Replica file checks (per replica_pattern skill)
- Every netvar declared in source appears in the Properties table.
- Methods are marked `(master only)` / `(client read)` / `(RPC handler)` as applicable.
- Overview states the corresponding master component name and what fields are mirrored.

## Special Case: need_special_case

Use need_special_case=true ONLY when ALL three conditions are true:
1. The content is ACCURATE — no wrong signatures, wrong types, hallucinated functions
2. The document uses a non-standard section name
3. The standard name would be semantically MISLEADING for this specific file

WHEN TO TRIGGER:
- File contains only `local function` declarations → "## Internal Helper Functions" is more
  accurate than "## Main functions" (local functions are NOT accessible outside the file)
- File mixes module-level globals with instance-level class properties → "## Global Variables"
  + "## Class Properties" is more accurate than a single "## Properties"
- Any case where the required heading misrepresents the actual content structure

DO NOT use need_special_case for:
- Normal content errors (wrong params, hallucinated APIs) → use findings instead
- Personal preference or style differences → enforce standard names
- When the standard name is merely imperfect but not misleading

## Valid Response States

Only these 4 combinations are valid:

1. Content accurate, no section dispute:
   {"approved": true, "need_special_case": false, "findings": []}

2. Content accurate, section name dispute:
   {"approved": true, "need_special_case": true,
    "special_case_standard_heading": "## Main functions",  // example only — use the actual disputed heading
    "special_case_reason": "...", "findings": []}

3. Content issues only (no section dispute):
   {"approved": false, "need_special_case": false, "findings": [{"issue": "...", "suggestion": "..."}]}

4. Content issues AND section name dispute:
   {"approved": false, "need_special_case": true,
    "special_case_standard_heading": "## Main functions",  // example only — use the actual disputed heading
    "special_case_reason": "...", "findings": [{"issue": "...", "suggestion": "..."}]}

INVARIANT: approved=false requires findings to be non-empty. NEVER return approved=false with findings=[].
DO NOT put the section name dispute in findings — section dispute belongs in special_case_reason only.

special_case_standard_heading: the EXACT standard heading being replaced (e.g. "## Main functions",
"## Properties"). This is required when need_special_case=true — it tells the system which specific
heading check to bypass. MUST be one of the standard required headings.

special_case_reason MUST follow: "The document uses [NON-STANDARD NAME] instead of the standard
[STANDARD NAME]. Reason: [Lua-backed evidence with line references]. This makes [NON-STANDARD NAME]
more accurate because [specific consequence if standard name were used]."

## Convergence Rule — Multi-iteration Review

When `=== PREVIOUS ITERATION ISSUES ===` appears in the review context, this is a follow-up iteration. Apply these rules:

**Budget:** At most **5 NEW findings** per follow-up iteration. Unresolved issues from the previous iteration do NOT count against this budget — always re-raise them.

**Priority order for new findings:**
1. Direct cascades from the previous patches (e.g., a fix created a new duplicate, a delete left a dangling reference)
2. Wrong function signatures or hallucinated functions introduced by the previous writer
3. Missing required sections (## Overview, ## Properties, etc.)

**Do NOT add in follow-up iterations:**
- Refinements or improvements to sections NOT touched by the previous writer patches
- Issues that existed before iteration 1 but were not in the previous findings (they had their chance)
- Cosmetic or wording improvements
- Issues requiring structural section rearrangement (moving functions between sections) — if you raised this in a previous iteration and the writer could not fix it, do not re-raise it until a prior critical issue is resolved

**Why this matters:** The writer applies patches sequentially. A 22-issue findings list leads to 22+ patches, most of which fail because earlier patches shifted the document text and made later `old_text` anchors stale. Focused reviews converge faster.

**Exception:** If the document has a CRITICAL content error (hallucinated API, completely wrong function signatures throughout, missing required section) that would make the documentation misleading or unusable, report it regardless of iteration limit.