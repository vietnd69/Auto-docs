---
id: chathistory
title: Chathistory
description: Manages chat message history storage, retrieval, and network synchronization for player and system communications.
tags: [ui, chat, network, history]
sidebar_position: 10

last_updated: 2026-03-20
build_version: 714014
change_status: stable
category_type: root
source_hash: 4cd941a6
system_scope: ui
---

# Chathistory

> Based on game build **714014** | Last updated: 2026-03-20

## Overview
`ChatHistory` is a manager class that maintains a circular buffer of chat messages displayed in the game UI. It handles multiple chat types including player messages, emotes, announcements, system messages, and NPC chatter. The component manages history persistence across server joins, filters duplicate NPC messages, applies word filtering, and synchronizes chat history between clients and server via RPC calls. It operates as a singleton instance (`ChatHistory`) rather than an entity component.

## Usage example
```lua
-- Access the global ChatHistory manager instance
local chatHistory = ChatHistory

-- Add a listener for new chat messages
chatHistory:AddChatHistoryListener(function(message)
    print("New chat:", message.message)
end)

-- Add a system message to history
chatHistory:OnSystemMessage("Server restarting in 5 minutes")

-- Retrieve the most recent chat message
local latestMessage = chatHistory:GetChatMessageAtIndex(1)
print(latestMessage.sender, latestMessage.message)
```

## Dependencies & tags
**Components used:** None (this is a manager class, not an entity component)
**Tags:** None identified

## Properties
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `listeners` | table | `{}` | Registered callback functions for chat history events |
| `history` | table | `{}` | Circular buffer storing chat message objects |
| `request_history_start` | number | `1` | Index tracking pending history sync requests |
| `history_start` | number | `MAX_CHAT_HISTORY` | Current write position in circular buffer |
| `MAX_CHAT_HISTORY` | number | `100` | Maximum messages retained in history buffer |
| `NPC_CHATTER_MAX_CHAT_NO_DUPES` | number | `20` | Number of recent messages checked for NPC duplicate filtering |
| `join_server` | boolean | `nil` | Flag indicating player has joined the server |
| `max_chat_history_plus_one` | any | `nil` | Reference to message overwritten during buffer rotation |

## Main functions
### `JoinServer()`
*   **Description:** Marks the manager as having completed server join, enabling normal chat history operations.
*   **Parameters:** None.
*   **Returns:** Nothing.
*   **Error states:** Must be called after player joins to enable message processing.

### `GetDisplayName(name, prefab)`
*   **Description:** Resolves a display name for chat sender, falling back to unknown user string if empty.
*   **Parameters:** `name` (string) - sender name, `prefab` (string) - sender prefab reference.
*   **Returns:** string - resolved display name.

### `OnAnnouncement(message, colour, announce_type)`
*   **Description:** Processes server announcement messages and adds them to history.
*   **Parameters:** `message` (string) - announcement text, `colour` (table) - RGBA colour, `announce_type` (any) - type identifier.
*   **Returns:** Nothing.
*   **Error states:** Returns early if `join_server` is not set.

### `OnSay(guid, userid, netid, name, prefab, message, colour, whisper, isemote, user_vanity)`
*   **Description:** Processes player chat messages, applying visibility checks and word filtering.
*   **Parameters:** `guid` (string) - entity GUID, `userid` (string) - user ID, `netid` (string) - network ID, `name` (string) - sender name, `prefab` (string) - prefab name, `message` (string) - chat text, `colour` (table) - text colour, `whisper` (boolean) - whisper flag, `isemote` (boolean) - emote flag, `user_vanity` (table) - vanity item data.
*   **Returns:** Nothing.
*   **Error states:** Returns early if `join_server` is not set or message fails visibility range check.

### `OnChatterMessage(inst, name_colour, message, colour, user_vanity, user_vanity_bg, priority)`
*   **Description:** Processes NPC chatter messages with duplicate filtering and priority checks.
*   **Parameters:** `inst` (entity) - chatter entity, `name_colour` (table) - name colour, `message` (string) - chatter text, `colour` (table) - message colour, `user_vanity` (string) - icon name, `user_vanity_bg` (string) - icon background, `priority` (number) - message priority level.
*   **Returns:** Nothing.
*   **Error states:** Returns early if NPC chat is disabled, priority exceeds profile setting, or message is duplicate within recent history.

### `AddToHistory(type, sender_userid, sender_netid, sender_name, message, colour, icondata, whisper, localonly, text_filter_context)`
*   **Description:** Adds a formatted chat message to the circular history buffer with duplicate filtering for chatter.
*   **Parameters:** `type` (number) - `ChatTypes` enum value, `sender_userid` (string) - user ID, `sender_netid` (string) - network ID, `sender_name` (string) - display name, `message` (string) - message text, `colour` (table) - colour data, `icondata` (table|string) - icon information, `whisper` (boolean) - whisper flag, `localonly` (boolean) - local visibility flag, `text_filter_context` (string) - filter context.
*   **Returns:** table - the generated chat message object.
*   **Error states:** Returns early if `join_server` is not set or duplicate chatter message detected.

### `GetChatMessageAtIndex(idx)`
*   **Description:** Retrieves a chat message from the history buffer by index.
*   **Parameters:** `idx` (number) - index from `1` (newest) to `MAX_CHAT_HISTORY` (oldest).
*   **Returns:** table - chat message object or `nil` if empty.
*   **Error states:** Returns `nil` if no message exists at index.

### `AddChatHistoryListener(fn)`
*   **Description:** Registers a callback function to be invoked when new messages are added to history.
*   **Parameters:** `fn` (function) - callback receiving chat message object.
*   **Returns:** Nothing.

### `RemoveChatHistoryListener(fn)`
*   **Description:** Unregisters a previously added chat history listener.
*   **Parameters:** `fn` (function) - callback to remove.
*   **Returns:** Nothing.

### `RequestChatHistory()`
*   **Description:** Initiates a server RPC request to synchronize missing chat history entries.
*   **Parameters:** None.
*   **Returns:** Nothing.
*   **Error states:** Returns early if `join_server` is not set or no pending request exists.

### `RecieveChatHistory(chat_history)`
*   **Description:** Processes received chat history data from server and inserts into buffer.
*   **Parameters:** `chat_history` (string) - encoded and compressed history data.
*   **Returns:** Nothing.
*   **Error states:** Returns early if no pending request exists.

### `GetChatHistory()`
*   **Description:** Exports current history buffer as encoded save data.
*   **Parameters:** None.
*   **Returns:** string - compressed and encoded history data.

### `SetChatHistory(history)`
*   **Description:** Imports and restores history buffer from saved data.
*   **Parameters:** `history` (string) - encoded save data from `GetChatHistory()`.
*   **Returns:** Nothing.

## Events & listeners
- **Listens to:** None (uses custom listener system via `AddChatHistoryListener`)
- **Pushes:** None (invokes registered listener callbacks directly when messages are added)