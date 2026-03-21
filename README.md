# mod-document

Hệ thống tự động sinh API documentation cho Lua mods của game Don't Starve Together (DST). Phân tích source code Lua và tạo tài liệu Markdown bằng AI thông qua Ollama Cloud API.

## Yêu cầu

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (package manager)
- Ollama Cloud API keys (cấu hình trong `.env`)

## Cài đặt

```bash
git clone <repo-url>
cd mod-document
uv sync
```

Tạo file `.env` ở root:

```env
TOTAL_ACCOUNT=2
ACCOUNT_1=your-ollama-api-key-1
ACCOUNT_2=your-ollama-api-key-2
```

## Sử dụng

### Sinh docs

```bash
# Sinh docs cho toàn bộ file .lua trong dst-scripts/
uv run mod-document

# Sinh docs cho 1 file cụ thể (luôn ghi đè nếu đã tồn tại)
uv run mod-document dst-scripts/components/combat.lua

# Sinh toàn bộ + ghi đè file đã có docs
uv run mod-document -f
```

### Diff watcher

Phát hiện file `.lua` thay đổi giữa các lần cập nhật `dst-scripts`:

```bash
uv run mod-watcher
```

### Chạy tests

```bash
# Toàn bộ workspace
uv run pytest

# Từng package
uv run pytest core/tests/
uv run pytest llm/tests/
uv run pytest rag/tests/
uv run pytest prompts/tests/
uv run pytest validator/tests/
uv run pytest watcher/tests/
```

## Kiến trúc

Project sử dụng **uv workspace** với 6 packages:

```
mod-document/
├── core/        — Pipeline chính, orchestration, CLI entry point
├── llm/         — Ollama Cloud API client, token counting, multi-account failover
├── rag/         — Trích xuất references, content analysis từ Lua source
├── prompts/     — Template generation cho LLM prompts
├── validator/   — Kiểm tra chất lượng output Markdown
├── watcher/     — Phát hiện thay đổi giữa các version dst-scripts
├── dst-scripts/ — Lua source code (input)
└── docs/        — Generated Markdown documentation (output)
```

### Dependency graph

```
core ──→ llm
  ├───→ rag ──→ llm
  ├───→ prompts ──→ llm
  └───→ validator ──→ llm, rag
watcher ──→ rag
```

### Pipeline xử lý

1. **File Discovery** — Quét `dst-scripts/` tìm file `.lua`
2. **Reference Analysis** — Trích xuất cross-file dependencies (require, components)
3. **Token Counting** — Xác định strategy dựa trên kích thước prompt
4. **Processing**:
   - **Standard** (< 32K tokens): Gọi LLM trực tiếp
   - **Chunked** (>= 32K tokens): Chia nhỏ → phân tích từng chunk → merge hierarchically
5. **Output** — Ghi file `.md` vào `docs/`

### Tính năng

- Round-robin load balancing qua nhiều Ollama account
- Tự động failover khi bị rate limit
- Checkpoint system cho chunked processing (resume khi bị gián đoạn)
- Graceful shutdown với Ctrl+C
- Diff tracking giữa các version game update
