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
   write `## Overview`, `## Usage example`, `## Dependencies & tags`, `## Properties` (mandatory for API pages) and `## Events & listeners`. Then `doc_set_meta(description, tags)`.
5. **Check.** `run_checks(page_id)`. Fix each issue in the section it names. Codes:
   `COVERAGE` missing heading · `SIGNATURE` wrong params · `PHANTOM` invented method ·
   `HEADINGS`/`EMPTY_SECTION` structure · `MDX_COMPILE` escape `{`, `}`, `<` outside code ·
   `LINKS` broken internal link · `FM_SCHEMA` frontmatter.
6. **Review.** For pages with more than 10 entries delegate to the `reviewer` subagent in
   groups of ≤10 symbols; for smaller pages also delegate to `reviewer` (never self-review). Fix every
   open finding, then `ledger_resolve` it with a one-line note.
7. **Finish.** `verdict(page_id)`. PASS → stop. FAIL with nothing fixable → write the reason
   in the notes and stop. Never loop on the same failure more than twice.

## Role routing and repair budget

The orchestrator always delegates entries to `writer` (DeepSeek), and semantic review to
`reviewer` (Ollama gpt-oss:120b; DeepSeek fallback on quota). Run deterministic checks before semantic review. Use stable task
descriptions `write:<group>` for the first draft, `repair:<group>` for up to two repair
calls, and `escalate:<group>` for one final `writer-escalation` (Claude) call. Keep the
same group id for the same symbols across retries. Do not change group ids to bypass
the budget. After escalation, record remaining issues and stop. Beam is opt-in only.


## Whole-page quality review

Review the entire page, including Properties, usage example and Events, not only function entries. Read relevant callers when claims depend on them. Verify cleanup conditions and server/platform preconditions in examples. Constructor defaults do not guarantee later mutable field types: document unguarded formatting/arithmetic failures. Record missing conditions as findings; they need not be outright contradictions. Component constructors belong in the Properties table, not a callable heading. Check every property type, default and consumer semantics, including clamping.
