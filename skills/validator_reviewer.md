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

=== SECTION ## Events & listeners ===
- **Listens to:** events registered via inst:ListenForEvent(event, fn)
- **Pushes:** events fired via inst:PushEvent(event, data)
Omit this section entirely if the component has no events.
