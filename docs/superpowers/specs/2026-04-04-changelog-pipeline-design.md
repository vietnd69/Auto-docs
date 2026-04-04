# Changelog Pipeline Design

**Date**: 2026-04-04
**Feature**: LLM-generated changelog.md from diff_report.json
**Status**: Approved

---

## Overview

A standalone pipeline that reads `data/diff_report.json`, builds a high-level prompt, calls the LLM once, and prepends a new Markdown section to `changelog.md` at the project root. Each run appends the newest build at the top of the file.

---

## Architecture & Data Flow

```
data/diff_report.json
      │
      ▼
core/changelog/pipeline.py
  ├── load_diff_report()          → reads version info + list of changes
  ├── build_changelog_entry()     → calls prompts.build_changelog_prompt() → calls LLM
  └── prepend_to_changelog()      → inserts new section at top of changelog.md
```

**LLM input** — high-level only, no unified_diff content:
- Version old → new, date
- File list with action + diff_summary ("+N lines, -N lines")
- Aggregate statistics (added/modified/deleted/moved counts)

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

---

## Files & Modules

**New files:**
```
core/src/core/changelog/
├── __init__.py
├── pipeline.py          # main logic: load → prompt → generate → prepend
└── prompts.py           # build_changelog_prompt()
```

**Output file:** `changelog.md` at project root — created automatically if absent.

**Reused from existing codebase (no rewrites):**
- `llm.client` — Ollama Cloud API call with multi-account failover
- `llm.settings.MODEL_UPDATE` — model for update/summary tasks
- `llm.paths.DATA_DIR`, `PROJECT_ROOT` — path constants
- `core.config.VERSION`, `TODAY_DATE` — version info
- `core.utils.shutdown` — Ctrl+C safe handling

**`pipeline.py` functions:**
1. `load_diff_report() -> dict | None` — reads `data/diff_report.json`
2. `build_changelog_entry(report: dict) -> str | None` — builds prompt, calls LLM, returns markdown string
3. `prepend_to_changelog(entry: str, changelog_path: Path)` — inserts section at top of file
4. `main()` — orchestrates all steps, handles `--dry-run` CLI arg

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
...

OUTPUT FORMAT: Markdown section starting with ## Build {new_ver}
- Write a 3-5 sentence "Highlights" paragraph identifying the most significant changes
- List files grouped by action (Added / Modified / Deleted / Moved)
- Be concise. Do not speculate beyond what file names and diff stats suggest.
```

---

## Error Handling

| Condition | Behavior |
|---|---|
| `diff_report.json` missing | Print error, exit |
| LLM returns empty/None | Print warning, exit with code 1, no file written |
| `changelog.md` not found | Create new file with `# DST API Changelog` header |
| Same build version already logged | Skip with "Already logged" message |
| `--dry-run` flag | Print prompt + LLM preview, do not write file |
| Ctrl+C | Graceful stop via `shutdown.request_stop()` |

---

## Entry Point

```bash
# Generate and prepend changelog entry
.venv/Scripts/python -m core.changelog

# Preview without writing
.venv/Scripts/python -m core.changelog --dry-run
```

---

## Constraints & Decisions

- **Single LLM call** — high-level summary only; no per-file deep analysis
- **No validation step** — output is a short summary, no MDX docsite requirements
- **Model**: `MODEL_UPDATE` (already tuned for update/summary tasks)
- **No chunking** — prompt is small (file list + diff_summary strings, well under 16K tokens)
- **Idempotent** — re-running on same diff_report skips if build already in changelog
