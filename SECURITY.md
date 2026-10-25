# Security Policy

## Supported versions

This project has no versioned releases. Only the latest commit on `main` receives
security fixes.

| Branch | Supported |
|---|---|
| `main` | ✅ |
| any other branch | ❌ |

## Reporting a vulnerability

**Do not open a public issue for security problems.**

Report privately with GitHub's
[private vulnerability reporting](https://github.com/vietnd69/Auto-docs/security/advisories/new)
(*Security → Report a vulnerability*). Include:

- the affected file(s) and commit,
- steps to reproduce or a proof of concept,
- the impact you expect (e.g. key leak, file write outside the repo, command execution).

What to expect:

- acknowledgement within **7 days**;
- an assessment and fix plan within **30 days**;
- credit in the advisory if you want it.

## Scope

In scope:

- **Secret handling** — Ollama Cloud and other API keys read from `.env`
  (`ACCOUNT_*`, `DEEPSEEK_API_KEY`, `OPENROUTER_API_KEY`).
- **`ollama-proxy`** (`harness/src/harness/proxy.py`) — the local OpenAI-compatible proxy
  that forwards requests with those keys.
- **`dst-tools` MCP server** (`harness/src/harness/mcp_server.py`, `harness/src/harness/tools/`)
  — tools that read source files and write documentation drafts.
- **OpenCode configuration** (`.opencode/`), including tool permissions and the
  `budget.ts` plugin.
- Anything that executes subprocesses: git access (`harness/src/harness/gitsource.py`),
  MDX validation via Node.js, OpenCode and Harness² launches.

Out of scope:

- Vulnerabilities in upstream projects (Ollama, OpenCode, Harness², Docusaurus,
  Python/Node packages). Report those upstream. We will still update a pinned
  dependency once a fix is available.
- Accuracy problems in the generated documentation. Use a normal issue.
- The Lua game scripts in `dst-scripts/`, which belong to Klei Entertainment.

## Security design

These rules are part of the design (see `docs/2026-10-25-opencode-harness-design.md`,
§3.2, ISO/IEC 27001 Annex A 8.28 / ISO/IEC 27034 mapping). A change that breaks one
of them is a security bug.

- **Secrets stay local.** Keys are read only from `.env` (git-ignored; `.env.template`
  holds no values). They must never be logged, written to `.cache/debug_prompts/`, put
  into prompts, or committed.
- **Loopback only.** `ollama-proxy` refuses to bind to anything other than
  `127.0.0.1`, `localhost` or `::1`.
- **Path confinement.** Every path an agent passes to a tool is normalised and
  rejected if it escapes its root (`harness/src/harness/safepath.py`). Source reads go
  through `git show <sha>:<path>`.
- **No shell.** Subprocesses are started with argument lists, never `shell=True`.
- **Least privilege for agents.** OpenCode's `bash`, `edit`, `write`, `patch`,
  `webfetch` and `websearch` tools are disabled. Agents can only change documents
  through `dst-tools`, and every write goes through deterministic checks.
- **Bounded runs.** Each job has a step budget (`budget.ts`), a token budget (proxy)
  and a wall-clock limit, so a misbehaving model cannot run up cost indefinitely.
- **Pinned dependencies.** Python packages are locked in `uv.lock` /
  `harness2-dst/uv.lock`, Node packages in `package-lock.json`, and Harness² at the
  commit in `harness2-dst/PIN`.

## Running the project safely

- Keep `.env` out of version control and give each Ollama account key only the access
  it needs.
- Harness² warns that its executors have unrestricted network access. Run
  `mod-harness improve` / `--escalate` only on a machine where that is acceptable.
- Treat generated drafts as untrusted model output until `mod-harness page verdict`
  reports `PASS`.

## Dependency audits

Run before releasing changes that touch dependencies:

```bash
.venv/Scripts/pip-audit --skip-editable      # Linux/macOS: .venv/bin/pip-audit
npm audit
```

Known open advisories (from `pip-audit` on 2026-10-25) in versions pinned by
`uv.lock`: `urllib3` 2.6.3, `requests` 2.32.5, `pytest` 9.0.2, `anyio` 4.12.1,
`certifi` 2026.2.25, `filelock` 3.25.2, `pygments` 2.19.2, `opentelemetry-api` 1.40.0.
Upgrading them is tracked as follow-up work.
