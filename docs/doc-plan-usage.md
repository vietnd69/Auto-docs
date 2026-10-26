# Structural doc plan

The active structural proposal is `.harness/doc-plan.json`; counts and integrity checks
are recorded in `.harness/doc-plan-summary.json`. It is pinned to build 759671, commit
`b729a8f68d4b635c21279e71723b9627f24c5c38`.

The existing `baseline` and `pages` schema is preserved. The new `structure` block holds
page types, candidate source objects, work units, file dispositions, review requirements
and unresolved execution dependencies. `load_plan` / `save_plan` preserve this block.

`pages[].sources[].symbols` is ownership of symbols understood by the current parser.
`structure.pages[page_id].signals` is evidence for additional candidates, not proof of
exported API coverage. Symbol-name responsibility groups require semantic verification.
Overview/guide/system pages reference sources without owning their API symbols.

Logical page budgets are source estimates; work units have separate 4000-source-token
and eight-symbol targets. Oversized atomic symbols are marked `needs_range_split`, not
silently claimed to fit. Actual request/output/tool budgets still need executor support.

The proposal has `execution_ready: false`. Generate, update and run-job paths reject it
before model calls or publishing. Do not flip this flag until the listed blockers have
been implemented and the pilot has passed. No model calls were made to create this plan.

Regenerate a candidate without overwriting the active plan:

```powershell
.venv/Scripts/python.exe -m harness.structureplan --source D:/code/dst-scripts --output .cache/structure-plan/doc-plan.json
```

The source checkout must contain the pinned commit; its working-tree HEAD need not match.
The command reads Git objects and never checks out or resets the source repository.
The previous active plan is backed up under `.harness/backups/`; the exact path and hash
are in the summary. Published docs and sync-state were not migrated by this operation.

Validation: 92 harness tests pass; Ruff check and format check pass. The full plan has
zero current-validator issues, exact work-unit ownership for parser symbols and a file
disposition for all 4084 Lua files. This does not validate unresolved object semantics.
Mypy was unavailable in the current environment and was not run successfully.
