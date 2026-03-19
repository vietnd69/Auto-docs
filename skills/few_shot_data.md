# Skill: few_shot_data

=== FEW-SHOT EXAMPLE (DATA CONFIG FILE) ===
Use this structure when the source file defines a static data table with no constructor. Mirror this format only — do NOT copy the content.

---
id: sampleregistry
title: SampleRegistry
description: A static registry mapping internal names to platform-specific identifiers for all sample entries.
tags: [config, data]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: root
source_hash: abc123
system_scope: world
---

# SampleRegistry

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`sampleregistry.lua` defines a global array-indexed table `SampleRegistry` containing all entries. It uses a helper function `ENTRY(id, name)` to construct records with both a human-readable name and platform-specific identifiers. This file is a configuration source — it is not a component and does not attach to entities; it is required by other systems that need to resolve entry identifiers.

## Usage example
```lua
local SampleRegistry = require "sampleregistry"
-- Access an entry by its array index
local first = SampleRegistry[1]
print(first.name)        -- "entry_alpha"
print(first.id.platform) -- "1_entry_alpha"
print(first.id.numeric)  -- 1
```

## Dependencies & tags
**Components used:** None identified
**Tags:** None identified

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `SampleRegistry` | table | — | Array-indexed global table of record tables; position corresponds to numeric ID order. |
| `name` | string | — | Internal lowercase underscore-separated name used in code (e.g., `"entry_alpha"`). |
| `id.platform` | string | — | Platform string identifier, formatted as `<id>_<name>`. |
| `id.numeric` | number | — | Platform numeric identifier from the platform definition file. |

## Main functions
### `ENTRY(id, name)`
*   **Description:** Factory function that constructs a registry record with platform-specific IDs.
*   **Parameters:**
    *   `id` (string or number) — base identifier; converted to string for the platform string field and kept as number for the numeric field.
    *   `name` (string) — internal name used in code.
*   **Returns:** `{ name = name, id = { platform = tostring(id).."_"..name, numeric = id } }`
*   **Error states:** None.

## Events & listeners
None.
(End of data config example)