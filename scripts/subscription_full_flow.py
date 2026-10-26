"""Bounded single-document repair -> independent review -> Harness2 skill proposal/replay.

Uses native subscriptions only. This is a single-page experiment, not run_sequential
or evidence for production promotion. Every stage is resumable without repeating calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import sys
from datetime import datetime
from pathlib import Path

from harness.config import Settings, load_settings
from harness.jobqueue import Job
from harness.ledger import Evidence, Ledger
from harness.runner import run_page
from harness.workspace import make_workspace

from harness import checkpoint, session, subscription

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "harness2-dst/src"), str(ROOT / "harness2-dst/vendor/harness2")]
PAGE = "components/counter"
SHA = "b729a8f68d4b635c21279e71723b9627f24c5c38"
ORIGINAL = ROOT / "outputs/harness2-trial-20261027-011200"
INPUT = ORIGINAL / "policy-review-012727/state"
REVIEWS = [ROOT / "outputs/harness2-trial-20261027-014558-subscriptions/sol-medium/state",
           ROOT / "outputs/harness2-trial-20261027-015006-subscriptions/sonnet-high/state"]
SKILL = "skills/review-symbols/SKILL.md"


def save(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def workspace(area, name="work", backend="claude-code"):
    cfg = load_settings(ROOT)
    return make_workspace(Settings(ROOT, dict(cfg.values,
        state_dir=str(area / name / "state"), docs_dir=str(area / name / "docs"),
        scripts_dir="D:/code/dst-scripts", final_review_backend=backend,
        codex_subscription_model="gpt-6.1-sol", codex_subscription_effort="medium",
        claude_subscription_model="claude-sonnet-5-5", claude_subscription_effort="high",
        max_wall_minutes=5, final_review_seconds=300, reflect=0)), SHA)


def native(ws, label, mode, prompt, backend):
    job = Job(label, "resume-review" if mode == "proposal" else "repair", PAGE, to_rev=SHA)
    env = session.session_env(ws, job)
    env["HARNESS_NATIVE_MODE"] = mode
    if mode == "repair":
        env.pop("HARNESS_REVIEW_ONLY", None)
        env["HARNESS_REPAIR_PAGE"] = PAGE
    log = ws.report_path(f"sessions/{label}.jsonl")
    if log.exists():
        raise ValueError("Refusing to repeat a native call under the same job identity")
    print("START", label, backend, flush=True)
    result = subscription.run_review(ws, job, prompt, log, env, backend)
    usage = json.loads(log.with_suffix(".usage.json").read_text())
    print("END", label, "completed", usage["completed"], flush=True)
    if result.timed_out or result.returncode or not usage["completed"]:
        raise RuntimeError(f"{label}: native session incomplete; inspect preserved logs")
    return log, usage


def final_text(log):
    messages = []
    for line in log.with_suffix(".native.jsonl").read_text(encoding="utf-8").splitlines():
        event = json.loads(line)
        if event.get("type") == "result" and isinstance(event.get("result"), str):
            messages.append(event["result"])
        item = event.get("item", {})
        if event.get("type") == "item.completed" and item.get("type") == "agent_message":
            messages.append(item["text"])
    if not messages:
        raise ValueError("No final native response")
    return messages[-1]


def initialize(area):
    ws = workspace(area)
    if (area / "manifest.json").exists():
        return ws
    shutil.copytree(ORIGINAL / "retry-011514/harnesses/candidate", area / "baseline")
    for name in ("drafts", "ledger"):
        shutil.copytree(INPUT / name, ws.settings.state_dir / name)
    shutil.copyfile(INPUT / "doc-plan.json", ws.plan_path)
    ledger = Ledger(ws, PAGE)
    for source in REVIEWS:
        for line in (source / "ledger/components__counter.jsonl").read_text(encoding="utf-8").splitlines():
            finding = json.loads(line)
            if finding["status"] == "open":
                _, message = ledger.add(finding["symbol"], finding["field"], finding["claim"],
                                        Evidence(**finding["evidence"]))
                if ledger.verify_evidence(Evidence(**finding["evidence"])):
                    raise ValueError(message)
    shutil.copytree(ws.settings.state_dir, area / "input-state")
    save(area / "manifest.json", {"page": PAGE, "source_sha": SHA,
        "input_draft_sha256": digest(ws.draft_path(PAGE + ".md")),
        "input_reviews": [str(p) for p in REVIEWS], "open_findings": len(ledger.open_findings()),
        "billing_mode": "subscription", "cost_usd": None, "api_fallback": False,
        "max_repair_rounds": 2, "production_promoted": False, "published": False,
        "scope": "Repair existing draft, propose skill via Harness2 Proposer, single-page replay"})
    return ws


def repair(area, ws, number):
    label = f"repair-{number}"
    ledger_path = ws.ledger_path(PAGE)
    before = digest(ledger_path)
    policy = (area / "baseline/skills/function-format/SKILL.md").read_text(encoding="utf-8")
    prompt = f"""Repair existing documentation for canonical page_id {PAGE!r} at pinned source {SHA}.
Read the entire draft, full components/counter.lua source and all open ledger findings first.
Fix every evidenced contradiction and inspect adjacent claims for the same semantic mistakes.
Use doc_write_section for complete replacement sections. Preserve all required fields, examples,
headings, source citations and metadata. Do not close findings: a separate reviewer owns that.
Pay attention to false/nil defaulting, numeric-string coercion under LuaJIT, nil table keys,
comparison versus arithmetic failures, inactive branches, and load fallback/preservation.
Source audit already executed LuaJIT: Set(nil), Clear(nil), DoNotSave(nil) error;
stored false reads as zero in arithmetic/GetCount; false magnitude defaults to one;
numeric strings work in arithmetic and %g formatting; nonconvertible strings do not.
These are source evidence, not a substitute for reading source and checking current wording.
Call run_checks after changes; fix deterministic errors. Do not publish or edit skills.
Do not claim final PASS: open findings are expected until independent review.
Required formatting policy:\n{policy}"""
    log, usage = native(ws, label, "repair", prompt, "codex")
    unchanged = digest(ledger_path) == before
    save(area / f"{label}.json", {"usage": usage, "writer_ledger_unchanged": unchanged,
                                  "log": str(log)})
    if not unchanged:
        raise RuntimeError("Writer changed ledger")


def review(area, ws, label, tree):
    result = area / label / "result.json"
    if result.exists():
        return json.loads(result.read_text())
    before = digest(ws.draft_path(PAGE + ".md"))
    checkpoint.save_checkpoint(ws, PAGE, tree, label + "-input")
    print("START", label, flush=True)
    run_page(ws, PAGE, tree=tree, result_path=result, events_path=area / label / "events.jsonl",
             publish_page=False, resume_review=True)
    if digest(ws.draft_path(PAGE + ".md")) != before:
        raise RuntimeError("Read-only reviewer changed draft")
    record = json.loads(result.read_text())
    print("END", label, record["status"], record.get("open_findings"), flush=True)
    return record


def propose(area, ws):
    from dst_bench.adapter import (
        DstAdapter,
        validate_skill_generalization,
        validate_skill_only_tree,
    )
    from harness2.core import tree
    from harness2.core.proposer import Proposer
    from harness2.core.spec import ChannelSpec

    surface = DstAdapter().substrate.surface()
    baseline = tree.read_tree(surface, area / "baseline")
    prompt = """Propose a reusable improvement to the review-symbols skill from this repair episode.
Return ONLY JSON {"rules_markdown": "...", "rationale": "..."}. Add at most 12 concise lines.
Rules must be general procedural checks, not answers. No page names, symbols, file paths,
finding IDs, source line numbers or specific expected values. No weakening existing gates.
Do not repeat existing rules. Prefer a concrete verification procedure to vague advice.
No need for tools: evidence follows. Do not edit documentation or close ledger findings.
""" + "\nCURRENT SKILL:\n" + baseline[SKILL]
    prompt += "\nBEFORE:\n" + (area / "input-state/drafts/components/counter.md").read_text(encoding="utf-8")
    prompt += "\nAFTER:\n" + ws.draft_path(PAGE + ".md").read_text(encoding="utf-8")
    prompt += "\nFINDINGS AND REVIEW RESOLUTIONS:\n" + ws.ledger_path(PAGE).read_text(encoding="utf-8")

    class SubscriptionProposer(Proposer):
        def _opencode(self, cwd, mission, system, wall):
            log, usage = native(ws, "skill-proposal", "proposal", system + "\n" + mission, "claude-code")
            # Upstream requires numeric accounting. This field is API-equivalent estimate ONLY;
            # actual subscription cost stays null in the authoritative native usage record.
            estimate = usage["provider_reported_cost_usd"]
            if estimate is None:
                raise ValueError("Proposer accounting estimate unavailable")
            return final_text(log), float(estimate), ""

    prop = SubscriptionProposer(ChannelSpec("opencode", "claude-sonnet-5-5", timeout=300),
                                audit_dir=area / "proposer-audit", attempts=1)
    reply = prop.call(prompt, None, "single-page-skill-proposal", max_attempts=1)
    text = reply.text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0]
    payload = json.loads(text)
    rules = payload["rules_markdown"].strip()
    if not rules or len(rules) > 4000 or len(rules.splitlines()) > 12:
        raise ValueError("Proposal must contain 1..12 concise nonempty lines")
    if "counter" in rules.lower() or any(f.id in rules for f in Ledger(ws, PAGE).items.values()):
        raise ValueError("Task-specific answer leakage in skill")
    candidate = dict(baseline)
    candidate[SKILL] += "\n\n" + rules + "\n"
    validate_skill_generalization(candidate, baseline, ["components/counter.lua"])
    validate_skill_only_tree(candidate, baseline, surface)
    tree.write_tree(surface, candidate, area / "candidate")
    save(area / "proposal.json", dict(payload, validated=True, actual_cost_usd=None,
        upstream_cost_semantics="provider API-equivalent estimate, not subscription charge"))


def clone_state(area, ws, name, source, backend):
    target = workspace(area, name, backend)
    if not target.plan_path.exists():
        for directory in ("drafts", "ledger"):
            shutil.copytree(source / directory, target.settings.state_dir / directory)
        shutil.copyfile(ws.plan_path, target.plan_path)
    return target


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--area", type=Path)
    parser.add_argument("--phase", choices=("repair", "review", "propose", "evaluate", "all"), default="all")
    args = parser.parse_args()
    area = args.area or ROOT / "outputs" / ("full-flow-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    area.mkdir(parents=True, exist_ok=True)
    print("ARTIFACT_DIR", area, flush=True)
    ws = initialize(area)
    if args.phase in ("all", "repair", "review"):
        for number in (1, 2):
            if args.phase != "review" and not (area / f"repair-{number}.json").exists():
                repair(area, ws, number)
            if args.phase == "repair":
                return
            result = review(area, ws, f"review-{number}", area / "baseline")
            if result["status"] == "PASS":
                break
            if args.phase == "review" or result["status"] != "FAIL":
                return
        else:
            return
    passes = [p for p in area.glob("review-*/result.json") if json.loads(p.read_text())["status"] == "PASS"]
    if not passes:
        raise ValueError("Skill proposal requires completed independent repair review")
    if args.phase in ("all", "propose") and not (area / "proposal.json").exists():
        propose(area, ws)
    if args.phase in ("all", "evaluate"):
        clean = clone_state(area, ws, "candidate-clean", ws.settings.state_dir, "codex")
        positive = review(area, clean, "candidate-clean", area / "candidate")
        # Blind replay: original ledger predates the seven review findings. Do not seed
        # known open findings, otherwise FAIL could occur without detecting any defect.
        broken = clone_state(area, ws, "candidate-blind", INPUT, "codex")
        negative = review(area, broken, "candidate-blind", area / "candidate")
        shutil.copytree(ws.settings.state_dir / "drafts", area / "docs", dirs_exist_ok=True)
        save(area / "summary.json", {"page": PAGE, "docs_status": positive["status"],
            "broken_replay_status": negative["status"], "skill_candidate_created": True,
            "candidate_smoke_passed": positive["status"] == "PASS" and negative["status"] == "FAIL",
            "generalization_proven": False, "production_promoted": False, "published": False,
            "broken_replay_blind": True,
            "promotion_blockers": ["Only one seen page", "Actual subscription cost unknown"],
            "billing_mode": "subscription", "cost_usd": None,
            "framework": "Harness2 Proposer and adapter guards; bounded replay, not run_sequential"})


if __name__ == "__main__":
    main()
