# Auto-docs

[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![uv](https://img.shields.io/badge/package%20manager-uv-blueviolet)](https://docs.astral.sh/uv/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Automated API documentation generator for **Don't Starve Together** (DST) Lua mods. Analyzes Lua source code and generates comprehensive Markdown documentation using AI models via Ollama Cloud API.

> Hệ thống tự động sinh API documentation cho Lua mods của game Don't Starve Together. Phân tích source code Lua và tạo tài liệu Markdown bằng AI thông qua Ollama Cloud API.

## Features

- 🔄 **Smart chunked processing** — Handles large Lua files (16K+ tokens) with hierarchical merging
- 🔍 **RAG-powered context** — Vector search (ChromaDB) for cross-file reference analysis
- ✅ **Built-in validation** — Format checks (MDX, YAML frontmatter) + AI-powered content review
- 📝 **Changelog generation** — Auto-generates changelogs from diff reports
- 🔀 **Diff watcher** — Detects Lua file changes between game updates
- ⚡ **Multi-account load balancing** — Round-robin across Ollama API keys with auto-failover
- 💾 **Checkpoint & resume** — Resume interrupted chunked processing
- 🛑 **Graceful shutdown** — Safe Ctrl+C handling

## Requirements

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (package manager)
- Node.js (for MDX validation)
- Ollama Cloud API keys

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/vietnd69/Auto-docs.git
cd Auto-docs
uv sync
```

### 2. Configure environment

```bash
cp .env.template .env
# Fill in your Ollama API keys
```

```env
TOTAL_ACCOUNT=2
ACCOUNT_1=your-ollama-api-key-1
ACCOUNT_2=your-ollama-api-key-2
```

### 3. Configure settings (optional)

```bash
cp config.toml.template config.toml
# Adjust model names, token thresholds, timing, etc.
```

> **Important** — This project uses a **uv workspace** with Python 3.11. Always use `.venv/Scripts/python` (Windows) or `.venv/bin/python` (Linux/Mac) instead of system `python`.

## Usage

### Generate documentation

```bash
# Generate docs for all .lua files in dst-scripts/
.venv/Scripts/mod-document

# Generate docs for a specific file (always overwrites)
.venv/Scripts/mod-document dst-scripts/components/combat.lua

# Generate all + overwrite existing docs
.venv/Scripts/mod-document -f
```

### Validate documentation

```bash
# Full validation (format + content)
.venv/Scripts/python -m validator

# Single file
.venv/Scripts/python -m validator dst-api-webdocs/docs/components/combat.md

# Format only
.venv/Scripts/python -m validator --format-only

# Content only (LLM review)
.venv/Scripts/python -m validator --content-only
```

### Auto-update from diff report

Re-renders documentation for changed files through the full pipeline (render → validate):

```bash
# Re-render docs for files in diff report (added/modified/moved)
.venv/Scripts/python -m core.update.docs

# Preview prompts without calling LLM
.venv/Scripts/python -m core.update.docs --dry-run

# Process only new files
.venv/Scripts/python -m core.update.docs --filter added

# Skip validation step
.venv/Scripts/python -m core.update.docs --no-validate
```

### Generate changelog

Reads `data/diff_report.json`, calls LLM to write a summary, and prepends to `dst-api-webdocs/change-log.md`:

```bash
# Generate + write (idempotent — skips if build already logged)
.venv/Scripts/python -m core.changelog

# Preview prompt without calling LLM
.venv/Scripts/python -m core.changelog --dry-run
```

### Diff watcher

Detects `.lua` file changes between game updates. Results are written to `data/diff_report.json` and `data/diff_log.txt`, and the vector store is automatically updated.

**Standard workflow for new game updates:**

1. Copy new Lua source into `dst-scripts/` (manual)
2. Update `data/version_log.txt`:
   ```
   now version: <new_version>
   previous version: <old_version>
   ```
3. Run watcher:
   ```bash
   .venv/Scripts/mod-watcher
   ```

Output categorizes changes into: `ADDED`, `MODIFIED`, `DELETED`, `MOVED`.

### RAG / Vector search

Index Lua source into ChromaDB and search by vector similarity (local embedding, no LLM calls):

```bash
# Index only (no server) — indexes new/changed files only
.venv/Scripts/python -m rag.indexer

# Start search server (indexes first, then serves at localhost:8000)
.venv/Scripts/python -m rag.search
```

REST API:

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{"question": "combat damage calculation"}'

# Swagger UI for manual testing: http://localhost:8000/docs
```

> **Note:** `mod-watcher` automatically calls `rag.indexer` after scanning if changes are detected — you usually don't need to run `rag.indexer` manually.

### Run tests

```bash
# Full workspace
.venv/Scripts/pytest

# Per package
.venv/Scripts/pytest core/tests/
.venv/Scripts/pytest llm/tests/
.venv/Scripts/pytest rag/tests/
.venv/Scripts/pytest prompts/tests/
.venv/Scripts/pytest validator/tests/
.venv/Scripts/pytest watcher/tests/
```

## Architecture

This project uses a **uv workspace** with 6 packages:

```
Auto-docs/
├── core/        — Main pipeline, orchestration, CLI entry point
├── llm/         — Ollama Cloud API client, token counting, multi-account failover
├── rag/         — Reference extraction, content analysis from Lua source
├── prompts/     — Template generation for LLM prompts
├── validator/   — Output quality checks (format + content via LLM)
├── watcher/     — Change detection between dst-scripts versions
├── skills/      — Markdown skill files → injected into prompts
├── data/        — Runtime tracking (diff reports, version log)
├── dst-scripts/ — Lua source code (input, git-excluded)
└── dst-api-webdocs/docs/ — Generated Markdown documentation (output)
```

### Dependency graph

```
core ──→ llm
  ├───→ rag ──→ llm
  ├───→ prompts ──→ llm
  └───→ validator ──→ llm, rag
watcher ──→ rag
```

### Doc generation pipeline

1. **File Discovery** — Scans `dst-scripts/` for `.lua` files
2. **Reference Analysis** — Extracts cross-file dependencies (require, components)
3. **Token Counting** — Determines processing strategy based on prompt size
4. **Processing**:
   - **Standard** (< 16K tokens): Direct LLM call
   - **Chunked** (≥ 16K tokens): Split → analyze per chunk → merge hierarchically
5. **Output** — Writes `.md` files to `dst-api-webdocs/docs/`

### Validation pipeline

Runs after doc generation (or independently):

1. **Format check** — YAML frontmatter, MDX syntax, emoji rules
2. **Content check** — LLM review → auto-fix → approve loop:
   - **Standard** (< 32K tokens Lua source): Reviews entire doc
   - **Chunked** (≥ 16K tokens): Per-section review with Lua context extraction

## Configuration

All settings are centralized in `config.toml` (loaded by `llm/src/llm/settings.py`). Override any setting with `MOD_DOC_<SECTION>_<KEY>` environment variables.

See [`config.toml.template`](config.toml.template) for all available options.

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
