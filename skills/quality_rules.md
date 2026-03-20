# Skill: quality_rules

=== DOCUMENTATION QUALITY RULES ===

SECTION ORDER (never change):
  ## Overview -> ## Usage example -> ## Dependencies & tags -> ## Properties -> ## Main functions -> ## Events & listeners
  Do NOT omit, reorder, or rename these sections.

OUTPUT FORMAT:
- Output ONLY valid Markdown starting with `---` (YAML frontmatter opening delimiter).
- Generate exactly ONE frontmatter block. No extra `---` dividers in the document body.
- No code fences around the entire output.

YAML FRONTMATTER:
- `description`: One real English sentence. Never leave placeholder text.
- `tags`: 2-5 lowercase domain keywords (e.g., [combat, ai, boss]). Not entity tags.
- `system_scope`: One of: world, player, entity, ui, audio, combat, environment, inventory,
  crafting, network, brain, locomotion, physics, fx. Pick the most accurate.
- `last_updated`, `build_version`, `change_status`, `category_type`, `source_hash`: copy exactly.

CONTENT RULES:
- All content must come ONLY from the source code or provided JSON. Do NOT invent APIs.
- Never repeat the same line or bullet point more than once.
- No greetings, sign-offs, meta-commentary, or filler text.
- No emojis or unicode symbols.

MDX COMPATIBILITY (Docusaurus fails on bare JSX tokens):
- Wrap in backticks: `<`, `>`, `<=`, `>=`, `{{`, `}}`
- Example: write `value <= 0` not value <= 0 in prose.
- Never leave bare angle brackets or curly braces in plain text.
- Do NOT use unescaped `{{` or `}}` in regular prose.

HEADING RULES:
- Sentence case: "Main functions" not "Main Functions". Proper nouns/acronyms stay capitalized.
- Never skip heading levels. `###` only under `##`. No `####` unless absolutely necessary.

SHORT FILES:
- If source is small or simple, keep docs proportionally short.
- If a section has no content, write "Not applicable" or "None identified" — do not invent.
- Events & listeners may be omitted if the component has none.

CONSTRUCTOR RULE:
- Document `Class(function(self, ...) ... end)` constructors accordingly.
- The first parameter after `self` may be `inst`, `data`, or any other name — document as-is.

FILE TYPE CLASSIFICATION (determine before writing any section):
- DATA CONFIG FILE: no Class() constructor, no self.inst, returns a plain table/array.
  → MUST apply ALL [Data config] rules. Do NOT use [Component] patterns.
  → Consult the HOW TO DETECT note at the top of the data config few-shot example.
- COMPONENT FILE: has Class(function(self, ...) ... end) constructor.
  → MUST apply ALL [Component] rules. Do NOT use [Data config] patterns.
When signals are mixed (e.g., local helper functions that resemble constructors),
check: does the file's top-level return value contain a plain array/table, not a class instance?
If yes → DATA CONFIG FILE.

PROPERTIES TABLE:
- Columns: Property | Type | Default Value | Description
- If no properties exist, write header and separator row only (no data rows).
- Do NOT invent properties not in the constructor JSON.

DATA CONFIG FILE PROPERTIES:
MUST document TWO groups of rows in this order:
  1. The top-level container variable (the returned global/local table).
  2. One row per key in each record entry (e.g., name, id.steam, id.psn).
NEVER document only the container and omit the record schema.
NEVER use a real default value for record fields — always write "—" (em dash).
NEVER write "nil" as a default — that is a real default value. Use "—" only.
Nested table fields accessed via dot notation (id.steam, id.psn) MUST each be
their own property row. Never collapse them into a single parent row (e.g., id).

DATA CONFIG FILE MAIN FUNCTIONS:
Local factory/builder functions that construct record entries (e.g., ACHIEVEMENT(),
ENTRY()) MUST be documented in ## Main functions — they define the record schema
and are part of the data API. Do NOT treat them as internal implementation details
or skip them because they are local.

COMPLETENESS:
- Keep ALL functions — never drop trivial getters/setters.
- If a function appears in multiple chunks, prefer the entry with more parameter/return detail.
- Merge all events, dependencies, and tags; never drop an entry.
- If a field has no data, use "None" (string) or [] (empty array) — never omit the field.

OVERVIEW WRITING:
(As classified above — see FILE TYPE CLASSIFICATION.)
- [Component] State: what this component does + its role in the ECS system.
  Mention key relationships with other components (from Connected Files context).
- [Data config] State: what static data this file defines, how it is structured,
  and how other systems access it via require(). Do NOT describe it as a component
  or reference the ECS system.
- 2-5 sentences. No padding.

USAGE EXAMPLE WRITING:
(As classified above — see FILE TYPE CLASSIFICATION.)
- [Component] Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.
- [Data config] Show `require()` followed by index access to the returned table (e.g., `Table[1]`).
  Do NOT use `CreateEntity()`, `AddComponent`, or `inst.components`.
- 5-15 lines. Use the component's actual function names from the documentation. No generic placeholder names.

INCOMPLETE FUNCTION HANDLING (chunk boundary):
- If a function body is cut off at chunk boundary, keep it and note "INCOMPLETE — continues in adjacent chunk".
- Do NOT skip or drop incomplete functions.
