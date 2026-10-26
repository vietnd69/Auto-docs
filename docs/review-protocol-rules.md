## Review completion and Lua claim discipline

- Use the exact canonical page_id from the mission for every page tool. A job ID,
  filename or underscore-encoded path is not a page ID. Use the registered
  `dst-tools_` tool names.
- In final review, read the full current draft with `doc_read` and every listed
  source file with `lua_read`, continuing after truncation. Omit `rev` to use the
  pinned source. Outlines and grep locate code; they do not replace reading it.
  Review completion requires successful reads recorded for this exact job and
  draft. Failed tool calls do not count. Obey any coverage gaps from review_finish.
- Compare every documented operation, error claim, property and example with the
  implementation. Substitute defaults into worked examples, including omitted
  arguments, false values and boundary branches. Do not infer a result from a
  method name alone.
- Distinguish reading an absent table key from assigning to an invalid key.
  Trace `or` fallbacks before predicting arithmetic. Numeric string coercion
  depends on the actual Lua runtime and operation; avoid blanket type-error claims.
  A matching source quote proves the quote exists, not that your interpretation is correct.
- Batch concrete findings with exact source ranges; do not fabricate findings to
  show activity. Re-read the current draft before closing a finding. Reject a false
  positive with a specific source-backed explanation, rather than rewriting correct docs.
- Read-only final review records remaining defects and stops for repair. Call
  review_finish only after full comparison and clean findings/checks. Its summary
  must state checked behavior and limitations. Read coverage is necessary evidence,
  not a guarantee that the review is semantically correct.
