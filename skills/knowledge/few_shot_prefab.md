---
name: few_shot_prefab
description: Prefab file few-shot example — expected output for entity prefab definitions returning Prefab(...)
inject_into: [analyst, analyst_chunk]
---

## Few-Shot Example: Prefab File

HOW TO DETECT: top-level `return Prefab(name, fn, assets, deps)` (or wrapper macro). The file
defines a spawnable entity, attaching components inside `fn()` and (on master) `master_postinit`.

Mirror the structure — do NOT copy the content.

```md
---
id: sampleprefab
title: SamplePrefab
description: Spawnable creature entity that combines combat, inventory, and locomotor components, attached to SGSample stategraph and samplebrain.
tags: [prefab, creature, entity]
sidebar_position: 10

last_updated: 2025-01-01
build_version: 000000
change_status: stable
category_type: prefabs
source_hash: abc123
system_scope: entity
---

# SamplePrefab

> Based on game build **000000** | Last updated: 2025-01-01

## Overview
`sampleprefab.lua` registers a spawnable creature entity. The prefab's `fn()` constructor builds the physics body and attaches client-side components; `master_postinit` runs only on the server and attaches gameplay components (combat, health, inventory). The prefab is referenced by its name `"sampleprefab"` and instantiated with `SpawnPrefab("sampleprefab")`.

## Usage example
```lua
-- Spawn at world origin:
local inst = SpawnPrefab("sampleprefab")
inst.Transform:SetPosition(0, 0, 0)

-- Reference assets at load time:
local assets = {
    Asset("ANIM", "anim/sampleprefab.zip"),
    Asset("SOUND", "sound/sampleprefab.fsb"),
}
```

## Dependencies & tags
**External dependencies:**
- `stategraphs/SGsample` -- attached via `inst:SetStateGraph("SGsample")`
- `brains/samplebrain` -- attached via `inst:SetBrain(brain)`
- `prefabs/skinutils` -- skin-handling helpers

**Components used:**
- `combat` -- attack damage and target tracking
- `health` -- HP and death handling
- `inventory` -- carried items
- `locomotor` -- movement
- `eater` -- consume food items

**Tags:**
- `monster` -- added in fn() for combat targeting
- `character` -- added in fn() for AI selection

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `assets` | table | --- | Array of `Asset(...)` entries listing animation, sound, and texture files loaded with this prefab. |
| `prefabs` | table | `{...}` | Array of dependent prefab names (e.g., spawned drops) that must be loaded with this entity. |
| `TUNING.SAMPLE_HEALTH` | constant | `200` | Max HP applied to `health` component in master_postinit. |
| `TUNING.SAMPLE_DAMAGE` | constant | `25` | Damage value applied to `combat` component. |

## Main functions
### `fn()`
*   **Description:** Client-side prefab constructor. Creates the entity, builds physics, attaches AnimState, sets default animation, and adds tags. Returns `inst` so the framework can branch into master_postinit on the server.
*   **Parameters:** None
*   **Returns:** entity instance
*   **Error states:** None — runs on every host (client and server).

### `master_postinit(inst)`
*   **Description:** Server-only initialisation. Attaches gameplay components, sets stats from TUNING, attaches stategraph and brain. Skipped on clients (master_postinit is only invoked when `TheWorld.ismastersim` is true).
*   **Parameters:** `inst` -- entity returned from fn()
*   **Returns:** nil
*   **Error states:** Errors if `inst` is nil (engine guarantees non-nil; included for completeness).

## Events & listeners
- **Listens to (set up in master_postinit):** `attacked` -- triggers brain re-evaluation by clearing target.
- **Listens to:** `death` -- spawns loot via `inst.components.lootdropper:DropLoot()`.
```
```