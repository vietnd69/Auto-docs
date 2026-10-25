---
name: example-screen
description: Model documentation page for a screen file.
---

<!-- ported from skills/knowledge/few_shot_screen.md -->

## Few-Shot Example: Screen File

HOW TO DETECT: file extends `Screen` via `Class(Screen, ...)`, lives in `screens/` (or root),
and is pushed onto the FrontEnd stack via `TheFrontEnd:PushScreen(MyScreen())`.

Mirror the structure — do NOT copy the content.

```md
---
id: samplescreen
title: SampleScreen
description: Modal popup screen presenting a confirm/cancel choice with keyboard and gamepad navigation.
tags: [screen, ui, modal]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: screens
source_hash: abc123
system_scope: ui
---

# SampleScreen

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SampleScreen` is a modal popup extending `Screen`. It darkens the underlying gameplay, presents a centered card with confirm and cancel buttons, and handles `CONTROL_ACCEPT` / `CONTROL_CANCEL` input. The screen invokes the supplied callback before popping itself off the FrontEnd stack.

## Usage example
```lua
local SampleScreen = require("screens/samplescreen")

local function OnConfirm()
    print("user confirmed")
end

TheFrontEnd:PushScreen(SampleScreen("Are you sure?", OnConfirm))
```

## Dependencies & tags
**External dependencies:**
- `widgets/screen` -- Screen base class
- `widgets/templates` -- StandardButton, StandardDialog factories
- `widgets/text` -- title/body text widgets

**Components used:** None.

**Tags:** None.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `prompt` | string | --- | The prompt text shown in the dialog body. |
| `on_confirm` | function | `nil` | Optional callback invoked when the user accepts. |
| `dialog` | Widget | --- | The StandardDialog child, parent of the buttons and text. |
| `confirm_btn` | Widget | --- | Confirm button child; bound to `OnConfirm`. |
| `cancel_btn` | Widget | --- | Cancel button child; bound to `OnCancel`. |

## Main functions
### `_ctor(prompt, on_confirm)`
*   **Description:** Initialises the screen, calls `Screen._ctor(self, "SampleScreen")`, builds the dialog widget tree, focuses the confirm button, and stores the callback.
*   **Parameters:**
    - `prompt` -- string shown in the dialog body
    - `on_confirm` -- optional function `()` invoked on accept
*   **Returns:** nil
*   **Error states:** None — accepts nil on_confirm.

### `OnControl(control, down)`
*   **Description:** Handles input. ACCEPT triggers `OnConfirm`, CANCEL triggers `OnCancel`. Returns true if the input was handled to suppress further propagation.
*   **Parameters:**
    - `control` -- one of CONTROL_* constants
    - `down` -- boolean (true on press, false on release)
*   **Returns:** boolean — true if handled
*   **Error states:** None.

### `OnConfirm()` (instance method)
*   **Description:** Invokes `self.on_confirm` if set, then pops this screen from the FrontEnd stack via `TheFrontEnd:PopScreen(self)`.
*   **Parameters:** None
*   **Returns:** nil
*   **Error states:** None — guards `on_confirm == nil`.

### `OnCancel()` (instance method)
*   **Description:** Pops this screen without invoking the callback.
*   **Parameters:** None
*   **Returns:** nil
*   **Error states:** None.

## Events & listeners
None — screens consume input via OnControl, not engine event subscriptions.
```
```
