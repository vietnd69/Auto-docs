---
name: plan-pages
description: Rules for splitting large files and merging small ones into documentation pages.
---

# Planning pages

- `index_summary()` gives sizes; `plan_get(prefix=...)` lists pages; `validate_plan()` checks.
- A page should cover ≤ its `budget_tokens` of source. One giant symbol may exceed it.
- Split large code files by meaning (state groups, responsibility of methods), with an
  `overview` page at `<file>/index`. Give split pages descriptive titles, e.g.
  "SGwilson — Combat states" instead of "States (3/23)".
- Merge small data files of one directory into collection pages.
- Every public symbol must belong to exactly one page; `validate_plan` must report "plan valid".
- Change pages with `plan_put(page_json)` (full page JSON) or `plan_remove(page_id)`.
