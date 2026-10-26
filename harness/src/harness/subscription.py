"""Native, locally authenticated CLI reviewers; never proxy subscription tokens."""
from __future__ import annotations

import json
import os
import shutil
import subprocess
from pathlib import Path

from harness.config import Settings

REVIEW_TOOLS = (
    "doc_read", "page_checklist", "notes_read", "notes_write", "lua_outline",
    "lua_symbol", "lua_read", "lua_grep", "lua_refs", "ledger_add", "ledger_list",
    "ledger_resolve", "run_checks", "verdict", "review_finish",
)
BACKENDS = ("opencode", "claude-code", "codex")

REPAIR_TOOLS = (*(t for t in REVIEW_TOOLS if t not in (
    "ledger_add", "ledger_resolve", "review_finish", "notes_write",
)), "doc_write_section", "doc_set_meta")
PROPOSAL_TOOLS = ("doc_read", "lua_read", "lua_symbol", "ledger_list")


def native_tools(env: dict[str, str]) -> tuple[str, ...]:
    """Fail closed on unknown modes; writers cannot certify their own repairs."""
    mode = env.get("HARNESS_NATIVE_MODE", "review")
    if mode == "repair":
        if not env.get("HARNESS_REPAIR_PAGE") or env.get("HARNESS_REVIEW_ONLY") == "1":
            raise ValueError("Native repair requires a scoped writable page")
        return REPAIR_TOOLS
    if mode in ("review", "proposal"):
        if env.get("HARNESS_REVIEW_ONLY") != "1":
            raise ValueError("Native review/proposal MCP requires read-only review mode")
        return REVIEW_TOOLS if mode == "review" else PROPOSAL_TOOLS
    raise ValueError("Unknown native session mode")


def clean_env(env: dict[str, str]) -> dict[str, str]:
    """Use CLI login, not project API keys, proxy endpoints or paid cloud routing."""
    blocked = ("ANTHROPIC_", "OPENAI_", "DEEPSEEK_", "OLLAMA_", "ACCOUNT_", "OPENCODE_",
               "CLAUDE_CODE_USE_", "CLAUDE_CODE_OAUTH_")
    return {k: v for k, v in env.items()
            if not k.upper().startswith(blocked)
            and not any(s in k.upper() for s in ("API_KEY", "AUTH_TOKEN"))
            and k not in ("CLAUDECODE", "CLAUDE_CODE_ENTRYPOINT")}


def executable(cfg: Settings, backend: str) -> str:
    if backend not in ("claude-code", "codex"):
        raise ValueError(f"Unsupported subscription backend: {backend}")
    name = "claude" if backend == "claude-code" else "codex"
    path = cfg.get_str(f"{name}_bin") or shutil.which(name)
    if not path:
        raise FileNotFoundError(f"Install the official {name} CLI or configure {name}_bin")
    return str(path)


def auth_status(cfg: Settings, backend: str, env: dict[str, str] | None = None) -> dict:
    """CLI-owned login inspection. Return no email, account ID, token or raw output."""
    binary = executable(cfg, backend)
    args = ["auth", "status", "--json"] if backend == "claude-code" else ["login", "status"]
    result = subprocess.run([binary, *args], env=clean_env(env or dict(os.environ)),
                            capture_output=True, text=True, encoding="utf-8", timeout=20, check=False)
    if backend == "claude-code":
        try:
            status = json.loads(result.stdout)
        except ValueError:
            status = {}
        ready = (result.returncode == 0 and status.get("loggedIn") is True
                 and bool(status.get("subscriptionType")))
        ready = ready and status.get("authMethod") in ("claude.ai", "oauth")
    else:
        ready = result.returncode == 0 and "chatgpt" in (result.stdout + result.stderr).lower()
    return {"backend": backend, "subscription_login": bool(ready),
            "login_command": "claude auth login" if backend == "claude-code" else "codex login"}


def command(cfg: Settings, backend: str, env: dict[str, str], folder: Path) -> list[str]:
    """Build a CLI invocation with only our review MCP tools and no shell/editor."""
    binary = executable(cfg, backend)
    allowed = native_tools(env)
    mcp_env = {k: v for k, v in env.items() if k.startswith(("HARNESS_", "MOD_DOC_HARNESS_"))}
    mcp_env["HARNESS_NATIVE_REVIEW"] = "1"
    server = {"command": env["HARNESS_MCP_BIN"], "env": mcp_env}
    if backend == "claude-code":
        config = folder / "mcp.json"
        config.write_text(json.dumps({"mcpServers": {"dst_tools": server}}), encoding="utf-8")
        argv = [binary, "-p", "--verbose", "--output-format", "stream-json",
                "--permission-mode", "dontAsk", "--tools", "", "--setting-sources", "",
                "--strict-mcp-config", "--mcp-config", str(config), "--no-session-persistence",
                "--disable-slash-commands", "--allowedTools",
                ",".join("mcp__dst_tools__" + tool for tool in allowed)]
        model = cfg.get_str("claude_subscription_model")
    else:
        # Isolate configuration, preserve the CLI's existing native login store.
        argv = [binary, "-a", "never", "exec", "--ignore-user-config", "--ephemeral",
                "--skip-git-repo-check", "--sandbox", "read-only", "--json",
                "-c", 'forced_login_method="chatgpt"', "-c", 'model_provider="openai"',
                "-c", "features.shell_tool=false", "-c", "features.multi_agent=false",
                "-c", 'web_search="disabled"']
        options = {"command": server["command"], "enabled_tools": list(allowed),
                   "required": True, "env": mcp_env}
        for key, value in options.items():
            if key == "env":
                for name, item in value.items():
                    argv.extend(["-c", f"mcp_servers.dst_tools.env.{name}={json.dumps(item)}"])
            else:
                argv.extend(["-c", f"mcp_servers.dst_tools.{key}={json.dumps(value)}"])
        # These local review operations are explicitly authorized by selecting this backend.
        # Keep the sandbox and allowlist; do not approve arbitrary MCP servers/tools.
        for tool in allowed:
            argv.extend(["-c", f'mcp_servers.dst_tools.tools.{tool}.approval_mode="approve"'])
        model = cfg.get_str("codex_subscription_model")
    if model:
        argv.extend(["--model", model])
    return argv + effort_args(cfg, backend)


def effort_args(cfg: Settings, backend: str) -> list[str]:
    name = "claude" if backend == "claude-code" else "codex"
    effort = cfg.get_str(f"{name}_subscription_effort")
    if not effort:
        return []
    allowed = ("low", "medium", "high", "max") if name == "claude" else (
        "minimal", "low", "medium", "high", "xhigh", "max", "ultra"
    )
    if effort not in allowed:
        raise ValueError(f"Unsupported {name} subscription reasoning effort")
    return ["--effort", effort] if name == "claude" else [
        "-c", f"model_reasoning_effort={json.dumps(effort)}"
    ]


def normalize(raw: Path, log: Path, backend: str, returncode: int, timed_out: bool) -> dict:
    """Require a terminal CLI result; a receipt remains independently mandatory."""
    complete = False
    failed = False
    usage = None
    reported_cost = None
    for line in raw.read_text(encoding="utf-8", errors="replace").splitlines():
        try:
            event = json.loads(line)
        except ValueError:
            continue
        if not isinstance(event, dict):
            continue
        if backend == "claude-code" and event.get("type") == "result":
            complete = event.get("subtype") == "success" and not event.get("is_error")
            failed |= not complete
            usage, reported_cost = event.get("usage"), event.get("total_cost_usd")
        elif backend == "codex" and event.get("type") == "turn.completed":
            complete, usage = True, event.get("usage")
        elif event.get("type") in ("error", "turn.failed"):
            failed = True
    ok = complete and not failed and returncode == 0 and not timed_out
    record = {"backend": backend, "billing_mode": "subscription", "cost_usd": None,
              "provider_reported_cost_usd": reported_cost, "usage": usage,
              "completed": ok, "timed_out": timed_out, "returncode": returncode}
    log.write_text(json.dumps({"type": "step_finish" if ok else "error",
                               "subscription": record}) + "\n", encoding="utf-8")
    log.with_suffix(".usage.json").write_text(json.dumps(record, indent=2), encoding="utf-8")
    return record


def run_review(ws, job, prompt: str, log: Path, env: dict[str, str], backend: str):
    from harness.session import SessionResult

    safe_env = clean_env(env)
    status = auth_status(ws.settings, backend, safe_env)
    if not status["subscription_login"]:
        raise ValueError(f"Subscription login required: run {status['login_command']}. No API fallback.")
    folder = ws.report_path(f"native-review/{job.id}/mcp.json").parent
    argv = command(ws.settings, backend, safe_env, folder)
    prompt = prompt.replace("dst-tools_", "mcp__dst_tools__")
    raw = log.with_suffix(".native.jsonl")
    stderr = log.with_suffix(".stderr.txt")
    timeout = min(ws.settings.get_int("max_wall_minutes") * 60,
                  max(1, ws.settings.get_int("final_review_seconds")))
    timed_out = False
    with raw.open("w", encoding="utf-8") as output, stderr.open("w", encoding="utf-8") as errors:
        try:
            result = subprocess.run(argv, input=prompt, text=True, encoding="utf-8",
                                    stdout=output, stderr=errors, cwd=folder, env=safe_env,
                                    timeout=timeout, check=False)
            returncode = result.returncode
        except subprocess.TimeoutExpired:
            timed_out, returncode = True, -1
    normalize(raw, log, backend, returncode, timed_out)
    return SessionResult(returncode, timed_out, log)
