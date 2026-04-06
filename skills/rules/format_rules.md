---
name: format_rules
description: MDX compatibility, section order, YAML frontmatter, heading rules for generated documentation
inject_into: [analyst, analyst_merge, analyst_merge_legacy]
---

# Format Rules

## Section Order

Never change this order:
`## Overview` → `## Usage example` → `## Dependencies & tags` → `## Properties` → `## Main functions` → `## Events & listeners`

Do NOT omit, reorder, or rename these sections.
**Exception:** `## Events & listeners` may be omitted when the source file has no events (no `ListenForEvent` or `PushEvent` calls).

## Output Format

- Output ONLY valid Markdown starting with `---` (YAML frontmatter opening delimiter).
- Generate exactly ONE frontmatter block. No extra `---` dividers in the document body.
- No code fences around the entire output.
- Do NOT wrap the entire output in a markdown code fence (```).
- No emojis or unicode symbols — plain text only.

## YAML Frontmatter

- `description`: One real English sentence. Never leave placeholder text.
- `tags`: 2-5 lowercase domain keywords (e.g., [combat, ai, boss]). Not entity tags.
- `system_scope`: One of: world, player, entity, ui, audio, combat, environment, inventory,
  crafting, network, brain, locomotion, physics, fx. Pick the most accurate.
- `last_updated`, `build_version`, `change_status`, `category_type`, `source_hash`: copy exactly.
- Do NOT leave any `[]`, `<>`, or the words "automatically generated" in the YAML.
- The YAML frontmatter block MUST start with exactly `---` on its own line and end with exactly `---` on its own line. Do NOT omit or duplicate these delimiters.

## MDX Compatibility

Docusaurus fails on bare JSX tokens:
- Wrap in backticks: `<`, `>`, `<=`, `>=`, `{{`, `}}`
- Example: write `value <= 0` not value <= 0 in prose.
- Never leave bare angle brackets or curly braces in plain text.
- Do NOT use unescaped `{{` or `}}` in regular prose.

## Heading Rules

- Sentence case: "Main functions" not "Main Functions". Proper nouns/acronyms stay capitalized.
- Never skip heading levels. `###` only under `##`. No `####` unless absolutely necessary.