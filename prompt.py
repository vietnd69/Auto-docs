"""
Module chứa hàm build_prompt() — tạo prompt cho LLM.
Không chứa constants, chỉ chứa template.
"""

from get_docs import (
    extract_lua_references,
    safe_read_lua,
    compute_source_hash,
    format_connected_section,
    clean_model_output,
    get_lua_files,
)
from skills_loader import load_skill

# Skill content loaded once at module import.
_DST_CONV = load_skill("dst_conventions")
_FEW_SHOT = load_skill("few_shot")


def build_prompt(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    lua_code: str,
    connected_section: str,
    connected_content: str = "",
    source_hash: str = "",
    *,
    file_tree: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
) -> str:
    """
    Tạo prompt đầy đủ để gửi cho LLM tạo tài liệu cho một file Lua.
    Tất cả config (version, date, tree...) được truyền vào qua tham số.
    """
    return f"""You are an expert technical writer and a veteran mod developer for the game Don't Starve Together (DST).
Your task is to analyze the Lua source file provided below and generate comprehensive, highly readable API reference documentation for modders and developers.
All documentation text must be written in clear, concise English.

=== CONTEXT ===

1. PROJECT FILE TREE
   The following is the directory structure of the DST Lua codebase.
   Use it to understand how the project is organized and where related files are located.

{file_tree}

2. TARGET FILE
   This is the file you are documenting:
   {display_filepath}

3. CONNECTED FILES AND FUNCTIONS
   The target file references the following external files and their functions/properties.
   These are extracted directly from `require()` statements and `components.X:Function()` calls in the source code.
   Use this information to understand cross-component dependencies and how this component interacts with the rest of the system.
   {connected_section if connected_section else "No external references found — this component is self-contained. You may write 'None identified' for the Dependencies & tags section."}

4. CONNECTED FILES — EXTRACTED SOURCE CODE
   Below is the actual source code of the referenced functions and properties from connected files.
   Use this to understand exact signatures, return types, and behaviors of external APIs used by the target file.
   {connected_content if connected_content else "No function source code available. Base your documentation solely on the target file's own code."}

5. DST CODING CONVENTIONS
{_DST_CONV}

=== TODAY'S DATE: {today_date} ===

=== OUTPUT FORMAT ===

Generate documentation following this EXACT Markdown structure. The output MUST start with the YAML frontmatter block (the first `---` line).

YAML FRONTMATTER RULES:
- `description`: Replace with a real, single English sentence summarizing what this component does. Do NOT leave placeholder text.
- `tags`: Populate with 2-5 lowercase tags that help categorize this component for search and filtering (e.g., `[combat, ai, boss]`). Choose from domain terms relevant to the component.
- `last_updated`: Use exactly `{today_date}`.
- `system_scope`: Choose ONE lowercase keyword that best describes this component's domain: `world`, `player`, `entity`, `ui`, `audio`, `combat`, `environment`, `inventory`, `crafting`, `network`, `brain`, `locomotion`, `physics`, or `fx`. If none of these fits well, use the closest match or infer a suitable single-word scope from context.
- Do NOT leave any `[]`, `<>`, or the words "automatically generated" in the YAML.
- The YAML frontmatter block MUST start with exactly `---` on its own line and end with exactly `---` on its own line. Do NOT omit or duplicate these delimiters.

---
id: {comp_name}
title: {comp_title}
description: 
tags: []
sidebar_position: 10

last_updated: {today_date}
build_version: {version}
change_status: stable
category_type: {category_type}
source_hash: {source_hash}
system_scope: 
---

# {comp_title}

> Based on game build **{version}** | Last updated: {today_date}

## Overview
Provide a clear, concise explanation of what this component does within the game's Entity Component System.
What is its main responsibility? How does it fit into the larger game architecture?
If it interacts heavily with other components (see "Connected Files" above), briefly mention the key relationships.

## Usage example
Provide a short (5-15 lines) Lua code snippet demonstrating typical usage of this component.
Show how to add the component to an entity and call its primary functions.
Use a fenced code block with `lua` syntax highlighting.

## Dependencies & tags
**Components used:** List components this script accesses via `inst.components.X` or adds via `inst:AddComponent("X")`.
**Tags:** List any tags this component adds, removes, or checks (e.g., `inst:AddTag("tag")`).
If none are apparent, write "None identified."

## Properties
Create a Markdown table of the key public variables/properties initialized in the constructor.
Columns: `Property` | `Type` (infer if possible) | `Default Value` | `Description`.
If no suitable properties can be identified, write "No public properties" instead of inventing content.

## Main functions
Document the core functional methods. Skip trivial getters/setters.
For each function:
### `FunctionName(params)`
* **Description:** What does this function do? When is it typically called?
* **Parameters:** Explain each argument's purpose and expected type.
* **Returns:** What does it return, if anything?
* **Error states:** If this function can return `nil` or has known failure/edge-case conditions, document them. Otherwise omit this line.

## Events & listeners
List events this component interacts with:
- **Listens to:** Events registered via `inst:ListenForEvent(event, fn)`.
- **Pushes:** Events fired via `inst:PushEvent(event, data)`.
If there are no events or listeners, omit this entire section.

=== CRITICAL INSTRUCTIONS ===
- REQUIRED SECTION ORDER: The output MUST strictly follow this exact sequence of sections: `## Overview` -> `## Usage example` -> `## Dependencies & tags` -> `## Properties` -> `## Main functions` -> `## Events & listeners`. Do NOT omit, reorder, or rename these sections.
- Output ONLY valid Markdown. The output must begin with `---` (the YAML frontmatter opening delimiter).
- Generate exactly ONE frontmatter block. Do NOT insert extra `---` dividers anywhere in the document body.
- All content must be derived ONLY from the source code below. Do NOT invent APIs, functions, properties, or behaviors that are not present in the source.
- SHORT FILES: If the source file is small or simple, keep the documentation proportionally short. If a section has no applicable content, write "Not applicable" or "None identified" rather than inventing information. It is acceptable for sections like Events & listeners or Properties to be very brief or omitted entirely.
- HEADING STYLE: Use sentence case for all headings — capitalize only the first word (e.g., "Main functions", not "Main Functions"). Proper nouns and acronyms remain capitalized (e.g., "DST", "Lua").
- HEADING LEVELS: Never skip heading levels. `###` must only appear under a `##` section. Do NOT introduce `####` or deeper unless absolutely necessary.
- MDX COMPATIBILITY: Wrap any expression containing `<`, `>`, `<=`, `>=`, `{{`, or `}}` in inline code backticks (e.g., `Y <= 0.05`, `inst:HasTag("tag")`). Never leave bare angle brackets or curly braces in plain prose — Docusaurus MDX will fail to parse them as JSX.
- CURLY BRACES: Do NOT use unescaped `{{` or `}}` in regular prose text. If required, use inline code backticks.
- CONSTRUCTOR: If the constructor uses `Class(function(self, ...) ... end)` instead of `_ctor`, document it accordingly. The first parameter after `self` may be `inst`, `data`, or any other name.
- NO CODE FENCES AROUND OUTPUT: Do NOT wrap the entire output in a markdown code fence (```).
- NO FILLER TEXT: Do NOT include greetings, sign-offs, meta-commentary, or any text that is not part of the documentation itself.
- NO EMOJIS OR UNICODE SYMBOLS: Do NOT use icons or special characters (e.g., ⚙️, ✅, ❌, 💡). Use plain text only.
- IMPORTANT: Never repeat the same line or bullet point more than once. If you find yourself repeating, stop and move to the next item.

{_FEW_SHOT}

=== SOURCE CODE ===
{lua_code}
"""
