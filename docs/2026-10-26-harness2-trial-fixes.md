# Harness²: assessment and fixes after the bounded trial

The trial exposed false success reporting and an insufficient quality/promotion
gate. More tokens alone would not address those failures. No additional model API
requests were made while implementing these fixes.

## Changes

1. Proposer errors and missing final artifacts are failures even when an introductory
   response exists. Budget errors are not retried by the transport. Cached proposals
   from the old completion protocol are invalidated by a fingerprint version.
2. Rollout success requires the adapter's independent passing score, not an existing
   directory. Final mode success also requires successful final rollouts and no
   failed/fallback proposal stages. A skeleton is not a delivered DST document.
3. Page checks catch class-method references without parentheses, direct unguarded
   numeric-format contracts falsely saying no errors, overbroad rejection of numeric
   strings, and explicit claims of no external dependencies despite a global Class
   constructor. These checks cover bounded source patterns, not arbitrary Lua semantics.
4. Runtime errors/timeouts/budget exhaustion override a clean draft and prevent
   publication. They do not trigger a further paid reflector session.
5. Promotion compares the same set of at least two pages, requires all candidate
   pages to pass with zero issues, rejects unknown/increased cost, and requires a
   strict improvement. Cost estimates read all assistant agents in an isolated
   OpenCode database. Candidate evaluation leaves the live tree untouched; failed
   installation restores it.
6. The trial stops new phases after a budget rejection, reuses unchanged successful
   trees, prevents stale-code resume, preserves the budget plugin, and rejects
   training-source facts newly embedded in shared skills.

## Verification

- Main harness suite: 107 tests passed.
- Separate Harness²/gateway regression tests cover error-with-text responses,
  failed final rollouts, skeleton delivery, budget persistence and skill overfitting.
- Ruff passed. Vendor fixes are saved as reproducible setup patches, not just edits
  in the ignored checkout.
- Offline replay of the saved INV document now reports PHANTOM, ERROR_CONTRACT,
  and DEPENDENCY_CONTRACT. Baseline/DOM also expose their numeric-string wording
  issue. The original trial artifacts remain unchanged.
- A separate reviewed baseline corrects that wording and passes current checks:
  `outputs/harness2-trial-20261026-213614/docs-reviewed/components/boatdrag.md`.
  Replay results are in `revalidation-after-fix.json` beside the original trial.

## Remaining limits

No new paid generation loop was run after the fixes. The prior usage ledger remains
334 requests / USD 0.418616126 conservative total including its unsettled reservation.
The experiment used one small component; it does not establish generalization across
the codebase. Multiple regression pages are required for promotion, but a separate
held-out dataset is still needed to measure generalization. The main structural plan
is still deliberately non-executable, and normal CLI escalation was not established
end to end by this isolated trial. No candidate was promoted or published.
