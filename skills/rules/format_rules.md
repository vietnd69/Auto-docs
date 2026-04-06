---
name: format_rules
description: MDX compatibility, section order, YAML frontmatter, heading rules for generated documentation
inject_into: [analyst, analyst_merge, analyst_merge_legacy]
---

# Format Rules

=== DOCUMENTATION FORMAT RULES ===

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
- Do NOT leave any `[]`, `<>`, or the words "automatically generated" in the YAML.
- The YAML frontmatter block MUST start with exactly `---` on its own line and end with exactly `---` on its own line. Do NOT omit or duplicate these delimiters.

MDX COMPATIBILITY (Docusaurus fails on bare JSX tokens):
- Wrap in backticks: `<`, `>`, `<=`, `>=`, `{{`, `}}`
- Example: write `value <= 0` not value <= 0 in prose.
- Never leave bare angle brackets or curly braces in plain text.
- Do NOT use unescaped `{{` or `}}` in regular prose.

HEADING RULES:
- Sentence case: "Main functions" not "Main Functions". Proper nouns/acronyms stay capitalized.
- Never skip heading levels. `###` only under `##`. No `####` unless absolutely necessary.

NO CODE FENCES AROUND OUTPUT: Do NOT wrap the entire output in a markdown code fence (```).
NO EMOJIS OR UNICODE SYMBOLS: Do NOT use icons or special characters. Use plain text only.
