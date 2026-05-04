---
name: format_rules
description: MDX compatibility, section order, YAML frontmatter, heading rules for generated documentation
inject_into: [analyst, analyst_chunk, analyst_merge, analyst_merge_legacy]
---

# Format Rules

## Section Order

Never change this order:
`## Overview` → `## Usage example` → `## Dependencies & tags` → `## Properties` → `## Main functions` → `## Events & listeners`

Do NOT omit, reorder, or rename these sections. If a section has no content, write `**None.**` — never drop the heading.

Exception: `## Events & listeners` — if the source file has no `ListenForEvent`, `PushEvent`, or `WatchWorldState` calls, write `**None.**` as the section body (keep the `## Events & listeners` heading).

`## Properties` is mandatory for all file types:
- Non-stategraph files: use the `| None | | | No properties are defined. |` row when no properties exist.
- Stategraph files: include the state reference table first, then file-scope constants if present.

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

## Code Fence Closure

Every fenced code block opened with ` ``` ` MUST be closed with a matching ` ``` ` before the next `##` or `###` heading.
A code block that bleeds into a heading causes Docusaurus to render the entire following section as raw code — the heading disappears from the page.

**Mandatory self-check after writing `## Usage example`:**
- Confirm the closing ` ``` ` appears on its own line.
- Confirm there is a blank line between the closing fence and the next `##` heading.
- If the code block is missing its closing fence, the MDX validator will flag it as a compile error.

## Heading Rules

- Sentence case: "Main functions" not "Main Functions". Proper nouns/acronyms stay capitalized.
- Never skip heading levels. `###` only under `##`. No `####` unless absolutely necessary.