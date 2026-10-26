# Runtime evidence and held-out skill evaluation

The final-review controller can now run fixed LuaJIT probes and attach verified
observations to review prompts. Enable `review_runtime_evidence = 1` in the
`[harness]` section of local `config.toml`. Probe failures stop before model dispatch.
The runtime artifact records the executable/probe hashes, version, source revision,
probe source and stdout. This proves standalone LuaJIT behavior, not in-game DST
behavior. Model-authored code is not executed by this mechanism.

## Real-model results

Source revision: `b729a8f68d4b635c21279e71723b9627f24c5c38` (build 759671).
All calls used native CLI subscriptions without API fallback.

| Experiment | Result |
|---|---|
| Counter repair, independent review | PASS; seven original findings resolved |
| Counter candidate blind replay without runtime evidence | Missed numeric-string `%g` behavior |
| Counter candidate replay with runtime evidence | Detected the previously missed numeric-string finding |
| Finiteuses baseline + runtime evidence, Sol medium | 13 open findings and three deterministic issues |
| Finiteuses candidate + runtime evidence, Sol medium | 15 open findings and three deterministic issues |
| Finiteuses repaired draft, Sonnet 5.5 high review | PASS; zero open findings and valid completion receipt |

The finiteuses A/B used identical input, model/effort and runtime probes. The
candidate tree was frozen from counter and was not tuned on finiteuses. The
imported older document's original metadata was preserved separately; changing
target metadata for the review was not treated as evidence of content correctness.

## Candidate quality remains inconclusive

Both skills detected the unbounded percentage and event-before-clamp defects.
The candidate added useful nil/false and inactive-branch checks, but failed to
retain two valid findings that the baseline recorded:

- The combat durability flag does not guard a configured ATTACK consumption path
  through `OnUsedAsItem`, despite the original document's broad claim.
- Without optional repair components, `SetMaxUses(false)` succeeds and later
  `GetDebugString` formatting fails. The candidate incorrectly rejected this
  setup by assuming the property watcher always performs a comparison.

Both cases were reproduced using the pinned Class and FiniteUses source with
minimal entity/action stubs. The independent component assertions were not shown
to the A/B reviewers. The final repaired document covers these cases correctly.
The original rejected finding remains preserved as historical evaluation evidence.

Candidate input usage was 477,845 tokens versus baseline 441,771, including cache,
about 8.2% higher. Findings are grouped differently between runs, so their raw count
is not a quality score. This single A/B does not establish a causal skill effect.
The candidate was not promoted, and generated documents were not published.

The held-out trial used five native sessions. Claude reported an API-equivalent
estimate of $0.28763445 for final review; this is not an actual subscription charge
and excludes any Codex price conversion. Actual subscription cost remains unknown.

## Validation and local artifacts

- Harness suite: 160 tests passed, including runtime injection and fail-closed cases.
- Runtime tests passed again with a hostile ambient `LUA_INIT` value, which is removed.
- Fixed language probes and component assertions passed on local LuaJIT.
- The final receipt was revalidated against source, draft, ledger and read coverage.

Reproduction drivers are `scripts/subscription_full_flow.py` and
`scripts/runtime_holdout_trial.py`. Their historical input checkpoints are local
trial artifacts, not bundled fixtures for a clean checkout. Native logs, account
usage, generated drafts and state under `outputs/` remain local and ignored.
Local reports are under `outputs/full-flow-20261027-counter/` and
`outputs/runtime-holdout-20261027-finiteuses/`.
