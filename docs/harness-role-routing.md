# Multi-provider documentation flow

The harness uses these defaults (override in `[harness]` in `config.toml`, or with
`MOD_DOC_HARNESS_<KEY>` environment variables):

| Role | Model | Setting |
| --- | --- | --- |
| writer-escalation only | anthropic/claude-sonnet-5-5 | claude_model |
| orchestrator, writer | deepseek/deepseek-flash | deepseek_model |
| reviewer | Ollama gpt-oss:120b | reviewer_model |
| planner | Ollama gpt-oss:120b | planner_model |
| reflector | Ollama gemma4:31b | reflector_model |
| writer-experimental (opt-in) | Ollama beam | experimental_writer_model |

`dst-proxy/reviewer`, `dst-proxy/planner`, `dst-proxy/reflector`, and `dst-proxy/writer-experimental` are
local routing aliases, not upstream model IDs. The proxy translates them before sending
requests. Planner and reviewer fall back to DeepSeek on Ollama quota/access responses (402/403/429).
The writer uses OpenCode's native DeepSeek provider. Planner fallback disables DeepSeek
thinking so an Ollama conversation can continue without DeepSeek-specific reasoning history.
Reflector does not spend paid-provider credits on fallback. A failed reflector is saved
under `.harness/reports/deferred-reflections/` for manual retry and never changes the page
verdict. There is no automatic replay of deferred reflections yet.

## Credentials and startup

Keep keys in the ignored root `.env`, or export them in the shell:

- `CLAUDE_API_KEY` or `ANTHROPIC_API_KEY` (the latter takes precedence).
- `DEEPSEEK_API_KEY`.
- `OLLAMA_API_KEY` or existing `ACCOUNT_1`. Only one Ollama account is used.

Environment values take precedence over `.env`. No secret is written into OpenCode JSON.
The runner supplies all role overrides through `OPENCODE_CONFIG_CONTENT`, including when
running a candidate Harness² tree. Use the harness CLI so `.env` and runtime overrides
are loaded; launching OpenCode directly requires exporting keys yourself.

```powershell
uv sync --package mod-document-harness --group dev
npm ci
uv run --package mod-document-harness mod-harness sync-opencode
uv run --package mod-document-harness mod-harness roles
```

Start **one** proxy process, in a separate terminal:

```powershell
uv run --package mod-document-harness ollama-proxy
```

The proxy listens on loopback port 4141. All Ollama requests share a single slot, held
until streaming ends. Do not start multiple proxies for the same free account. The queue
defaults to one page at a time (`parallel = 1`). Claude and DeepSeek requests go directly
to their providers; the proxy's token accounting covers only requests routed through it,
including planner/reviewer fallback. It is not a global spending cap for all providers.

## Workflow and guardrails

The orchestrator delegates writing to DeepSeek and semantic review to Ollama gpt-oss:120b, including
small pages. Deterministic checks run before semantic review. Tasks use stable descriptions:

1. `write:<group>`: initial draft for a group of symbols.
2. `repair:<group>`: at most two repair calls for that same group.
3. `escalate:<group>`: at most one Claude repair after those two calls.

The budget plugin rejects extra repair/escalation calls. Group identity is supplied by the
orchestrator; prompts prohibit changing the group id to evade the budget. Beam is available
as `writer-experimental` only for explicitly requested experiments, not automatic fallback.
Checks plus ledger remain the authority on PASS/FAIL.

## Validation boundaries

Model-list authentication verifies IDs/key access, not generation quality or credit balance.
Use an isolated `run-page --state-dir ...` without `--publish` for a real-model trial.
The source clone must contain the plan's baseline revision. Provider routing does not fix
the separately identified legacy metadata, failed-update checkpoint, queue retry, or
concurrent sync-state issues; do not start a bulk publishing run until those are fixed.

Claude is reserved for bounded writer escalation after two failed repair calls; ordinary pages make no Claude calls. Reviewer fallback remains a separate agent session even when it shares the DeepSeek model with the writer. Ollama free credits are limited; proxy cost zero does not establish remaining quota or free billing.
