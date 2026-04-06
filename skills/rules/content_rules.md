---
name: content_rules
description: Content accuracy, completeness, file type classification, properties table rules
inject_into: [analyst, analyst_chunk, analyst_merge, analyst_intermediate, analyst_merge_legacy, reviewer_full, reviewer_typed]
---

# Content Rules

## Content Accuracy

- All content must come ONLY from the source code or provided JSON. Do NOT invent APIs.
- Never repeat the same line or bullet point more than once.
- No greetings, sign-offs, meta-commentary, or filler text.
- No emojis or unicode symbols.

## File Type Classification

Determine before writing any section:
- DATA CONFIG FILE: no Class() constructor, no self.inst, returns a plain table/array.
  → MUST apply ALL [Data config] rules. Do NOT use [Component] patterns.
  → Consult the HOW TO DETECT note at the top of the data config few-shot example.
- COMPONENT FILE: has Class(function(self, ...) ... end) constructor.
  → MUST apply ALL [Component] rules. Do NOT use [Data config] patterns.

When signals are mixed (e.g., local helper functions that resemble constructors),
check: does the file's top-level return value contain a plain array/table, not a class instance?
If yes → DATA CONFIG FILE.

## Completeness

- Keep ALL functions — never drop trivial getters/setters.
- If a function appears in multiple chunks, prefer the entry with more parameter/return detail.
- Merge all events, dependencies, and tags; never drop an entry.
- If a field has no data, use "None" (string) or [] (empty array) — never omit the field.

## Short Files

- If source is small or simple, keep docs proportionally short.
- If a section has no content, write "Not applicable" or "None identified" — do not invent.
- Events & listeners may be omitted if the component has none.

## Properties Table

- Columns: Property | Type | Default Value | Description
- If no properties exist, the table MUST include a None data row:
  | None | | | No properties are defined. |
  Do NOT leave the table with header + separator only and no data rows — that is incorrect.
- Do NOT invent properties not in the constructor.

## Data Config File Properties

MUST document TWO groups of rows in this order:
  1. The top-level container variable (the returned global/local table).
  2. One row per key in each record entry (e.g., name, id.steam, id.psn).
NEVER document only the container and omit the record schema.
NEVER use a real default value for record fields — always write "---" (em dash).
NEVER write "nil" as a default — that is a real default value. Use "---" only.
Nested table fields accessed via dot notation (id.steam, id.psn) MUST each be
their own property row. Never collapse them into a single parent row (e.g., id).

## Data Config File Main Functions

Local factory/builder functions that construct record entries (e.g., ACHIEVEMENT(),
ENTRY()) MUST be documented in ## Main functions — they define the record schema
and are part of the data API. Do NOT treat them as internal implementation details
or skip them because they are local.

## Incomplete Function Handling

At chunk boundary: if a function body is cut off, keep it and note "INCOMPLETE — continues in adjacent chunk".
Do NOT skip or drop incomplete functions.
