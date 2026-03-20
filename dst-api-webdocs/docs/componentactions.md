---
id: componentactions
title: Componentactions
description: This component defines the core logic for computing valid player interactions based on component presence and entity state, including built-in and modded action handlers across INVENTORY, POINT, and EQUIPPED contexts, with helper functions for rowing, fishing, scything, plant research, and action validation methods for the EntityScript class.
tags: [actions, components, interactions, player, modding]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: b7084665
system_scope: player
---

# Componentactions

> Based on game build **714014** | Last updated: 2026-03-20

## Overview

The `componentactions` module is the central action resolution system for Don't Starve Together, responsible for determining which interactions are available to players based on entity components, tags, and contextual states. It registers action handler functions for hundreds of interaction types including combat, crafting, deployment, storage, feeding, healing, repair, and special equipment actions. The system operates across three primary contexts: INVENTORY (item-to-item interactions), POINT (world position interactions), and EQUIPPED (held item interactions). Each handler function conditionally appends appropriate ACTION constants to an actions list based on component presence, tag checks, component state validation, and player constraints like riding status or heavy lifting. The module also provides core query methods (`CollectActions`, `IsActionValid`, `HasActionComponent`) for the EntityScript class and supports modded components through separate registry tables. This enables the game's contextual action wheel and interaction system to dynamically present valid options to players based on their current situation and target entities.

## Usage example

```lua
-- Check if an entity has a specific action component
if inst:HasActionComponent("inventoryitem") then
    -- Collect all valid inventory actions for this entity
    local actions = {}
    inst:CollectActions("INVENTORY", inst, doer, target, actions, false)
    
    -- Validate if a specific action is permitted
    if inst:IsActionValid(action, right_click) then
        -- Action is valid, proceed with interaction
        doer:DoAction(action)
    end
end

-- Register a modded component action handler
AddComponentAction("EQUIPPED", "mycomponent", MyComponentActionHandler, "mymod")
```

## Dependencies & tags

**External dependencies:**
- `vecutil` -- Provides VecUtil_LengthSq, VecUtil_Normalize, VecUtil_Dist
- `TheWorld` -- Used for map operations: IsOceanAtPoint, IsVisualGroundAtPoint, GetPlatformAtPoint
- `TheNet` -- Used to check if game is dedicated server
- `ThePlayer` -- Used to compare with doer to adjust test_length during rowing
- `ACTIONS` -- Enum-like table of action constants used throughout component actions
- `TUNING` -- Provides constants like OVERRIDE_ROW_ACTION_DISTANCE and KITCOON_NEAR_DEN_DIST
- `ThePlantRegistry` -- Used for plant/fertilizer knowledge checks
- `FindVirtualOceanEntity` -- Called by CanCastFishingNetAtPoint to detect virtual ocean
- `FindEntity` -- Used by Kitcoon handler to detect nearby dens
- `IsEntityDead` -- Used in SCENE.combat to determine if target can be attacked
- `IsInValidHermitCrabDecorArea` -- Used in crittertraits handler to validate decor placement area
- `TROPHYSCALE_TYPES` -- Global constant table used in trophyscale handler to iterate over scale types for comparison
- `FOODGROUP` -- Global constant table used in edible handler to match edible tags to eater tags by food group
- `FOODTYPE` -- Global constant table used in edible handler to match edible tags to eater tags by food type
- `EQUIPSLOTS` -- Global constant used to reference EQUIPSLOTS.BODY for item slot checks
- `SPECIAL_EVENTS` -- Global constant table used in yotb_stager to check if YOTB event is active via IsSpecialEventActive
- `GLOBAL` -- Referenced via TheWorld, TheNet, ThePlayer, AllPlayers, TheSim, TheInput, TUNING, STRINGS, ACTIONS, AllRecipes, GetValidRecipe, IsEntityDead, GetGameModeProperty, CONTROLS, CONTROL_FORCE_STACK, FunctionOrValue, SpawnPrefab, POPUPS, TheCamera, WORLD.isday, easing module, and more
- `LOCKTYPE` -- Used in key action to iterate lock types and match keys
- `OCCUPANTTYPE` -- Used in occupier to match occupant types to occupiable targets
- `MATERIALS` -- Used in repairer and forgerepair to match repair materials
- `FORGEMATERIALS` -- Used in forgerepair to check forgerepair_ tags on inst and target
- `UPGRADETYPES` -- Used in upgrader to match upgrade types and user/target tags
- `TOOLACTIONS` -- Used in tool action to iterate tool action types and match tags (e.g., 'axe_tool')
- `FUELTYPE` -- Used in fuel to iterate fuel types and match _fuel and _fueled tags
- `GetValidRecipe` -- Called to validate recipes for recipescanner action
- `AllRecipes` -- Used in recipescanner to look up recipes by prefab name
- `GetGameModeProperty` -- Used in inventoryitem and other actions to check game mode flags like non_item_equips
- `FunctionOrValue` -- Used in recipescanner to evaluate per-target no_deconstruction configuration
- `SpawnPrefab` -- Referenced in PumpkinHatCarvable module
- `POPUPS` -- Referenced in PumpkinHatCarvable module
- `TheInput` -- Used in playercontroller.IsControlPressed for CONTROL_FORCE_STACK detection
- `CONTROL_FORCE_STACK` -- Referenced in inventoryitem to control GIVEALLTOPLAYER behavior
- `CONTROLS` -- Used to define control constants such as CONTROL_FORCE_STACK
- `easing` -- Referenced in PumpkinCarvable module
- `WORLD.isday` -- Referenced in PumpkinCarvable module
- `SPELLTYPES` -- Iterated for spellcaster tags
- `CLIENT_REQUESTED_ACTION` -- Compared for specific deployment actions
- `CheckRowOverride` -- Used to determine row override for oar actions
- `Row` -- Called to generate rowing action for oar
- `IsTeleportingPermittedFromPointToPoint` -- Called for blink staff teleport validity
- `CanCastFishingNetAtPoint` -- Called for fishing net/cast validity
- `GetFishingAction` -- Called to get contextual fishing action
- `orderedPairs` -- Used to iterate over COMPONENT_ACTIONS and MOD_COMPONENT_ACTIONS tables for remapping
- `AllPlayers` -- Referenced indirectly via player replication and networking
- `TheSim` -- Referenced indirectly via simulation and entity lifecycle
- `dumptable` -- Used for mod debugging to dump modactioncomponents tables
- `COMPONENT_ACTIONS` -- Global table mapping action type names to component action tables
- `ACTION_COMPONENT_NAMES` -- Global table mapping built-in component names to IDs used for indexing
- `CheckModComponentActions` -- Function called to retrieve modded component action tables
- `CheckModComponentNames` -- Function called to retrieve modded component name-to-ID mapping
- `CheckModComponentIds` -- Function called to retrieve modded component IDs by name

**Components used:**
- `attuner` -- Used in SCENE.attunable to call IsAttunedTo on doer
- `boatringdata` -- Used in SCENE.boatrotator and CheckRowOverride to get radius and rotation state
- `constructionbuilderuidata` -- Used in SCENE.container to determine if builder is in use
- `container_proxy` -- Used in SCENE.container_proxy and SCENE.container via replica.container to check CanBeOpened
- `floater` -- Used in SCENE.machine to check if item is floating
- `playercontroller` -- Used in SCENE.ROW and many others to check isclientcontrollerattached, HasAOETargeting, and IsControlPressed
- `skilltreeupdater` -- Used in SCENE.ghostgestalter to check if skill is activated
- `revivablecorpse` -- Used in revivablecorpse action handler via inst.components.revivablecorpse:CanBeRevivedBy(doer)
- `spellbook` -- Used in spellbook action handler via inst.components.spellbook:CanBeUsedBy(doer)
- `rider` -- doer.replica.rider:IsRiding() used to restrict actions while mounted
- `inventoryitem` -- Used to check ownership (IsGrandOwner, IsHeld, IsEquipped) and tags (CanOnlyGoInPocket)
- `container` -- target.replica.container:CanBeOpened() and IsOpenedBy() used to allow storing into containers
- `health` -- target.replica.health:CanHeal() used in healer/maxhealer to validate healability
- `inventory` -- doer.replica.inventory:IsHeavyLifting() used to prevent actions while carrying heavy items
- `equippable` -- target.replica.equippable:IsEquipped() and:IsRestricted(doer) used to check equipping status and restrictions
- `stackable` -- target.replica.stackable:IsFull() and IsStack() used in stackable logic
- `follower` -- target.replica.follower:GetLeader() compared to doer in summoningitem logic
- `builder` -- target.replica.builder present for teacher action (doer==target)
- `pumpkincarvable` -- target.components.pumpkincarvable existence checks for carving (client-safe)
- `pumpkinhatcarvable` -- target.components.pumpkinhatcarvable existence checks for pumpkin hat carving
- `snowmandecoratable` -- target.components.snowmandecoratable existence checks for snowman decoration (client-safe)
- `constructionsite` -- Accessed via target.replica.constructionsite for build actions
- `combat` -- Checked via doer.replica.combat and target.replica.combat for targeting, ally, and attack validity
- `aoetargeting` -- Accessed via inst.components.aoetargeting to check enabled state and constraints
- `fishingrod` -- Accessed via inst.replica.fishingrod to check caught fish and target
- `oceanfishingrod` -- Accessed via inst.replica.oceanfishingrod for ocean fishing target and actions
- `containerinstallableitem` -- Calls GetValidOpenContainer on the item's component
- `singinginspiration` -- Calls IsSongActive to check if song is active

**Tags:**
- `inactive` -- check
- `engineering` -- check
- `portableengineer` -- check
- `activatable_forceright` -- check
- `smolder` -- check
- `fire` -- check
- `anchor_raised` -- check
- `anchor_transitioning` -- check
- `paired` -- check
- `turnedoff` -- check
- `ammoloaded` -- check
- `occupied` -- check
- `is_rowing` -- check
- `is_row_failing` -- check
- `overriderowaction` -- check
- `boat` -- check
- `fishing_idle` -- check
- `projectile` -- check
- `oceanfishing_catchable` -- check
- `fishinghook` -- check
- `plantresearchable` -- check
- `fertilizerresearchable` -- check
- `farmplantstress` -- check
- `weedplantstress` -- check
- `plantinspector` -- check
- `plantkin` -- check
- `reader` -- check
- `controlled_burner` -- check
- `stokeablefire` -- check
- `cancatch` -- check
- `channelable` -- check
- `channeled` -- check
- `burnt` -- check
- `battery` -- check
- `batteryuser` -- check
- `bathingpool` -- check
- `bundle` -- check
- `oceantrawler` -- check
- `trawler_lowered` -- check
- `rider` -- check
- `isriding` -- check
- `pickable` -- check
- `activatable` -- check
- `groundonlymachine` -- check
- `enabled` -- check
- `turnedon` -- check
- `cooldown` -- check
- `fueldepleted` -- check
- `alwayson` -- check
- `emergency` -- check
- `readytocook` -- check
- `minesprung` -- check
- `mine_not_reusable` -- check
- `usingmagiciantool` -- check
- `sailraised` -- check
- `saillowered` -- check
- `sail_transitioning` -- check
- `loaded` -- check
- `strongman` -- check
- `player` -- check
- `hasstrongman` -- check
- `hasoneoftags` -- check
- `catchable` -- check
- `lighter` -- check
- `spider` -- check
- `spiderwhisperer` -- check
- `heavy` -- check
- `heavylift_lmb` -- check
- `is_furling` -- check
- `near_kitcoonden` -- check
- `kitcoonden` -- check
- `unlockable` -- check
- `hastag` -- check
- `marked` -- check
- `hitcher` -- check
- `hitcher_locked` -- check
- `dried` -- check
- `readyforharvest` -- check
- `withered` -- check
- `cancycle` -- check
- `inventoryitemholder_take` -- check
- `tendable_farmplant` -- check
- `mime` -- check
- `fully_electrically_linked` -- check
- `is_electrically_linked` -- check
- `can_use_heavy` -- check
- `markable` -- check
- `markable_proxy` -- check
- `haunted` -- check
- `holdable` -- check
- `craftable` -- check
- `noabandon` -- check
- `trawler_fish_escaped` -- check
- `pinned` -- check
- `intense` -- check
- `portable_campfire` -- check
- `portable_campfire_user` -- check
- `mastercookware` -- check
- `masterchef` -- check
- `craftingenabled` -- check
- `hitched` -- check
- `dogrider_only` -- check
- `dogrider` -- check
- `woby` -- check
- `hassleeper` -- check
- `spiderden` -- check
- `wardrobe` -- check
- `dressable` -- check
- `readyforfeast` -- check
- `waxedplant` -- check
- `unwrappable` -- check
- `interactable` -- check
- `plank_extended` -- check
- `on_walkable_plank` -- check
- `stageactingprop` -- check
- `stageactor` -- check
- `play_in_progress` -- check
- `storytellingprop` -- check
- `storyteller` -- check
- `maxwellnottalking` -- check
- `teleporter` -- check
- `townportal` -- check
- `vault_teleporter` -- check
- `channeling` -- check
- `trapsprung` -- check
- `trophyscale_*` -- check
- `trophycanbetaken` -- check
- `wax` -- check
- `migrator` -- check
- `yotb_conteststartable` -- check
- `has_prize` -- check
- `has_no_prize` -- check
- `race_on` -- check
- `readytosew` -- check
- `cansit` -- check
- `donecooking` -- check
- `takeshelfitem` -- check
- `insomniac` -- check
- `appraiser` -- check
- `canbait` -- check
- `bathbomb` -- check
- `bathbombable` -- check
- `bedazzleable` -- check
- `bedazzled` -- check
- `boat_patch` -- check
- `boat_leak` -- check
- `canbebottled` -- check
- `brushable` -- check
- `carnivalgame_canfeed` -- check
- `cooker` -- check
- `dangerouscooker` -- check
- `expertchef` -- check
- `cookable` -- check
- `playingcard` -- check
- `deckcontainer` -- check
- `drawable` -- check
- `candry` -- check
- `edible_*` -- check
- `*_eater` -- check
- `wereplayer` -- check
- `strongstomach` -- check
- `ignoresspoilage` -- check
- `spoiled` -- check
- `badfood` -- check
- `unsafefood` -- check
- `compostingbin_accepts_items` -- check
- `papereraser` -- check
- `watersource` -- check
- `fishable` -- check
- `soil` -- check
- `NOCLICK` -- check
- `notreadyforharvest` -- check
- `fertile` -- check
- `infertile` -- check
- `barren` -- check
- `fertilizable` -- check
- `self_fertilizable` -- check
- `critter` -- check
- `handfed` -- check
- `small_livestock` -- check
- `fedbyall` -- check
- `follower` -- check
- `edible_ELEMENTAL` -- check
- `edible_GEARS` -- check
- `edible_INSECT` -- check
- `edible_BURNT` -- check
- `DECOR` -- check
- `furnituredecortaker` -- check
- `elixir_drinker` -- check
- `gravediggable` -- check
- `gravedigger_user` -- check
- `alltrader` -- check
- `playerghost` -- check
- `ghost` -- check
- `reviver` -- check
- `boatcannon` -- check
- `boatcannon_ammo` -- check
- `inventoryitemholder_give` -- check
- `INLIMBO` -- check
- `BURNABLE_fueled` -- check
- `BURNABLE_fuel` -- check
- `constructionsite` -- check
- `quagmire_stewable` -- check
- `quagmire_stewer` -- check
- `quagmire_cookwaretrader` -- check
- `vase` -- check
- `vasedecoration` -- check
- `waxable` -- check
- `waxspray` -- check
- `needssewing` -- check
- `saddleable` -- check
- `saddled` -- check
- `tacklestation` -- check
- `canpeek` -- check
- `bearded` -- check
- `moontrader` -- check
- `klaussacklock` -- check
- `klaussackkey` -- check
- `pocketwatch` -- check
- `clockmaker` -- check
- `pocketwatch_mountedcast` -- check
- `pocketwatchcaster` -- check
- `pocketwatch_inactive` -- check
- `souleater` -- check
- `canbeslaughtered` -- check
- `tappable` -- check
- `quagmire_altar` -- check
- `quagmire_replater` -- check
- `quagmire_replatable` -- check
- `quagmire_saltable` -- check
- `saltpond` -- check
- `installations` -- check
- `fullfertile` -- check
- `trader` -- check
- `tree` -- check
- `monster` -- check
- `stump` -- check
- `leif` -- check
- `no_force_grow` -- check
- `LunarBuildup` -- check
- `MINE_tool` -- check
- `fillable` -- check
- `outofammo` -- check
- `rangedweapon` -- check
- `tranquilizer` -- check
- `canlight` -- check
- `nolight` -- check
- `sleeper` -- check
- `container_proxy` -- check
- `structure` -- check
- `weighable_*` -- check
- `winter_treestand` -- check
- `rotatableobject` -- check
- `watersource` -- check
- `gestaltcapturable` -- check
- `burnableignorefuel` -- check
- `lifting` -- check
- `moonstormstaticcapturable` -- check
- `floater` -- check
- `nohighlight` -- check
- `steeringboat` -- check
- `rotatingboat` -- check
- `castonpoint` -- check
- `castonpointwater` -- check
- `castonrecipes` -- check
- `castonlocomotors` -- check
- `castonlocomotorspvp` -- check
- `castonworkable` -- check
- `castoncombat` -- check
- `crushitemcast` -- check
- `plow` -- check
- `fillable_showoceanaction` -- check
- `tile_deploy` -- check
- `deployable` -- check
- `special_action_toss` -- check
- `complexprojectile_showoceanaction` -- check
- `boatbuilder` -- check
- `nomagic` -- check
- `faced_chair` -- check
- `wall` -- check
- `mustforceattack` -- check
- `mole` -- check
- `hammer` -- check
- `needswaxspray` -- check
- `equippable` -- check
- `fertilizer` -- check
- `elixirbrewer` -- check
- `healerbuffs` -- check
- `ghostfriend_notsummoned` -- check
- `ghostfriend_summoned` -- check
- `castfrominventory` -- check
- `pocketwatch_castfrominventory` -- check
- `handyperson` -- check
- `slingshotmodscontainer` -- check
- `walter_slingshot_modding` -- check
- `readable` -- check
- `upgrademoduleowner` -- check
- `inuse` -- check
- `cannotuse` -- check
- `useabletargeteditem_inventorydisable` -- check
- `inuse_targeted` -- check
- `accepts_oceanfishingtackle` -- check
- `broadcasting` -- check
- `invenoryitem` -- check

## Properties

| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|

## Main functions

### `CanCastFishingNetAtPoint(thrower, target_x, target_z)`
* **Description:** Checks if a fishing net can be cast at the given point: requires it to be over ocean or virtual ocean and at least min_throw_distance away from the thrower.
* **Parameters:**
  - `thrower` -- Entity attempting to cast the net; used to get position
  - `target_x` -- World X-coordinate of the target point
  - `target_z` -- World Z-coordinate of the target point
* **Returns:** true if casting is valid, false otherwise

### `Row(inst, doer, pos, actions)`
* **Description:** Generates rowing actions (ROW, ROW_FAIL, ROW_CONTROLLER) based on platform type, player control state, and proximity to water or boat.
* **Parameters:**
  - `inst` -- Ignored; present for signature compatibility
  - `doer` -- Entity (typically player) attempting to row; checked for platform, boat tag, rowing state
  - `pos` -- World position (x,z) of interaction point, used when controller is detached
  - `actions` -- Mutable table into which compatible ACTION constants are inserted
* **Returns:** nil
* **Error states:** Early exit if doer not on a boat, or if controller is attached and position matches current platform

### `PlantRegistryResearch(inst, doer, actions)`
* **Description:** Adds plant registry research and plant stress assessment actions if doer has required tools/tags and target is researchable.
* **Parameters:**
  - `inst` -- Target entity (plant or fertilizer); checked for research tags and registry keys
  - `doer` -- Entity performing the action; checked for plantinspector tag or plantkin, andCanExamine
  - `actions` -- Mutable table into which PLANTREGISTRY_RESEARCH or PLANTREGISTRY_RESEARCH_FAIL and ASSESSPLANTHAPPINESS actions may be inserted
* **Returns:** nil
* **Error states:** No action added if doer lacks plantinspector or plantkin tag, or if target not researchable

### `GetFishingAction(doer, fishing_target)`
* **Description:** Returns the appropriate Ocean Fishing action (OCEAN_FISHING_CATCH, OCEAN_FISHING_REEL, or OCEAN_FISHING_STOP) based on doer state and target.
* **Parameters:**
  - `doer` -- Entity performing fishing; must have fishing_idle tag
  - `fishing_target` -- Fishing hook or catchable entity; checked for oceanfishing_catchable and fishinghook tags
* **Returns:** String action constant or nil if no valid action
* **Error states:** Returns nil if doer not in fishing_idle state or target is projectile or not catchable

### `CheckRowOverride(doer, target)`
* **Description:** Returns true if target has overriderowaction and is within OVERRIDE_ROW_ACTION_DISTANCE of the doer or boat, allowing the override action to supersede normal row.
* **Parameters:**
  - `doer` -- Entity attempting to row; used for position and platform lookup
  - `target` -- Potential override entity (e.g., ocean trawler) with overriderowaction tag
* **Returns:** true if row action should be overridden, false otherwise
* **Error states:** Returns false if doer not on a boat or no valid override target

### `IsValidScytheTarget(target)`
* **Description:** Predicate to validate whether a target is harvestable by a scythe.
* **Parameters:**
  - `target` -- Entity to check; must have one of SCYTHE_ONEOFTAGS tags
* **Returns:** true if target has one of the required tags (plant, lichen, oceanvine, kelp), false otherwise

### `CollectActions(actiontype, ...)`
* **Description:** Iterates over the entity's action components (both built-in and modded), retrieves the corresponding collector function for the given action type, and invokes it. Handles fallbacks for modded components via CheckModComponentActions and CheckModComponentNames.
* **Parameters:**
  - `actiontype` -- string identifier of the action type (e.g., "GATHER", "ATTACK") to collect components for; must exist in COMPONENT_ACTIONS
  - `...` -- variable arguments passed through to each collected collector function
* **Returns:** nil
* **Error states:** Prints an error and returns early if actiontype is not found in COMPONENT_ACTIONS

### `IsActionValid(action, right)`
* **Description:** Determines if the given action is valid for this entity by checking rmb constraints and delegating to ISVALID validators registered in both built-in and modded action components. Returns true on first match.
* **Parameters:**
  - `action` -- Action table with at least an rmb boolean field (right mouse button requirement)
  - `right` -- boolean indicating whether the action was triggered via right mouse button
* **Returns:** boolean -- true if any component's ISVALID validator returns true, otherwise false
* **Error states:** Returns false if no validators match or if modded component lookups fail

### `HasActionComponent(name)`
* **Description:** Checks whether the entity possesses a given action component by ID, first in the built-in list (actioncomponents) and then in modded lists (modactioncomponents).
* **Parameters:**
  - `name` -- string name of the action component (e.g., "inventory", "melee") to check for presence
* **Returns:** boolean -- true if the component is present, otherwise false
* **Error states:** Returns false if the component name is unrecognized (id is nil) or not found in either list

### `AddComponentAction(actiontype, component, fn, modname)`
* **Description:** Registers a mod-provided component action handler, maintaining separate per-mod registries.
* **Parameters:**
  - `actiontype` -- The action type key (e.g., 'INVENTORY', 'WEAPON')
  - `component` -- The component name
  - `fn` -- The callback function
  - `modname` -- The mod identifier
* **Returns:** nil

### `EntityScript:RegisterComponentActions(name)`
* **Description:** Registers a component's ID into the entity's actioncomponents and modactioncomponents arrays.
* **Parameters:**
  - `name` -- The component name to register
* **Returns:** nil

### `EntityScript:UnregisterComponentActions(name)`
* **Description:** Removes a component's ID from the entity's actioncomponents and modactioncomponents arrays.
* **Parameters:**
  - `name` -- The component name to unregister
* **Returns:** nil

### `RemapComponentActions()`
* **Description:** Maps component names to numeric IDs for network efficiency by iterating over COMPONENT_ACTIONS.
* **Parameters:** None
* **Returns:** nil
* **Error states:** Assertion fails if more than 255 unique components

## Events & listeners

**Listens to:** None

**Pushes:** None