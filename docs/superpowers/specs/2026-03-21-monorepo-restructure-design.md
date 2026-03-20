# Design Spec: Monorepo Restructure

**Date:** 2026-03-21
**Status:** Approved
**Goal:** Tái cấu trúc project thành Python monorepo chuẩn — cấu trúc sạch + package độc lập có thể mở rộng.

---

## 1. Mục tiêu

- Tách các Python file phẳng ở root thành các package độc lập theo domain
- Mỗi package có `pyproject.toml`, `src/` layout, và `tests/` riêng
- Tập trung runtime data vào `data/`
- Giữ nguyên `validator/`, `dst-scripts/`, `docs/`

---

## 2. Cấu trúc mục tiêu

```
mod-document/
├── core/
│   ├── src/core/
│   │   ├── __init__.py
│   │   ├── main.py            ← main.py
│   │   ├── config.py          ← config.py
│   │   ├── pipeline/
│   │   │   ├── __init__.py
│   │   │   ├── standard.py    ← olm.py
│   │   │   ├── chunked.py     ← chunked_olm.py
│   │   │   ├── chunking.py    ← chunked.py
│   │   │   └── pre_synthesis.py
│   │   ├── update/
│   │   │   ├── __init__.py
│   │   │   └── docs.py        ← update_docs.py
│   │   └── utils/
│   │       ├── __init__.py
│   │       ├── shutdown.py
│   │       ├── tree.py        ← get_tree.py
│   │       └── skills_loader.py
│   ├── tests/
│   │   ├── test_per_chunk.py
│   │   ├── test_pre_synthesis.py
│   │   ├── test_file_type_detection.py
│   │   ├── test_skills_loader.py
│   │   ├── test_zlib.py
│   │   ├── test.py
│   │   └── chunked_test.py
│   └── pyproject.toml
│
├── rag/
│   ├── src/rag/
│   │   ├── __init__.py
│   │   ├── search.py          ← rag.py
│   │   ├── content.py         ← rag_get_fnc_content.py
│   │   └── docs.py            ← get_docs.py
│   ├── tests/
│   │   ├── test_require_stubs.py
│   │   └── test_regex.py
│   └── pyproject.toml
│
├── prompts/
│   ├── src/prompts/
│   │   ├── __init__.py
│   │   ├── standard.py        ← prompt.py
│   │   ├── chunked.py         ← chunked_prompt.py
│   │   └── update.py          ← update_prompt.py
│   ├── tests/
│   │   ├── test_chunk_prompts.py
│   │   └── test_events_section.py
│   └── pyproject.toml
│
├── watcher/
│   ├── src/watcher/
│   │   ├── __init__.py
│   │   ├── diff.py            ← get_diff_update.py
│   │   └── hash.py            ← patch_hash.py
│   ├── tests/
│   │   └── simulate_changes.py  ← dev tool
│   └── pyproject.toml
│
├── validator/                 ← không thay đổi
│
├── data/                      ← runtime files (gitignored)
│   ├── diff_tracker.json
│   ├── file_tracker.json
│   ├── diff_report.json
│   ├── version_log.txt
│   └── diff_log.txt
│
├── dst-scripts/               ← không thay đổi
├── docs/                      ← không thay đổi
├── tmp/                       ← không thay đổi (gitignored)
├── dst_chroma_db/             ← không thay đổi (gitignored)
├── skills/                    ← không thay đổi
├── pyproject.toml             ← workspace root
└── CLAUDE.md
```

---

## 3. Package Configuration

### Root workspace (`pyproject.toml`)

```toml
[tool.uv.workspace]
members = ["core", "rag", "prompts", "watcher", "validator"]

[tool.uv]
dev-dependencies = ["pytest>=8.0"]
```

### core (`core/pyproject.toml`)

```toml
[project]
name = "mod-document-core"
version = "0.1.0"
dependencies = [
    "mod-document-rag",
    "mod-document-prompts",
    "ollama",
    "tiktoken",
]

[project.scripts]
mod-document = "core.main:main"

[tool.setuptools.packages.find]
where = ["src"]
```

### rag (`rag/pyproject.toml`)

```toml
[project]
name = "mod-document-rag"
version = "0.1.0"
dependencies = ["llama-index", "chromadb"]

[tool.setuptools.packages.find]
where = ["src"]
```

### prompts (`prompts/pyproject.toml`)

```toml
[project]
name = "mod-document-prompts"
version = "0.1.0"
dependencies = []

[tool.setuptools.packages.find]
where = ["src"]
```

### watcher (`watcher/pyproject.toml`)

```toml
[project]
name = "mod-document-watcher"
version = "0.1.0"
dependencies = []

[project.scripts]
mod-watcher = "watcher.diff:main"

[tool.setuptools.packages.find]
where = ["src"]
```

---

## 4. Dependency Flow

```
watcher
  └─→ produces: data/diff_report.json
                    ↓
core.update.docs    ← reads diff_report, triggers regeneration
      ↓
core.pipeline ←── prompts (templates)
      ↑
     rag (content extraction, semantic search)
      ↓
docs/ (Markdown output)
```

**Import path changes (examples):**

| Trước | Sau |
|-------|-----|
| `from prompt import ...` | `from prompts.standard import ...` |
| `from chunked_prompt import ...` | `from prompts.chunked import ...` |
| `from rag import ...` | `from rag.search import ...` |
| `from rag_get_fnc_content import ...` | `from rag.content import ...` |
| `from get_docs import ...` | `from rag.docs import ...` |
| `from chunked_olm import ...` | `from core.pipeline.chunked import ...` |
| `from olm import ...` | `from core.pipeline.standard import ...` |
| `from chunked import ...` | `from core.pipeline.chunking import ...` |
| `from config import ...` | `from core.config import ...` |

---

## 5. Chiến lược Migration

### Giai đoạn 1 — Scaffolding (không đụng code)
- Tạo thư mục package và `pyproject.toml` cho từng package
- Tạo `data/` và di chuyển runtime files
- Cập nhật `.gitignore`

### Giai đoạn 2 — Di chuyển file (bottom-up, ít dependency trước)
1. `prompts/` — không phụ thuộc gì
2. `watcher/` — độc lập
3. `rag/` — phụ thuộc llama-index
4. `core/` — phụ thuộc rag + prompts

### Giai đoạn 3 — Cập nhật imports
- Cập nhật tất cả import statements trong các file đã di chuyển
- Cập nhật `CLAUDE.md` với đường dẫn mới

### Giai đoạn 4 — Kiểm tra & dọn dẹp
- Chạy `uv run pytest` cho từng package
- Xóa file gốc ở root sau khi tests pass
- Cập nhật `CLAUDE.md`

---

## 6. Cách chạy sau migration

```bash
# Thay cho: python main.py
uv run mod-document

# Thay cho: python get_diff_update.py
uv run mod-watcher

# Test riêng từng package
uv run pytest core/tests/
uv run pytest rag/tests/
uv run pytest prompts/tests/
uv run pytest watcher/tests/

# Test toàn bộ workspace
uv run pytest
```

---

## 7. Không thay đổi

- `dst-scripts/` — Lua source input
- `docs/` — generated Markdown output
- `validator/` — giữ nguyên cấu trúc hiện tại
- `skills/` — giữ nguyên
- `dst_chroma_db/` — vector DB runtime
- `tmp/` — temp files
