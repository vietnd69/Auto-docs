# Data Config Skill Fix Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Fix the LLM doc generation pipeline so data config files (no constructor, returns plain table/array) consistently produce Properties tables with both the top-level container AND all record schema fields.

**Architecture:** Three targeted text edits across two skill files and one config file. No code changes. Verification is done by regenerating `achievements.lua` docs and diffing against success criteria.

**Tech Stack:** Markdown text editing, Python pipeline (`main.py`), `.venv`

**Spec:** `docs/superpowers/specs/2026-03-20-data-config-skill-fix-design.md`

---

## Chunk 1: Edit skill files and config

### Task 1: Add FILE TYPE CLASSIFICATION block to `quality_rules.md`

**Files:**
- Modify: `skills/quality_rules.md:46` — insert before PROPERTIES TABLE section

- [ ] **Step 1: Insert classification block before line 46**

  Add the following block immediately before the `PROPERTIES TABLE:` line:

  ```
  FILE TYPE CLASSIFICATION (determine before writing any section):
  - DATA CONFIG FILE: no Class() constructor, no self.inst, returns a plain table/array.
    → MUST apply ALL [Data config] rules. Do NOT use [Component] patterns.
    → Consult the HOW TO DETECT note at the top of the data config few-shot example.
  - COMPONENT FILE: has Class(function(self, ...) ... end) constructor.
    → MUST apply ALL [Component] rules. Do NOT use [Data config] patterns.
  When signals are mixed (e.g., local helper functions that resemble constructors),
  check: does the file's top-level return value contain a plain array/table, not a class instance?
  If yes → DATA CONFIG FILE.

  ```

  Result: `PROPERTIES TABLE:` becomes the section immediately after this block.

- [ ] **Step 2: Verify the edit**

  Read `skills/quality_rules.md` lines 44-60 and confirm:
  - `FILE TYPE CLASSIFICATION` block appears before `PROPERTIES TABLE:`
  - The `→ Consult the HOW TO DETECT note` line is present

---

### Task 2: Strengthen DATA CONFIG FILE PROPERTIES rule in `quality_rules.md`

**Files:**
- Modify: `skills/quality_rules.md:51-56` — replace existing DATA CONFIG FILE PROPERTIES block

- [ ] **Step 1: Replace the DATA CONFIG FILE PROPERTIES block**

  Replace existing lines 51-56 (after the insert from Task 1, line numbers will shift — locate by content):

  **Find:**
  ```
  DATA CONFIG FILE PROPERTIES:
  - When the source has no constructor (returns a plain table/array), document BOTH:
    1. The top-level container (the returned global/local table variable).
    2. The schema of each individual record entry: list every key present in the record tables
       (e.g., `name`, `id.steam`, `id.psn` for achievement records).
  - Never document only the container and omit the record schema.
  ```

  **Replace with:**
  ```
  DATA CONFIG FILE PROPERTIES:
  MUST document TWO groups of rows in this order:
    1. The top-level container variable (the returned global/local table).
    2. One row per key in each record entry (e.g., name, id.steam, id.psn).
  NEVER document only the container and omit the record schema.
  NEVER use a real default value for record fields — always write "—" (em dash).
  ```

- [ ] **Step 2: Verify the edit**

  Read the DATA CONFIG FILE PROPERTIES block and confirm:
  - Uses `MUST` and `NEVER` language (not soft "document BOTH")
  - Lists the "NEVER use a real default value" line (new addition)

---

### Task 3: Add back-references in OVERVIEW WRITING and USAGE EXAMPLE WRITING

**Files:**
- Modify: `skills/quality_rules.md` — OVERVIEW WRITING and USAGE EXAMPLE WRITING sections

- [ ] **Step 1: Add reminder to OVERVIEW WRITING section**

  **Find:**
  ```
  OVERVIEW WRITING:
  - [Component] State: what this component does + its role in the ECS system.
    Mention key relationships with other components (from Connected Files context).
  - [Data config] State: what static data this file defines, how it is structured,
    and how other systems access it via require(). Do NOT describe it as a component
    or reference the ECS system.
  - 2-5 sentences. No padding.
  ```

  **Replace with:**
  ```
  OVERVIEW WRITING:
  (As classified above — see FILE TYPE CLASSIFICATION.)
  - [Component] State: what this component does + its role in the ECS system.
    Mention key relationships with other components (from Connected Files context).
  - [Data config] State: what static data this file defines, how it is structured,
    and how other systems access it via require(). Do NOT describe it as a component
    or reference the ECS system.
  - 2-5 sentences. No padding.
  ```

- [ ] **Step 2: Add reminder to USAGE EXAMPLE WRITING section**

  **Find:**
  ```
  USAGE EXAMPLE WRITING:
  - [Component] Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.
  - [Data config] Show `require()` followed by index access to the returned table (e.g., `Table[1]`).
    Do NOT use `CreateEntity()`, `AddComponent`, or `inst.components`.
  - 5-15 lines. Use the component's actual function names from the documentation. No generic placeholder names.
  ```

  **Replace with:**
  ```
  USAGE EXAMPLE WRITING:
  (As classified above — see FILE TYPE CLASSIFICATION.)
  - [Component] Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.
  - [Data config] Show `require()` followed by index access to the returned table (e.g., `Table[1]`).
    Do NOT use `CreateEntity()`, `AddComponent`, or `inst.components`.
  - 5-15 lines. Use the component's actual function names from the documentation. No generic placeholder names.
  ```

- [ ] **Step 3: Verify both edits**

  Read OVERVIEW WRITING and USAGE EXAMPLE WRITING sections and confirm `(As classified above — see FILE TYPE CLASSIFICATION.)` appears at the start of each.

---

### Task 4: Rewrite `few_shot_data.md`

**Files:**
- Modify: `skills/few_shot_data.md`

- [ ] **Step 1: Add HOW TO DETECT header after the description line (line 4)**

  **Find:**
  ```
  === FEW-SHOT EXAMPLE (DATA CONFIG FILE) ===
  Use this structure when the source file defines a static data table with no constructor. Mirror this format only — do NOT copy the content.
  ```

  **Replace with:**
  ```
  === FEW-SHOT EXAMPLE (DATA CONFIG FILE) ===
  HOW TO DETECT: source file has NO Class() constructor, no self.inst,
  and returns a plain table/array at top level → use this example, NOT the component example.
  Use this structure when the source file defines a static data table with no constructor. Mirror this format only — do NOT copy the content.
  ```

- [ ] **Step 2: Update Usage example field names (platform → steam, numeric → psn)**

  **Find:**
  ```
  print(first.id.platform) -- "1_entry_alpha"
  print(first.id.numeric)  -- 1
  ```

  **Replace with:**
  ```
  print(first.id.steam) -- "1_entry_alpha"
  print(first.id.psn)   -- 1
  ```

- [ ] **Step 3: Update Properties table (platform → steam, numeric → psn)**

  **Find:**
  ```
  | `id.platform` | string | — | Platform string identifier, formatted as `<id>_<name>`. |
  | `id.numeric` | number | — | Platform numeric identifier from the platform definition file. |
  ```

  **Replace with:**
  ```
  | `id.steam` | string | — | Steam string identifier, formatted as `<id>_<name>` (e.g., `"1_entry_alpha"`). |
  | `id.psn` | number | — | PSN numeric ID from the platform definition file. |
  ```

- [ ] **Step 4: Update ENTRY() parameter description to show both platform behaviors explicitly**

  **Find:**
  ```
  *   **Parameters:**
      *   `id` (string or number) — base identifier; converted to string for the platform string field and kept as number for the numeric field.
      *   `name` (string) — internal name used in code.
  *   **Returns:** `{ name = name, id = { platform = tostring(id).."_"..name, numeric = id } }`
  ```

  **Replace with:**
  ```
  *   **Parameters:**
      *   `id` (string or number) — base identifier; stored as string for steam via `tostring(id).."_"..name` concatenation; kept as-is (number) for psn.
      *   `name` (string) — internal name used in code.
  *   **Returns:** `{ name = name, id = { steam = tostring(id).."_"..name, psn = id } }`
  ```

- [ ] **Step 5: Verify the full few_shot_data.md**

  Read the entire file and confirm:
  - HOW TO DETECT header is on line 4-5 (before Use this structure...)
  - Usage example uses `id.steam` and `id.psn`
  - Properties table has `id.steam` and `id.psn` rows
  - ENTRY() Returns shows `steam = tostring(id).."_"..name, psn = id`

---

### Task 5: Patch `docs_SKILL.md` inject_into for few_shot_data

**Files:**
- Modify: `docs_SKILL.md:22`

- [ ] **Step 1: Add merge_prompt to few_shot_data inject_into**

  **Find:**
  ```
  ## few_shot_data
  file: skills/few_shot_data.md
  inject_into: [single_prompt]
  ```

  **Replace with:**
  ```
  ## few_shot_data
  file: skills/few_shot_data.md
  inject_into: [single_prompt, merge_prompt]
  ```

- [ ] **Step 2: Verify the edit**

  Read `docs_SKILL.md` and confirm `few_shot_data` inject_into now contains both `single_prompt` and `merge_prompt`.

---

### Task 6: Commit skill file changes

- [ ] **Step 1: Commit**

  ```bash
  git add skills/quality_rules.md skills/few_shot_data.md docs_SKILL.md
  git commit -m "fix: strengthen data config file pattern in prompt skills

  - Add FILE TYPE CLASSIFICATION trigger to quality_rules.md
  - Upgrade DATA CONFIG FILE PROPERTIES to MUST/NEVER language
  - Add back-references in OVERVIEW WRITING and USAGE EXAMPLE WRITING
  - Add HOW TO DETECT header to few_shot_data.md
  - Update few_shot_data field names to steam/psn (matches DST codebase)
  - Clarify ENTRY() params to show tostring concat vs numeric passthrough
  - Add merge_prompt to few_shot_data inject scope"
  ```

---

## Chunk 2: Verification

### Task 7: Regenerate achievements.md and verify against success criteria

**Files:**
- Run against: `dst-scripts/achievements.lua`
- Output: `dst-api-webdocs/docs/achievements.md`

- [ ] **Step 1: Activate venv**

  ```bash
  .venv/Scripts/activate
  ```

- [ ] **Step 2: Check if main.py supports single-file targeting**

  Read `main.py` lines 1-60 to find if there is a `--file` arg or similar flag for targeting one file. If yes, use it. If no, note the full pipeline will run.

- [ ] **Step 3: Run generation for achievements.lua**

  If single-file flag exists:
  ```bash
  python main.py --file achievements.lua
  ```
  Otherwise run full pipeline and watch for achievements.lua output:
  ```bash
  python main.py
  ```

- [ ] **Step 4: Verify success criteria against generated `dst-api-webdocs/docs/achievements.md`**

  Check each criterion manually:

  **SC1 — Properties table has exactly 4 rows:**
  Open `dst-api-webdocs/docs/achievements.md` and confirm Properties section contains:
  - `Achievements` (container row)
  - `name`
  - `id.steam`
  - `id.psn`

  **SC2 — Usage example uses array index:**
  Confirm usage example contains `Achievements[1]`, NOT `achievements["survive_20"]` or any string key access.

  **SC3 — Overview has no ECS language:**
  Confirm Overview does NOT contain: `AddComponent`, `ECS`, `inst.components`, `entity` (in context of describing the file as an entity), or `component` used as a noun to describe the file itself (e.g., "this component manages...").

  **SC4 — ACHIEVEMENT() params show both behaviors:**
  Confirm Main functions section for `ACHIEVEMENT()` references BOTH:
  - `tostring(id)` or equivalent description of string concatenation for steam
  - numeric passthrough for psn

- [ ] **Step 5: Regression check — regenerate `health.lua`**

  Use `dst-api-webdocs/docs/components/health.md` as the regression target (confirmed `system_scope: entity` component). Regenerate it and confirm:
  - Properties table still uses constructor-sourced fields only (`self.` fields from the Class constructor)
  - No two-group container+record schema appears (that pattern is for data config only)
  - Overview still describes it as a component in the ECS system, not as a static data table

- [ ] **Step 6: Commit verified output**

  ```bash
  git add dst-api-webdocs/docs/achievements.md
  git commit -m "docs: regenerate achievements.md with fixed data config pattern"
  ```
