---
id: characterutil
title: Characterutil
description: Provides utility functions for loading character display data including portraits, avatars, titles, and inventory items.
tags: [character, ui, utility]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: ae2b38b5
system_scope: ui
---

# Characterutil

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
`characterutil` is a utility module providing helper functions for loading and processing character-related display data. It handles portrait textures, avatar locations, character titles, morgue death information, and starting inventory item lists. This module is commonly used by UI screens and character selection interfaces to display character information correctly, including support for skinned characters and mod characters.

## Usage example
```lua
local characterutil = require("characterutil")

-- Load a skinned oval portrait into a widget
local widget = ImageWidget()
characterutil.SetSkinnedOvalPortraitTexture(widget, "wilson", "wilson_formal")

-- Get character starting inventory items
local items = characterutil.GetUniquePotentialCharacterStartingInventoryItems("wilson", true)

-- Get character title for display
local title = characterutil.GetCharacterTitle("wilson", "wilson_formal")
```

## Dependencies & tags
**Components used:** None identified. This is a utility module, not an entity component.
**Tags:** None identified.

## Properties
No public properties. This module consists of standalone functions rather than a class with instance properties.

## Main functions
### `SetSkinnedOvalPortraitTexture(image_widget, character, skin)`
*   **Description:** Loads the oval portrait texture for a skinned character into the specified image widget. Checks if the character supports skins and attempts to load the appropriate portrait atlas.
*   **Parameters:** `image_widget` (ImageWidget) - the widget to set the texture on. `character` (string) - character identifier like `wilson`. `skin` (string) - skin identifier like `wilson_formal`.
*   **Returns:** `boolean` - `true` if the oval portrait atlas was found and loaded, `false` otherwise.
*   **Error states:** Returns `false` if the portrait file does not exist. Prints an error message to the console if the portrait name is invalid.

### `SetOvalPortraitTexture(image_widget, character)`
*   **Description:** Loads the oval portrait texture for a character using the default skin. Wraps `SetSkinnedOvalPortraitTexture` with the default skin suffix.
*   **Parameters:** `image_widget` (ImageWidget) - the widget to set the texture on. `character` (string) - character identifier like `wilson`.
*   **Returns:** `boolean` - `true` if the oval portrait atlas was found, `false` otherwise.
*   **Error states:** Returns `false` for non-skinnable characters.

### `SetHeroNameTexture_Grey(image_widget, character)`
*   **Description:** Loads the grey hero name texture for the specified character into the image widget.
*   **Parameters:** `image_widget` (ImageWidget) - the widget to set the texture on. `character` (string) - character identifier.
*   **Returns:** `boolean` - `true` if the hero atlas was found, `nil` otherwise.
*   **Error states:** May still fail if the texture file does not exist even if the atlas path resolves.

### `SetHeroNameTexture_Gold(image_widget, character)`
*   **Description:** Loads the gold hero name texture for the specified character. Falls back to grey texture if gold version is not available (common for mod characters).
*   **Parameters:** `image_widget` (ImageWidget) - the widget to set the texture on. `character` (string) - character identifier.
*   **Returns:** `boolean` - `true` if the gold hero atlas was found, result of grey fallback otherwise.
*   **Error states:** Falls back to `SetHeroNameTexture_Grey` if gold texture is not found.

### `GetCharacterAvatarTextureLocation(character)`
*   **Description:** Returns the atlas path and texture name for a character's avatar image. Handles normal characters, mod characters, and edge cases like `random` or unknown identifiers.
*   **Parameters:** `character` (string) - character identifier.
*   **Returns:** `string, string` - atlas location path and texture filename.
*   **Error states:** Returns default `mod` or `unknown` avatar paths for unrecognized character names.

### `GetCharacterTitle(character, skin)`
*   **Description:** Retrieves the display title for a character. Returns the skin name if a skin is provided, otherwise returns the base character title from `STRINGS.CHARACTER_TITLES`.
*   **Parameters:** `character` (string) - character identifier. `skin` (string, optional) - skin identifier.
*   **Returns:** `string` - the character title for display.
*   **Error states:** Returns `nil` if the character is not found in `STRINGS.CHARACTER_TITLES` and no skin is provided.

### `GetKilledByFromMorgueRow(data)`
*   **Description:** Processes morgue death data to return a formatted killer name. Handles special cases like PK names, nil values, unknown deaths, and mob name variations.
*   **Parameters:** `data` (table) - morgue row data containing `killed_by`, `character`, `pk`, and `morgue_random` fields.
*   **Returns:** `string` - formatted killer name with proper capitalization.
*   **Error states:** Returns empty string if `killed_by` is `nil`. Applies special remapping for certain death causes like `darkness` or `shenanigans`.

### `GetUniquePotentialCharacterStartingInventoryItems(character, with_bonus_items)`
*   **Description:** Retrieves the list of starting inventory items for a character based on game mode and season settings. Removes duplicate items and optionally includes seasonal bonus items.
*   **Parameters:** `character` (string) - character identifier. `with_bonus_items` (boolean) - whether to include seasonal and extra starting items.
*   **Returns:** `table` - array of item prefab names without duplicates.
*   **Error states:** Returns empty table if character has no defined starting items in `TUNING.GAMEMODE_STARTING_ITEMS`.

## Events & listeners
Not applicable. This utility module does not register event listeners or push events.