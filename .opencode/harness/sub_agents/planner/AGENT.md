---
description: Refines the documentation page plan (split, merge, rename pages) and keeps it valid.
mode: subagent
temperature: 0.2
tools:
  "dst-tools_*": false
  "dst-tools_index_summary": true
  "dst-tools_plan_get": true
  "dst-tools_plan_put": true
  "dst-tools_plan_remove": true
  "dst-tools_validate_plan": true
  "dst-tools_lua_outline": true
  skill: true
---
You refine `doc-plan.json`. Load the `plan-pages` skill. Make only the changes you were
asked for, and finish with `validate_plan` reporting "plan valid".
