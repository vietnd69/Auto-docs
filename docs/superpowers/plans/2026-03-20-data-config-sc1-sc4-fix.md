# Data Config SC1/SC4 Fix Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix two remaining LLM output failures for data config files — Properties sub-key row collapse (SC1) and local factory function being dismissed (SC4).

**Architecture:** Four surgical text edits across two skill files. No code changes. Verification is done by regenerating `achievements.lua` docs and checking against success criteria.

**Tech Stack:** Markdown text editing, Python pipeline (`main.py`), `.venv`

**Spec:** `docs/superpowers/specs/2026-03-20-data-config-properties-function-fix-design.md`

---

## Chunk 1: Edit skill files

### Task 1: Harden `quality_rules.md` — sub-key expansion and local function rules

**Files:**
- Modify: `skills/quality_rules.md`

- [ ] **Step 1: Append sub-key and nil rules to DATA CONFIG FILE PROPERTIES block**

  **Find** (exact text, currently line 66):
  ```
  NEVER use a real default value for record fields — always write "—" (em dash).
  ```

  **Replace with:**
  ```
  NEVER use a real default value for record fields — always write "—" (em dash).
  NEVER write "nil" as a default — that is a real default value. Use "—" only.
  Nested table fields accessed via dot notation (id.steam, id.psn) MUST each be
  their own property row. Never collapse them into a single parent row (e.g., id).
  ```

- [ ] **Step 2: Insert DATA CONFIG FILE MAIN FUNCTIONS block before COMPLETENESS section**

  **Find** (exact text, currently line 68):
  ```
  COMPLETENESS:
  ```

  **Replace with:**
  ```
  DATA CONFIG FILE MAIN FUNCTIONS:
  Local factory/builder functions that construct record entries (e.g., ACHIEVEMENT(),
  ENTRY()) MUST be documented in ## Main functions — they define the record schema
  and are part of the data API. Do NOT treat them as internal implementation details
  or skip them because they are local.

  COMPLETENESS:
  ```

- [ ] **Step 3: Verify the edits**

  Read `skills/quality_rules.md` and confirm:
  - `NEVER write "nil" as a default` line is present inside DATA CONFIG FILE PROPERTIES block
  - `Nested table fields accessed via dot notation` line is present
  - `DATA CONFIG FILE MAIN FUNCTIONS:` block appears between the properties block and `COMPLETENESS:`
  - The block contains the `ACHIEVEMENT()` and `ENTRY()` examples

---

### Task 2: Add inline markers to `few_shot_data.md`

**Files:**
- Modify: `skills/few_shot_data.md`

- [ ] **Step 1: Add sub-key comment above Properties table**

  **Find** (exact text, currently lines 44-45):
  ```
  ## Properties
  | Property | Type | Default Value | Description |
  ```

  **Replace with:**
  ```
  ## Properties
  <!-- RULE: Each dot-notation sub-key (id.steam, id.psn) gets its own row. Never collapse into a single "id" row. -->
  | Property | Type | Default Value | Description |
  ```

- [ ] **Step 2: Add REQUIRED marker above ENTRY() function**

  **Find** (exact text, currently lines 52-53):
  ```
  ## Main functions
  ### `ENTRY(id, name)`
  ```

  **Replace with:**
  ```
  ## Main functions
  <!-- REQUIRED: Local factory functions like ENTRY() MUST be documented here — they define the record schema. Do NOT skip because they are local. -->
  ### `ENTRY(id, name)`
  ```

- [ ] **Step 3: Verify the edits**

  Read `skills/few_shot_data.md` and confirm:
  - HTML comment about dot-notation sub-keys is present between `## Properties` and the table header
  - HTML comment about REQUIRED local factory functions is present between `## Main functions` and `### \`ENTRY(id, name)\``

---

### Task 3: Commit skill file changes

- [ ] **Step 1: Commit**

  ```bash
  git add skills/quality_rules.md skills/few_shot_data.md
  git commit -m "fix: harden sub-key row expansion and local factory function rules

  - NEVER write nil as default (explicit, not covered by em dash rule alone)
  - Nested dot-notation fields (id.steam, id.psn) each MUST have own row
  - New DATA CONFIG FILE MAIN FUNCTIONS block: local factory functions MUST
    be documented, not treated as internal implementation details
  - Inline comments in few_shot_data.md to reinforce both rules in-example"
  ```

---

## Chunk 2: Verification

### Task 4: Regenerate achievements.md and verify SC1 + SC4

**Files:**
- Run against: `dst-scripts/achievements.lua`
- Output: `dst-api-webdocs/docs/achievements.md`

- [ ] **Step 1: Delete existing achievements.md**

  The pipeline skips files that already exist. Delete the current output to force regeneration:

  ```bash
  rm dst-api-webdocs/docs/achievements.md
  ```

- [ ] **Step 2: Activate venv and run pipeline**

  ```bash
  .venv/Scripts/activate && python main.py
  ```

  Wait for completion. The pipeline will skip all other files that already have docs and process only `achievements.lua`.

- [ ] **Step 3: Verify SC1 — Properties table has exactly 4 rows with em-dash defaults**

  Open `dst-api-webdocs/docs/achievements.md` and confirm the Properties section contains exactly these rows (and no others):
  - `Achievements` — container row, type `table`, default `—`
  - `name` — type `string`, default `—`
  - `id.steam` — type `string`, default `—`
  - `id.psn` — type `number`, default `—`

  Confirm: NO row named `id` (collapsed). NO `nil` in Default Value column.

- [ ] **Step 4: Verify SC4 — ACHIEVEMENT() is documented**

  Confirm `## Main functions` section contains a documented `ACHIEVEMENT(id, name)` entry that:
  - Describes the `id` parameter referencing `tostring(id).."_"..name` (or equivalent) for the steam field
  - Describes the numeric passthrough behavior for `psn`
  - Does NOT say "local and used only during module initialization" or dismiss it as internal

- [ ] **Step 5: Verify SC2 and SC3 still pass (regression)**

  Confirm:
  - Usage example uses `Achievements[1]` (array index, not string key)
  - Overview does NOT contain `AddComponent`, `ECS`, `inst.components`, or describe the file as a "component"

- [ ] **Step 6: Regression check — regenerate health.md**

  ```bash
  rm dst-api-webdocs/docs/components/health.md
  python main.py
  ```

  Open `dst-api-webdocs/docs/components/health.md` and confirm:
  - Properties table uses `self.` constructor fields (e.g., `maxhealth`, `currenthealth`) — NOT a two-group container+record schema
  - Overview describes it as a component in the ECS system
  - `## Main functions` does NOT say "None identified"

- [ ] **Step 7: Commit verified outputs**

  ```bash
  git add dst-api-webdocs/docs/achievements.md dst-api-webdocs/docs/components/health.md
  git commit -m "docs: regenerate achievements.md and health.md with SC1/SC4 fixes verified"
  ```
