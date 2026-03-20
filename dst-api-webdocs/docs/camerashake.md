---
id: camerashake
title: CameraShake
description: A utility class that calculates camera shake offset vectors based on mode, duration, and intensity parameters.
tags: [camera, fx, utility]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: 52f1b726
system_scope: fx
---

# CameraShake

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
`CameraShake` is a utility class that calculates camera shake offset vectors for visual effects during gameplay. It supports three shake modes (`FULL`, `SIDE`, `VERTICAL`) and uses easing functions to smoothly interpolate shake intensity over time. This class is typically instantiated by systems that need to apply camera disturbance effects, such as combat impacts, earthquakes, or environmental events. Unlike entity components, this is a standalone utility that does not attach to game entities.

## Usage example
```lua
local shake = CameraShake(CAMERASHAKE.FULL, 2, 0.05, 1)
local dt = 0.016
local offset = shake:Update(dt)
-- offset is a Vector3 representing the camera displacement
-- Call Update each frame until shake completes
```

## Dependencies & tags
**Components used:** None (standalone utility class)
**Tags:** None identified.

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `mode` | CAMERASHAKE enum | `CAMERASHAKE.FULL` | Determines the shake pattern direction set. |
| `duration` | number | `1` | Total shake duration in seconds. |
| `speed` | number | `0.05` | Controls how quickly the shake cycles through positions. |
| `scale` | number | `1` | Multiplier for shake intensity magnitude. |
| `currentTime` | number | `0` | Tracks elapsed shake time since start. |
| `shakeType` | table | `ShakeDeltas[FULL]` | Internal reference to active shake delta pattern. |

## Main functions
### `CameraShake(mode, duration, speed, scale)`
*   **Description:** Constructor that initializes a new camera shake instance with specified parameters. Automatically calls `StopShaking()` to reset state.
*   **Parameters:** `mode` (CAMERASHAKE enum) - shake pattern type; `duration` (number) - shake duration in seconds; `speed` (number) - cycle speed; `scale` (number) - intensity multiplier.
*   **Returns:** New CameraShake instance.

### `StopShaking()`
*   **Description:** Immediately halts the shake effect and resets all timing values to defaults.
*   **Parameters:** None.
*   **Returns:** Nothing.

### `Update(dt)`
*   **Description:** Calculates the current camera shake offset vector based on elapsed time. Must be called each frame with delta time to get continuous shake offsets.
*   **Parameters:** `dt` (number) - time elapsed since last update in seconds.
*   **Returns:** Vector3 representing the camera displacement offset. Returns early if shake is inactive.
*   **Error states:** Returns early without calculation if `mode` is `nil`, `speed` equals `0`, or `duration` equals `0`. Also stops shaking if `currentTime` exceeds `duration + 2*speed`.

## Events & listeners
Not applicable - this is a standalone utility class with no event system integration.