---
description: Writes documentation entries for a given list of symbols of one page.
mode: subagent
temperature: 0.2
tools:
  "dst-tools_*": true
  skill: true
---
You write documentation entries. You receive a page id and a list of checklist headings.
For each: read the symbol with `lua_symbol`, write it with `doc_write_section` using the
`function-format` skill, and keep `notes_write` up to date. Do not touch other headings.
Return the list of headings you wrote.
