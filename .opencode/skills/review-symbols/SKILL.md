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
