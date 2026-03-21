# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Local 
`D:/code/mod-document`

## RAG Search — mod-document

Use the `local-rag` MCP server to search this codebase.
- **workspace_id**: `mod-document`
- **Path**: D:\code\mod-document

When asked about code in this project, call:
- `search_code(query, workspace_id="mod-document")` — semantic search
- `lookup_symbol(symbol_name=..., workspace_id="mod-document")` — find class/function
- `get_file_context(file_path=..., workspace_id="mod-document")` — full file content

## Environment

Project sử dụng **uv workspace** với Python 3.11 (`.venv` trong project root).

**QUAN TRỌNG — luôn dùng `uv run` thay cho `python` trực tiếp:**
- `uv sync` — cài dependencies
- `uv run mod-document` — chạy document generation (thay cho `python main.py`)
- `uv run pytest` — chạy tests
- `uv run python ...` — chạy bất kỳ script Python nào

KHÔNG BAO GIỜ gọi `python` hay `python3` trực tiếp — luôn prefix bằng `uv run` để đảm bảo dùng đúng `.venv` của project (Python 3.11), tránh dùng nhầm system Python.

## Project Overview

This is a Python-based document generation system that automatically creates API documentation for Lua-based Don't Starve Together (DST) game mods. The system analyzes Lua source code and generates comprehensive Markdown documentation using AI models via the Ollama API.

## Core Architecture

### Directory Layout

```
mod-document/
├── core/              # Pipeline chính, orchestration, CLI entry point
├── llm/               # Ollama Cloud API client, token counting, multi-account failover
├── rag/               # Trích xuất references, content analysis từ Lua source
├── prompts/           # Template generation cho LLM prompts
├── validator/         # Kiểm tra chất lượng output (format + content via LLM)
├── watcher/           # Phát hiện thay đổi giữa các version dst-scripts
├── skills/            # Markdown skill files (conventions, few-shot examples) → inject vào prompts
├── data/              # Runtime tracking (diff_tracker.json, version_log.txt, diff_report.json)
├── dst-scripts/       # Input: Lua source code (git-excluded, copy thủ công)
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
- `llm/src/llm/paths.py`: Base paths — `BASE_LUA_DIR` (dst-scripts/), `BASE_DOCS_DIR` (dst-api-webdocs/docs/)
- `llm/src/llm/client.py`: Multi-account Ollama Cloud API management with automatic failover and round-robin load balancing
- `core/src/core/config.py`: Model settings, version, timing constants

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

**Validation (validator/):**
- `validator/src/validator/format/checks.py`: YAML frontmatter, MDX syntax, emoji checks
- `validator/src/validator/format/validate_mdx.mjs`: Node.js MDX compilation validation (requires Node.js)
- `validator/src/validator/content/loop.py`: Iterative LLM review → fix → approve loop
- `validator/src/validator/pipeline.py`: Full pipeline orchestration (format + content)

## Common Development Commands

### Running the System

```bash
# Sinh docs cho toàn bộ file .lua (bỏ qua file đã có docs)
uv run mod-document

# Sinh docs cho 1 file cụ thể (luôn ghi đè)
uv run mod-document dst-scripts/components/combat.lua

# Sinh toàn bộ + ghi đè file đã có docs
uv run mod-document -f

# Validate docs (format + content)
uv run python -m validator                           # Toàn bộ docs
uv run python -m validator path/to/file.md           # 1 file
uv run python -m validator --format-only             # Chỉ format
uv run python -m validator --content-only            # Chỉ content

# Auto-update docs từ diff report (added/modified/deleted/moved)
uv run python -m core.update.docs
uv run python -m core.update.docs --dry-run          # Xem prompt, không gọi LLM
uv run python -m core.update.docs --filter added     # Chỉ xử lý file mới

# Chạy diff watcher (phát hiện thay đổi giữa các version)
uv run mod-watcher

# Test
uv run pytest                    # Toàn workspace
uv run pytest core/tests/        # Từng package
uv run pytest llm/tests/
uv run pytest rag/tests/
uv run pytest prompts/tests/
uv run pytest validator/tests/
uv run pytest watcher/tests/
```

## Architecture Notes

### Key Token Thresholds

- `PROMPT_TOKEN_LIMIT = 16,000` — Triggers chunked pipeline
- `MERGE_TOKEN_LIMIT = 20,000` — Triggers hierarchical merge (vs rolling)
- `CONTEXT_RESERVE = 7,000` — Reserved for connected content stubs
- `STUB_FULL_THRESHOLD = 400` — Files ≤400 tokens included in full, larger get compressed stubs
- `OLLAMA_NUM_CTX = 256,000` — Model context window

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

- `.env.template` có sẵn — copy thành `.env` và điền API keys
- Validator MDX check cần **Node.js** (chạy `validate_mdx.mjs` qua subprocess)
- `dst-scripts/` là git-excluded — cần copy Lua source thủ công
- Output docs ghi vào `dst-api-webdocs/docs/` (không phải `docs/`)
- Data tracking files (`data/diff_tracker.json` ~72MB) cũng git-excluded