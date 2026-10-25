"""Run one harness job as an OpenCode session and capture its event stream."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from harness.jobqueue import Job
from harness.plan import Page
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
        f"domain: {page.domain}; page kind: {page.kind}; sources: {', '.join(s.file for s in page.sources)}",
    ]
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
        return str(venv / "Scripts" / "dst-tools-mcp.exe")
    return str(venv / "bin" / "dst-tools-mcp")


def session_env(ws: Workspace, job: Job) -> dict[str, str]:
    env = dict(os.environ)
    env.update(
        {
            "HARNESS_JOB": job.id,
            "HARNESS_MCP_BIN": mcp_bin(ws),
            "MOD_DOC_HARNESS_REV": job.to_rev or ws.rev,
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
        }
    )
    return env


def run_agent(
    ws: Workspace, job: Job, agent: str, prompt: str, log_name: str, project_dir: Path | None = None
) -> SessionResult:
    """Run ``opencode run`` for ``agent`` with a wall-clock limit; stream events to a log.

    ``project_dir`` (default: the repository) is the directory whose ``.opencode/`` harness
    OpenCode loads; Harness² rollouts point it at a copy holding a candidate tree.
    """
    project = project_dir or ws.settings.root
    model = f"{ws.settings.get_str('provider_id')}/{ws.settings.get_str('model')}"
    argv = [
        opencode_bin(ws),
        "run",
        prompt,
        "--dir",
        str(project),
        "--model",
        model,
        "--agent",
        agent,
        "--title",
        job.id,
        "--format",
        "json",
    ]
    log_path = ws.report_path(f"sessions/{log_name}.jsonl")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    timeout = ws.settings.get_int("max_wall_minutes") * 60
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


def budget_hit(log_path: Path, marker: Path | None = None) -> bool:
    """Whether the budget plugin (marker file) or the proxy (log text) stopped the session."""
    if marker is not None and marker.exists():
        return True
    try:
        text = log_path.read_text(encoding="utf-8", errors="replace")
    except FileNotFoundError:
        return False
    return BUDGET_EXHAUSTED in text
