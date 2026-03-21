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
project sử dụng uv workspace
chạy: `uv sync` để cài dependencies
chạy: `uv run mod-document` thay cho `python main.py`

## Project Overview

This is a Python-based document generation system that automatically creates API documentation for Lua-based Don't Starve Together (DST) game mods. The system analyzes Lua source code and generates comprehensive Markdown documentation using AI models via the Ollama API.

## Core Architecture

### Document Generation Pipeline

**Main Flow (core/src/core/main.py):**
1. **File Discovery**: Scans `dst-scripts/` directory for `.lua` files
2. **Reference Analysis**: Extracts cross-file dependencies and connected content
3. **Token Counting**: Determines if chunked processing is needed (>32K tokens)
4. **Processing Strategy**:
   - **Standard Pipeline**: Direct LLM call for smaller files via `core/src/core/pipeline/standard.py`
   - **Chunked Pipeline**: Multi-stage processing via `core/src/core/pipeline/chunked.py` for large files

**Chunked Processing (core/src/core/pipeline/chunked.py):**
- Splits large files into manageable chunks
- Generates analysis for each chunk independently
- Hierarchically merges results into final documentation
- Includes checkpoint system for resuming interrupted processing

### Key Components

**Configuration System:**
- `llm/src/llm/client.py`: Multi-account Ollama Cloud API management with automatic failover and round-robin load balancing
- `core/src/core/config.py`: Project path configuration and model settings

**Content Analysis:**
- `rag/src/rag/content.py`: Extracts function signatures and connected code
- `rag/src/rag/docs.py`: Handles Lua reference extraction and file reading
- `prompts/src/prompts/standard.py` & `prompts/src/prompts/chunked.py`: Template generation for LLM prompts

**Processing Modules:**
- `core/src/core/pipeline/chunking.py` + `llm/src/llm/tokens.py`: Token counting and chunking logic
- `core/src/core/pipeline/standard.py`: Standard document generation
- `core/src/core/pipeline/chunked.py`: Multi-stage chunked processing with hierarchical merging

## Common Development Commands

### Running the System

```bash
# Chạy document generation
uv run mod-document

# Chạy diff watcher
uv run mod-watcher

# Test riêng từng package
uv run pytest core/tests/
uv run pytest rag/tests/
uv run pytest prompts/tests/
uv run pytest watcher/tests/

# Test toàn workspace
uv run pytest
```

## Architecture Notes

### File Processing Strategy

The system automatically chooses between two processing modes:
- **Files < 32K tokens**: Direct processing via `core/src/core/pipeline/standard.py`
- **Files ≥ 32K tokens**: Chunked processing via `core/src/core/pipeline/chunked.py`

### Connected Content System

Files are analyzed for dependencies using:
- Import pattern matching in Lua code
- Function signature extraction from referenced files
- Context-aware content inclusion with token budget management

### Prompt Engineering

Two distinct prompt systems:
- `prompts/src/prompts/standard.py`: Standard single-pass documentation generation
- `prompts/src/prompts/chunked.py`: Multi-stage prompts for chunk analysis and merging

### Error Handling & Resilience

- Automatic retry logic for LLM failures (non-rate-limit errors)
- Checkpoint system for long-running chunked operations
- Rate limit detection and automatic account switching
- Graceful Ctrl+C handling with safe shutdown

## Important Files

- `core/src/core/main.py`: Entry point and orchestration
- `llm/src/llm/client.py`: LLM client and Ollama API management
- `core/src/core/config.py`: Project configuration and settings
- `core/src/core/pipeline/chunked.py`: Core chunked processing logic
- `rag/src/rag/content.py`: Content extraction utilities
- `.env`: API keys and environment variables (not in repo)