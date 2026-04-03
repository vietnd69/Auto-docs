# mod-document

Hệ thống tự động sinh API documentation cho Lua mods của game Don't Starve Together (DST). Phân tích source code Lua và tạo tài liệu Markdown bằng AI thông qua Ollama Cloud API.

## Yêu cầu

- Python >= 3.11
- [uv](https://docs.astral.sh/uv/) (package manager)
- Node.js (cho validator MDX check)
- Ollama Cloud API keys (cấu hình trong `.env`)

## Cài đặt

```bash
git clone <repo-url>
cd mod-document
uv sync
```

> **QUAN TRỌNG** — Project sử dụng **uv workspace** với Python 3.11 (`.venv` trong project root).
> Luôn dùng `.venv/Scripts/python` (Windows) hoặc `.venv/bin/python` (Linux/Mac) thay cho `python` trực tiếp để tránh dùng nhầm system Python.

Tạo file `.env` từ template:

```bash
cp .env.template .env
# Điền API keys vào .env
```

Tạo file `config.toml` từ template (tuỳ chọn — dùng để override model/token defaults):

```bash
cp config.toml.template config.toml
# Chỉnh sửa nếu cần override model hoặc các ngưỡng token
```

```env
TOTAL_ACCOUNT=2
ACCOUNT_1=your-ollama-api-key-1
ACCOUNT_2=your-ollama-api-key-2
```

## Sử dụng

### Sinh docs

```bash
# Sinh docs cho toàn bộ file .lua trong dst-scripts/
.venv/Scripts/mod-document

# Sinh docs cho 1 file cụ thể (luôn ghi đè nếu đã tồn tại)
.venv/Scripts/mod-document dst-scripts/components/combat.lua

# Sinh toàn bộ + ghi đè file đã có docs
.venv/Scripts/mod-document -f
```

### Validate docs

```bash
# Toàn bộ docs (format + content)
.venv/Scripts/python -m validator

# 1 file cụ thể
.venv/Scripts/python -m validator dst-api-webdocs/docs/components/combat.md

# Chỉ format check
.venv/Scripts/python -m validator --format-only

# Chỉ content check (LLM review)
.venv/Scripts/python -m validator --content-only
```

### Auto-update từ diff report

Re-render lại toàn bộ nội dung MD cho các file thay đổi theo pipeline chuẩn (render → validator):

```bash
# Re-render docs cho file trong diff report (added/modified/moved)
.venv/Scripts/python -m core.update.docs

# Xem prompt, không gọi LLM
.venv/Scripts/python -m core.update.docs --dry-run

# Chỉ xử lý file mới
.venv/Scripts/python -m core.update.docs --filter added

# Bỏ qua bước validation
.venv/Scripts/python -m core.update.docs --no-validate
```

### Diff watcher

Phát hiện file `.lua` thay đổi giữa các lần cập nhật `dst-scripts`:

```bash
.venv/Scripts/mod-watcher
```

### Chạy tests

```bash
# Toàn bộ workspace
.venv/Scripts/pytest

# Từng package
.venv/Scripts/pytest core/tests/
.venv/Scripts/pytest llm/tests/
.venv/Scripts/pytest rag/tests/
.venv/Scripts/pytest prompts/tests/
.venv/Scripts/pytest validator/tests/
.venv/Scripts/pytest watcher/tests/
```

## Kiến trúc

Project sử dụng **uv workspace** với 6 packages:

```
mod-document/
├── core/        — Pipeline chính, orchestration, CLI entry point
├── llm/         — Ollama Cloud API client, token counting, multi-account failover
├── rag/         — Trích xuất references, content analysis từ Lua source
├── prompts/     — Template generation cho LLM prompts
├── validator/   — Kiểm tra chất lượng output Markdown (format + content via LLM)
├── watcher/     — Phát hiện thay đổi giữa các version dst-scripts
├── skills/      — Markdown skill files → inject vào prompts
├── data/        — Runtime tracking (diff_tracker.json, diff_report.json)
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

1. **File Discovery** — Quét `dst-scripts/` tìm file `.lua`
2. **Reference Analysis** — Trích xuất cross-file dependencies (require, components)
3. **Token Counting** — Xác định strategy dựa trên kích thước prompt
4. **Processing**:
   - **Standard** (< 16K tokens): Gọi LLM trực tiếp
   - **Chunked** (≥ 16K tokens): Chia nhỏ → phân tích từng chunk → merge hierarchically
5. **Output** — Ghi file `.md` vào `dst-api-webdocs/docs/`

### Validation pipeline

Chạy sau khi sinh docs (hoặc độc lập):

1. **Format check** — YAML frontmatter, MDX syntax, emoji rules
2. **Content check** — LLM review → auto-fix → approve loop:
   - **Standard** (< 32K tokens Lua source): review toàn bộ doc
   - **Chunked** (≥ 16K tokens): per-section review với Lua context extraction

### Tính năng

- Round-robin load balancing qua nhiều Ollama account
- Tự động failover khi bị rate limit
- Checkpoint system cho chunked processing (resume khi bị gián đoạn)
- Graceful shutdown với Ctrl+C
- Diff tracking giữa các version game update
- Per-section content validation cho file Lua lớn
