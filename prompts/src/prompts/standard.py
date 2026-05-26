"""
Module containing build_prompt() -- builds the prompt for the LLM.
Does not contain constants, only the template.
"""

from prompts.skills_loader import combine_skills, few_shot_excludes, load_trimmed_writing_guide
from prompts.type_detect import detect_lua_type


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
    Build the complete prompt to send to the LLM for documenting a Lua file.
    All config (version, date, tree...) is passed in via parameters.
    """
    lua_type = detect_lua_type(display_filepath)
    exclude = [*few_shot_excludes(lua_type), "writing_guide"]
    skills_block = combine_skills("analyst", exclude=exclude)
    skills_block += "\n\n=== SKILL: writing_guide ===\n" + load_trimmed_writing_guide(lua_type)

    return f"""=== CONTEXT ===

1. PROJECT FILE TREE
{file_tree}

2. TARGET FILE: {display_filepath}

3. CONNECTED FILES AND FUNCTIONS
{connected_section or "No external references found."}

4. CONNECTED FILES -- EXTRACTED SOURCE CODE
{connected_content or "No function source code available."}

=== TODAY'S DATE: {today_date} ===

=== SKILLS ===
{skills_block}

=== OUTPUT TEMPLATE ===
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

=== SOURCE CODE ===
{lua_code}"""
