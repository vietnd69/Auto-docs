"""Offline replay of saved runtime evidence and DOM skill validation; no API calls."""
import hashlib
import json

from harness2_budget_trial import ROOT, DstAdapter, tree


def main():
    from dst_bench.adapter import (
        execution_header,
        validate_skill_generalization,
        validate_skill_only_tree,
    )

    trial = ROOT / 'outputs/harness2-trial-20261026-223406'
    surface = DstAdapter().substrate.surface()
    base = tree.read_tree(surface, trial / 'experiment/harnesses/base')
    proposal_path = trial / 'proposals-fixed/dom1.a2.45e4be33c966babe.workspace'
    proposal = tree.read_tree(surface, proposal_path)
    original_hash = hashlib.sha256(json.dumps(proposal, sort_keys=True).encode()).hexdigest()
    # The historical proposal manually inserted this exact trigger. Strip only
    # that recognized migration edit before asking runtime to regenerate it.
    historical = '- When documenting a component file (`components/*.lua`), load the `component-contract` skill before writing Overview, Usage example or Properties.'
    guard = proposal['guardrails.md']
    assert guard.count(historical) == 1
    normalized = '\n'.join(line for line in guard.splitlines() if line != historical)
    assert normalized.rstrip() == base['guardrails.md'].rstrip(), 'Unexpected guardrail edit'
    candidate = dict(proposal)
    candidate['guardrails.md'] = base['guardrails.md']
    validate_skill_generalization(candidate, base, ['components/boatdrag.lua'])
    validate_skill_only_tree(candidate, base, surface)
    assert '`component-contract` skill' in candidate['guardrails.md']
    after = tree.read_tree(surface, proposal_path)
    assert hashlib.sha256(json.dumps(after, sort_keys=True).encode()).hexdigest() == original_hash
    destination = ROOT / 'outputs/harness2-offline-replay-20261026'
    destination.mkdir(parents=True, exist_ok=True)
    tree.write_tree(surface, candidate, destination / 'normalized-dom')
    header = execution_header(trial / 'rollouts/base')
    assert '"completed": false' in header
    assert 'legacy_interruption_cause_unknown' in header
    (destination / 'base-runtime-header.txt').write_text(header, encoding='utf-8')
    report = {
        'api_cost_usd': 0,
        'legacy_base_completion': False,
        'legacy_base_cause': 'unknown (old artifact lacks execution fields)',
        'dom_skill_validation': 'PASS after explicit historical trigger migration',
        'migration': 'removed only the recognized manual trigger; regenerated canonical trigger',
        'original_proposal_unchanged': True,
        'original_proposal_sha256': original_hash,
        'limits': 'Offline validation only; no model rerun, quality approval or promotion.',
    }
    (destination / 'report.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps(report, indent=2))


if __name__ == '__main__':
    main()
