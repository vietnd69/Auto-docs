"""Self-improvement tier 2: Harness² recursion on failing pages + regression-gated promotion."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import threading
from dataclasses import dataclass, field
from pathlib import Path

from harness.codeindex import index_codebase
from harness.jobqueue import Job
from harness.opencode_sync import replace_tree
from harness.pages import get_plan
from harness.plan import DocPlan, Page, symbol_tokens
from harness.timeutil import now_iso
from harness.workspace import Workspace

_lock = threading.Lock()
_escalations = 0


def harness2_bin(ws: Workspace) -> Path:
    venv = ws.settings.root / "harness2-dst" / ".venv"
    return venv / ("Scripts/harness2.exe" if sys.platform == "win32" else "bin/harness2")


def escalate(ws: Workspace, page: Page) -> bool:
    """Run Harness² task-level recursion (seq, k=2) for one page; bounded per process."""
    global _escalations  # noqa: PLW0603 - per-run counter shared by worker threads
    with _lock:
        if _escalations >= ws.settings.get_int("escalate_max"):
            return False
        _escalations += 1
    binary = harness2_bin(ws)
    if not binary.exists():
        print(
            f"  [improve] {binary} missing; run `uv sync --project harness2-dst` (see harness2-dst/README.md)"
        )
        return False
    env = dict(os.environ, HARNESS2_DST_TASKS=page.id, HARNESS2_DST_ROOT=str(ws.settings.root))
    argv = [str(binary), "--bench", "dst", "--k", "2", "--mode", "seq", "--max-tasks", "1"]
    result = subprocess.run(argv, env=env, cwd=ws.settings.root / "harness2-dst", check=False)
    if result.returncode != 0:
        return False
    return harvest(ws, page) is not None


def harvest(ws: Workspace, page: Page) -> Path | None:
    """Copy the harness Harness² adopted for ``page`` into our domain library."""
    slug = page.id.replace("/", "__")
    runs = ws.settings.root / "harness2-dst" / "runs"
    found = sorted(runs.glob(f"**/harnesses/{slug}/harness"), key=lambda p: p.stat().st_mtime)
    if not found:
        return None
    target = ws.library_dir(page.domain) / "harnesses" / slug
    if target.exists():
        shutil.rmtree(target)
    shutil.copytree(found[-1].parent, target)
    return target


def setup_harness2(ws: Workspace) -> int:
    """Clone the pinned Harness² commit into harness2-dst/vendor and apply our patches."""
    base = ws.settings.root / "harness2-dst"
    url, commit = (base / "PIN").read_text(encoding="utf-8").split()
    vendor = base / "vendor" / "harness2"
    if not vendor.exists():
        vendor.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--filter=blob:none", url, str(vendor)], check=True)
    subprocess.run(["git", "-C", str(vendor), "checkout", "--force", commit], check=True)
    subprocess.run(["git", "-C", str(vendor), "clean", "-fd"], check=True)
    for patch in sorted((base / "patches").glob("*.patch")):
        subprocess.run(["git", "-C", str(vendor), "apply", str(patch.resolve())], check=True)
    print(f"Harness² {commit[:10]} ready in {vendor}; now run `uv sync --project harness2-dst`")
    return 0


# ---- regression gate ---------------------------------------------------------------------
@dataclass
class Score:
    passed: int
    issues: int
    pages: int
    outcomes: dict[str, str] = field(default_factory=dict)
    cost_usd: float | None = None

    def at_least(self, other: Score) -> bool:
        """Require multiple-page coverage, no page regression and an evidenced improvement."""
        if (
            self.pages < 2
            or self.pages != other.pages
            or self.passed != self.pages
            or self.issues != 0
            or set(self.outcomes) != set(other.outcomes)
            or len(self.outcomes) != self.pages
            or any(status != "PASS" for status in self.outcomes.values())
        ):
            return False
        if any(
            cost is None or not math.isfinite(cost) or cost < 0 for cost in (self.cost_usd, other.cost_usd)
        ):
            return False
        if self.cost_usd is None or other.cost_usd is None:
            return False
        return self.cost_usd <= other.cost_usd and (
            self.passed > other.passed or self.issues < other.issues or self.cost_usd < other.cost_usd
        )


def regression_pages(ws: Workspace, plan: DocPlan, domain: str, per_domain: int = 3) -> list[str]:
    """Fixed sample per domain (smallest, median, largest api page), stored for reuse."""
    path = ws.regression_path
    stored: dict[str, list[str]] = json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}
    if domain not in stored:
        index = index_codebase(ws)
        candidates = sorted(
            (p for p in plan.pages if p.domain == domain and p.kind == "api"),
            key=lambda p: symbol_tokens(p, index),
        )
        if candidates:
            picks = {candidates[0].id, candidates[len(candidates) // 2].id, candidates[-1].id}
            stored[domain] = sorted(picks)[:per_domain]
            path.write_text(json.dumps(stored, indent=1) + "\n", encoding="utf-8")
    return stored.get(domain, [])


def _isolated(ws: Workspace, label: str) -> Workspace:
    from harness.config import Settings
    from harness.runner import isolated_workspace
    from harness.workspace import make_workspace

    state = ws.settings.state_dir / "regression" / label
    if state.exists():
        shutil.rmtree(state)
    isolated = isolated_workspace(ws, state)
    return make_workspace(
        Settings(ws.settings.root, dict(isolated.settings.values, isolated_usage=True)), ws.rev
    )


def score_harness(ws: Workspace, page_ids: list[str], label: str, *, tree: Path | None = None) -> Score:
    """Run each regression page from scratch in an isolated state dir and score it."""
    from harness.runner import RunOptions, candidate_project, run_job

    iso = _isolated(ws, label)
    project = candidate_project(iso, tree, iso.settings.state_dir) if tree else None
    opts = RunOptions(
        build=ws.settings.get_str("baseline_build"), publish=False, reflect=False, project_dir=project
    )
    passed = issues = 0
    outcomes = {}
    for page_id in page_ids:
        job = Job(id=f"regress-{label}-{page_id}".replace("/", "__"), kind="generate", page_id=page_id)
        status, report = run_job(iso, job, opts)
        passed += status == "PASS"
        outcomes[page_id] = status
        issues += max(0, len(report.splitlines()) - 1)
    from harness.usage import regression_cost

    cost = regression_cost(iso.settings.state_dir / "opencode/data/opencode/opencode.db")
    if (
        iso.settings.get_str("reviewer_model") != "gpt-oss:120b"
        or iso.settings.get_str("planner_model") != "gpt-oss:120b"
        or iso.settings.get_str("deepseek_model") != "deepseek-flash"
    ):
        cost = None  # the pinned alias rates do not cover other routing configurations
    return Score(passed, issues, len(page_ids), outcomes, cost)


def promote(ws: Workspace, domain: str, candidate: str) -> int:
    """Adopt ``candidate`` (a Harness² tree) only if it does not regress ``domain``."""
    cand = Path(candidate) if candidate else _latest_candidate(ws, domain)
    if cand is None or not cand.is_dir():
        print(f"no candidate harness for {domain}")
        return 1
    plan = get_plan(ws)
    pages = regression_pages(ws, plan, domain)
    if len(set(pages)) < 2:
        print("promotion requires at least two distinct regression pages")
        return 2
    opencode = ws.settings.root / ".opencode"
    baseline = score_harness(ws, pages, "baseline")
    trial = score_harness(ws, pages, "candidate", tree=cand)
    record = {
        "domain": domain,
        "candidate": str(cand),
        "baseline": vars(baseline),
        "candidate_score": vars(trial),
        "time": now_iso(),
    }
    if trial.at_least(baseline):
        replace_tree(opencode, cand)
        record["decision"] = "promoted"
        code = 0
    else:
        record["decision"] = "rejected"
        record["reason"] = (
            "Require multiple identical pages, all candidate pages PASS, complete costs, "
            "no cost increase and strict improvement."
        )
        code = 2
    log = ws.report_path("promotions.jsonl")
    with log.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record) + "\n")
    print(json.dumps(record, indent=1))
    return code


def _latest_candidate(ws: Workspace, domain: str) -> Path | None:
    root = ws.library_dir(domain) / "harnesses"
    trees = sorted(
        (p / "harness" for p in root.glob("*") if (p / "harness").is_dir()), key=lambda p: p.stat().st_mtime
    )
    return trees[-1] if trees else None


__all__ = ["Score", "escalate", "harvest", "promote", "regression_pages", "score_harness", "setup_harness2"]
