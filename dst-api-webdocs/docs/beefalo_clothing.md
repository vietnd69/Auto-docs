---
id: beefalo_clothing
title: Beefalo Clothing
description: Defines skin configuration data for beefalo body part customizations including body, feet, head, horn, and tail variants.
tags: [skins, beefalo, customization]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: 6da6bb3c
system_scope: entity
---

# Beefalo Clothing

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
`beefalo_clothing.lua` is a data configuration file that defines all available skin variants for beefalo body parts. It provides a lookup table (`BEEFALO_CLOTHING`) containing skin definitions for five body part types: body, feet, head, horn, and tail. Each skin entry specifies visual symbol overrides, rarity classification, and release group information. The file also generates two helper lookup tables (`BEEFALO_CLOTHING_SYMBOLS` and `BEEFALO_HIDE_SYMBOLS`) for runtime symbol resolution. This file is referenced by the beefalo skinning system and account items framework.

## Usage example
```lua
local BEEFALO_CLOTHING = require("beefalo_clothing")

-- Access a specific skin definition
local skin = BEEFALO_CLOTHING.beefalo_body_lunar
print(skin.type)           -- "beef_body"
print(skin.rarity)         -- "Distinguished"
print(skin.release_group)  -- 158

-- Check if a symbol is used by any skin
if BEEFALO_CLOTHING_SYMBOLS["beefalo_body"] then
    -- Symbol is overridden by at least one skin
end
```

## Dependencies & tags
**Components used:** None identified. This is a data table file, not a component class.

**Tags:** None identified. Skin tags are defined within the data structure (`skin_tags` field) but not applied via the tag system.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `BEEFALO_CLOTHING` | table | N/A | Main lookup table containing all beefalo skin definitions keyed by skin name. |
| `BEEFALO_CLOTHING_SYMBOLS` | table | N/A | Lookup table mapping symbol names to `true` if they are overridden by any skin. |
| `BEEFALO_HIDE_SYMBOLS` | table | N/A | Lookup table mapping symbol names to `true` if they are hidden by any skin. |

## Main functions
No public functions. This file exposes data tables only. Each skin entry within `BEEFALO_CLOTHING` contains the following fields:

### Skin entry structure
*   **Description:** Each key in `BEEFALO_CLOTHING` represents a unique skin variant with consistent field structure.
*   **Fields:**
    *   `type` (string) - Body part category (`beef_body`, `beef_feet`, `beef_head`, `beef_horn`, `beef_tail`).
    *   `skin_tags` (table) - Array of tag strings for skin filtering (always includes `BEEFALO` plus part-specific tag).
    *   `symbol_overrides` (table) - Array of symbol names that this skin replaces.
    *   `rarity` (string) - Rarity tier (`Complimentary`, `Distinguished`, `Spiffy`, `Elegant`).
    *   `release_group` (number) - Numeric identifier for the content release batch.
    *   `rarity_modifier` (string, optional) - Additional rarity classification (e.g., `Woven`).
    *   `symbol_hides` (table, optional) - Array of symbol names to hide for this skin.

## Events & listeners
Not applicable. This is a static data file with no event system integration.