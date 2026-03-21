---
id: constants
title: Constants
description: This module defines global constants for game mechanics, rendering, input, and content classification (including tiles, events, colors, and tech tiers), and provides helper functions to query active event states and generate tile maps.
tags: [core, globals, events, configuration, utilities]
sidebar_position: 10

last_updated: 2026-03-21
build_version: 714014
change_status: stable
category_type: root
source_hash: 707f1cbb
system_scope: global
---

# Constants

> Based on game build **714014** | Last updated: 2026-03-21

## Overview
The `constants` module serves as the central repository for global enumerations, configuration tables, and utility functions used throughout the Don't Starve Together codebase. It defines essential data structures for ground tiles, special and festival events, crafting tabs, seasons, rendering colors, and input controls. Additionally, it provides logic to query the current state of special events, festival seasons, and tournament modes, ensuring consistent access to game configuration data across client and server environments. This file is frequently required by other core modules such as `techtree`, `clothing`, and `prefabskins` to populate their respective lookup tables.

## Usage example
```lua
local CONSTANTS = require("constants")

-- Access a ground tile ID
local dirt_id = GROUND.DIRT

-- Check if a specific special event is active
if CONSTANTS.IsSpecialEventActive("hallowed_nights") then
    print("Hallowed Nights is currently active.")
end

-- Convert RGB integers to a normalized color table
local white_color = CONSTANTS.RGB(255, 255, 255)
-- Result: {1, 1, 1, 1}

-- Get the active festival skin tag
local skin_tag = CONSTANTS.GetSpecialEventSkinTag()
```

## Dependencies & tags

**External dependencies:**
- `util` -- Required at the start to load global utilities.
- `techtree` -- Required locally for TechTree module.
- `prefabskins` -- Required to populate skin lookup tables.
- `clothing` -- Required to populate CLOTHING global table.
- `beefalo_clothing` -- Required to populate BEEFALO_CLOTHING global table.
- `misc_items` -- Required to populate MISC_ITEMS global table.
- `emote_items` -- Required to populate EMOTE_ITEMS global table.
- `item_blacklist` -- Required to populate item visibility constraints.
- `entitlementlookups` -- Required to populate ENTITLEMENTLOOKUPS global table.

**Components used:**
None

**Tags:**
None

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|

## Main functions

### `GetWorldTileMap()`
* **Description:** Iterates through WORLD_TILES and GROUND tables to construct a unified map of tile names to IDs.
* **Parameters:** None
* **Returns:** table (world_tile_map)

### `IsSpecialEventActive(event)`
* **Description:** Checks if a specific special event is currently active.
* **Parameters:**
  - `event` -- string, the special event identifier to check
* **Returns:** boolean

### `IsAnySpecialEventActive()`
* **Description:** Checks if any special event is currently active.
* **Parameters:** None
* **Returns:** boolean

### `GetActiveSpecialEventCount()`
* **Description:** Returns the count of active special events.
* **Parameters:** None
* **Returns:** number

### `GetFirstActiveSpecialEvent()`
* **Description:** Returns the first active special event identifier.
* **Returns:** string or nil

### `GetAllActiveEvents(special_event, extra_events)`
* **Description:** Aggregates all active special and extra events into a single table.
* **Parameters:**
  - `special_event` -- string or nil, the primary special event identifier
  - `extra_events` -- table or nil, additional active events
* **Returns:** table

### `IsAny_YearOfThe_EventActive()`
* **Description:** Checks if any Year of the Creature event is active.
* **Parameters:** None
* **Returns:** boolean

### `GetSpecialEventSkinTag()`
* **Description:** Returns the skin tag associated with the current special event.
* **Parameters:** None
* **Returns:** string or nil

### `IsFestivalEventActive(event)`
* **Description:** Checks if a specific festival event is currently active.
* **Parameters:**
  - `event` -- string, the festival event identifier to check
* **Returns:** boolean

### `IsPreviousFestivalEvent(event)`
* **Description:** Checks if the event is a previous festival event.
* **Parameters:**
  - `event` -- string, the festival event identifier to check
* **Returns:** boolean

### `IsAnyFestivalEventActive()`
* **Description:** Checks if any festival event is currently active.
* **Parameters:** None
* **Returns:** boolean

### `GetFestivalEventSkinTag()`
* **Description:** Returns the skin tag associated with the current festival event.
* **Parameters:** None
* **Returns:** string or nil

### `GetFestivalEventInfo()`
* **Description:** Returns the info table for the current festival event.
* **Parameters:** None
* **Returns:** table or nil

### `GetFestivalEventSeasons(festival)`
* **Description:** Returns the latest season number for a festival event.
* **Parameters:**
  - `festival` -- string, the festival event identifier
* **Returns:** number
* **Error states:** Returns 0 if festival info is nil

### `GetActiveFestivalEventServerName()`
* **Description:** Returns the server name for the active festival event.
* **Parameters:** None
* **Returns:** string

### `GetActiveFestivalProductName()`
* **Description:** Returns the product name for the active festival event.
* **Parameters:** None
* **Returns:** string

### `GetFestivalEventServerName(festival, season)`
* **Description:** Returns the server name for a specific festival event and season.
* **Parameters:**
  - `festival` -- string, the festival event identifier
  - `season` -- number, the season number
* **Returns:** string
* **Error states:** Returns empty string if info is nil

### `GetActiveFestivalEventStatsFilePrefix()`
* **Description:** Returns the stats file prefix for the active festival event.
* **Parameters:** None
* **Returns:** string
* **Error states:** Defaults to 'stats' if nil

### `GetActiveFestivalEventAchievementStrings()`
* **Description:** Returns the achievement strings table for the active festival event.
* **Parameters:** None
* **Returns:** table or nil

### `Server_IsTournamentActive()`
* **Description:** Checks if the tournament mode is active on the server.
* **Parameters:** None
* **Returns:** boolean
* **Error states:** Always returns false in this implementation

### `Client_IsTournamentActive()`
* **Description:** Checks if the tournament mode is active on the client.
* **Parameters:** None
* **Returns:** boolean

### `RGB(r, g, b)`
* **Description:** Converts integer RGB values to a normalized color table with alpha set to 1.
* **Parameters:**
  - `r` -- number, red channel value (0-255)
  - `g` -- number, green channel value (0-255)
  - `b` -- number, blue channel value (0-255)
* **Returns:** table, normalized color array {r/255, g/255, b/255, 1}

## Events & listeners

**Listens to:**
None

**Pushes:**
None