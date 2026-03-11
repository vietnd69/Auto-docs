---
id: actions
title: Actions
description: Central action system defining player and entity interactions, including validation, execution, and string labeling for actions like chopping, mining, fishing, and spellcasting.
tags: [action, entity, player, interaction, system]
sidebar_position: 10

last_updated: 2026-03-11
build_version: 714014
change_status: stable
category_type: root
source_hash: 82eee1ae
system_scope: player
---

# Actions

> Based on game build **714014** | Last updated: 2026-03-11

## Overview
The `actions.lua` file defines the core action system for Don't Starve Together, implementing a comprehensive framework for player and entity interactions. It provides action definitions (via `ACTIONS` table), validation functions (`validfn`), execution logic (`fn`), string labeling (`strfn`), and range checks (`rangecheckfn`). Actions are invoked through the `ACTIONS_MAP` and support remapping (e.g., for map-based targeting like BLINK), with extensive integration into components such as `workable`, `repairable`, `fueled`, `inventory`, `container`, `spellbook`, `aoespell`, `fishingrod`, `pickable`, `searchable`, `plantable`, `fertilizer`, `burnable`, `trap`, `trader`, `eater`, `crittertraits`, `petleash`, `joustuser`, `joustsource`, `lunarhailbuildup`, `bathingpool`, `itemmimic`, and many more. The system handles context-sensitive behavior, including state checks, inventory constraints, physics-based range calculations, and platform-specific logic (e.g., water vs. land).

## Usage example
```lua
-- Example: Define a custom action for harvesting a special crop
ACTIONS.MY_HARVEST = {
    code = 100,
    priority = 1,
    fn = function(act)
        if act.target.components.crop and act.target.components.crop:IsReadyForHarvest() then
            act.target.components.crop:Harvest(act.doer)
            return true
        end
        return false, "NOTREADY"
    end,
    validfn = function(act)
        return act.target ~= nil and act.target:HasTag("crop") and
               act.target.components.crop and act.target.components.crop:IsReadyForHarvest()
    end,
    strfn = function(act)
        return "HARVEST"
    end,
    rangecheckfn = DefaultRangeCheck,
}
```

## Dependencies & tags
**Components used:**
activatable, anchor, aoespell, appraisable, attunable, attuner, bait, balloonmaker, bathbomb, bathbombable, bathingpool, battery, batteryuser, beard, bedazzler, blinkstaff, boatcannon, boatcannonuser, boatleak, boatmagnet, boatmagnetbeacon, boatrotator, book, bottler, brushable, builder, bundler, burnable, carnivalgamefeedable, cattoy, channelable, channelcastable, channelcaster, childspawner, clientpickupsoundsuppressor, closeinspector, combat, complexprojectile, compostingbin, constructionbuilder, constructionbuilderuidata, constructionplans, constructionsite, container, container_proxy, containerinstallableitem, cookable, cooker, craftingstation, crewmember, crittertraits, crop, curseditem, cyclable, deckcontainer, deployable, drawable, drawingtool, dryer, dryingrack, dumbbelllifter, eater, edible, electricconnector, entitytracker, equippable, expertsailor, fan, farmplantable, farmplantstress, farmplanttendable, farmtiller, fertilizable, fertilizer, fertilizerresearchable, fillable, finiteuses, fishingnet, fishingrod, follower, followerherder, forgerepair, forgerepairable, freezable, fueled, fueler, furnituredecortaker, gestaltcage, ghostgestalter, ghostlybond, ghostlyelixir, ghostlyelixirable, grabbable, gravediggable, gravedigger, groomer, grower, guardian, halloweenpotionmoon, harvestable, hauntable, healer, health, heavyobstacleusetarget, helmsplitter, hideandseekhidingspot, hideout, hitchable, hitcher, incinerator, inspectable, instrument, inventory, inventoryitem, inventoryitemholder, itemmimic, itemtyperestrictions, itemweigher, joustsource, joustuser, kitcoon, kitcoonden, klaussacklock, knownlocations, lighter, lock, locomotor, lootdropper, lunarhailbuildup, machine, magician, maprecorder, mapspotrevealer, markable, markable_proxy, mast, maxhealer, maxwelltalker, mightygym, mine, moonstormstaticcatcher, moontrader, murderable, nabbag, npc_talker, oar, occupiable, occupier, oceanfishable, oceanfishingrod, oceanthrowable, oceantrawler, papereraser, perishable, petleash, pickable, pinnable, plantresearchable, playbill, playbill_lecturn, playercontroller, playingcard, playingcardsmanager, pocketwatch, pocketwatch_dismantler, pollinator, poppable, portablestructure, preservative, projectile, pumpkincarvable, pumpkinhatcarvable, pushable, questowner, reader, recipescanner, remoteteleporter, repairable, repairer, repellent, revivablecorpse, rideable, rider, sanity, scrapbookable, searchable, sewing, shaveable, shaver, shelf, simplebook, singable, singinginspiration, sittable, skilltreeupdater, sleepingbag, slingshotmodder, slingshotmods, snowmandecoratable, soul, souleater, spawner, spellbook, spellcaster, spidermutator, spooked, stackable, stageactingprop, stageactor, steeringwheel, steeringwheeluser, stewer, storyteller, strongman, summoningitem, tackler, tacklesketch, talkable, talker, teacher, teleporter, terraformer, thief, toggleableitem, tool, trader, trap, treegrowthsolution, trophyscale, unwrappable, upgradeable, upgrademodule, upgrademoduleowner, upgrader, useableitem, useabletargeteditem, vase, walkingplank, wardrobe, wateryprotection, waxable, weighable, winch, workable, worker, workmultiplier, worldmigrator, writeable, yotb_sewer, yotb_skinunlocker, yotb_stagemanager, yotb_stager, yotc_racecompetitor, yotc_raceprizemanager, yotc_racestart

**Tags:**
`repairable_moon_altar`, `repairable_vitae`, `tape`, `frozen`, `pet_treat`, `nibble`, `has_aggressive_follower`, `trophyscale_chicken`, `weighable_chicken`, `trophyscale_fish`, `weighable_fish`, `trophyscale_cowgirl`, `weighable_cowgirl`, `trophyscale_pigman`, `weighable_pigman`, `trophyscale_squid`, `weighable_squid`, `trophyscale_crab`, `weighable_crab`, `trophyscale_snurtle`, `weighable_snurtle`, `trophyscale_bird`, `weighable_bird`, `trophyscale_butterfly`, `weighable_butterfly`, `trophyscale_bee`, `weighable_bee`, `trophyscale_spider`, `weighable_spider`, `trophyscale_snatcher`, `weighable_snatcher`, `trophyscale_bat`, `weighable_bat`, `trophyscale_penguin`, `weighable_penguin`, `trophyscale_pig`, `weighable_pig`, `trophyscale_rabbit`, `weighable_rabbit`, `trophyscale_mole`, `weighable_mole`, `trophyscale_molebat`, `weighable_molebat`, `trophyscale_sheep`, `weighable_sheep`, `trophyscale_beefalo`, `weighable_beefalo`, `trophyscale_krampus`, `weighable_krampus`, `trophyscale_spring`, `weighable_spring`, `trophyscale_summer`, `weighable_summer`, `trophyscale_autumn`, `weighable_autumn`, `trophyscale_winter`, `weighable_winter`, `trophyscale_moon`, `weighable_moon`, `trophyscale_sun`, `weighable_sun`, `trophyscale_star`, `weighable_star`, `trophyscale_moonrock`, `weighable_moonrock`, `trophyscale_snow`, `weighable_snow`, `trophyscale_snowball`, `weighable_snowball`, `trophyscale_snowpile`, `weighable_snowpile`, `trophyscale_snowpile_small`, `weighable_snowpile_small`, `trophyscale_snowpile_medium`, `weighable_snowpile_medium`, `trophyscale_snowpile_large`, `weighable_snowpile_large`, `trophyscale_snowpile_huge`, `weighable_snowpile_huge`, `trophyscale_snowpile_giant`, `weighable_s