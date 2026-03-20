---
id: builtinusercommands
title: Builtinusercommands
description: Registers default chat commands and voting logic for the server.
tags: [commands, chat, admin, voting]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: ab75f569
system_scope: network
---

# Builtinusercommands

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
`builtinusercommands.lua` is a global initialization script that registers the default set of chat commands available to players and administrators (e.g., `/help`, `/kick`, `/roll`). It is not an Entity Component System (ECS) component attached to entities; instead, it executes on load to populate the `UserCommands` system. Modders typically reference this file to understand the structure required for adding custom commands via `AddUserCommand`.

## Usage example
Modders do not `require` this file directly. Instead, they create their own command registration scripts following the pattern established here.

```lua
AddUserCommand("mycommand", {
    prettyname = "My Command",
    desc = "Does something useful.",
    permission = COMMAND_PERMISSION.USER,
    slash = true,
    params = {"option"},
    paramsoptional = {true},
    localfn = function(params, caller)
        -- Client-side logic
        TheNet:Say("Command executed by " .. caller.name)
    end,
})
```

## Dependencies & tags
**Components used:** None (Global script).
**Tags:** None identified.

## Properties
This file does not instantiate a class with properties. However, the command definition tables passed to `AddUserCommand` utilize the following configuration fields observed in the source code.

| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `permission` | enum | `COMMAND_PERMISSION.USER` | Required permission level (e.g., `USER`, `MODERATOR`, `ADMIN`). |
| `slash` | boolean | `true` | Whether the command is invoked with a `/` prefix. |
| `params` | table | `{}` | List of parameter names expected by the command. |
| `paramsoptional` | table | `{}` | Boolean list indicating if each param is optional. |
| `localfn` | function | `nil` | Function executed on the client when the command is called. |
| `serverfn` | function | `nil` | Function executed on the master server (if applicable). |
| `vote` | boolean | `false` | Whether the command requires a player vote to execute. |
| `aliases` | table | `{}` | Alternative names for the command (e.g., `{"e", "me"}`). |
| `votetimeout` | number | `30` | Time in seconds before a vote expires. |
| `confirm` | boolean | `false` | Whether a confirmation dialog is shown before execution. |

## Main functions
The script defines callback functions within command tables. These are not exported methods but execution hooks called by the `UserCommands` system.

### `localfn(params, caller)`
*   **Description:** Executed on the client when the user invokes the command. Handles UI feedback or local logic.
*   **Parameters:** 
    *   `params` (table) - Contains parsed command arguments (e.g., `params.user`, `params.seconds`).
    *   `caller` (entity) - The player entity executing the command (may be `nil` during voting).
*   **Returns:** Nothing.
*   **Error states:** May return early if `caller` or `caller.HUD` is `nil`.

### `serverfn(params, caller)`
*   **Description:** Executed on the master server for commands that affect world state (e.g., `/rollback`, `/regenerate`).
*   **Parameters:** 
    *   `params` (table) - Command arguments.
    *   `caller` (entity) - The player entity (may be `nil` during voting).
*   **Returns:** Nothing.
*   **Error states:** Checks `world.ismastersim` before executing world-altering logic.

### `votecanstartfn(command, caller, targetid)`
*   **Description:** Determines if a vote is allowed to start for this command.
*   **Parameters:** 
    *   `command` (table) - The command definition.
    *   `caller` (entity) - Player attempting to start the vote.
    *   `targetid` (string) - ID of the target (if applicable).
*   **Returns:** Boolean (success), optional string (failure reason).
*   **Error states:** Returns `false` if cooldowns or permissions are not met.

## Events & listeners
- **Listens to:** None identified.
- **Pushes:** None identified. (Interacts directly with `TheNet` and `UserCommands` APIs).