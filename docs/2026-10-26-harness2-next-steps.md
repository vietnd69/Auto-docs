# Harness²: follow-up diagnosis and next acceptance gates

## Evidence and scope

The second isolated trial is `outputs/harness2-trial-20261026-223406`.
Its conservative ledger total is USD 0.340300768. The final page passed current
checks, but the experiment was not fully successful: DOM fell back and the base
rollout exhausted its time limit. No paid API calls were made for this follow-up.

Do not use this single-page result as proof of full-codebase quality or savings.
Do not promote the candidate or enable the structural plan yet.

## Confirmed defect fixed: lost draft updates

`write_section` and `doc_set_meta` previously read and replaced a whole draft
without sharing a transaction. Separate MCP processes could both read the same
old file and discard each other's updates. A two-process regression reproduced
both section/section and section/metadata loss before the fix.

Draft reads, creation, section updates and metadata updates now share a reentrant
per-path transaction. A thread lock and OS file lock serialize cooperating MCP
processes. Writes use a closed temporary file followed by atomic replacement.
Persistent `.lock` files are intentional; removing them can split the lock domain.
External editors that do not acquire this lock are outside this guarantee.

The two reproductions pass after the fix. A third test verifies that a failed
replacement preserves the previous document and removes the temporary file.
This establishes the race defect; it does not prove that the race caused every
missing section in the saved model runs. Windows is tested; POSIX needs CI coverage.

## Controller-owned runtime evidence (implemented; design below)

Compose's saved rationale says all rollouts passed and none exhausted a budget,
which conflicts with the base rollout's persisted result. Intermediate tool
verdicts are not authoritative process-completion evidence.

Write a separate execution record containing process return code, timeout,
provider error, budget-stop reason and whether execution completed. Prepend a
small, whitelisted summary to the trajectory given to the proposer. Do not expose
hidden grader scores, findings or evaluation answers through this channel.
Old runs lacking these fields should say `unknown`, not infer success from a draft.

Acceptance: replay the saved interrupted base trajectory offline; its header must
identify interruption even if an earlier tool verdict passed. Test process error,
timeout, budget stop and missing execution records independently. Then verify a
future compose proposal uses that evidence; the runtime header alone cannot
guarantee that a model will interpret it correctly.

## Runtime-owned skill triggers (implemented for the bounded trial)

Upstream `autotrigger` appends new-skill triggers to `guardrails.md`, while the
trial validator freezes every file outside `skills/**/*.md`. Thus a legitimate
new skill can fail validation solely because its required trigger was generated.
The second DOM attempt also proposed a trigger edit and was rejected.

Keep the budget plugin and existing guardrails immutable. Have the runtime derive
canonical triggers from validated skill metadata. Permit exactly those generated
additions, not arbitrary model edits to guardrails. Tell the proposer to edit only
skills; let the runtime own trigger placement. If importing historical proposals,
normalize only explicitly recognized trigger additions and revalidate the result.

Acceptance: a new generic skill gets a canonical trigger; edits/removals of existing
guardrails and changes to the budget plugin still fail. Replay the saved DOM
proposal without modifying its original artifacts. Keep task-fact leakage checks.
This repair is now implemented in the bounded trial validator; see verification below.

## Quality direction: explicit claims and held-out cases

More prose regexes are insufficient for the remaining failures. Require critical
claims to carry source evidence and scope, and review them against a small curated
fixture set before spending on another optimization run:

| Case | Required evidence or behavior |
| --- | --- |
| Cleanup callback | State the current-platform and boatphysics preconditions |
| Usage example | Establish the entity/platform setup; do not silently demonstrate a no-op |
| Dynamic debug calls | Include dispatcher evidence; literal call-name search is insufficient |
| Numeric formatting | Distinguish numeric strings from invalid strings using LuaJIT checks |
| Dependency declarations | Recognize constructor globals even when formatted as bullets |
| Negative claims | Bound “no callers” to the searched revision and static-search limitations |

Separate these semantic cases from format/coverage checks. LuaJIT plus stubs can
verify local function behavior, but cannot establish full DST game integration.
Keep training pages separate from held-out pages, include more than one file type,
and evaluate candidates on the same cases with complete usage accounting.

The mechanical fixes now pass offline replay and regression tests. Next build the
semantic fixtures and held-out suite before another bounded paid trial. Measure completion, factual
errors, held-out regressions and cost per accepted page separately. Keep Claude
for unresolved evidence conflicts instead of routine drafting or retries.


## Implementation and verification update

The controller writes execution facts before evaluating document quality, resets
stale execution records at launch, and records launch exceptions without private
provider details. The adapter prepends only whitelisted runtime fields to the
trajectory. Legacy interrupted runs indicate non-completion with unknown cause;
legacy PASS results do not imply process completion.

The trial independently derives canonical triggers from frozen guardrails plus
candidate skill metadata. Only skill Markdown and those exact generated trigger
additions are accepted. Guardrail removals, arbitrary edits and budget-plugin
changes remain rejected. No vendor patch is needed for this change.

- Full harness suite: **116 passed** offline.
- Harness2/gateway suite: **12 passed, 3 subtests passed** offline.
- Ruff passed on all touched Python files.
- `scripts/replay_harness2_runtime.py` replays the second saved trial without APIs.
- Its base runtime header correctly identifies non-completion, cause unknown.
- Saved DOM attempt 2 passes validation after a checked migration: remove only
  its exact historical manual trigger and regenerate the canonical trigger.
  The original proposal remains unchanged, verified by hash.
- Artifacts: `outputs/harness2-offline-replay-20261026/report.json`,
  `base-runtime-header.txt`, and `normalized-dom/`.

API cost for this follow-up: USD 0. No model rerun, publication or promotion.
The normalized tree is for inspection, not an approved production candidate.
A future model run is still needed to verify compose follows the execution facts;
semantic fixtures and held-out evaluation remain outstanding.
