---
name: review-symbols
description: Evidence-based review of documented symbols against the Lua source; produces ledger findings.
---

# Reviewing symbols

For each symbol in your group:

1. `doc_read(page_id, "<its ### heading>")` and `lua_symbol(file, qualname)`.
2. Compare claim by claim: description, every parameter (name, type, meaning), return
   value, error states, events pushed/listened, tags, TUNING keys.
3. Report only **concrete contradictions or omissions** you can prove from source:
   `ledger_add(page_id, symbol, field, claim, file, line_start, line_end, quote)`
   - `field`: one of description, params, returns, errors, events, tags, example.
   - `quote`: copied verbatim from those lines (the tool verifies it).
   - `claim`: what is wrong and what the source shows, in one sentence.
4. Do not report style, wording or ordering. Do not report something already resolved
   unless the evidence is different.
5. When a group has no provable problem, report nothing — that is a valid outcome.


## Whole-page quality review

Review the entire page, including Properties, usage example and Events, not only function entries. Read relevant callers when claims depend on them. Verify cleanup conditions and server/platform preconditions in examples. Constructor defaults do not guarantee later mutable field types: document unguarded formatting/arithmetic failures. Record missing conditions as findings; they need not be outright contradictions. Component constructors belong in the Properties table, not a callable heading. Check every property type, default and consumer semantics, including clamping.
