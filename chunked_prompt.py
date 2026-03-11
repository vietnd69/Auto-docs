"""
Module chứa prompt templates cho xử lý file Lua dài (chunked processing).
3 templates:
  - build_chunk_prompt():  prompt cho mỗi chunk (phân tích từng phần)
  - build_merge_prompt():  prompt tổng hợp / merge kết quả
  - build_single_prompt(): re-export prompt cũ cho file ngắn
"""

from prompt import build_prompt as build_single_prompt  # noqa: F401


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
    LLM sẽ chỉ phân tích chunk này và trả về kết quả trung gian
    (danh sách functions, properties, events) — KHÔNG có YAML frontmatter.
    """
    return f"""You are an expert technical writer and a veteran mod developer for the game Don't Starve Together (DST).
You are analyzing CHUNK {chunk_index} of {total_chunks} from the Lua source file: {display_filepath}

This is NOT the full file. You are only seeing a portion of the code.
Your task is to extract and document ALL functions, properties, and events found in THIS CHUNK ONLY.

=== CONTEXT ===

1. PROJECT FILE TREE
   The following is the directory structure of the DST Lua codebase.
   Use it to understand how the project is organized and where related files are located.

{file_tree}

2. TARGET FILE: {display_filepath} (chunk {chunk_index}/{total_chunks})

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
   - DST uses an Entity Component System (ECS). Components are attached to entities via `inst:AddComponent("name")`.
   - `self.inst` refers to the entity instance that owns this component.
   - The constructor is defined as `Class(function(self, inst) ... end)`, NOT a traditional `_ctor` method.
   - `inst:ListenForEvent(event, fn)` registers event listeners; `inst:PushEvent(event, data)` fires events.
   - Tags are added/removed via `inst:AddTag("tag")` / `inst:RemoveTag("tag")` and checked with `inst:HasTag("tag")`.
   - `self.inst.replica.X` refers to the network-replicated version of a component (client-server sync).

=== OUTPUT FORMAT ===

Produce a structured analysis of this chunk using the EXACT format below.
Do NOT produce a complete document. Do NOT include YAML frontmatter.

## Constructor analysis
Describe what the constructor initializes. List all `self.X = value` assignments as properties. (Write "None in this chunk" if not present)

## Functions found
For each function:
### `FunctionName(params)`
* **Description:** What does this function do?
* **Parameters:** Explain each argument.
* **Returns:** What does it return, if anything?
* **Error states:** Edge cases or nil returns (omit if none).
(Write "None in this chunk" if not present)

## Events found
- **Listens to:** event_name — description
- **Pushes:** event_name — description
(Write "None in this chunk" if not present)

## Dependencies found
- Component name — how it's used
(Write "None in this chunk" if not present)

## Tags found
- tag_name — add/remove/check
(Write "None in this chunk" if not present)

=== CRITICAL INSTRUCTIONS ===
- INCOMPLETE BLOCKS: If a function or block appears to be cut off at the beginning or end of this chunk, note it as "INCOMPLETE — continues from/to adjacent chunk" and document what is visible.
- LENGTH: Be thorough but concise — you will have a chance to expand in the merge step.
- Only document what is ACTUALLY in this chunk. Do NOT invent or assume content from other chunks.
- Keep descriptions concise but accurate.
- Use sentence case for headings.
- Wrap expressions with `<`, `>`, `<=`, `>=`, `{{`, `}}` in backticks.
- Do NOT wrap output in code fences.
- Do NOT include greetings, sign-offs, or meta-commentary.
- IMPORTANT: Never repeat the same line or bullet point more than once. If you find yourself repeating, stop and move to the next item.

=== SOURCE CODE (CHUNK {chunk_index}/{total_chunks}) ===
{chunk_code}
"""


def build_merge_prompt(
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
    Tạo prompt tổng hợp — merge nhiều kết quả chunk thành 1 tài liệu hoàn chỉnh.
    """
    # Gộp tất cả chunk results có đánh số
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
   - DST uses an Entity Component System (ECS). Components are attached to entities via `inst:AddComponent("name")`.
   - `self.inst` refers to the entity instance that owns this component.
   - The constructor is defined as `Class(function(self, inst) ... end)`, NOT a traditional `_ctor` method.
   - `inst:ListenForEvent(event, fn)` registers event listeners; `inst:PushEvent(event, data)` fires events.
   - Tags are added/removed via `inst:AddTag("tag")` / `inst:RemoveTag("tag")` and checked with `inst:HasTag("tag")`.
   - `self.inst.replica.X` refers to the network-replicated version of a component (client-server sync).

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

YAML FRONTMATTER RULES:
- `description`: A real, single English sentence summarizing what this component does.
- `tags`: 2-5 lowercase tags for categorization.
- `last_updated`: Use exactly `{today_date}`.
- `system_scope`: Choose ONE: `world`, `player`, `entity`, `ui`, `audio`, `combat`, `environment`, `inventory`, `crafting`, `network`, `brain`, `locomotion`, `physics`, or `fx`. Pick the MOST SPECIFIC scope. If the component primarily manages a player's state, use `player`. If it modifies a generic entity, use `entity`.
- Do NOT leave any `[]`, `<>`, or "automatically generated" in the YAML.

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
Provide a clear, concise explanation of what this component does within the game's Entity Component System.

## Usage example
Provide a short (5-15 lines) Lua code snippet demonstrating typical usage.

## Dependencies & tags
**Components used:** List all components referenced across all chunks.
**Tags:** List all tags found across all chunks.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|

## Main functions
Document all functions found across all chunks. Skip trivial getters/setters.
For each function:
### `FunctionName(params)`
* **Description:** ...
* **Parameters:** ...
* **Returns:** ...

## Events & listeners
Merge all events from all chunks.

=== CRITICAL INSTRUCTIONS ===
- REQUIRED SECTION ORDER: The output MUST strictly follow this exact sequence of sections: `## Overview` -> `## Usage example` -> `## Dependencies & tags` -> `## Properties` -> `## Main functions` -> `## Events & listeners`. Do NOT omit, reorder, or rename these sections.
- Output ONLY valid Markdown starting with `---`.
- Generate exactly ONE frontmatter block. No extra `---` dividers in the body.
- ALL content must come from the chunk analyses above. Do NOT invent APIs.
- HEADING STYLE: Sentence case.
- MDX COMPATIBILITY: Wrap `<`, `>`, `<=`, `>=`, `{{`, `}}` in backticks.
- NO code fences around the output.
- NO filler text, greetings, or sign-offs.
- NO emojis or unicode symbols.
- IMPORTANT: Never repeat the same line or bullet point more than once. If you find yourself repeating, stop and move to the next item.
"""
