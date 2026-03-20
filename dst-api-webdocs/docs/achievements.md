---
id: achievements
title: Achievements
description: Defines the master list of achievement identifiers and platform-specific IDs for Steam and PSN.
tags: [meta, data, ui, progress]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: 65f75a2b
system_scope: ui
---

# Achievements

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
This module serves as a data registry for game achievements. It defines a global table mapping internal achievement names to platform-specific identifiers for Steam and PlayStation Network. The table is typically required by systems responsible for tracking player progress and displaying UI notifications. It does not contain logic for unlocking achievements, only the definition of their IDs.

## Usage example
```lua
local Achievements = require("achievements")

-- Access the first achievement entry
local entry = Achievements[1]
print(entry.name) 
-- Output: "survive_20"

-- Access platform-specific ID
print(entry.id.steam) 
-- Output: "1_survive_20"
```

## Dependencies & tags
**Components used:** None identified.
**Tags:** None identified.

## Properties
No public properties.

## Main functions
None identified.

## Events & listeners
None identified.