---
name: doc-job
description: Step-by-step workflow for generating or updating one documentation page with dst-tools.
---

# Documentation job workflow

1. **Orient.** `notes_read(page_id)` (resume if work exists), `page_checklist(page_id)`,
   `memory_search(domain, "<page title> <kind>")`.
2. **Outline the sources.** `lua_outline(file)` for each source file. Never read whole files.
3. **Entries first.** For each unchecked checklist item, in order:
   - `lua_symbol(file, qualname)` (continue with `lua_read` if it was cut off);
   - `lua_refs` / `lua_deps` only if behaviour depends on another file;
   - write it with `doc_write_section(page_id, "<exact checklist heading>", body)` using the
     `function-format` skill; the tool places it under the right `##` section;
   - every 5 entries, `notes_write` the list of finished headings.
4. **Summary sections last.** From your notes and the outline (not from re-reading code)
   write `## Overview`, `## Usage example`, `## Dependencies & tags`, `## Properties` (if
   required) and `## Events & listeners`. Then `doc_set_meta(description, tags)`.
5. **Check.** `run_checks(page_id)`. Fix each issue in the section it names. Codes:
   `COVERAGE` missing heading · `SIGNATURE` wrong params · `PHANTOM` invented method ·
   `HEADINGS`/`EMPTY_SECTION` structure · `MDX_COMPILE` escape `{`, `}`, `<` outside code ·
   `LINKS` broken internal link · `FM_SCHEMA` frontmatter.
6. **Review.** For pages with more than 10 entries delegate to the `reviewer` subagent in
   groups of ≤10 symbols; otherwise load `review-symbols` and review yourself. Fix every
   open finding, then `ledger_resolve` it with a one-line note.
7. **Finish.** `verdict(page_id)`. PASS → stop. FAIL with nothing fixable → write the reason
   in the notes and stop. Never loop on the same failure more than twice.
