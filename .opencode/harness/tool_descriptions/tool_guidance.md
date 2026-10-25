# Tool guidance (dst-tools)

| Need | Tool |
|---|---|
| What is in a file, how big each part is | `lua_outline(file)` |
| Body of one function/state/handler | `lua_symbol(file, qualname)` |
| More lines (large symbol) | `lua_read(file, from_line, to_line)` — repeat from the line it stopped at |
| Who calls X / where is X defined | `lua_refs(name)` / `lua_grep(pattern)` |
| APIs of required modules/components | `lua_deps(file)` |
| Shape of data tables or generated files | `lua_table_schema(file, table)` |
| What the page must contain | `page_checklist(page_id)` |
| Read / write the draft | `doc_read(page_id, heading)` / `doc_write_section(page_id, heading, markdown)` |
| Frontmatter description and tags | `doc_set_meta(page_id, description, tags)` |
| Deterministic problems | `run_checks(page_id)` |
| Final status | `verdict(page_id)` |
| Record / close review findings | `ledger_add(...)` / `ledger_resolve(...)` / `ledger_list(...)` |
| What changed between builds | `diff_overview(from, to)`, `symbol_diff(file, qualname, from, to)`, `patch_notes(build)` |
| Lessons from earlier jobs | `memory_search(domain, query)` |

Long files: never read a file top to bottom. Outline → pick symbols from the checklist →
read each symbol → write its section → note progress → next symbol.

Tool output is capped; when you see `…[truncated` or `…[stopped at`, continue with a narrower
call instead of repeating the same one.
