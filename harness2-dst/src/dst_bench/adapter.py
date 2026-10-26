"""``DstAdapter``: lets Harness² propose, run and select harness variants for doc pages.

A task is one ``page_id`` of ``.harness/doc-plan.json``. A rollout runs
``mod-harness run-page`` with the candidate harness tree in an isolated state directory;
the deterministic verdict (checks + evidenced findings) is the score.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

from harness2.core.spec import BenchPrompts, BenchSpec, resolve_channel_model
from harness2.substrate.opencode import OpencodeSubstrate, render_events

ROOT = Path(os.environ.get("HARNESS2_DST_ROOT", Path(__file__).resolve().parents[3]))
RUNS = ROOT / "harness2-dst" / "runs"
PLAN = ROOT / ".harness" / "doc-plan.json"
REGRESSION = ROOT / ".harness" / "regression.json"
BASE_TREE = ROOT / ".opencode" / "harness"

PROMPTS = BenchPrompts(
    work=(
        "Write Docusaurus (MDX) API reference pages for Don't Starve Together Lua scripts, for "
        "mod developers: exact signatures, behaviour, events, tags and usage, every statement "
        "traceable to the Lua source, built section by section with the dst-tools MCP tools."
    ),
    domain_word="file type",
    deliverable_word="documentation page",
    inv_levers="how the agent navigates long Lua files, orders its work and verifies coverage",
    dom_levers="conventions specific to this file type (components, prefabs, stategraphs, data files)",
)


def _mod_harness() -> Path:
    venv = ROOT / ".venv"
    return venv / (
        "Scripts/mod-harness.exe" if sys.platform == "win32" else "bin/mod-harness"
    )


def _plan_pages() -> dict[str, dict[str, object]]:
    data = json.loads(PLAN.read_text(encoding="utf-8"))
    return {p["id"]: p for p in data["pages"]}


class DstAdapter:
    def __init__(self, substrate: str = "oc", split_file: Path | None = None) -> None:
        if substrate != "oc":
            raise ValueError("the dst bench runs on OpenCode only (--substrate oc)")
        self.substrate = OpencodeSubstrate()
        self.spec = BenchSpec(
            name="dst",
            runs_root=RUNS,
            install_mode="workspace_config",
            prompts=PROMPTS,
            channels={
                "proposer": resolve_channel_model(None, None),
                "selector": resolve_channel_model(None, None),
            },
            domain_word="file type",
            allow_subagents=True,
            reserved_scripts=frozenset(),
        )
        self._split_file = split_file

    # -- task discovery -----------------------------------------------------------------
    def tasks(self, split: str = "all") -> list[str]:
        explicit = [
            t for t in os.environ.get("HARNESS2_DST_TASKS", "").split(",") if t.strip()
        ]
        if explicit:
            return sorted(explicit)
        stored = (
            json.loads(REGRESSION.read_text(encoding="utf-8"))
            if REGRESSION.exists()
            else {}
        )
        return sorted({page for pages in stored.values() for page in pages})

    def domain_of(self, task_id: str) -> str:
        return str(_plan_pages().get(task_id, {}).get("domain", "core"))

    def task_prompt(self, task_id: str) -> str:
        page = _plan_pages().get(task_id, {})
        sources = ", ".join(s["file"] for s in page.get("sources", []))  # type: ignore[union-attr]
        return f"Document page `{task_id}` ({page.get('kind', 'api')}) from {sources}."

    def task_files(self, task_id: str) -> Path | None:
        return None

    # -- rollouts ------------------------------------------------------------------------
    def execute(
        self,
        task_id: str,
        harness_dir: Path | None,
        run_id: str,
        *,
        timeout: int | None = None,
    ) -> Path:
        run_dir = RUNS / "rollouts" / run_id
        if (run_dir / "result.json").exists():
            return run_dir
        run_dir.mkdir(parents=True, exist_ok=True)
        argv = [
            str(_mod_harness()),
            "run-page",
            task_id,
            "--state-dir",
            str(run_dir / "state"),
            "--harness-tree",
            str(harness_dir or BASE_TREE),
            "--result",
            str(run_dir / "result.json"),
            "--events",
            str(run_dir / "events.jsonl"),
        ]
        subprocess.run(argv, cwd=ROOT, timeout=timeout, check=False)
        return run_dir

    def delivered(self, run_dir: Path) -> bool:
        result = run_dir / "result.json"
        return (
            result.exists()
            and json.loads(result.read_text(encoding="utf-8")).get("status") == "PASS"
            and bool(self.deliverable_text(run_dir).strip())
        )

    def trajectory(self, run_dir: Path, *, obs_trunc: int) -> str:
        header = execution_header(run_dir)
        events = run_dir / "events.jsonl"
        if not events.exists():
            return header + "\n[ERROR] no trajectory recorded"
        return header + "\n" + render_events(events, obs_trunc=obs_trunc, max_chars=400_000)

    def deliverable_files(self, run_dir: Path) -> dict[str, str]:
        drafts = run_dir / "state" / "drafts"
        return {
            p.relative_to(drafts).as_posix(): p.read_text(encoding="utf-8")
            for p in drafts.rglob("*.md")
        }

    def deliverable_text(self, run_dir: Path) -> str:
        return (
            "\n\n".join(self.deliverable_files(run_dir).values())
            if (run_dir / "state").exists()
            else ""
        )

    # -- harness ---------------------------------------------------------------------------
    def base_harness(self) -> Path:
        return BASE_TREE

    def validate_tree(self, tree: dict[str, str]) -> None:
        problems = []
        if "plugin/budget.ts" not in tree:
            problems.append(
                "plugin/budget.ts must stay: it enforces the step budget and loop guards"
            )
        elif tree["plugin/budget.ts"] != (BASE_TREE / "plugin/budget.ts").read_text(
            encoding="utf-8"
        ):
            problems.append("plugin/budget.ts is immutable during skill optimization")
        if "skills/doc-job/SKILL.md" not in tree:
            problems.append(
                "skills/doc-job/SKILL.md must stay: the orchestrator loads it first"
            )
        if any(rel.startswith("sub_agents/orchestrator") for rel in tree):
            problems.append(
                "the orchestrator is fixed outside the editable tree; edit systemprompt.md instead"
            )
        if problems:
            raise ValueError("; ".join(problems))
        task_ids = set(self.tasks())
        sources = [
            source["file"]
            for page_id, page in _plan_pages().items()
            if page_id in task_ids
            for source in page.get("sources", [])
        ]
        baseline = {
            name: (BASE_TREE / name).read_text(encoding="utf-8")
            for name in tree
            if name.startswith("skills/") and (BASE_TREE / name).is_file()
        }
        validate_skill_generalization(tree, baseline, sources)

    def score(self, run_dir: Path, task_id: str) -> dict[str, object] | None:
        result = run_dir / "result.json"
        if not result.exists():
            return None
        data = json.loads(result.read_text(encoding="utf-8"))
        issues = int(data.get("issues", 0)) + int(data.get("open_findings", 0))
        value = 1.0 if data.get("status") == "PASS" and issues == 0 else 0.0
        return {"score": value, "status": data.get("status"), "issues": issues}


def execution_header(run_dir: Path) -> str:
    """Expose controller runtime facts, never grader scores or findings."""
    result = run_dir / "result.json"
    try:
        data = json.loads(result.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    execution = data.get("execution") if isinstance(data, dict) else None
    facts: dict[str, object] = {"completed": "unknown", "reason": "missing_execution_record"}
    if isinstance(execution, dict):
        for key in ("completed", "timed_out", "budget_stop", "error_event_or_missing_log"):
            if isinstance(execution.get(key), bool):
                facts[key] = execution[key]
        if type(execution.get("returncode")) is int:
            facts["returncode"] = execution["returncode"]
        if execution.get("reason") in (
            "running", "completed", "timeout", "budget_stop", "process_error",
            "error_event_or_missing_log", "launch_or_runtime_exception",
        ):
            facts["reason"] = execution["reason"]
    elif isinstance(data, dict) and data.get("status") in ("BUDGET_EXHAUSTED", "ERROR"):
        facts = {"completed": False, "reason": "legacy_interruption_cause_unknown"}
    return (
        "[CONTROLLER EXECUTION — not a quality verdict]\n"
        + json.dumps(facts, sort_keys=True)
        + "\nUse this record for process completion. Intermediate tool verdicts do not establish "
        "completion or final documentation quality.\n"
    )


def validate_skill_only_tree(candidate, baseline, surface) -> None:
    """Permit skill Markdown and only the triggers derived by the runtime.

    Upstream autotrigger runs before adapter validation. Recompute independently
    from frozen guardrails so model edits cannot be smuggled in as triggers.
    """
    from harness2.core import tree

    canonical = dict(candidate)
    trigger_file = surface.autotrigger_file
    for name in set(candidate) | set(baseline):
        if name.startswith("skills/") and name.endswith(".md"):
            continue
        if name != trigger_file and candidate.get(name) != baseline.get(name):
            raise ValueError("Only skill Markdown changes are permitted: " + name)
    if trigger_file in baseline:
        canonical[trigger_file] = baseline[trigger_file]
    else:
        canonical.pop(trigger_file, None)
    tree.autotrigger(surface, canonical)
    if candidate.get(trigger_file) not in (baseline.get(trigger_file), canonical.get(trigger_file)):
        raise ValueError("Existing guardrails are immutable; only canonical runtime triggers are permitted")
    tree.validate(surface, canonical)
    candidate.clear()
    candidate.update(canonical)


def validate_skill_generalization(
    candidate: dict[str, str], baseline: dict[str, str], sources: list[str]
) -> None:
    """Reject new task-specific source anchors in reusable procedural skills."""
    for name, content in candidate.items():
        if not name.startswith("skills/"):
            continue
        previous = set(baseline.get(name, "").splitlines())
        additions = "\n".join(
            line for line in content.splitlines() if line not in previous
        )
        if any(source in additions for source in sources):
            raise ValueError(
                f"{name}: keep task-specific source facts in task notes, not shared skills"
            )
