---
id: actions
title: Actions
description: A comprehensive registry of game actions in Don't Starve Together, defining their properties, validation logic, and integration with over 100 components to support player and entity interactions, construction, crafting, combat, farming, sailing, and specialized mechanics.
tags: [CLASSIFIED, _upgradeuser, abigail_flower, ancient_reader, ancient_text, balloonomancer, batteryuser, boat_leak, boatbuilder, boatcannon_ammo, bundle, burnt, can_be_bathbombed, can_use_heavy, canbeslaughtered, cannotheal, cannotuse, canpeek, cansee, catchable, character, coach_whistle, coaching, combatmount, constructionsite, controlled_burner, cookable, critterlab, crushitemcast, decoratable, deployable, deployedfarmplant, deploykititem, dogrider, dogrider_only, dressable, drop_inventory_onmurder, drop_inventory_onpickup, elixir_drinker, eyeturret, farm_plant, fencebuilder, fertilizer, fertilizerresearchable, fire, fogrevealer, fooddrink, fresh, frozen, fueldepleted, furnituredecortaker, gatebuilder, gemsocket, ghostlyelixir, ghostlyelixirable, globalmapicon, globalmapicon_player, graveplanter, groundtile, hammer, handyperson, has_aggressive_follower, hasemergencymode, haunted, heavy, hermitcrab, inventoryitemholder_give, is_using_cannon, kitcoonden, lighter, mapspotrevealer, master_crewman, masterchef, mastercookware, merm, mermonly, mightiness_normal, mine, moontrader, near_kitcoonden, offerconstructionsite, overridelocomote, pet_treat, pickapart, playbill_lecturn, player, playerfloater, playerghost, pocketwatchcaster, portableitem, projectile, propweapon, pump, pushing_roll, pyromaniac, quagmire_altar, quagmire_replatable, quagmire_salted, quagmire_stewer, race_on, rebuildconstructionsite, recipescanner, reloaditem_ammo, repairable_moon_altar, repairable_vitae, repairconstructionsite, scrapbook_data, scrapbook_note, sewingmachine, singingshell, smashable, smolder, soil, soul, souljar, soulstealer, special_action_toss, spicer, spider, spiderwhisperer, spoiled, stale, stewer, stokeablefire, super_elixir, switchtoho, tappable, teleporter, tentacle_pillar, trader_just_show, trader_repair, trap, trophycanbetaken, trophyscale_*, unwrappable, usedeploystring, virtualocean, wallbuilder, watersource, weighable_*, whackable, winter_treestand, wintersfeasttable, withered, wolfgang_coach, wormhole]
sidebar_position: 10

last_updated: 2026-03-13
build_version: 714014
change_status: stable
category_type: root
source_hash: 82eee1ae
system_scope: inventory
---

# Actions

> Based on game build **714014** | Last updated: 2026-03-13

## Overview

The `actions.lua` file constitutes the central action registry for Don't Starve Together, defining how all interactive gameplay behaviors are structured, validated, and executed. It implements an Entity Component System–style framework where actions are registered with metadata (e.g., `priority`, `distance`, `canforce`, `map_action`), associated with component-specific handlers, and coordinated with input, UI, and stategraph systems. Each action includes a primary function (`.fn`) for behavior and optional helper functions (`.strfn`, `.stroverridefn`, `.theme_music_fn`, `.pre_action_cb`) for UI localization, audio cues, and pre-execution validation. Actions may support map-based targeting, platform-relative range checks, ghost/mount/exclusive modes, and tile placement. Over 200 action variants are defined—covering fundamental interactions like `PICKUP`, `DROP`, `EAT`, `ATTACK`, and `LOOKAT`, through advanced mechanics such as AoE spell casting, boat navigation, construction building, plant tending, and specialized Quagmire, YOTB, and YOTC systems—each with precise integration into components like `workable`, `deployable`, `steeringwheeluser`, `spellcaster`, `questowner`, `upgrademoduleowner`, `fertilizer`, `combat`, and many more. The system enforces safety checks for item ownership, stategraph restrictions, platforming context, and visibility while supporting modding through action remapping and custom components.

## Usage example

```lua
-- Example: Registering a custom action that works on soil with map targeting
ACTIONS.MY_CUSTOM_ACTION = Action(
    "MY_CUSTOM_ACTION",
    function(act)
        local target = act.target
        if target == nil or not target:HasTag("soil") then
            return false
        end
        -- Perform custom behavior
        target:PushEvent("my_custom_event")
        return true
    end,
    "my_custom_action"
)

-- Set action properties
ACTIONS.MY_CUSTOM_ACTION.priority = 100
ACTIONS.MY_CUSTOM_ACTION.map_action = true
ACTIONS.MY_CUSTOM_ACTION.is_relative_to_platform = false
ACTIONS.MY_CUSTOM_ACTION.rangecheckfn = function(doer, target) return true end
ACTIONS.MY_CUSTOM_ACTION.pre_action_cb = function(act) end
```

## Dependencies & tags
**Components used:**
- `appraisable` -- Used in APPRAISE action for CanAppraise and Appraise methods
- `balloonmaker` -- Used in MAKEBALLOON action for spawning balloons
- `burnable` -- Used in PICKUP to prevent burning pickup
- `container` -- Used in RUMMAGE, DROP, STEAL, and related logic for container operations
- `container_proxy` -- Used in RUMMAGE for proxy container handling
- `crewmember` -- Used in ROW handler for non-oar rowing
- `curseditem` -- Used in PICKUP to check player space for cursed items
- `dryer` -- Used in STEAL for dropping items
- `eater` -- Used in EAT action for eating food
- `edible` -- Used in EAT action
- `entitytracker` -- Used in PICKUP for YOTC trainer checks
- `equippable` -- Used in PICKUP, UNEQUIP, and DROP actions
- `farmplanttendable` -- Used in INTERACT_WITH action
- `follower` -- Used in PICKUP to check spider leader
- `forgerepairable` -- Used in REPAIR action
- `fueled` -- Used in SEW action
- `inspectable` -- Used in LOOKAT action
- `inventory` -- Used throughout for inventory manipulation and queries
- `inventoryitem` -- Used for ownership checks and item movement logic
- `itemtyperestrictions` -- Used in PICKUP for item restrictions
- `locomotor` -- Used in LOOKAT and TALKTO actions to stop movement
- `maxwelltalker` -- Used in TALKTO action
- `oar` -- Used in ROW and ROW_FAIL actions
- `oceanfishable` -- Used in EAT and fishing actions
- `oceanfishingrod` -- Used in all ocean fishing actions
- `playercontroller` -- Used in LOOKAT locomotor stop check
- `projectile` -- Used in PICKUP to prevent throwing item pickup
- `reader` -- Used in READ action
- `repairable` -- Used in REPAIR action
- `repairer` -- Used in REPAIR action as material component
- `rideable` -- Used in RUMMAGE and PICKUP to check mount rider
- `rider` -- Used in RUMMAGE and REPAIR actions
- `sanity` -- Used in MAKEBALLOON to consume sanity
- `sewing` -- Used in SEW action
- `simplebook` -- Used in READ action
- `skilltreeupdater` -- Used in RUMMAGE for soul jar check
- `soul` -- Used in EAT action for soul eating
- `souleater` -- Used in EAT action for soul eating
- `stackable` -- Used in DROP and various container operations
- `talkable` -- Used in TALKTO action
- `talker` -- Used in LOOKAT and ROW_FAIL for speech
- `thief` -- Used in STEAL action
- `workable` -- Used in EMPTY_CONTAINER action
- `yotc_racecompetitor` -- Used in PICKUP for YOTC trainer check
- `farmplantstress` -- Used in ATTACKPLANT to set happiness stress state.
- `storyteller` -- Used in TELLSTORY to perform storytelling.
- `stageactor` -- Required for performer in PERFORM action.
- `stageactingprop` -- Required target for PERFORM action to execute performance.
- `trap` -- Used in BAIT and CHECKTRAP actions to set bait and harvest.
- `deployable` -- Core component for DEPLOY action, handles deployment logic.
- `complexprojectile` -- Used in DEPLOY to launch projectiles instead of direct deployment.
- `guardian` -- Called by SUMMONGUARDIAN action.
- `itemmimic` -- Blocks work when mimic item is used.
- `tool` -- Provides effectiveness for work actions.
- `worker` -- Provides worker effectiveness when no tool is available.
- `workmultiplier` -- Provides multiplier and resolves special work amounts in DoToolWork.
- `spooked` -- Spooks player when CHOPping at stage 4.
- `crop` -- Fertilized via FERTILIZE action.
- `grower` -- Fertilized via FERTILIZE action.
- `pickable` -- Fertilized and picked via FERTILIZE and PICK actions.
- `quagmire_fertilizable` -- Quagmire-specific fertilizable via FERTILIZE.
- `fertilizer` -- Applied as item with OnApplied callback in FERTILIZE.
- `fertilizable` -- Used to self-fertilize player via FERTILIZE.
- `searchable` -- Used in PICK action as alternative to pickable.
- `fishingrod` -- Used in FISH and REEL actions to start/stop fishing and handle hooking.
- `combat` -- Used in ATTACK action to perform attacks.
- `multithruster` -- Used for thrusting attacks in ATTACK.
- `helmsplitter` -- Used for helm splitting attacks in ATTACK.
- `cooker` -- Used in COOK for container cooking.
- `stewer` -- Used in COOK for stew pot cooking.
- `cookable` -- Used in COOK for cooking items held by other entities.
- `fueler` -- Used in ADDFUEL for passive refueling.
- `trader` -- Used in GIVE to accept gifts and check acceptance.
- `moontrader` -- Used in GIVE to accept celestial offerings.
- `furnituredecortaker` -- Used in GIVE to accept decoration items.
- `inventoryitemholder` -- Used in GIVE to place items on holders.
- `quagmire_cookwaretrader` -- Used in GIVE for Quagmire cookware trading.
- `quagmire_altar` -- Used in GIVE for Quagmire food tributes.
- `playbill_lecturn` -- Used in GIVE to swap playbills.
- `ghostlyelixirable` -- Used in GIVE for ghostly elixir application.
- `ghostlyelixir` -- Applied in GIVE to target entities.
- `fillable` -- Used in FILL to fill containers with water.
- `vase` -- Used in DECORATEVASE to add flowers.
- `carnivalgamefeedable` -- Used in CARNIVALGAME_FEED to feed carnival games.
- `grabbable` -- Used in NET action to check if entity can be grabbed.
- `nabbag` -- Used in NET action to replicate net action to entities.
- `health` -- Checked in NET to prevent attacking dead entities.
- `activatable` -- CanActivate, DoActivate
- `beard` -- Shave
- `builder` -- DoBuild, UsePrototyper
- `childspawner` -- GoHome
- `constructionbuilder` -- constructioninst
- `constructionbuilderuidata` -- GetContainer, GetSlotForIngredient, GetTarget
- `constructionsite` -- builder
- `dryerack` -- None
- `groomer` -- None
- `harvestable` -- Harvest
- `hauntable` -- DoHaunt
- `healer` -- Heal
- `hideout` -- GoHome
- `hitcher` -- SetHitched, Unhitch
- `instrument` -- Play
- `klaussacklock` -- UseKey
- `knownlocations` -- GetLocation, RememberLocation
- `lighter` -- Light
- `lock` -- IsLocked, Lock, Unlock
- `lootdropper` -- GenerateLoot
- `machine` -- IsOn, TurnOff, TurnOn
- `maprecorder` -- TeachMap
- `mapspotrevealer` -- RevealMap, postreveal
- `markable` -- HasMarked, Mark
- `markable_proxy` -- Mark
- `maxhealer` -- Heal
- `mine` -- Reset
- `murderable` -- murdersound
- `npc_talker` -- Chatter, Say, donextline, haslines
- `occupiable` -- CanOccupy, Harvest, IsOccupied, Occupy
- `occupier` -- None
- `pocketwatch` -- CastSpell
- `pollinator` -- CreateFlower, Pollinate
- `quagmire_stewer` -- None
- `quagmire_tappable` -- Harvest
- `recipescanner` -- Scan
- `scrapbookable` -- Teach
- `shaveable` -- Shave
- `shaver` -- None
- `sleepingbag` -- DoSleep
- `spawner` -- GoHome
- `teacher` -- Teach
- `teleporter` -- IsActive
- `terraformer` -- Terraform
- `toggleableitem` -- CanInteract, ToggleItem
- `useableitem` -- CanInteract, StartUsingItem
- `useabletargeteditem` -- CanInteract, StartUsingItem, StopUsingItem
- `wardrobe` -- None
- `shelf` -- Used by TAKEITEM to call TakeItem on target shelf.
- `spellcaster` -- Used by CASTSPELL to check cast conditions and cast spells.
- `ghostlybond` -- Used in CASTSUMMON, CASTUNSUMMON, COMMUNEWITHSUMMONED for ghost control.
- `writeable` -- Used in WRITE action to begin writing on objects.
- `attunable` -- Used in ATTUNE to link player to target entity.
- `worldmigrator` -- Used in MIGRATE to initiate world transitions.
- `attuner` -- Used in REMOTERESURRECT to find attuned resurrectors.
- `revivablecorpse` -- Used in REVIVE_CORPSE to check/trigger revival.
- `pinnable` -- Used in UNPIN to check stuck status.
- `poppable` -- Used in CATPLAYGROUND/CATPLAYAIR to trigger pop actions.
- `cattoy` -- Used in CATPLAYGROUND/CATPLAYAIR to play with cat toys.
- `brushable` -- Used in BRUSH to apply brushing effects.
- `fan` -- Used in FAN action to trigger airflow behavior.
- `upgrader` -- Used in UPGRADE to verify upgrade compatibility.
- `upgradeable` -- Used in UPGRADE to perform upgrades.
- `petleash` -- Used in ABANDON to despawn pets.
- `crittertraits` -- Used in ABANDON to verify critter status.
- `kitcoon` -- Used in ACTIONS.PET to push 'on_petted' event; referenced in ACTIONS.RETURN_FOLLOWER.
- `hideandseekhidingspot` -- Used in ACTIONS.HIDEANSEEK_FIND to search.
- `drawingtool` -- Required for ACTIONS.DRAW.
- `drawable` -- Required for ACTIONS.DRAW; checked CanDraw.
- `channelable` -- Used in ACTIONS.STARTCHANNELING and ACTIONS.STOPCHANNELING.
- `channelcaster` -- Used in ACTIONS.START_CHANNELCAST and ACTIONS.STOP_CHANNELCAST.
- `channelcastable` -- Used in ACTIONS.START_CHANNELCAST and ACTIONS.STOP_CHANNELCAST to check user.
- `bundler` -- Required for bundling, wrapping, and peeking actions.
- `unwrappable` -- Required for unwrap and peekbundle actions; checked canbeunwrapped.
- `constructionplans` -- Used in construct to spawn new structures from plans.
- `aoespell` -- Required for CASTAOE action; checks CanCast and calls CastSpell.
- `spellbook` -- Used in CASTAOE to get spell name for string override.
- `portablestructure` -- Required for DISMANTLE action; calls Dismantle.
- `tackler` -- Required for TACKLE action; calls StartTackle.
- `halloweenpotionmoon` -- Required for HALLOWEENMOONMUTATE; calls Use.
- `perishable` -- Updated in APPLYPRESERVATIVE to increase percent.
- `preservative` -- Used in APPLYPRESERVATIVE; reads divide_effect_by_stack_size and percent_increase.
- `trophyscale` -- Used in COMPARE_WEIGHABLE; calls Compare.
- `weighable` -- Required for COMPARE_WEIGHABLE and WEIGH_ITEM.
- `itemweigher` -- Used in WEIGH_ITEM to call DoWeighIn.
- `yotc_racestart` -- Used in START_CARRAT_RACE; calls CanInteract and StartRace.
- `yotc_raceprizemanager` -- Used in START_CARRAT_RACE to get race data.
- `farmtiller` -- Used in TILL to call Till.
- `quagmire_tiller` -- Used in TILL for Quagmire tilling.
- `farmplantable` -- Used in PLANTSOIL to plant seeds.
- `quagmire_plantable` -- Used in PLANTSOIL for Quagmire planting.
- `quagmire_installable` -- Used in INSTALL to spawn and install parts.
- `quagmire_installations` -- Used in INSTALL to call Install.
- `quagmire_saltextractor` -- Used in INSTALL to call DoInstall.
- `quagmire_saltpond` -- Required in INSTALL for salt extractor installation.
- `quagmire_tapper` -- Required in TAPTREE to provide tap item.
- `quagmire_slaughtertool` -- Used in SLAUGHTER to perform slaughter.
- `craftingstation` -- Used in GIVE_TACKLESKETCH to check recipe knowledge.
- `tacklesketch` -- Used in GIVE_TACKLESKETCH to call Teach.
- `bathbomb` -- Required for BATHBOMB action.
- `bathbombable` -- Required for BATHBOMB action; calls OnBathBombed.
- `mast` -- Used in RAISE_SAIL and LOWER_SAIL_BOOST; calls UnfurlSail and AddSailFurler.
- `anchor` -- Used in RAISE_ANCHOR and LOWER_ANCHOR.
- `walkingplank` -- Used in mount/dismount/abandon/extend/retract plank actions.
- `boatleak` -- Required for REPAIR_LEAK; calls Repair.
- `steeringwheeluser` -- Used in STEER_BOAT, SET_HEADING, STOP_STEERING_BOAT.
- `steeringwheel` -- Required for STEER_BOAT; checked sailor and burning.
- `fishingnet` -- Required for CAST_NET.
- `boatrotator` -- Used in boat rotation actions.
- `boatmagnet` -- Used in BOAT_MAGNET_ACTIVATE and BOAT_MAGNET_DEACTIVATE.
- `boatmagnetbeacon` -- Used in BOAT_MAGNET_BEACON_TURN_ON/OFF.
- `boatcannon` -- Used in LOAD_AMMO, START_AIMING, SHOOT, STOP_AIMING.
- `boatcannonuser` -- Used in START_AIMING and SHOOT.
- `oceantrawler` -- Used in OCEAN_TRAWLER_LOWER/RAISE/FIX.
- `cyclable` -- Used by CYCLE, checks cancycle and calls Cycle
- `oceanthrowable` -- Used by OCEAN_TOSS to add projectile component and launch
- `questowner` -- Used by BEGIN_QUEST and ABANDON_QUEST to manage quests
- `singinginspiration` -- Used by SING to validate/record active songs
- `singable` -- Used by SING to add songs to singer
- `quagmire_replater` -- Used by REPLATE to define target plate
- `quagmire_replatable` -- Used by REPLATE to perform replate
- `quagmire_saltable` -- Used by SALT to apply salt
- `wateryprotection` -- Used by POUR_WATER to spread protection
- `finiteuses` -- Used by POUR_WATER to check water usage
- `plantresearchable` -- Used by PLANTREGISTRY_RESEARCH to learn plant
- `fertilizerresearchable` -- Used by PLANTREGISTRY_RESEARCH to learn fertilizer
- `compostingbin` -- Used by ADDCOMPOSTABLE to add compost
- `waxable` -- Used by WAX to apply wax
- `winch` -- Used by UNLOAD_WINCH to call unloadfn
- `heavyobstacleusetarget` -- Used by USE_HEAVY_OBSTACLE to handle usage
- `mightygym` -- Used by ENTER_GYM, LEAVE_GYM, UNLOAD_GYM
- `strongman` -- Used by LEAVE_GYM to retrieve gym
- `upgrademoduleowner` -- Used by APPLYMODULE and REMOVEMODULES
- `upgrademodule` -- Used by APPLYMODULE for module instance
- `upgrademoduleremover` -- Used by REMOVEMODULES
- `batteryuser` -- Used by CHARGE_FROM to get user from item or doer
- `battery` -- Used by CHARGE_FROM as charge source
- `fencerotator` -- Used by ROTATE_FENCE to rotate fence
- `magician` -- Used by USEMAGICTOOL and STOPUSINGMAGICTOOL
- `sittable` -- Used by SITON to check occupancy and set occupier
- `remoteteleporter` -- Used by REMOTE_TELEPORT
- `incinerator` -- Used by INCINERATE
- `bottler` -- Used by BOTTLE
- `pumpkincarvable` -- Used by CARVEPUMPKIN
- `pumpkinhatcarvable` -- Used by CARVEPUMPKIN
- `snowmandecoratable` -- Used by DECORATESNOWMAN to identify stackable items
- `pushable` -- Used to start/stop pushing logic
- `gravediggable` -- Used to dig up graves
- `gravedigger` -- Used as tool to trigger grave digging
- `ghostgestalter` -- Used to perform ghost gestalt mutation
- `containerinstallableitem` -- Used to find valid open containers for installing items
- `equipment` -- Used to check equipslot and IsRestricted
- `slingshotmods` -- Used to check CanBeOpenedBy during modding
- `slingshotmodder` -- Used to start/stop modding
- `deckcontainer` -- Used to add/remove/merge cards in decks
- `playingcard` -- Used to get/set card IDs
- `gestaltcage` -- Used to capture targets
- `moonstormstaticcatcher` -- Used to catch moonstorm static targets
- `electricconnector` -- Used to start/end/disconnect electric links
- `lunarhailbuildup` -- Used to remove lunar buildup
- `bathingpool` -- Used to enter pool
- `joustuser` -- Used to check CanJoust for jousting
- `joustsource` -- Used to validate joust source item
- `clientpickupsoundsuppressor` -- Used to suppress next pickup sound
- `playingcardsmanager` -- Used to spawn playing cards

**Tags:**
- `CLASSIFIED` -- add / remove / check
- `_upgradeuser` -- add / remove / check
- `abigail_flower` -- add / remove / check
- `ancient_reader` -- add / remove / check
- `ancient_text` -- add / remove / check
- `balloonomancer` -- add / remove / check
- `batteryuser` -- add / remove / check
- `boat_leak` -- add / remove / check
- `boatbuilder` -- add / remove / check
- `boatcannon_ammo` -- add / remove / check
- `bundle` -- add / remove / check
- `burnt` -- add / remove / check
- `can_be_bathbombed` -- add / remove / check
- `can_use_heavy` -- add / remove / check
- `canbeslaughtered` -- add / remove / check
- `cannothale` -- add / remove / check
- `cannotuse` -- add / remove / check
- `canpeek` -- add / remove / check
- `cansee` -- add / remove / check
- `catchable` -- add / remove / check
- `character` -- add / remove / check
- `coach_whistle` -- add / remove / check
- `coaching` -- add / remove / check
- `combatmount` -- add / remove / check
- `constructionsite` -- add / remove / check
- `controlled_burner` -- add / remove / check
- `cookable` -- add / remove / check
- `critterlab` -- add / remove / check
- `crushitemcast` -- add / remove / check
- `decoratable` -- add / remove / check
- `deployable` -- add / remove / check
- `deployedfarmplant` -- add / remove / check
- `deploykititem` -- add / remove / check
- `dogrider` -- add / remove / check
- `dogrider_only` -- add / remove / check
- `dressable` -- add / remove / check
- `drop_inventory_onmurder` -- add / remove / check
- `drop_inventory_onpickup` -- add / remove / check
- `elixir_drinker` -- add / remove / check
- `eyeturret` -- add / remove / check
- `farm_plant` -- add / remove / check
- `fencebuilder` -- add / remove / check
- `fertilizer` -- add / remove / check
- `fertilizerresearchable` -- add / remove / check
- `fire` -- add / remove / check
- `fogrevealer` -- add / remove / check
- `fooddrink` -- add / remove / check
- `fresh` -- add / remove / check
- `frozen` -- add / remove / check
- `fueldepleted` -- add / remove / check
- `furnituredecortaker` -- add / remove / check
- `gatebuilder` -- add / remove / check
- `gemsocket` -- add / remove / check
- `ghostlyelixir` -- add / remove / check
- `ghostlyelixirable` -- add / remove / check
- `globalmapicon` -- add / remove / check
- `globalmapicon_player` -- add / remove / check
- `graveplanter` -- add / remove / check
- `groundtile` -- add / remove / check
- `hammer` -- add / remove / check
- `handyperson` -- add / remove / check
- `has_aggressive_follower` -- add / remove / check
- `hasemergencymode` -- add / remove / check
- `haunted` -- add / remove / check
- `heavy` -- add / remove / check
- `hermitcrab` -- add / remove / check
- `inventoryitemholder_give` -- add / remove / check
- `is_using_cannon` -- add / remove / check
- `kitcoonden` -- add / remove / check
- `lighter` -- add / remove / check
- `mapspotrevealer` -- add / remove / check
- `master_crewman` -- add / remove / check
- `masterchef` -- add / remove / check
- `mastercookware` -- add / remove / check
- `merm` -- add / remove / check
- `mermonly` -- add / remove / check
- `mightiness_normal` -- add / remove / check
- `mine` -- add / remove / check
- `moontrader` -- add / remove / check
- `near_kitcoonden` -- add / remove / check
- `offerconstructionsite` -- add / remove / check
- `overridelocomote` -- add / remove / check
- `pet_treat` -- add / remove / check
- `pickapart` -- add / remove / check
- `playbill_lecturn` -- add / remove / check
- `player` -- add / remove / check
- `playerfloater` -- add / remove / check
- `playerghost` -- add / remove / check
- `pocketwatchcaster` -- add / remove / check
- `portableitem` -- add / remove / check
- `projectile` -- add / remove / check
- `propweapon` -- add / remove / check
- `pump` -- add / remove / check
- `pushing_roll` -- add / remove / check
- `pyromaniac` -- add / remove / check
- `quagmire_altar` -- add / remove / check
- `quagmire_replatable` -- add / remove / check
- `quagmire_salted` -- add / remove / check
- `quagmire_stewer` -- add / remove / check
- `race_on` -- add / remove / check
- `rebuildconstructionsite` -- add / remove / check
- `recipescanner` -- add / remove / check
- `reloaditem_ammo` -- add / remove / check
- `repairable_moon_altar` -- add / remove / check
- `repairable_vitae` -- add / remove / check
- `repairconstructionsite` -- add / remove / check
- `scrapbook_data` -- add / remove / check
- `scrapbook_note` -- add / remove / check
- `sewingmachine` -- add / remove / check
- `singingshell` -- add / remove / check
- `smashable` -- add / remove / check
- `smolder` -- add / remove / check
- `soil` -- add / remove / check
- `soul` -- add / remove / check
- `souljar` -- add / remove / check
- `soulstealer` -- add / remove / check
- `special_action_toss` -- add / remove / check
- `spicer` -- add / remove / check
- `spider` -- add / remove / check
- `spiderwhisperer` -- add / remove / check
- `spoiled` -- add / remove / check
- `stale` -- add / remove / check
- `stewer` -- add / remove / check
- `stokeablefire` -- add / remove / check
- `super_elixir` -- add / remove / check
- `switchtoho` -- add / remove / check
- `tappable` -- add / remove / check
- `teleporter` -- add / remove / check
- `tentacle_pillar` -- add / remove / check
- `trader_just_show` -- add / remove / check
- `trader_repair` -- add / remove / check
- `trap` -- add / remove / check
- `trophycanbetaken` -- add / remove / check
- `trophyscale_*` -- add / remove / check
- `unwrappable` -- add / remove / check
- `usedeploystring` -- add / remove / check
- `virtualocean` -- add / remove / check
- `wallbuilder` -- add / remove / check
- `watersource` -- add / remove / check
- `weighable_*` -- add / remove / check
- `whackable` -- add / remove / check
- `winter_treestand` -- add / remove / check
- `wintersfeasttable` -- add / remove / check
- `withered` -- add / remove / check
- `wolfgang_coach` -- add / remove / check
- `wormhole` -- add / remove / check

## Properties
| Name | Type | Default | Description |
|------|------|---------|-------------|
| `self.priority` | number | `0` | Action priority; higher values take precedence. |
| `self.fn` | function | `function() return false end` | Default action function that returns false. |
| `self.strfn` | function | `nil` | Optional function to compute string description. |
| `self.instant` | boolean | `false` | Whether the action is instant (no movement required). |
| `self.rmb` | boolean | `nil` | Whether the action requires right mouse button. |
| `self.distance` | number | `nil` | Fixed action range distance. |
| `self.mindistance` | number | `nil` | Minimum distance required to perform the action. |
| `self.arrivedist` | number | `nil` | Distance within which the action is considered arrived. |
| `self.ghost_exclusive` | boolean | `false` | Whether the action is exclusive to ghost state. |
| `self.ghost_valid` | boolean | `false` | Whether the action is valid in ghost state. |
| `self.mount_valid` | boolean | `false` | Whether the action is valid while mounted. |
| `self.encumbered_valid` | boolean | `false` | Whether the action is valid while encumbered. |
| `self.floating_valid` | boolean | `false` | Whether the action is valid while floating. |
| `self.canforce` | boolean | `nil` | Whether the action can be forced (e.g., via input override). |
| `self.rangecheckfn` | function | `nil` | Custom function to check if target is within range. |
| `self.mod_name` | string | `nil` | Name of the mod defining this action (if any). |
| `self.silent_fail` | boolean | `nil` | Whether failures should be silent (no feedback). |
| `self.silent_generic_fail` | boolean | `nil` | Whether generic failures should be silent. |
| `self.paused_valid` | boolean | `false` | Whether the action is valid while game is paused. |
| `self.actionmeter` | boolean | `nil` | Whether the action consumes an action meter. |
| `self.customarrivecheck` | function | `nil` | Custom function to validate arrival condition. |
| `self.is_relative_to_platform` | boolean | `false` | Whether range checks are relative to current platform. |
| `self.disable_platform_hopping` | boolean | `false` | Whether to prevent platform-hopping during locomotion. |
| `self.skip_locomotor_facing` | boolean | `false` | Whether to skip facing direction checks during locomotion. |
| `self.do_not_locomote` | boolean | `false` | Whether to skip locomotion entirely for this action. |
| `self.extra_arrive_dist` | function | `nil` | Function returning extra distance added to arrival check. |
| `self.tile_placer` | string | `nil` | Identifier for tile placement mode (e.g., 'gridplacer'). |
| `self.show_tile_placer_fn` | function | `nil` | Function determining visibility of tile placer UI. |
| `self.theme_music` | string | `nil` | Theme music ID to play when this action is available. |
| `self.theme_music_fn` | function | `nil` | Client-side function returning theme music ID. |
| `self.pre_action_cb` | function | `nil` | Callback to run before action starts (client and server). |
| `self.invalid_hold_action` | boolean | `false` | Whether holding the action button prevents it. |
| `self.show_primary_input_left` | boolean | `nil` | Whether to show primary input hint on left side. |
| `self.show_secondary_input_right` | boolean | `nil` | Whether to show secondary input hint on right side. |
| `self.map_action` | boolean | `false` | Whether the action is only valid from the minimap. |
| `self.closes_map` | boolean | `false` | Whether the action immediately closes the minimap on start. |
| `self.map_only` | boolean | `false` | Whether the action exists only from the minimap. |
| `self.map_works_on_unexplored` | boolean | `false` | Whether the action bypasses visibility checks. |

## Main functions

### `MakeRangeCheckFn(range)`
* **Description:** Returns a function that checks if doer is near target within given range.
* **Parameters:** `range` -- number, maximum distance to consider nearness
* **Returns:** `function(doer, target) => boolean` that returns true if distance is within range.
* **Error states:** None

### `PickRangeCheck(doer, target)`
* **Description:** Checks if target is within range considering weapon attack range and physics radius.
* **Parameters:**
  - `doer` -- actor performing the action
  - `target` -- entity to be targeted
* **Returns:** `boolean or nil`, where `nil` indicates target is nil.
* **Error states:** Returns `nil` if target is nil.

### `ExtraPickRange(doer, dest)`
* **Description:** Returns extra range needed for picking actions, depending on target tags and water status.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
* **Returns:** `number (extra range)`, defaults to 0 for non-water scenarios.
* **Error states:** Returns 0 if no target or not on water.

### `PhysicsPaddedRangeCheck(doer, target)`
* **Description:** Checks distance using physics radius + 4 (currently unused).
* **Parameters:**
  - `doer` -- actor performing the action
  - `target` -- entity to be targeted
* **Returns:** `boolean or nil`, where `nil` indicates target is nil.
* **Error states:** Returns `nil` if target is nil.

### `CheckFishingOceanRange(doer, dest)`
* **Description:** Checks if fishing point over ocean has valid virtual ocean entity.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
* **Returns:** `boolean`, always true in standard ocean checks.
* **Error states:** None

### `CheckRowRange(doer, dest)`
* **Description:** Returns false if destination is on a platform; otherwise true.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
* **Returns:** `boolean`, false if on platform, true otherwise.
* **Error states:** None

### `CheckIsOnPlatform(doer, dest)`
* **Description:** Checks if doer is currently on a platform.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
* **Returns:** `boolean`, true if on platform.
* **Error states:** None

### `CheckOceanFishingCastRange(doer, dest)`
* **Description:** Checks if ocean fishing cast point is over ocean with virtual entity.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
* **Returns:** `boolean`, true if valid ocean tile.
* **Error states:** None

### `CheckTileWithinRange(doer, dest)`
* **Description:** Checks if destination tile center is within half-tile distance.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
* **Returns:** `boolean or nil`
* **Error states:** None

### `ShowPourWaterTilePlacer(right_mouse_action)`
* **Description:** Returns true if pouring water on farm plant is valid and soil is farmable.
* **Parameters:** `right_mouse_action` -- boolean indicating RMB context
* **Returns:** `boolean`, false if target not farm plant or soil not farmable.
* **Error states:** False if target is not a farm plant or soil is not farmable.

### `ExtraPickupRange(doer, dest)`
* **Description:** Returns 0.75 extra distance if destination is on water; otherwise 0.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
* **Returns:** `number`, extra range value.
* **Error states:** None

### `ExtraDeployDist(doer, dest, bufferedaction)`
* **Description:** Returns extra deployment distance based on object type and platform crossing.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
  - `bufferedaction` -- optional action object for context
* **Returns:** `number`, extra distance value.
* **Error states:** None

### `ExtraDropDist(doer, dest, bufferedaction)`
* **Description:** Returns extra drop distance for water, physics collisions, and explicit flags.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
  - `bufferedaction` -- optional action object for context
* **Returns:** `number`, extra distance value.
* **Error states:** None

### `ExtraPourWaterDist(doer, dest, bufferedaction)`
* **Description:** Returns fixed extra distance of 1.5 for pouring water actions.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
  - `bufferedaction` -- optional action object for context
* **Returns:** `number`, fixed extra distance value.
* **Error states:** None

### `ExtraHealRange(doer, dest, bufferedaction)`
* **Description:** Fixes range for healing on entities with physics radius overrides.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
  - `bufferedaction` -- optional action object for context
* **Returns:** `number`, extra distance value.
* **Error states:** None

### `ArriveAnywhere()`
* **Description:** Returns true unconditionally; used for map-only arrive checks.
* **Parameters:** None
* **Returns:** `true`

### `ExtraWobyForagingDist(doer, dest, bufferedaction)`
* **Description:** Returns 0.5 for small creatures, or 1.5 for large creatures.
* **Parameters:**
  - `doer` -- actor performing the action
  - `dest` -- destination point
  - `bufferedaction` -- optional action object for context
* **Returns:** `number`, extra distance value.
* **Error states:** None

### `SetClientRequestedAction(actioncode, mod_name)`
* **Description:** Sets global CLIENT_REQUESTED_ACTION based on action code and optional mod name.
* **Parameters:**
  - `actioncode` -- string identifier for action
  - `mod_name` -- optional mod identifier string
* **Returns:** None

### `ClearClientRequestedAction()`
* **Description:** Clears global CLIENT_REQUESTED_ACTION to nil.
* **Parameters:** None
* **Returns:** None

### `IsItemInReadOnlyContainer(item)`
* **Description:** Checks whether an item is inside a read-only container by inspecting its ownership chain.
* **Parameters:** `item` -- inventory item to check
* **Returns:** `boolean` indicating if item is in a read-only container
* **Error states:** None

### `ShouldLOOKATStopLocomotor(act)`
* **Description:** Determines if LOOKAT action should stop the locomotor based on direct walking or state graph tags.
* **Parameters:** `act` -- action object
* **Returns:** `boolean` indicating if locomotor should stop
* **Error states:** None

### `row(act)`
* **Description:** Core helper function for ROW actions that handles both oar-based rowing and crewmember rowing logic.
* **Parameters:** `act` -- action object containing doer, target, and position
* **Returns:** `boolean` success status
* **Error states:** False if neither oar nor crewmember component present

### `ACTIONS.APPRAISE.fn(act)`
* **Description:** Action handler to appraise a target using an appraisable item.
* **Parameters:** `act` -- action object with doer, target, and object
* **Returns:** `true` on success, `false` or `'NOTNOW'`
* **Error states:** Returns `false` if canappraise fails with a reason other than `'NOTNOW'`; returns `false` if target or object missing

### `ACTIONS.EAT.strfn(act)`
* **Description:** Dynamic string generator for EAT action based on whether target is fooddrink.
* **Parameters:** `act` -- action object
* **Returns:** `string 'DRINK'` or `nil`
* **Error states:** None

### `ACTIONS.EAT.fn(act)`
* **Description:** Action handler for eating food, drinking, soul eating, or swapping ocean fishing rod.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` depending on component calls, or `nil` if components missing
* **Error states:** Nil if no matching edible or soul eater component

### `ACTIONS.STEAL.fn(act)`
* **Description:** Action handler for stealing items from inventory or dryer-based item dropping.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` depending on thief/dryer component success, `nil` if not in range
* **Error states:** Range check fails if target too far (>4 units)

### `ACTIONS.MAKEBALLOON.fn(act)`
* **Description:** Action handler for spawning balloon using balloonmaker and sanity cost.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` if sanity insufficient
* **Error states:** No spawn if doer missing balloonoomancer tag or item lacks balloonmaker

### `ACTIONS.EQUIP.fn(act)`
* **Description:** Action handler for equipping an item to player inventory.
* **Parameters:** `act` -- action object
* **Returns:** `result` of `inventory:Equip` call
* **Error states:** Nil if inventory missing

### `ACTIONS.UNEQUIP.strfn(act)`
* **Description:** Dynamic string generator for UNEQUIP action based on item heaviness or game mode.
* **Parameters:** `act` -- action object
* **Returns:** `string 'HEAVY'` or `nil`
* **Error states:** None

### `ACTIONS.UNEQUIP.fn(act)`
* **Description:** Action handler for unequipping item, giving it to inventory or dropping it.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` if item restricted
* **Error states:** Returns `nil` if item should prevent unequipping

### `ACTIONS.PICKUP.strfn(act)`
* **Description:** Dynamic string generator for PICKUP action, returns `'HEAVY'` if target is heavy.
* **Parameters:** `act` -- action object
* **Returns:** `string 'HEAVY'` or `nil`
* **Error states:** None

### `ACTIONS.PICKUP.fn(act)`
* **Description:** Action handler for picking up items respecting heavy-lifting, cursed-item, spider-follower, inventory slot, and container restrictions.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason string on failure, `nil` if item can't be picked up
* **Error states:** Multiple early returns for restrictions (heavy, spider, cursed, container use)

### `ACTIONS.EMPTY_CONTAINER.fn(act)`
* **Description:** Calls onwork callback on workable component if present, acting as container-empty action.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** Silent failure if workable component missing

### `ACTIONS.REPAIR.strfn(act)`
* **Description:** Dynamic string generator for REPAIR action, specialized strings for moon altar (`SOCKET`) or vitae (`REFRESH`).
* **Parameters:** `act` -- action object
* **Returns:** `string 'SOCKET'`, `'REFRESH'`, or `nil`
* **Error states:** None

### `ACTIONS.REPAIR.fn(act)`
* **Description:** Action handler for repairing via repairable or forgerepairable component using appropriate repairer material.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` depending on `repairable:Repair` call, or `nil` if no component found
* **Error states:** Falls back to heavy lifting if no invobject and is heavy-lifting player

### `ACTIONS.SEW.strfn(act)`
* **Description:** Dynamic string generator for SEW action, returns `'PATCH'` if item has tape tag.
* **Parameters:** `act` -- action object
* **Returns:** `string 'PATCH'` or `nil`
* **Error states:** None

### `ACTIONS.SEW.fn(act)`
* **Description:** Action handler for sewing repairs using sewing component on fueled target.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` from sewing component call, or `nil` if components missing
* **Error states:** Nil if target lacks fueled or invobject lacks sewing component

### `ACTIONS.RUMMAGE.fn(act)`
* **Description:** Action handler for opening/closing containers, including proxy containers, restrictions, and droponopen behaviors.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason on failure
* **Error states:** Multiple early failures: restricted, not master chef, not merm, soul jar, in use, not visible in dark

### `ACTIONS.RUMMAGE.strfn(act)`
* **Description:** Dynamic string generator for RUMMAGE action, returns `'CLOSE'` if container opened, else decorative strings or nil.
* **Parameters:** `act` -- action object
* **Returns:** `string 'CLOSE'`, `'DECORATE'`, `'PEEK'`, or `nil`
* **Error states:** None

### `ACTIONS.DROP.strfn(act)`
* **Description:** Dynamic string generator for DROP action, specialized strings for traps, mines, soul jars, etc.
* **Parameters:** `act` -- action object
* **Returns:** `string` like `'SETTRAP'`, `'FREESOUL'`, etc., or `nil`
* **Error states:** None

### `ACTIONS.DROP.fn(act)`
* **Description:** Action handler for dropping items from inventory, respecting stack splitting, heavy flags, and floater behavior.
* **Parameters:** `act` -- action object
* **Returns:** `result` of `inventory:DropItem` call
* **Error states:** Returns `nil` if equippable item should prevent unequipping

### `ACTIONS.LOOKAT.strfn(act)`
* **Description:** Dynamic string generator for LOOKAT action, detects `CLOSEINSPECT`, `READ`, or decoratable string.
* **Parameters:** `act` -- action object
* **Returns:** `string 'CLOSEINSPECT'`, `'READ'`, `'DECORATE'`, `'PEEK'`, or `nil`
* **Error states:** None

### `ACTIONS.LOOKAT.fn(act)`
* **Description:** Action handler for inspecting entity or point using closeinspector (equipment) or inspectable component.
* **Parameters:** `act` -- action object
* **Returns:** `true` or result of closeinspector, or `nil` if no description
* **Error states:** Fails silently if inspectable returns nil description

### `ACTIONS_MAP_REMAP[ACTIONS.ACTIVATE.code](act, targetpos)`
* **Description:** Special remap action handler for ACTIVATE action during map use, particularly for charlieresidue wormhole detection.
* **Parameters:**
  - `act` -- action object
  - `targetpos` -- destination position
* **Returns:** `BufferedAction or nil`
* **Error states:** Nil if charlieresidue missing or target not valid wormhole

### `ACTIONS.READ.fn(act)`
* **Description:** Action handler for reading books via book or simplebook component.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` from `reader:Read`, or `true` from `simplebook:Read`, or `nil`
* **Error states:** Nil if no book/simplebook or reader component

### `ACTIONS.ROW_FAIL.fn(act)`
* **Description:** Action handler for failed rowing attempt, retrieves oar and calls RowFail, reports fail string.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** False if no oar equipped

### `ACTIONS.ROW.fn(act)`
* **Description:** Action handler for ROW, delegates to helper row function.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` depending on row helper
* **Error states:** Nil if row helper returns nil

### `ACTIONS.ROW_CONTROLLER.fn(act)`
* **Description:** Action handler for ROW_CONTROLLER, identical to ROW handler.
* **Parameters:** `act` -- action object
* **Returns:** `true/false`
* **Error states:** Same as `ACTIONS.ROW.fn`

### `ACTIONS.BOARDPLATFORM.fn(act)`
* **Description:** Placeholder handler for boarding a platform, always succeeds.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.OCEAN_FISHING_POND.fn(act)`
* **Description:** Action handler for pond fishing, checks for virtualocean tag.
* **Parameters:** `act` -- action object
* **Returns:** `true` if pond virtual ocean, else `false` with `'WRONGGEAR'`
* **Error states:** Returns `'WRONGGEAR'` if not virtual ocean

### `ACTIONS.OCEAN_FISHING_CAST.fn(act)`
* **Description:** Action handler for ocean fishing cast, delegates to `rod:Cast`.
* **Parameters:** `act` -- action object
* **Returns:** `result` of `oceanfishingrod:Cast`, or `nil` if no rod
* **Error states:** Nil if no `oceanfishingrod` component

### `ACTIONS.OCEAN_FISHING_REEL.strfn(act)`
* **Description:** Dynamic string generator for OCEAN_FISHING_REEL, returns `'SETHOOK'` if target partiallyhooked.
* **Parameters:** `act` -- action object
* **Returns:** `string 'SETHOOK'` or `nil`
* **Error states:** None

### `ACTIONS.OCEAN_FISHING_REEL.fn(act)`
* **Description:** Action handler for ocean fishing reel, delegates to `rod:Reel`.
* **Parameters:** `act` -- action object
* **Returns:** `result` of `oceanfishingrod:Reel`, or `nil` if no rod
* **Error states:** Nil if no `oceanfishingrod` component

### `ACTIONS.OCEAN_FISHING_STOP.fn(act)`
* **Description:** Action handler for ocean fishing stop, transitions state and calls `rod:StopFishing`.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.OCEAN_FISHING_CATCH.fn(act)`
* **Description:** Action handler for ocean fishing catch, transitions state and calls `rod:CatchFish`.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.CHANGE_TACKLE.strfn(act)`
* **Description:** Dynamic string generator for CHANGE_TACKLE, returns `'REMOVE'` or `'AMMO'` depending on item state.
* **Parameters:** `act` -- action object
* **Returns:** `string 'REMOVE'` or `'AMMO'` or `nil`
* **Error states:** None

### `ACTIONS.CHANGE_TACKLE.fn(act)`
* **Description:** Action handler for changing tackle items inside slingshot container or similar
* **Parameters:** `act` -- action object
* **Returns:** `true/false` depending on container operations
* **Error states:** Returns `false` if equipped or container invalid, or operations fail

### `ACTIONS.TALKTO.fn(act)`
* **Description:** Action handler for talking to talkable entities, triggers maxwelltalker if present.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** Nil if no talkable component or already talking

### `ACTIONS.INTERACT_WITH.strfn(act)`
* **Description:** Dynamic string generator for INTERACT_WITH, returns `'FARM_PLANT'` if target has farm_plant tag.
* **Parameters:** `act` -- action object
* **Returns:** `string 'FARM_PLANT'` or `nil`
* **Error states:** None

### `ACTIONS.INTERACT_WITH.fn(act)`
* **Description:** Action handler for farm plant tending using farmplanttendable component.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** Nil if no farmplanttendable component or `TendTo` returns false

### `ACTIONS.INTERACT_WITH.theme_music_fn(act)`
* **Description:** Theme music generator for INTERACT_WITH, returns `'farming'` if target has farm_plant tag.
* **Parameters:** `act` -- action object
* **Returns:** `string 'farming'` or `nil`
* **Error states:** None

### `DoToolWork(act, workaction)`
* **Description:** Performs tool-based work on a target entity using workable component, accounting for tool effectiveness, worker skill, multipliers, and recoil.
* **Parameters:**
  - `act` -- action object
  - `workaction` -- string identifier for type of work (e.g., "CHOP", "HACK")
* **Returns:** `true` on success; `false + reason` on failure
* **Error states:** Fails if target lacks workable component, is not workable, wrong workaction, or weapon is restricted. Returns `false` with reason `'ITEMMIMIC'` if mimicking item used.

### `ValidToolWork(act, workaction)`
* **Description:** Validates whether a target can be worked with a specific workaction (without performing work).
* **Parameters:**
  - `act` -- action object
  - `workaction` -- string identifier for type of work
* **Returns:** `boolean` indicating validity
* **Error states:** None

### `ShouldBlockGiving(act)`
* **Description:** Checks if giving an item should be blocked due to pocket-only restrictions.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** None

### `ACTIONS.STORE.fn(act)`
* **Description:** Handles storing items into containers or construction sites, including proxy resolution, restricted access checks, and bundle/construction handling.
* **Parameters:** `act` -- action object
* **Returns:** `true` if stored, `false` with error string otherwise
* **Error states:** `INUSE`, `NOTALLOWED`, `RESTRICTED`, `NOTMASTERCHEF`, `NOTAMERM`, `NOTSOULJARHANDLER`

### `ACTIONS.BUNDLESTORE.strfn(act)`
* **Description:** Determines if the action is relevant to bundle/construction storage based on UI data context.
* **Parameters:** `act` -- action object
* **Returns:** `'CONSTRUCT'` if matching, `nil` otherwise
* **Error states:** None

### `ACTIONS.STORE.strfn(act)`
* **Description:** Returns appropriate verb string for stored target types (stewer, cook, birdcage, decoratable).
* **Parameters:** `act` -- action object
* **Returns:** Verb string or `nil`
* **Error states:** None

### `ACTIONS.BUILD.fn(act)`
* **Description:** Performs building via the builder component if present.
* **Parameters:** `act` -- action object
* **Returns:** Result of `builder:DoBuild` or `nil`
* **Error states:** None

### `ACTIONS.PLANT.strfn(act)`
* **Description:** Returns `'PLANTER'` for winter treestand targets.
* **Parameters:** `act` -- action object
* **Returns:** `'PLANTER'` or `nil`
* **Error states:** None

### `ACTIONS.PLANT.fn(act)`
* **Description:** Plants seeds using grower component or triggers winter treestand planting event.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` or `false`
* **Error states:** None

### `ACTIONS.HARVEST.fn(act)`
* **Description:** Harvests crops, harvestables, stewers, dryers, or extracts items from drying racks/occupiables.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` or `false`
* **Error states:** None

### `ACTIONS.HARVEST.strfn(act)`
* **Description:** Returns `'FREE'` for birdcage, `'WITHERED'` for withered crops.
* **Parameters:** `act` -- action object
* **Returns:** Verb string or `nil`
* **Error states:** None

### `ACTIONS.LIGHT.fn(act)`
* **Description:** Lights targets using lighter component, fires `'onstartedfire'` event.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.SLEEPIN.fn(act)`
* **Description:** Sleeps in sleeping bag (on invobject or target).
* **Parameters:** `act` -- action object
* **Returns:** `true` if sleeping bag used, `nil` otherwise
* **Error states:** None

### `ACTIONS.HITCHUP.fn(act)`
* **Description:** Hitches a beefalo to the target after validation of proximity, mood, and inventory.
* **Parameters:** `act` -- action object
* **Returns:** `true` if hitched, `false` with error string otherwise
* **Error states:** `NEEDBEEF`, `NEEDBEEF_CLOSER`, `INMOOD`

### `ACTIONS.UNHITCH.fn(act)`
* **Description:** Unhitches from hitcher component on target.
* **Parameters:** `act` -- action object
* **Returns:** `true` if unhitched, `nil` otherwise
* **Error states:** None

### `ACTIONS.HITCH.fn(act)`
* **Description:** Hitches actor to target if target has hitcher tag.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.MARK.strfn(act)`
* **Description:** Returns `'UNMARK'` if already marked by actor.
* **Parameters:** `act` -- action object
* **Returns:** `'UNMARK'` or `nil`
* **Error states:** None

### `ACTIONS.MARK.fn(act)`
* **Description:** Marks or unmarks target via markable or markable_proxy components.
* **Parameters:** `act` -- action object
* **Returns:** `true` if marked/unmarked, `false` with error string otherwise
* **Error states:** `NOT_PARTICIPANT`, `ALREADY_MARKED`

### `ACTIONS.CHANGEIN.strfn(act)`
* **Description:** Returns `'DRESSUP'` if target has dressable tag.
* **Parameters:** `act` -- action object
* **Returns:** `'DRESSUP'` or `nil`
* **Error states:** None

### `ACTIONS.CHANGEIN.fn(act)`
* **Description:** Begins changing outfit via wardrobe or groomer components, respecting visibility.
* **Parameters:** `act` -- action object
* **Returns:** `true` if change started, `false` with reason otherwise
* **Error states:** None

### `ACTIONS.SHAVE.strfn(act)`
* **Description:** Returns `'SELF'` if targeting self with controller attached.
* **Parameters:** `act` -- action object
* **Returns:** `'SELF'` or `nil`
* **Error states:** None

### `ACTIONS.SHAVE.fn(act)`
* **Description:** Shaves target using shaver or shaveable components.
* **Parameters:** `act` -- action object
* **Returns:** Result of `beard:Shave` or `shaveable:Shave`, `nil` otherwise
* **Error states:** None

### `ACTIONS.PLAY.strfn(act)`
* **Description:** Returns appropriate verb for coach whistle use or generic tweet.
* **Parameters:** `act` -- action object
* **Returns:** Verb string or `nil`
* **Error states:** None

### `ACTIONS.PLAY.fn(act)`
* **Description:** Plays instrument (invobject) if present.
* **Parameters:** `act` -- action object
* **Returns:** Result of `instrument:Play` or `nil`
* **Error states:** None

### `ACTIONS.POLLINATE.fn(act)`
* **Description:** Pollinates target or creates flower via pollinator component.
* **Parameters:** `act` -- action object
* **Returns:** Result of `pollinator` methods or `nil`
* **Error states:** None

### `ACTIONS.TERRAFORM.fn(act)`
* **Description:** Terraforms ground at action point using terraformer component.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` result of terraform, `nil` otherwise
* **Error states:** None

### `ACTIONS.EXTINGUISH.fn(act)`
* **Description:** Extinguishes fire or reduces fueled section if burning or smoldering.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.STOKEFIRE.fn(act)`
* **Description:** Stokes controlled burn if stokeable and actor has controlled_burner tag.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` otherwise
* **Error states:** None

### `ACTIONS.LAYEGG.fn(act)`
* **Description:** Regenerates pickable item if not currently pickable.
* **Parameters:** `act` -- action object
* **Returns:** Result of `pickable:Regen` or `nil`
* **Error states:** None

### `ACTIONS.INVESTIGATE.fn(act)`
* **Description:** Remembers investigate location, triggers retargeting.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.COMMENT.fn(act)`
* **Description:** Executes queued comment via npc_talker or talker components.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.GOHOME.fn(act)`
* **Description:** Returns entity to home via spawner, childspawner, or hideout components or removes entity.
* **Parameters:** `act` -- action object
* **Returns:** `true` or result of `gohome` methods
* **Error states:** None

### `ACTIONS.JUMPIN.strfn(act)`
* **Description:** Returns `'HAUNT'` for playerghost entities.
* **Parameters:** `act` -- action object
* **Returns:** `'HAUNT'` or `nil`
* **Error states:** None

### `ACTIONS.JUMPIN.fn(act)`
* **Description:** Enters teleporter in jumpin_pre state if active.
* **Parameters:** `act` -- action object
* **Returns:** `true` if transitioned to jumpin state, `nil` otherwise
* **Error states:** None

### `ACTIONS.JUMPIN_MAP.stroverridefn(act)`
* **Description:** Returns `'MAP_WORMHOLE'` string.
* **Parameters:** `act` -- action object
* **Returns:** `STRING` value
* **Error states:** None

### `ACTIONS.JUMPIN_MAP.fn(act)`
* **Description:** Handles teleportation through charlieresidue or direct teleporter in jumpin_pre state.
* **Parameters:** `act` -- action object
* **Returns:** `true` if transitioned, `nil` otherwise
* **Error states:** None

### `ACTIONS.TELEPORT.strfn(act)`
* **Description:** Returns `'TOWNPORTAL'` if target is present.
* **Parameters:** `act` -- action object
* **Returns:** `'TOWNPORTAL'` or `nil`
* **Error states:** None

### `ACTIONS.TELEPORT.fn(act)`
* **Description:** Enters entertownportal state using teleporter.
* **Parameters:** `act` -- action object
* **Returns:** `true` if transitioned, `nil` otherwise
* **Error states:** None

### `ACTIONS.RESETMINE.fn(act)`
* **Description:** Resets mine component on target.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.ACTIVATE.fn(act)`
* **Description:** Activates activatable component if not burning/smoldering.
* **Parameters:** `act` -- action object
* **Returns:** `true` with message or `false` with message
* **Error states:** None

### `ACTIONS.ACTIVATE.strfn(act)`
* **Description:** Calls target:GetActivateVerb if present.
* **Parameters:** `act` -- action object
* **Returns:** Verb string or `nil`
* **Error states:** None

### `ACTIONS.ACTIVATE.stroverridefn(act)`
* **Description:** Calls target:OverrideActivateVerb if present.
* **Parameters:** `act` -- action object
* **Returns:** Override verb string or `nil`
* **Error states:** None

### `ACTIONS.OPEN_CRAFTING.strfn(act)`
* **Description:** Returns action string from PROTOTYPER_DEFS.
* **Parameters:** `act` -- action object
* **Returns:** Verb string or `nil`
* **Error states:** None

### `ACTIONS.OPEN_CRAFTING.fn(act)`
* **Description:** Uses prototyper via builder component.
* **Parameters:** `act` -- action object
* **Returns:** Result of `UsePrototyper` or `false`
* **Error states:** None

### `ACTIONS.CAST_POCKETWATCH.strfn(act)`
* **Description:** Calls GetActionVerb_CAST_POCKETWATCH on item if available.
* **Parameters:** `act` -- action object
* **Returns:** Verb string or `nil`
* **Error states:** None

### `ACTIONS.CAST_POCKETWATCH.fn(act)`
* **Description:** Casts pocketwatch spell using pocketwatch component.
* **Parameters:** `act` -- action object
* **Returns:** Result of `CastSpell` or `nil`
* **Error states:** None

### `ACTIONS.HAUNT.fn(act)`
* **Description:** Haunts target if valid, not held, and not already haunted/catchable.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.MURDER.fn(act)`
* **Description:** Murders victim, plays sound, drops loot, transfers inventory.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.HEAL.strfn(act)`
* **Description:** Returns `'SELF'`, `'USEONSELF'`, or `'USE'` based on target, controller, and cannotheal tag.
* **Parameters:** `act` -- action object
* **Returns:** Verb string or `nil`
* **Error states:** None

### `ACTIONS.HEAL.fn(act)`
* **Description:** Heals target using healer or maxhealer components.
* **Parameters:** `act` -- action object
* **Returns:** Result of healer/maxhealer method or `nil`
* **Error states:** None

### `ACTIONS.UNLOCK.fn(act)`
* **Description:** Unlocks target lock component if locked.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.USEKLAUSSACKKEY.fn(act)`
* **Description:** Uses key on klaussacklock component.
* **Parameters:** `act` -- action object
* **Returns:** `true` if successful, `false` with reason otherwise
* **Error states:** None

### `ACTIONS.TEACH.strfn(act)`
* **Description:** Returns appropriate verb for teachable items (scrapbook_note/data, mapspotrevealer, recipescanner).
* **Parameters:** `act` -- action object
* **Returns:** Verb string or `nil`
* **Error states:** None

### `ACTIONS.TEACH.fn(act)`
* **Description:** Teaches via scrapbookable, teacher, maprecorder, mapspotrevealer, or recipescanner components.
* **Parameters:** `act` -- action object
* **Returns:** Result of respective method or `false` with reason
* **Error states:** None

### `ACTIONS.TURNON.fn(act)`
* **Description:** Turns on machine component on target or invobject.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.TURNOFF.strfn(act)`
* **Description:** Returns `'EMERGENCY'` for targets with hasemergencymode tag.
* **Parameters:** `act` -- action object
* **Returns:** `'EMERGENCY'` or `nil`
* **Error states:** None

### `ACTIONS.TURNOFF.fn(act)`
* **Description:** Turns off machine component on target or invobject.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.USEITEM.fn(act)`
* **Description:** Toggles toggleableitem or starts use of useableitem.
* **Parameters:** `act` -- action object
* **Returns:** Result of `toggleableitem:ToggleItem` or `useableitem:StartUsingItem`, `nil` otherwise
* **Error states:** None

### `ACTIONS.USEITEMON.strfn(act)`
* **Description:** Returns uppercase invobject prefab or `'GENERIC'`.
* **Parameters:** `act` -- action object
* **Returns:** `string`
* **Error states:** None

### `ACTIONS.USEITEMON.pre_action_cb(act)`
* **Description:** Closes controller inventory HUD before action.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.USEITEMON.fn(act)`
* **Description:** Uses targeted item via useabletargeteditem component.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** None

### `ACTIONS.STOPUSINGITEM.strfn(act)`
* **Description:** Returns uppercase invobject prefab or `'GENERIC'`.
* **Parameters:** `act` -- action object
* **Returns:** `string`
* **Error states:** None

### `ACTIONS.STOPUSINGITEM.fn(act)`
* **Description:** Stops using targeted item via useabletargeteditem:StopUsingItem.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.TAKEITEM.fn(act)`
* **Description:** Attempts to take an item from a shelf or inventory item holder component.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, otherwise implies failure
* **Error states:** None

### `ACTIONS.TAKEITEM.strfn(act)`
* **Description:** Returns the string key for the TAKEITEM action, based on target prefab.
* **Parameters:** `act` -- action object
* **Returns:** `string` key `'BIRDCAGE'` or `'GENERIC'`
* **Error states:** None

### `ACTIONS.TAKEITEM.stroverridefn(act)`
* **Description:** Generates localized display text for TAKEITEM action, including stack count when applicable.
* **Parameters:** `act` -- action object
* **Returns:** localized string or `nil`
* **Error states:** None

### `ACTIONS.TAKESINGLEITEM.fn(act)`
* **Description:** Takes a single item from an inventory item holder, preventing full stack transfer.
* **Parameters:** `act` -- action object
* **Returns:** result of `inventoryitemholder:TakeItem`, or `nil`
* **Error states:** None

### `ACTIONS.TAKESINGLEITEM.stroverridefn(act)`
* **Description:** Returns static localized string for TAKESINGLEITEM action.
* **Parameters:** `act` -- action object
* **Returns:** localized string
* **Error states:** None

### `ACTIONS.CASTSPELL.strfn(act)`
* **Description:** Returns the spell type name from the invocation object or hand item for display.
* **Parameters:** `act` -- action object
* **Returns:** spelltype string or `nil`
* **Error states:** None

### `ACTIONS.CASTSPELL.fn(act)`
* **Description:** Handles spell casting using a staff, checking mimic state, combat restrictions, and spellcaster CanCast/CastSpell.
* **Parameters:** `act` -- action object
* **Returns:** `true` on cast success, `false` with reason on failure
* **Error states:** `ITEMMIMIC`, rider status, heavy lifting,CanCast failure

### `ACTIONS.DIRECTCOURIER_MAP.maponly_checkvalidpos_fn(act)`
* **Description:** Finds valid target position within courier detection radius (chest or player globalmapicon), returning target entity if found.
* **Parameters:** `act` -- action object
* **Returns:** `true, nil, act_posx, act_posz, mapent` on success, else `false` with reason
* **Error states:** `NOTARGET`, skilltree check, distance exceeding radius

### `ACTIONS.DIRECTCOURIER_MAP.stroverridefn(act)`
* **Description:** Generates localized string for DIRECTCOURIER_MAP action based on target type (player or chest).
* **Parameters:** `act` -- action object
* **Returns:** localized string or `nil`
* **Error states:** None

### `ACTIONS.DIRECTCOURIER_MAP.fn(act)`
* **Description:** Sends courier command to teleport item via woby_commands_classified.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` on invalid conditions
* **Error states:** Invalid target, missing classified state, non-player

### `TryToSoulhop(act, act_pos, consumeall)`
* **Description:** Helper function to check conditions and initiate soulhop via portal_jumpin state.
* **Parameters:**
  - `act` -- action object
  - `act_pos` -- destination position
  - `consumeall` -- boolean whether to consume all souls
* **Returns:** `bool` indicating whether portal hop was attempted
* **Error states:** Missing stategraph, missing portal, invalid distance

### `ACTIONS.BLINK.strfn(act)`
* **Description:** Returns display string for BLINK action, distinguishing free soul hops and regular soul hops.
* **Parameters:** `act` -- action object
* **Returns:** string key `'FREESOUL'`, `'SOUL'`, or `nil`
* **Error states:** None

### `ACTIONS.BLINK.fn(act)`
* **Description:** Performs blink using blinkstaff or soulhop state transition for soulstealer characters.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason on failure
* **Error states:** `ITEMMIMIC`, blink in progress, invalid destination

### `ACTIONS.BLINK_MAP.stroverridefn(act)`
* **Description:** Returns display string for BLINK_MAP action, indicating soul count needed for map-based hop.
* **Parameters:** `act` -- action object
* **Returns:** localized string or `nil`
* **Error states:** None

### `ActionCanMapSoulhop(act)`
* **Description:** Checks if map-based soulhop is permitted via CanSoulhop on the doer.
* **Parameters:** `act` -- action object
* **Returns:** result of canSoulhop or `false`
* **Error states:** None

### `ACTIONS.BLINK_MAP.fn(act)`
* **Description:** Initiated map-assisted soulhop by transitioning to portal_jumpin state.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` or `nil` on failure
* **Error states:** CanSoulhop failure, invalid position

### `ACTIONS_MAP_REMAP[ACTIONS.BLINK.code](act, targetpos)`
* **Description:** Remaps BLINK to BLINK_MAP action for map-based teleport, handling map tile detection and platform alignment.
* **Parameters:**
  - `act` -- action object
  - `targetpos` -- destination position
* **Returns:** remapped action or `nil`
* **Error states:** No valid map tile, boat detection failure

### `ACTIONS.CASTSUMMON.fn(act)`
* **Description:** Summons a ghost using ghostlybond component if summoning item is equipped.
* **Parameters:** `act` -- action object
* **Returns:** result of `ghostlybond:Summon`, or `nil`
* **Error states:** Missing ghostlybond, missing summoningitem component

### `ACTIONS.CASTUNSUMMON.fn(act)`
* **Description:** Recalls a summoned ghost via `ghostlybond:Recall`.
* **Parameters:** `act` -- action object
* **Returns:** result of `ghostlybond:Recall`, or `nil`
* **Error states:** Missing ghostlybond, missing summoningitem component

### `ACTIONS.COMMUNEWITHSUMMONED.strfn(act)`
* **Description:** Returns string key for COMMUNEWITHSUMMONED action, depending on aggressive follower tag.
* **Parameters:** `act` -- action object
* **Returns:** `'MAKE_DEFENSIVE'` or `'MAKE_AGGRESSIVE'`, or `nil`
* **Error states:** None

### `ACTIONS.COMMUNEWITHSUMMONED.fn(act)`
* **Description:** Changes summoned follower behavior via `ghostlybond:ChangeBehaviour`.
* **Parameters:** `act` -- action object
* **Returns:** result of `ghostlybond:ChangeBehaviour`, or `nil`
* **Error states:** Missing ghostlybond, missing summoningitem component

### `ACTIONS.COMBINESTACK.fn(act)`
* **Description:** Attempts to merge stacks of identical items.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, otherwise `nil`
* **Error states:** Mismatched prefabs/skins, stack full

### `ACTIONS.TRAVEL.fn(act)`
* **Description:** Invokes travel_action_fn on target for world travel actions.
* **Parameters:** `act` -- action object
* **Returns:** `true` if travel_action_fn executed, otherwise `nil`
* **Error states:** No travel_action_fn

### `ACTIONS.UNPIN.fn(act)`
* **Description:** Unpins a target that is stuck via pinnable component.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, otherwise `nil`
* **Error states:** Not stuck, missing pinnable, same as doer

### `ACTIONS.STEALMOLEBAIT.fn(act)`
* **Description:** Handles mole stealing bait from target.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success
* **Error states:** Not mole or missing target

### `ACTIONS.MAKEMOLEHILL.fn(act)`
* **Description:** Spawns molehill or molebathill at mole/molebat position.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, otherwise `nil`
* **Error states:** Not mole or molebat

### `ACTIONS.MOLEPEEK.fn(act)`
* **Description:** Triggers peek event on mole character.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.FEED.strfn(act)`
* **Description:** Returns string key for FEED action, depending on pet treat tag.
* **Parameters:** `act` -- action object
* **Returns:** `'TREAT'` or `nil`
* **Error states:** None

### `ACTIONS.FEED.fn(act)`
* **Description:** Feeds target via trader or eater component, handling death and loot.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason on failure
* **Error states:** `ITEMMIMIC`, no valid target, CanEat failure

### `ACTIONS.HAIRBALL.fn(act)`
* **Description:** Placeholder action for catcoon hairball behavior.
* **Parameters:** `act` -- action object
* **Returns:** `true` if catcoon doer, otherwise `nil`
* **Error states:** Not catcoon

### `ACTIONS.CATPLAYGROUND.fn(act)`
* **Description:** Simulates catcoon playground interactions: playing toys, popping items, attacking small targets, picking up items, activating objects.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.CATPLAYAIR.fn(act)`
* **Description:** Simulates catcoon air-play interactions similar to CATPLAYGROUND, including state timer update.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.ERASE_PAPER.fn(act)`
* **Description:** Erases paper using papereraser and erasablepaper components.
* **Parameters:** `act` -- action object
* **Returns:** result of `papereraser:DoErase`, or `nil`
* **Error states:** Fire/burnt target, missing components

### `ACTIONS.FAN.fn(act)`
* **Description:** Uses fan component on target or doer.
* **Parameters:** `act` -- action object
* **Returns:** result of `fan:Fan`, `false` with reason if mimic
* **Error states:** `ITEMMIMIC`, missing fan component

### `ACTIONS.TOSS.fn(act)`
* **Description:** Tosses an item as a projectile via complexprojectile component.
* **Parameters:** `act` -- action object
* **Returns:** `true` on launch success, `nil` if toss blocked
* **Error states:** Invalid projectile, restricted equippable, itemmimic

### `ACTIONS.WATER_TOSS.fn(act)`
* **Description:** Alias to `ACTIONS.TOSS.fn` for water-specific toss behavior.
* **Parameters:** `act` -- action object
* **Returns:** same as `TOSS.fn`
* **Error states:** None

### `ACTIONS.TOSS_MAP.stroverridefn(act)`
* **Description:** Returns localized TOSS action string if CanTossOnMap succeeds.
* **Parameters:** `act` -- action object
* **Returns:** localized string or `nil`
* **Error states:** No CanTossOnMap support

### `ActionCanMapToss(act)`
* **Description:** Helper to validate map-based toss via CanTossOnMap.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** None

### `ACTIONS.TOSS_MAP.fn(act)`
* **Description:** Executes TOSS action while flagged as map-based (from_map=true).
* **Parameters:** `act` -- action object
* **Returns:** result of `TOSS.fn`, or `nil`
* **Error states:** Invalid toss conditions

### `ACTIONS_MAP_REMAP[ACTIONS.TOSS.code](act, targetpos)`
* **Description:** Remaps TOSS for map-based targeting with distance clamping and ocean tile validation.
* **Parameters:**
  - `act` -- action object
  - `targetpos` -- destination position
* **Returns:** remapped action or `nil`
* **Error states:** Not ocean tile, invalid distance

### `ACTIONS.UPGRADE.fn(act)`
* **Description:** Attempts to upgrade an object using upgrader and upgradeable components.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason on failure
* **Error states:** Upgrade conditions not met, CanUpgrade failure

### `ACTIONS.UPGRADE.strfn(act)`
* **Description:** Returns string key based on `UPGRADETYPES.WATERPLANT` tag.
* **Parameters:** `act` -- action object
* **Returns:** `'WATERPLANT'` or `nil`
* **Error states:** None

### `ACTIONS.NUZZLE.fn(act)`
* **Description:** Placeholder action for affection behavior.
* **Parameters:** `act` -- action object
* **Returns:** `true` if target exists
* **Error states:** None

### `ACTIONS.WRITE.fn(act)`
* **Description:** Begins writing on an unwritten writeable target via writeable component.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason if in use or dark
* **Error states:** `INUSE`, CanEntitySeeTarget failure

### `ACTIONS.ATTUNE.fn(act)`
* **Description:** Attunes target to player via attunable component.
* **Parameters:** `act` -- action object
* **Returns:** result of `attunable:LinkToPlayer`, or `nil`
* **Error states:** Missing attunable component

### `ACTIONS.MIGRATE.fn(act)`
* **Description:** Initiates world migration via worldmigrator component.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason
* **Error states:** `NODESTINATION`, missing worldmigrator

### `ACTIONS.REMOTERESURRECT.fn(act)`
* **Description:** Requests respawn via remote resurrector via attuner and ghost state.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** Missing attuner, no attuned target

### `ACTIONS.REVIVE_CORPSE.fn(act)`
* **Description:** Attempts to revive a corpse if allowed by revivablecorpse component.
* **Parameters:** `act` -- action object
* **Returns:** `true` (silent failure if invalid)
* **Error states:** Not revivable by doer

### `ACTIONS.MOUNT.fn(act)`
* **Description:** Mounts a rideable target if conditions are satisfied (not in combat, not dead/frozen, not already ridden).
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason on failure
* **Error states:** `TARGETINCOMBAT`, `INUSE`, specific rider tag check

### `ACTIONS.DISMOUNT.fn(act)`
* **Description:** Dismounts from the current mount via rider:Dismount.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** Not riding

### `ACTIONS.SADDLE.fn(act)`
* **Description:** Equips saddle onto a rideable mount, removing the item from inventory.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason
* **Error states:** `TARGETINCOMBAT`, dead mount, itemmimic

### `ACTIONS.UNSADDLE.fn(act)`
* **Description:** Removes current saddle from a rideable mount.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason
* **Error states:** `TARGETINCOMBAT`, dead mount, itemmimic

### `ACTIONS.BRUSH.fn(act)`
* **Description:** Brushes a brushable target via brushable component.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` with reason
* **Error states:** `TARGETINCOMBAT`, dead target, itemmimic, missing brushable

### `ACTIONS.ABANDON.fn(act)`
* **Description:** Abandons pet by despawning or stopping following, depending on components.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` or `nil` otherwise
* **Error states:** Orphanage tech not built, follower not owned by doer

### `COMPARE_WEIGHABLE_TEST(target, weighable)`
* **Description:** Checks if a target and weighable item share a matching trophy type tag prefix.
* **Parameters:**
  - `target` -- entity to compare
  - `weighable` -- item with weighable component
* **Returns:** `true` if matching type tags found, `false` otherwise
* **Error states:** None

### `GetLowerSailStr(act)`
* **Description:** Selects the appropriate action string index based on the `'switchtoho'` tag.
* **Parameters:** `act` -- action object
* **Returns:** String index (1 or 2)
* **Error states:** None

### `IsBoatCannonAmmo(item)`
* **Description:** Verifies that an item qualifies as boat cannon ammunition.
* **Parameters:** `item` -- item to check
* **Returns:** `true` if item has `projectileprefab` and `'boatcannon_ammo'` tag, `false` otherwise
* **Error states:** None

### `ACTIONS.PET.fn(act)`
* **Description:** Pet a creature: triggers crittertraits pet state if present and emits `on_petted` event to kitcoons.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** `act.target` nil or missing components → nil

### `ACTIONS.RETURN_FOLLOWER.fn(act)`
* **Description:** Returns a follower to its den within proximity if the player is near a kitcoinden.
* **Parameters:** `act` -- action object
* **Returns:** `true` if returned, `false` if den not found
* **Error states:** `act.target` missing follower or not led by doer, or den not found → false

### `ACTIONS.HIDEANSEEK_FIND.fn(act)`
* **Description:** Search a hiding spot: calls `hideandseekhidingspot:SearchHidingSpot` if present.
* **Parameters:** `act` -- action object
* **Returns:** `true` if search performed, `nil` otherwise
* **Error states:** No target/hiding spot → nil

### `ACTIONS.DRAW.stroverridefn(act)`
* **Description:** Overrides display string for drawing action by listing the item being drawn.
* **Parameters:** `act` -- action object
* **Returns:** Formatted string or `nil`
* **Error states:** No item found → nil

### `ACTIONS.DRAW.fn(act)`
* **Description:** Attempts to draw on a target using a drawing tool (requires drawingtool, drawable, candraw).
* **Parameters:** `act` -- action object
* **Returns:** `true` if drawing succeeded, `false` or `'NOIMAGE'` if image unavailable
* **Error states:** Missing components or `CanDraw()` → false; `GetImageToDraw` returns nil → false, `'NOIMAGE'`

### `ACTIONS.STARTCHANNELING.strfn(act)`
* **Description:** Returns `'PUMP'` action string if target has `'pump'` tag.
* **Parameters:** `act` -- action object
* **Returns:** `'PUMP'` or `nil`
* **Error states:** None

### `ACTIONS.STARTCHANNELING.fn(act)`
* **Description:** Starts channeling on a channelable target.
* **Parameters:** `act` -- action object
* **Returns:** Result of `channelable:StartChanneling (true/false)`, or `nil` if target nil
* **Error states:** `act.target` nil → nil

### `ACTIONS.STOPCHANNELING.fn(act)`
* **Description:** Stops channeling on a target if present.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.START_CHANNELCAST.strfn(act)`
* **Description:** Returns `'LIGHTER'` action string if the off-hand item has `'lighter'` tag.
* **Parameters:** `act` -- action object
* **Returns:** `'LIGHTER'` or `nil`
* **Error states:** None

### `ACTIONS.START_CHANNELCAST.fn(act)`
* **Description:** Starts channel casting via channelcaster: either off-hand or equipped item (with channelcastable). Blocks mimic items.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` or `'ITEMMIMIC'` on failure
* **Error states:** No channelcaster, invalid item, or itemmimic → false; `'ITEMMIMIC'` if mimic present

### `ACTIONS.STOP_CHANNELCAST.fn(act)`
* **Description:** Stops channel casting if user is channeling with the target channelcastable. Blocks mimic items.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds), `'ITEMMIMIC'` if mimic present
* **Error states:** itemmimic → false, `'ITEMMIMIC'`

### `ACTIONS.BUNDLE.fn(act)`
* **Description:** Starts bundling if bundler is ready; silently fails if doer cannot see.
* **Parameters:** `act` -- action object
* **Returns:** Result of `bundler:StartBundling` or `true` if dark
* **Error states:** No bundler, cannot start bundling, or darkness → true (silent fail)

### `ACTIONS.WRAPBUNDLE.fn(act)`
* **Description:** Finishes bundling if container has items; alerts if empty.
* **Parameters:** `act` -- action object
* **Returns:** Result of `bundler:FinishBundling` or `true` (alerts if empty)
* **Error states:** Not bundling, empty container → true; empty sound played if talker present

### `ACTIONS.UNWRAP.fn(act)`
* **Description:** Unwraps an unwrappable item that can be unwrapped.
* **Parameters:** `act` -- action object
* **Returns:** `true` after calling `Unwrap`, `nil` otherwise
* **Error states:** No unwrappable or `cannotbeunwrapped` → nil

### `ACTIONS.PEEKBUNDLE.fn(act)`
* **Description:** Peeks inside a container bundle if allowed (not burning, has canpeek tag, bundler ready).
* **Parameters:** `act` -- action object
* **Returns:** Result of `unwrappable:PeekInContainer` or `nil`
* **Error states:** Missing conditions (e.g., fire tags, missing bundler) → nil

### `ACTIONS.BREAK.strfn(act)`
* **Description:** Returns `'PICKAPART'` if target/invobject has pickapart tag.
* **Parameters:** `act` -- action object
* **Returns:** `'PICKAPART'` or `nil`
* **Error states:** None

### `ACTIONS.CONSTRUCT.stroverridefn(act)`
* **Description:** Overrides string with formatted construction name (from constructionname or prefab).
* **Parameters:** `act` -- action object
* **Returns:** Formatted name string or `nil`
* **Error states:** No name found → nil

### `ACTIONS.CONSTRUCT.strfn(act)`
* **Description:** Returns construction type string: `OFFER/STORE/OFFER_TO/REPAIR/REBUILD` based on target tags.
* **Parameters:** `act` -- action object
* **Returns:** One of `'OFFER','STORE','OFFER_TO','REPAIR','REBUILD'`, or `nil`
* **Error states:** None

### `ACTIONS.CONSTRUCT.fn(act)`
* **Description:** Starts construction: spawns site, applies plans, stores items, handles failure cases.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false/'REASON'` or `'INUSE','BURNT','NOTALLOWED','COOKING'` on failure
* **Error states:** Darkness → true (silent fail); invalid builder or state → false; dark → true; invalid item → false/'REASON'; container not allowed → talker + `'NOTALLOWED'`

### `ACTIONS.STOPCONSTRUCTION.stroverridefn(act)`
* **Description:** Overrides string with formatted stop construction name.
* **Parameters:** `act` -- action object
* **Returns:** Formatted name string or `nil`
* **Error states:** None

### `ACTIONS.STOPCONSTRUCTION.strfn(act)`
* **Description:** Returns stop construction type string based on target tags.
* **Parameters:** `act` -- action object
* **Returns:** `'OFFER','REPAIR','REBUILD', or nil`
* **Error states:** None

### `ACTIONS.STOPCONSTRUCTION.fn(act)`
* **Description:** Stops current construction via constructionbuilder.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.APPLYCONSTRUCTION.strfn(act)`
* **Description:** Returns construction type string (same as `STOPCONSTRUCTION.strfn`).
* **Parameters:** `act` -- action object
* **Returns:** `'OFFER','REPAIR','REBUILD', or nil`
* **Error states:** None

### `ACTIONS.APPLYCONSTRUCTION.fn(act)`
* **Description:** Finishes ongoing construction if container not empty; alerts if empty.
* **Parameters:** `act` -- action object
* **Returns:** Result of `FinishConstruction` or `true` (alerts if empty)
* **Error states:** Not constructing or container empty → true (talker alert)

### `ACTIONS.CASTAOE.stroverridefn(act)`
* **Description:** Overrides string with spell name from spellbook.
* **Parameters:** `act` -- action object
* **Returns:** Spell name string or `nil`
* **Error states:** None

### `ACTIONS.CASTAOE.strfn(act)`
* **Description:** Returns uppercase prefab name of the item.
* **Parameters:** `act` -- action object
* **Returns:** String or `nil`
* **Error states:** None

### `ACTIONS.CASTAOE.fn(act)`
* **Description:** Casts AoE spell if valid; checks mimic and cancast conditions.
* **Parameters:** `act` -- action object
* **Returns:** Result of `CastSpell` or `false/'ITEMMIMIC'`
* **Error states:** Missing components or CanCast fails → false; itemmimic → false, `'ITEMMIMIC'`

### `ACTIONS.SCYTHE.fn(act)`
* **Description:** Calls DoScythe on the inventory item if present; blocks mimic.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` or `'ITEMMIMIC'`
* **Error states:** No DoScythe or itemmimic → false; `'ITEMMIMIC'` if mimic present

### `ACTIONS.NABBAG.fn(act)`
* **Description:** Invokes nabbag:DoNabFromAct for the item; blocks mimic.
* **Parameters:** `act` -- action object
* **Returns:** Result of DoNabFromAct or `false/'ITEMMIMIC'`
* **Error states:** No nabbag or mimic → false; `'ITEMMIMIC'` if mimic present

### `ACTIONS.DISMANTLE.fn(act)`
* **Description:** Dismantles portable structure if not burning (or campfire), container not in use/empty, and candismantle allowed.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false/'REASON'` (`INUSE`, `NOTEMPTY`, `COOKING`)
* **Error states:** Burning non-campfire, container in use, non-empty, cooking, or candismantle false → false/'REASON'

### `ACTIONS.TACKLE.fn(act)`
* **Description:** Calls `tackler:StartTackle` on the doer.
* **Parameters:** `act` -- action object
* **Returns:** Result of `StartTackle` or `nil`
* **Error states:** No tackler → nil

### `ACTIONS.HALLOWEENMOONMUTATE.fn(act)`
* **Description:** Uses potion to mutate target if conditions met (not burning/smoldering/frozen).
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` if conditions unmet
* **Error states:** Target missing, burning, smoldering, or frozen → false

### `ACTIONS.APPLYPRESERVATIVE.strfn(act)`
* **Description:** Returns `'SALT'` if item is saltrock.
* **Parameters:** `act` -- action object
* **Returns:** `'SALT'` or `nil`
* **Error states:** None

### `ACTIONS.APPLYPRESERVATIVE.fn(act)`
* **Description:** Increases perishable percent by preservative effect; handles stack-size division.
* **Parameters:** `act` -- action object
* **Returns:** `true` if item removed, `false` otherwise
* **Error states:** Invalid target, missing perishable tags, or removal failure → false

### `ACTIONS.COMPARE_WEIGHABLE.fn(act)`
* **Description:** Compares weight of target vs weighed item using trophyyscale if types match.
* **Parameters:** `act` -- action object
* **Returns:** Result of `Compare` or `false`
* **Error states:** Missing components, tags, or fire/burnt → false

### `ACTIONS.WEIGH_ITEM.fn(act)`
* **Description:** Uses itemweigher to weigh an item on a weighable entity.
* **Parameters:** `act` -- action object
* **Returns:** Result of `DoWeighIn` or `false`
* **Error states:** No weigher/weighable or fire/burnt → false

### `ACTIONS.START_CARRAT_RACE.fn(act)`
* **Description:** Starts a carrat race if race start is interactive, racers exist, and not fire/burnt.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false/'NO_RACERS'`
* **Error states:** Race start unavailable or no racers → false/'NO_RACERS'

### `ACTIONS.TILL.fn(act)`
* **Description:** Tills soil using farmtiller or quagmire_tiller; blocks mimic.
* **Parameters:** `act` -- action object
* **Returns:** Result of `Till` or `false/'ITEMMIMIC'`
* **Error states:** No tiller or mimic → false; `'ITEMMIMIC'` if mimic present

### `ACTIONS.PLANTSOIL.fn(act)`
* **Description:** Plants seed on soil using farmplantable or quagmire_plantable; restores seed if planting fails.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** No seed, missing plantable, or planting failure → nil (seed returned)

### `ACTIONS.INSTALL.fn(act)`
* **Description:** Installs quagmire_installable or saltextractor on compatible targets.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** No installable, target not enabled, or spawn failure → nil

### `ACTIONS.TAPTREE.fn(act)`
* **Description:** Taps/uninstalls tap on tree using quagmire_tappable and quagmire_tapper.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** No tappable or missing tapper → nil

### `ACTIONS.TAPTREE.strfn(act)`
* **Description:** Returns `'UNTAP'` if target not tappable.
* **Parameters:** `act` -- action object
* **Returns:** `'UNTAP'` or `nil`
* **Error states:** None

### `ACTIONS.SLAUGHTER.stroverridefn(act)`
* **Description:** Returns custom slaughter string via `GetSlaughterActionString` on tool.
* **Parameters:** `act` -- action object
* **Returns:** Custom string or `nil`
* **Error states:** No custom string → nil

### `ACTIONS.SLAUGHTER.fn(act)`
* **Description:** Slaughters canbeslaughtered target if valid and nearby; uses quagmire_slaughtertool.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false/'TOOFAR'`
* **Error states:** Target missing/invalid, not near, or alive → false/'TOOFAR'

### `ACTIONS.REPLATE.stroverridefn(act)`
* **Description:** Returns formatted replating string for Quagmire replatable items.
* **Parameters:** `act` -- action object
* **Returns:** Formatted string or `nil`
* **Error states:** No replatable or no dish name → nil

### `ACTIONS.BATHBOMB.fn(act)`
* **Description:** Applies bathbomb to bathbombable target and removes bathbomb item.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** No bathbomb or bathbombable or not `can_be_bathbombed` → nil

### `ACTIONS.RAISE_SAIL.fn(act)`
* **Description:** Unfurls sail on mast.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** No mast → nil

### `ACTIONS.LOWER_SAIL.fn(act)`
* **Description:** Placeholder for lowering sail (false-positive name); always returns true.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.LOWER_SAIL_BOOST.fn(act)`
* **Description:** Boosts sail lowering with expert sailor strength and master crewman multiplier; adds furler and fires event.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** No mast, sail not raised → nil

### `ACTIONS.LOWER_SAIL_FAIL.fn(act)`
* **Description:** Placeholder for failed sail lowering; always returns true.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.RAISE_ANCHOR.fn(act)`
* **Description:** Adds anchor raiser to target anchor.
* **Parameters:** `act` -- action object
* **Returns:** Result of `AddAnchorRaiser (true/false)`
* **Error states:** None

### `ACTIONS.LOWER_ANCHOR.fn(act)`
* **Description:** Starts lowering target anchor.
* **Parameters:** `act` -- action object
* **Returns:** Result of `StartLoweringAnchor (true/false)`
* **Error states:** None

### `ACTIONS.MOUNT_PLANK.fn(act)`
* **Description:** Mounts walking plank for doer.
* **Parameters:** `act` -- action object
* **Returns:** Result of `MountPlank (true/false)`
* **Error states:** None

### `ACTIONS.DISMOUNT_PLANK.fn(act)`
* **Description:** Dismounts doer from walking plank.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.ABANDON_SHIP.fn(act)`
* **Description:** Abandons ship via walking plank for doer.
* **Parameters:** `act` -- action object
* **Returns:** Result of `AbandonShip (true/false)`
* **Error states:** None

### `ACTIONS.EXTEND_PLANK.fn(act)`
* **Description:** Extends walking plank.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.RETRACT_PLANK.fn(act)`
* **Description:** Retracts walking plank.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.REPAIR_LEAK.fn(act)`
* **Description:** Repairs boat leak using repair item.
* **Parameters:** `act` -- action object
* **Returns:** Result of `Repair` or `nil`
* **Error states:** Missing leak or item → nil

### `ACTIONS.STEER_BOAT.pre_action_cb(act)`
* **Description:** Closes spell wheel before steering.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.STEER_BOAT.fn(act)`
* **Description:** Sets doer's steering wheel if available, unoccupied, and not burning.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** Occupied, burning, or missing components → nil

### `ACTIONS.SET_HEADING.fn(act)`
* **Description:** Sets boat heading via `steeringwheeluser:Steer` at action point.
* **Parameters:** `act` -- action object
* **Returns:** Result of `Steer (true/false)`
* **Error states:** No `steeringwheeluser` or invalid position → false

### `ACTIONS.STOP_STEERING_BOAT.fn(act)`
* **Description:** Stops steering by clearing steering wheel reference.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.CAST_NET.fn(act)`
* **Description:** Casts fishing net at action point or target position; blocks mimic.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false` or `'ITEMMIMIC'`
* **Error states:** No fishingnet or mimic → false; `'ITEMMIMIC'` if mimic present

### `ACTIONS.ROTATE_BOAT_CLOCKWISE.fn(act)`
* **Description:** Sets rotation direction to `1` on boatrotator.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.ROTATE_BOAT_COUNTERCLOCKWISE.fn(act)`
* **Description:** Sets rotation direction to `-1` on boatrotator.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.ROTATE_BOAT_STOP.fn(act)`
* **Description:** Sets rotation direction to `0` on boatrotator.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.BOAT_MAGNET_ACTIVATE.fn(act)`
* **Description:** Transitions boatmagnet to `search_pre` state.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.BOAT_MAGNET_DEACTIVATE.fn(act)`
* **Description:** Unpairs magnet beacon via `boatmagnet:UnpairWithBeacon`.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.BOAT_MAGNET_BEACON_TURN_ON.fn(act)`
* **Description:** Turns on beacon via `boatmagnetbeacon:TurnOnBeacon`.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** No beacon or component → returns true (early exit)

### `ACTIONS.BOAT_MAGNET_BEACON_TURN_OFF.fn(act)`
* **Description:** Turns off beacon via `boatmagnetbeacon:TurnOffBeacon`.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** No beacon or component → returns true (early exit)

### `ACTIONS.BOAT_CANNON_LOAD_AMMO.fn(act)`
* **Description:** Loads cannon with valid ammo; removes ammo and announces.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `true` (silent if no ammo)
* **Error states:** Not loaded, no ammo → true (talker alert)

### `ACTIONS.BOAT_CANNON_START_AIMING.pre_action_cb(act)`
* **Description:** Closes spell wheel before aiming cannon.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.BOAT_CANNON_START_AIMING.fn(act)`
* **Description:** Sets doer's cannon user to target cannon if available and unoccupied.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `nil` otherwise
* **Error states:** Occupied, burning, or missing components → nil

### `ACTIONS.BOAT_CANNON_SHOOT.fn(act)`
* **Description:** Shoots cannon via state graph: either user-cannon or direct target.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.BOAT_CANNON_STOP_AIMING.fn(act)`
* **Description:** Stops aiming by clearing cannon user.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.OCEAN_TRAWLER_LOWER.fn(act)`
* **Description:** Lowers ocean trawler.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.OCEAN_TRAWLER_RAISE.fn(act)`
* **Description:** Raises ocean trawler.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.OCEAN_TRAWLER_FIX.fn(act)`
* **Description:** Fixes trawler and announces fix.
* **Parameters:** `act` -- action object
* **Returns:** `true` (always succeeds)
* **Error states:** None

### `ACTIONS.GIVE_TACKLESKETCH.fn(act)`
* **Description:** Teaches tackle sketch recipe if target doesn't know it yet; blocks burnt targets.
* **Parameters:** `act` -- action object
* **Returns:** `true` on success, `false/'DUPLICATE'`
* **Error states:** No crafting station, burnt, duplicate → false/'DUPLICATE'

### `ACTIONS.REMOVE_FROM_TROPHYSCALE.fn(act)`
* **Description:** Removes an item from a trophy scale if the target is valid and conditions are met.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` with optional reason string
* **Error states:** Target is burnt, on fire, lacks trophy component, or test function fails

### `ACTIONS.CYCLE.strfn(act)`
* **Description:** Returns string key for singing shell cycling UI hint.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** None

### `ACTIONS.CYCLE.fn(act)`
* **Description:** Cycles through states of a target entity if it has a cyclable component and allows cycling.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Target lacks cyclable component or cycling is disallowed

### `ACTIONS.OCEAN_TOSS.fn(act)`
* **Description:** Drops an ocean throwable item and launches it as a projectile toward the action target or point.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Item is mimic or lacks `oceanthrowable`/`complexprojectile` components

### `ACTIONS.WINTERSFEAST_FEAST.fn(act)`
* **Description:** Placeholder action stub for winter's feast feast logic handled in stategraph.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.BEGIN_QUEST.fn(act)`
* **Description:** Starts a new quest on the target if possible.
* **Parameters:** `act` -- action object
* **Returns:** `success (bool)` with message string
* **Error states:** Target lacks questowner component or condition functions prevent start

### `ACTIONS.ABANDON_QUEST.fn(act)`
* **Description:** Attempts to abandon the active quest on the target.
* **Parameters:** `act` -- action object
* **Returns:** `success (bool)` with message string
* **Error states:** Target lacks questowner or can't abandon condition is false

### `ACTIONS.SING.fn(act)`
* **Description:** Adds a song from the held item to the singer's inspiration if conditions match.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Item or singer missing required components, song already active

### `ACTIONS.SING_FAIL.fn(act)`
* **Description:** Stub function that always returns true for singing fail state.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.SING_FAIL.stroverridefn(act)`
* **Description:** Overrides string for SING_FAIL action to return generic SING string.
* **Parameters:** `act` -- action object
* **Returns:** string
* **Error states:** None

### `ACTIONS.REPLATE.fn(act)`
* **Description:** Replaces one food plate with another of different type in Quagmire cooking mechanics.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Missing replater/replatable components or type mismatch

### `ACTIONS.SALT.fn(act)`
* **Description:** Applies salt to a food plate, spawning a new salted entity in inventory or dropping on ground.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Target lacks quagmire_saltable component

### `ACTIONS.UNPATCH.fn(act)`
* **Description:** Removes a patch from a boat leak and restores some health, flinging the patch item.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Target lacks `boatleak` component or missing lootdropper/failure to spawn patch

### `ACTIONS.POUR_WATER.fn(act)`
* **Description:** Uses water from an item to spread protection to a target entity or point, extinguishing fires if present.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Item is mimic, empty watering can, or target invalid

### `ACTIONS.POUR_WATER.strfn(act)`
* **Description:** Returns string key when target is on fire or smoldering.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** None

### `ACTIONS.POUR_WATER_GROUNDTILE.fn(act)`
* **Description:** Alias to `POUR_WATER.fn`.
* **Parameters:** `act` -- action object
* **Returns:** see `POUR_WATER.fn`
* **Error states:** see `POUR_WATER.fn`

### `ACTIONS.POUR_WATER_GROUNDTILE.stroverridefn(act)`
* **Description:** Overrides string to generic `POUR_WATER` string for ground tile use.
* **Parameters:** `act` -- action object
* **Returns:** string
* **Error states:** None

### `ACTIONS.PLANTREGISTRY_RESEARCH_FAIL.fn(act)`
* **Description:** Stub for failed research actions, returning false with reason if fertilizer.
* **Parameters:** `act` -- action object
* **Returns:** `false` with reason or `false`
* **Error states:** Item is mimic or target is fertilizer

### `ACTIONS.PLANTREGISTRY_RESEARCH.fn(act)`
* **Description:** Researches a plant or fertilizer item, announcing result if talker component present.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Item is mimic or target lacks researchable components

### `ACTIONS.ASSESSPLANTHAPPINESS.stroverridefn(act)`
* **Description:** Overrides string to show plant name with generic assessment format.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** Plant display name missing

### `ACTIONS.ASSESSPLANTHAPPINESS.fn(act)`
* **Description:** Assesses plant happiness via stress or default description, speaking via talker component.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Item is mimic or assessment string missing

### `ACTIONS.PLANTWEED.fn(act)`
* **Description:** Spawns a random weed on a soil tile based on weighted seed table.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** Target not soil or spawn failure

### `ACTIONS.ADDCOMPOSTABLE.fn(act)`
* **Description:** Adds an item to a composting bin using `AddCompostable` function.
* **Parameters:** `act` -- action object
* **Returns:** result from `AddCompostable (bool)`
* **Error states:** Target lacks `compostingbin` component

### `ACTIONS.WAX.fn(act)`
* **Description:** Applies wax to a target item if possible, consuming the wax item.
* **Parameters:** `act` -- action object
* **Returns:** result from `waxfn` or `false` with reason
* **Error states:** Target lacks `waxable` component or item is mimic

### `ACTIONS.UNLOAD_WINCH.fn(act)`
* **Description:** Calls winch's `unloadfn` callback to handle unloading.
* **Parameters:** `act` -- action object
* **Returns:** result of `unloadfn`
* **Error states:** Winch or callback missing

### `ACTIONS.USE_HEAVY_OBSTACLE.strfn(act)`
* **Description:** Returns the string key stored on the target for heavy obstacle use.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** None

### `ACTIONS.USE_HEAVY_OBSTACLE.fn(act)`
* **Description:** Uses the equipped heavy item on the obstacle if conditions are met.
* **Parameters:** `act` -- action object
* **Returns:** result from `UseHeavyObstacle` or `false`
* **Error states:** No heavy item equipped, target not usable, or filter fails

### `ACTIONS.YOTB_SEW.fn(act)`
* **Description:** Starts or continues sewing on a sewing machine, validating container state.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Not a sewing machine, already sewing, container in use, or can't sew

### `ACTIONS.YOTB_STARTCONTEST.fn(act)`
* **Description:** Starts a contest in YOTB if conditions allow: no active contest, host visible, correct target.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** No stagemanager, contest active, host missing, or wrong target

### `ACTIONS.YOTB_UNLOCKSKIN.fn(act)`
* **Description:** Unlocks a skin via skin unlocker item, using YOTB set/unlock functions.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Missing components, skin already known, or setup missing

### `ACTIONS.MUTATE_SPIDER.fn(act)`
* **Description:** Mutates a spider if the mutator item can mutate the target.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Target is same type or mutation not allowed

### `ACTIONS.HERD_FOLLOWERS.fn(act)`
* **Description:** Herd or disband herd on a leader's followers using followerherder component.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Can't herd due to component logic or cooldown

### `ACTIONS.BEDAZZLE.fn(act)`
* **Description:** Bedazzles a target if the bedazzler item can target it.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Target already bedazzled, burning, burnt, or frozen

### `ACTIONS.REPEL.fn(act)`
* **Description:** Repels targets using the repellant component, stopping followers and combat targets.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Item lacks repellant component

### `ACTIONS.ADVANCE_TREE_GROWTH.fn(act)`
* **Description:** Advances tree growth using a tree growth solution item.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Target blocked or item lacks solution component

### `ACTIONS.DISMANTLE_POCKETWATCH.fn(act)`
* **Description:** Dismantles a pocket watch using the dismantler item if allowed.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` with reason
* **Error states:** Cannot dismantle due to cooldown or missing clockmaker tag

### `ACTIONS.STOP_LIFT_DUMBBELL.fn(act)`
* **Description:** Pushes `stopliftingdumbbell` event on the doer.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.LIFT_DUMBBELL.fn(act)`
* **Description:** Starts lifting a dumbbell if lifter allows and item isn't mimic.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Item is mimic or lifter doesn't allow lift

### `ACTIONS.ENTER_GYM.fn(act)`
* **Description:** Enters a mighty gym if workout is allowed for the player.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Missing gym component or `CanWorkout` fails

### `ACTIONS.LIFT_GYM_FAIL.pre_action_cb(act)`
* **Description:** Plays fail bell sound and pushes `lift_gym` event if not dedicated server.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.LIFT_GYM_FAIL.fn(act)`
* **Description:** Stub returning true for failed gym lift.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.LIFT_GYM_SUCCEED_PERFECT.pre_action_cb(act)`
* **Description:** Plays perfect bell sound if doer has bell component.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.LIFT_GYM_SUCCEED_PERFECT.fn(act)`
* **Description:** Stub returning true for perfect gym lift.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.LIFT_GYM_SUCCEED.pre_action_cb(act)`
* **Description:** Plays succeed bell sound if doer has bell component.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.LIFT_GYM_SUCCEED.fn(act)`
* **Description:** Stub returning true for successful gym lift.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.LEAVE_GYM.fn(act)`
* **Description:** Exits current gym using strongman/gym component.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `nil`
* **Error states:** Gym missing from strongman component

### `ACTIONS.UNLOAD_GYM.fn(act)`
* **Description:** Unloads weight from the gym using `UnloadWeight`.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** Target missing or `UnloadWeight` fails

### `ACTIONS.APPLYMODULE.fn(act)`
* **Description:** Applies an upgrade module to the player if upgrade conditions are met.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Missing module or owner components or `CanUpgrade` fails

### `ACTIONS.APPLYMODULE_FAIL.fn(act)`
* **Description:** Speaks fail message for apply module failure and returns true.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.APPLYMODULE_FAIL.stroverridefn(act)`
* **Description:** Returns generic `APPLYMODULE` string.
* **Parameters:** `act` -- action object
* **Returns:** string
* **Error states:** None

### `ACTIONS.REMOVEMODULES.fn(act)`
* **Description:** Removes one upgrade module from player, deducting energy cost.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Missing remover/owner components or no modules available

### `ACTIONS.REMOVEMODULES_FAIL.fn(act)`
* **Description:** Speaks fail message for remove modules failure and returns true.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.REMOVEMODULES_FAIL.stroverridefn(act)`
* **Description:** Returns generic `REMOVEMODULES` string.
* **Parameters:** `act` -- action object
* **Returns:** string
* **Error states:** None

### `ACTIONS.CHARGE_FROM.strfn(act)`
* **Description:** Returns string key indicating whether charging from item or self.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** None

### `ACTIONS.CHARGE_FROM.fn(act)`
* **Description:** Charges a battery user from a battery source.
* **Parameters:** `act` -- action object
* **Returns:** result of `ChargeFrom (bool, reason)`
* **Error states:** Target lacks battery or no valid user

### `ACTIONS.ROTATE_FENCE.fn(act)`
* **Description:** Rotates a fence using fencerotator component.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Item is mimic or lacks fencerotator component

### `ACTIONS.USEMAGICTOOL.fn(act)`
* **Description:** Captures a tool with magician component, making it transient and attached.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Lacks magician component or item is mimic

### `ACTIONS.STOPUSINGMAGICTOOL.fn(act)`
* **Description:** Stops using the current magic tool, returning or dropping it.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** Lacks magician component

### `ACTIONS.USESPELLBOOK.strfn(act)`
* **Description:** Returns string key based on player tag or item type for spellbook use.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** None

### `ACTIONS.USESPELLBOOK.pre_action_cb(act)`
* **Description:** Pre-action hook to close HUD, validate spellbook, and open spell wheel if valid.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** HUD blocking or spellbook not usable by doer

### `ACTIONS.USESPELLBOOK.fn(act)`
* **Description:** Handles inventory cleanup and confirms spellbook use based on state.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` depending on fuel/depleted state
* **Error states:** Inventory cleanup fails or item fuel depleted

### `ACTIONS.CLOSESPELLBOOK.strfn(act)`
* **Description:** Returns string key for closing spellbook UI based on player/item tags.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** None

### `ACTIONS.CLOSESPELLBOOK.pre_action_cb(act)`
* **Description:** Closes the spell wheel HUD if currently open.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.CLOSESPELLBOOK.fn(act)`
* **Description:** Stub function always returning true for closing spellbook.
* **Parameters:** `act` -- action object
* **Returns:** `true`
* **Error states:** None

### `ACTIONS.CAST_SPELLBOOK.fn(act)`
* **Description:** Casts a spell from a spellbook item or self-cast on player.
* **Parameters:** `act` -- action object
* **Returns:** result of `CastSpell` or `false`
* **Error states:** Spellbook not usable by doer or missing components

### `ACTIONS.SITON.fn(act)`
* **Description:** Completes sitting on a sittable entity if ready and unoccupied.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `nil`
* **Error states:** Not in sitting state, sittable occupied, or missing components

### `ACTIONS.USE_WEREFORM_SKILL.fn(act)`
* **Description:** Calls `UseWereFormSkill` method on the doer if present.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false`
* **Error states:** Missing method or logic fails

### `ACTIONS.REMOTE_TELEPORT.stroverridefn(act)`
* **Description:** Returns formatted string for remote teleport with item name.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** Item missing or no display name

### `ACTIONS.REMOTE_TELEPORT.fn(act)`
* **Description:** Activates remote teleporter item, checking `canactivate` and performing teleport.
* **Parameters:** `act` -- action object
* **Returns:** `true/false` with reason
* **Error states:** Item is mimic, cannot activate, or teleport fails

### `ACTIONS.INCINERATE.fn(act)`
* **Description:** Incinerates the target item if incinerator component exists.
* **Parameters:** `act` -- action object
* **Returns:** result of `Incinerate` or `false`
* **Error states:** Target lacks incinerator component

### `ACTIONS.BOTTLE.fn(act)`
* **Description:** Bottles a target using bottler component from an item.
* **Parameters:** `act` -- action object
* **Returns:** result of `Bottle (bool)`
* **Error states:** Bottler missing or bottle conditions not met

### `ACTIONS.CARVEPUMPKIN.fn(act)`
* **Description:** Begins carving a pumpkin or pumpkin hat if visible and held correctly.
* **Parameters:** `act` -- action object
* **Returns:** `true` or `false` with reason
* **Error states:** Darkness, mimic, invalid holder, or carve conditions fail

### `ACTIONS.DECORATESNOWMAN.strfn(act)`
* **Description:** Returns string key for snowman decoration UI based on held item and lifting state.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** None

### `ACTIONS.DECORATESNOWMAN.fn(act)`
* **Description:** Handles equipping hats or stacking snowballs onto a snowman; silently fails in darkness.
* **Parameters:** `act` -- action object
* **Returns:** `boolean, string (success/failure and reason)`
* **Error states:** Returns `false` if target lacks `snowmandecoratable` component, invalid input item, or dark.

### `ACTIONS.START_PUSHING.strfn(act)`
* **Description:** Provides the display string for the start pushing action based on target tags.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** Returns `nil` if target is invalid or lacks `pushing_roll` tag.

### `ACTIONS.START_PUSHING.fn(act)`
* **Description:** Initiates pushing on a valid pushable target.
* **Parameters:** `act` -- action object
* **Returns:** `boolean` or `nil`
* **Error states:** Returns `nil` if target is invalid or already pushing.

### `ACTIONS.APPLYELIXIR.stroverridefn(act)`
* **Description:** Returns the localized string for applying elixir, adjusting for drink vs apply context.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** Returns `nil` if no valid invobject or target.

### `ACTIONS.APPLYELIXIR.fn(act)`
* **Description:** Applies a ghost elixir to the target (or find an elixirable item if target is not elixir_drinker).
* **Parameters:** `act` -- action object
* **Returns:** `boolean, string (success/failure and reason)`
* **Error states:** Returns failure for too-super elixir, no elixirable item found.

### `ACTIONS.GRAVEDIG.fn(act)`
* **Description:** Triggers grave digging via gravedigger tool and gravediggable component.
* **Parameters:** `act` -- action object
* **Returns:** `boolean, string (success/failure and reason)`
* **Error states:** Returns false and reason if missing components or `DigUp` fails.

### `ACTIONS.MUTATE.stroverridefn(act)`
* **Description:** Returns the localized string for ghost gestalt mutation.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** Returns `nil` if target or `ghostgestalter` is missing.

### `ACTIONS.MUTATE.fn(act)`
* **Description:** Triggers mutation via `ghostgestalter` component.
* **Parameters:** `act` -- action object
* **Returns:** `boolean, string (success/failure and reason)`
* **Error states:** Returns `false` if `ghostgestalter` or `DoMutate` fails.

### `ACTIONS.WOBY_PICKUP.fn(act)`
* **Description:** Handles pickup of items via Woby's container, respecting restrictions and burning state.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false for heavy lifting, burning items, restricted items, or contested containers.

### `ACTIONS.WOBY_PICK.validfn(act)`
* **Description:** Validates if Woby can pick the target item.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false if target is not pickable or already picked.

### `ACTIONS.WOBY_PICK.fn(act)`
* **Description:** Harvests a single unit from a pickable item and launches loot.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false if target or loot spawn fails.

### `ACTIONS.CONTAINER_INSTALL_ITEM.strfn(act)`
* **Description:** Returns `UNINSTALL` string when item is currently installed.
* **Parameters:** `act` -- action object
* **Returns:** string or `nil`
* **Error states:** Returns `nil` if no valid container or not installed.

### `ACTIONS.CONTAINER_INSTALL_ITEM.pre_action_cb(act)`
* **Description:** Plays negative click sound if container is full or slots mismatch before installing.
* **Parameters:** `act` -- action object
* **Returns:** `nil`
* **Error states:** None

### `ACTIONS.CONTAINER_INSTALL_ITEM.fn(act)`
* **Description:** Installs or uninstalls an item into a container, handling specific slots or general capacity.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false if no valid container or install condition not met.

### `ACTIONS.MODSLINGSHOT.fn(act)`
* **Description:** Starts modding a slingshot (equipped or in inventory) using the item with slingshotmodder.
* **Parameters:** `act` -- action object
* **Returns:** `boolean, string`
* **Error states:** Returns false or `NOSLINGSHOT` if no valid slingshot found.

### `ACTIONS.STOPMODSLINGSHOT.fn(act)`
* **Description:** Stops modding by closing the slingshot mods container.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false if no valid container or `install_target`.

### `ACTIONS.DASH.fn(act)`
* **Description:** Executes dash action by forcing entity to face the action point.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false if no action point.

### `ACTIONS.WHISTLE.fn(act)`
* **Description:** Calls recall for Woby if `woby_commands_classified` is present.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false if Woby not found or commands missing.

### `ACTIONS.DRAW_FROM_DECK.fn(act)`
* **Description:** Draws top card from deck, spawns card, and gives to inventory.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false if deck missing or inventory give fails.

### `ACTIONS.FLIP_DECK.fn(act)`
* **Description:** Flips a deck or playing card and plays a UI sound.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false if invobject missing or not a deck/card.

### `ACTIONS.ADD_CARD_TO_DECK.fn(act)`
* **Description:** Adds a card or deck to another deck or playing card, merging as needed.
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false if any component missing or deck creation fails.

### `ACTIONS.POUNCECAPTURE.fn(act)`
* **Description:** Captures a target using a gestalt cage item.
* **Parameters:** `act` -- action object
* **Returns:** `boolean, string (success/failure and reason)`
* **Error states:** Returns false or `ITEMMIMIC` if cage or target invalid, or item mimic present.

### `ACTIONS.DIVEGRAB.fn(act)`
* **Description:** Catches a target using a moonstorm static catcher item.
* **Parameters:** `act` -- action object
* **Returns:** `boolean, string (success/failure and reason)`
* **Error states:** Returns false or `ITEMMIMIC` if catcher or target invalid, or item mimic present.

### `ACTIONS.STARTELECTRICLINK.fn(act)`
* **Description:** Starts or ends linking on an electric connector (toggle based on current linking state).
* **Parameters:** `act` -- action object
* **Returns:** `boolean`
* **Error states:** Returns false if target or `electricconnector` missing.

### `ACTIONS.ENDELECTRICLINK.fn(act)`
* **Description:** Ends electric linking by disconnecting all links.
* **Parameters:** `act` -- action object