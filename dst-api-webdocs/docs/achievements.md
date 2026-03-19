---
id: achievements
title: Achievements
description: Defines achievement identifiers and mapping data for Steam and PSN platforms.
tags: [data, platform, meta]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: a1b2c3d4
system_scope: world
---

# Achievements

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
The `achievements` module provides a centralized lookup table for defining achievement identifiers. It maps internal achievement names to platform-specific IDs required for Steam and PlayStation Network integration. This script is not an Entity Component System component but a global data reference used by the game's statistics and UI systems to track player progress across different services.

## Usage example
```lua
local Achievements = require("achievements")
-- Access the first achievement entry
local achievement = Achievements[1]
print(achievement.name)
print(achievement.id.steam)
print(achievement.id.psn)
```

## Dependencies & tags
**Components used:** None identified.
**Tags:** None identified.

## Properties
The module returns a table where each entry contains the following structure:

| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `name` | string | `nil` | Internal code name used to refer to this achievement in logic. |
| `id` | table | `nil` | Contains platform-specific identifiers for `steam` and `psn`. |

## Main functions
None identified. This module exposes data tables rather than functional methods. The internal helper function `ACHIEVEMENT` is local and used only during module initialization.

## Events & listeners
None identified.