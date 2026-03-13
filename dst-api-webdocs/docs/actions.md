---
id: actions
title: Actions
description: This core component defines and manages all interactive gameplay actions (e.g., attack, cook, build, cast, plant), their properties, execution logic, and integration with components like workable, inventory, and tools.
tags: ["CLASSIFIED", "ITEMMIMIC", "_upgradeuser", "abigail_flower", "ancient_text", "balloonomancer", "batteryuser", "boat_leak", "boatbuilder", "bundle", "burnt", "can_use_heavy", "canbeslaughtered", "cannotheal", "canpeek", "catchable", "coach_whistle", "coaching", "combatmount", "constructionsite", "controlled_burner", "cookable", "critterlab", "crushitemcast", "decoratable", "deployable", "deployedfarmplant", "deploykititem", "dogrider", "dogrider_only", "dressable", "drop_inventory_onmurder", "drop_inventory_onpickup", "eyeturret", "farm_debris", "farm_plant", "fencebuilder", "fertilizer", "fertilizerresearchable", "fire", "flying", "fogrevealer", "fooddrink", "fresh", "frozen", "fueldepleted", "furnituredecortaker", "gatebuilder", "gemsocket", "ghostlyelixir", "ghostlyelixirable", "globalmapicon", "globalmapicon_player", "graveplanter", "groundtile", "hammer", "handyperson", "hasemergencymode", "haunted", "heavy", "hitcher", "inventoryitemholder_give", "inventoryitemholder_take", "jostlepick", "jostlerummage", "jostlesearch", "kitcoonden", "largecreature", "lighter", "mapspotrevealer", "master_crewman", "masterchef", "mastercookware", "merm", "mermonly", "mightiness_normal", "mine", "moontrader", "near_kitcoonden", "offerconstructionsite", "pet_treat", "pickable_harvest_str", "pickable_rummage_str", "pickable_search_str", "pickapart", "playbill_lecturn", "player", "playerfloater", "playerghost", "pocketwatchcaster", "portableitem", "projectile", "propweapon", "pump", "pyromaniac", "quagmire_altar", "quagmire_salted", "quagmire_stewer", "race_on", "rebuildconstructionsite", "recipescanner", "repairconstructionsite", "scrapbook_data", "scrapbook_note", "sewingmachine", "singingshell", "smashable", "smolder", "soil", "soul", "souljar", "soulstealer", "special_action_toss", "spider", "spoiled", "stale", "stokeablefire", "switchtoho", "tappable", "teleporter", "tentacle_pillar", "trader_just_show", "trader_repair", "trap", "trophycanbetaken", "trophyscale_bug", "trophyscale_fish", "trophyscale_meat", "unwrappable", "usedeploystring", "virtualocean", "wallbuilder", "watersource", "weighable_bug", "weighable_fish", "weighable_meat", "whackable", "winter_treestand", "wintersfeasttable", "wolfgang_coach", "wormhole"]
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

The `actions` module is the central system responsible for defining, validating, and executing all interactive gameplay actions in Don't Starve Together. It establishes the framework for player, NPC, and entity interactions—ranging from basic movement and item handling to complex mechanics like cooking, construction, spellcasting, andmodular upgrades—by associating each action with configurable properties and execution functions. Actions are tied to components such as `workable`, `inventory`, `combat`, `fueled`, and `deployable`, and are triggered through the game's input and UI system via action cards and targeted interactions.

Each action is implemented as a structured `Action` object containing properties (e.g., range, priority, exclusivity for ghosts) and a function that performs the action logic. The system includes robust helper functions for range checking, distance adjustments (e.g., for ocean tiles, physics padding), and action-specific overrides (e.g., fishing reel strings, theme music). Additionally, the module handles remapping actions for map view (e.g., soulhop, toss), provides support for item mimicry checks, platform hopping restrictions, and integrates deeply with the client-server architecture through replicated components (e.g., `replica`) and stategraph triggers. Event-driven interactions are key: actions push custom events (`onacted`, `haunt`, `brushed`, `on_petted`, etc.) for UI updates, achievements, and AI state transitions.

The `ACTIONS` table serves as the global registry for all built-in actions, with each entry representing a specific gameplay verb and its associated behavior, string hints, and constraints. Action handlers are designed with modularity in mind, delegating core logic to dedicated components, ensuring consistency, and enabling deep customization via callbacks and component extensions.

## Usage example

```lua
-- Define a custom action that plants a seed on soil
local function PlantSeedOnSoil(act)
    local target = act.target
    local doer = act.doer

    if target and target:HasTag("soil") then
        local seed = act.invobject
        if seed and seed.components.plantable and seed.components.plantable.plant then
            -- Remove seed from inventory
            doer.components.inventory:RemoveItem(seed)
            -- Spawn plant
            local plant = SpawnPrefab(seed.components.plantable.plant)
            plant.Transform:SetPosition(target:GetPosition():Get())
            target:Remove()
            return true
        end
    end
    return false, "INVALID"
end

-- Register action
ACTIONS.PLANTSOIL = Action {
    fn = PlantSeedOnSoil,
    distance = 4,
    ghost_valid = false,
    rmb = true,
}

-- Use it in an action call
local act = BufferedAction(doer, target, Vector3(x, y, z), ACTIONS.PLANTSOIL, invobject)
```

## Dependencies & tags

**Components**
- `components/activatable`: `CanActivate`, `DoActivate`
- `components/anchor`: `AddAnchorRaiser`, `StartLoweringAnchor`
- `components/aoespell`: `CanCast`, `CastSpell`
- `components/appraisable`: `Appraise`, `CanAppraise`
- `components/attunable`: `LinkToPlayer`
- `components/attuner`: referenced via attuner
- `components/bait`: used in bait theft
- `components/balloonmaker`: `MakeBalloon`
- `components/bathbomb`: `BATHBOMB`
- `components/bathbombable`: `BATHBOMB`
- `components/bathingpool`: `EnterPool`
- `components/battery`: existence check
- `components/batteryuser`: `ChargeFrom`
- `components/beard`: `Shave`
- `components/bedazzler`: `Bedazzle`, `CanBedazzle`
- `components/blinkstaff`: `Blink`
- `components/boatcannon`: `IsAmmoLoaded`, `LoadAmmo`
- `components/boatcannonuser`: `SetCannon`
- `components/boatleak`: `GetRemainingRepairedTime`, `Repair`
- `components/boatmagnet`: `UnpairWithBeacon`
- `components/boatmagnetbeacon`: `TurnOffBeacon`, `TurnOnBeacon`
- `components/boatrotator`: `SetRotationDirection`
- `components/book`: read via `reader`, `simplebook`
- `components/bottler`: `Bottle`
- `components/brushable`: `Brush`
- `components/builder`: `DoBuild`, `UsePrototyper`
- `components/bundler`: `CanStartBundling`, `FinishBundling`, `IsBundling`, `StartBundling`
- `components/burnable`: `Extinguish`, `IsBurning`, `IsSmoldering`, `SmotherSmolder`, `StokeControlledBurn`
- `components/carnivalgamefeedable`: `DoFeed`
- `components/cattoy`: `Play`
- `components/channelable`: `StartChanneling`, `StopChanneling`
- `components/channelcastable`: `IsAnyUserChanneling`, `IsUserChanneling`, `StopChanneling`
- `components/channelcaster`: `StartChanneling`
- `components/childspawner`: `GoHome`
- `components/clientpickupsoundsuppressor`: `IgnoreNextPickupSound`
- `components/closeinspector`: `CloseInspectPoint`, `CloseInspectTarget`
- `components/combat`: `CanBeAttacked`, `DoAttack`, `GetWeapon`, `HasTarget`, `TryRetarget`
- `components/complexprojectile`: `Launch`
- `components/compostingbin`: `AddCompostable`
- `components/constructionbuilder`: `CanStartConstruction`, `FinishConstruction`, `IsConstructing`, `IsConstructingAny`, `StartConstruction`, `StopConstruction`
- `components/constructionbuilderuidata`: `GetContainer`, `GetSlotForIngredient`, `GetTarget`
- `components/constructionplans`: `StartConstruction`
- `components/constructionsite`: referenced via builder
- `components/container`: `CanAcceptCount`, `CanOpen`, `CanTakeItemInSlot`, `Close`, `DropEverything`, `DropItem`, `DropItemAt`, `GetItemInSlot`, `GiveItem`, `IsOpen`, `Open`, `RemoveItem`
- `components/container_proxy`: `CanBeOpened`, `Close`, `GetMaster`, `IsOpenedBy`, `Open`
- `components/containerinstallableitem`: `GetValidOpenContainer`
- `components/cookable`: cookable check
- `components/cooker`: `CanCook`, `CookItem`
- `components/craftingstation`: `KnowsItem`
- `components/crewmember`: `Row`
- `components/crittertraits`: `OnPet`
- `components/crop`: `Fertilize`, `Harvest`, `IsReadyForHarvest`
- `components/curseditem`: `checkplayersinventoryforspace`
- `components/cyclable`: `Cycle`
- `components/deckcontainer`: `AddCard`, `MergeDecks`, `RemoveCard`
- `components/deployable`: `CanDeploy`, `Deploy`
- `components/drawable`: `CanDraw`
- `components/drawingtool`: `Draw`, `GetImageToDraw`
- `components/dryer`: `CanDry`, `DropItem`, `Harvest`, `StartDrying`
- `components/dryingrack`: `Harvest`
- `components/dumbbelllifter`: `CanLift`, `StartLifting`
- `components/eater`: `CanEat`, `Eat`, `PrefersToEat`
- `components/edible`: foodtype
- `components/electricconnector`: `Disconnect`, `EndLinking`, `IsLinking`, `StartLinking`
- `components/embarker`: used for map/platform utilities
- `components/entitytracker`: `GetEntity`
- `components/equippable`: `IsEquipped`, `IsRestricted`, `ShouldPreventUnequipping`
- `components/expertsailor`: `GetLowerSailStrength`
- `components/fan`: `Fan`
- `components/farmplantable`: `Plant`
- `components/farmplantstress`: `GetStressDescription`, `SetStressed`
- `components/farmplanttendable`: `SetTendable`, `TendTo`
- `components/farmtiller`: `Till`
- `components/fencerotator`: `Rotate`
- `components/fertilizable`: `Fertilize`
- `components/fertilizer`: `Heal`, `OnApplied`
- `components/fertilizerresearchable`: `LearnFertilizer`
- `components/fillable`: `Fill`
- `components/finiteuses`: `GetUses`
- `components/fishingnet`: `CastNet`
- `components/fishingrod`: fishing rod actions
- `components/follower`: `GetLeader`, `IsLeaderSame`, `StopFollowing`
- `components/followerherder`: `CanHerd`, `Herd`
- `components/forgerepair`: forge repair
- `components/forgerepairable`: `Repair`
- `components/freezable`: `IsFrozen`
- `components/fueled`: `ChangeSection`, `IsEmpty`, `TakeFuelItem`
- `components/fueler`: fuel handling
- `components/furnituredecortaker`: `AbleToAcceptDecor`, `AcceptDecor`
- `components/gestaltcage`: `Capture`
- `components/ghostgestalter`: `DoMutate`
- `components/ghostlybond`: `ChangeBehaviour`, `Recall`, `Summon`
- `components/ghostlyelixir`: `Apply`
- `components/ghostlyelixirable`: `GetApplyToTarget`
- `components/grabbable`: `CanGrab`
- `components/gravediggable`: `DigUp`
- `components/gravedigger`: `OnUsed`
- `components/groomer`: grooming
- `components/grower`: `Fertilize`, `IsEmpty`, `PlantItem`
- `components/guardian`: `Call`
- `components/halloweenpotionmoon`: `Use`
- `components/harvestable`: `Harvest`
- `components/hauntable`: `DoHaunt`
- `components/healer`: `Heal`
- `components/health`: `DoDelta`, `IsDead`
- `components/heavyobstacleusetarget`: `UseHeavyObstacle`
- `components/hideandseekhidingspot`: `SearchHidingSpot`
- `components/hideout`: `GoHome`
- `components/hitchable`: `GetHitch`
- `components/hitcher`: `SetHitched`, `Unhitch`
- `components/incinerator`: `Incinerate`
- `components/inspectable`: `GetDescription`
- `components/instrument`: `Play`
- `components/inventory`: `CanAcceptCount`, `CloseAllChestContainers`, `DropItem`, `Equip`, `FindItem`, `ForEachItem`, `GetActiveItem`, `GetEquippedItem`, `GiveActiveItem`, `GiveItem`, `IsFloaterHeld`, `IsHeavyLifting`, `IsOpenedBy`, `RemoveItem`, `TransferInventory`, `Unequip`
- `components/inventoryitem`: `DoDropPhysics`, `GetGrandOwner`, `HibernateLivingItem`, `IsHeld`, `IsHeldBy`, `RemoveFromOwner`
- `components/inventoryitemholder`: `GiveItem`, `TakeItem`
- `components/itemmimic`: mimic checks
- `components/itemtyperestrictions`: `IsAllowed`
- `components/itemweigher`: `DoWeighIn`
- `components/kitcoon`: `OnPet` event
- `components/kitcoonden`: `AddKitcoon`
- `components/klaussacklock`: `UseKey`
- `components/knownlocations`: `GetLocation`, `RememberLocation`
- `components/lighter`: `Light`
- `components/lock`: `IsLocked`, `Lock`, `Unlock`
- `components/locomotor`: `Stop`
- `components/lootdropper`: `FlingItem`, `GenerateLoot`
- `components/lunarhailbuildup`: `RemoveBuildup`
- `components/machine`: `IsOn`, `TurnOff`, `TurnOn`
- `components/magician`: `StartUsingTool`, `StopUsing`
- `components/maprecorder`: `TeachMap`
- `components/mapspotrevealer`: `RevealMap`
- `components/markable`: `HasMarked`, `Mark`
- `components/markable_proxy`: `Mark`
- `components/mast`: `AddSailFurler`, `UnfurlSail`
- `components/maxhealer`: `Heal`
- `components/maxwelltalker`: `DoTalk`, `IsTalking`
- `components/mightygym`: `CharacterExitGym`, `CharacterEnterGym`, `UnloadWeight`, `CanWorkout`
- `components/mine`: `Reset`
- `components/moonstormstaticcatcher`: `Catch`
- `components/moontrader`: `AcceptOffering`
- `components/multithruster`: multithruster
- `components/murderable`: murdersound
- `components/nabbag`: `DoNabFromAct`, `ReplicateNetFromAct`
- `components/npc_talker`: `Chatter`, `Say`
- `components/oar`: `Row`, `RowFail`
- `components/occupiable`: `CanOccupy`, `Harvest`, `IsOccupied`, `Occupy`
- `components/occupier`: occupier state
- `components/oceanfishable`: `GetRod`, `SetRod`
- `components/oceanfishingrod`: `Cast`, `CatchFish`, `Reel`, `StopFishing`
- `components/oceanthrowable`: `AddProjectile`
- `components/oceantrawler`: `Fix`, `Lower`, `Raise`
- `components/papereraser`: `DoErase`
- `components/perishable`: `GetPercent`, `SetPercent`
- `components/petleash`: `AttachPet`, `DespawnPet`, `DetachPet`, `IsFull`
- `components/pickable`: `CanBeFertilized`, `CanBePicked`, `IsStuck`, `Pick`, `Regen`
- `components/pinnable`: `IsStuck`
- `components/plantresearchable`: `IsRandomSeed`, `LearnPlant`
- `components/playbill`: playbill
- `components/playbill_lecturn`: `SwapPlayBill`
- `components/playercontroller`: `IsEnabled`, `directwalking`
- `components/playingcard`: `GetID`, `SetID`
- `components/playingcardsmanager`: `MakePlayingCard`
- `components/pocketwatch`: `CastSpell`
- `components/pocketwatch_dismantler`: `CanDismantle`, `Dismantle`
- `components/pollinator`: `CreateFlower`, `Pollinate`
- `components/poppable`: `Pop`
- `components/portablestructure`: `Dismantle`
- `components/preservative`: `percent_increase`, `divide_effect_by_stack_size`
- `components/projectile`: `IsThrown`
- `components/pumpkincarvable`: `CanBeginCarving`, `BeginCarving`
- `components/pumpkinhatcarvable`: `CanBeginCarving`, `BeginCarving`
- `components/pushable`: `IsPushing`, `StartPushing`
- `components/quagmire_altar`: `AcceptFoodTribute`
- `components/quagmire_cookwaretrader`: `AcceptCookware`
- `components/quagmire_fertilizable`: `Fertilize`
- `components/quagmire_installable`: `installprefab`
- `components/quagmire_installations`: `Install`, `IsEnabled`
- `components/quagmire_plantable`: `Plant`
- `components/quagmire_replatable`: `Replate`
- `components/quagmire_replater`: replater
- `components/quagmire_saltable`: `Salt`
- `components/quagmire_saltextractor`: `DoInstall`
- `components/quagmire_saltpond`: saltpond
- `components/quagmire_slaughtertool`: `Slaughter`
- `components/quagmire_stewer`: `IsCooking`, `CanCook`, `StartCooking`
- `components/quagmire_tappable`: `Harvest`, `InstallTap`, `IsTapped`, `UninstallTap`
- `components/quagmire_tapper`: tapper
- `components/quagmire_tiller`: `Till`
- `components/questowner`: `AbandonQuest`, `BeginQuest`, `CanAbandonQuest`, `CanBeginQuest`
- `components/reader`: `Read`
- `components/recipescanner`: `Scan`
- `components/remoteteleporter`: `CanActivate`, `Teleport`
- `components/repairable`: `Repair`
- `components/repairer`: healthrepairvalue
- `components/repellent`: `Repel`
- `components/revivablecorpse`: `CanBeRevivedBy`, `Revive`
- `components/rideable`: `GetRider`, `IsBeingRidden`, `SetSaddle`
- `components/rider`: `Dismount`, `GetMount`, `IsRiding`, `Mount`
- `components/sanity`: `DoDelta`
- `components/scrapbookable`: `Teach`
- `components/searchable`: `Search`
- `components/sewing`: `DoSewing`
- `components/shaveable`: `Shave`
- `components/shaver`: shaver
- `components/shelf`: `TakeItem`
- `components/simplebook`: `Read`
- `components/singable`: `Sing`
- `components/singinginspiration`: `IsSongActive`, `CanAddSong`
- `components/sittable`: `IsOccupied`, `SetOccupier`
- `components/skilltreeupdater`: `IsActivated`
- `components/sleepingbag`: `DoSleep`, `InUse`
- `components/slingshotmodder`: `StartModding`, `StopModding`
- `components/slingshotmods`: `CanBeOpenedBy`
- `components/snowmandecoratable`: `BeginDecorating`, `CanBeginDecorating`, `CanStack`, `EquipHat`, `GetSize`, `Stack`
- `components/soul`: soul entity
- `components/souleater`: `EatSoul`
- `components/spawner`: `GoHome`
- `components/spellbook`: `CanBeUsedBy`, `CastSpell`, `GetSpellName`, `OpenSpellBook`, `ShouldOpen`
- `components/spellcaster`: `CanCast`, `CastSpell`
- `components/spidermutator`: `CanMutate`, `Mutate`
- `components/spooked`: `Spook`
- `components/stackable`: `Get`, `IsFull`, `IsOverStacked`, `IsStack`, `Put`, `SetStackSize`, `StackSize`
- `components/stageactingprop`: `DoPerformance`
- `components/stageactor`: stageactor
- `components/steeringwheel`: sailor
- `components/steeringwheeluser`: `SetSteeringWheel`, `Steer`
- `components/stewer`: `CanCook`, `Harvest`, `IsCooking`, `IsDone`, `StartCooking`
- `components/storyteller`: `TellStory`
- `components/strongman`: gym
- `components/summoningitem`: summoning context
- `components/tackler`: `StartTackle`
- `components/tacklesketch`: `Teach`
- `components/talker`: `Chatter`, `Say`
- `components/teacher`: `Teach`
- `components/teleporter`: `IsActive`
- `components/terraformer`: `Terraform`
- `components/thief`: `StealItem`
- `components/toggleableitem`: `CanInteract`, `ToggleItem`
- `components/tool`: `GetEffectiveness`
- `components/trader`: `AbleToAccept`, `AcceptGift`, `IsAcceptingStacks`
- `components/trap`: `Harvest`, `SetBait`
- `components/treegrowthsolution`: `GrowTarget`
- `components/trophyscale`: `Compare`, `TakeItem`
- `components/unwrappable`: `PeekInContainer`, `Unwrap`
- `components/upgradeable`: `CanUpgrade`, `Upgrade`
- `components/upgrademodule`: module
- `components/upgrademoduleowner`: `AddCharge`, `CanUpgrade`, `NumModules`, `PopOneModule`, `PushModule`
- `components/upgrademoduleremover`: remover
- `components/upgrader`: `CanUpgrade`
- `components/useableitem`: `CanInteract`, `StartUsingItem`
- `components/useabletargeteditem`: `CanInteract`, `StartUsingItem`, `StopUsingItem`
- `components/vase`: `Decorate`
- `components/walkingplank`: `AbandonShip`, `DismountPlank`, `Extend`, `MountPlank`, `Retract`
- `components/wardrobe`: wardrobe
- `components/wateryprotection`: `SpreadProtection`, `SpreadProtectionAtPoint`
- `components/waxable`: `Wax`
- `components/weighable`: weight
- `components/winch`: unloadfn
- `components/workable`: `CanBeWorked`, `GetWorkAction`, `ShouldRecoil`, `WorkedBy`, `WorkedBy_Internal`, `onwork`
- `components/worker`: `GetEffectiveness`
- `components/workmultiplier`: `GetMultiplier`, `ResolveSpecialWorkAmount`
- `components/worldmigrator`: `Activate`
- `components/writeable`: `BeginWriting`, `IsBeingWritten`, `IsWritten`
- `components/yotb_sewer`: `CanSew`, `IsSewing`, `StartSewing`
- `components/yotb_skinunlocker`: `GetSkin`
- `components/yotb_stagemanager`: isContestActive
- `components/yotb_stager`: `StartContest`
- `components/yotc_racecompetitor`: ownership check
- `components/yotc_raceprizemanager`: `GetRaceById`
- `components/yotc_racestart`: `CanInteract`, `StartRace`

**Tags**
- `CLASSIFIED`: action-only, hidden from UI
- `ITEMMIMIC`: blocks certain actions to prevent mimic exploits
- `_upgradeuser`: upgrade user tag
- `abigail_flower`, `ancient_text`, `balloonomancer`, `batteryuser`, `boat_leak`, `boatbuilder`, `bundle`, `burnt`, `can_use_heavy`, `canbeslaughtered`, `cannotheal`, `canpeek`, `catchable`, `coach_whistle`, `coaching`, `combatmount`, `constructionsite`, `controlled_burner`, `cookable`, `critterlab`, `crushitemcast`, `decoratable`, `deployable`, `deployedfarmplant`, `deploykititem`, `dogrider`, `dogrider_only`, `dressable`, `drop_inventory_onmurder`, `drop_inventory_onpickup`, `eyeturret`, `farm_debris`, `farm_plant`, `fencebuilder`, `fertilizer`, `fertilizerresearchable`, `fire`, `flying`, `fogrevealer`, `fooddrink`, `fresh`, `frozen`, `fueldepleted`, `furnituredecortaker`, `gatebuilder`, `gemsocket`, `ghostlyelixir`, `ghostlyelixirable`, `globalmapicon`, `globalmapicon_player`, `graveplanter`, `groundtile`, `hammer`, `handyperson`, `hasemergencymode`, `haunted`, `heavy`, `hitcher`, `inventoryitemholder_give`, `inventoryitemholder_take`, `jostlepick`, `jostlerummage`, `jostlesearch`, `kitcoonden`, `largecreature`, `lighter`, `mapspotrevealer`, `master_crewman`, `masterchef`, `mastercookware`, `merm`, `mermonly`, `mightiness_normal`, `mine`, `moontrader`, `near_kitcoonden`, `offerconstructionsite`, `pet_treat`, `pickable_harvest_str`, `pickable_rummage_str`, `pickable_search_str`, `pickapart`, `playbill_lecturn`, `player`, `playerfloater`, `playerghost`, `pocketwatchcaster`, `portableitem`, `projectile`, `propweapon`, `pump`, `pyromaniac`, `quagmire_altar`, `quagmire_salted`, `quagmire_stewer`, `race_on`, `rebuildconstructionsite`, `recipescanner`, `repairconstructionsite`, `scrapbook_data`, `scrapbook_note`, `sewingmachine`, `singingshell`, `smashable`, `smolder`, `soil`, `soul`, `souljar`, `soulstealer`, `special_action_toss`, `spider`, `spoiled`, `stale`, `stokeablefire`, `switchtoho`, `tappable`, `teleporter`, `tentacle_pillar`, `trader_just_show`, `trader_repair`, `trap`, `trophycanbetaken`, `trophyscale_bug`, `trophyscale_fish`, `trophyscale_meat`, `unwrappable`, `usedeploystring`, `virtualocean`, `wallbuilder`, `watersource`, `weighable_bug`, `weighable_fish`, `weighable_meat`, `whackable`, `winter_treestand`, `wintersfeasttable`, `wolfgang_coach`, `wormhole`

## Properties

| Name | Type | Default | Description |
|------|------|---------|-------------|
| `priority` | `number` | `0` | Action priority for ordering; higher values override lower priority actions. |
| `fn` | `function` | `function() return false end` | Function called to execute the action; defaults to returning false. |
| `strfn` | `nil` | `nil` | Optional string-generating function for UI hints. |
| `instant` | `boolean` | `false` | If true, action executes immediately without locomotion delay. |
| `rmb` | `nil` | `nil` | If true, action requires right mouse button; only effective for tools. |
| `distance` | `nil` | `nil` | Maximum range (world units) to perform action; nil means unlimited. |
| `mindistance` | `nil` | `nil` | Minimum required range; action fails if too close. |
| `arrivedist` | `nil` | `nil` | Acceptable distance tolerance at arrival for completing action. |
| `ghost_exclusive` | `boolean` | `false` | If true, action is valid only for ghost characters. |
| `ghost_valid` | `boolean` | `false` | If true, action is valid for ghost characters (but not exclusive). |
| `mount_valid` | `boolean` | `false` | If true, action can be performed while mounted. |
| `encumbered_valid` | `boolean` | `false` | If true, action can be performed while encumbered. |
| `floating_valid` | `boolean` | `false` | If true, action can be performed while floating. |
| `canforce` | `nil` | `nil` | If present, action can be forced even under some constraints. |
| `rangecheckfn` | `nil` | `nil` | Custom function to validate distance between doer and target. |
| `mod_name` | `nil` | `nil` | Name of the mod defining this action. |
| `silent_fail` | `nil` | `nil` | If true, action failure produces no UI feedback. |
| `silent_generic_fail` | `nil` | `nil` | If true, generic failure conditions produce no UI feedback. |
| `paused_valid` | `boolean` | `false` | If true, action can be performed while game is paused. |
| `actionmeter` | `nil` | `nil` | If present, action requires or uses an action meter. |
| `customarrivecheck` | `nil` | `nil` | Custom function to validate arrival at destination. |
| `is_relative_to_platform` | `nil` | `nil` | If true, action distance is relative to platform boundaries. |
| `disable_platform_hopping` | `nil` | `nil` | If true, prevents automatic platform switching for this action. |
| `skip_locomotor_facing` | `nil` | `nil` | If true, skips locomotor facing adjustments before action. |
| `do_not_locomote` | `nil` | `nil` | If true, skips full locomotion pathfinding for this action. |
| `extra_arrive_dist` | `nil` | `nil` | Additional distance buffer added to arrival tolerance. |
| `tile_placer` | `nil` | `nil` | Name of tile placement system if action places tiles (e.g., gridplacer). |
| `show_tile_placer_fn` | `nil` | `nil` | Function used to determine visibility of tile placement preview. |
| `theme_music` | `nil` | `nil` | Theme music identifier to play during action. |
| `theme_music_fn` | `nil` | `nil` | Client-side function returning theme music identifier. |
| `pre_action_cb` | `nil` | `nil` | Callback function executed before the action runs (client and server). |
| `invalid_hold_action` | `nil` | `nil` | If true, action invalidates held items (e.g., stops using tools). |
| `show_primary_input_left` | `nil` | `nil` | If true, shows left-click input hint. |
| `show_secondary_input_right` | `nil` | `nil` | If true, shows right-click input hint. |
| `map_action` | `boolean` | `false` | If true, action can be performed from the map view. |
| `closes_map` | `boolean` | `false` | If true, immediately closes the minimap upon action start. |
| `map_only` | `boolean` | `false` | If true, action only exists and is valid from map view. |
| `map_works_on_unexplored` | `boolean` | `false` | If true, bypasses seeable/reveal checks for map actions. |

## Main functions

### MakeRangeCheckFn

Returns a function that checks if the doer is within a given range of the target using `IsNear`.

**Parameters**

- `range` — Number. Maximum allowed distance.

**Returns**

- `function(doer, target): boolean or nil` — Returns true if within range, nil if target is nil.

**Error states**

- None.

### PickRangeCheck

Checks if the doer is within range to interact with the target, including weapon attack range and physics radius padding.

**Parameters**

- `doer`, `target` — Entities.

**Returns**

- `boolean or nil` — True if valid, nil if target is nil.

**Error states**

- Returns nil if target is nil.

### ExtraPickRange

Returns extra range (0.75 on ocean tiles) plus weapon attack range for jostle actions.

**Parameters**

- `doer`, `dest`, `bufferedaction` — Entity, position, and buffered action.

**Returns**

- `number` — Extra range value.

**Error states**

- Returns 0 if dest or bufferedaction.target is nil or conditions not met.

### PhysicsPaddedRangeCheck

Legacy range check using physics radius + 4, currently unused.

**Parameters**

- `doer`, `target` — Entities.

**Returns**

- `boolean or nil` — Legacy range check result, nil if target is nil.

**Error states**

- Returns nil if target is nil.

### CheckFishingOceanRange

Checks if a fishing cast reaches valid ocean tile (not void or land), including virtual ocean detection.

**Parameters**

- `doer`, `dest` — Entity and action point.

**Returns**

- `boolean` — True if cast is valid on ocean.

**Error states**

- None.

### CheckRowRange

Checks if rowing action destination is not on a platform (i.e., valid water).

**Parameters**

- `doer`, `dest` — Entity and target position.

**Returns**

- `boolean` — True if valid rowing position.

**Error states**

- None.

### CheckIsOnPlatform

Checks if the doer is currently on a platform.

**Parameters**

- `doer`, `dest` — Entity and target position.

**Returns**

- `boolean` — True if on a platform.

**Error states**

- None.

### CheckOceanFishingCastRange

Checks if an ocean fishing cast is valid at target position, allowing for ocean/tile transitions.

**Parameters**

- `doer`, `dest` — Entity and action point.

**Returns**

- `boolean` — True if cast position is valid.

**Error states**

- None.

### CheckTileWithinRange

Checks if the target tile is within one tile of the doer.

**Parameters**

- `doer`, `dest` — Entity and action point.

**Returns**

- `boolean or nil` — True if within range.

**Error states**

- None.

### ShowPourWaterTilePlacer

Determines if the pour water tile placer preview should show, only if target is valid farm soil.

**Parameters**

- `right_mouse_action` — Boolean.

**Returns**

- `boolean` — True if preview should be shown.

**Error states**

- Returns false if no valid farm_plant target or soil is not farmable.

### ExtraPickupRange

Returns extra range (0.75) if destination is on water and impassable.

**Parameters**

- `doer`, `dest` — Entity and target position.

**Returns**

- `number` — Extra range value.

**Error states**

- Returns 0 if dest is nil or target is not on ocean tile.

### ExtraDeployDist

Returns additional deployment distance based on target terrain (land/void/ocean) and item tags.

**Parameters**

- `doer`, `dest`, `bufferedaction` — Entity, position, and buffered action.

**Returns**

- `number` — Extra distance value.

**Error states**

- Returns 0 if no special terrain case applies.

### ExtraDropDist

Returns extra drop distance (1.75 on water) or physics radius + 0.5 if item collides with doer.

**Parameters**

- `doer`, `dest`, `bufferedaction` — Entity, position, and buffered action.

**Returns**

- `number` — Extra distance value.

**Error states**

- Returns 0 if no conditions matched.

### ExtraPourWaterDist

Fixed extra distance (1.5) for pour water action.

**Parameters**

- `doer`, `dest`, `bufferedaction` — Entity, position, and buffered action.

**Returns**

- `number` — Extra distance.

**Error states**

- None.

### ExtraHealRange

Adjusts healing range to account for physics radius overrides (e.g., Brightshades).

**Parameters**

- `doer`, `dest`, `bufferedaction` — Entity, position, and buffered action.

**Returns**

- `number` — Extra range.

**Error states**

- Returns 0 if no offset or target is nil.

### ArriveAnywhere

Always-valid arrival check for actions like blink and toss map.

**Parameters**

- None.

**Returns**

- `true`.

**Error states**

- None.

### ExtraWobyForagingDist

Returns extra foraging distance (0.5 or 1.5 for large creatures).

**Parameters**

- `doer`, `dest`, `bufferedaction` — Entity, position, and buffered action.

**Returns**

- `number` — Extra distance.

**Error states**

- None.

### SetClientRequestedAction

Sets global `CLIENT_REQUESTED_ACTION` from mod or base action mappings.

**Parameters**

- `actioncode`, `mod_name` — Action code string and optional mod name.

**Returns**

- `nil`.

**Error states**

- Sets to nil if action not found.

### ClearClientRequestedAction

Resets global `CLIENT_REQUESTED_ACTION` to nil.

**Parameters**

- None.

**Returns**

- `nil`.

**Error states**

- None.

### Action

Constructor for Action objects; supports positional (deprecated) and table args.

**Parameters**

- `data` — Table of action properties.
- `instant`, `rmb`, `distance`, `ghost_valid`, `ghost_exclusive`, `canforce`, `rangecheckfn` — Optional overrides (positional args deprecated).

**Returns**

- `Action` instance.

**Error states**

- Prints warning and converts positional arguments if used incorrectly.

### IsItemInReadOnlyContainer

Checks if an item is inside a read-only container.

**Parameters**

- `item` — Item entity.

**Returns**

- `true` if item is in a read-only container, `false` otherwise.

**Error states**

- None.

### ShouldLOOKATStopLocomotor

Determines if the action should stop the locomotor before looking at something.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if locomotor should be stopped, `false` otherwise.

**Error states**

- None.

### row

Helper function to execute rowing actions for either crewmembers or oars.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if rowing succeeded, `false` otherwise.

**Error states**

- None.

### DoToolWork

Performs work on a target using tool/worker components, applying multipliers, recoil, and special work amounts; handles item mimic checks and recoil events.

**Parameters**

- `act`, `workaction` — Action table and work type.

**Returns**

- `true` if work succeeded, `false + reason` if failed.

**Error states**

- Fails if target missing workable component, not workable, wrong action, restricted tool, or item mimic present.

### ValidToolWork

Checks if a target can be worked on using the given workaction (workable, valid action, not restricted tool).

**Parameters**

- `act`, `workaction` — Action table and work type.

**Returns**

- `boolean` indicating validity.

**Error states**

- None.

### ShouldBlockGiving

Determines if giving an item should be blocked based on inventoryitem replica constraints (pocket-only rules).

**Parameters**

- `act` — Action table.

**Returns**

- `true` if giving should be blocked, `false` otherwise.

**Error states**

- None.

### ACTIONS.ATTACKPLANT.fn

Sets plant stress and tendability when a plant is attacked.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Fails silently if target or components missing.

### ACTIONS.TELLSTORY.stroverridefn

Overrides the string for tell story actions to avoid showing target name.

**Parameters**

- `act` — Action table.

**Returns**

- `STRINGS.ACTIONS.TELLSTORY`.

**Error states**

- None.

### ACTIONS.TELLSTORY.fn

Calls storyteller component to tell a story using a target or inventory object.

**Parameters**

- `act` — Action table.

**Returns**

- Result of `TellStory` or nil.

**Error states**

- Returns nil if storyteller component missing.

### ACTIONS.PERFORM.fn

Initiates a performance if actor and prop are valid.

**Parameters**

- `act` — Action table.

**Returns**

- Result of `DoPerformance` or nil.

**Error states**

- Fails silently if actor or prop components missing.

### ACTIONS.BAIT.fn

Sets bait on a trap using the inventory object, removing it from inventory.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Fails silently if target trap missing.

### ACTIONS.DEPLOY.fn

Deploys an item (e.g., builds wall, fence, portable item, or throws projectile) using deployable, complexprojectile, or deployable components.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false + reason` on failure.

**Error states**

- Returns reason if can't deploy; returns false if deploy fails and item can't be restored.

### ACTIONS.DEPLOY.strfn

Selects appropriate deployment string based on item tags (e.g., wallbuilder, projectile, fertilizer).

**Parameters**

- `act` — Action table.

**Returns**

- Deployment string key or nil.

**Error states**

- Returns nil if item nil or no matching tag.

### ACTIONS.DEPLOY.theme_music_fn

Returns 'farming' theme music if deploying a farm plant.

**Parameters**

- `act` — Action table.

**Returns**

- `'farming'` or nil.

**Error states**

- None.

### ACTIONS.SUMMONGUARDIAN.fn

Calls a guardian to summon help if guardable target exists.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- Fails silently if guardian component missing.

### ACTIONS.CHECKTRAP.fn

Harvests a trap if it contains bait and has triggered.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Fails silently if trap component missing.

### ACTIONS.CHOP.fn

Performs chopping work and triggers spooking if applicable.

**Parameters**

- `act` — Action table.

**Returns**

- `true`, or `false + reason` if tool work failed.

**Error states**

- Returns false if `DoToolWork` fails.

### ACTIONS.CHOP.validfn

Checks if the target is valid for chopping.

**Parameters**

- `act` — Action table.

**Returns**

- `boolean`.

**Error states**

- None.

### ACTIONS.MINE.fn

Performs mining work.

**Parameters**

- `act` — Action table.

**Returns**

- `true`, or `false + reason` if tool work failed.

**Error states**

- Returns false if `DoToolWork` fails.

### ACTIONS.MINE.validfn

Checks if the target is valid for mining.

**Parameters**

- `act` — Action table.

**Returns**

- `boolean`.

**Error states**

- None.

### ACTIONS.HAMMER.fn

Performs hammering work.

**Parameters**

- `act` — Action table.

**Returns**

- `true`, or `false + reason` if tool work failed.

**Error states**

- Returns false if `DoToolWork` fails.

### ACTIONS.HAMMER.validfn

Checks if the target is valid for hammering.

**Parameters**

- `act` — Action table.

**Returns**

- `boolean`.

**Error states**

- None.

### ACTIONS.DIG.fn

Performs digging work.

**Parameters**

- `act` — Action table.

**Returns**

- `true`, or `false + reason` if tool work failed.

**Error states**

- Returns false if `DoToolWork` fails.

### ACTIONS.DIG.validfn

Checks if the target is valid for digging.

**Parameters**

- `act` — Action table.

**Returns**

- `boolean`.

**Error states**

- None.

### ACTIONS.DIG.theme_music_fn

Returns 'farming' theme if target is farm debris or farm plant.

**Parameters**

- `act` — Action table.

**Returns**

- `'farming'` or nil.

**Error states**

- None.

### ACTIONS.FERTILIZE.fn

Applies fertilizer to crops, growers, pickables, or the player if no target, using respective component handlers.

**Parameters**

- `act` — Action table.

**Returns**

- `applied` boolean, or nil if no fertilizer or no applicable component.

**Error states**

- None.

### ACTIONS.SMOTHER.fn

Smothers smoldering fire on a target using inventory object or doer as smotherer.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Fails silently if target not smoldering.

### ACTIONS.MANUALEXTINGUISH.fn

Extinguishes burning target using frozen inventory object.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Fails silently if target not burning or item not frozen.

### ACTIONS.NET.fn

Works on a nettable target using workable component; replicates net action if item has nabbag component.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.CATCH.fn

Placeholder action for catching; currently returns true.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.FISH_OCEAN.fn

Blocks ocean fishing with 'TOODEEP' error.

**Parameters**

- `act` — Action table.

**Returns**

- `false, 'TOODEEP'`.

**Error states**

- None.

### ACTIONS.FISH.fn

Starts fishing with a fishing rod at a target.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Fails silently if no fishing rod component.

### ACTIONS.REEL.fn

Reels in fishing line based on hook, bite, or stop state.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Fails silently if no fishing rod or not fishing.

### ACTIONS.REEL.strfn

Returns appropriate reel string (REEL, HOOK, CANCEL) based on fishing state.

**Parameters**

- `act` — Action table.

**Returns**

- `string` key or nil.

**Error states**

- Returns nil if mismatched target or no fishing rod.

### ACTIONS.PICK.strfn

Returns appropriate pick string (HARVEST, RUMMAGE, SEARCH) based on target tags.

**Parameters**

- `act` — Action table.

**Returns**

- `string` key or nil.

**Error states**

- Returns nil if target nil or no matching tag.

### ACTIONS.PICK.fn

Picks a pickable or searches a searchable target.

**Parameters**

- `act` — Action table.

**Returns**

- `true`, or `false + reason` (e.g., STUCK) or searchable result.

**Error states**

- Returns STUCK if target stuck; delegates searchable result.

### ACTIONS.PICK.validfn

Checks if target is pickable or searchable.

**Parameters**

- `act` — Action table.

**Returns**

- `boolean`.

**Error states**

- None.

### ACTIONS.PICK.theme_music_fn

Returns 'farming' theme if target is farm plant.

**Parameters**

- `act` — Action table.

**Returns**

- `'farming'` or nil.

**Error states**

- None.

### ACTIONS.ATTACK.fn

Performs attack using combat component, handling prop attacks, thrusting, and helm splitting special cases.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.ATTACK.strfn

Returns appropriate attack string (PROP, RANGEDSMOTHER, RANGEDLIGHT, WHACK, SMASHABLE) based on weapon and target tags.

**Parameters**

- `act` — Action table.

**Returns**

- `string` key or nil.

**Error states**

- Returns nil if target nil or no matching condition.

### ACTIONS.COOK.stroverridefn

Overrides COOK string to SPICE if target is spicer.

**Parameters**

- `act` — Action table.

**Returns**

- `STRINGS.ACTIONS.SPICE` or nil.

**Error states**

- None.

### ACTIONS.COOK.fn

Cooks ingredients using cooker or stewer component; kills living items and handles inventory movement.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` on failure.

**Error states**

- Returns reason strings like INUSE, TOOFAR, or false if cannot cook.

### ACTIONS.ACTIVATE_CONTAINER.fn

Calls container's cookbuttonfn if defined and not in use.

**Parameters**

- `act` — Action table.

**Returns**

- `true`, or `false + reason` (INUSE).

**Error states**

- Returns INUSE if container opened by others.

### ACTIONS.FILL.fn

Fills a fillable object from a water source or ocean at action point.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false + reason` on failure.

**Error states**

- Returns oceanwatererrorreason if ocean fill failed; returns false if no source/filled object.

### ACTIONS.DRY.fn

Starts drying an inventory object in a dryer if possible.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- Returns false if dryer cannot dry or dry fails.

### ACTIONS.ADDFUEL.fn

Adds fuel to a fueled component using inventory item or fueler component.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- None.

### ACTIONS.GIVE.strfn

Returns GIVE string key (SOCKET, SHOW, REPAIR, CELESTIAL) based on target tags.

**Parameters**

- `act` — Action table.

**Returns**

- `string` key or nil.

**Error states**

- Returns nil if target nil or no matching tag.

### ACTIONS.GIVE.stroverridefn

Returns overridden GIVE string for special cases (ghostly elixir, quagmire altar, winters feast, etc.).

**Parameters**

- `act` — Action table.

**Returns**

- `formatted` string or nil.

**Error states**

- None.

### ACTIONS.GIVE.fn

Handles giving items to various targets: playbill_lecturn, ghostlyelixirable, trader, moontrader, furnituredecor, inventoryitemholder, cookware trader, quagmire altar.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false + reason` if blocked or not accepted.

**Error states**

- Returns false if blocked by pocket rules; returns reason if trader cannot accept.

### ACTIONS.GIVETOPLAYER.fn

Gives one item to a player trader that is opened by itself or a ghost.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false + reason` (FULL or trader reason).

**Error states**

- Returns FULL if inventory full; returns trader reason if cannot accept.

### ACTIONS.GIVEALLTOPLAYER.fn

Gives as many items as possible to a player trader.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false + reason` (FULL or trader reason).

**Error states**

- Returns FULL if can't accept any; returns trader reason if cannot accept.

### ACTIONS.FEEDPLAYER.fn

Feeds a player if idle, not busy/sleeping/ghost/wereplayer, and the food is edible and acceptable.

**Parameters**

- `act` — Action table.

**Returns**

- `true`, or `false + reason` if blocked.

**Error states**

- Returns true even if player refuses food (wonteatfood event); returns false if cannot feed.

### ACTIONS.DECORATEVASE.fn

Decorates a vase with a flower if enabled.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Returns nil silently if vase disabled or missing.

### ACTIONS.CARNIVALGAME_FEED.fn

Feeds a carnival game if enabled and valid.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of DoFeed or false + TOO_LATE.

**Error states**

- Returns TOO_LATE if game disabled; returns nil if invalid inputs.

### ACTIONS.STORE.fn

Handles storing an item into a container, including proxy master resolution, restriction checks, and construction builder integration.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` (success), optional reason string on failure.

**Error states**

- Container closed/INUSE, restricted, not masterchef for mastercookware, invalid slot for construction, bundle busy state.

### ACTIONS.BUNDLESTORE.strfn

Returns 'CONSTRUCT' if the target is the current container or target in the construction builder UI.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.STORE.strfn

Returns appropriate string action verb based on target type (stewer, birdcage, decoratable).

**Parameters**

- `act` — Action table.

**Returns**

- `string` (COOK/SPICE/DECORATE/IMPRISON) or nil.

**Error states**

- None.

### ACTIONS.BUILD.fn

Calls builder:DoBuild with recipe, position, rotation, and skin.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` (success) from builder component.

**Error states**

- Builder component missing.

### ACTIONS.PLANT.strfn

Returns 'PLANTER' if target is a winter_treestand.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.PLANT.fn

Removes seed from inventory and plants it in the grower target or handles winter treestand planting event.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` (success) or nil if seed not planted.

**Error states**

- No grower, no winter_treestand, or seed not removed.

### ACTIONS.HARVEST.fn

Attempts harvesting from crop, harvestable, stewer, dryer, dryingrack, occupiable, or quagmire_tappable components.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` (success) from underlying component or nil.

**Error states**

- Target lacks harvestable component or invalid state.

### ACTIONS.HARVEST.strfn

Returns 'FREE' for birdcage or 'WITHERED' for withered crops.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.LIGHT.fn

Uses lighter component on target, pushes 'onstartedfire' event.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No lighter component on invobject.

### ACTIONS.SLEEPIN.fn

Uses sleepingbag component to make the doer sleep.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No valid sleepingbag item or target.

### ACTIONS.HITCHUP.fn

Attempts to hitch a beefalo to the target; checks beefalo presence, mood, and proximity.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` (success) or reason string.

**Error states**

- No beefalo, too far, or in mood.

### ACTIONS.UNHITCH.fn

Calls unhitch on target hitcher if present and not tagged as hitcher.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No hitcher component.

### ACTIONS.HITCH.fn

Sets the doer as hitched to the target if target has hitcher tag.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- Target missing hitcher component.

### ACTIONS.MARK.strfn

Returns 'UNMARK' if target has markable and is already marked.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.MARK.fn

Calls markable or markable_proxy to mark/unmark target.

**Parameters**

- `act` — Action table.

**Returns**

- `true` or `false`, reason string.

**Error states**

- Not participant, already marked.

### ACTIONS.CHANGEIN.strfn

Returns 'DRESSUP' if target has dressable tag.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.CHANGEIN.fn

Calls wardrobe or groomer to begin changing outfit.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` (success) or reason string.

**Error states**

- Component missing or CanBeginChanging fails.

### ACTIONS.SHAVE.strfn

Returns 'SELF' if target is nil/self and controller attached.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.SHAVE.fn

Calls beard or shaveable component to shave target.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` (success), reason string.

**Error states**

- No valid implement or beard/shaveable component.

### ACTIONS.PLAY.strfn

Returns appropriate string for coach whistle actions based on tags.

**Parameters**

- `act` — Action table.

**Returns**

- `string` (TWEET/COACH_ON/COACH_OFF) or nil.

**Error states**

- None.

### ACTIONS.PLAY.fn

Calls instrument component to play the item.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No instrument component.

### ACTIONS.POLLINATE.fn

Calls pollinator component to pollinate target or create flower.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of pollinator:Pollinate or :CreateFlower.

**Error states**

- No pollinator component.

### ACTIONS.TERRAFORM.fn

Calls terraformer component to terraform at action point.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` (success).

**Error states**

- No terraformer component.

### ACTIONS.EXTINGUISH.fn

Extinguishes burning or smoldering burnable or consumes a fuel section for fueled.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No burnable or fueled component, or not burning.

### ACTIONS.STOKEFIRE.fn

Stokes a controlled burn if doer has controlled_burner tag.

**Parameters**

- `act` — Action table.

**Returns**

- `true` or `false`.

**Error states**

- Not a stokeable fire or missing controlled_burner tag.

### ACTIONS.LAYEGG.fn

Calls pickable:Regen() if egg not pickable.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of pickable:Regen().

**Error states**

- No pickable or already pickable.

### ACTIONS.INVESTIGATE.fn

Uses knownlocations to investigate remembered spot and retarget combat.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No investigate location or combat component.

### ACTIONS.COMMENT.fn

Executes pending comment speech via npc_talker or talker components.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- No comment_data or talker components.

### ACTIONS.GOHOME.fn

Calls GoHome on spawner, childspawner, or hideout components, or removes entity.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of GoHome or true (removal).

**Error states**

- No target or valid home component.

### ACTIONS.JUMPIN.strfn

Returns 'HAUNT' if doer is playerghost.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.JUMPIN.fn

Enters jumpin state if teleporter is active.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Not in jumpin_pre state or inactive teleporter.

### ACTIONS.JUMPIN_MAP.stroverridefn

Returns localized string for wormhole map action.

**Parameters**

- `act` — Action table.

**Returns**

- `string`.

**Error states**

- None.

### DoCharlieResidueMapAction

Handles wormhole or tentacle_pillar map actions using charlieresidue context.

**Parameters**

- `act`, `target`, `charlieresidue`, `residue_context` — Action, target, residue entity, and context.

**Returns**

- `bool` (success).

**Error states**

- No valid wormhole/exit found or context invalid.

### ACTIONS.JUMPIN_MAP.fn

Handles map-based teleport via jumpin state and charlieresidue logic.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Invalid teleporter or charlieresidue state.

### ACTIONS.TELEPORT.strfn

Returns 'TOWNPORTAL' if target exists.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.TELEPORT.fn

Enters entertownportal state if teleporter valid.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No valid teleporter or wrong state.

### ACTIONS.RESETMINE.fn

Calls mine:Reset() to un-spring a mine.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No mine component.

### ACTIONS.ACTIVATE.fn

Calls activatable:DoActivate after CanActivate check; skips if burning/smoldering.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with msg.

**Error states**

- Activatable missing, CanActivate fails, or burning.

### ACTIONS.ACTIVATE.strfn

Returns custom verb from GetActivateVerb if present.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.ACTIVATE.stroverridefn

Returns override verb from OverrideActivateVerb if present.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.OPEN_CRAFTING.strfn

Returns action_str from PROTOTYPER_DEFS for known prototyper prefabs.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.OPEN_CRAFTING.fn

Calls builder:UsePrototyper on target.

**Parameters**

- `act` — Action table.

**Returns**

- `bool`.

**Error states**

- No builder component.

### ACTIONS.CAST_POCKETWATCH.strfn

Returns action verb from GetActionVerb_CAST_POCKETWATCH on item.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.CAST_POCKETWATCH.fn

Calls pocketwatch:CastSpell on item for pocketwatchcaster.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` (success), reason string.

**Error states**

- No pocketwatchcaster tag or missing component.

### ACTIONS.HAUNT.fn

Triggers haunt on target if valid and not already haunted.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Invalid target, held, or already haunted.

### ACTIONS.MURDER.fn

Kills victim, plays sound, spawns loot, transfers inventory, removes victim.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No murderable component or invalid victim.

### ACTIONS.HEAL.strfn

Returns 'SELF' or 'USEONSELF' based on controller presence and cannotheal tag.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.HEAL.fn

Uses healer or maxhealer component to heal target.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` (success), reason string.

**Error states**

- Dead, ghost, or missing healer/maxhealer.

### ACTIONS.UNLOCK.fn

Calls lock:Unlock with key item.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No lock component.

### ACTIONS.USEKLAUSSACKKEY.fn

Calls klaussacklock:UseKey to unlock with key item.

**Parameters**

- `act` — Action table.

**Returns**

- `true` or `false`, reason string.

**Error states**

- No component or UseKey fails.

### ACTIONS.TEACH.strfn

Returns verb based on scrapbook_note, scrapbook_data, mapspotrevealer, or recipescanner tags.

**Parameters**

- `act` — Action table.

**Returns**

- `string` (NOTES/SCRAPBOOK/READ/SCAN) or nil.

**Error states**

- None.

### ACTIONS.TEACH.fn

Calls teaching component on item (scrapbookable, teacher, maprecorder, mapspotrevealer, recipescanner).

**Parameters**

- `act` — Action table.

**Returns**

- `bool` with optional reason.

**Error states**

- No applicable teaching component.

### ACTIONS.TURNON.fn

Calls machine:TurnOn on target or invobject.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Not machine or already on.

### ACTIONS.TURNOFF.strfn

Returns 'EMERGENCY' if target has hasemergencymode tag.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.TURNOFF.fn

Calls machine:TurnOff on target or invobject.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- Not machine or already off.

### ACTIONS.USEITEM.fn

Toggles toggleableitem or starts using useableitem if interactable.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of toggle/use use.

**Error states**

- Not interactable or cannotuse tag.

### ACTIONS.USEITEMON.strfn

Returns uppercase item prefab name or 'GENERIC'.

**Parameters**

- `act` — Action table.

**Returns**

- `string`.

**Error states**

- None.

### ACTIONS.USEITEMON.pre_action_cb

Closes controller inventory if open.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- None.

### ACTIONS.USEITEMON.fn

Calls useabletargeteditem:StartUsingItem on item against target.

**Parameters**

- `act` — Action table.

**Returns**

- `bool` with optional reason.

**Error states**

- Not interactable or StartUsingItem fails.

### ACTIONS.STOPUSINGITEM.strfn

Returns uppercase item prefab name or 'GENERIC'.

**Parameters**

- `act` — Action table.

**Returns**

- `string`.

**Error states**

- None.

### ACTIONS.STOPUSINGITEM.fn

Calls useabletargeteditem:StopUsingItem.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- No useabletargeteditem component.

### ACTIONS.TAKEITEM.fn

Attempts to take an item from a shelf or inventory holder.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- None.

### ACTIONS.TAKEITEM.strfn

Returns the action string key for TAKEITEM based on target type.

**Parameters**

- `act` — Action table.

**Returns**

- `string` key.

**Error states**

- None.

### ACTIONS.TAKEITEM.stroverridefn

Returns a custom display string for the item being taken, including stack size.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.TAKESINGLEITEM.fn

Takes a single item from an inventory holder.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- None.

### ACTIONS.TAKESINGLEITEM.stroverridefn

Returns the generic string for TAKE_SINGLE_ITEM action.

**Parameters**

- `act` — Action table.

**Returns**

- `string`.

**Error states**

- None.

### ACTIONS.CASTSPELL.strfn

Returns the spell type of the casting item (if any).

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.CASTSPELL.fn

Casts a spell using a staff (item or equipped), with checks for mimicry, combat mount, heavy lifting, and spellcaster validation.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- ITEMMIMIC, rider with combat mount, heavy lifting with crushitemcast tag.

### ACTIONS.DIRECTCOURIER_MAP.maponly_checkvalidpos_fn

Finds the nearest valid target (chest or player) within courier range for map-based direct courier action.

**Parameters**

- `act` — Action table.

**Returns**

- `true, nil, act_posx, act_posz, mapent` on success; `false, reason` on fail.

**Error states**

- NOTARGET if no valid position found within radius.

### ACTIONS.DIRECTCOURIER_MAP.stroverridefn

Returns the display string for the DIRECTCOURIER_MAP action based on nearest target (chest or named player).

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ACTIONS.DIRECTCOURIER_MAP.fn

Executes the DIRECTCOURIER_MAP action by sending courier instructions if the doer has required tags and permissions.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- Missing playercontroller or woby_commands_classified.

### TryToSoulhop

Helper function to check and trigger a soulhop action (portal jump-in state).

**Parameters**

- `act`, `act_pos`, `consumeall` — Action table, position, and consume flag.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- None.

### ACTIONS.BLINK.strfn

Returns the string key for BLINK action based on soulstealer tag and freesoul counter.

**Parameters**

- `act` — Action table.

**Returns**

- `string` key or nil.

**Error states**

- None.

### ACTIONS.BLINK.fn

Performs blink using blinkstaff or triggers soulhop if character has soulstealer tag.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- ITEMMIMIC.

### ACTIONS.BLINK_MAP.stroverridefn

Returns the display string for map-based soulhop (BLINK_MAP) showing required souls.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- None.

### ActionCanMapSoulhop

Helper function to check if map soulhop is allowed.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if allowed, `false` otherwise.

**Error states**

- None.

### ACTIONS.BLINK_MAP.fn

Executes map-based soulhop (BLINK_MAP) with portal state transition.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- None.

### ACTIONS_MAP_REMAP[ACTIONS.BLINK.code]

Remaps BLINK action on map click to calculate distances, mod effects, and Souls per hop for wortox.

**Parameters**

- `act`, `targetpos` — Action table and target position.

**Returns**

- `remapped` BufferedAction or nil.

**Error states**

- No valid terrain or fogrevealer detected.

### ACTIONS.CASTSUMMON.fn

Summons a ghost using a summoning item.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- Missing components.

### ACTIONS.CASTUNSUMMON.fn

Recalls a summoned ghost.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- Missing components.

### ACTIONS.COMMUNEWITHSUMMONED.strfn

Returns the display string key based on aggressive follower tag.

**Parameters**

- `act` — Action table.

**Returns**

- `string` key.

**Error states**

- None.

### ACTIONS.COMMUNEWITHSUMMONED.fn

Changes ghost behavior using ghostlybond component.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- Missing components.

### ACTIONS.COMBINESTACK.fn

Combines two stacks of same item type and skin if target is not full.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- None.

### ACTIONS.TRAVEL.fn

Executes custom travel action defined on target.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- Missing travel_action_fn.

### ACTIONS.UNPIN.fn

Unpins a target if stuck and not self.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- None.

### ACTIONS.STEALMOLEBAIT.fn

Handles mole stealing bait from a target.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- None.

### ACTIONS.MAKEMOLEHILL.fn

Spawns a molehill or molebathill for mole/molebat characters.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- None.

### ACTIONS.MOLEPEEK.fn

Pushes 'peek' event on the mole character.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- None.

### ACTIONS.FEED.strfn

Returns string key 'TREAT' if item is a pet treat, else nil.

**Parameters**

- `act` — Action table.

**Returns**

- `string` key or nil.

**Error states**

- None.

### ACTIONS.FEED.fn

Feeds an item to a target via trader or eater component; handles death/loot for predators.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- ITEMMIMIC, no target or eater, can't eat food.

### ACTIONS.HAIRBALL.fn

Checks if the doer is catcoon (valid for hairball action).

**Parameters**

- `act` — Action table.

**Returns**

- `true` if catcoon, `false`.

**Error states**

- None.

### ACTIONS.CATPLAYGROUND.fn

Handles catcoon playground interaction (play toy, pop, attack, pick up item, activate).

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.CATPLAYAIR.fn

Handles catcoon airborne play interaction (play toy, pop, attack, activate).

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.ERASE_PAPER.fn

Erases paper using an eraser item on a non-burning target.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- ITEMMIMIC or invalid target.

### ACTIONS.FAN.fn

Uses a fan item on target (doer if none provided).

**Parameters**

- `act` — Action table.

**Returns**

- `true` if onusefn called, `false` with reason.

**Error states**

- ITEMMIMIC.

### ACTIONS.TOSS.fn

Tosses an item as a projectile (uses invobject or equipped item).

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- Missing projectile, restricted item, itemmimic.

### ACTIONS.WATER_TOSS.fn

Alias to TOSS.fn.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of TOSS.fn.

**Error states**

- None.

### ACTIONS.TOSS_MAP.stroverridefn

Returns TOSS string key if CanTossOnMap returns true.

**Parameters**

- `act` — Action table.

**Returns**

- `string` key or nil.

**Error states**

- None.

### ActionCanMapToss

Helper function to check map toss permission.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if allowed, `false`.

**Error states**

- None.

### ACTIONS.TOSS_MAP.fn

Executes TOSS_MAP by delegating to TOSS.fn with from_map flag.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- None.

### ACTIONS_MAP_REMAP[ACTIONS.TOSS.code]

Remaps TOSS action for map usage, clamping distances and verifying ocean tile.

**Parameters**

- `act`, `targetpos` — Action table and target position.

**Returns**

- `remapped` BufferedAction or nil.

**Error states**

- Not ocean tile or CanTossOnMap fails.

### ACTIONS.UPGRADE.fn

Upgrades a target using an upgrader item after validation.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- Upgrade limit reached, invalid upgrader or target.

### ACTIONS.UPGRADE.strfn

Returns 'WATERPLANT' if target is waterplant-upgradable.

**Parameters**

- `act` — Action table.

**Returns**

- `string` key or nil.

**Error states**

- None.

### ACTIONS.NUZZLE.fn

Performs nuzzle action (always succeeds if target exists).

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.WRITE.fn

Begins writing on a target if not written, not in use, and visible.

**Parameters**

- `act` — Action table.

**Returns**

- `true, false` with reason.

**Error states**

- INUSE, invisible, or not writeable.

### ACTIONS.ATTUNE.fn

Attunes a target item to the player using attunable component.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- Missing attunable component.

### ACTIONS.MIGRATE.fn

Migrates player or item via worldmigrator component.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- Missing components or destination.

### ACTIONS.REMOTERESURRECT.fn

Attempts remote resurrection via attuner and ghost tag.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- Missing attuner, not ghost, no attuned target.

### ACTIONS.REVIVE_CORPSE.fn

Revives a corpse if reviver is allowed.

**Parameters**

- `act` — Action table.

**Returns**

- `true` (always).

**Error states**

- None (silent fail if not allowed).

### ACTIONS.MOUNT.fn

Attempts to mount a rideable target after many validation checks.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- TARGETINCOMBAT, not rideable, dead, frozen, hitched, locked, dogrider_only mismatch.

### ACTIONS.DISMOUNT.fn

Dismounts if rider is riding.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- None.

### ACTIONS.SADDLE.fn

Saddles a rideable target using an item.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- TARGETINCOMBAT, dead, itemmimic, not rideable.

### ACTIONS.UNSADDLE.fn

Unsaddles a rideable target.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- TARGETINCOMBAT, dead, itemmimic, not rideable.

### ACTIONS.BRUSH.fn

Brushes a target (e.g., beefalo) with brush item.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- TARGETINCOMBAT, dead, itemmimic, not brushable.

### ACTIONS.ABANDON.fn

Abandons a pet (despawn pet or stop following).

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false`.

**Error states**

- None.

### ACTIONS.PET.fn

Handles petting logic by invoking crittertraits:OnPet if the target has the component, and pushing 'on_petted' event if the target has kitcoon component.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `nil` if conditions not met.

**Error states**

- None.

### ACTIONS.RETURN_FOLLOWER.fn

Attempts to return a follower to its kitcoon den if the follower belongs to the doer and the doer is near a kitcoon den.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if successfully returned, `false` otherwise.

**Error states**

- Returns false if no kitcoon den is found within distance.

### ACTIONS.HIDEANSEEK_FIND.fn

Performs search on a hiding spot via hideandseekhidingspot:SearchHidingSpot when target matches.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `nil` if no matching target.

**Error states**

- None.

### ACTIONS.DRAW.stroverridefn

Overrides the action string for DRAW actions by resolving the item to draw.

**Parameters**

- `act` — Action table.

**Returns**

- Formatted string showing the item name or nil.

**Error states**

- None.

### ACTIONS.DRAW.fn

Executes drawing on a target by retrieving image data from drawingtool and invoking draw function on the target.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` if image cannot be retrieved.

**Error states**

- NOIMAGE error if GetImageToDraw returns nil.

### ACTIONS.STARTCHANNELING.strfn

Returns action string override based on whether the target has the 'pump' tag.

**Parameters**

- `act` — Action table.

**Returns**

- `PUMP` if target has 'pump', otherwise nil.

**Error states**

- None.

### ACTIONS.STARTCHANNELING.fn

Initiates channeling on the target via channelable:StartChanneling if target is valid.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of StartChanneling call (true/false).

**Error states**

- None.

### ACTIONS.STOPCHANNELING.fn

Stops channeling on the target via channelable:StopChanneling(true) if target is valid.

**Parameters**

- `act` — Action table.

**Returns**

- `true` unconditionally.

**Error states**

- None.

### ACTIONS.START_CHANNELCAST.strfn

Returns LIGHTER if the inventory object has the lighter tag.

**Parameters**

- `act` — Action table.

**Returns**

- `LIGHTER` or nil.

**Error states**

- None.

### ACTIONS.START_CHANNELCAST.fn

Starts channel casting either with off-hand (nil invobject) or equipped item (invobject with channelcastable), with itemmimic check.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise, `ITEMMIMIC` error if mimic present.

**Error states**

- `ITEMMIMIC` error if the item is an item mimic.

### ACTIONS.STOP_CHANNELCAST.strfn

Same as START_CHANNELCAST.strfn.

**Parameters**

- `act` — Action table.

**Returns**

- `LIGHTER` or nil.

**Error states**

- None.

### ACTIONS.STOP_CHANNELCAST.fn

Stops channel casting on the invobject if user is channeling it, with itemmimic check.

**Parameters**

- `act` — Action table.

**Returns**

- `true` unconditionally, `ITEMMIMIC` error if mimic present.

**Error states**

- `ITEMMIMIC` error if the item is an item mimic.

### ACTIONS.BUNDLE.fn

Starts bundling process on target or invobject using bundler component if conditions are met and entity can see.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of StartBundling or true if silent failure (darkness).

**Error states**

- None.

### ACTIONS.WRAPBUNDLE.fn

Finishes bundling if target is being bundled and container is not empty; otherwise says fail string.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of FinishBundling or true after logging error.

**Error states**

- EMPTY fail if bundle is empty.

### ACTIONS.UNWRAP.fn

Calls unwrappable:Unwrap on target if target is valid and unwrapable.

**Parameters**

- `act` — Action table.

**Returns**

- `true` unconditionally.

**Error states**

- None.

### ACTIONS.PEEKBUNDLE.fn

Peeks inside container (if canpeek and not smoldering/fire) by calling unwrapable:PeekInContainer.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of PeekInContainer.

**Error states**

- None.

### ACTIONS.BREAK.strfn

Returns PICKAPART if target or invobject has 'pickapart' tag.

**Parameters**

- `act` — Action table.

**Returns**

- `PICKAPART` or nil.

**Error states**

- None.

### ACTIONS.CONSTRUCT.stroverridefn

Overrides construction action string using constructionname from target or invobject.

**Parameters**

- `act` — Action table.

**Returns**

- Formatted name string or nil.

**Error states**

- None.

### ACTIONS.CONSTRUCT.strfn

Returns construction type string: OFFER, STORE, OFFER_TO, REPAIR, or REBUILD based on target tags.

**Parameters**

- `act` — Action table.

**Returns**

- Construction type string or nil.

**Error states**

- None.

### ACTIONS.CONSTRUCT.fn

Starts construction on target using constructionbuilder component; handles construction plans and item storage inside.

**Parameters**

- `act` — Action table.

**Returns**

- `true` or `false` with reason.

**Error states**

- Silent fail if in darkness, INUSE/BURNT for invalid states.

### ACTIONS.STOPCONSTRUCTION.stroverridefn

Overrides stop construction string using constructionname of target.

**Parameters**

- `act` — Action table.

**Returns**

- Formatted stop name or nil.

**Error states**

- None.

### ACTIONS.STOPCONSTRUCTION.strfn

Returns stop construction type string: OFFER, REPAIR, REBUILD based on target tags.

**Parameters**

- `act` — Action table.

**Returns**

- Stop type string or nil.

**Error states**

- None.

### ACTIONS.STOPCONSTRUCTION.fn

Stops ongoing construction using constructionbuilder:StopConstruction.

**Parameters**

- `act` — Action table.

**Returns**

- `true` unconditionally.

**Error states**

- None.

### ACTIONS.APPLYCONSTRUCTION.strfn

Same as CONSTRUCT.strfn for apply construction.

**Parameters**

- `act` — Action table.

**Returns**

- `OFFER, REPAIR, REBUILD` or nil.

**Error states**

- None.

### ACTIONS.APPLYCONSTRUCTION.fn

Finishes construction if target container is not empty or notifies user.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of FinishConstruction or true after logging error.

**Error states**

- EMPTY fail if container empty.

### ACTIONS.CASTAOE.stroverridefn

Returns spell name from spellbook component if present.

**Parameters**

- `act` — Action table.

**Returns**

- Spell name or nil.

**Error states**

- None.

### ACTIONS.CASTAOE.strfn

Returns uppercase prefab name of invobject.

**Parameters**

- `act` — Action table.

**Returns**

- `prefab` string or nil.

**Error states**

- None.

### ACTIONS.CASTAOE.fn

Casts AOE spell from invobject if valid, using aoespell:CastSpell after CanCast check.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of CastSpell or false with reason.

**Error states**

- ITEMMIMIC error if item is mimic.

### ACTIONS.SCYTHE.fn

Calls DoScythe on invobject if it has the method, with itemmimic check.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if scythe succeeded, `false` otherwise.

**Error states**

- ITEMMIMIC error if item is mimic.

### ACTIONS.NABBAG.fn

Calls DoNabFromAct on invobject if valid, with itemmimic check.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of DoNabFromAct or false.

**Error states**

- ITEMMIMIC error if item is mimic.

### ACTIONS.DISMANTLE.fn

Dismantles portable structure if it exists, is not burning (unless campfire), and container checks pass.

**Parameters**

- `act` — Action table.

**Returns**

- `true` after dismantle, `false` with reason (INUSE, NOTEMPTY, COOKING, etc.).

**Error states**

- INUSE/NOTEMPTY/COOKING for container conditions.

### ACTIONS.TACKLE.fn

Starts tackle using tackler component if available.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of StartTackle or nil.

**Error states**

- None.

### ACTIONS.HALLOWEENMOONMUTATE.fn

Mutates target using halloweenpotionmoon component if target is valid and not burning/smoldering/frozen.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- Target invalid, burning, smoldering, or frozen returns false.

### ACTIONS.APPLYPRESERVATIVE.strfn

Returns SALT if invobject is saltrock.

**Parameters**

- `act` — Action table.

**Returns**

- `SALT` or nil.

**Error states**

- None.

### ACTIONS.APPLYPRESERVATIVE.fn

Increases perish percentage of target based on preservative effect and stack size.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- None.

### COMPARE_WEIGHABLE_TEST

Helper function to test if target and weighable share a trophy scale type tag.

**Parameters**

- `target`, `weighable` — Entities.

**Returns**

- `true` if tags match, `false` otherwise.

**Error states**

- None.

### ACTIONS.COMPARE_WEIGHABLE.fn

Compares item weight against trophy scale using trophyyscale:Compare.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of Compare or false.

**Error states**

- None.

### ACTIONS.WEIGH_ITEM.fn

Weighs an item using itemweigher component via DoWeighIn.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of DoWeighIn or false.

**Error states**

- None.

### ACTIONS.START_CARRAT_RACE.fn

Starts carrat race if target and race conditions are valid.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `NO_RACERS` error if no racers.

**Error states**

- `NO_RACERS` error if race has zero racers.

### ACTIONS.TILL.fn

Tills ground using farmtiller or quagmire_tiller components.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of Till call or false.

**Error states**

- `ITEMMIMIC` error if item is mimic.

### ACTIONS.PLANTSOIL.fn

Plants seed on soil using farmplantable or quagmire_plantable components.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if planted, `false` otherwise.

**Error states**

- None.

### ACTIONS.INSTALL.fn

Installs quagmire installable or salt extractor part into target.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- None.

### ACTIONS.TAPTREE.fn

Taps or untaps a tree using quagmire_tappable and quagmire_tapper components.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- None.

### ACTIONS.TAPTREE.strfn

Returns UNTAP if target lacks 'tappable' tag.

**Parameters**

- `act` — Action table.

**Returns**

- `UNTAP` or nil.

**Error states**

- None.

### ACTIONS.SLAUGHTER.stroverridefn

Returns custom slaughter action string if GetSlaughterActionString exists.

**Parameters**

- `act` — Action table.

**Returns**

- String or nil.

**Error states**

- None.

### ACTIONS.SLAUGHTER.fn

Slaughters target if valid, using quagmire_slaughtertool component.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if successfully slaughtered, `false` with reason.

**Error states**

- `TOOFAR` if target is too far.

### ACTIONS.REPLATE.stroveroverridefn

Overrides replation action string using dish name for Quagmire replatable items.

**Parameters**

- `act` — Action table.

**Returns**

- Formatted string or nil.

**Error states**

- None.

### ACTIONS.BATHBOMB.fn

Applies bath bomb to bathbombable target.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success.

**Error states**

- None.

### ACTIONS.RAISE_SAIL.fn

Unfurrs sail using mast:UnfurlSail.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if mast exists, nil otherwise.

**Error states**

- None.

### ACTIONS.RAISE_SAIL.stroverridefn

Returns fixed string RAISE_SAIL.

**Parameters**

- `act` — Action table.

**Returns**

- `RAISE_SAIL`.

**Error states**

- None.

### ACTIONS.LOWER_SAIL.fn

Placeholder for lowering sail.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.LOWER_SAIL.stroverridefn

Returns fixed string LOWER_SAIL.

**Parameters**

- `act` — Action table.

**Returns**

- `LOWER_SAIL`.

**Error states**

- None.

### ACTIONS.LOWER_SAIL_BOOST.fn

Boosts lowering sail strength using expertsailor if present and applies sail furler.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if mast exists and sail is raised.

**Error states**

- None.

### GetLowerSailStr

Returns localized string index for lower sail boost actions.

**Parameters**

- `act` — Action table.

**Returns**

- `String` index 1 or 2 depending on switchtoho tag.

**Error states**

- None.

### ACTIONS.LOWER_SAIL_BOOST.stroverridefn

Overrides string using GetLowerSailStr.

**Parameters**

- `act` — Action table.

**Returns**

- Localized string.

**Error states**

- None.

### ACTIONS.LOWER_SAIL_FAIL.fn

Placeholder failure action.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.LOWER_SAIL_FAIL.stroverridefn

Same as LOWER_SAIL_BOOST.stroverridefn.

**Parameters**

- `act` — Action table.

**Returns**

- Localized string.

**Error states**

- None.

### ACTIONS.RAISE_ANCHOR.fn

Calls anchor:AddAnchorRaiser on target.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of AddAnchorRaiser.

**Error states**

- None.

### ACTIONS.LOWER_ANCHOR.fn

Calls anchor:StartLoweringAnchor on target.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of StartLoweringAnchor.

**Error states**

- None.

### ACTIONS.MOUNT_PLANK.fn

Mounts walking plank using walkingplank:MountPlank.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of MountPlank.

**Error states**

- None.

### ACTIONS.DISMOUNT_PLANK.fn

Dismounts plank using walkingplank:DismountPlank.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.ABANDON_SHIP.fn

Abandons ship using walkingplank:AbandonShip.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of AbandonShip.

**Error states**

- None.

### ACTIONS.EXTEND_PLANK.fn

Extends plank using walkingplank:Extend.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.RETRACT_PLANK.fn

Retracts plank using walkingplank:Retract.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.REPAIR_LEAK.fn

Repairs boat leak using boatleak:Repair.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of Repair.

**Error states**

- None.

### ACTIONS.STEER_BOAT.pre_action_cb

Closes spell wheel before steering.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- None.

### ACTIONS.STEER_BOAT.fn

Sets steering wheel using steeringwheeluser:SetSteeringWheel.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if wheel was set, nil otherwise.

**Error states**

- None.

### ACTIONS.SET_HEADING.fn

Sets heading direction via steeringwheeluser:Steer using action point.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of Steer or false.

**Error states**

- None.

### ACTIONS.STOP_STEERING_BOAT.fn

Stops steering by setting steering wheel to nil.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.CAST_NET.fn

Casts fishing net using fishingnet:CastNet at action point.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- `ITEMMIMIC` error if item is mimic.

### ACTIONS.ROTATE_BOAT_CLOCKWISE.fn

Sets rotation direction to 1 on boatrotator.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.ROTATE_BOAT_COUNTERCLOCKWISE.fn

Sets rotation direction to -1 on boatrotator.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.ROTATE_BOAT_COUNTERCLOCKWISE.stroverridefn

Returns localized ROTATE_BOAT_COUNTERCLOCKWISE string.

**Parameters**

- `act` — Action table.

**Returns**

- `String`.

**Error states**

- None.

### ACTIONS.ROTATE_BOAT_STOP.fn

Sets rotation direction to 0 on boatrotator.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.ROTATE_BOAT_STOP.stroverridefn

Returns localized ROTATE_BOAT_STOP string.

**Parameters**

- `act` — Action table.

**Returns**

- `String`.

**Error states**

- None.

### ACTIONS.BOAT_MAGNET_ACTIVATE.fn

Starts beacon search state on boatmagnet.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.BOAT_MAGNET_DEACTIVATE.fn

Unpairs beacon using boatmagnet:UnpairWithBeacon.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.BOAT_MAGNET_BEACON_TURN_ON.fn

Turns on beacon using boatmagnetbeacon:TurnOnBeacon.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.BOAT_MAGNET_BEACON_TURN_OFF.fn

Turns off beacon using boatmagnetbeacon:TurnOffBeacon.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### IsBoatCannonAmmo

Checks if item is valid boat cannon ammo.

**Parameters**

- `item` — Item entity.

**Returns**

- `true` if projectileprefab exists and has boatcannon_ammo tag.

**Error states**

- None.

### ACTIONS.BOAT_CANNON_LOAD_AMMO.fn

Loads cannon ammo from inventory or findItem, using boatcannon:LoadAmmo.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, true after logging noammo.

**Error states**

- None.

### ACTIONS.BOAT_CANNON_START_AIMING.pre_action_cb

Closes spell wheel before aiming cannon.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- None.

### ACTIONS.BOAT_CANNON_START_AIMING.fn

Sets cannon user via boatcannonuser:SetCannon if valid.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if cannon was set, nil otherwise.

**Error states**

- None.

### ACTIONS.BOAT_CANNON_SHOOT.fn

Shoots cannon by going to shoot state, clears user or target.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.BOAT_CANNON_STOP_AIMING.fn

Stops aiming cannon by setting cannon to nil.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.OCEAN_TRAWLER_LOWER.fn

Lowers ocean trawler net using oceantrawler:Lower.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.OCEAN_TRAWLER_RAISE.fn

Raises ocean trawler net using oceantrawler:Raise.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.OCEAN_TRAWLER_FIX.fn

Fixes trawler and notifies player via talker.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.GIVE_TACKLESKETCH.fn

Teaches new tackle sketch to crafting station if unknown, using tacklesketch:Teach.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if taught, `false` with `DUPLICATE` error if already known.

**Error states**

- `DUPLICATE` error if recipe already known.

### ACTIONS.REMOVE_FROM_TROPHYSCALE.fn

Removes item from trophy scale if target is valid, not burnt, not on fire, and has trophyscale component with canbetaken tag.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with optional reason string, or result of TakeItem call.

**Error states**

- `target` missing trophyscale, has 'burnt' or 'fire' tag, takeitemtestfn returns failure.

### ACTIONS.CYCLE.strfn

Returns 'TUNE' string if target is singingshell.

**Parameters**

- `act` — Action table.

**Returns**

- `string` 'TUNE' or nil.

**Error states**

- `target` is nil or doesn't have singingshell tag.

### ACTIONS.CYCLE.fn

Calls cyclable:Cycle if available and cancycle returns true.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- `target` missing cyclable component or cancycle returns false.

### ACTIONS.OCEAN_TOSS.fn

Tosses item into ocean by dropping it, adding projectile component, and launching it.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- `invobject` missing oceanthrowable, itemmimic present, inventory missing.

### ACTIONS.WINTERSFEAST_FEAST.fn

Placeholder action that always returns true as logic is handled in stategraph.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.BEGIN_QUEST.fn

Checks quest eligibility and begins quest if possible.

**Parameters**

- `act` — Action table.

**Returns**

- `success` (bool) with message.

**Error states**

- `target` missing questowner, CanBeginQuest fails.

### ACTIONS.ABANDON_QUEST.fn

Abandons active quest if questowner allows.

**Parameters**

- `act` — Action table.

**Returns**

- `success` (bool) with message.

**Error states**

- `target` missing questowner, CanAbandonQuest fails.

### ACTIONS.SING.fn

Adds song from inventory item to singer's inspiration if valid.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- missing invobject/singinginspiration, song already active, CanAddSong fails.

### ACTIONS.SING_FAIL.fn

Placeholder action for singing failure.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.SING_FAIL.stroverridefn

Returns SING action string for singing failure override.

**Parameters**

- `act` — Action table.

**Returns**

- `STRINGS.ACTIONS.SING`.

**Error states**

- None.

### ACTIONS.REPLATE.fn

Replates food using replater/replatable components with proper inventory/container handling.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- missing components, dish type mismatch, same dish, no grand owner.

### ACTIONS.SALT.fn

Salts food plate using quagmire_saltable component with proper inventory/container handling.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- missing quagmire_saltable component.

### ACTIONS.UNPATCH.fn

Unpatches boat leak by spawning patch item and setting leak state.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- missing boatleak component, lootdropper missing.

### ACTIONS.POUR_WATER.fn

Spreads water protection from item to target or point.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- missing invobject, itemmimic present, finiteuses empty.

### ACTIONS.POUR_WATER.strfn

Returns 'EXTINGUISH' string if target is on fire or smoldering.

**Parameters**

- `act` — Action table.

**Returns**

- `string` 'EXTINGUISH' or nil.

**Error states**

- target missing fire/smolder tags.

### ACTIONS.POUR_WATER_GROUNDTILE.fn

Alias for ACTIONS.POUR_WATER.fn.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- See ACTIONS.POUR_WATER.fn.

### ACTIONS.POUR_WATER_GROUNDTILE.stroverridefn

Returns generic POUR_WATER string for ground tile.

**Parameters**

- `act` — Action table.

**Returns**

- `STRINGS.ACTIONS.POUR_WATER.GENERIC`.

**Error states**

- None.

### ACTIONS.PLANTREGISTRY_RESEARCH_FAIL.fn

Research fail action that returns false with reason for fertilizer.

**Parameters**

- `act` — Action table.

**Returns**

- `false` with reason.

**Error states**

- None.

### ACTIONS.PLANTREGISTRY_RESEARCH.fn

Performs plant or fertilizer research with talker announcement.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- itemmimic present, no researchable components.

### ACTIONS.ASSESSPLANTHAPPINESS.stroverridefn

Returns formatted string for assessing plant happiness.

**Parameters**

- `act` — Action table.

**Returns**

- formatted string or nil.

**Error states**

- target missing plant display name.

### ACTIONS.ASSESSPLANTHAPPINESS.fn

Gets plant stress description and speaks it with talker if available.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- itemmimic present, no stress component or description.

### ACTIONS.PLANTWEED.fn

Plants random weed from weighted seed table into soil.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- target not soil, spawn fails.

### ACTIONS.ADDCOMPOSTABLE.fn

Adds compostable item to composting bin.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of AddCompostable call.

**Error states**

- target missing compostingbin component.

### ACTIONS.WAX.fn

Waxes item using waxable component.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of Wax call.

**Error states**

- target missing waxable component, itemmimic present.

### ACTIONS.UNLOAD_WINCH.fn

Calls winch's unloadfn callback.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of unloadfn call.

**Error states**

- missing winch component or unloadfn.

### ACTIONS.USE_HEAVY_OBSTACLE.strfn

Returns use_heavy_obstacle_string_key from target.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- target missing string key.

### ACTIONS.USE_HEAVY_OBSTACLE.fn

Uses heavy obstacle if equipped, target has can_use_heavy tag, and action filter passes.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of UseHeavyObstacle call.

**Error states**

- heavy item missing, tag missing, filter fails.

### ACTIONS.YOTB_SEW.fn

Starts or continues sewing on sewing machine.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- not sewing machine, already sewing, container in use, CanSew fails.

### ACTIONS.YOTB_STARTCONTEST.fn

Starts contest if stagemanager exists and contest not active.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- stagemanager missing, contest already active, host visible conditions.

### ACTIONS.YOTB_UNLOCKSKIN.fn

Unlocks skin if not already known and handles doll creation.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- missing components, skin already known.

### ACTIONS.MUTATE_SPIDER.fn

Mutates spider if mutation is valid.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- CanMutate returns false (SAMETYPE).

### ACTIONS.HERD_FOLLOWERS.fn

Herd's followers using followerherder if possible.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- CanHerd returns false.

### ACTIONS.BEDAZZLE.fn

Bedazzles target if bedazzler allows.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- CanBedazzle returns false.

### ACTIONS.REPEL.fn

Repels using repellent component.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- repellent component missing.

### ACTIONS.ADVANCE_TREE_GROWTH.fn

Advances tree growth using treegrowthsolution component.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- missing target, missing treegrowthsolution component.

### ACTIONS.DISMANTLE_POCKETWATCH.fn

Dismantles pocketwatch if dismantle is allowed.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- CanDismantle returns false.

### ACTIONS.STOP_LIFT_DUMBBELL.fn

Pushes 'stopliftingdumbbell' event.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- None.

### ACTIONS.LIFT_DUMBBELL.fn

Lifts dumbbell if CanLift passes and starts lifting.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- missing components, itemmimic, CanLift fails.

### ACTIONS.ENTER_GYM.fn

Enters gym if CanWorkout passes and starts workout.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- missing components, CanWorkout fails.

### ACTIONS.LIFT_GYM_FAIL.pre_action_cb

Fires bell ding for fail result and pushes lift_gym event.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- None.

### ACTIONS.LIFT_GYM_FAIL.fn

Placeholder action for gym lifting failure.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.LIFT_GYM_SUCCEED_PERFECT.pre_action_cb

Fires bell ding for perfect result.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- None.

### ACTIONS.LIFT_GYM_SUCCEED_PERFECT.fn

Placeholder action for perfect gym lift.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.LIFT_GYM_SUCCEED.pre_action_cb

Fires bell ding for succeed result.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- None.

### ACTIONS.LIFT_GYM_SUCCEED.fn

Placeholder action for successful gym lift.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.LEAVE_GYM.fn

Leaves gym and calls CharacterExitGym.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- gym missing from strongman component.

### ACTIONS.UNLOAD_GYM.fn

Unloads gym weight and calls UnloadWeight.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- target missing.

### ACTIONS.APPLYMODULE.fn

Applies upgrade module to owner if upgrade is possible.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- missing components, CanUpgrade fails.

### ACTIONS.APPLYMODULE_FAIL.fn

Speaks apply module fail string and returns true.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.APPLYMODULE_FAIL.stroverridefn

Returns APPLYMODULE action string for fail override.

**Parameters**

- `act` — Action table.

**Returns**

- `STRINGS.ACTIONS.APPLYMODULE`.

**Error states**

- None.

### ACTIONS.REMOVEMODULES.fn

Removes upgrade module if modules exist and deducts energy cost.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- missing components, no modules present.

### ACTIONS.REMOVEMODULES_FAIL.fn

Speaks remove modules fail string and returns true.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.REMOVEMODULES_FAIL.stroverridefn

Returns REMOVEMODULES action string for fail override.

**Parameters**

- `act` — Action table.

**Returns**

- `STRINGS.ACTIONS.REMOVEMODULES`.

**Error states**

- None.

### ACTIONS.CHARGE_FROM.strfn

Returns 'ITEM' or 'SELF' based on batteryuser tag.

**Parameters**

- `act` — Action table.

**Returns**

- `string` 'ITEM'/'SELF' or nil.

**Error states**

- no batteryuser tags.

### ACTIONS.CHARGE_FROM.fn

Charges batteryuser from battery target.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of ChargeFrom call.

**Error states**

- missing target battery, no batteryuser found.

### ACTIONS.ROTATE_FENCE.fn

Rotates fence using fencerotator component.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- missing fencerotator, itemmimic present.

### ACTIONS.USEMAGICTOOL.fn

Starts using magic tool via magician component.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of StartUsingTool call.

**Error states**

- magician missing, itemmimic present.

### ACTIONS.STOPUSINGMAGICTOOL.fn

Stops using magic tool via magician component.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- magician missing.

### ACTIONS.USESPELLBOOK.strfn

Returns spell type string based on user tags or item tags.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- no matching tags.

### ACTIONS.USESPELLBOOK.pre_action_cb

Pre-action handler to open spellbook via HUD if conditions met.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- HUD missing, spellbook conditions not met.

### ACTIONS.USESPELLBOOK.fn

Finalizes spellbook usage by handling inventory and closing containers.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` based on item state.

**Error states**

- fuel depleted, missing valid target.

### ACTIONS.CLOSESPELLBOOK.strfn

Returns spell type string for closing spellbook.

**Parameters**

- `act` — Action table.

**Returns**

- `string` or nil.

**Error states**

- no matching tags.

### ACTIONS.CLOSESPELLBOOK.pre_action_cb

Closes spell wheel via HUD if book is open.

**Parameters**

- `act` — Action table.

**Returns**

- `nil`.

**Error states**

- HUD missing.

### ACTIONS.CLOSESPELLBOOK.fn

Placeholder action for closing spellbook.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.CAST_SPELLBOOK.fn

Casts spell from spellbook if conditions met.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of CastSpell call.

**Error states**

- missing spellbook, CanBeUsedBy fails.

### ACTIONS.SITON.fn

Sits on sittable object if not occupied.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- not in start_sitting state, sittable missing, occupied.

### ACTIONS.USE_WEREFORM_SKILL.fn

Uses wereform skill on actor.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of UseWereFormSkill call.

**Error states**

- actor missing.

### ACTIONS.REMOTE_TELEPORT.stroverridefn

Returns formatted string for remote teleport action.

**Parameters**

- `act` — Action table.

**Returns**

- formatted string or nil.

**Error states**

- missing invobject display name.

### ACTIONS.REMOTE_TELEPORT.fn

Activates remote teleporter if possible.

**Parameters**

- `act` — Action table.

**Returns**

- success (bool) with reason.

**Error states**

- missing remoteteleporter, CanActivate fails, Teleport fails.

### ACTIONS.INCINERATE.fn

Incinerates contents using incinerator component.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false`.

**Error states**

- incinerator missing.

### ACTIONS.BOTTLE.fn

Bottles target using bottler component.

**Parameters**

- `act` — Action table.

**Returns**

- `result` of Bottle call.

**Error states**

- missing bottler component.

### ACTIONS.CARVEPUMPKIN.fn

Carves pumpkin if conditions met, drops and handles visibility.

**Parameters**

- `act` — Action table.

**Returns**

- `true/false` with reason.

**Error states**

- pumpkincarvable missing, can't see, someone else holding.

### ACTIONS.DECORATESNOWMAN.strfn

Returns 'STACK' string for snowman decoration if applicable.

**Parameters**

- `act` — Action table.

**Returns**

- `string` 'STACK' or nil.

**Error states**

- no valid decoration condition.

### ACTIONS.DECORATESNOWMAN.fn

Handles decorating a snowman with a held item or stacking snowballs; supports equipping hats or stacking items with validation.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason on failure.

**Error states**

- Fails silently in darkness, fails if target is melting, too high, or in use.

### ACTIONS.START_PUSHING.strfn

Provides the string override for starting a push, returning 'ROLL' if the target has the pushing_roll tag.

**Parameters**

- `act` — Action table.

**Returns**

- `String` 'ROLL' or nil.

**Error states**

- None.

### ACTIONS.START_PUSHING.fn

Initiates pushing on a pushable entity if not already pushing.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if push started successfully.

**Error states**

- Returns nil if target invalid, missing pushable component, or already pushing.

### ACTIONS.APPLYELIXIR.stroverridefn

Provides a string override for applying elixir, distinguishing between drinking and applying to others.

**Parameters**

- `act` — Action table.

**Returns**

- Formatted string or nil.

**Error states**

- None.

### ACTIONS.APPLYELIXIR.fn

Applies a ghostly elixir to a target, either directly or to the first eligible elixirable item found.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success with apply result, false with reason.

**Error states**

- Fails if target is too super, no elixirable item found, or invalid doer/object.

### ACTIONS.GRAVEDIG.fn

Handles grave digging by invoking the gravedigger on tool and then diggable target.

**Parameters**

- `act` — Action table.

**Returns**

- success and reason tuple.

**Error states**

- None.

### ACTIONS.MUTATE.stroverridefn

Provides a string override for the mutation action, showing the target name if available.

**Parameters**

- `act` — Action table.

**Returns**

- Formatted string or nil.

**Error states**

- None.

### ACTIONS.MUTATE.fn

Triggers a ghostgestalter mutation on the target if the component exists.

**Parameters**

- `act` — Action table.

**Returns**

- success and reason tuple.

**Error states**

- None.

### ACTIONS.WOBY_PICKUP.fn

Handles picking up items into a container, with restrictions for heavy lifting, burning, projectiles, and YOTC trainer ownership.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` with reason.

**Error states**

- Fails for restricted items, locked containers, heavy items, invalid owner, burning, thrown projectiles, or limbo status.

### ACTIONS.WOBY_PICK.validfn

Validates that a target is pickable or already targeted by woby.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if valid, `false` otherwise.

**Error states**

- None.

### ACTIONS.WOBY_PICK.fn

Performs a single harvest from a pickable entity, launching loot at the target.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if loot spawned, `false` otherwise.

**Error states**

- Fails if target missing pickable component or no loot spawned.

### ACTIONS.CONTAINER_INSTALL_ITEM.strfn

Provides string override for container install/uninstall action based on held status.

**Parameters**

- `act` — Action table.

**Returns**

- `String` 'UNINSTALL' or nil.

**Error states**

- None.

### ACTIONS.CONTAINER_INSTALL_ITEM.pre_action_cb

Plays negative UI sounds before installing to container if slots are full or invalid.

**Parameters**

- `act` — Action table.

**Returns**

- `nil` (side-effect only).

**Error states**

- None.

### ACTIONS.CONTAINER_INSTALL_ITEM.fn

Installs an item into a container or uninstalls it, handling specific slots and inventory transitions.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- Fails if no valid open container found or component checks fail.

### ACTIONS.MODSLINGSHOT.fn

Starts modding a slingshot using a slingshotmodder item, scanning inventory if needed.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of StartModding or false with reason.

**Error states**

- Fails if no valid slingshot found, restricted, or modder missing.

### ACTIONS.STOPMODSLINGSHOT.fn

Stops modding by closing the slingshot mods container.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of StopModding or false.

**Error states**

- Fails if no matching container found.

### ACTIONS.DASH.fn

Forces the doer to face the action point if valid.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if action point found, `false` otherwise.

**Error states**

- None.

### ACTIONS.WHISTLE.fn

Recalls Woby if the doer has woby_commands_classified.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if recall succeeded, `false` otherwise.

**Error states**

- None.

### ACTIONS.DRAW_FROM_DECK.fn

Draws top card from deck, spawns card, and adds to inventory or drops if full.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- Fails if deck empty or inventory give fails without fallback.

### ACTIONS.FLIP_DECK.fn

Flips a deck or playing card and plays a UI sound.

**Parameters**

- `act` — Action table.

**Returns**

- `true`.

**Error states**

- None.

### ACTIONS.ADD_CARD_TO_DECK.fn

Adds a card or deck to another deck or card, merging into decks as needed.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- None.

### ACTIONS.POUNCECAPTURE.fn

Attempts to capture a target using a gestalt cage, skipping if item mimic or invalid.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of Capture or false with reason.

**Error states**

- Fails if cage has item mimic or invalid target.

### ACTIONS.DIVEGRAB.fn

Attempts to catch a target with a moonstorm static catcher, skipping if item mimic or invalid.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of Catch or false with reason.

**Error states**

- Fails if catcher has item mimic or invalid target.

### ACTIONS.STARTELECTRICLINK.fn

Starts or ends linking on an electric connector fence.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of EndLinking or StartLinking or false.

**Error states**

- None.

### ACTIONS.ENDELECTRICLINK.fn

Disconnects all links on an electric connector fence.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of Disconnect or false.

**Error states**

- None.

### ACTIONS.REMOVELUNARBUILDUP.fn

Removes lunar buildup by performing work; supports one-hit clear for Bright-beaks.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- Fails if buildup not workable or item mimic present.

### ACTIONS.REMOVELUNARBUILDUP.validfn

Validates lunar buildup removal is allowed, checking for restricted equippable items.

**Parameters**

- `act` — Action table.

**Returns**

- `true` if valid, `false` otherwise.

**Error states**

- None.

### ACTIONS.SOAKIN.fn

Attempts to have the doer enter a bathing pool.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of EnterPool or nil.

**Error states**

- None.

### ACTIONS.TRANSFER_CRITTER.fn

Transfers a critter from one pet leash to a nearby hermit crab.

**Parameters**

- `act` — Action table.

**Returns**

- `true` on success, `false` otherwise.

**Error states**

- Fails if no hermit crab nearby, full, or attach fails.

### ACTIONS.JOUST.fn

Checks if a joust can be performed by verifying joustuser, joustsource, and no item mimic.

**Parameters**

- `act` — Action table.

**Returns**

- `Result` of CanJoust or nil.

**Error states**

- Fails if missing components or item mimic present.

## Events & listeners

- **listens_to**
  - `onremove` — Listened by SnowmanDecoratable to close decorating session when target is removed.
  - `ms_closepopup` — Listened by SnowmanDecoratable to close decorating session via popup close event.

- **pushes**
  - `onpickupitem` — Fired when an item is picked up.
  - `closecontainer` — Fired when a container is closed (via RUMMAGE).
  - `opencontainer` — Fired when a container is opened (via RUMMAGE).
  - `working` — Fired during rowing and row-failure actions to indicate partial completion.
  - `talkedto` — Fired on a target when interacted with for talking.
  - `CHEVO_fertilized` — Pushed when a pickable is fertilized.
  - `CHEVO_starteddrying` — Pushed when drying starts.
  - `murdered` — Pushed when cooking something alive (e.g., killer rabbit).
  - `killed` — Pushed when cooking something with combat component.
  - `tooltooweak` — Pushed during recoil when numworks becomes 0.
  - `recoil_off` — Pushed immediately during recoil when leaving recoil state.
  - `wonteatfood` — Pushed when player refuses to eat offered food.
  - `haunt` — Fired by ACTIONS.HAUNT.fn to initiate haunting.
  - `onwenthome` — Fired by ACTIONS.GOHOME.fn to signal entity returning home.
  - `plantwintertreeseed` — Pushed when planting a winter tree seed.
  - `onstartedfire` — Fired by ACTIONS.LIGHT.fn when fire is started.
  - `onacted` — Implicitly used but not directly found in chunk.
  - `brushed` — Fired by brushable:Brush.
  - `unpinned` — Fired by UNPIN action.
  - `onstolen` — Fired by STEALMOLEBAIT and CATPLAYGROUND.
  - `peek` — Fired by MOLEPEEK action.
  - `saddle` — Fired by SADDLE and UNSADDLE actions.
  - `respawnfromghost` — Fired by REMOTERESURRECT action.
  - `respawnfromcorpse` — Fired by revivablecorpse:Revive.
  - `dismount` — Fired by rider:Dismount.
  - `stacksizechange` — Fired by stackable:Put.
  - `on_petted` — Pushed by pet target when it receives a pet action.
  - `on_lower_sail_boost` — Pushed by doer when successfully boosting sail lowering.
  - `stopliftingdumbbell` — Pushed when stopping dumbbell lift.
  - `lift_gym` — Pushed during gym lifting fail/succeed states with result data.
  - `on_planted` — Pushed when weed is planted in soil.
  - `flipdeck` — Pushed when a deck or playing card is flipped.
  - `adopted_critter` — Pushed by hermit crab when a critter is transferred to it.