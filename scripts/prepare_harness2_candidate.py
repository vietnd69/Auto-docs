"""Prepare an isolated, manually corrected candidate and pinned held-out evaluation plan.

No model calls, publication, or live skill installation.
"""
import hashlib
import json
import shutil
import subprocess

from harness2_budget_trial import ROOT, DstAdapter, tree

SHA = 'b729a8f68d4b635c21279e71723b9627f24c5c38'
ORIGINAL = ROOT / 'outputs/harness2-trial-20261026-232322'
TARGET = ROOT / 'outputs/harness2-trial-20261027-reviewed-candidate'


def replace_once(text, old, new):
    if text.count(old) != 1:
        raise ValueError('Expected exactly one original rule: ' + old[:70])
    return text.replace(old, new, 1)


def main():
    from dst_bench.adapter import (
        validate_skill_generalization,
        validate_skill_only_tree,
    )
    from harness.config import Settings, load_settings
    from harness.ledger import Ledger
    from harness.plan import DocPlan, Page, SourceRef, load_plan, save_plan
    from harness.verdict import evaluate
    from harness.workspace import make_workspace

    from harness import checkpoint

    surface = DstAdapter().substrate.surface()
    live = tree.read_tree(surface, ROOT / '.opencode/harness')
    base = tree.read_tree(surface, ORIGINAL / 'experiment/harnesses/base')
    candidate = tree.read_tree(surface, ORIGINAL / 'experiment/harnesses/c1')
    source_fingerprint = hashlib.sha256(json.dumps(candidate, sort_keys=True).encode()).hexdigest()
    guide = candidate['skills/writing-guide/SKILL.md']
    guide = replace_once(guide,
        '- [Component] Show realistic Lua: `CreateEntity()`, `AddComponent`, then call 2-3 primary functions.',
        '- [Component] Show a realistic operation supported by this component. Use an existing entity when '
        'its lifecycle, platform, world or server state matters; state how it was prepared. Use '
        '`CreateEntity()` only when the example supplies the required setup. Do not invent extra method '
        'calls for passive components. Declare every non-engine variable or state its precondition.')
    guide = replace_once(guide, '- 5-15 lines. Use a fenced code block with `lua` syntax highlighting.',
        '- Prefer 5-15 lines, but retain necessary setup and guards. Use a fenced `lua` code block.')
    guide = replace_once(guide,
        'A file too small to carry much behaviour (a 19-line component whose only method is a debug\nstring, a passive record, a one-flag helper)',
        'A file that mainly stores state (a passive record or a small configuration helper)')
    start = guide.index('- **Name the operators exactly.**')
    end = guide.index('## Events & Listeners Section', start)
    guide = guide[:start] + '''- **Describe operations accurately.** Distinguish sums, products, clamping and conditional updates.
  Explain a boundary value only when the source supports it; include relevant assumptions about
  other inputs. Entity references and flags do not need invented numeric examples.
- **Separate attachment from activation.** A caller that adds/configures a component does not
  prove that its effects are registered or activated. Cite each path independently. Bound negative
  search conclusions to the inspected revision and scope; allow unresolved dynamic dispatch.
- **Registration pairs.** Inspect the exact add/remove implementation and all side effects.
  Explain identity keys, guards and cleanup preconditions. A plain Lua table assignment of nil
  removes a key, but do not assume all registries use that representation or all consumers use pairs.
- **No oversell.** Attribute interpreted effects to their actual consumer. Distinguish a stored
  default from a value assigned by a caller and from a runtime-computed value.

For each property, record type and constructor initialization (or absence of initialization).
Describe an evidenced reader or writer when found. If none is found, state the bounded search
result or uncertainty instead of fabricating a caller or effect. A constructor-only reference
can be documented as such; a caller-assigned value is optional evidence, not a required field.

''' + guide[end:]
    guide = replace_once(guide,
        '- If there are no events, listeners, or worldstate watchers, omit this entire section.',
        '- Keep every section required by page_checklist, including Events & listeners. If the source '
        'has no own event behavior, say so. Distinguish consumer-owned listeners from listeners '
        'registered by this component. Omit a section only when the page checklist does not require it.')
    candidate['skills/writing-guide/SKILL.md'] = guide
    review = candidate['skills/review-symbols/SKILL.md']
    review = replace_once(review,
        'Record a finding only when the\nsource contradicts the text; if the text is right, reply "claim holds" with the line range.',
        'Record a finding for a concrete contradiction or an evidenced omission, including missing\n'
        'setup, activation or cleanup conditions. If the text is right and complete for the claim,\n'
        'reply "claim holds" with the line range. Re-read the current draft before closing an old\n'
        'finding; cite the repaired behavior rather than relying on the prior session summary.')
    candidate['skills/review-symbols/SKILL.md'] = review
    workflow = candidate['skills/doc-job/SKILL.md']
    workflow = replace_once(workflow,
        'A focused follow-up re-check (see `review-symbols`) is a `review:` task, not a\n'
        '`repair:` round, so a single suspicious claim does not consume the repair budget.',
        'A focused follow-up re-check is a `review:` task rather than a `repair:` task, but it still\n'
        'consumes time, tokens and the shared monetary budget. Batch related claims into one focused\n'
        'review and avoid reopening completed work. If review cannot finish in the remaining time,\n'
        'save notes naming open finding IDs and repaired sections for checkpoint continuation.')
    workflow += '''
## Review continuation

When the controller requests resume-review, read the saved draft, ledger and notes first.
Skip outlining and first-draft delegation. Recheck each open finding against the current text
and pinned source; resolve only with evidence, and repair only a demonstrated remaining defect.
Finish with checks and verdict. A timed-out session is not a quality PASS, even after repairs.
'''
    candidate['skills/doc-job/SKILL.md'] = workflow
    validate_skill_generalization(candidate, base, ['components/boatdrag.lua'])
    validate_skill_only_tree(candidate, base, surface)
    tree.write_tree(surface, candidate, TARGET / 'harness')

    state = TARGET / 'state'
    for folder in ('drafts', 'ledger', 'notes'):
        source = ORIGINAL / 'rollouts/c1/state' / folder
        if source.exists():
            shutil.copytree(source, state / folder, dirs_exist_ok=True)
    shutil.copyfile(ORIGINAL / 'rollouts/c1/state/doc-plan.json', state / 'doc-plan.json')
    doc = state / 'drafts/components/boatdrag.md'
    text = doc.read_text(encoding='utf-8')
    old = "An owning entity (an anchor, a winch, a crabking claw) is passed to the boat's `boatphysics` component with `boat.components.boatphysics:AddBoatDrag(inst)`, which stores that entity's `boatdrag` component in `boatphysics.boatdraginstances`."
    new = "Anchor and winch code register an owning entity with the boat's `boatphysics` using `boat.components.boatphysics:AddBoatDrag(inst)`, which stores that entity's `boatdrag` component in `boatphysics.boatdraginstances`. The crabking claw prefab also attaches and configures `boatdrag`; that attachment alone does not establish a registration path."
    text = replace_once(text, old, new)
    text = replace_once(text, 'All reading of these fields happens in `boatphysics`.',
        '`boatphysics` interprets these fields for movement; `GetDebugString` also reads three of them for diagnostics.')
    doc.write_text(text, encoding='utf-8')
    audit = TARGET / 'source-audit'
    shutil.copytree(ORIGINAL / 'source-audit', audit, dirs_exist_ok=True)
    logs = []
    for script in ('check.lua', 'cleanup-check.lua', 'final-example-check.lua'):
        result = subprocess.run(['luajit', script], cwd=audit, text=True, capture_output=True, check=True)
        logs.append(result.stdout.strip())
    (audit / 'result.txt').write_text('\n'.join(logs) + '\n', encoding='utf-8')
    cfg = load_settings()
    ws = make_workspace(Settings(ROOT, dict(cfg.values, state_dir=str(state),
        scripts_dir='D:/code/dst-scripts', docs_dir=str(TARGET / 'docs'), baseline_sha=SHA,
        baseline_build='759671')), SHA)
    ledger = Ledger(ws, 'components/boatdrag')
    finding = ledger.items['f1d0e0ac6c']
    if ledger.verify_evidence(finding.evidence):
        raise ValueError('Original finding evidence no longer matches pinned source')
    ledger.resolve('f1d0e0ac6c', 'Manual review of copied candidate: current Usage example has an explicit '
        'platform precondition and mutually exclusive lowered/raised branches, matching anchor.lua:145-157. '
        'Exact example passes source-audit/final-example-check.lua under LuaJIT with stub platform: '
        'add once, repeated lowering no-op, raise removes once. Not full-game validation.')
    plan = load_plan(ws.plan_path)
    verdict = evaluate(ws, plan, plan.page('components/boatdrag'))
    if verdict.status != 'PASS':
        raise ValueError(verdict.render())
    output_doc = TARGET / 'docs/components/boatdrag.md'
    output_doc.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(doc, output_doc)
    checkpoint.save_checkpoint(ws, 'components/boatdrag', TARGET / 'harness', 'manual-offline-review')

    specs = [
        ('components/counter', 'Counter', 'components', 'api', ['nil/default vs zero; Set/Clear/DoDelta', 'DoNotSave filtering and empty OnSave', 'no fabricated external caller required']),
        ('components/savedrotation', 'SavedRotation', 'components', 'api', ['Transform precondition', 'zero rotation returns nil', 'LoadPostPass and delayed rotation; no invented initialized flag']),
        ('components/timer', 'Timer', 'components', 'api', ['duplicate StartTimer is a guarded no-op', 'StopTimer vs completion timerdone payload', 'pause/resume/cancellation lifecycle']),
        ('prefabs/boards', 'Boards', 'prefabs', 'api', ['network setup before client return', 'server-only component attachment', 'SpawnPrefab example rather than fabricated ECS methods']),
    ]
    pages = [Page(pid, pid+'.md', title, domain, kind, [domain], [SourceRef(pid+'.lua')])
             for pid,title,domain,kind,_ in specs]
    holdout = DocPlan({'build':'759671','sha':SHA}, pages)
    save_plan(holdout, TARGET / 'holdout/doc-plan.json')
    checks = []
    for pid,_,_,_,expectations in specs:
        source = ws.git.show(SHA,pid+'.lua')
        dest = TARGET / 'holdout/evaluator-only/source' / (pid+'.lua')
        dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(source,encoding='utf-8')
        checks.append({'page_id':pid, 'source':pid+'.lua',
            'source_sha256':hashlib.sha256(source.encode()).hexdigest(),
            'acceptance':expectations, 'generated_docs_status':'NOT_RUN'})
    (TARGET/'holdout/evaluator-only/criteria.json').write_text(json.dumps(checks,indent=2),encoding='utf-8')
    evaluator = TARGET / 'holdout/evaluator-only'
    shutil.copyfile(ROOT / 'scripts/fixtures/harness2-holdout/source-contracts.lua', evaluator / 'source-contracts.lua')
    oracle = subprocess.run(['luajit', 'source-contracts.lua'], cwd=evaluator,
                            text=True, capture_output=True, check=True)
    (evaluator / 'source-contracts-result.txt').write_text(oracle.stdout, encoding='utf-8')
    prefab = (evaluator / 'source/prefabs/boards.lua').read_text(encoding='utf-8')
    assert prefab.index('inst.entity:SetPristine()') < prefab.index('if not TheWorld.ismastersim then')
    client_guard = prefab.index('if not TheWorld.ismastersim then')
    assert prefab.index('return inst', client_guard) < prefab.index('inst:AddComponent("edible")')
    assert 'return Prefab("boards", fn, assets)' in prefab
    (evaluator / 'prefab-static-result.txt').write_text(
        'PASS: pristine before client guard, client returns before edible attachment, boards Prefab export. '
        'Static source checks only; not full engine execution.\n', encoding='utf-8')
    assert not {p.id for p in pages} & {'components/boatdrag'}
    assert tree.read_tree(surface,ROOT/'.opencode/harness') == live
    assert hashlib.sha256(json.dumps(tree.read_tree(surface,ORIGINAL/'experiment/harnesses/c1'),sort_keys=True).encode()).hexdigest() == source_fingerprint
    original_ledger = (ORIGINAL / 'rollouts/c1/state/ledger/components__boatdrag.jsonl').read_text(encoding='utf-8')
    assert json.loads(original_ledger.strip())["status"] == "open"
    assert json.loads((ORIGINAL / 'rollouts/c1/result.json').read_text())["execution"]["reason"] == "timeout"
    result = {'api_cost_usd':0,'manual_candidate_verdict':verdict.status,'original_trial_status':'timeout, unchanged',
        'original_finding_unchanged':True,'copied_finding_status':Ledger(ws,'components/boatdrag').items['f1d0e0ac6c'].status,
        'skill_validation':'PASS','holdout_pages':len(pages),'holdout_generation':'NOT_RUN','promoted':False,
        'candidate_tree_sha256':hashlib.sha256(json.dumps(candidate,sort_keys=True).encode()).hexdigest()}
    (TARGET/'validation.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result,indent=2))
    print(TARGET)


if __name__ == '__main__':
    main()
