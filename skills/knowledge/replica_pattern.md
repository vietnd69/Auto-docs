---
name: replica_pattern
description: Replica component pattern — netvar mirroring, master/client routing, RPC registration, and documentation rules for *_replica.lua files
inject_into: [analyst, analyst_chunk, analyst_merge, reviewer_full, reviewer_typed]
---

## Replica Components

Files matching `components/*_replica.lua` are CLIENT-SIDE mirrors of master components. They
expose read-only state to the client via netvars and forward player-initiated actions back to
the master via RPCs.

### Detection

- Filename ends in `_replica.lua`.
- Constructor declares one or more `self.X = net_bool(self.inst.GUID, "ns.field", "ns.field_dirty")`-style netvars.
- Class name typically matches the master with `_replica` suffix (e.g., `Combat_Replica`).

### Document the master/replica relationship explicitly

The Overview MUST mention:
1. The corresponding master component (e.g., "mirrors `combat` master state to clients").
2. Which fields are mirrored via netvars.
3. Whether the replica forwards any RPCs back to the master.

### Properties section

List EVERY netvar with this format:

| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `_target` | net_entity | --- | Mirrors `Combat.target` from the master. Read via `GetTarget()`. |
| `_canattack` | net_bool | `true` | Mirrors `Combat.canattack`; gated by `Combat:CanAttackable()` on master. |

Default Value:
- For netvars, write the literal default (e.g., `true`, `0`, `""`) when source initialises it.
- If the netvar is initialised by an external setter rather than constructor literal, write `---`.

### Main functions

Group methods by execution context:

- **Constructor / `_ctor`**: declare netvars, register dirty event listeners.
- **Getters (client-readable)**: `GetTarget()`, `IsAttacker()` — mark `(client read)`.
- **Setters (master-only)**: `SetTarget(target)`, `SetCanAttack(b)` — mark `(master only)`.
- **RPC handlers**: methods registered via `AddRPCHandler(...)` — mark `(RPC handler)`.

Format example:

```md
### `GetTarget()` (client read)
*   **Description:** Returns the entity currently mirrored from `master.combat.target`. Safe to call on both client and master.
*   **Parameters:** None
*   **Returns:** entity or `nil`
*   **Error states:** None.

### `SetTarget(target)` (master only)
*   **Description:** Updates `_target` netvar and propagates to clients on next network tick. No-op on client.
*   **Parameters:** `target` -- entity instance or `nil` to clear
*   **Returns:** nil
*   **Error states:** Errors if called on client without master guard. Source typically guards with `if not TheWorld.ismastersim then return end`; if absent, list as error state.
```

### Usage example

Show client-side query first, then optional master-side mutation:

```lua
-- Client-side read:
if inst.replica.combat ~= nil then
    local target = inst.replica.combat:GetTarget()
end

-- Master-side mutation (only valid on server):
if TheWorld.ismastersim then
    inst.replica.combat:SetTarget(some_entity)
end
```

### Reviewer note

The reviewer MUST check that:
- Each netvar declared in source appears in the Properties table.
- Methods with master-only guards are correctly marked `(master only)`.
- The replica's relationship to its master component is stated in Overview.
