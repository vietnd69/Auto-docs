"""
Module chua ham build_prompt() -- tao prompt cho LLM.
Khong chua constants, chi chua template.
"""

from prompts.skills_loader import combine_skills

_DATA_CONFIG_DIRS = {"map", "languages", "util"}


def _detect_file_type(display_filepath: str) -> str:
    """Returns 'component' or 'data_config' based on directory path.

    Expects a relative path as produced by main.py (e.g. './map/a.lua',
    './components/combat.lua', './achievements.lua'). Absolute paths are
    unsupported and results are not guaranteed.
    """
    normalized = display_filepath.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    elif normalized.startswith("/"):
        normalized = normalized.lstrip("/")
    parts = normalized.split("/")
    if len(parts) == 1:
        return "data_config"
    if parts[0].lower() in _DATA_CONFIG_DIRS:
        return "data_config"
    return "component"


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
    Tao prompt day du de gui cho LLM tao tai lieu cho mot file Lua.
    Tat ca config (version, date, tree...) duoc truyen vao qua tham so.
    """
    file_type = _detect_file_type(display_filepath)
    exclude = ["few_shot_data"] if file_type == "component" else ["few_shot"]
    skills_block = combine_skills("analyst", exclude=exclude)

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
