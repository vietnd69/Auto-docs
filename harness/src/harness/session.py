"""Run one harness job as an OpenCode session and capture its event stream."""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from harness.jobqueue import Job
from harness.plan import Page
from harness.role_config import credentials, role_models, runtime_config
from harness.workspace import Workspace

BUDGET_EXHAUSTED = "BUDGET_EXHAUSTED"


class OpenCodeMissingError(FileNotFoundError):
    """OpenCode CLI not installed (run ``npm ci`` at the repository root)."""


@dataclass
class SessionResult:
    returncode: int
    timed_out: bool
    log_path: Path


def opencode_bin(ws: Workspace) -> str:
    configured = ws.settings.get_str("opencode_bin")
    if configured:
        return configured
    # Prefer the executable over npm's .cmd shim (CreateProcess quoting on Windows).
    native = ws.settings.root / "node_modules" / "opencode-ai" / "bin" / "opencode.exe"
    if sys.platform == "win32" and native.exists():
        return str(native)
    bin_dir = ws.settings.root / "node_modules" / ".bin"
    for name in ("opencode.cmd", "opencode"):
        candidate = bin_dir / name
        if candidate.exists():
            return str(candidate)
    found = shutil.which("opencode")
    if found is None:
        raise OpenCodeMissingError("opencode not found; run `npm ci` in the repository root")
    return found


def job_prompt(job: Job, page: Page) -> str:
    """Minimal starting context: everything else is pulled through tools (goal G3)."""
    lines = [
        f"JOB {job.id}: {job.kind} documentation page `{page.id}`.",
        f"Canonical page_id for EVERY page tool: {page.id!r}. Job ID is not a page ID.",
        f"domain: {page.domain}; page kind: {page.kind}; sources: {', '.join(s.file for s in page.sources)}",
    ]
    if job.kind == "resume-review":
        lines.append(
            "Resume the existing draft at final review; do not restart doc-job or generate a new outline. "
            "Use the actual dst-tools_ prefixed tool names. Read dst-tools_doc_read with empty heading, "
            "ledger_list and notes_read first. Re-check every open finding against the "
            "current draft and pinned source. Read every listed source with lua_read (continue until EOF); "
            "omit rev to use the pinned revision. Grep/outline do not count as source reading. "
            "Completion requires tool-recorded full draft and source coverage for THIS job. "
            "Load review-symbols and batch the specific claims. "
            "This is a read-only final review: do not rewrite sections or delegate tasks. "
            "Resolve an already-repaired finding only with source-backed evidence. Record remaining "
            "contradictions or omissions, leave them open, and stop for a separate repair. "
            "Check example setup/preconditions, caller versus callee, and repair item versus target. "
            "Do not expand into unrelated helper internals. Finish by calling review_finish(page_id, "
            "summary) once all checks and findings are clean, then stop. If time or calls run short, "
            "record unresolved items in notes and stop without claiming completion."
        )
        return "\n".join(lines)
    if job.kind == "update":
        lines.append(
            f"source changed from `{job.from_rev}` to `{job.to_rev}`; update only affected sections."
        )
    lines.append(
        "Follow the `doc-job` skill. Finish when `verdict` reports PASS or nothing more can be fixed."
    )
    return "\n".join(lines)


def mcp_bin(ws: Workspace) -> str:
    """Absolute path of the ``dst-tools-mcp`` entry point inside the project ``.venv``."""
    venv = ws.settings.root / ".venv"
    if sys.platform == "win32":
        # OpenCode expands this inside JSON text, where backslashes are escape characters.
        return (venv / "Scripts" / "dst-tools-mcp.exe").as_posix()
    return str(venv / "bin" / "dst-tools-mcp")


def session_env(ws: Workspace, job: Job) -> dict[str, str]:
    env = credentials(ws.settings)
    if ws.settings.values.get("isolated_usage"):
        for kind in ("DATA", "CONFIG", "CACHE", "STATE"):
            env[f"XDG_{kind}_HOME"] = str(ws.settings.state_dir / "opencode" / kind.lower())
    env.update(
        {
            "HARNESS_JOB": job.id,
            "HARNESS_MCP_BIN": mcp_bin(ws),
            "MOD_DOC_HARNESS_REV": job.to_rev or ws.rev,
            "MOD_DOC_HARNESS_BASELINE_BUILD": ws.settings.get_str("baseline_build"),
            "MOD_DOC_HARNESS_BASELINE_SHA": ws.settings.get_str("baseline_sha"),
            "OPENCODE_DISABLE_CLAUDE_CODE_SKILLS": "1",
            "OPENCODE_DISABLE_EXTERNAL_SKILLS": "1",
            "OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX": str(ws.settings.get_int("output_token_max")),
            "OPENCODE_PERMISSION": json.dumps({"external_directory": {"*": "deny"}}),
            "HARNESS_MAX_STEPS": str(ws.settings.get_int("max_steps")),
            # the MCP server must see the same source/docs/state as this runner
            "MOD_DOC_HARNESS_ROOT": str(ws.settings.root),
            "MOD_DOC_HARNESS_SCRIPTS_DIR": str(ws.settings.scripts_dir),
            "MOD_DOC_HARNESS_DOCS_DIR": str(ws.settings.docs_dir),
            "MOD_DOC_HARNESS_STATE_DIR": str(ws.settings.state_dir),
            "HARNESS_MAX_TOKENS": str(ws.settings.get_int("max_tokens")),
            "HARNESS_REVIEW_ROUNDS": str(ws.settings.get_int("review_rounds")),
            "OPENCODE_CONFIG_CONTENT": json.dumps(runtime_config(ws.settings)),
        }
    )
    if job.kind == "resume-review":
        steps = max(1, min(ws.settings.get_int("max_steps"), ws.settings.get_int("final_review_steps")))
        config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
        allowed = ["doc_read", "page_checklist", "notes_read", "notes_write", "lua_outline",
                   "lua_symbol", "lua_read", "lua_grep", "lua_refs", "ledger_add", "ledger_list",
                   "ledger_resolve", "run_checks", "verdict", "review_finish"]
        tools = {"*": False, "skill": True, **{f"dst-tools_{name}": True for name in allowed}}
        config.setdefault("agent", {})["harness-final-review"] = dict(
            model=role_models(ws.settings)["reviewer"],
            mode="primary", steps=steps, tools=tools,
            prompt="You perform a bounded final review. Never edit docs or delegate. "
                   "Follow the supplied resume-review mission. Call review_finish only after "
                   "checking the current draft and all open findings, then stop.",
        )
        env.update(HARNESS_MAX_STEPS=str(steps), HARNESS_REVIEW_ONLY="1",
                   HARNESS_REVIEW_PAGE=job.page_id, OPENCODE_CONFIG_CONTENT=json.dumps(config))
    return env


def run_agent(
    ws: Workspace, job: Job, agent: str, prompt: str, log_name: str, project_dir: Path | None = None
) -> SessionResult:
    """Run ``opencode run`` for ``agent`` with a wall-clock limit; stream events to a log.

    ``project_dir`` (default: the repository) is the directory whose ``.opencode/`` harness
    OpenCode loads; Harness² rollouts point it at a copy holding a candidate tree.
    """
    project = project_dir or ws.settings.root
    model = role_models(ws.settings)[agent]
    if job.kind == "resume-review":
        policy_path = project / ".opencode/harness/skills/review-symbols/SKILL.md"
        policy = policy_path.read_text(encoding="utf-8")
        if not policy.strip():
            raise ValueError("Final review requires a nonempty frozen review-symbols skill")
        prompt += "\n\nRequired review policy (loaded by controller):\n" + policy
        if ws.settings.get_int("review_runtime_evidence"):
            from harness.runtime_evidence import collect

            prompt += collect(ws, job)
        ws.report_path(f"review-policy/{job.id}.json").write_text(
            json.dumps({"job_id": job.id, "skill_sha256": hashlib.sha256(policy.encode()).hexdigest(),
                        "path": str(policy_path), "loaded_by": "controller"}), encoding="utf-8",
        )
    backend = ws.settings.get_str("final_review_backend") if job.kind == "resume-review" else "opencode"
    from harness.subscription import BACKENDS, run_review

    if backend not in BACKENDS:
        raise ValueError(f"Unknown final_review_backend: {backend}")
    if backend != "opencode":
        return run_review(ws, job, prompt, ws.report_path(f"sessions/{log_name}.jsonl"),
                          session_env(ws, job), backend)
    argv = [
        opencode_bin(ws),
        "run",
        prompt,
        "--dir",
        str(project),
        "--model",
        model,
        "--agent",
        "harness-final-review" if job.kind == "resume-review" else agent,
        "--title",
        job.id,
        "--format",
        "json",
    ]
    log_path = ws.report_path(f"sessions/{log_name}.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = ws.settings.get_int("max_wall_minutes") * 60
    if job.kind == "resume-review":
        timeout = min(timeout, max(1, ws.settings.get_int("final_review_seconds")))
    with log_path.open("w", encoding="utf-8") as log:
        try:
            proc = subprocess.run(
                argv,
                stdout=log,
                stderr=subprocess.STDOUT,
                env=session_env(ws, job),
                cwd=project,
                timeout=timeout,
                check=False,
            )
        except subprocess.TimeoutExpired:
            return SessionResult(-1, True, log_path)
    return SessionResult(proc.returncode, False, log_path)


def has_error_event(log_path: Path) -> bool:
    if not log_path.exists():
        return True
    for line in log_path.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if isinstance(event, dict) and event.get("type") == "error":
            return True
    return False


def budget_hit(log_path: Path, marker: Path | None = None) -> bool:
    """Whether the budget plugin (marker file) or the proxy (log text) stopped the session."""
    if marker is not None and marker.exists():
        return True
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return False
    return BUDGET_EXHAUSTED in text
