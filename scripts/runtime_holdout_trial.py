"""Frozen-skill trial: counter regression plus untouched finiteuses holdout.

Native subscriptions only. Holdout A/B receive the same input and language evidence.
No skill tuning, production promotion, publishing or API fallback.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
from pathlib import Path

import frontmatter
from harness.config import Settings, load_settings
from harness.jobqueue import Job
from harness.plan import DocPlan, Page, SourceRef, save_plan
from harness.runner import run_page
from harness.workspace import make_workspace

from harness import checkpoint, runtime_evidence, session, subscription

ROOT = Path(__file__).resolve().parents[1]
PRIOR = ROOT / "outputs/full-flow-20261027-counter"
ORIGINAL = ROOT / "outputs/harness2-trial-20261027-011200/policy-review-012727/state"
SHA = "b729a8f68d4b635c21279e71723b9627f24c5c38"
PAGE = "components/finiteuses"
DOC = Path("D:/code/dst-api-webdocs/docs/game-scripts/components/finiteuses.md")


def save(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def ws_for(area, label, backend="codex"):
    cfg = load_settings(ROOT)
    return make_workspace(Settings(ROOT, dict(cfg.values,
        state_dir=str(area / label / "state"), docs_dir=str(area / label / "docs"),
        scripts_dir="D:/code/dst-scripts", final_review_backend=backend,
        codex_subscription_model="gpt-6.1-sol", codex_subscription_effort="medium",
        claude_subscription_model="claude-sonnet-5-5", claude_subscription_effort="high",
        review_runtime_evidence=1, max_wall_minutes=7, final_review_seconds=420, reflect=0)), SHA)


def initialize(area):
    if (area / "manifest.json").exists():
        return
    for name in ("baseline", "candidate"):
        shutil.copytree(PRIOR / name, area / name)
    imported = ws_for(area, "input")
    page = Page(PAGE, PAGE + ".md", "FiniteUses", "components", "api", ["components"],
                [SourceRef("components/finiteuses.lua")])
    save_plan(DocPlan({"build": "759671", "sha": SHA}, [page]), imported.plan_path)
    # Preserve the old build in an immutable provenance copy. Target metadata denotes
    # the review target, not a claim that this imported content already matches it.
    shutil.copyfile(DOC, area / "finiteuses-original.md")
    post = frontmatter.loads(DOC.read_text(encoding="utf-8"))
    post.metadata.update(source_sha=SHA, build_version="759671", sources=["components/finiteuses.lua"])
    post.content = re.sub(r"^> Based on game build.*$", "> Based on game build **759671**",
                          post.content, flags=re.MULTILINE)
    draft = imported.draft_path(PAGE + ".md")
    draft.write_text(frontmatter.dumps(post) + "\n", encoding="utf-8")
    for label in ("holdout-baseline", "holdout-candidate"):
        ws = ws_for(area, label)
        shutil.copytree(imported.settings.state_dir / "drafts", ws.settings.state_dir / "drafts")
        shutil.copyfile(imported.plan_path, ws.plan_path)
    counter = ws_for(area, "counter-runtime")
    for name in ("drafts", "ledger"):
        shutil.copytree(ORIGINAL / name, counter.settings.state_dir / name)
    shutil.copyfile(ORIGINAL / "doc-plan.json", counter.plan_path)
    save(area / "manifest.json", {"source_sha": SHA, "holdout_page": PAGE,
        "original_doc": str(DOC), "original_doc_sha256": sha(DOC),
        "imported_draft_sha256": sha(draft), "imported_content_unverified": True,
        "metadata_only_normalization": True, "holdout_findings_seeded": False,
        "candidate_sha256": sha(area / "candidate/skills/review-symbols/SKILL.md"),
        "candidate_unchanged_from_counter": True, "review_runtime_evidence": True,
        "max_native_calls": 5, "actual_cost_usd": None, "published": False, "promoted": False})


def review(area, label, tree, page=PAGE, backend="codex"):
    dest = area / label / "result.json"
    if dest.exists():
        return json.loads(dest.read_text())
    ws = ws_for(area, label, backend)
    before = sha(ws.draft_path(page + ".md"))
    checkpoint.save_checkpoint(ws, page, area / tree, label + "-input")
    print("START", label, backend, flush=True)
    run_page(ws, page, tree=area / tree, result_path=dest, events_path=area / label / "events.jsonl",
             publish_page=False, resume_review=True)
    if before != sha(ws.draft_path(page + ".md")):
        raise RuntimeError("Reviewer changed draft")
    result = json.loads(dest.read_text())
    print("END", label, result["status"], result.get("open_findings"), flush=True)
    return result


def repair(area):
    ws = ws_for(area, "holdout-final", "claude-code")
    if not ws.plan_path.exists():
        source = ws_for(area, "holdout-candidate")
        for name in ("drafts", "ledger"):
            shutil.copytree(source.settings.state_dir / name, ws.settings.state_dir / name)
        shutil.copyfile(source.plan_path, ws.plan_path)
    marker = area / "repair.json"
    if marker.exists():
        return
    job = Job("holdout-repair", "repair", PAGE, to_rev=SHA)
    env = session.session_env(ws, job)
    env.update(HARNESS_NATIVE_MODE="repair", HARNESS_REPAIR_PAGE=PAGE)
    log = ws.report_path("sessions/holdout-repair.jsonl")
    if log.exists():
        raise ValueError("Interrupted repair requires inspection; no automatic duplicate call")
    before = sha(ws.ledger_path(PAGE))
    policy = (area / "candidate/skills/function-format/SKILL.md").read_text(encoding="utf-8")
    prompt = f"""Repair page {PAGE!r} against pinned source {SHA}.
Read the full draft, components/finiteuses.lua, checklist and all open findings first.
This is an imported old-build document: verify all claims, complete missing public methods,
properties, error/return contracts, examples and events. Distinguish setter callbacks,
event-before-clamp values, action objects, doer-owned dependencies, and branch-specific behavior.
Use doc_write_section/doc_set_meta to fix it. Follow the formatting policy below.
Do not close findings or publish; an independent reviewer will verify repairs.
Run deterministic checks and fix remaining issues before stopping.\n{policy}"""
    prompt += runtime_evidence.collect(ws, job)
    print("START holdout-repair codex", flush=True)
    result = subscription.run_review(ws, job, prompt, log, env, "codex")
    usage = json.loads(log.with_suffix(".usage.json").read_text())
    if result.timed_out or result.returncode or not usage["completed"]:
        raise RuntimeError("Repair incomplete; preserved logs")
    if before != sha(ws.ledger_path(PAGE)):
        raise RuntimeError("Writer changed ledger")
    save(marker, {"writer_ledger_unchanged": True, "usage": usage})
    print("END holdout-repair", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--area", type=Path, required=True)
    parser.add_argument("--phase", choices=("all", "counter", "ab", "repair"), default="all")
    args = parser.parse_args()
    area = args.area.resolve()
    area.mkdir(parents=True, exist_ok=True)
    initialize(area)
    if args.phase in ("all", "counter"):
        review(area, "counter-runtime", "candidate", "components/counter")
    if args.phase in ("all", "ab"):
        review(area, "holdout-baseline", "baseline")
        review(area, "holdout-candidate", "candidate")
    if args.phase in ("all", "repair"):
        repair(area)
        final = review(area, "holdout-final", "candidate", backend="claude-code")
        shutil.copytree(ws_for(area, "holdout-final").settings.state_dir / "drafts",
                        area / "docs", dirs_exist_ok=True)
        save(area / "summary.json", {"docs_status": final["status"], "published": False, "promoted": False,
            "actual_cost_usd": None, "candidate_retuned_on_holdout": False,
            "results": {p.parent.name: json.loads(p.read_text()) for p in area.glob("*/result.json")}})


if __name__ == "__main__":
    main()
