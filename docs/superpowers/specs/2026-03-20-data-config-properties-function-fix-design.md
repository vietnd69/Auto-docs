# Design: Fix SC1/SC4 — Sub-key Row Expansion and Local Factory Function Documentation

**Date:** 2026-03-20
**Scope:** `skills/quality_rules.md`, `skills/few_shot_data.md`
**Parent fix:** Follows `2026-03-20-data-config-skill-fix-design.md` (classification trigger, MUST/NEVER language, HOW TO DETECT header)

---

## Problem

After the first fix pass, two success criteria still fail when regenerating `achievements.lua` docs:

**SC1 (partial):** Properties table collapses `id.steam` and `id.psn` into a single `id` row instead of two separate rows. The `Achievements` container row is also missing. Default values appear as `nil` instead of `—` (em dash).

Root cause: The rule "one row per key in each record entry" is ambiguous — `id` IS a key in the record, so the model creates one row for it. Nothing in the current rules says to expand dot-notation sub-keys into their own rows. The em-dash NEVER rule also didn't prevent `nil` appearing.

**SC4:** `ACHIEVEMENT()` local factory function is dismissed as "local and used only during module initialization" — not documented at all.

Root cause: No rule exists for data config local factory functions. The model's training treats local functions as implementation details. The few-shot example shows `ENTRY()` being documented but the model did not generalize the pattern.

---

## Approach: Approach 1 — Surgical edits in-place

No new sections, no restructuring. Two targeted additions to `quality_rules.md` and two inline markers in `few_shot_data.md`.

---

## Changes

### `skills/quality_rules.md`

**Edit 1: Append two lines to `DATA CONFIG FILE PROPERTIES` block**

Append after `NEVER use a real default value for record fields — always write "—" (em dash).`:

```
NEVER write "nil" as a default — that is a real default value. Use "—" only.
Nested table fields accessed via dot notation (id.steam, id.psn) MUST each be
their own property row. Never collapse them into a single parent row (e.g., id).
```

**Edit 2: Insert new `DATA CONFIG FILE MAIN FUNCTIONS` block** after the properties block:

```
DATA CONFIG FILE MAIN FUNCTIONS:
Local factory/builder functions that construct record entries (e.g., ACHIEVEMENT(),
ENTRY()) MUST be documented in ## Main functions — they define the record schema
and are part of the data API. Do NOT treat them as internal implementation details
or skip them because they are local.
```

---

### `skills/few_shot_data.md`

**Edit 3: Add inline comment above Properties table header**

Insert before the `| Property | Type | ...` header row:

```
<!-- RULE: Each dot-notation sub-key (id.steam, id.psn) gets its own row. Never collapse into a single "id" row. -->
```

**Edit 4: Add REQUIRED marker above `ENTRY()` in Main functions**

Insert before `### \`ENTRY(id, name)\``:

```
<!-- REQUIRED: Local factory functions like ENTRY() MUST be documented here — they define the record schema. Do NOT skip because they are local. -->
```

---

## Files Changed

| File | Edit |
|------|------|
| `skills/quality_rules.md` | Append 3 lines to DATA CONFIG FILE PROPERTIES; insert DATA CONFIG FILE MAIN FUNCTIONS block |
| `skills/few_shot_data.md` | Add comment before Properties table; add REQUIRED marker before ENTRY() |

## Files NOT Changed

| File | Reason |
|------|--------|
| `docs_SKILL.md` | Injection scope already fixed in previous pass |
| `skills/dst_conventions.md` | Unrelated |
| `skills/few_shot.md` | Component example unaffected |

---

## Success Criteria

**SC1 — Properties table has exactly 4 rows:**
- `Achievements` (container row)
- `name`
- `id.steam`
- `id.psn`
Default values must be `—` (em dash), not `nil`.

**SC4 — ACHIEVEMENT() is documented in Main functions:**
- Parameters section references `tostring(id).."_"..name` concatenation for steam
- Parameters section references numeric passthrough for psn (`psn = id`)
- Function is NOT described as internal/skipped

**Regression — health.md unchanged:**
- Properties table still uses `self.` constructor fields
- No two-group container+record schema appears
- Overview still describes it as an ECS component
