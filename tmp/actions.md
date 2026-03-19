---
id: actions
title: Actions
description: Defines the in-game action system for Don't Starve Together, including action constructors, range checks, and comprehensive built-in action handlers for interaction, movement, crafting, and specialized gameplay mechanics.
tags: [actions, player, interaction, game mechanics, movement]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
system_scope: player
---

# Actions

> Based on game build **714014** | Last updated: 2026-03-20

## Overview

The `actions.lua` file implements Don't Starve Together's centralized action system, forming the core infrastructure for all player and entity interactions. It provides an `Action` class for defining new gameplay actions, numerous helper functions for range validation and tile placement, and a complete registry of predefined action handlers. These actions govern movement (rowing, steering, boarding), interaction (opening containers, inspecting, reading, cooking, farming), specialized systems (ocean fishing, boat operations, Quagmire mechanics, YOTB sewing/contest), and utility operations (teleporting, healing, crafting, upgrading). Each action includes validation logic, display string generation, and integration with ECS components such as `inventory`, `combat`, `fueled`, and custom systems like `spidermutator` and `ghostlybond`. The system also supports map-based actions, context-sensitive remapping (e.g., wormholes), and client-server synchronization via replicated components.

## Usage example

```lua
-- Define a custom action
local custom_action = Action({
    fn = function(act)
        local doer = act.doer
        local target = act.target
        if target ~= nil and doer:IsNear(target, 3) then
            print("Custom action performed on", target.prefab)
            return true
        end
        return false, "TOOFAR"
    end,
    distance = 3,
    strfn = function(act) return "CUSTOM" end
})

-- Add it to the global ACTIONS table
ACTIONS.MY_CUSTOM = custom_action

-- Use an existing action (drop item)
local doer = ThePlayer
local item = doer.components.inventory:GetActiveItem()
if item ~= nil then
    doer.components.inventory:DropItem(item)
end
```

## Dependencies & tags
**External dependencies:**
- `class` -- defines the `Action` class constructor
- `bufferedaction` -- used for remap actions and action context data
- `debugtools` -- used for debug stack warnings
- `TheWorld` -- accessed via `TheWorld.Map` for world geometry and ocean checks
- `TheSim` -- used for entity search (e.g., wormhole detection)
- `TheNet` -- used to check PVP settings
- `ThePlayer` -- referenced via external modules (attuner, skilltreeupdater)
- `TheFocalPoint` -- used for UI sound feedback
- `TUNING` -- used for tuning constants in range, cooking, and special logic
- `STRINGS` and `GetString` -- used for localized action and error strings
- `ACTIONS` and `ACTIONS_MAP_REMAP` -- global tables for action definitions and map remapping
- `AllRecipes`, `CONSTRUCTION_PLANS`, `TROPHYSCALE_TYPES`, `prefabs/weed_defs` -- used for recipe lookups, construction plans, trophy types, and weed spawning
- `spawnprefab`, `FunctionOrValue`, `distsq`, `FindVirtualOceanEntity`, `GetRandomWithVariance`, `GetTime`, `EntityScript.is_instance`, `FindEntity`, `LaunchAt`, `vecutil.Vector3`, `TILE_SCALE`, `DEGREES`, `TWOPI` -- core utilities used across action handlers

**Components used:**
- `activatable` -- used in `ACTIVATE` to check and perform activation via `CanActivate` and `DoActivate`
- `anchor` -- used in `RAISE_ANCHOR` and `LOWER_ANCHOR` to manipulate anchor state
- `aoespell` -- used in `CASTAOE` to validate and cast area-of-effect spells
- `appraisable` -- used in `APPRaise` actions to appraise items
- `attunable` -- used in `ATTUNE` to link items to players
- `balloonmaker` -- used in `MAKEBALLOON` to spawn balloons
- `balloonmaker`, `sanity` -- used together for sanity deduction when spawning balloons
- `bathingpool` -- used in `SOAKIN` to allow entering pools
- `batteryuser` -- used in `CHARGE_FROM` to charge from batteries
- `beard`, `shaveable` -- used in `SHAVE` actions to remove beard or other shaveables
- `bedazzler` -- used in `BEDAZZLE` to apply bedazzlement effects
- `blinkstaff` -- used in `BLINK` and `BLINK_MAP` for teleportation
- `boatcannon`, `boatcannonuser` -- used in boat cannon actions for loading, aiming, and shooting
- `boatleak` -- used in `REPAIR_LEAK` and `UNPATCH` to handle leak repair
- `boatmagnet`, `boatmagnetbeacon` -- used in magnet activation/deactivation
- `boatrotator` -- used in rotate boat actions to set rotation direction
- `bottler` -- used in `BOTTLE` to bottle entities
- `brushable` -- used in `BRUSH` to brush entities
- `builder` -- used in `CONSTRUCT`, `BUILD`, and prototyper interactions
- `bundler` -- used in `BUNDLE`, `UNWRAP`, `PEEKBUNDLE` for bundling state
- `burnable` -- used in many actions to handle fire, smolder, and extinguishing
- `carnivalgamefeedable` -- used in `FEED` actions for carnival game feeding
- `cattoy`, `poppable` -- used in `CATPLAYGROUND` and `CATPLAYAIR` for catcoon play
- `channelable`, `channelcaster`, `channelcastable` -- used in channeling actions (`STARTCHANNELING`, `STOPCHANNELING`, `START_CHANNELCAST`, `STOP_CHANNELCAST`)
- `childspawner`, `spawner`, `hideout` -- used in `GOHOME` actions to return entities home
- `closeinspector` -- used in `LOOKAT` for targeted close inspection
- `combat` -- used in `ATTACK`, `MOUNT`, and many combat-related actions
- `complexprojectile` -- used in `TOSS`, `DEPLOY` for projectile-based actions
- `container` and `container_proxy` -- used in `RUMMAGE`, `PICKUP`, `EMPTY_CONTAINER` to manage opening and dropping
- `containerinstallableitem` -- used in `CONTAINER_INSTALL_ITEM` to validate containers
- `cookable`, `cooker`, `stewer` -- used in `COOK` actions for individual and pot cooking
- `craftingstation` -- used in recipe learning and crafting station interactions
- `crittertraits`, `petleash` -- used in `PET`, `ABANDON`, and follower management
- `crop` -- used in `FERTILIZE` and `HARVEST` for crop cycles
- `cyclable` -- used in `CYCLE` for cycling singable shells
- `deployable`, `deployable` (component) -- used in `DEPLOY` actions for item deployment
- `dryingrack` -- used in `HARVEST` for dried item removal
- `eater` and `edible` -- used in `FEED` actions to consume food
- `electricconnector` -- used in `STARTELECTRICLINK`, `ENDELECTRICLINK` for fence linking
- `entitytracker` -- used in `PICKUP` to locate owner entities
- `equipable` and `inventoryitem` -- used in `EQUIP`, `UNEQUIP`, `PICKUP`, and container operations
- `expertsailor` -- used in sail lowering and rowing speed adjustments
- `fan` -- used in `FAN` to apply air flow
- `farmplantstress`, `farmplanttendable` -- used in `ATTACKPLANT` and `INTERACT_WITH`
- `farmtiller`, `quagmire_tiller` -- used in `TILL` to till soil
- `farmplantable`, `quagmire_plantable` -- used in `PLANTSOIL` to plant seeds
- `follower`, `followerherder` -- used in `HERD_FOLLOWERS`, `ABANDON`, and follower management
- `fueled`, `fertilizer` -- used in `FERTILIZE`, `FUEL`, and cooking
- `furnituredecortaker` -- used in `DECORATE` to accept decor items
- `ghostgestalter`, `ghostlyelixir`, `ghostlybond` -- used in `MUTATE`, `APPLYELIXIR`, and ghost summoning actions
- `grabbable`, `health` -- used in `NET` to validate netting
- `gravediggable`, `gravedigger` -- used in `GRAVEDIG` for grave digging
- `grower` -- used in `FERTILIZE` for soil fertilization
- `guardian` -- used in `SUMMONGUARDIAN` to call guardians
- `hitchable`, `hitcher` -- used in `HITCH` and `UNHITCH` for beefalo hitching
- `hideandseekhidingspot` -- used in `HIDEANSEEK_FIND` for hiding spot search
- `inspectable` -- used in `LOOKAT` to read descriptions
- `instrument` -- used in `PLAY` for instrument playing
- `inventory` -- used across many actions for item movement, dropping, and equipping
- `inventoryitemholder` -- used in `GIVE`, `TAKEITEM`, and storage interactions
- `itemmimic` -- checked in multiple actions to block mimic usage
- `itemtyperestrictions` -- used in `PICKUP` to validate item placement
- `itemweigher`, `trophyscale`, `weighable` -- used in `WEIGH_ITEM` and `COMPARE_WEIGHABLE`
- `kitcoon`, `kitcoonden` -- used in `ABANDON` and `RETURN_FOLLOWER` for kitcoon logic
- `lighter` -- used in `LIGHT` actions to ignite burnables
- `lock`, `klaussacklock` -- used in `UNLOCK` and `USEKLAUSSACKKEY`
- `locomotor` -- stopped before actions like `LOOKAT` and `TALKTO`
- `lootdropper` -- used in `MURDER` and `HAUNT` for loot generation
- `machine` -- used in `TURNON`/`TURNOFF` for toggling devices
- `magician` -- used in `USEMAGICTOOL` and `STOPUSINGMAGICTOOL`
- `mast` -- used in sail raising and lowering actions
- `maxhealer`, `healer` -- used in `HEAL` actions
- `maxwelltalker` -- used in `TALKTO` for Maxwell speech
- `mightygym`, `strongman` -- used in gym-related actions (`ENTER_GYM`, `LEAVE_GYM`, `UNLOAD_GYM`)
- `mine` -- used in `RESETMINE` to reset mines
- `moonstormstaticcatcher`, `gestaltcage` -- used in `POUNCECAPTURE` and `DIVEGRAB`
- `moontrader` -- used in `GIVE_MOONTRADER` for moon trading
- `npc_talker` -- used in `COMMENT` for NPC chatter
- `occupiable`, `occupier` -- used in `OCCUPY` and `UNOCCUPY`
- `oar`, `crewmember` -- used in `ROW` and `ROW_FAIL` actions
- `oceanfishingrod`, `oceanfishable` -- used in `OCEAN_FISHING` actions
- `oceantrawler` -- used in trawler lowering, raising, and fixing
- `oceanthrowable` -- used in `OCEAN_TOSS` for projectile prep
- `pinnable` -- used in `UNPIN` to unstick entities
- `playercontroller` -- checked for direct walking and input focus
- `playingcard`, `deckcontainer` -- used in card deck actions
- `playbill_lecturn` -- used in `SWAP_PLAYBILL`
- `pollinator` -- used in `POLLINATE` actions
- `portablestructure` -- used in `DISMANTLE`
- `preservative`, `perishable` -- used in `APPLYPRESERVATIVE`
- `questowner` -- used in `BEGIN_QUEST` and `ABANDON_QUEST`
- `reader`, `book`, `simplebook` -- used in `READ` actions
- `recipescanner` -- used in `TEACH` actions
- `remoteteleporter` -- used in `REMOTE_TELEPORT` for remote teleporting
- `repairable`, `repairer`, `forgerepairable`, `forgerepair`, `sewing` -- used in `REPAIR` actions
- `rideable`, `rider` -- used in `MOUNT`, `DISMOUNT`, and `SADDLE` actions
- `scrapbookable`, `teacher`, `maprecorder`, `mapspotrevealer` -- used in `TEACH` actions
- `ship_tiller`, `quagmire_tiller` -- used in `TILL`
- `singable`, `singinginspiration` -- used in `SING` actions
- `sleepingbag` -- used in `SLEEP` actions
- `slingshotmodder`, `slingshotmods` -- used in `MODSLINGSHOT` and `STOPMODSLINGSHOT`
- `snowmandecoratable` -- used in `DECORATESNOWMAN` for decoration and stacking
- `spellbook`, `spellcaster`, `pocketwatch`, `pocketwatch_dismantler` -- used in spellcasting and dismantling
- `spidermutator` -- used in `MUTATE_SPIDER`
- `sittable` -- used in `SITON`
- `skilltreeupdater` -- used to validate skill-based access
- `stageactingprop`, `stageactor` -- used in `PERFORM` for performance actions
- `steeringwheel`, `steeringwheeluser` -- used in `STEER_BOAT` and steering logic
- `storyteller` -- used in `TELLSTORY`
- `tackler`, `tacklesketch` -- used in `TACKLE` and `GIVE_TACKLESKETCH`
- `tropyscale`, `itemweigher` -- used in `WEIGH_ITEM` and `COMPARE_WEIGHABLE`
- `trap` -- used in `BAIT` to set bait
- `terraformer` -- used in `TERRAFORM` for ground modification
- `thief` -- used in `STEAL` actions
- `toggleableitem`, `useableitem`, `useabletargeteditem` -- used in `USEITEM`, `USEITEMON`, `STOPUSINGITEM`
- `unwrappable` -- used in `UNWRAP` and `PEEKBUNDLE`
- `upgradeable`, `upgrader`, `upgrademoduleowner`, `upgrademodule`, `upgrademoduleremover` -- used in `UPGRADE` and module actions
- `vase` -- used in `DECORATE_VASE`
- `walkingplank` -- used in plank actions for ship boarding/deboarding
- `wateringcan`, `wateryprotection` -- used in `POUR_WATER` actions
- `waxable` -- used in `WAX`
- `winch` -- used in `UNLOAD_WINCH`
- `writeable` -- used in `WRITE` actions
- `yotb_sewer`, `yotb_stager`, `yotb_skinunlocker`, `yotc_racestart`, `yotc_raceprizemanager` -- used in YOTB/YOTC system actions

**Tags:**
- `heavy` -- checked for physics-based weight checks
- `player`, `playerghost`, `playerfloater` -- used for player-specific logic and ghost actions
- `fooddrink`, `soul`, `souljar` -- used for eating, soul consumption, and soul jar logic
- `noslip`, `nosteal` -- used for inventory and steal behavior
- `drop_inventory_onpickup`, `INLIMBO`, `fueldepleted`, `burnableignorefuel` -- used for special drop and fueling behavior
- `repairable_moon_altar`, `repairable_vitae` -- used for moon altar and vitae repairs
- `tape`, `mastercookware`, `masterchef`, `expertchef` -- used for cooking and repair restrictions
- `merm`, `mermonly` -- used for merm-specific behavior
- `decoratable`, `unwrappable`, `ancient_text` -- used for decor and reading actions
- `farm_plant`, `portablestorage`, `pocketdimension_container` -- used for farming and storage logic
- `usedeploystring` -- used for deployment display strings
- `projectile` -- used to block picking up thrown projectiles
- `groundtile`, `wallbuilder`, `fencebuilder`, `gatebuilder`, `boatbuilder`, `deploykititem` -- used for construction and placement
- `eyeturret` -- used for turret interactions
- `fertilizer`, `graveplanter` -- used for fertilizing and grave planting
- `deployedfarmplant`, `frozen` -- used for farm and frozen state logic
- `farming` -- used for farming actions
- `whackable`, `hammer`, `smashable`, `spicer`, `gemsocket` -- used for harvesting and processing
- `trader_just_show`, `trader_repair`, `moontrader` -- used for trader behavior
- `ghostlyelixirable`, `ghostlyelixir`, `wintersfeasttable` -- used for elixir and winter feast logic
- `inventoryitemholder_give`, `furnituredecortaker`, `quagmire_stewer`, `quagmire_altar` -- used for giving and trading
- `watersource` -- used for filling actions
- `pickable_harvest_str`, `pickable_rummage_str`, `pickable_search_str` -- used for display strings
- `nibble`, `propweapon` -- used for feeding and prop actions
- `farm_debris`, `withered`, `plant`, `burnt` -- used for plant and debris state logic
- `dangerouscooker` -- used for cooker safety checks
- `toughworker`, `rangedweapon`, `tough`, `thrusting`, `helmsplitting` -- used for work and combat actions
- `propattack` -- used for prop attack behavior
- `playbill_lecturn`, `stewer`, `wolfgang_coach`, `mightiness_normal`, `coaching`, `coach_whistle` -- used for playbills and coaching
- `controlled_burner`, `stokeablefire` -- used for fire control
- `dressable`, `hitcher` -- used for dressing and hitching
- `strongstomach`, `ignoresspoilage`, `monstermeat`, `spoiled`, `badfood`, `unsafefood` -- used for eating checks
- `quick eat`, `slow eat` -- used for eating speed modifiers
- `winter_treestand`, `bundle`, `birdcage` -- used for special container and event logic
- `teleporter`, `hasemergencymode`, `haunted`, `catchable`, `cannotheal`, `soulstealer`, `pocketwatchcaster` -- used for teleportation and special interactions
- `wormhole`, `tentacle_pillar` -- used for wormhole and pillar actions
- `ITEMMIMIC` -- checked across many actions to prevent mimic usage
- `has_aggressive_follower`, `dogrider_only`, `combatmount`, `fire`, `corpse`, `dogrider`, `CLASSIFIED`, `globalmapicon`, `fogrevealer` -- used for combat and map interactions
- `pet_treat`, `special_action_toss` -- used for feeding and tossing
- `critterlab`, `kitcoonden`, `near_kitcoonden` -- used for critter and kitcoon logic
- `pump` -- used in `STARTCHANNELING.strfn`
- `lighter` -- used in `START_CHANNELCAST.strfn`
- `offerconstructionsite`, `constructionsite`, `repairconstructionsite`, `rebuildconstructionsite`, `pickapart` -- used for construction state
- `canpeek`, `smolder` -- used for peeking and smolder checks
- `race_on` -- used for race start conditions
- `tappable`, `fresh`, `stale` -- used for tree tapping and freshness
- `cookable`, `deployable`, `weighable_<type>`, `trophyscale_<type>` -- used for cooking and weighing
- `anchor_transitioning`, `anchor_lowered`, `boat_leak`, `paired`, `turnedoff`, `sail_transitioning`, `activeprojectile` -- used for boat state tags
- `trawler_lowered`, `trawler_fish_escaped` -- used for trawler state
- `canbeslaughtered`, `quagmire_replatable` -- used for quagmire actions
- `singingshell`, `fertilizerresearchable`, `trophycanbetaken` -- used for shell and research logic
- `wateringcan`, `boatcannon_ammo` -- used for watering and cannon actions
- `steeringboat` -- used for boat steering state
- `bathbomb`, `bathbombable` -- used for bath bomb effects
- `switchtoho` -- used in sail boost string selection
- `master_crewman` -- used in anchor raising speed
- `battery`, `batteryuser` -- used in charging logic
- `can_use_heavy`, `elixir_drinker`, `liftingdumbbell`, `pyromaniac`, `handyperson`, `abigail_flower`, `sewingmachine`, `soil`, `pushing_roll`, `super_elixir`, `hermitcrab`, `character`, `LunarBuildup` -- used for various state and capability checks

## Properties

| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `priority` | number | `0` | Action priority; higher values take precedence. |
| `fn` | function | `function() return false end` | Callback function executed when the action is performed. |
| `strfn` | function or nil | `nil` | Optional function returning a string description for UI. |
| `instant` | boolean | `false` | If true, action executes instantly without locomotion. |
| `rmb` | boolean or nil | `nil` | If true, action requires right mouse button activation (used primarily by tools). |
| `distance` | number or nil | `nil` | Maximum distance from target for action validity. |
| `mindistance` | number or nil | `nil` | Minimum required distance for action validity. |
| `arrivedist` | number or nil | `nil` | Distance threshold at which the action is considered 'arrived'. |
| `ghost_exclusive` | boolean | `false` | If true, action is valid only when ghost and excludes non-ghost interactions. |
| `ghost_valid` | boolean | `false` | If true, action is valid for ghosts. |
| `mount_valid` | boolean | `false` | If true, action is valid while mounted. |
| `encumbered_valid` | boolean | `false` | If true, action is valid while encumbered. |
| `floating_valid` | boolean | `false` | If true, action is valid while floating (e.g., on water). |
| `canforce` | boolean or nil | `nil` | If true, action can be forced (overridden by controller inputs or mod systems). |
| `rangecheckfn` | function or nil | `nil` | Custom function to check range; only used if `canforce` is set. |
| `mod_name` | string or nil | `nil` | Name of the mod defining this action. |
| `silent_fail` | boolean or nil | `nil` | If true, suppresses failure messages for this action. |
| `silent_generic_fail` | boolean or nil | `nil` | If true, suppresses generic failure messages for this action. |
| `paused_valid` | boolean | `false` | If true, action is valid while the game is paused. |
| `actionmeter` | boolean or nil | `nil` | If true, action requires/successfully uses action meter. |
| `customarrivecheck` | function or nil | `nil` | Custom function to check arrival condition (e.g., `CheckTileWithinRange`). |
| `is_relative_to_platform` | boolean or nil | `nil` | If true, position checks are relative to current platform. |
| `disable_platform_hopping` | boolean or nil | `nil` | If true, prevents switching platforms during action. |
| `skip_locomotor_facing` | boolean or nil | `nil` | If true, skips facing direction update during locomotion. |
| `do_not_locomote` | boolean or nil | `nil` | If true, prevents locomotion for this action. |
| `extra_arrive_dist` | number or nil | `nil` | Additional distance added to arrive threshold. |
| `tile_placer` | string or nil | `nil` | Name of tile placer to use (e.g., `'gridplacer'`). |
| `show_tile_placer_fn` | function or nil | `nil` | Function to control tile placer visibility. |
| `theme_music` | string or nil | `nil` | Theme music ID to play when action is active. |
| `theme_music_fn` | function or nil | `nil` | Client-side function returning theme music ID dynamically. |
| `pre_action_cb` | function or nil | `nil` | Callback function executed before action runs on client and server. |
| `invalid_hold_action` | boolean or nil | `nil` | If true, cancels held-item actions on conflict. |
| `show_primary_input_left` | string or nil | `nil` | Input label to show for primary (left) input. |
| `show_secondary_input_right` | string or nil | `nil` | Default `nil` | Input label to show for secondary (right) input. |
| `map_action` | boolean or nil | `nil` | If true, action is intended for minimap context. |
| `closes_map` | boolean or nil | `nil` | If true, minimap closes immediately on action start. |
| `map_only` | boolean or nil | `nil` | If true, action only exists when the minimap is open. |
| `map_works_on_unexplored` | boolean or nil | `nil` | If true, bypasses visibility checks for map actions. |

## Main functions

### `MakeRangeCheckFn(range)`
* **Description:** Returns a closure function that checks if the doer is within a specified range of the target using `doer:IsNear(target, range)`.
* **Parameters:**
  - `range` -- number: Maximum distance threshold for proximity checks
* **Returns:** function(doer, target) -- returns boolean if target is non-nil and within range, else false.
* **Error states:** None

### `PickRangeCheck(doer, target)`
* **Description:** Checks if the doer is within range of the target, including extra range for jostle-pick/rummage/search weapons and physics radius adjustments.
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `target` -- Entity: The target entity
* **Returns:** boolean or nil -- true if target is within effective range, else nil if target is nil.
* **Error states:** Returns `nil` if `target` is `nil`.

### `ExtraPickRange(doer, dest, bufferedaction)`
* **Description:** Returns additional distance (0.75) if `dest` is on ocean water (tile is ocean but not passable), plus weapon attack range for jostle-pick actions.
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like: Destination point, if present
  - `bufferedaction` -- table or nil: Optional buffered action with target and invobject
* **Returns:** number -- Extra distance tolerance (0 or 0.75 plus weapon range).
* **Error states:** Returns 0 if `dest` or `bufferedaction.target` is nil or no extra range is applicable.

### `PhysicsPaddedRangeCheck(doer, target)`
* **Description:** Checks squared distance between `doer` and `target` against target's physics radius + 4 padding (unused in codebase).
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `target` -- Entity: The target entity
* **Returns:** boolean or nil -- true if within padded range, else nil if target is nil.
* **Error states:** Returns `nil` if `target` is nil.

### `CheckFishingOceanRange(doer, dest)`
* **Description:** Verifies if the test point near doer at fishing destination is over valid ocean tile (found via `FindVirtualOceanEntity`) when on land or platform, otherwise allows.
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like: Destination point (fishing location)
* **Returns:** boolean -- true if valid ocean fishing spot, false otherwise.
* **Error states:** None

### `CheckRowRange(doer, dest)`
* **Description:** Checks if the test point is not on a platform (i.e., on open water) to allow rowing actions.
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like: Destination point
* **Returns:** boolean -- true if not on a platform (open water), false otherwise.
* **Error states:** None

### `CheckIsOnPlatform(doer, dest)`
* **Description:** Checks whether doer is currently standing on a platform (not open ocean).
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like or nil: Destination point (unused in implementation)
* **Returns:** boolean -- true if doer has a current platform, false otherwise.
* **Error states:** None

### `CheckOceanFishingCastRange(doer, dest)`
* **Description:** Similar to `CheckFishingOceanRange` but with a larger test offset (1.5 units).
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like: Destination point for ocean fishing cast
* **Returns:** boolean -- true if ocean fishing cast is valid, false otherwise.
* **Error states:** None

### `CheckTileWithinRange(doer, dest)`
* **Description:** Checks if doer is within half a tile of the target tile center.
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like: Destination point (tile position)
* **Returns:** boolean or nil -- true if within `TILE_SCALE * 0.5`, else false.
* **Error states:** None

### `ShowPourWaterTilePlacer(right_mouse_action)`
* **Description:** Returns true only if target is a `farm_plant` and its position is farmable soil; false otherwise.
* **Parameters:**
  - `right_mouse_action` -- table or nil: Action context containing target
* **Returns:** boolean -- true if target is valid farm plant on farmable soil, else false.
* **Error states:** Returns false if `right_mouse_action` is nil or target is not a `farm_plant`.

### `ExtraPickupRange(doer, dest)`
* **Description:** Returns 0.75 extra distance if `dest` is on ocean water (tile is ocean but not passable).
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like or nil: Destination point
* **Returns:** number -- 0.75 if on water, else 0.
* **Error states:** Returns 0 if `dest` is nil or not on ocean water.

### `ExtraDeployDist(doer, dest, bufferedaction)`
* **Description:** Returns extra deployment distance (0, 1, or inventory-defined spacing + 1) when crossing between land/water/void/boat platforms or for projectile items.
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like or nil: Destination point
  - `bufferedaction` -- table or nil: Buffered action with invobject reference
* **Returns:** number -- Extra distance tolerance based on terrain transitions or item properties.
* **Error states:** Returns 0 if no extra spacing conditions are met.

### `ExtraDropDist(doer, dest, bufferedaction)`
* **Description:** Returns 1.75 extra distance for dropping on ocean water, and physics radius + 0.5 for colliding items unless explicitly disabled.
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like or nil: Destination point
  - `bufferedaction` -- table or nil: Buffered action with invobject reference
* **Returns:** number -- Extra drop distance (0, 1.75, or physics-based).
* **Error states:** Returns 0 if `dest` is nil, item has no collision, or item explicitly opts out.

### `ExtraPourWaterDist(doer, dest, bufferedaction)`
* **Description:** Returns fixed extra distance (1.5) for pouring water actions.
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like or nil: Destination point (unused)
  - `bufferedaction` -- table or nil: Buffered action (unused)
* **Returns:** number -- 1.5
* **Error states:** None

### `ExtraHealRange(doer, dest, bufferedaction)`
* **Description:** Returns absolute difference between physics radius and overridden radius if target has lower radius (e.g., Brightshades).
* **Parameters:**
  - `doer` -- Entity: The entity performing the action (unused)
  - `dest` -- Vector3-like or nil: Destination point (unused)
  - `bufferedaction` -- table or nil: Buffered action with target reference
* **Returns:** number -- Absolute radius difference or 0.
* **Error states:** Returns 0 if target has no physics or radius delta is non-negative.

### `ArriveAnywhere()`
* **Description:** Always returns true; used as custom arrive check for actions like `BLINK_MAP`.
* **Parameters:** None
* **Returns:** boolean -- true
* **Error states:** None

### `ExtraWobyForagingDist(doer, dest, bufferedaction)`
* **Description:** Returns 0.5 extra range for Woby foraging, plus 1 if doer is a large creature.
* **Parameters:**
  - `doer` -- Entity: The entity performing the action
  - `dest` -- Vector3-like or nil: Destination point (unused)
  - `bufferedaction` -- table or nil: Buffered action (unused)
* **Returns:** number -- 0.5 or 1.5 depending on doer tag.
* **Error states:** None

### `SetClientRequestedAction(actioncode, mod_name)`
* **Description:** Sets `CLIENT_REQUESTED_ACTION` global by looking up action in `ACTIONS_BY_ACTION_CODE` or `MOD_ACTIONS_BY_ACTION_CODE[mod_name]`.
* **Parameters:**
  - `actioncode` -- string: Action code identifier
  - `mod_name` -- string or nil: Optional mod name to scope action lookup
* **Returns:** None
* **Error states:** Sets nil if action not found.

### `ClearClientRequestedAction()`
* **Description:** Resets `CLIENT_REQUESTED_ACTION` global to nil.
* **Parameters:** None
* **Returns:** None
* **Error states:** None

### `Action(data, instant, rmb, distance, ghost_valid, ghost_exclusive, canforce, rangecheckfn)`
* **Description:** Constructor for Action objects; accepts table-based config or legacy positional arguments (with deprecation warning). Initializes all fields and validates data.
* **Parameters:**
  - `data` -- table: Configuration table or deprecated positional priority argument
  - `instant` -- boolean (positional, deprecated)
  - `rmb` -- boolean (positional, deprecated)
  - `distance` -- number (positional, deprecated)
  - `ghost_valid` -- boolean (positional, deprecated)
  - `ghost_exclusive` -- boolean (positional, deprecated)
  - `canforce` -- boolean (positional, deprecated)
  - `rangecheckfn` -- function (positional, deprecated)
* **Returns:** None (constructs self)
* **Error states:** Prints warning and converts positional args to table if legacy interface used.

### `IsItemInReadOnlyContainer(item)`
* **Description:** Checks whether the given item is inside a container marked as read-only.
* **Parameters:**
  - `item` -- Entity: to check; function returns true if it is in a read-only container
* **Returns:** boolean -- true if item is in a read-only container, false otherwise
* **Error states:** None

### `ACTIONS.RUMMAGE.fn(act)`
* **Description:** Handles opening/closing containers, checking restrictions, dropping items on open if configured, and resolving `container_proxy` to master containers.
* **Parameters:**
  - `act` -- action context object containing doer, target/invobject, options, and action point information
* **Returns:** true if action succeeded, false with reason string if blocked, nil if no target or container
* **Error states:** Returns early if no target/container; silent fail if container opened in darkness or unseeable; silent fail if trying to open container while riding it (unless it's a player floater)

### `ACTIONS.RUMMAGE.strfn(act)`
* **Description:** Returns display string for the RUMMAGE action, preferring 'CLOSE' if container/proxy is opened, else checking for DECORATE/PEEK if target has respective tags.
* **Parameters:**
  - `act` -- action context object
* **Returns:** 'CLOSE'/'DECORATE'/'PEEK' string, or nil if none apply
* **Error states:** Returns nil if no matching condition

### `ACTIONS.DROP.fn(act)`
* **Description:** Drops the held item from the doer's inventory, respecting unequip protection, stack behavior, random drop direction, and keeping overstacked items.
* **Parameters:**
  - `act` -- action context object
* **Returns:** result of `Inventory:DropItem` or nil
* **Error states:** Returns nil if `invobject` is nil or equippable prevents unequipping

### `ACTIONS.DROP.strfn(act)`
* **Description:** Returns a display string for the DROP action based on item tags or special functions.
* **Parameters:**
  - `act` -- action context object
* **Returns:** String key like 'SETTRAP', 'SETMINE', 'FREESOUL', 'PLACELANTERN', 'PLAYERFLOATER', or custom via `GetDropActionString`; nil if none match
* **Error states:** Returns nil if item has deployable component or no matching tag

### `ShouldLOOKATStopLocomotor(act)`
* **Description:** Helper that determines if the doer's locomotion should be stopped before a LOOKAT action based on playercontroller settings and state graph tags.
* **Parameters:**
  - `act` -- action context object
* **Returns:** boolean
* **Error states:** None

### `ACTIONS.LOOKAT.strfn(act)`
* **Description:** Returns 'CLOSEINSPECT' if a close inspection target exists, or 'READ' if the target is `ancient_text` and the doer has `ancient_reader` equipped.
* **Parameters:**
  - `act` -- action context object
* **Returns:** 'CLOSEINSPECT' or 'READ' string, or nil
* **Error states:** None

### `ACTIONS.LOOKAT.fn(act)`
* **Description:** Performs close inspection if the equipped item has a `closeinspector` component, otherwise reads and speaks the description from `inspectable` component.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true and success args if inspection/description succeeds, false/reason if `closeinspector` fails, nil otherwise
* **Error states:** Stops locomotion before inspecting; fails silently if entity is in darkness and not a portable storage; fails with talker if `closeinspector` returns false

### `ACTIONS_MAP_REMAP[ACTIONS.ACTIVATE.code](act, targetpos)`
* **Description:** Map remap function for `ACTIVATE` action, used to detect wormholes via `charlieresidue` when looking at map positions.
* **Parameters:**
  - `act` -- action context object
  - `targetpos` -- Vector3 position on map
* **Returns:** BufferedAction for `JUMPIN_MAP` if wormhole is detected, else nil
* **Error states:** Returns nil if `doer` is nil, no `charlieresidue`, no valid wormhole found, or context does not match `WORMHOLE`

### `ACTIONS.READ.fn(act)`
* **Description:** Attempts to read a book or `simplebook` via `reader` or `simplebook` components.
* **Parameters:**
  - `act` -- action context object
* **Returns:** success and reason from `reader:Read` or true if `simplebook:Read` was invoked, nil otherwise
* **Error states:** Returns nil if target or doer is nil, or neither book component is present

### `ACTIONS.ROW_FAIL.fn(act)`
* **Description:** Attempts to row a boat with an equipped oar; triggers failure logic and sound if `oar:RowFail` returns a reason.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true (to trigger action chain), regardless of oar failure
* **Error states:** Returns false early if no oar equipped

### `row(act)`
* **Description:** Shared helper for `ROW`/`ROW_CONTROLLER` actions: rows with oar or `crewmember` component, pushes working event on success.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true if oar or crewmember is present, false otherwise
* **Error states:** Returns false if neither oar nor crewmember component present

### `ACTIONS.ROW.fn(act)`
* **Description:** Wrapper around the shared `row()` helper for rowing with an oar.
* **Parameters:**
  - `act` -- action context object
* **Returns:** result of `row(act)`
* **Error states:** None

### `ACTIONS.ROW_CONTROLLER.fn(act)`
* **Description:** Wrapper around the shared `row()` helper for rowing with a controller.
* **Parameters:**
  - `act` -- action context object
* **Returns:** result of `row(act)`
* **Error states:** None

### `ACTIONS.BOARDPLATFORM.fn(act)`
* **Description:** Simple board action stub that always succeeds.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true
* **Error states:** None

### `ACTIONS.OCEAN_FISHING_POND.fn(act)`
* **Description:** Checks if the target is a `virtualocean` tag entity for ocean fishing pond action.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true if tagged, false with 'WRONGGEAR' reason otherwise
* **Error states:** None

### `ACTIONS.OCEAN_FISHING_CAST.fn(act)`
* **Description:** Casts the ocean fishing rod at the provided or target position.
* **Parameters:**
  - `act` -- action context object
* **Returns:** result of `oceanfishingrod:Cast` or nil
* **Error states:** Returns nil if rod or rod component missing

### `ACTIONS.OCEAN_FISHING_REEL.strfn(act)`
* **Description:** Returns 'SETHOOK' if the reel target is partiallyhooked.
* **Parameters:**
  - `act` -- action context object
* **Returns:** 'SETHOOK' or nil
* **Error states:** None

### `ACTIONS.OCEAN_FISHING_REEL.fn(act)`
* **Description:** Reels in the fishing line.
* **Parameters:**
  - `act` -- action context object
* **Returns:** result of `oceanfishingrod:Reel` or nil
* **Error states:** Returns nil if rod or component missing

### `ACTIONS.OCEAN_FISHING_STOP.fn(act)`
* **Description:** Stops ocean fishing by transitioning to 'oceanfishing_stop' state and calling `StopFishing`.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true
* **Error states:** None

### `ACTIONS.OCEAN_FISHING_CATCH.fn(act)`
* **Description:** Catches a fish by transitioning to 'oceanfishing_catch' state and calling `CatchFish`.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true
* **Error states:** None

### `ACTIONS.CHANGE_TACKLE.strfn(act)`
* **Description:** Returns 'REMOVE' or 'AMMO' based on if the item is inside equipped container or is a `reloaditem_ammo`.
* **Parameters:**
  - `act` -- action context object
* **Returns:** 'REMOVE'/'AMMO' or nil
* **Error states:** None

### `ACTIONS.CHANGE_TACKLE.fn(act)`
* **Description:** Handles complex tackle swapping logic: removing from container, stacking, slot-specific storage, or swapping with existing items.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true on success, false on failure
* **Error states:** Returns false if equipped item is missing container or item constraints fail; fails to move item back to inventory on container failure

### `ACTIONS.TALKTO.fn(act)`
* **Description:** Handles talking to entities with `talkable` or `maxwelltalker` components, stopping locomotion and starting speech threads.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true if talkable present, otherwise nil
* **Error states:** Returns nil if target lacks `talkable` component

### `ACTIONS.INTERACT_WITH.strfn(act)`
* **Description:** Returns 'FARM_PLANT' if target has `farm_plant` tag.
* **Parameters:**
  - `act` -- action context object
* **Returns:** 'FARM_PLANT' or nil
* **Error states:** None

### `ACTIONS.INTERACT_WITH.fn(act)`
* **Description:** Tends a farm plant if it has the `farmplanttendable` component and enables talker state.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true on successful tend, otherwise nil
* **Error states:** Returns nil if target missing `farmplanttendable` or tend fails

### `ACTIONS.INTERACT_WITH.theme_music_fn(act)`
* **Description:** Returns 'farming' theme music string if target has `farm_plant` tag.
* **Parameters:**
  - `act` -- action context object
* **Returns:** 'farming' or nil
* **Error states:** None

### `ACTIONS.ATTACKPLANT.fn(act)`
* **Description:** Stresses a farm plant by marking it as stressed and tendable.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true if `farmplantstress` component exists
* **Error states:** None

### `ACTIONS.TELLSTORY.stroverridefn(act)`
* **Description:** Returns the localized string for `TELLSTORY` action, overriding display to hide target prefix.
* **Parameters:**
  - `act` -- action context object
* **Returns:** `STRINGS.ACTIONS.TELLSTORY`
* **Error states:** None

### `ACTIONS.TELLSTORY.fn(act)`
* **Description:** Executes `storyteller:TellStory` on the doer for the target or `invobject`.
* **Parameters:**
  - `act` -- action context object
* **Returns:** result of `storyteller:TellStory` or nil
* **Error states:** Returns nil if doer lacks storyteller component

### `ACTIONS.PERFORM.fn(act)`
* **Description:** Runs `stageactingprop:DoPerformance` by a `stageactor` doer on a `stageactingprop` target.
* **Parameters:**
  - `act` -- action context object
* **Returns:** result of `DoPerformance` or nil
* **Error states:** Returns nil if either doer or target lacks required component

### `ACTIONS.BAIT.fn(act)`
* **Description:** Sets bait on a trap after removing it from the doer's inventory.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true on success
* **Error states:** Returns nil if target lacks `trap` component

### `ACTIONS.DEPLOY.fn(act)`
* **Description:** Handles item deployment logic: checks `canDeploy`, launches `complexprojectile`, or deploys via `deployable` component while managing inventory removal.
* **Parameters:**
  - `act` -- action context object
* **Returns:** true on success, false with reason if deploy fails
* **Error states:** Returns false if `CanDeploy` fails, or deployment fails; drops item back into inventory on failure if needed

### `DoToolWork(act, workaction)`
* **Description:** Performs work on a target entity using tool and worker effectiveness, accounting for recoil, work multipliers, and internal work application.
* **Parameters:**
  - `act` -- Action table containing doer, target, invobject, and action metadata
  - `workaction` -- String identifier of the work type (e.g., 'CHOP', 'MINE')
* **Returns:** true on success, false with error reason string on failure
* **Error states:** `ITEMMIMIC`: early return false if the object is an item mimic

### `ValidToolWork(act, workaction)`
* **Description:** Checks if an action is valid for work (target is workable, not restricted, correct action).
* **Parameters:**
  - `act` -- Action table containing doer, target, invobject
  - `workaction` -- String identifier of the work type
* **Returns:** boolean indicating validity
* **Error states:** None

### `ShouldBlockGiving(act)`
* **Description:** Determines if giving an item to another entity should be blocked based on pocket-only inventory constraints.
* **Parameters:**
  - `act` -- Action table with doer, target, invobject and replica fields
* **Returns:** boolean
* **Error states:** None

### `fn(act)`
* **Description:** Handles giving items to targets via multiple component-based logic paths including playbill swap, ghostly elixir application, trading, feeding, decorating, and inventory storage.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false with reason string otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Handles giving items specifically to players with validation for trader availability, inventory capacity, and opened state.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false with reason string otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Handles giving all stacked items to players with validation for trader availability and full inventory check.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false with reason string otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Handles feeding items to players under specific conditions including eater compatibility, edible type, stomach tolerance, and PVP status.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true if action processed (even if item refused), false otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Decorates vases with items if vase is enabled and valid.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Feeds carnival game feedable targets with validation for enabled state.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** result of `DoFeed` callback or false with reason
* **Error states:** None

### `fn(act)`
* **Description:** Stores items into containers or construction sites, handling proxies, restrictions, open states, and special cases like soul jars and bundles.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false with reason string otherwise
* **Error states:** None

### `strfn(act)`
* **Description:** Returns UI string identifier when target matches construction builder UI state.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** `CONSTRUCT` or nil
* **Error states:** None

### `strfn(act)`
* **Description:** Returns appropriate UI string based on target type such as stewer, birdcage, decoratable, etc.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** `COOK`, `SPICE`, `IMPRISON`, `DECORATE`, or nil
* **Error states:** None

### `fn(act)`
* **Description:** Calls builder component to build a recipe at action point with rotation and skin.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** result of `DoBuild` call or nil
* **Error states:** None

### `strfn(act)`
* **Description:** Returns `PLANTER` string when targeting a `winter_treestand`.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** `PLANTER` or nil
* **Error states:** None

### `fn(act)`
* **Description:** Attempts to plant seeds using grower component or special winter tree event logic.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Harvests from crop, harvestable, stewer, dryer, drying rack, occupiable, or quagmire_tappable components.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** result of harvesting operation or false
* **Error states:** None

### `strfn(act)`
* **Description:** Returns `FREE` string for birdcage target or `WITHERED` for withered crops.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** `FREE`, `WITHERED`, or nil
* **Error states:** None

### `fn(act)`
* **Description:** Uses lighter component to ignite burnable target.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Puts player to sleep in a sleeping bag found in inventory or as target.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Initiates hitching process for beefalo to target if conditions like range, mood, and inventory are met.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false with reason string otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Unhitches a hitcher component from its target.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Hitch doer to a hitcher target.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** nil
* **Error states:** None

### `strfn(act)`
* **Description:** Returns `UNMARK` if target is already marked by doer.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** `UNMARK` or nil
* **Error states:** None

### `fn(act)`
* **Description:** Marks or unmarks a target using `markable` or `markable_proxy` components.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on mark/unmark success, false with reason otherwise
* **Error states:** None

### `strfn(act)`
* **Description:** Returns `DRESSUP` if target is dressable.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** `DRESSUP` or nil
* **Error states:** None

### `fn(act)`
* **Description:** Begins changing outfit using wardrobe or groomer component if target is dressable and visible.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false with reason otherwise
* **Error states:** None

### `strfn(act)`
* **Description:** Returns `SELF` if targeting self with controller attached.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** `SELF` or nil
* **Error states:** None

### `fn(act)`
* **Description:** Shaves beard or `shaveable` entity using shaver implement.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** result of shave operation or false
* **Error states:** None

### `strfn(act)`
* **Description:** Returns UI string identifier for coach whistle actions based on state.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** `COACH_OFF`, `COACH_ON`, `TWEET`, or nil
* **Error states:** None

### `fn(act)`
* **Description:** Plays instrument using instrument component.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** result of `Play` call or nil
* **Error states:** None

### `fn(act)`
* **Description:** Pollinates flower or creates new flower if none targeted.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** nil
* **Error states:** None

### `fn(act)`
* **Description:** Terraforms ground using `terraformer` component at action point.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Extinguishes fires via `burnable` or `fueled` components.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Stokes controlled burn for stokeable fire if doer is `controlled_burner`.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false otherwise
* **Error states:** None

### `fn(act)`
* **Description:** Regenerates pickable target if not currently pickable.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** result of `Regen` call or nil
* **Error states:** None

### `fn(act)`
* **Description:** Investigates remembered location, clears it, and tries to retarget combat.
* **Parameters:**
  - `act` -- Action object containing doer, target, invobject, and metadata
* **Returns:** true on success, false otherwise
* **Error states:** None

### `ACTIONS.COMMENT.fn(act)`
* **Description:** Plays a character's comment using `npc_talker` or `talker` component based on `comment_data` attached to the doer.
* **Parameters:**
  - `act` -- Action object containing doer, target, pos, invobject; represents the triggered action.
* **Returns:** nil (no explicit return)
* **Error states:** None

### `ACTIONS.GOHOME.fn(act)`
* **Description:** Attempts to return the doer to a spawner, childspawner, or hideout. If no such component exists, removes the doer or pushes event.
* **Parameters:**
  - `act` -- Action object; contains doer, target, pos.
* **Returns:** boolean or nil (result of `GoHome` call, or true/false based on path taken)
* **Error states:** If `act.target` has no spawner/childspawner/hideout, uses default fallback (Remove or PushEvent).

### `ACTIONS.JUMPIN.strfn(act)`
* **Description:** Returns "HAUNT" string if doer is a `playerghost`, else nil.
* **Parameters:**
  - `act` -- Action object; used to determine verb string based on doer tag.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.JUMPIN.fn(act)`
* **Description:** Transitions the doer’s stategraph into the 'jumpin' state if in 'jumpin_pre', and target is an active teleporter.
* **Parameters:**
  - `act` -- Action object; contains doer, target.
* **Returns:** boolean (true on success, otherwise nil)
* **Error states:** If conditions not met, falls back to 'idle' state.

### `ACTIONS.JUMPIN_MAP.stroverridefn(act)`
* **Description:** Returns the localized string for `JUMPIN_MAP` action (e.g., `MAP_WORMHOLE`).
* **Parameters:**
  - `act` -- Action object.
* **Returns:** string or nil
* **Error states:** None

### `DoCharlieResidueMapAction(act, target, charlieresidue, residue_context)`
* **Description:** Attempts to locate a valid exit teleporter (wormhole or tentacle_pillar) near the action point and transitions to 'jumpin' state. Handles end-node correction and decay of residue.
* **Parameters:**
  - `act` -- Action object.
  - `target` -- Target entity or charlieresidue target.
  - `charlieresidue` -- Entity with charlieresidue component; used to get residue context and target.
  - `residue_context` -- Integer context constant (e.g., `WORMHOLE` or `tentacle_pillar_hole`).
* **Returns:** boolean (true if teleport was successful, false otherwise)
* **Error states:** Default fallback to original target if no other teleporter found.

### `ACTIONS.JUMPIN_MAP.fn(act)`
* **Description:** Handles map-based wormhole entry: resolves charlieresidue target, checks if target is active teleporter, calls helper to handle special cases or default jump-in.
* **Parameters:**
  - `act` -- Action object; contains doer, target (potentially a charlieresidue).
* **Returns:** boolean (true if transitioned to jumpin state, false otherwise)
* **Error states:** Falls back to 'idle' state if no active teleporter or helper fails.

### `ACTIONS.TELEPORT.strfn(act)`
* **Description:** Returns 'TOWNPORTAL' if target is non-nil, else nil.
* **Parameters:**
  - `act` -- Action object; target determines return string.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.TELEPORT.fn(act)`
* **Description:** Transitions the doer to 'entertownportal' state if a valid teleporter is in hand or target.
* **Parameters:**
  - `act` -- Action object; uses invobject or target as teleporter, checks stategraph and tags.
* **Returns:** boolean (true if teleport state started, otherwise nil)
* **Error states:** Requires specific stategraph state and teleporter tag.

### `ACTIONS.RESETMINE.fn(act)`
* **Description:** Calls `Reset()` on the target’s `mine` component if it exists.
* **Parameters:**
  - `act` -- Action object; contains target.
* **Returns:** boolean (true if mine.reset called, otherwise nil)
* **Error states:** None

### `ACTIONS.ACTIVATE.fn(act)`
* **Description:** Validates activation conditions (not smoldering/burning), checks `CanActivate`, and executes `DoActivate`.
* **Parameters:**
  - `act` -- Action object; contains target and doer.
* **Returns:** boolean, msg (success or false, failure message)
* **Error states:** Returns early if `activatable` is missing or target is smoldering/burning.

### `ACTIONS.ACTIVATE.strfn(act)`
* **Description:** Returns the verb string from `target:GetActivateVerb()` if available.
* **Parameters:**
  - `act` -- Action object; contains target and doer.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.ACTIVATE.stroverridefn(act)`
* **Description:** Returns override verb string from `target:OverrideActivateVerb()` if available.
* **Parameters:**
  - `act` -- Action object; contains target and doer.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.OPEN_CRAFTING.strfn(act)`
* **Description:** Returns action string from `PROTOTYPER_DEFS[target.prefab].action_str` if defined.
* **Parameters:**
  - `act` -- Action object; target is used to look up `PROTOTYPER_DEFS`.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.OPEN_CRAFTING.fn(act)`
* **Description:** Calls `builder:UsePrototyper(target)` to open crafting menu.
* **Parameters:**
  - `act` -- Action object; contains doer and target.
* **Returns:** boolean (true if prototyper was used, otherwise false)
* **Error states:** None

### `ACTIONS.CAST_POCKETWATCH.strfn(act)`
* **Description:** Returns verb string using `FunctionOrValue` on custom function or `invobject` default.
* **Parameters:**
  - `act` -- Action object; uses `invobject` and optional custom verb function.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.CAST_POCKETWATCH.fn(act)`
* **Description:** Calls `pocketwatch:CastSpell()` on the held pocketwatch item.
* **Parameters:**
  - `act` -- Action object; uses `invobject` as pocketwatch, doer as caster, and target/position for spell.
* **Returns:** boolean, msg or nil
* **Error states:** Requires `pocketwatchcaster` tag and valid `invobject`.

### `ACTIONS.HAUNT.fn(act)`
* **Description:** Attempts to haunt target if all conditions met (valid, not held, not already haunted, etc.).
* **Parameters:**
  - `act` -- Action object; doer attempts to haunt target.
* **Returns:** boolean (true if haunt succeeded)
* **Error states:** Early returns nil if conditions not satisfied.

### `ACTIONS.MURDER.fn(act)`
* **Description:** Murders the target (or `invobject`), plays sound, drops loot, transfers inventory, and removes entity.
* **Parameters:**
  - `act` -- Action object; doer murders target or `invobject`.
* **Returns:** boolean (true on success)
* **Error states:** Early returns nil if no `health`/`murderable` component.

### `ACTIONS.HEAL.strfn(act)`
* **Description:** Returns verb string: 'SELF', 'USEONSELF', or 'USE' based on target and controller.
* **Parameters:**
  - `act` -- Action object; used to determine verb string based on self-target and controller status.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.HEAL.fn(act)`
* **Description:** Calls `healer:maxhealer:Heal()` on the target with multiplier applied via `efficientuser`.
* **Parameters:**
  - `act` -- Action object; healer item is in `invobject`, target is target or doer.
* **Returns:** boolean, msg or nil (depending on healer component presence and validity)
* **Error states:** Does not heal if target is dead or ghost.

### `ACTIONS.UNLOCK.fn(act)`
* **Description:** Calls `lock:Unlock(key, doer)` on target if it is locked.
* **Parameters:**
  - `act` -- Action object; uses `invobject` (key) to unlock target.
* **Returns:** boolean (true regardless of whether it was locked)
* **Error states:** None

### `ACTIONS.USEKLAUSSACKKEY.fn(act)`
* **Description:** Calls `klaussacklock:UseKey()` with key and doer; returns success and optional reason.
* **Parameters:**
  - `act` -- Action object; uses `invobject` (key) on target’s `klaussacklock`.
* **Returns:** boolean, reason
* **Error states:** None

### `ACTIONS.TEACH.strfn(act)`
* **Description:** Returns verb string ('NOTES', 'SCRAPBOOK', 'READ', or 'SCAN') based on tags of `invobject`.
* **Parameters:**
  - `act` -- Action object; determines verb string based on tags of `invobject`.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.TEACH.fn(act)`
* **Description:** Calls appropriate teach function: `scrapbookable`, `teacher`, `maprecorder`, `mapspotrevealer`, or `recipescanner`.
* **Parameters:**
  - `act` -- Action object; `invobject` teaches target (or doer).
* **Returns:** boolean, reason or nil
* **Error states:** None

### `ACTIONS.TURNON.fn(act)`
* **Description:** Calls `machine:TurnOn()` if the target or item is a machine and is currently off.
* **Parameters:**
  - `act` -- Action object; turns on target or `invobject` if off.
* **Returns:** boolean (true if turned on)
* **Error states:** None

### `ACTIONS.TURNOFF.strfn(act)`
* **Description:** Returns 'EMERGENCY' if target has `hasemergencymode` tag, else nil.
* **Parameters:**
  - `act` -- Action object; checks target for `emergencymode` tag.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.TURNOFF.fn(act)`
* **Description:** Calls `machine:TurnOff()` if the target or item is a machine and is currently on.
* **Parameters:**
  - `act` -- Action object; turns off target or `invobject` if on.
* **Returns:** boolean (true if turned off)
* **Error states:** None

### `ACTIONS.USEITEM.fn(act)`
* **Description:** Calls `ToggleItem()` or `StartUsingItem()` on `invobject` depending on component availability and conditions.
* **Parameters:**
  - `act` -- Action object; invokes `toggleableitem` or `useableitem` on `invobject`.
* **Returns:** boolean or nil (result of invoked method)
* **Error states:** Early returns nil if `invobject` or components invalid.

### `ACTIONS.USEITEMON.strfn(act)`
* **Description:** Returns uppercase `invobject` prefab, or 'GENERIC'.
* **Parameters:**
  - `act` -- Action object; returns uppercase `invobject` prefab, or 'GENERIC'.
* **Returns:** string
* **Error states:** None

### `ACTIONS.USEITEMON.pre_action_cb(act)`
* **Description:** Closes controller inventory if open.
* **Parameters:**
  - `act` -- Action object; used to close inventory HUD if controller is active.
* **Returns:** nil
* **Error states:** None

### `ACTIONS.USEITEMON.fn(act)`
* **Description:** Calls `useabletargeteditem:StartUsingItem(target, doer)` if interaction allowed.
* **Parameters:**
  - `act` -- Action object; uses `useabletargeteditem` on target with doer.
* **Returns:** boolean, reason
* **Error states:** None

### `ACTIONS.STOPUSINGITEM.strfn(act)`
* **Description:** Returns uppercase `invobject` prefab, or 'GENERIC'.
* **Parameters:**
  - `act` -- Action object; returns uppercase `invobject` prefab, or 'GENERIC'.
* **Returns:** string
* **Error states:** None

### `ACTIONS.STOPUSINGITEM.fn(act)`
* **Description:** Calls `useabletargeteditem:StopUsingItem()` and returns true.
* **Parameters:**
  - `act` -- Action object; invokes `StopUsingItem` on `useabletargeteditem`.
* **Returns:** boolean (true if stopped using)
* **Error states:** None

### `ACTIONS.TAKEITEM.fn(act)`
* **Description:** Calls `shelf:TakeItem` or `inventoryitemholder:TakeItem` on target.
* **Parameters:**
  - `act` -- Action object; takes item from target’s shelf or `inventoryitemholder`.
* **Returns:** boolean or nil
* **Error states:** None

### `ACTIONS.TAKEITEM.strfn(act)`
* **Description:** Returns 'BIRDCAGE' if target is birdcage, else 'GENERIC'.
* **Parameters:**
  - `act` -- Action object; returns 'BIRDCAGE' if target is birdcage, else 'GENERIC'.
* **Returns:** string
* **Error states:** None

### `ACTIONS.TAKEITEM.stroverridefn(act)`
* **Description:** Returns dynamic item name with stack size when applicable.
* **Parameters:**
  - `act` -- Action object; returns dynamic item name with stack size when applicable.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.TAKESINGLEITEM.fn(act)`
* **Description:** Calls `inventoryitemholder:TakeItem(doer, false)` to take a partial stack.
* **Parameters:**
  - `act` -- Action object; takes one item from `inventoryitemholder`.
* **Returns:** boolean or nil
* **Error states:** None

### `ACTIONS.TAKESINGLEITEM.stroverridefn(act)`
* **Description:** Returns literal `STRINGS.ACTIONS.TAKESINGLEITEM`.
* **Parameters:**
  - `act` -- Action object; returns literal `STRINGS.ACTIONS.TAKESINGLEITEM`.
* **Returns:** string
* **Error states:** None

### `ACTIONS.CASTSPELL.strfn(act)`
* **Description:** Returns `spelltype` from `invobject` if present.
* **Parameters:**
  - `act` -- Action object; returns `spelltype` from `invobject` if present.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.CASTSPELL.fn(act)`
* **Description:** Casts spell using `spellcaster` component on staff, checks `itemmimic` and heavy lifting constraints.
* **Parameters:**
  - `act` -- Action object; casts spell from held or equipped staff.
* **Returns:** boolean, reason or nil
* **Error states:** Returns early if no `spellcaster`, mimic, or invalid conditions.

### `ACTIONS.DIRECTCOURIER_MAP.maponly_checkvalidpos_fn(act)`
* **Description:** Finds the nearest valid map target (chest or player) within courier radius and restriction criteria.
* **Parameters:**
  - `act` -- Action object; used to find nearest valid courier target (chest or player).
* **Returns:** boolean, reason, x, z, mapent
* **Error states:** Fails with 'NOTARGET' if no entity within range.

### `ACTIONS.DIRECTCOURIER_MAP.stroverridefn(act)`
* **Description:** Returns localized `SEND` verb with target name or `CHEST` string.
* **Parameters:**
  - `act` -- Action object; builds verb string with target name if available.
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.DIRECTCOURIER_MAP.fn(act)`
* **Description:** Calls `maponly_checkvalidpos_fn`, then sends courier command with `destpos`, platform, and chest flag.
* **Parameters:**
  - `act` -- Action object; sends courier command to server via RPC.
* **Returns:** boolean, reason
* **Error states:** Returns early if invalid position or missing components.

### `TryToSoulhop(act, act_pos, consumeall)`
* **Description:** Helper function to validate and attempt portal hop from 'portal_jumpin_pre' state.
* **Parameters:**
  - `act` -- Action object; used for doer and sg checks.
  - `act_pos` -- Vector3 position where portal hop should occur.
  - `consumeall` -- Boolean flag indicating whether to consume all souls.
* **Returns:** boolean (result of `TryToPortalHop`)
* **Error states:** Returns nil if conditions not met.

### `ACTIONS.BLINK.strfn(act)`
* **Description:** Returns 'FREESOUL' or 'SOUL' verb if doer is `soulstealer` and has souls.
* **Parameters:**
  - `act` -- Action object; returns verb based on soulstealer tag and free soul count.
* **Returns:** string or nil
* **Error states:** None

### `ActionCanMapSoulhop(act)`
* **Description:** Checks if the doer can perform soulhop based on their `CanSoulhop` method or returns false.
* **Parameters:**
  - `act` -- Action object containing doer, distance, and action point data
* **Returns:** boolean indicating if soulhop is allowed
* **Error states:** None

### `ActionCanMapToss(act)`
* **Description:** Checks if the `invobject` supports map-based tossing via `CanTossOnMap` method.
* **Parameters:**
  - `act` -- Action object containing doer and `invobject`
* **Returns:** boolean indicating if map toss is allowed
* **Error states:** None

### `ACTIONS.BLINK.fn(act)`
* **Description:** Handles the `BLINK` action: uses `blinkstaff` if present, otherwise attempts soulhop via `portal_jumpin` state.
* **Parameters:**
  - `act` -- Action object containing doer, `invobject`, and action point data
* **Returns:** boolean success or error string
* **Error states:** `ITEMMIMIC` tag blocks usage; soulhop fails if `CanSoulhop` returns false

### `ACTIONS.BLINK_MAP.stroverridefn(act)`
* **Description:** Returns localized soul-based string if doer has `soulstealer` tag and `invobject` is nil.
* **Parameters:**
  - `act` -- Action object containing doer and distancecount
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.BLINK_MAP.fn(act)`
* **Description:** Performs soulhop via `BLINK_MAP` action when `ActionCanMapSoulhop` succeeds.
* **Parameters:**
  - `act` -- Action object containing doer, distance, and target position
* **Returns:** boolean true on success
* **Error states:** None

### `ACTIONS_MAP_REMAP[ACTIONS.BLINK.code](act, targetpos)`
* **Description:** Remaps `BLINK` action for map use, detecting and correcting teleport destinations near fog revealers and boats, and computes soul cost based on distance modifiers.
* **Parameters:**
  - `act` -- Original action object
  - `targetpos` -- Vector3 target position from map cursor
* **Returns:** remapped BufferedAction or nil
* **Error states:** Fails if no valid revealers found; fails if destination is underwater

### `ACTIONS.CASTSUMMON.fn(act)`
* **Description:** Summons a ghost using `ghostlybond` component if `summoningitem` and `ghostlybond` exist.
* **Parameters:**
  - `act` -- Action object containing doer and `invobject`
* **Returns:** return value from `ghostlybond:Summon()` or nil
* **Error states:** None

### `ACTIONS.CASTUNSUMMON.fn(act)`
* **Description:** Recalls a summoned ghost using `ghostlybond:Recall()` if `summoningitem` and `ghostlybond` exist.
* **Parameters:**
  - `act` -- Action object containing doer and `invobject`
* **Returns:** return value from `ghostlybond:Recall()` or nil
* **Error states:** None

### `ACTIONS.COMMUNEWITHSUMMONED.strfn(act)`
* **Description:** Returns action string key based on whether doer has `has_aggressive_follower` tag.
* **Parameters:**
  - `act` -- Action object containing doer
* **Returns:** string `MAKE_DEFENSIVE` or `MAKE_AGGRESSIVE`
* **Error states:** None

### `ACTIONS.COMMUNEWITHSUMMONED.fn(act)`
* **Description:** Changes behavior of summoned follower via `ghostlybond:ChangeBehaviour()` if conditions met.
* **Parameters:**
  - `act` -- Action object containing doer and `invobject`
* **Returns:** return value from `ghostlybond:ChangeBehaviour()` or nil
* **Error states:** None

### `ACTIONS.COMBINESTACK.fn(act)`
* **Description:** Combines stacks of identical items via `stackable:Put()` if target is not full.
* **Parameters:**
  - `act` -- Action object containing target and `invobject`
* **Returns:** boolean true on success
* **Error states:** None

### `ACTIONS.TRAVEL.fn(act)`
* **Description:** Executes a custom travel action via `target.travel_action_fn`.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** boolean true on success
* **Error states:** None

### `ACTIONS.UNPIN.fn(act)`
* **Description:** Unpins a `pinnable` entity if it is stuck.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** boolean true after pushing unpinned event
* **Error states:** None

### `ACTIONS.STEALMOLEBAIT.fn(act)`
* **Description:** Simulates a mole stealing bait, clearing selected target and pushing `onstolen` event.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** boolean true
* **Error states:** None

### `ACTIONS.MAKEMOLEHILL.fn(act)`
* **Description:** Spawns a molehill or molebathill at doer's position for mole/molebat entities.
* **Parameters:**
  - `act` -- Action object containing doer
* **Returns:** boolean true on success
* **Error states:** None

### `ACTIONS.MOLEPEEK.fn(act)`
* **Description:** Triggers a peek event on the doer.
* **Parameters:**
  - `act` -- Action object containing doer
* **Returns:** boolean true
* **Error states:** None

### `ACTIONS.FEED.strfn(act)`
* **Description:** Returns action string key `TREAT` if `invobject` is a pet treat.
* **Parameters:**
  - `act` -- Action object containing `invobject`
* **Returns:** string `TREAT` or nil
* **Error states:** None

### `ACTIONS.FEED.fn(act)`
* **Description:** Feeds an item to target via `trader:AcceptGift` or `eater:Eat`, handling death and loot drops if eater dies.
* **Parameters:**
  - `act` -- Action object containing doer, target, and `invobject`
* **Returns:** boolean true or error reason
* **Error states:** `ITEMMIMIC` blocks feeding; fails if no trader or eater component

### `ACTIONS.HAIRBALL.fn(act)`
* **Description:** Returns true if doer is catcoon (hairball action placeholder).
* **Parameters:**
  - `act` -- Action object containing doer
* **Returns:** boolean true
* **Error states:** None

### `ACTIONS.CATPLAYGROUND.fn(act)`
* **Description:** Performs catcoon play behaviors: `cattoy`, `poppable`, combat (penguins only), picking up items, or activating entities.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** boolean true
* **Error states:** None

### `ACTIONS.CATPLAYAIR.fn(act)`
* **Description:** Performs catcoon airborne play behaviors: `cattoy`, `poppable`, combat (penguins only), or activation.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** boolean true
* **Error states:** None

### `ACTIONS.ERASE_PAPER.fn(act)`
* **Description:** Erases a paper item using `papereraser` if target is not on fire or burnt.
* **Parameters:**
  - `act` -- Action object containing `invobject`, target, and doer
* **Returns:** boolean return from `papereraser:DoErase()`
* **Error states:** None

### `ACTIONS.FAN.fn(act)`
* **Description:** Uses a fan component on target or doer if `invobject` is present.
* **Parameters:**
  - `act` -- Action object containing `invobject` and target
* **Returns:** boolean return from `fan:Fan()` or false with 'ITEMMIMIC'
* **Error states:** `ITEMMIMIC` blocks usage

### `ACTIONS.TOSS.fn(act)`
* **Description:** Tosses an item as a projectile using `complexprojectile:Launch()`, supporting equipped toss items.
* **Parameters:**
  - `act` -- Action object containing doer and `invobject`
* **Returns:** boolean true on launch success
* **Error states:** Fails if no projectile found or item restricted/blocked; `ITEMIMIC` blocks

### `ACTIONS.TOSS_MAP.stroverridefn(act)`
* **Description:** Returns action string if `invobject` supports map toss.
* **Parameters:**
  - `act` -- Action object containing doer and `invobject`
* **Returns:** string or nil
* **Error states:** None

### `ACTIONS.TOSS_MAP.fn(act)`
* **Description:** Executes `TOSS` action when map toss conditions are met.
* **Parameters:**
  - `act` -- Action object containing doer, `invobject`, and target position
* **Returns:** return from `ACTIONS.TOSS.fn()` or nil
* **Error states:** None

### `ACTIONS_MAP_REMAP[ACTIONS.TOSS.code](act, targetpos)`
* **Description:** Remaps `TOSS` action for map use, enforcing min/max distance constraints and ocean-only tiles.
* **Parameters:**
  - `act` -- Original action object
  - `targetpos` -- Vector3 target position from map
* **Returns:** remapped BufferedAction or nil
* **Error states:** Fails if not an ocean tile or outside min/max distance bounds

### `ACTIONS.UPGRADE.fn(act)`
* **Description:** Upgrades a target using `upgrader` and `upgradeable` components.
* **Parameters:**
  - `act` -- Action object containing doer, target, and `invobject`
* **Returns:** boolean true or error string from upgrade
* **Error states:** Fails if `CanUpgrade` returns false

### `ACTIONS.UPGRADE.strfn(act)`
* **Description:** Returns 'WATERPLANT' key if target is a waterplant upgradeable.
* **Parameters:**
  - `act` -- Action object containing target
* **Returns:** string 'WATERPLANT' or nil
* **Error states:** None

### `ACTIONS.NUZZLE.fn(act)`
* **Description:** Performs a nuzzle interaction; currently a placeholder returning true.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** boolean true
* **Error states:** None

### `ACTIONS.WRITE.fn(act)`
* **Description:** Begins writing on a `writeable` entity if not already written and visible.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** boolean true or false with 'INUSE'
* **Error states:** Fails silently in dark; `INUSE` if already being written

### `ACTIONS.ATTUNE.fn(act)`
* **Description:** Attunes a player to a target using `attunable:LinkToPlayer()`.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** return value from `attunable:LinkToPlayer()` or nil
* **Error states:** None

### `ACTIONS.MIGRATE.fn(act)`
* **Description:** Activates world migration via `worldmigrator:Activate()` for the player.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** return value from `worldmigrator:Activate()` or nil
* **Error states:** Fails if destination is missing

### `ACTIONS.REMOTERESURRECT.fn(act)`
* **Description:** Resurrects a ghost remotely using `attuner`'s linked `remoteresurrector` or `gravestoneresurrector`.
* **Parameters:**
  - `act` -- Action object containing doer
* **Returns:** boolean true on success
* **Error states:** None

### `ACTIONS.REVIVE_CORPSE.fn(act)`
* **Description:** Revives a corpse via `revivablecorpse` component if conditions met.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** boolean true
* **Error states:** Silent fail if cannot be revived

### `ACTIONS.MOUNT.fn(act)`
* **Description:** Attempts to mount a `rideable` entity, checking combat, saddle, health, frozen state, hitching, and rider tags.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** boolean true or error reason
* **Error states:** Fails if target is in combat, frozen, hitched, ridden, or tag-restricted

### `ACTIONS.DISMOUNT.fn(act)`
* **Description:** Dismounts the rider if doer equals target and is currently riding.
* **Parameters:**
  - `act` -- Action object containing doer and target
* **Returns:** boolean true after dismount event
* **Error states:** None

### `ACTIONS.SADDLE.fn(act)`
* **Description:** Handles equipping a saddle onto a `rideable` entity, checking for combat, death, mimic, and rideable compatibility.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if successful, false or error string otherwise
* **Error states:** `TARGETINCOMBAT`, `ITEMMIMIC`

### `ACTIONS.UNSADDLE.fn(act)`
* **Description:** Handles removing a saddle from a `rideable` entity, checking for combat, death, mimic, and rideable compatibility.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if successful, false or error string otherwise
* **Error states:** `TARGETINCOMBAT`, `ITEMMIMIC`

### `ACTIONS.BRUSH.fn(act)`
* **Description:** Handles brushing a `brushable` entity, checking for combat, death, mimic, and `brushable` compatibility.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if successful, false or error string otherwise
* **Error states:** `TARGETINCOMBAT`, `ITEMMIMIC`

### `ACTIONS.ABANDON.fn(act)`
* **Description:** Handles abandoning a pet by despawning it (via `petleash`) or stopping follower relationship.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if successful, false otherwise
* **Error states:** None

### `ACTIONS.PET.fn(act)`
* **Description:** Handles petting a critter or `kitcoon`, triggering `OnPet` or `on_petted` events.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true
* **Error states:** None

### `ACTIONS.RETURN_FOLLOWER.fn(act)`
* **Description:** Returns a follower to the nearest `kitcoon` den if the doer is near one and the follower is owned by doer.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if successfully added to `kitcoon` den, false otherwise
* **Error states:** None

### `ACTIONS.HIDEANSEEK_FIND.fn(act)`
* **Description:** Searches a hiding spot component and releases the hider.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if successful, false otherwise
* **Error states:** None

### `ACTIONS.DRAW.stroverridefn(act)`
* **Description:** Generates a dynamic action string when drawing on an entity with a drawing tool.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** formatted string with item name or nil
* **Error states:** None

### `ACTIONS.DRAW.fn(act)`
* **Description:** Handles drawing an image onto a target entity using a drawing tool.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if successful, false or `NOIMAGE` error otherwise
* **Error states:** `NOIMAGE`

### `ACTIONS.STARTCHANNELING.strfn(act)`
* **Description:** Returns `PUMP` action string if target has `pump` tag.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** `"PUMP"` or nil
* **Error states:** None

### `ACTIONS.STARTCHANNELING.fn(act)`
* **Description:** Starts channeling on the target entity.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `StartChanneling` (true/false) or nil
* **Error states:** None

### `ACTIONS.STOPCHANNELING.fn(act)`
* **Description:** Stops channeling on the target entity.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true
* **Error states:** None

### `ACTIONS.START_CHANNELCAST.strfn(act)`
* **Description:** Returns `LIGHTER` action string if `invobject` has `lighter` tag.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** `"LIGHTER"` or nil
* **Error states:** None

### `ACTIONS.START_CHANNELCAST.fn(act)`
* **Description:** Starts channel casting using `channelcaster` component, handling both off-hand and equipped item casting.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `StartChanneling` or false
* **Error states:** `ITEMMIMIC`

### `ACTIONS.STOP_CHANNELCAST.strfn(act)`
* **Description:** Delegates to `START_CHANNELCAST.strfn`.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `START_CHANNELCAST.strfn`
* **Error states:** None

### `ACTIONS.STOP_CHANNELCAST.fn(act)`
* **Description:** Stops channel casting if user is channeling on the item.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true
* **Error states:** `ITEMMIMIC`

### `ACTIONS.BUNDLE.fn(act)`
* **Description:** Starts bundling an item using `bundler` component, with silent fail for darkness.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `StartBundling` or true
* **Error states:** None

### `ACTIONS.WRAPBUNDLE.fn(act)`
* **Description:** Finishes bundling if target bundle container is not empty; says fail string otherwise.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true
* **Error states:** `EMPTY`

### `ACTIONS.UNWRAP.fn(act)`
* **Description:** Unwraps an `unwrappable` item if it is marked as `canbeunwrapped`.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true
* **Error states:** None

### `ACTIONS.PEEKBUNDLE.fn(act)`
* **Description:** Peeks inside a bundling container if conditions (`canpeek`, no fire) are met.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `PeekInContainer` or nil
* **Error states:** None

### `ACTIONS.BREAK.strfn(act)`
* **Description:** Returns `PICKAPART` action string if target has `pickapart` tag.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** `"PICKAPART"` or nil
* **Error states:** None

### `ACTIONS.CONSTRUCT.stroverridefn(act)`
* **Description:** Generates a dynamic action string when constructing a prefab using `constructionname`.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** formatted string with construction name or nil
* **Error states:** None

### `ACTIONS.CONSTRUCT.strfn(act)`
* **Description:** Returns action type string (`OFFER`, `STORE`, `OFFER_TO`, `REPAIR`, `REBUILD`) based on target tags.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** one of `OFFER`, `STORE`, `OFFER_TO`, `REPAIR`, `REBUILD` or nil
* **Error states:** None

### `ACTIONS.CONSTRUCT.fn(act)`
* **Description:** Starts construction using `constructionbuilder`, handles item storage into construction container, supports `constructionplans`.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true or false with reason (`INUSE`/`BURNT`)
* **Error states:** None

### `ACTIONS.STOPCONSTRUCTION.stroverridefn(act)`
* **Description:** Generates dynamic action string for stopping construction.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** formatted string with construction name or nil
* **Error states:** None

### `ACTIONS.STOPCONSTRUCTION.strfn(act)`
* **Description:** Returns stop construction action type string (`OFFER`, `REPAIR`, `REBUILD`) based on target tags.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** one of `OFFER`, `REPAIR`, `REBUILD` or nil
* **Error states:** None

### `ACTIONS.STOPCONSTRUCTION.fn(act)`
* **Description:** Stops current construction via `constructionbuilder` component.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true
* **Error states:** None

### `ACTIONS.APPLYCONSTRUCTION.strfn(act)`
* **Description:** Returns apply construction action type string (`OFFER`, `REPAIR`, `REBUILD`) based on target tags.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** one of `OFFER`, `REPAIR`, `REBUILD` or nil
* **Error states:** None

### `ACTIONS.APPLYCONSTRUCTION.fn(act)`
* **Description:** Finishes construction if container is not empty, otherwise says fail string.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true
* **Error states:** `EMPTY`

### `ACTIONS.CASTAOE.stroverridefn(act)`
* **Description:** Returns spell name from `spellbook` if available.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** spell name or nil
* **Error states:** None

### `ACTIONS.CASTAOE.strfn(act)`
* **Description:** Returns uppercase prefab name of the AOE spell item.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** prefab name string or nil
* **Error states:** None

### `ACTIONS.CASTAOE.fn(act)`
* **Description:** Casts an AOE spell using `aoespell` component, checks `CanCast` before `CastSpell`.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `CastSpell` or false
* **Error states:** `ITEMMIMIC`

### `ACTIONS.SCYTHE.fn(act)`
* **Description:** Calls `DoScythe` method on the scythe item to harvest entities.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if successful, false otherwise
* **Error states:** `ITEMMIMIC`

### `ACTIONS.NABBAG.fn(act)`
* **Description:** Calls `DoNabFromAct` on `nabbag` component to pick up items in cone.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `DoNabFromAct` or false
* **Error states:** `ITEMMIMIC`

### `ACTIONS.DISMANTLE.fn(act)`
* **Description:** Dismantles a portable structure after checking container state and burning status.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if dismantled, false with reason (`INUSE`/`NOTEMPTY`/`COOKING`)
* **Error states:** `INUSE`, `NOTEMPTY`, `COOKING`

### `ACTIONS.TACKLE.fn(act)`
* **Description:** Starts tackle action using `tackler` component.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `StartTackle` or nil
* **Error states:** None

### `ACTIONS.HALLOWEENMOONMUTATE.fn(act)`
* **Description:** Mutates a target entity using `halloweenpotionmoon` component, avoiding burnable/frozen targets.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if mutated, false otherwise
* **Error states:** None

### `ACTIONS.APPLYPRESERVATIVE.strfn(act)`
* **Description:** Returns `SALT` action string if preservative item is saltrock.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** `"SALT"` or nil
* **Error states:** None

### `ACTIONS.APPLYPRESERVATIVE.fn(act)`
* **Description:** Applies preservative effect to a target item, adjusting percent by stack size if configured.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if successful, false otherwise
* **Error states:** None

### `ACTIONS.COMPARE_WEIGHABLE.fn(act)`
* **Description:** Compares a weighable item against a trophy scale using component tags and weight types.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `TrophyScale.Compare` or false
* **Error states:** None

### `ACTIONS.WEIGH_ITEM.fn(act)`
* **Description:** Weights an item using `itemweigher` component on either the target or the item itself.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `DoWeighIn` or false
* **Error states:** None

### `ACTIONS.START_CARRAT_RACE.fn(act)`
* **Description:** Starts a carrat race via `yotc_racestart` component, checks racer count, and schedules talker message.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if started, false with reason (`NO_RACERS`)
* **Error states:** `NO_RACERS`

### `ACTIONS.TILL.fn(act)`
* **Description:** Tills soil using `farmtiller` or `quagmire_tiller` components.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** result of `Till` or false
* **Error states:** `ITEMMIMIC`

### `ACTIONS.PLANTSOIL.fn(act)`
* **Description:** Plants a seed on soil using `farmplantable` or `quagmire_plantable` components.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if planted, false otherwise
* **Error states:** None

### `ACTIONS.INSTALL.fn(act)`
* **Description:** Installs a quagmire installable or salt extractor on a compatible target.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if installed, false otherwise
* **Error states:** None

### `ACTIONS.TAPTREE.fn(act)`
* **Description:** Taps or untaps a quagmire tappable tree.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** true if tapped/untapped, false otherwise
* **Error states:** None

### `ACTIONS.TAPTREE.strfn(act)`
* **Description:** Returns `UNTAP` action string if target lacks `tappable` tag.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** `"UNTAP"` or nil
* **Error states:** None

### `ACTIONS.SLAUGHTER.stroverridefn(act)`
* **Description:** Delegates to item's `GetSlaughterActionString` method if available.
* **Parameters:**
  - `act` -- Action object containing doer, target, `invobject`, and action metadata
* **Returns:** string from `GetSlaughterActionString` or nil
* **Error states:** None

### `GetLowerSailStr(act)`
* **Description:** Selects the appropriate string index for `LOWER_SAIL_BOOST` and `LOWER_SAIL_FAIL` actions based on doer's `switchtoho` tag.
* **Parameters:**
  - `act` -- Action object containing doer, target, and context; used to determine string index based on `switchtoho` tag
* **Returns:** String index (1 or 2) for `STRINGS.ACTIONS.LOWER_SAIL_BOOST`
* **Error states:** None

### `IsBoatCannonAmmo(item)`
* **Description:** Validates if an item qualifies as boat cannon ammunition by checking required properties and tags.
* **Parameters:**
  - `item` -- Item to check; must have `projectileprefab` property and `boatcannon_ammo` tag
* **Returns:** Boolean indicating if item is valid cannon ammo
* **Error states:** None

### `ASSESSPLANTHAPPINESS.stroverridefn(act)`
* **Description:** Generates a display string for assessing plant happiness, using the target's display name and format string.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject, etc.
* **Returns:** formatted string or nil
* **Error states:** None

### `ASSESSPLANTHAPPINESS.fn(act)`
* **Description:** Performs plant happiness assessment, checking for item mimic and calling `GetStressDescription` or default description.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true on success, false otherwise
* **Error states:** target missing or `act.invobject` has `itemmimic` component

### `PLANTWEED.fn(act)`
* **Description:** Spawns a random weed at the target soil position and removes the target entity.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true on success
* **Error states:** target missing or not soil-tagged

### `ADDCOMPOSTABLE.fn(act)`
* **Description:** Adds the `invobject` as compostable to the target composting bin.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** return value of `AddCompostable`, or nil if missing component
* **Error states:** target missing or no `compostingbin` component

### `WAX.fn(act)`
* **Description:** Applies wax from `invobject` to target using `waxable` component.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** result of `Wax` call or false
* **Error states:** `invobject` has `itemmimic` component

### `UNLOAD_WINCH.fn(act)`
* **Description:** Calls the `unloadfn` of the winch component on target.
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** return value of `unloadfn`, or nil if missing components
* **Error states:** target missing winch component or `unloadfn`

### `USE_HEAVY_OBSTACLE.strfn(act)`
* **Description:** Returns the string key for heavy obstacle use from target.
* **Parameters:**
  - `act` -- action object containing target
* **Returns:** `target.use_heavy_obstacle_string_key` or nil
* **Error states:** None

### `USE_HEAVY_OBSTACLE.fn(act)`
* **Description:** Uses a heavy obstacle equipped on `BODY` slot to interact with a target if conditions are met.
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** result of `UseHeavyObstacle` or false
* **Error states:** no heavy item equipped, target missing `can_use_heavy` tag, or filter returns false

### `YOTB_SEW.fn(act)`
* **Description:** Starts or resumes sewing on a sewing machine target.
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** true if already sewing or started, false otherwise
* **Error states:** target not sewing machine, container in use by other, or cannot sew

### `YOTB_STARTCONTEST.fn(act)`
* **Description:** Starts a contest if conditions are met (no active contest, host visible check).
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** true if started, false otherwise with reason
* **Error states:** stagemanager missing, contest active, or host visibility mismatch

### `YOTB_UNLOCKSKIN.fn(act)`
* **Description:** Unlocks a skin from a skin unlocker item for the player.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true if unlocked, false otherwise with reason
* **Error states:** missing components or skin already known

### `MUTATE_SPIDER.fn(act)`
* **Description:** Mutates a spider using a spider mutator item.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true on success, false otherwise with reason
* **Error states:** cannot mutate target (same type or already mutation target)

### `HERD_FOLLOWERS.fn(act)`
* **Description:** Herdes followers using a follower herder item.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true on success, false otherwise with reason
* **Error states:** cannot herd (`canherd` check fails)

### `BEDAZZLE.fn(act)`
* **Description:** Bedazzles a target using a bedazzler item.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true on success, false otherwise with reason
* **Error states:** cannot bedazzle (target already bedazzled, etc.)

### `REPEL.fn(act)`
* **Description:** Repels followers using a repellent item.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true on success, false if no repellent component
* **Error states:** missing repellent component

### `ADVANCE_TREE_GROWTH.fn(act)`
* **Description:** Grows a target tree using a tree growth solution item.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** result of `GrowTarget`, or false
* **Error states:** target missing or no `treegrowthsolution` component

### `DISMANTLE_POCKETWATCH.fn(act)`
* **Description:** Dismantles a pocketwatch target using a dismantler item.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** `can_dismantle` status, reason if failed
* **Error states:** cannot dismantle (cooldown or conditions)

### `STOP_LIFT_DUMBBELL.fn(act)`
* **Description:** Pushes `stopliftingdumbbell` event to doer.
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** nil
* **Error states:** None

### `LIFT_DUMBBELL.fn(act)`
* **Description:** Starts lifting a dumbbell using dumbbelllifter component.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true on success, false otherwise with reason
* **Error states:** dumbbell has `itemmimic`, missing lifter component, or cannot lift

### `ENTER_GYM.fn(act)`
* **Description:** Enters a gym and starts a workout if possible.
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** true if entered successfully, false otherwise with reason
* **Error states:** missing components, cannot workout

### `LIFT_GYM_FAIL.pre_action_cb(act)`
* **Description:** Plays a fail bell sound if `doer.bell` exists, and pushes `lift_gym` event on client.
* **Parameters:**
  - `act` -- action object containing doer
* **Returns:** nil
* **Error states:** None

### `LIFT_GYM_FAIL.fn(act)`
* **Description:** Action function that always returns true.
* **Parameters:**
  - `act` -- action object
* **Returns:** true
* **Error states:** None

### `LIFT_GYM_SUCCEED_PERFECT.pre_action_cb(act)`
* **Description:** Plays a perfect bell sound if `doer.bell` exists.
* **Parameters:**
  - `act` -- action object containing doer
* **Returns:** nil
* **Error states:** None

### `LIFT_GYM_SUCCEED_PERFECT.fn(act)`
* **Description:** Action function that always returns true.
* **Parameters:**
  - `act` -- action object
* **Returns:** true
* **Error states:** None

### `LIFT_GYM_SUCCEED.pre_action_cb(act)`
* **Description:** Plays a succeed bell sound if `doer.bell` exists.
* **Parameters:**
  - `act` -- action object containing doer
* **Returns:** nil
* **Error states:** None

### `LIFT_GYM_SUCCEED.fn(act)`
* **Description:** Action function that always returns true.
* **Parameters:**
  - `act` -- action object
* **Returns:** true
* **Error states:** None

### `LEAVE_GYM.fn(act)`
* **Description:** Exits the gym using the doer's `strongman` component.
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** true if gym existed and exit called, nil otherwise
* **Error states:** `strongman.gym` missing

### `UNLOAD_GYM.fn(act)`
* **Description:** Unloads weight from the gym target using `mightygym` component.
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** true if target existed, false otherwise
* **Error states:** target missing

### `APPLYMODULE.fn(act)`
* **Description:** Applies an upgrade module from `invobject` to doer using `upgrademodule` components.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true if applied, false otherwise with reason
* **Error states:** missing components or cannot upgrade

### `APPLYMODULE_FAIL.fn(act)`
* **Description:** Speaks a failure string if talker component exists.
* **Parameters:**
  - `act` -- action object containing doer
* **Returns:** true
* **Error states:** None

### `APPLYMODULE_FAIL.stroverridefn(act)`
* **Description:** Returns the `APPLYMODULE` string from `STRINGS.ACTIONS`.
* **Parameters:**
  - `act` -- action object
* **Returns:** `STRINGS.ACTIONS.APPLYMODULE`
* **Error states:** None

### `REMOVEMODULES.fn(act)`
* **Description:** Removes one upgrade module from doer using `upgrademoduleremover` and adjusts charge.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true if removed, false otherwise with reason
* **Error states:** missing components or no modules present

### `REMOVEMODULES_FAIL.fn(act)`
* **Description:** Speaks a failure string if talker component exists.
* **Parameters:**
  - `act` -- action object containing doer
* **Returns:** true
* **Error states:** None

### `REMOVEMODULES_FAIL.stroverridefn(act)`
* **Description:** Returns the `REMOVEMODULES` string from `STRINGS.ACTIONS`.
* **Parameters:**
  - `act` -- action object
* **Returns:** `STRINGS.ACTIONS.REMOVEMODULES`
* **Error states:** None

### `CHARGE_FROM.strfn(act)`
* **Description:** Returns string indicating whether charging from item or self.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** `ITEM`, `SELF`, or nil
* **Error states:** None

### `CHARGE_FROM.fn(act)`
* **Description:** Charges from a battery target using a `batteryuser` component.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** result of `ChargeFrom`, or false
* **Error states:** target missing battery component or no `batteryuser` component on `doer/invobject`

### `ROTATE_FENCE.fn(act)`
* **Description:** Rotates a fence target using `fencerotator` component.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true on success, false otherwise
* **Error states:** `invobject` missing or `itemmimic` or `fencerotator` missing

### `USEMAGICTOOL.fn(act)`
* **Description:** Starts using a magical tool via `magician` component.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** result of `StartUsingTool`, or false
* **Error states:** `magician` component missing or `itemmimic` present

### `STOPUSINGMAGICTOOL.fn(act)`
* **Description:** Stops using the current magical tool via `magician` component.
* **Parameters:**
  - `act` -- action object containing doer
* **Returns:** true
* **Error states:** None

### `USESPELLBOOK.strfn(act)`
* **Description:** Returns appropriate string key based on player tags or item tags for spellbook usage.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** `PYROKINESIS`, `REMOTE`, `WOBY`, `GHOSTTALK`, or nil
* **Error states:** None

### `USESPELLBOOK.pre_action_cb(act)`
* **Description:** Pre-action callback that opens spellbook UI and handles HUD state.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** nil
* **Error states:** None

### `USESPELLBOOK.fn(act)`
* **Description:** Finalizes spellbook usage: returns active item, closes chests, resets steering wheel/cannon.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true if item not `fueldepleted`, or if targeting a valid non-item object
* **Error states:** None

### `CLOSESPELLBOOK.strfn(act)`
* **Description:** Returns appropriate string key for closing spellbook UI.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** `PYROKINESIS`, `REMOTE`, or `GHOSTTALK`, or nil
* **Error states:** None

### `CLOSESPELLBOOK.pre_action_cb(act)`
* **Description:** Pre-action callback that closes the spell wheel HUD if open.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** nil
* **Error states:** None

### `CLOSESPELLBOOK.fn(act)`
* **Description:** Finalizes spellbook closing action; always succeeds.
* **Parameters:**
  - `act` -- action object
* **Returns:** true
* **Error states:** None

### `CAST_SPELLBOOK.fn(act)`
* **Description:** Casts a spell from a spellbook item or from doer themselves.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** result of `CastSpell`, or nil
* **Error states:** spellbook not useable by doer or target mismatch

### `SITON.fn(act)`
* **Description:** Completes sitting action on a `sittable` target if state and conditions match.
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** true if occupied, nil otherwise
* **Error states:** wrong state, missing `sittable`, or target occupied

### `USE_WEREFORM_SKILL.fn(act)`
* **Description:** Calls `UseWereFormSkill` on doer.
* **Parameters:**
  - `act` -- action object
* **Returns:** result of `UseWereFormSkill`, or false if doer missing
* **Error states:** doer missing

### `REMOTE_TELEPORT.stroverridefn(act)`
* **Description:** Generates a display string for remote teleport using item name.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** formatted string or nil
* **Error states:** None

### `REMOTE_TELEPORT.fn(act)`
* **Description:** Activates and performs remote teleport using `remoteteleporter` component.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** success, reason from `Teleport`, or false
* **Error states:** `invobject` missing, `remoteteleporter` missing, cannot activate, or `itemmimic` present

### `INCINERATE.fn(act)`
* **Description:** Incinerates target using `incinerator` component.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** result of `Incinerate`, or false
* **Error states:** target missing `incinerator` component

### `BOTTLE.fn(act)`
* **Description:** Bottles target using bottler component on `invobject`.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** return value of `Bottle`, or nil
* **Error states:** `invobject` missing or `bottler` component missing

### `CARVEPUMPKIN.fn(act)`
* **Description:** Begins carving a pumpkin or pumpkin hat if conditions are met.
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** true on success, false otherwise with reason
* **Error states:** no `carvable` component, cannot begin, not visible, or someone else holding it

### `DECORATESNOWMAN.strfn(act)`
* **Description:** Returns string for snowman decoration based on inventory state.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** `STACK` or nil
* **Error states:** None

### `DECORATESNOWMAN.fn(act)`
* **Description:** Starts decorating or stacking items onto a snowman target.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** true on success, false otherwise with reason
* **Error states:** missing components, can't begin, not visible, or stack conditions failed

### `START_PUSHING.strfn(act)`
* **Description:** Returns string key for pushing action based on target tag.
* **Parameters:**
  - `act` -- action object containing target
* **Returns:** `ROLL` or nil
* **Error states:** None

### `START_PUSHING.fn(act)`
* **Description:** Starts pushing a target using `pushable` component.
* **Parameters:**
  - `act` -- action object containing doer, target
* **Returns:** true on success, nil otherwise
* **Error states:** target missing `pushable` or already pushing

### `APPLYELIXIR.stroverridefn(act)`
* **Description:** Returns appropriate string for elixir application based on target tag.
* **Parameters:**
  - `act` -- action object containing doer, target, invobject
* **Returns:** formatted `DRINK` or `APPLY` string, or nil
* **Error states:** None

### `find_elixirable_fn(item)`
* **Description:** Helper function to determine if an item has the `ghostlyelixirable` component.
* **Parameters:**
  - `item` -- Entity to check for `ghostlyelixirable` component
* **Returns:** boolean indicating presence of `ghostlyelixirable` component
* **Error states:** None

### `ACTIONS.APPLYELIXIR.fn(act)`
* **Description:** Executes ghost elixir application logic: attempts direct application to target tagged with 'elixir_drinker' or finds an elixirable item in doer's inventory.
* **Parameters:**
  - `act` -- Action table containing doer, target, and invobject entities
* **Returns:** true on success, false with reason string on failure
* **Error states:** `TOO_SUPER` for super elixirs on `elixir_drinker` targets, `NO_ELIXIRABLE` when no eligible item found

### `ACTIONS.GRAVEDIG.fn(act)`
* **Description:** Performs grave digging: triggers `gravedigger` OnUsed and `gravediggable` DigUp functions.
* **Parameters:**
  - `act` -- Action table with doer, target, and invobject
* **Returns:** success boolean and optional reason string
* **Error states:** None

### `ACTIONS.MUTATE.stroverridefn(act)`
* **Description:** Provides dynamic string override for the MUTATE action by fetching the target name via `getghostgestalttarget` callback.
* **Parameters:**
  - `act` -- Action table with target and doer entities
* **Returns:** Formatted string or nil
* **Error states:** None

### `ACTIONS.MUTATE.fn(act)`
* **Description:** Executes ghost gestalt mutation via `ghostgestalter` DoMutate function.
* **Parameters:**
  - `act` -- Action table with doer and target entities
* **Returns:** success boolean and optional reason string
* **Error states:** None

### `ACTIONS.WOBY_PICKUP.fn(act)`
* **Description:** Handles special pickup logic for Woby: validates eligibility (`canbepickedup`, `grabbableoverridetag`), checks restrictions, and moves item to container.
* **Parameters:**
  - `act` -- Action table with doer and target entities
* **Returns:** true on success, false with reason on failure
* **Error states:** restriction, `INUSE`, `NOTMINE_YOTC`, `NO_HEAVY_LIFTING`

### `ACTIONS.WOBY_PICK.validfn(act)`
* **Description:** Validates Woby pick action: checks for active forager target or unpickable pickable component.
* **Parameters:**
  - `act` -- Action table with doer and target entities
* **Returns:** boolean validity result
* **Error states:** None

### `ACTIONS.WOBY_PICK.fn(act)`
* **Description:** Performs single-item harvesting from pickable entity and launches loot projectiles.
* **Parameters:**
  - `act` -- Action table with doer and target entities
* **Returns:** true if loot spawned, false otherwise
* **Error states:** None

### `ACTIONS.CONTAINER_INSTALL_ITEM.strfn(act)`
* **Description:** Returns action label for installing/uninstalling items into containers, detecting if item is currently held by the container.
* **Parameters:**
  - `act` -- Action table with invobject and doer entities
* **Returns:** String 'UNINSTALL' or nil
* **Error states:** None

### `ACTIONS.CONTAINER_INSTALL_ITEM.pre_action_cb(act)`
* **Description:** Pre-action callback that plays sound feedback for invalid container install/uninstall attempts.
* **Parameters:**
  - `act` -- Action table with doer, invobject, and container details
* **Returns:** nil
* **Error states:** None

### `ACTIONS.CONTAINER_INSTALL_ITEM.fn(act)`
* **Description:** Executes item installation/uninstallation between inventory and containers with support for specific slots and full container checks.
* **Parameters:**
  - `act` -- Action table with doer, invobject, and target container
* **Returns:** true on success, false otherwise
* **Error states:** None

### `ACTIONS.MODSLINGSHOT.fn(act)`
* **Description:** Attempts to open slingshot modding UI using a valid slingshot item, preferring equipped or active inventory.
* **Parameters:**
  - `act` -- Action table with doer and invobject
* **Returns:** Result from `slingshotmodder` StartModding or `NOSLINGSHOT` error
* **Error states:** `NOSLINGSHOT` if no valid slingshot found

### `ACTIONS.STOPMODSLINGSHOT.fn(act)`
* **Description:** Closes the slingshot modding UI by calling `StopModding` on the modder component.
* **Parameters:**
  - `act` -- Action table with doer and invobject
* **Returns:** Result from `slingshotmodder` StopModding or false
* **Error states:** None

### `ACTIONS.DASH.fn(act)`
* **Description:** Orients the doer entity toward the action point.
* **Parameters:**
  - `act` -- Action table with action point target
* **Returns:** true on successful point targeting, false otherwise
* **Error states:** None

### `ACTIONS.WHISTLE.fn(act)`
* **Description:** Recalls the Woby companion if the doer has the `woby_commands_classified` component.
* **Parameters:**
  - `act` -- Action table with doer entity
* **Returns:** true if recall initiated, false otherwise
* **Error states:** None

### `ACTIONS.DRAW_FROM_DECK.fn(act)`
* **Description:** Draws the top card from a deck and gives it to the doer's inventory, handling overflow.
* **Parameters:**
  - `act` -- Action table with doer and target deck container
* **Returns:** true on success, false otherwise
* **Error states:** None

### `ACTIONS.FLIP_DECK.fn(act)`
* **Description:** Flips the deck or card visually and plays a UI sound.
* **Parameters:**
  - `act` -- Action table with doer and invobject (deck or card)
* **Returns:** true on success, false otherwise
* **Error states:** None

### `ACTIONS.ADD_CARD_TO_DECK.fn(act)`
* **Description:** Adds a playing card to a deck or merges two cards/decks into a new deck.
* **Parameters:**
  - `act` -- Action table with doer, invobject, and target
* **Returns:** true on successful merge, false otherwise
* **Error states:** None

### `ACTIONS.POUNCECAPTURE.fn(act)`
* **Description:** Captures a target entity using a gestalt cage, checking for mimics and valid targets.
* **Parameters:**
  - `act` -- Action table with doer, target, and invobject (gestalt cage)
* **Returns:** Result of `gestaltcage` Capture or false
* **Error states:** `ITEMMIMIC` if item is a mimic

### `ACTIONS.DIVEGRAB.fn(act)`
* **Description:** Catches a target entity using a moonstorm static catcher, checking for mimics and target validity.
* **Parameters:**
  - `act` -- Action table with doer, target, and invobject (moonstorm catcher)
* **Returns:** Result of `moonstormstaticcatcher` Catch or false
* **Error states:** `ITEMMIMIC` if item is a mimic

### `ACTIONS.STARTELECTRICLINK.fn(act)`
* **Description:** Toggles linking mode on an electric connector: ends linking if already linking, otherwise starts linking.
* **Parameters:**
  - `act` -- Action table with target fence entity
* **Returns:** Result of `StartLinking`/`EndLinking` or false
* **Error states:** None

### `ACTIONS.ENDELECTRICLINK.fn(act)`
* **Description:** Terminates all electric links from a connector by calling `Disconnect`.
* **Parameters:**
  - `act` -- Action table with target fence entity
* **Returns:** Result of `Disconnect` or false
* **Error states:** None

### `ACTIONS.REMOVELUNARBUILDUP.fn(act)`
* **Description:** Removes lunar hail buildup by performing work, with support for instant clearing via doer flag.
* **Parameters:**
  - `act` -- Action table with doer, target (lunar buildup entity), and invobject
* **Returns:** true on success, false otherwise
* **Error states:** `ITEMMIMIC` if item is a mimic

### `ACTIONS.REMOVELUNARBUILDUP.validfn(act)`
* **Description:** Validates lunar buildup removal: ensures target has `lunarhailbuildup` component and item restrictions allow usage.
* **Parameters:**
  - `act` -- Action table with target and invobject
* **Returns:** boolean validity result
* **Error states:** None

### `ACTIONS.SOAKIN.fn(act)`
* **Description:** Attempts to enter a bathing pool via `BathingPool` `EnterPool` function.
* **Parameters:**
  - `act` -- Action table with doer and target bathing pool
* **Returns:** Result of `EnterPool` or nil
* **Error states:** None

### `ACTIONS.TRANSFER_CRITTER.fn(act)`
* **Description:** Transfers a critter from the doer's leash to a nearby hermit crab with available space.
* **Parameters:**
  - `act` -- Action table with doer and target critter
* **Returns:** true on success, false otherwise
* **Error states:** None

### `ACTIONS.JOUST.fn(act)`
* **Description:** Validates jousting readiness: checks `joustuser` and `joustsource` components, and mimic status.
* **Parameters:**
  - `act` -- Action table with doer and invobject (joust source)
* **Returns:** Result of `joustuser` `CanJoust` or nil
* **Error states:** `ITEMMIMIC` if item is a mimic

## Events & listeners
* **Listens to:**
  - `player_despawn` -- Used in Container component to handle cleanup when player despawns
  - `onremove` -- Listened by boat magnet, boat magnet beacon, and steering wheel components to handle entity removal
  - `death` -- Listened by boat magnet to handle beacon death
  - `onturnon` -- Listened by boat magnet to respond to beacon activation
  - `onturnoff` -- Listened by boat magnet to respond to beacon deactivation
  - `stopturning` -- Listened by steering wheel user to handle boat turning cessation
  - `healthdelta` -- Pushed by Health component when health changes
  - `perishchange` -- Pushed by Perishable component when perish percentage changes
  - `dropitem` -- Pushed by Inventory when item is dropped
  - `onlearnednewtacklesketch` -- Pushed after teaching tackle sketch
  - `learnfertilizer` -- Pushed to doer when fertilizer is learned
  - `learnplantstage` -- Pushed to doer when plant is learned
  - `on_lower_sail_boost` -- Pushed when sail lowering boost is applied
  - `ammoloaded` -- Pushed by BoatCannon when ammo is loaded
  - `ammounloaded` -- Pushed by BoatCannon when ammo is unloaded
  - `rotationdirchanged` -- Pushed when boat rotation direction changes
  - `raising_anchor` -- Pushed when anchor starts raising
  - `lowering_anchor` -- Pushed when anchor starts lowering
  - `start_abandoning` -- Pushed immediately when abandoning ship via walking plank
  - `start_extending` -- Pushed immediately when extending walking plank
  - `start_mounting` -- Pushed immediately when mounting walking plank
  - `start_retracting` -- Pushed immediately when retracting walking plank
  - `bathbombable` -- Tag-based event handling in BathBombable component
  - `bathbomb` -- Tag-based event handling in BathBomb component
  - `onbathbombed` -- Called by BathBombable component when bath bombing occurs
  - `is_using_cannon` -- State tag used by SteeringWheelUser for stategraph navigation

* **Pushes:**
  - `onpickupitem` -- Fired by doer when picking up an item, with item data
  - `closecontainer` -- Pushed when closing a container via RUMMAGE action
  - `opencontainer` -- Pushed when opening a container via RUMMAGE action
  - `working` -- Pushed during ROW_FAIL, ROW, OCEAN_FISHING actions to simulate work and potential item drop when wet
  - `talkedto` -- Pushed on target when talkto interaction with maxwelltalker is started
  - `dropitem` -- Pushed internally by container/inventory components when items are dropped (not directly here)
  - `recoil_off` -- Pushed on the doer when recoil is triggered
  - `tooltooweak` -- Pushed on the doer when numworks is zero after recoil
  - `worked` -- Pushed on the target when worked
  - `workfinished` -- Pushed on the target when work is completed
  - `finishedwork` -- Pushed on the doer after completing work
  - `murdered` -- Pushed on doer when cooking something alive
  - `killed` -- Pushed on doer when killing a living item for cooking
  - `CHEVO_fertilized` -- Pushed globally when a pickable is fertilized
  - `CHEVO_starteddrying` -- Pushed globally when drying begins
  - `plantkilled` -- Pushed globally when a plant is killed via work
  - `searched` -- Pushed on searchable entity when searched
  - `picked` -- Pushed on pickable entity when picked
  - `stacksizechange` -- Pushed when stack size changes (in stackable component)
  - `plantwintertreeseed` -- Fired when planting a winter tree seed into a non-burning treestand
  - `wonteatfood` -- Fired when target refuses to eat offered food
  - `onstartedfire` -- Fired by doer when lighting a fire
  - `hitchto` -- Pushed to beefalo to initiate hitching
  - `unhitched` -- Fired by hitcher component when unhitching
  - `haunt` -- Pushed by doer when attempting to haunt a target in `ACTIONS.HAUNT.fn`
  - `onwenthome` -- Pushed by doer if `force_onwenthome_message` is true in `ACTIONS.GOHOME.fn`
  - `onactivated` -- Pushed by `activatable:DoActivate()` after successful activation
  - `attuned` -- Pushed by `attunable:LinkToPlayer()` after linking to player
  - `oneat` -- Pushed by `eater:Eat()` after consuming food
  - `feedincontainer` -- Pushed to feeder when feeding from an open container
  - `feedmount` -- Pushed to rider when feeding their mount
  - `unpinned` -- Pushed by `UNPIN` action when unsticking a pinnable entity
  - `onstolen` -- Pushed by `STEALMOLEBAIT` action when bait is stolen
  - `peek` -- Pushed by `MOLEPEEK` action
  - `trade` -- Pushed by `trader:AcceptGift()` after successful trade
  - `respawnfromghost` -- Pushed by `REMOTERESURRECT` to trigger ghost respawn
  - `respawnfromcorpse` -- Pushed by `revivablecorpse:Revive()` to trigger resurrection
  - `dismount` -- Pushed by `rider:Dismount()`
  - `migration_activate` -- Pushed by `worldmigrator:Activate()` before migration
  - `ms_playerdespawnandmigrate` -- Pushed globally to trigger world migration
  - `gotnewattunement` -- Handled via external `attuner` module (not directly pushed in chunk)
  - `attunementlost` -- Handled via external `attuner` module (not directly pushed in chunk)
  - `saddle` -- Pushed when successfully saddling an entity
  - `healthdelta` -- Fired by `Health` component when health changes
  - `perishchange` -- Fired by `Perishable` component when perish percentage changes
  - `learnfertilizer` -- Fired to doer when fertilizer is learned
  - `learnplantstage` -- Fired to doer when plant is learned
  - `onlearnednewtacklesketch` -- Fired after teaching tackle sketch
  - `on_lower_sail_boost` -- Fired when sail lowering boost is applied
  - `ammoloaded` -- Fired by `BoatCannon` when ammo is loaded
  - `ammounloaded` -- Fired by `BoatCannon` when ammo is unloaded
  - `rotationdirchanged` -- Fired by `BoatRotator` when rotation direction changes
  - `raising_anchor` -- Fired by `Anchor` when anchor starts raising
  - `lowering_anchor` -- Fired by `Anchor` when anchor starts lowering
  - `start_abandoning` -- Immediate event fired by `WalkingPlank` when abandoning ship
  - `start_extending` -- Immediate event fired by `WalkingPlank` when extending
  - `start_mounting` -- Immediate event fired by `WalkingPlank` when mounting
  - `start_retracting` -- Immediate event fired by `WalkingPlank` when retracting
  - `bathbombable` -- Tag event in `BathBombable` component
  - `bathbomb` -- Tag event in `BathBomb` component
  - `onbathbombed` -- Fired by `BathBombable` when