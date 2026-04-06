---
name: validator_reviewer
description: Content accuracy review checklist, section requirements, special case logic for documentation validation
inject_into: [reviewer_full, reviewer_typed]
---

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
If no properties exist, the table MUST include a None data row:
| None | | | No properties are defined. |
Do NOT leave the table with header + separator only and no data rows — that is incorrect.
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

=== SPECIAL CASE — need_special_case ===
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

VALID RESPONSE STATES — only these 4 combinations are valid:

1. Content accurate, no section dispute:
   {"approved": true, "need_special_case": false, "findings": []}

2. Content accurate, section name dispute:
   {"approved": true, "need_special_case": true,
    "special_case_standard_heading": "## Main functions",
    "special_case_reason": "...", "findings": []}

3. Content issues only (no section dispute):
   {"approved": false, "need_special_case": false, "findings": [{"issue": "...", "suggestion": "..."}]}

4. Content issues AND section name dispute:
   {"approved": false, "need_special_case": true,
    "special_case_standard_heading": "## Main functions",
    "special_case_reason": "...", "findings": [{"issue": "...", "suggestion": "..."}]}

INVARIANT: approved=false requires findings to be non-empty. NEVER return approved=false with findings=[].
DO NOT put the section name dispute in findings — section dispute belongs in special_case_reason only.

special_case_standard_heading: the EXACT standard heading being replaced (e.g. "## Main functions",
"## Properties"). This is required when need_special_case=true — it tells the system which specific
heading check to bypass. MUST be one of the standard required headings.

special_case_reason MUST follow: "The document uses [NON-STANDARD NAME] instead of the standard
[STANDARD NAME]. Reason: [Lua-backed evidence with line references]. This makes [NON-STANDARD NAME]
more accurate because [specific consequence if standard name were used]."
