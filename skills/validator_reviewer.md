# Skill: validator_reviewer

=== REVIEWER CHECKLIST ===
Check CONTENT ACCURACY ONLY:
1. Function signatures and params match Lua source exactly — no hallucinated names/types
2. Descriptions are accurate (not vague/wrong about what the function actually does)
3. Usage example uses real function names and correct call patterns
4. Section contains required content (see requirements below)
5. No invented properties, events, or dependencies not present in Lua source

Do NOT flag formatting, bullet style, or structural notation issues — only flag content errors (wrong/missing/hallucinated information).

STRUCTURAL GUARD: Do NOT rename or remove ### headings in your review suggestions unless the function is hallucinated (not in the Lua source).

=== SECTION ## Overview ===
[Component] 2-5 sentences: what this component does + its role in ECS.
Mention key relationships with other components.
[Data config] 2-5 sentences: what static data this file defines, how it is structured,
and how other systems access it via require(). Do NOT reference ECS or AddComponent.

=== SECTION ## Usage example ===
5-15 lines of realistic Lua using actual function names from this file.
[Component] Show CreateEntity(), AddComponent(), then call 2-3 primary functions.
[Data config] Show require() followed by table index access (e.g. Table[1]).
No CreateEntity(), AddComponent(), or inst.components.

REQUIRE PATH RULE: The require() path must match the actual source FILE NAME, not the class name.
Example: if the file is `brains/crittersbrain.lua` and the class is `CritterBrain`,
the correct path is require("brains/crittersbrain") — NOT require("brains/critterbrain").
Do NOT flag a require path as wrong solely because it differs from the class name.

=== SECTION ## Dependencies & tags ===
Must contain EXACTLY these labels (in order):
**External dependencies:** — list each `name` -- usage, or omit if none
**Components used:** — list each `component_name` -- methods/properties accessed
**Tags:** — list each `tag_name` -- add/remove/check, or 'None' if no game tags

=== SECTION ## Properties ===
Table with columns: Property | Type | Default Value | Description.
If no properties exist, write header + separator row only (no data rows).
Do NOT invent properties not in the constructor.
Data config files: document the top-level container + each record field.

=== SECTION ## Main functions ===
Each entry uses a ### heading with function name.
Keep ALL functions — never drop trivial getters/setters.

FIELD RULES:
- **Error states:** is a valid field even when it describes conditional behavior or logic branches
  (not just exceptions). Do NOT suggest renaming it to Notes, Behavior, or any other name.
- If content inside **Error states:** is genuinely non-error (e.g. pure conditional logic with
  no failure path), suggest incorporating that content into **Description:** instead.
- `* **Error states:** None` is a valid, correct value — do NOT flag it.
- Do NOT introduce new field names. Only use: Description, Parameters, Returns, Error states.

ERROR STATES BOUNDARY TEST (apply before flagging anything in this field):
  Ask: "Would calling this function with this input CRASH or SILENTLY CORRUPT state,
  given no guard exists in the Lua source?" If YES → valid Error states entry.
  If NO (it returns a defined value, falls back, or is an optional param) → belongs in
  Description or Returns, NOT Error states.

ERROR STATES — WHAT DOES NOT BELONG THERE (move to Description):
  BAD: "Returns false if entity is on specific island" — normal conditional return path
  BAD: "If inst is nil, falls back to default behavior" — optional parameter handling
  BAD: "Behavior changes if SPECIAL_EVENTS.X is active" — conditional logic branch
  BAD: "Returns standard result if entity lacks tag Y" — else branch of an if statement
  BAD: "Returns nil if no entity found" — expected empty-result return path
  GOOD: "Errors if inst is nil (no nil guard before member access)" — actual crash path
  GOOD: "Returns nil if required component missing (inventory, luckuser)" — missing dependency

=== SECTION ## Events & listeners ===
- **Listens to:** events registered via inst:ListenForEvent(event, fn)
- **Pushes:** events fired via inst:PushEvent(event, data)
Omit this section entirely if the component has no events.
