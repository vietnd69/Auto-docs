# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## RAG Search — mod-document

Use the `local-rag` MCP server to search this codebase.
- **workspace_id**: `mod-document`
- **Path**: D:\code\mod-document

When asked about code in this project, call:
- `search_code(query, workspace_id="mod-document")` — semantic search
- `lookup_symbol(symbol_name=..., workspace_id="mod-document")` — find class/function
- `get_file_context(file_path=..., workspace_id="mod-document")` — full file content


## Project Overview

This is a Python-based document generation system that automatically creates API documentation for Lua-based Don't Starve Together (DST) game mods. The system analyzes Lua source code and generates comprehensive Markdown documentation using AI models via the Ollama API.

## Core Architecture

### Document Generation Pipeline

**Main Flow (main.py:53-153):**
1. **File Discovery**: Scans `dst-scripts/` directory for `.lua` files
2. **Reference Analysis**: Extracts cross-file dependencies and connected content
3. **Token Counting**: Determines if chunked processing is needed (>32K tokens)
4. **Processing Strategy**:
   - **Standard Pipeline**: Direct LLM call for smaller files via `olm.py`
   - **Chunked Pipeline**: Multi-stage processing via `chunked_olm.py` for large files

**Chunked Processing (chunked_olm.py):**
- Splits large files into manageable chunks
- Generates analysis for each chunk independently
- Hierarchically merges results into final documentation
- Includes checkpoint system for resuming interrupted processing

### Key Components

**Configuration System (config.py):**
- Multi-account Ollama Cloud API management with automatic failover
- Round-robin load balancing with rate limit detection
- Project path configuration and model settings

**Content Analysis:**
- `rag_get_fnc_content.py`: Extracts function signatures and connected code
- `get_docs.py`: Handles Lua reference extraction and file reading
- `prompt.py` & `chunked_prompt.py`: Template generation for LLM prompts

**Processing Modules:**
- `chunked.py`: Token counting and chunking logic
- `olm.py`: Standard document generation
- `chunked_olm.py`: Multi-stage chunked processing with hierarchical merging

## Common Development Commands

### Running the System

```bash
# Activate Python virtual environment
.venv/Scripts/activate

# Run main document generation
python main.py

# Run specific tests
python test_per_chunk.py

# Check Python syntax for all files
python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('main.py: OK')"
```

### Environment Setup

The project requires:
- Python virtual environment in `.venv/`
- Dependencies from `requirements.txt`
- Ollama API keys configured in `.env` file
- LlamaIndex, Ollama, and related ML libraries

### Testing

Test files follow the pattern `test_*.py`:
- `test_per_chunk.py`: Tests chunked content extraction
- Individual module tests for validation

## Architecture Notes

### File Processing Strategy

The system automatically chooses between two processing modes:
- **Files < 32K tokens**: Direct processing via `olm.generate_doc()`
- **Files ≥ 32K tokens**: Chunked processing via `chunked_olm.process_chunked_file()`

### Connected Content System

Files are analyzed for dependencies using:
- Import pattern matching in Lua code
- Function signature extraction from referenced files
- Context-aware content inclusion with token budget management

### Prompt Engineering

Two distinct prompt systems:
- `prompt.py`: Standard single-pass documentation generation
- `chunked_prompt.py`: Multi-stage prompts for chunk analysis and merging

### Error Handling & Resilience

- Automatic retry logic for LLM failures (non-rate-limit errors)
- Checkpoint system for long-running chunked operations
- Rate limit detection and automatic account switching
- Graceful Ctrl+C handling with safe shutdown

## Important Files

- `main.py`: Entry point and orchestration
- `config.py`: Configuration and Ollama API management
- `chunked_olm.py`: Core chunked processing logic
- `rag_get_fnc_content.py`: Content extraction utilities
- `requirements.txt`: Python dependencies
- `.env`: API keys and environment variables (not in repo)