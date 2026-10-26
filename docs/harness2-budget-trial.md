# Bounded Harness² skill trial

Run from the repository root after installing the pinned `harness2-dst` dependencies:

```powershell
.venv/Scripts/python.exe scripts/test_harness2_budget_trial.py
.venv/Scripts/python.exe scripts/harness2_budget_trial.py
```

Each invocation is a **new paid experiment** with a USD 0.45 internal cap; do not
rerun to resume a user-authorized USD 0.50 experiment without counting the previous
invocation's spend. To continue an interrupted experiment with the same ledger and
reuse completed rollouts, pass `--resume outputs/harness2-trial-<timestamp>`.
Unsettled request reservations remain charged. Output lives in a new `outputs/harness2-trial-<timestamp>/`
directory. Existing docs, the structural doc-plan, and live skills are not promoted
or published by this script.

The experiment runs the pinned upstream sequential recursion at `k=1`: one baseline,
invariant and domain proposals with their rollouts, then a composition proposal and
rollout. Proposals use the installed native OpenCode executable on Windows. Only
skill Markdown changes are accepted. The single task is `components/boatdrag` at
source revision `b729a8f68d4b635c21279e71723b9627f24c5c38` (build 759671).

All experiment model requests share a serial localhost gateway. It reserves an
uncached input/output upper estimate before sending each request, persists that
reservation, then settles from provider usage. Unknown usage and transport errors
retain the reservation. Requests exceeding the remaining cap are rejected before
network IO. DeepSeek accounting uses peak rates; Ollama credit usage is counted
even if covered by free credits. The gateway only accepts DeepSeek Flash and the
reviewer/planner/reflector aliases. Claude and other providers are disabled.

`usage.json` is the authoritative cost ledger. `experiment.json` records actual
upstream stage errors, fallback and changed/unchanged proposals. `summary.json`
contains deterministic checks; `docs/<rollout>/` contains independent outputs.
Inspect proposal diffs and source correctness separately: PASS alone is not evidence
of semantic improvement, and one page does not establish cross-codebase quality.

This runner supplies isolated plan/state and native proposer execution explicitly.
It does not establish that the normal CLI escalation or automatic promotion path
works, and intentionally does not exercise the separate post-job reflector.

The Windows tree-path fix is shipped as `0002-normalize-windows-tree-paths.patch`.
The native proposer rejects error events/nonzero exits even when introductory prose
exists, and requires its final `output/answer.md`. The initial experiment exposed
this false-success condition; the stricter completion check was subsequently
verified offline, without spending more on another model run.

After the trial hardening:

- A budget rejection is persisted and stops subsequent proposer/rollout launches.
- Identical successful skill trees reuse their completed rollout; `rollout_sources`
  identifies reuse. This saves calls but is not an independent quality sample.
- Resume requires an unchanged runner/checker code fingerprint. Older trials without
  `execution-version.json` remain readable evidence, but cannot reuse obsolete PASS
  results through `--resume`.
- Shared skills reject newly added training-page source anchors; the budget plugin
  is immutable. This is a bounded overfitting guard, not a proof of generalization.
- Promotion requires at least two matching pages, all candidate pages passing,
  complete isolated-session cost estimates, no increased cost, and strict improvement.
  All assistant agents count toward estimated cost. Unknown models or incomplete
  usage reject promotion instead of counting as zero. Rates are pinned in
  `harness/usage.py` and must be maintained when provider pricing/routing changes.
- Candidate evaluation does not replace live skills. Failed installation restores
  the previous tree. Runtime errors/budget exhaustion override a superficially clean
  draft and prevent publishing.

The structural plan still has `execution_ready: false`. These changes do not make
that plan executable or establish a paid end-to-end result for the normal CLI
escalation path. Use the trial report and offline revalidation for the tested scope.


## Continue final review after timeout

New page runs save checkpoints in their isolated state reports. Each attempt keeps
its own draft, ledger, execution record and session events. `run-page --resume-review`
validates the pinned source, plan, draft, ledger and skill tree before any model call,
then requests review of the existing page instead of starting the generation workflow.
A fresh attempt ID preserves prior logs and avoids inheriting an old step-limit marker.
The prompt requests source-backed closure of already-repaired findings and local
repairs for remaining defects. This is a targeted model workflow, not a guarantee
that a model will never rewrite a section. Final PASS still requires clean checks,
closed findings and a completed session.

For a bounded paid experiment, use the trial gateway, **not a direct CLI resume**:

```powershell
.venv/Scripts/python.exe scripts/harness2_budget_trial.py --resume-review outputs/harness2-trial-20261026-232322
```

This command makes paid requests if the existing shared cap admits them. It imports
only the timed-out c1 page into a separate `review-<timestamp>/state` directory,
checks source/candidate identity, and continues final review with the original
`usage.json` and USD 0.45 cap. It does not rerun baseline, INV, DOM or compose.
Original trial result/docs are preserved; review results are separate and do not
retroactively change `experiment.ok`. Each invocation starts from the original c1
snapshot; resuming a subsequently interrupted review snapshot is not yet exposed
through this trial command.

Legacy c1 trials without checkpoints can be imported only after source SHA and
installed-candidate identity checks. Trials that have checkpoints also require
matching fingerprints. Changed runner code is recorded for the review attempt;
old quality scores are never reused to infer review success. This is intentionally
separate from full experiment `--resume`, which still requires an identical code
fingerprint.

Do not reset or discard unsettled reservations. The last trial's conservative
USD 0.44073202 leaves only USD 0.00926798 under the internal cap; a review request
may be rejected before network IO. A new funding allowance must not be inferred
from the availability of this resume command.

Offline validation after implementation: 7 checkpoint tests cover draft reuse,
immutable prior evidence, changed/missing state rejection and preserving open
findings. The gateway test confirms previous settled spend and pending reservations
still count on review continuation. An offline import of the saved c1 is recorded in
`outputs/harness2-trial-20261026-232322/review-20261026-235436/offline-replay.json`.
No paid review continuation was launched during implementation.


## Bounded final review update — 2026-10-27

This supersedes the earlier description of resume-review as a workflow that may
repair sections. Resume-review now uses the reviewer directly, in primary mode,
with **120 seconds and 24 tool calls** by default (`final_review_seconds` and
`final_review_steps`), additionally bounded by the job's overall limits.

The final reviewer cannot delegate or rewrite docs. It can read evidence, record
findings, resolve already-repaired findings, and save notes. Remaining content
repairs require a separate repair step; the review does not hide them to force PASS.
It must call `review_finish(page_id, summary)` on a clean page and then stop.
A receipt binds the job, source SHA, draft hash and ledger hash. A normal process
exit without a valid current receipt is `REVIEW_INCOMPLETE`; timeout still overrides
any receipt. This establishes explicit completion, not proof of every factual claim.

For a paired holdout rollout, the existing shared budget can be reused explicitly:

```powershell
.venv/Scripts/python.exe scripts/harness2_budget_trial.py --resume-review outputs/harness2-trial-20261027-000934 prefabs__boards-candidate
```

This is a paid command if the ledger admits a request. It copies only the selected
timed-out rollout and its original frozen harness, validates identity/checkpoint,
and preserves the original results. No new cap or ledger is created. This command
was **not** executed with model calls during implementation; only its import path
was replayed offline.

Generic deterministic checks now catch the exact unguarded deferred Transform
callback paired with “Error states: None”, and literal SetPosition(x, y, z) examples
with no other mention/setup of x/y/z in the Usage section. These are narrow patterns,
not general Lua semantic analysis. Source-pinned regression cases separately cover
the observed boards repair-item/target confusion and savedrotation caller confusion.
They live in `harness/semantic_cases.py`, not in reusable skills, and deliberately
apply only to the audited revision. These pages are now seen regression cases;
use fresh pages for subsequent generalization claims.

Replay evidence and manually corrected copies:
`outputs/harness2-trial-20261027-bounded-review/replay.json` and `docs-reviewed/`.
The four original drafts now each expose their known defect; corrected copies pass
checks. Original trial statuses, docs, skills and usage remain unchanged. No skill
promotion or completed live final-review result is claimed by these offline tests.

### Ledger transactions and review coverage (2026-10-27)

Ledger mutations now lock the full read/modify/write transaction across threads
and processes, reload inside the lock, and atomically replace the file. Corrupt
records remain untouched and produce a structured `LEDGER_CORRUPT` failing verdict.
There is no automatic dropping of damaged findings or automatic recovery/promotion.

Final-review receipts require a successful full draft read and all source lines
returned by `lua_read`/`lua_symbol` at the pinned revision, scoped to the current
job, draft hash and source list. Grep, outlines, failed reads and truncated partial
lines do not count. Changed drafts invalidate coverage. These checks prove source
exposure, not comprehension; independent semantic auditing remains necessary.

`--review-eval` freezes a candidate with generic rules from
`docs/review-protocol-rules.md`, reviews two corrected inputs, then generates the
previously observed counter regression case from scratch and final-reviews it.
All phases share the same $0.45 request gate within the user's $0.50 allowance.
This mode evaluates manual skill corrections; it does not run autonomous tuning.

Final review uses the dedicated `harness-final-review` agent, avoiding inherited
reviewer wildcard permissions that can hide source tools after OpenCode merges
configuration. The controller injects the frozen `review-symbols` skill into the
mission and records its SHA-256 under `reports/review-policy/`; loading the policy
does not depend on the model choosing to call the skill tool.

To continue a stopped evaluation without resetting its request ledger, use
`--review-eval AREA`. To re-review the preserved counter draft from a completed
retry without regenerating it, use `--review-existing AREA retry-HHMMSS`.
Both create separate attempt artifacts and retain prior results and reserved costs.
