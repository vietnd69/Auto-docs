---
name: example-widget
description: Model documentation page for a widget file.
---

<!-- ported from skills/knowledge/few_shot_widget.md -->

## Few-Shot Example: Widget File

HOW TO DETECT: file imports `Widget` from `widgets/widget` and constructor calls
`Widget._ctor(self, "MyWidget")`. Widgets are UI containers, not gameplay components.

Mirror the structure — do NOT copy the content.

```md
---
id: samplewidget
title: SampleWidget
description: A reusable label widget that displays a numeric value with an icon and updates on a periodic timer.
tags: [widget, ui]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: widgets
source_hash: abc123
system_scope: ui
---

# SampleWidget

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`SampleWidget` is a UI widget extending `Widget`. It composes an icon `Image` and a `Text` label, exposes `SetValue()` for parents to push updates, and refreshes itself on a 0.5s tick. Embedded inside HUD screens via `screen:AddChild(SampleWidget())`.

## Usage example
```lua
local SampleWidget = require("widgets/samplewidget")

-- Inside a screen's _ctor:
self.sample = self:AddChild(SampleWidget("images/icon.tex", "icon_default"))
self.sample:SetPosition(0, 100, 0)
self.sample:SetValue(42)
```

## Dependencies & tags
**External dependencies:**
- `widgets/widget` -- Widget base class
- `widgets/text` -- Text child widget
- `widgets/image` -- Image child widget

**Components used:** None — widgets do not interact with ECS components directly.

**Tags:** None.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `icon` | Image | --- | Child image widget; created in `_ctor`. |
| `label` | Text | --- | Child text widget showing the current numeric value. |
| `value` | number | `0` | Current displayed value, updated via SetValue. |
| `update_task` | task | `nil` | Periodic refresh task scheduled in OnGainFocus, cancelled in OnLoseFocus. |

## Main functions
### `_ctor(atlas, tex)`
*   **Description:** Initialises the widget, calls `Widget._ctor(self, "SampleWidget")`, creates icon and label children, applies default styling.
*   **Parameters:**
    - `atlas` -- string atlas path for the icon
    - `tex` -- string texture name within the atlas
*   **Returns:** nil
*   **Error states:** None — Widget._ctor handles nil internally.

### `SetValue(value)`
*   **Description:** Updates `self.value` and rewrites the label text via `self.label:SetString(tostring(value))`.
*   **Parameters:** `value` -- number to display
*   **Returns:** nil
*   **Error states:** Errors if `self.label` is nil (would only occur if widget construction failed; no guard).

### `OnGainFocus()`
*   **Description:** Override of Widget:OnGainFocus(). Starts the periodic refresh task that polls source state every 0.5s.
*   **Parameters:** None
*   **Returns:** nil
*   **Error states:** None.

### `OnLoseFocus()`
*   **Description:** Override of Widget:OnLoseFocus(). Cancels the periodic refresh task to free resources.
*   **Parameters:** None
*   **Returns:** nil
*   **Error states:** None.

## Events & listeners
None — widgets typically expose callbacks via parent screens, not engine events.
```
