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

PROPERTIES TABLE:
- Columns: Property | Type | Default Value | Description
- If no properties exist, write header and separator row only (no data rows).
- Do NOT invent properties not in the constructor JSON.

COMPLETENESS:
- Keep ALL functions — never drop trivial getters/setters.
- If a function appears in multiple chunks, prefer the entry with more parameter/return detail.
- Merge all events, dependencies, and tags; never drop an entry.
- If a field has no data, use "None" (string) or [] (empty array) — never omit the field.

OVERVIEW WRITING:
- State: what this component does + its role in the ECS system.
- Mention key relationships with other components (from Connected Files context).
- 2-5 sentences. No padding.

USAGE EXAMPLE WRITING:
- Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.
- 5-15 lines. Use the component's actual function names from the documentation.
- No generic placeholder names.

INCOMPLETE FUNCTION HANDLING (chunk boundary):
- If a function body is cut off at chunk boundary, keep it and note "INCOMPLETE — continues in adjacent chunk".
- Do NOT skip or drop incomplete functions.
