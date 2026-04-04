# Changelog Pipeline Design

**Date**: 2026-04-04
**Feature**: LLM-generated changelog.md from diff_report.json
**Status**: Approved

---

## Overview

A standalone pipeline that reads `data/diff_report.json`, builds a high-level prompt, calls the LLM once, and prepends a new Markdown section to `changelog.md` at the project root. Each run inserts the newest build at the top of the file.

---

## Architecture & Data Flow

```
data/diff_report.json
      │
      ▼
core/changelog/pipeline.py
  ├── load_diff_report()          → reads version info + list of changes
  ├── build_changelog_entry()     → calls prompts.build_changelog_prompt() → calls LLM (think=False)
  └── prepend_to_changelog()      → inserts new section at top of changelog.md
```

**LLM input** — high-level only; `unified_diff` field is explicitly excluded from the prompt:
- Version strings: `report["version"]["old"]` and `report["version"]["new"]` (NOT `core.config.VERSION`)
- Date from `report["date"]`
- File list with action + `diff_summary` string per entry
- Aggregate statistics (added/modified/deleted/moved counts)

**File list rendering per action:**
- `added` / `modified`: `[action]    filepath (diff_summary)`
- `deleted`: `[deleted]   filepath (removed)`
- `moved`: `[moved]     old_path → new_path (diff_summary or "(no content changes)")`

`diff_summary` may be absent for exact-match `moved` entries (`content_changed: False`); use `c.get("diff_summary", "(no content changes)")` as fallback.

**LLM output** — a single Markdown section:
```markdown
## Build 718694 — 2026-03-23

> 714014 → 718694 | 51 changes: 2 added, 49 modified, 0 deleted, 0 moved

### Highlights
3-5 sentence summary of the most significant changes inferred from file names and diff stats.

### Changes
- **Added**: `prefabs/w_radio.lua`, `stategraphs/SGcritter_bulbin.lua`
- **Modified** (49 files): `brains/crittersbrain.lua` (+2/-0), ...
```

The heading `## Build {new_ver}` uses the version string from `report["version"]["new"]` (e.g., `718694`), not a sequential integer counter.

---

## Files & Modules

**New files:**
```
core/src/core/changelog/
├── __init__.py
├── pipeline.py          # main logic: load → prompt → generate → prepend
└── prompts.py           # build_changelog_prompt()
```

**Output file:** `changelog.md` at project root — created automatically if absent with `# DST API Changelog` header.

**Reused from existing codebase (no rewrites):**
- `llm.client.ollama_chat` — Ollama Cloud API call with multi-account failover (use `ollama_chat()`, not `client.chat()` directly)
- `llm.settings.MODEL_UPDATE` — model for update/summary tasks
- `llm.paths.DATA_DIR` — `str` constant; wrap with `Path()` before path operations
- `llm.paths.PROJECT_ROOT` — already a `Path` object; use directly
- `core.utils.shutdown` — Ctrl+C safe handling

**`pipeline.py` functions:**
1. `load_diff_report() -> dict | None` — reads `Path(DATA_DIR) / "diff_report.json"`
2. `build_changelog_entry(report: dict) -> str | None` — builds prompt, calls LLM with `think=False`, strips/cleans output, returns markdown string
3. `prepend_to_changelog(entry: str, changelog_path: Path)` — inserts section at top of file
4. `main()` — orchestrates all steps, registers `signal.SIGINT` handler, handles `--dry-run` CLI arg

---

## Prompt Design

```
You are a technical writer documenting changes in the Don't Starve Together game API.
Given the list of changed files between two game builds, write a concise, high-level
changelog entry in Markdown.

BUILD: {old_ver} → {new_ver} | DATE: {date}

STATISTICS:
- Added: N files
- Modified: N files
- Deleted: N files
- Moved: N files

CHANGED FILES:
[added]    prefabs/w_radio.lua (+102 lines)
[added]    stategraphs/SGcritter_bulbin.lua (new file)
[modified] brains/crittersbrain.lua (+2 lines, -0 lines)
[moved]    old/path.lua → new/path.lua (+3 lines, -0 lines)
...

OUTPUT FORMAT: Markdown section starting with ## Build {new_ver}
- Write a 3-5 sentence "Highlights" paragraph identifying the most significant changes
- List files grouped by action (Added / Modified / Deleted / Moved)
- Be concise. Do not speculate beyond what file names and diff stats suggest.
```

**LLM call**: `ollama_chat(..., think=False)`. Response is read from the return value of `ollama_chat()` as `response["message"]["content"]` (no think-block stripping needed when `think=False`).

---

## Error Handling

| Condition | Behavior | Exit Code |
|---|---|---|
| `diff_report.json` missing | Print error, exit | 1 |
| LLM returns empty/None | Print warning, do not write file, exit | 1 |
| `changelog.md` not found | Create with `# DST API Changelog` header, then write | — |
| Same build already logged | Print "Already logged", exit | 0 |
| `--dry-run` flag | Skip idempotency check, print rendered prompt, LLM NOT called, no write | 0 |
| Ctrl+C | `shutdown.request_stop()`, exit | 1 |

**Idempotency check**: scan `changelog.md` for the exact heading `## Build {new_ver}` (where `new_ver = report["version"]["new"]`). Skipped entirely when `--dry-run` is set — dry-run always prints the prompt regardless of existing changelog state.

---

## Entry Point

```bash
# Generate and prepend changelog entry
.venv/Scripts/python -m core.changelog

# Preview prompt without calling LLM or writing file
.venv/Scripts/python -m core.changelog --dry-run
```

`main()` registers a `signal.SIGINT` handler (same pattern as `core/update/docs.py`). Session logging via `_TeeWriter` is intentionally omitted — changelog runs are short single-call operations, not long multi-file sessions.

---

## Constraints & Decisions

- **Single LLM call** — high-level summary only; no per-file deep analysis
- **No validation step** — output is a short summary, no MDX docsite requirements
- **Model**: `MODEL_UPDATE` (already tuned for update/summary tasks)
- **`think=False`** — chain-of-thought not needed for a short summarization task
- **No chunking** — prompt is small (`diff_summary` strings only, no `unified_diff`; well under 16K tokens)
- **`unified_diff` excluded** — only `diff_summary` ("+N lines, -N lines") is included in prompt
- **Version source**: always `report["version"]["old/new"]`, never `core.config.VERSION`
- **Path construction**: `DATA_DIR` is `str` → wrap with `Path()`; `PROJECT_ROOT` is already a `Path`
- **`ollama_chat()`** — use the high-level wrapper, not `client.chat()` directly
- **Idempotent** — re-running skips if `## Build {new_ver}` heading exists; dry-run always prints prompt regardless
- **No session log** — `_TeeWriter` omitted intentionally (short operation, not worth a log file)
- **Ctrl+C exit code**: 1 — matches `core/update/docs.py` behavior
