# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Environment

Project uses **uv workspace** with Python 3.11 (`.venv` in project root).

**IMPORTANT — always use `.venv` directly, NEVER use `python` or `uv run python` directly:**
- `uv sync` — install dependencies (first time or after changing deps)
- `.venv/Scripts/mod-document` — run document generation
- `.venv/Scripts/pytest` — run tests
- `.venv/Scripts/python -m <module>` — run any Python module

NEVER call `python`, `python3`, or `uv run python` directly — always use `.venv/Scripts/python` to ensure the correct Python 3.11, avoiding system Python.

## Project Overview

This is a Python-based document generation system that automatically creates API documentation for Lua-based Don't Starve Together (DST) game mods. The system analyzes Lua source code and generates comprehensive Markdown documentation using AI models via the Ollama API.

## Core Architecture

### Directory Layout

```
Auto-docs/
├── core/              # Main pipeline, orchestration, CLI entry point
├── llm/               # Ollama Cloud API client, token counting, multi-account failover
├── rag/               # Reference extraction, content analysis from Lua source
├── prompts/           # Template generation for LLM prompts
├── validator/         # Output quality checks (format + content via LLM)
├── watcher/           # Change detection between dst-scripts versions
├── skills/            # Markdown skill files (conventions, few-shot examples) → injected into prompts
├── data/              # Runtime tracking (diff_tracker.json, version_log.txt, diff_report.json) — git-excluded
├── dst-scripts/       # Input: Lua source code (git-excluded, copy manually)
├── dst-api-webdocs/docs/  # Output: Generated Markdown documentation
└── .cache/            # compression_cache/ + chunked_checkpoints/
```

### Document Generation Pipeline

**Main Flow (core/src/core/main.py):**
1. **File Discovery**: Scans `dst-scripts/` directory for `.lua` files
2. **Reference Analysis**: Extracts cross-file dependencies and connected content
3. **Token Counting**: Determines if chunked processing is needed (prompt > 16K tokens)
4. **Processing Strategy**:
   - **Standard Pipeline**: Direct LLM call for smaller files via `core/src/core/pipeline/standard.py`
   - **Chunked Pipeline**: Multi-stage processing via `core/src/core/pipeline/chunked.py` for large files

**Chunked Processing (core/src/core/pipeline/chunked.py):**
- Splits large files into manageable chunks
- Generates analysis for each chunk independently
- Hierarchically merges results into final documentation
- Includes checkpoint system for resuming interrupted processing

### Key Components

**Configuration & Paths:**
- `llm/src/llm/settings.py`: **Central config** — all typed constants, loaded from `config.toml` + `MOD_DOC_*` env override
- `llm/src/llm/paths.py`: Base paths — `BASE_LUA_DIR` (dst-scripts/), `BASE_DOCS_DIR` (dst-api-webdocs/docs/)
- `llm/src/llm/client.py`: Multi-account Ollama Cloud API management with automatic failover and round-robin load balancing
- `core/src/core/config.py`: `CHECKPOINT_DIR`, `VERSION`, `TODAY_DATE`, `get_shared_file_tree()` only — constants moved to `llm.settings`

**Content Analysis:**
- `rag/src/rag/content.py`: Extracts function signatures and connected code
- `rag/src/rag/docs.py`: Handles Lua reference extraction and file reading
- `prompts/src/prompts/standard.py` & `prompts/src/prompts/chunked.py`: Template generation for LLM prompts
- `prompts/src/prompts/skills_loader.py`: Loads skill .md files from `skills/` directory

**Processing Modules:**
- `core/src/core/pipeline/chunking.py` + `llm/src/llm/tokens.py`: Token counting and chunking logic
- `core/src/core/pipeline/standard.py`: Standard document generation
- `core/src/core/pipeline/chunked.py`: Multi-stage chunked processing with hierarchical merging
- `core/src/core/update/docs.py`: Auto-update docs based on diff report (added/modified/deleted/moved)
- `core/src/core/changelog/pipeline.py`: Changelog generation — reads `data/diff_report.json`, calls LLM, prepends entry to `dst-api-webdocs/change-log.md`, runs MDX autofix
- `core/src/core/changelog/prompts.py`: `build_changelog_prompt()` — formats diff report into LLM prompt

**Validation (validator/):**
- `validator/src/validator/pipeline.py`: Full pipeline orchestration (format + content), routes chunked files (≥32K tokens) to per-section loop
- `validator/src/validator/format/checks.py`: YAML frontmatter, MDX syntax, emoji checks
- `validator/src/validator/format/autofix.py`: Auto-fix common format issues
- `validator/src/validator/format/validate_mdx.mjs`: Node.js MDX compilation validation (requires Node.js)
- `validator/src/validator/content/loop.py`: Iterative LLM review → fix → approve loop (standard files)
- `validator/src/validator/content/chunked.py`: Per-section content validation for large files (≥32K tokens)
- `validator/src/validator/content/sections.py`: `DocSection`, `split_md_sections`, `extract_function_names`, `extract_lua_context`
- `validator/src/validator/content/reviewer.py`: `ReviewResult`, `parse_review_response`
- `validator/src/validator/content/writer.py`: `Patch`, `apply_patches`, `parse_writer_response`
- `validator/src/validator/content/prompts.py`: `build_section_reviewer_prompt`, `build_section_writer_prompt`
- `validator/src/validator/update/validate_update.py`: Validate docs after auto-update from diff report

## Common Development Commands

### Running the System

```bash
# IMPORTANT: Use .venv/Scripts/python (not python or uv run python directly)
# Project uses uv workspace with Python 3.11 (.venv in project root)

# Generate docs for all .lua files (skip files that already have docs)
.venv/Scripts/mod-document

# Generate docs for a specific file (always overwrites)
.venv/Scripts/mod-document dst-scripts/components/combat.lua

# Generate all + overwrite existing docs
.venv/Scripts/mod-document -f

# Validate docs (format + content)
.venv/Scripts/python -m validator                           # All docs
.venv/Scripts/python -m validator path/to/file.md           # Single file
.venv/Scripts/python -m validator --format-only             # Format only
.venv/Scripts/python -m validator --content-only            # Content only

# Auto-update docs from diff report (re-render full pipeline)
.venv/Scripts/python -m core.update.docs
.venv/Scripts/python -m core.update.docs --dry-run          # Preview prompt, no LLM call
.venv/Scripts/python -m core.update.docs --filter added     # Only new files
.venv/Scripts/python -m core.update.docs --no-validate      # Skip validation

# Generate changelog from diff report (prepend to dst-api-webdocs/change-log.md)
.venv/Scripts/python -m core.changelog             # Call LLM + write
.venv/Scripts/python -m core.changelog --dry-run   # Preview prompt, no write

# Run diff watcher (detect changes between versions)
.venv/Scripts/mod-watcher

# Test
.venv/Scripts/pytest                    # Full workspace
.venv/Scripts/pytest core/tests/        # Per package
.venv/Scripts/pytest llm/tests/
.venv/Scripts/pytest rag/tests/
.venv/Scripts/pytest prompts/tests/
.venv/Scripts/pytest validator/tests/
.venv/Scripts/pytest watcher/tests/
```

## Architecture Notes

### Key Token Thresholds

All constants now in `llm/src/llm/settings.py` (loaded from `config.toml`, override with `MOD_DOC_*` env vars):
- `DEBUG_PROMPTS = 0` — Set `MOD_DOC_DEBUG_PROMPTS=1` to dump full prompts/responses to `.cache/debug_prompts/`
- **`_get()` gotcha**: NEVER use `bool` as default — `bool("false") == True`. Use `int` (0/1) instead.
- `PROMPT_TOKEN_LIMIT = 16,000` — Triggers chunked doc generation pipeline
- `MERGE_TOKEN_LIMIT = 20,000` — Triggers hierarchical merge (vs rolling)
- `CONTEXT_RESERVE = 7,000` — Reserved for connected content stubs
- `STUB_FULL_THRESHOLD = 400` — Files ≤400 tokens included in full, larger get compressed stubs
- `CHUNKED_TOKEN_THRESHOLD = 16,000` — Triggers per-section content validation (validator)
- `VALIDATOR_MAX_ITERATIONS = 10`, `VALIDATOR_LOOP_MAX_ITERATIONS = 5`, `MDX_NODE_TIMEOUT = 20`, `LUA_CONTEXT_TOKENS = 8,000`
- `OLLAMA_NUM_CTX = 256,000` — Model context window
- `MODEL_MAIN = "qwen3.5:cloud"`, `MODEL_UPDATE`, `MODEL_EMBED`, `MODEL_COMPRESS`

### Connected Content System

Files are analyzed for dependencies using:
- Import pattern matching in Lua code (`require("path")`, `components.X:FuncName()`)
- Function signature extraction from referenced files
- Context-aware content inclusion with token budget management

### Prompt Engineering

- `prompts/src/prompts/standard.py`: Standard single-pass documentation generation
- `prompts/src/prompts/chunked.py`: Multi-stage prompts for chunk analysis and merging
- `prompts/src/prompts/pre_synthesis.py`: Pre-merge synthesis (YAML frontmatter + section summaries)
- `prompts/src/prompts/update.py`: Prompts for doc updates based on diff report
- `skills/`: Markdown skill files injected into prompts (conventions, few-shot examples, quality rules)

### Error Handling & Resilience

- Automatic retry logic for LLM failures (non-rate-limit errors)
- Checkpoint system for long-running chunked operations (`.cache/chunked_checkpoints/`)
- Rate limit detection and automatic account switching
- Graceful Ctrl+C handling with safe shutdown (`core/src/core/utils/shutdown.py`)
- `interruptible_sleep()` — Sleep that respects stop_requested flag

## Environment Notes

- `.env.template` provided — copy to `.env` and fill in API keys
- Validator MDX check requires **Node.js** (runs `validate_mdx.mjs` via subprocess)
- `dst-scripts/` is git-excluded — copy Lua source manually
- Output docs are written to `dst-api-webdocs/docs/` (not `docs/`)
- Data tracking files in `data/` are git-excluded (runtime artifacts)