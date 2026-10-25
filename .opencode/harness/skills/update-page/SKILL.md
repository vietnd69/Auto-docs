---
name: update-page
description: Update an existing page after a source change, touching only affected sections.
---

# Updating a page after a build change

1. `impact_map(from_rev, to_rev)` shows which symbols of this page changed and how.
2. `patch_notes(<build>)` explains the intent of the change (Steam patch notes); use it to
   describe *why*, never as a source of API facts.
3. For each changed symbol:
   - `signature_changed` / `body_changed`: `symbol_diff(file, qualname, from, to)`, then
     rewrite only that entry with `doc_write_section`.
   - `added`: document it like a new entry (`function-format`).
   - `removed`: delete its entry by writing the parent section without it.
   - `renamed`: rename the heading to the new checklist heading and adjust the text.
4. Re-check summary sections (`Overview`, `Events & listeners`, `Dependencies & tags`)
   only if a change affects them.
5. `run_checks`, review only the changed symbols (`review-symbols`), then `verdict`.
