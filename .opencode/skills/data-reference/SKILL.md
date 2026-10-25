---
name: data-reference
description: Document data/config/generated Lua files by structure (schema, keys, samples), never by dumping data.
---

# Data reference pages

Data files (strings, skins, tuning, static layouts, generated registries) are too large to
list. Document their **shape**:

1. `lua_table_schema(file)` for every table listed in the checklist; for generated files it
   also reports the most repeated calls.
2. Write `## Structure` with one `###` entry per checklist table: what the table holds,
   key pattern, value kinds, nested fields (from "keys of nested tables"), 2–3 real samples
   in a code block.
3. `## Usage example`: how a mod reads or extends it (e.g. `STRINGS.NAMES.X = "..."`,
   `TUNING.X`), using real keys from the samples.
4. Never paste more than 15 lines of data.
