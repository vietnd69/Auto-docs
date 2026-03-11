"""
Module chứa hàm build_update_prompt() — tạo prompt cho LLM dành cho tính năng UPDATE file.
Dựa trên prompt.py gốc nhưng bổ sung logic xử lý cho file Added, Modified, Deleted, Moved.
"""

def build_update_prompt(
    action: str,  # "added", "modified", "deleted", "moved"
    comp_name: str,
    comp_title: str,
    display_filepath: str,
    lua_code: str = "",
    connected_section: str = "",
    connected_content: str = "",
    source_hash: str = "",
    *,
    existing_doc: str = "",
    unified_diff: str = "",
    old_path: str = "",
    new_path: str = "",
    file_tree: str = "",
    today_date: str = "",
    build_version: str = "",
    old_version: str = "",
    category_type: str = "",
    content_changed: bool = True,
) -> str:
    """
    Tạo prompt cho LLM để cập nhật tài liệu cho một file Lua.
    - action "added": giống prompt tạo mới.
    - action "modified": update doc dựa vào unified diff và doc cũ.
    - action "deleted": thêm block deprecation.
    - action "moved": kết hợp đổi tên/path và update doc nếu content_changed.
    """
    
    # 1. Xác định header text & directive dựa trên action
    if action == "deleted":
        action_directive = f"""This file has been DELETED in the new game update (build {build_version}).
Your task is to update the frontmatter to `change_status: deprecated` and add a deprecation notice. 
Do NOT remove or restructure the existing documentation content.
Add the following blockquote exactly as shown immediately after the `## Overview` heading:

> [!WARNING]
> **Deprecated in build {build_version}** — `{display_filepath}` đã bị xóa khỏi codebase.
> Tài liệu này được giữ lại để tham khảo cho các build cũ hơn.
"""
    elif action == "modified":
        action_directive = f"""This file has been MODIFIED in build {build_version}.
Your task is to update the existing documentation intelligently based on the provided UNIFIED DIFF.
Update the frontmatter (`last_updated`, `build_version`, `change_status: updated`, `source_hash`).
For every logical change found in the diff, apply inline change notes exactly matching the stipulated Doc Format rules (e.g., blockquotes for changes, strikethrough for removed elements, inline "*(Added in build ...)*" notes).
Do NOT add a separate `## Changelog` section and do NOT rewrite sections that have not changed."""
    elif action == "moved":
        if content_changed:
            action_directive = f"""This file has been MOVED in build {build_version} from `{old_path}` to `{new_path}` and its content has MODIFIED.
Your task is to update the existing documentation based on the provided UNIFIED DIFF.
Update the frontmatter (`last_updated`, `build_version`, `change_status: moved`, `source_hash`).
Apply inline change notes for every logical change found in the diff, exactly matching the stipulated Doc Format rules.
Do NOT add a separate `## Changelog` section and do NOT rewrite sections that have not changed."""
        else:
            action_directive = f"""This file has been MOVED in build {build_version} from `{old_path}` to `{new_path}` WITHOUT logic changes.
Your task is to ONLY update the frontmatter (`last_updated`, `build_version`, `change_status: moved`, `source_hash`).
Do NOT change the documentation body or add change notes."""
    else:  # "added"
        action_directive = f"""This is a NEW file added in build {build_version}. Generate comprehensive, highly readable API reference documentation from scratch."""

    # 2. Add specific formatting block for changes
    change_formatting_rules = ""
    if action == "modified" or (action == "moved" and content_changed):
        change_formatting_rules = f"""
=== INLINE CHANGE NOTES FORMAT REQUIREMENTS ===
When documenting changes from the UNIFIED DIFF, you must adhere strictly to these formats.

1. Dependencies & tags:
   `new_component` *(Added in build {build_version})*,
   ~~`removed_component`~~ *(Removed in build {build_version})*

2. Properties Table:
   | `newprop` | number | `0` | *(Added in build {build_version})* Description. |
   | ~~`removedprop`~~ | ~~number~~ | ~~`0`~~ | ~~Old description.~~ *(Removed in build {build_version}, replaced by `newprop`)* |

3. Main Functions (Changed):
   ### `FunctionName(param1, param2)`
   > *(Changed in build {build_version})*
   > - `param1`: Old behavior -> New behavior.

4. Main Functions (Added):
   ### `NewFunction(param1)` *(Added in build {build_version})*
   > *(Added in build {build_version})* Reason for adding.

5. Main Functions (Removed):
   ### ~~`RemovedFunction(param1)`~~ *(Removed in build {build_version})*
   > *(Removed in build {build_version})* Reason for removal. Migrate to: `replacement_call()`.

6. Events & Listeners:
   `new_event` — triggers `NewHandler()`. *(Added in build {build_version})*
   ~~`removed_event` — triggers `RemovedHandler()`.~~ *(Removed in build {build_version})*
"""

    # 3. Handle existing documentation context
    existing_doc_section = ""
    if existing_doc and action in ["modified", "moved", "deleted"]:
        existing_doc_section = f"""
=== EXISTING DOCUMENTATION ===
This is the current state of the documentation before the update. 
{existing_doc}
"""

    # 4. Handle unified diff context
    diff_section = ""
    if unified_diff and (action == "modified" or (action == "moved" and content_changed)):
        diff_section = f"""
=== UNIFIED DIFF ===
This diff shows exactly what changed in the Lua source code. Use this to determine exactly what needs updating. lines starting with `+` are additions, `-` are removals.
```diff
{unified_diff}
```
"""

    # 5. Output template structure (excluded for deleted or simple moves to avoid confusion)
    doc_template = ""
    if action not in ["deleted"] and not (action == "moved" and not content_changed):
        doc_template = f"""
# {comp_title}

> Based on game build **{old_version if action in ['modified', 'deleted', 'moved'] else build_version}** | {"Updated on game build **"+build_version+"** | " if action in ['modified', 'moved'] else ("Removed on game build **"+build_version+"** | " if action == 'deleted' else "")}Last updated: {today_date}

## Overview
Provide a clear, concise explanation of what this component does within the game's Entity Component System.

## Usage example
Provide a short (5-15 lines) Lua code snippet demonstrating typical usage.

## Dependencies & tags
**Components used:** List components this script accesses.
**Tags:** List any tags this component adds, removes, or checks.

## Properties
Create a Markdown table of the key public variables/properties initialized in the constructor.

## Main functions
Document the core functional methods.

## Events & listeners
List events this component interacts with.
"""

    return f"""You are an expert technical writer and a veteran mod developer for the game Don't Starve Together (DST).
Your task is to analyze the context provided below and generate or update the API reference documentation.
All documentation text must be written in clear, concise English.

**ACTION CONTEXT**: 
{action_directive}
{change_formatting_rules}

=== CONTEXT ===

1. PROJECT FILE TREE
   The following is the directory structure of the DST Lua codebase.
{file_tree}

2. TARGET FILE
   This is the file you are documenting:
   {display_filepath}

3. CONNECTED FILES AND FUNCTIONS
   {connected_section if connected_section else "No external references found."}

4. CONNECTED FILES — EXTRACTED SOURCE CODE
   {connected_content if connected_content else "No function source code available."}
{existing_doc_section}{diff_section}
=== TODAY'S DATE: {today_date} ===

=== OUTPUT FORMAT ===

Generate documentation following this EXACT Markdown structure. The output MUST start with the YAML frontmatter block.

YAML FRONTMATTER RULES:
- `description`: Single English sentence summarizing what this component does.
- `tags`: Generate 2-5 lowercase tags.
- `last_updated`: Use exactly `{today_date}`.
- `build_version`: Use exactly `{build_version}`.
- `change_status`: Use `new` if added, `updated` if modified, `deprecated` if deleted, `moved` if moved.
- `source_hash`: Use exactly `{source_hash}`. (If deleted, keep existing hash unchanged).

---
id: {comp_name}
title: {comp_title}
description: 
tags: []
sidebar_position: 10

last_updated: {today_date}
build_version: {build_version}
change_status: {"new" if action == "added" else "deprecated" if action == "deleted" else "moved" if action == "moved" else "updated"}
category_type: {category_type}
source_hash: {source_hash}
system_scope: 
---
{doc_template}
=== CRITICAL INSTRUCTIONS ===
{'- REQUIRED SECTION ORDER: ## Overview -> ## Usage example -> ## Dependencies & tags -> ## Properties -> ## Main functions -> ## Events & listeners.' if doc_template else ""}
- Only use valid Markdown. The output must begin with `---`.
- Write only ONE frontmatter block.
- MDX COMPATIBILITY: Wrap any expression containing `<`, `>`, `<=`, `>=`, `{{`, or `}}` in inline code backticks to prevent Docusaurus MDX build failures.
- IMPORTANT: Never repeat the same line or bullet point more than once. If you find yourself repeating, stop and move to the next item.

=== SOURCE CODE ===
{lua_code if lua_code else "(File deleted or not needed due to diff-based modification)"}
"""
