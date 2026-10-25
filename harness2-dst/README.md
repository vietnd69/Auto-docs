# harness2-dst

Harness² ([google-research/harness2](https://github.com/google-research/harness2)) with a
`dst` benchmark whose tasks are pages of `.harness/doc-plan.json`. Used by
`mod-harness generate|update --escalate` and `mod-harness improve` to pick the best
skills/prompts (the editable tree in `.opencode/harness/`).

Setup (once, from the repository root):

```bash
.venv/Scripts/mod-harness setup-harness2      # Linux/macOS: .venv/bin/mod-harness
uv sync --project harness2-dst                # creates harness2-dst/.venv (Python 3.12)
```

`setup-harness2` clones the commit pinned in `PIN` into `vendor/harness2` and applies
`patches/*.patch` (registers `--bench dst`). Model settings for Harness² go in
`vendor/harness2/.env` — point `HARNESS2_SOLVER_MODEL` / `HARNESS2_IMPROVER_MODEL` at
`dst-proxy/<model>` and `HARNESS2_JUDGE_BASE_URL` at `http://127.0.0.1:4141/v1` so every
call goes through the key-rotating proxy.

Harness² documents Linux for benchmark runs; on Windows use WSL if a run fails.
