"""
Module chứa prompt templates cho xử lý file Lua dài (chunked processing).

Templates:
  - build_chunk_prompt():  prompt cho mỗi chunk — output JSON matching schema
  - build_merge_prompt():  prompt tổng hợp — nhận PreSynthesisResult, pre-filled YAML
  - build_single_prompt(): re-export prompt cũ cho file ngắn

Legacy (kept for backward compat, not used in JSON pipeline):
  - _build_merge_prompt_legacy():  old text-based merge prompt
  - build_intermediate_merge_prompt():  old hierarchical merge prompt
"""

import json

from prompts.standard import build_prompt as build_single_prompt  # noqa: F401
from prompts.pre_synthesis import PreSynthesisResult
from prompts.skills_loader import combine_skills


def build_intermediate_merge_prompt(
    comp_name: str,
    display_filepath: str,
    group_results: list[str],
    group_index: int,
    total_groups: int,
) -> str:
    """
    Prompt gọn cho merge trung gian (tầng 1 của hierarchical merge).
    KHÔNG cần file_tree, connected_content, YAML frontmatter.
    Output được dùng làm input cho build_merge_prompt() ở tầng 2,
    nên phải giữ đầy đủ thông tin — KHÔNG được mất function/event nào.
    """
    combined = ""
    for i, r in enumerate(group_results, 1):
        combined += f"\n--- ANALYSIS {i}/{len(group_results)} OF {comp_name} ---\n{r}\n"

    return f"""You are an expert technical writer merging partial analyses of a DST Lua component.

File: {display_filepath}
Component: {comp_name}
This is intermediate merge group {group_index}/{total_groups}.

Your task: merge the {len(group_results)} chunk analyses below into ONE structured intermediate summary.
This output will be used as input for a final merge step — information lost here CANNOT be recovered.

=== MERGE RULES ===
- COMPLETENESS OVER BREVITY: Keep all function signatures, parameters, return types, and descriptions intact.
- Deduplicate functions and properties that appear more than once. When duplicate, prefer the entry with more detail (more parameters / return info).
- Keep ALL functions found. Do NOT drop any, even trivial getters/setters.
- If a function is marked "INCOMPLETE — continues from/to adjacent chunk", include it and preserve the incomplete note.
- Merge all events, dependencies, and tags without dropping any entry.
- Do NOT produce YAML frontmatter.
- Do NOT invent or assume any API not present in the analyses below.
- Do NOT include greetings, sign-offs, or meta-commentary.
- Wrap `<`, `>`, `<=`, `>=`, `{{`, `}}` in backticks.
- IMPORTANT: Never repeat the same line or bullet point more than once. If you find yourself repeating, stop and move to the next item.

=== SKILLS ===
{combine_skills("analyst_intermediate")}

=== OUTPUT FORMAT ===
Use EXACTLY this structure — do not add, remove, or rename sections:

## Constructor analysis
List all `self.X = value` assignments as properties. Write "None found" if absent.

## Functions found
For each function:
### `FunctionName(params)`
* **Description:** What does this function do?
* **Parameters:** Explain each argument.
* **Returns:** What does it return, if anything?
* **Error states:** Edge cases or nil returns (omit if none).
Write "None found" if absent.

## Events found
- **Listens to:** event_name — description
- **Pushes:** event_name — description
Write "None found" if absent.

## Dependencies found
- Component name — how it's used
Write "None found" if absent.

## Tags found
- tag_name — add/remove/check
Write "None found" if absent.

=== ANALYSES TO MERGE ===
{combined}
"""


def build_chunk_prompt(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    chunk_code: str,
    chunk_index: int,
    total_chunks: int,
    *,
    file_tree: str = "",
    connected_section: str = "",
    connected_content: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
) -> str:
    """
    Tạo prompt cho 1 chunk của file Lua.
    LLM output ONLY JSON matching the fixed schema — no markdown, no prose.
    JSON sẽ được parse bởi pre_synthesize() trong pre_synthesis.py.
    """
    return f"""You are an expert technical writer and a veteran mod developer for the game Don't Starve Together (DST).
You are analyzing CHUNK {chunk_index} of {total_chunks} from the Lua source file: {display_filepath}

This is NOT the full file. You are only seeing a portion of the code.
Your task is to extract ALL functions, properties, events, dependencies, and tags found in THIS CHUNK ONLY, and output them as a single JSON object.

=== CONTEXT ===

1. PROJECT FILE TREE
{file_tree}

2. TARGET FILE: {display_filepath} (chunk {chunk_index}/{total_chunks})

3. CONNECTED FILES AND FUNCTIONS
   {connected_section if connected_section else "No external references found — this component is self-contained."}

4. CONNECTED FILES — EXTRACTED SOURCE CODE
   {connected_content if connected_content else "No function source code available. Base your analysis solely on the target file's own code."}

=== SKILLS ===
{combine_skills("analyst_chunk")}

=== OUTPUT FORMAT ===

Output ONLY a single valid JSON object. No markdown, no code fences, no commentary.
All fields are REQUIRED. Use the string "None" if a field has no data.

JSON SCHEMA:
{{
  "partial_description": "<one complete sentence describing what this chunk does>",
  "suggested_scope": "<one of: world, player, entity, ui, audio, combat, environment, inventory, crafting, network, brain, locomotion, physics, fx>",
  "constructor_properties": [
    {{
      "name": "<property name (self.X)>",
      "type": "<Lua type: number, string, boolean, table, function, nil, Entity>",
      "default": "<default value as string>",
      "description": "<what this property stores>"
    }}
  ],
  "functions": [
    {{
      "name": "<function name>",
      "params": "<comma-separated parameter list, used in function signature heading>",
      "parameters": [
        {{"name": "<param_name>", "description": "<type and purpose of this parameter>"}}
      ],
      "description": "<what this function does>",
      "returns": "<return value description, or 'nil'>",
      "error_states": "<edge cases or early returns, or 'None'>",
      "incomplete": false
    }}
  ],
  "events": {{
    "listens_to": [{{"event": "<event_name>", "description": "<when/why>"}}],
    "pushes":     [{{"event": "<event_name>", "description": "<when/why>"}}]
  }},
  "dependencies": [
    {{"component": "<component_name>", "usage": "<how it's used>"}}
  ],
  "game_tags": [
    {{"name": "<tag_name>", "operation": "<add|remove|check>"}}
  ],
  "external_deps": [
    {{"name": "<module or global name>", "usage": "<how it is used in this chunk>"}}
  ]
}}

=== FIELD RULES ===
- partial_description: One complete English sentence summarizing THIS chunk's content.
- suggested_scope: Your best guess for the component's system scope based on this chunk.
- constructor_properties: All `self.X = value` assignments found inside any `Class(function(self, ...) ... end)` block in this chunk.
  This applies regardless of what the first parameter is named (inst, data, etc.).
  Use empty array [] if no `Class(...)` block exists in this chunk.
- functions: ALL functions found. Set "incomplete": true if a function is cut off at chunk boundary.
- functions[].params: Comma-separated parameter names only (used in `### FunctionName(params)` heading).
- functions[].parameters: Array with one entry per parameter — name and full description (type, purpose, valid values). Use empty array [] if function takes no parameters.
- events.listens_to: All `inst:ListenForEvent(...)` calls. Use empty array [] if none.
- events.pushes: All `inst:PushEvent(...)` calls. Use empty array [] if none.
- dependencies: All external components referenced (e.g., `inst.components.health`). Use empty array [] if none.
- game_tags: All `AddTag`, `RemoveTag`, `HasTag` calls. Use empty array [] if none found.
- external_deps: All `require("module")` calls AND direct references to these DST global singletons:
  `TheWorld`, `TheNet`, `ThePlayer`, `GLOBAL`, `AllPlayers`, `TheSim`, `TheInput`, `TheCamera`.
  One entry per unique module/singleton name — do NOT create a separate entry for each `GLOBAL.X`
  field access; record the whole pattern as a single entry named `GLOBAL`.
  Do NOT include Lua standard-library names (math, string, table, ipairs, pairs, etc.).
  Use empty array [] if none found.
- For any field with no data, use "None" (string) for string fields or [] (empty array) for array fields.

=== CRITICAL INSTRUCTIONS ===
- Output ONLY valid JSON. No text before or after the JSON object.
- Do NOT wrap the JSON in code fences (no ```json).
- Only extract what is ACTUALLY in this chunk. Do NOT invent content from other chunks.
- If a function body is cut off at the start or end of this chunk, set "incomplete": true.
- Keep descriptions concise but accurate.

=== SOURCE CODE (CHUNK {chunk_index}/{total_chunks}) ===
{chunk_code}
"""


_LARGE_FUNC_LIST_THRESHOLD = 100


def _compact_functions_json(functions: list[dict]) -> str:
    """
    Serialize functions list for merge prompt.
    For large lists (>100 fns): strip always-None/false fields + use compact JSON.
    Saves ~20K tokens for files like SGwilson (601 functions).
    """
    _NOISE_FIELDS = ("incomplete", "error_states")
    _NULL_VALUES = {"none", "", "n/a", "null", "no", "false"}

    def _strip(fn: dict) -> dict:
        return {
            k: v for k, v in fn.items()
            if k not in _NOISE_FIELDS or str(v).strip().lower() not in _NULL_VALUES
        }

    if len(functions) > _LARGE_FUNC_LIST_THRESHOLD:
        stripped = [_strip(f) for f in functions]
        return json.dumps(stripped, ensure_ascii=False)
    return json.dumps(functions, indent=2, ensure_ascii=False)


def build_merge_prompt(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    presynthesis: PreSynthesisResult,
    source_hash: str = "",
    *,
    file_tree: str = "",
    connected_section: str = "",
    connected_content: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
    sidebar_position: int = 10,
) -> str:
    """
    Tạo prompt tổng hợp — nhận PreSynthesisResult đã pre-filled.
    LLM chỉ viết description, Overview, Usage example, và format các section từ JSON.
    """
    # Game tags and external deps for Dependencies section body
    game_tags_json    = json.dumps(presynthesis.game_tags, indent=2, ensure_ascii=False)
    external_deps_json = json.dumps(presynthesis.external_deps, indent=2, ensure_ascii=False)

    # Partial descriptions — numbered list
    descs_section = "\n".join(
        f"{i}. {d}" for i, d in enumerate(presynthesis.partial_descriptions, 1)
    ) or "No descriptions available."

    # JSON sections for LLM to format
    deps_json = json.dumps(presynthesis.dependencies, indent=2, ensure_ascii=False)
    props_json = json.dumps(presynthesis.constructor_properties, indent=2, ensure_ascii=False)
    funcs_json = _compact_functions_json(presynthesis.functions)
    events_json = json.dumps({
        "listens_to": presynthesis.events_listens,
        "pushes": presynthesis.events_pushes,
    }, indent=2, ensure_ascii=False)

    return f"""You are an expert technical writer for Don't Starve Together (DST) modding documentation.

You are creating the final documentation for the component "{comp_name}" from file {display_filepath}.
All structured data (tags, scope, dependencies, properties, functions, events) has been pre-extracted and is provided below as JSON.
Your task is to format this data into a well-organized Markdown document and write the semantic prose sections.

=== CONTEXT ===

1. PROJECT FILE TREE
{file_tree}

2. TARGET FILE: {display_filepath}

3. CONNECTED FILES AND FUNCTIONS
   {connected_section if connected_section else "No external references found."}

4. CONNECTED FILES — EXTRACTED SOURCE CODE
   {connected_content if connected_content else "No function source code available."}

=== SKILLS ===
{combine_skills("analyst_merge")}

=== PARTIAL DESCRIPTIONS (one per chunk) ===
Synthesize these into a single description sentence for the YAML frontmatter.
{descs_section}

=== DEPENDENCIES (pre-extracted) ===
{deps_json}

=== GAME TAGS (pre-extracted) ===
{game_tags_json}

=== EXTERNAL DEPENDENCIES (pre-extracted) ===
{external_deps_json}

=== PROPERTIES (pre-extracted) ===
Format into a markdown table. Do not invent or omit entries.
{props_json}

=== FUNCTIONS (pre-extracted) ===
Deduplicate by name (prefer longer description). Format into ### headings.
{funcs_json}

=== EVENTS (pre-extracted) ===
{events_json}

=== OUTPUT INSTRUCTIONS ===

Produce a complete Markdown document starting with YAML frontmatter.
The YAML frontmatter is PARTIALLY PRE-FILLED — copy the pre-filled values exactly as shown.

YOUR TASKS:
1. Write `description` — synthesize the partial descriptions above into one English sentence.
2. Write `## Overview` — comprehensive summary of the entire component.
3. Write `## Usage example` — 5-15 lines Lua code snippet demonstrating typical usage.
4. Format `## Properties` — render the PROPERTIES JSON as a markdown table. Do not invent or omit entries.
   If the PROPERTIES JSON array is empty ([]), write the table header and separator row only (no data rows):
   `| Property | Type | Default Value | Description |\n|----------|------|---------------|-------------|`
5. Format `## Main functions` using EXACTLY the FUNCTION FORMAT defined in the FORMAT SPECIFICATION section below.
   Deduplicate by function name; prefer the entry with more parameter/return detail.
   For each function's `* **Parameters:**`: use the `parameters` array from the JSON (name + description per entry).
   If the `parameters` array is empty or absent, write `None`.
6. Format `## Events & listeners` — render the EVENTS JSON as bullet lists.
7. Format `## Dependencies & tags` using EXACTLY the DEPENDENCY SECTION FORMAT defined in the FORMAT SPECIFICATION section below, including External dependencies from EXTERNAL DEPENDENCIES JSON (omit External dependencies bullet if empty).

---
id: {comp_name}
title: {comp_title}
description: <WRITE: one sentence from partial descriptions>
tags: <WRITE: 2-5 lowercase tags categorizing this component for docs search. Choose domain terms (e.g. [actions, combat, player]). Do NOT list game entity tags. Maximum 5 entries.>
sidebar_position: {sidebar_position}

last_updated: {today_date}
build_version: {version}
change_status: stable
category_type: {category_type}
source_hash: {source_hash}
system_scope: <REVIEW hint {presynthesis.system_scope} — set the most accurate value from the allowed list based on the Overview you are writing>
---

# {comp_title}

> Based on game build **{version}** | Last updated: {today_date}

## Overview
<WRITE: comprehensive overview>

## Usage example
<WRITE: 5-15 lines Lua code>

## Dependencies & tags
<FORMAT using EXACTLY the DEPENDENCY SECTION FORMAT from the FORMAT SPECIFICATION below>

## Properties
<FORMAT from PROPERTIES JSON into table>

## Main functions
<FORMAT from FUNCTIONS JSON>

## Events & listeners
<FORMAT from EVENTS JSON>

=== CRITICAL INSTRUCTIONS ===
- REQUIRED SECTION ORDER: ## Overview -> ## Usage example -> ## Dependencies & tags -> ## Properties -> ## Main functions -> ## Events & listeners. Do NOT omit, reorder, or rename.
- Write YAML tags freely (2-5 doc-category keywords from the Overview). Review the system_scope hint and set the most accurate value from the allowed list.
- Output ONLY valid Markdown starting with `---`.
- Generate exactly ONE frontmatter block. No extra `---` dividers in the body.
- ALL data must come from the pre-extracted sections above. Do NOT invent APIs.
- MDX COMPATIBILITY: Wrap `<`, `>`, `<=`, `>=`, `{{{{`, `}}}}` in backticks.
- NO code fences around the output.
- NO filler text, greetings, or sign-offs.
- NO emojis or unicode symbols.
- IMPORTANT: Never repeat the same line or bullet point more than once.
"""


# ── Multipass merge prompts (Pass 1a, 1b, 1c, 2) ──


def build_deps_props_prompt(
    comp_name: str,
    display_filepath: str,
    deps_json: str,
    game_tags_json: str,
    external_deps_json: str,
    props_json: str,
) -> str:
    """
    Pass 1a — format `## Dependencies & tags` and `## Properties` from JSON.
    Output ONLY those 2 sections, no YAML frontmatter, no overview.
    """
    return f"""You are an expert technical writer for Don't Starve Together (DST) modding documentation.

You are formatting 2 sections for the component "{comp_name}" from file {display_filepath}.
No prose is needed — format the provided JSON data into the exact Markdown structure specified.

=== FORMAT SPECIFICATION ===
{combine_skills("analyst_merge")}

=== DEPENDENCIES (pre-extracted) ===
{deps_json}

=== GAME TAGS (pre-extracted) ===
{game_tags_json}

=== EXTERNAL DEPENDENCIES (pre-extracted) ===
{external_deps_json}

=== PROPERTIES (pre-extracted) ===
{props_json}

=== OUTPUT INSTRUCTIONS ===

Output ONLY these 2 sections in this exact order:

1. `## Dependencies & tags` — format using EXACTLY the DEPENDENCY SECTION FORMAT from the FORMAT SPECIFICATION section above.
   Include External dependencies bullet only if external_deps JSON is non-empty.

2. `## Properties` — render the PROPERTIES JSON as a markdown table with columns: Property | Type | Default Value | Description.
   If the PROPERTIES JSON array is empty ([]), write the table header and separator row only (no data rows):
   `| Property | Type | Default Value | Description |`
   `|----------|------|---------------|-------------|`

=== CRITICAL INSTRUCTIONS ===
- Output ONLY the 2 sections above. No YAML frontmatter, no ## Overview, no ## Main functions.
- ALL data must come from the JSON provided above. Do NOT invent entries.
- MDX COMPATIBILITY: Wrap `<`, `>`, `<=`, `>=`, `{{{{`, `}}}}` in backticks.
- NO filler text, greetings, or sign-offs.
- NO emojis or unicode symbols.
- IMPORTANT: Never repeat the same line or bullet point more than once.
"""


def build_functions_batch_prompt(
    comp_name: str,
    display_filepath: str,
    functions_batch: list[dict],
    batch_index: int,
    total_batches: int,
) -> str:
    """
    Pass 1b — format a batch of functions into ### FunctionName(params) headings.
    Output ONLY the ### entries — no section header, no YAML, no prose.
    """
    funcs_json = _compact_functions_json(functions_batch)

    return f"""You are an expert technical writer for Don't Starve Together (DST) modding documentation.

You are formatting batch {batch_index}/{total_batches} of `## Main functions` for the component "{comp_name}" from file {display_filepath}.

=== FORMAT SPECIFICATION ===
{combine_skills("analyst_merge")}

=== FUNCTIONS (this batch) ===
{funcs_json}

=== OUTPUT INSTRUCTIONS ===

Format each function from the JSON above using EXACTLY the FUNCTION FORMAT defined in the FORMAT SPECIFICATION section above.
- Use `### FunctionName(params)` as the heading (use the `name` and `params` fields).
- For `* **Parameters:**`: use the `parameters` array from the JSON (one entry per param, name + description). Write `None` if the array is empty or absent.
- For `* **Returns:**`: use the `returns` field.
- For `* **Error states:**`: use the `error_states` field. Omit this bullet entirely if the value is "None", empty, or absent.
- If the same function name appears more than once, deduplicate — keep the entry with more detail (more parameters or longer description).

=== CRITICAL INSTRUCTIONS ===
- Output ONLY the `### ...` function entries. Do NOT write a `## Main functions` section header.
- Do NOT write YAML frontmatter, ## Overview, ## Usage example, or any other section.
- ALL data must come from the JSON provided above. Do NOT invent functions.
- MDX COMPATIBILITY: Wrap `<`, `>`, `<=`, `>=`, `{{{{`, `}}}}` in backticks.
- NO filler text, greetings, or sign-offs.
- NO emojis or unicode symbols.
- IMPORTANT: Never repeat the same function entry more than once.
"""


def build_events_prompt(
    comp_name: str,
    display_filepath: str,
    events_json: str,
) -> str:
    """
    Pass 1c — format `## Events & listeners` from JSON.
    Output ONLY the ## Events & listeners section.
    """
    return f"""You are an expert technical writer for Don't Starve Together (DST) modding documentation.

You are formatting the `## Events & listeners` section for the component "{comp_name}" from file {display_filepath}.

=== SKILLS ===
{combine_skills("analyst_merge")}

=== EVENTS (pre-extracted) ===
{events_json}

=== OUTPUT INSTRUCTIONS ===

Format the EVENTS JSON into the `## Events & listeners` section:
- Under `**Listens to:**`, list each entry from the `listens_to` array as: `- \`event_name\` — description`
- Under `**Pushes:**`, list each entry from the `pushes` array as: `- \`event_name\` — description`
- If both `listens_to` and `pushes` arrays are empty, write exactly:

```
## Events & listeners

None.
```

=== CRITICAL INSTRUCTIONS ===
- Output ONLY the `## Events & listeners` section.
- Do NOT write YAML frontmatter, ## Overview, ## Main functions, or any other section.
- ALL data must come from the JSON provided above. Do NOT invent events.
- MDX COMPATIBILITY: Wrap `<`, `>`, `<=`, `>=`, `{{{{`, `}}}}` in backticks.
- NO filler text, greetings, or sign-offs.
- NO emojis or unicode symbols.
- IMPORTANT: Never repeat the same event entry more than once.
"""


def build_prose_prompt(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    presynthesis: "PreSynthesisResult",
    function_names: list[str],
    *,
    file_tree: str = "",
    connected_section: str = "",
    connected_content: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
    sidebar_position: int = 10,
    source_hash: str = "",
) -> str:
    """
    Pass 2 — write YAML frontmatter + ## Overview + ## Usage example.
    Output stops after ## Usage example — structured sections are assembled separately.
    """
    # Partial descriptions — numbered list
    descs_section = "\n".join(
        f"{i}. {d}" for i, d in enumerate(presynthesis.partial_descriptions, 1)
    ) or "No descriptions available."

    # Function names — flat list
    fn_names_list = "\n".join(f"- {name}" for name in (function_names or [])) or "No functions found."

    # Brief game_tags and external_deps for overview context
    game_tags_json = json.dumps(presynthesis.game_tags, ensure_ascii=False)
    external_deps_json = json.dumps(presynthesis.external_deps, ensure_ascii=False)

    return f"""You are an expert technical writer for Don't Starve Together (DST) modding documentation.

You are writing the document header for the component "{comp_name}" from file {display_filepath}.
Your task: write ONLY the YAML frontmatter, title heading, version line, ## Overview, and ## Usage example.
Stop after ## Usage example. Do NOT write ## Dependencies & tags or any section below it.

=== SKILLS ===
{combine_skills("analyst_merge")}

=== CONTEXT ===

1. PROJECT FILE TREE
{file_tree}

2. TARGET FILE: {display_filepath}

3. CONNECTED FILES AND FUNCTIONS
   {connected_section if connected_section else "No external references found."}

4. CONNECTED FILES — EXTRACTED SOURCE CODE
   {connected_content if connected_content else "No function source code available."}

=== PARTIAL DESCRIPTIONS (one per chunk) ===
Synthesize these into a single description sentence for the YAML frontmatter.
{descs_section}

=== ALL FUNCTION NAMES ===
Use this list to inform the Overview and Usage example. Do not document each function here.
{fn_names_list}

=== GAME TAGS (brief — for overview context) ===
{game_tags_json}

=== EXTERNAL DEPENDENCIES (brief — for overview context) ===
{external_deps_json}

=== OUTPUT INSTRUCTIONS ===

Produce ONLY the document top in this exact order:

1. YAML frontmatter — copy the pre-filled values exactly, then write `description`, `tags`, and `system_scope`:

---
id: {comp_name}
title: {comp_title}
description: <WRITE: one sentence synthesized from the partial descriptions above>
tags: <WRITE: 2-5 lowercase tags categorizing this component for docs search. Choose domain terms (e.g. [actions, combat, player]). Do NOT list game entity tags. Maximum 5 entries.>
sidebar_position: {sidebar_position}

last_updated: {today_date}
build_version: {version}
change_status: stable
category_type: {category_type}
source_hash: {source_hash}
system_scope: <REVIEW hint {presynthesis.system_scope} — set the most accurate value from the allowed list based on the Overview you are writing>
---

2. Title heading:
# {comp_title}

3. Version line:
> Based on game build **{version}** | Last updated: {today_date}

4. ## Overview — comprehensive summary of the entire component (what it does, when it is used, key behaviors).

5. ## Usage example — 5-15 lines of Lua code demonstrating typical usage of this component.

=== CRITICAL INSTRUCTIONS ===
- Output ONLY the 5 elements above (YAML + title + version line + ## Overview + ## Usage example).
- Stop immediately after ## Usage example. Do NOT write ## Dependencies & tags or any section below it.
- Write YAML tags freely (2-5 doc-category keywords). Review the system_scope hint and set the most accurate value.
- Output ONLY valid Markdown starting with `---`.
- Generate exactly ONE frontmatter block. No extra `---` dividers in the body.
- ALL data must come from the pre-extracted sections above. Do NOT invent APIs.
- MDX COMPATIBILITY: Wrap `<`, `>`, `<=`, `>=`, `{{{{`, `}}}}` in backticks.
- NO code fences around the output.
- NO filler text, greetings, or sign-offs.
- NO emojis or unicode symbols.
- IMPORTANT: Never repeat the same line or bullet point more than once.
"""


# ── Legacy merge prompt (kept for hierarchical/rolling backward compat) ──


def _build_merge_prompt_legacy(
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    chunk_results: list[str],
    source_hash: str = "",
    *,
    file_tree: str = "",
    connected_section: str = "",
    connected_content: str = "",
    today_date: str = "",
    version: str = "",
    category_type: str = "",
    sidebar_position: int = 10,
    input_label: str = "CHUNK",
) -> str:
    """
    Legacy text-based merge prompt — used by hierarchical_merge() and rolling_merge_to_one().
    NOT used in the JSON pipeline.
    """
    merged_chunks = ""
    for i, result in enumerate(chunk_results, 1):
        merged_chunks += f"\n--- {input_label} {i}/{len(chunk_results)} ANALYSIS ---\n{result}\n"

    desc_line = (
        f"You have previously analyzed a large Lua source file in {len(chunk_results)} separate chunks."
        if input_label == "CHUNK" else
        f"You have previously analyzed a large Lua source file. Below are {len(chunk_results)} intermediate group analyses."
    )

    return f"""You are an expert technical writer for Don't Starve Together (DST) modding documentation.

{desc_line}
Below are the analysis results from each portion. Your task is to MERGE them into ONE coherent, complete API reference document.

=== CONTEXT ===

1. PROJECT FILE TREE
{file_tree}

2. TARGET FILE: {display_filepath}

3. CONNECTED FILES AND FUNCTIONS
   {connected_section if connected_section else "No external references found."}

4. CONNECTED FILES — EXTRACTED SOURCE CODE
   {connected_content if connected_content else "No function source code available."}

=== SKILLS ===
{combine_skills("analyst_merge_legacy")}

=== CHUNK ANALYSIS RESULTS ===
{merged_chunks}

=== MERGE INSTRUCTIONS ===

Combine all chunk analyses into a single, well-organized document following the EXACT Markdown structure below.
The output MUST start with the YAML frontmatter block (the first `---` line).

RULES:
- Deduplicate any functions or properties that appear in multiple chunks.
- If the same function is described differently across chunks, prefer the chunk that contains the COMPLETE function body (more parameters/return info wins).
- Organize functions logically (constructor-related first, then core API, then helpers).
- Merge all events, dependencies, and tags into their respective sections.
- Write a comprehensive Overview that summarizes the ENTIRE component, not just one chunk.
- Write a Usage example that demonstrates the most important functions.

---
id: {comp_name}
title: {comp_title}
description:
tags: []
sidebar_position: {sidebar_position}

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
## Usage example
## Dependencies & tags
## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
## Main functions
## Events & listeners

=== CRITICAL INSTRUCTIONS ===
- REQUIRED SECTION ORDER: ## Overview -> ## Usage example -> ## Dependencies & tags -> ## Properties -> ## Main functions -> ## Events & listeners.
- Output ONLY valid Markdown starting with `---`.
- Generate exactly ONE frontmatter block.
- ALL content must come from the chunk analyses above. Do NOT invent APIs.
- MDX COMPATIBILITY: Wrap `<`, `>`, `<=`, `>=`, `{{{{`, `}}}}` in backticks.
- NO code fences around the output.
- NO filler text, greetings, or sign-offs.
- NO emojis or unicode symbols.
- IMPORTANT: Never repeat the same line or bullet point more than once.
"""
