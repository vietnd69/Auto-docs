# Design Spec: Monorepo Restructure

**Date:** 2026-03-21
**Status:** Approved
**Goal:** Tái cấu trúc project thành Python monorepo chuẩn — cấu trúc sạch + package độc lập có thể mở rộng.

---

## 1. Mục tiêu

- Tách các Python file phẳng ở root thành các package độc lập theo domain
- Mỗi package có `pyproject.toml`, `src/` layout, và `tests/` riêng
- Tập trung runtime data vào `data/`
- Giữ nguyên `dst-scripts/`, `docs/`, `skills/`
- `validator/` được tích hợp vào workspace (cần thêm `pyproject.toml`)

---

## 2. Dependency Graph (không có cycle)

```
llm/       ← base layer: ollama client + token utilities
watcher/   ← base layer: độc lập, không phụ thuộc gì
prompts/   → llm/
rag/       → llm/
core/      → llm/ + prompts/ + rag/ + validator/
validator/ ← standalone Python package
```

---

## 3. Cấu trúc mục tiêu

```
mod-document/
├── llm/                        ← MỚI: base layer LLM
│   ├── src/llm/
│   │   ├── __init__.py
│   │   ├── client.py           ← ollama_chat + account management từ config.py
│   │   ├── tokens.py           ← count_tokens từ chunked.py
│   │   └── paths.py            ← BASE_LUA_DIR và các path constants dùng chung (rag + core)
│   ├── tests/
│   └── pyproject.toml
│
├── core/
│   ├── src/core/
│   │   ├── __init__.py
│   │   ├── main.py             ← main.py
│   │   ├── config.py           ← phần còn lại của config.py (paths, model settings)
│   │   ├── pipeline/
│   │   │   ├── __init__.py
│   │   │   ├── standard.py     ← olm.py
│   │   │   ├── chunked.py      ← chunked_olm.py
│   │   │   └── chunking.py     ← chunked.py (split logic, dùng llm.tokens)
│   │   └── update/
│   │       ├── __init__.py
│   │       └── docs.py         ← update_docs.py
│   ├── tests/
│   │   ├── test_per_chunk.py
│   │   ├── test_file_type_detection.py
│   │   ├── test_skills_loader.py
│   │   ├── test.py
│   │   └── chunked_test.py
│   └── pyproject.toml
│
├── rag/
│   ├── src/rag/
│   │   ├── __init__.py
│   │   ├── search.py           ← rag.py
│   │   ├── content.py          ← rag_get_fnc_content.py (dùng llm.client, llm.tokens)
│   │   └── docs.py             ← get_docs.py
│   ├── tests/
│   │   └── test_require_stubs.py
│   └── pyproject.toml
│
├── prompts/
│   ├── src/prompts/
│   │   ├── __init__.py
│   │   ├── standard.py         ← prompt.py
│   │   ├── chunked.py          ← chunked_prompt.py
│   │   ├── update.py           ← update_prompt.py
│   │   ├── pre_synthesis.py    ← pre_synthesis.py (PreSynthesisResult dùng bởi chunked.py)
│   │   └── skills_loader.py    ← skills_loader.py (dùng bởi standard + chunked prompts)
│   ├── tests/
│   │   ├── test_chunk_prompts.py
│   │   ├── test_events_section.py
│   │   └── test_pre_synthesis.py
│   └── pyproject.toml
│
├── watcher/
│   ├── src/watcher/
│   │   ├── __init__.py
│   │   ├── diff.py             ← get_diff_update.py
│   │   └── hash.py             ← patch_hash.py
│   ├── scripts/
│   │   └── simulate_changes.py ← dev tool (không phải test)
│   ├── tests/
│   └── pyproject.toml
│
├── validator/                  ← thêm pyproject.toml, giữ nguyên code
│   ├── __init__.py             (đã có)
│   ├── __main__.py             (đã có)
│   ├── validator.py            (đã có)
│   ├── validate_update.py      (đã có)
│   ├── ... (các file khác giữ nguyên)
│   └── pyproject.toml          ← MỚI: cần thêm để tham gia workspace
│
├── data/                       ← runtime files (gitignored)
│   ├── diff_tracker.json
│   ├── file_tracker.json
│   ├── diff_report.json
│   ├── version_log.txt
│   └── diff_log.txt
│
├── dst-scripts/                ← không thay đổi
├── docs/                       ← không thay đổi
├── skills/                     ← không thay đổi + nhận thêm docs_SKILL.md từ root
│   ├── docs_SKILL.md           ← MOVE từ root (gộp chung skill files)
│   ├── dst_conventions.md
│   ├── few_shot.md
│   ├── few_shot_data.md
│   ├── function_format.md
│   └── quality_rules.md
├── tmp/                        ← gitignored
├── dst_chroma_db/              ← gitignored
├── pyproject.toml              ← workspace root
└── CLAUDE.md
```

---

## 4. Package Configuration

### Root workspace (`pyproject.toml`)
```toml
[tool.uv.workspace]
members = ["llm", "core", "rag", "prompts", "watcher", "validator"]

[tool.uv]
dev-dependencies = ["pytest>=8.0"]
```

### llm (`llm/pyproject.toml`)
```toml
[project]
name = "mod-document-llm"
version = "0.1.0"
dependencies = ["ollama", "tiktoken"]

[tool.setuptools.packages.find]
where = ["src"]
```

### core (`core/pyproject.toml`)
```toml
[project]
name = "mod-document-core"
version = "0.1.0"
dependencies = [
    "mod-document-llm",
    "mod-document-rag",
    "mod-document-prompts",
    "mod-document-validator",
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
dependencies = ["mod-document-llm", "llama-index", "chromadb"]

[tool.setuptools.packages.find]
where = ["src"]
```

### prompts (`prompts/pyproject.toml`)
```toml
[project]
name = "mod-document-prompts"
version = "0.1.0"
dependencies = ["mod-document-llm", "pyyaml"]

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

### validator (`validator/pyproject.toml`)
```toml
[project]
name = "mod-document-validator"
version = "0.1.0"
dependencies = []

[tool.setuptools.packages.find]
where = ["."]
include = ["validator*"]
```

---

## 5. Dependency Flow

```
watcher → produces: data/diff_report.json
                          ↓
core.update.docs   ← reads diff_report, triggers regeneration
      ↓
core.pipeline  ←── prompts (templates + pre_synthesis)
      ↑
     rag (content extraction) ←── llm (client + tokens)
      ↑
     llm ← base layer
```

**Import path changes (examples):**

| Trước | Sau |
|-------|-----|
| `from prompt import ...` | `from prompts.standard import ...` |
| `from chunked_prompt import ...` | `from prompts.chunked import ...` |
| `from update_prompt import ...` | `from prompts.update import ...` |
| `from pre_synthesis import PreSynthesisResult` | `from prompts.pre_synthesis import PreSynthesisResult` |
| `from skills_loader import load_skill` | `from prompts.skills_loader import load_skill` |
| `from rag import ...` | `from rag.search import ...` |
| `from rag_get_fnc_content import ...` | `from rag.content import ...` |
| `from get_docs import ...` | `from rag.docs import ...` |
| `from chunked_olm import ...` | `from core.pipeline.chunked import ...` |
| `from olm import ...` | `from core.pipeline.standard import ...` |
| `from chunked import ...` | `from core.pipeline.chunking import ...` |
| `from config import ollama_chat` | `from llm.client import ollama_chat` |
| `from config import ...` (paths/model) | `from core.config import ...` |
| `from chunked import count_tokens` | `from llm.tokens import count_tokens` |
| `import config` → `config.BASE_LUA_DIR` (trong `rag_get_fnc_content.py`) | `from llm.paths import BASE_LUA_DIR` |

---

## 6. Chiến lược Migration

### Giai đoạn 1 — Scaffolding (không đụng code)
- Tạo thư mục và `pyproject.toml` cho từng package: `llm/`, `core/`, `rag/`, `prompts/`, `watcher/`
- Thêm `validator/pyproject.toml`
- Tạo `data/` và di chuyển runtime files
- Cập nhật `.gitignore`: thêm `data/`, `tmp/`, `dst_chroma_db/`

### Giai đoạn 2 — Di chuyển file (bottom-up, ít dependency trước)
1. `llm/` — tách `ollama_chat` từ `config.py`, tách `count_tokens` từ `chunked.py`
2. `watcher/` — `get_diff_update.py`, `patch_hash.py`; `simulate_changes.py` → `watcher/scripts/`
3. `prompts/` — `prompt.py`, `chunked_prompt.py`, `update_prompt.py`, `pre_synthesis.py`, `skills_loader.py`; move `docs_SKILL.md` → `skills/docs_SKILL.md`
4. `rag/` — `rag.py`, `rag_get_fnc_content.py`, `get_docs.py`
5. `core/` — `main.py`, `config.py` (phần còn lại), `olm.py`, `chunked_olm.py`, `chunked.py` (split logic), `update_docs.py`, `get_tree.py`, `shutdown.py`

### Giai đoạn 3 — Cập nhật imports
- Cập nhật tất cả import statements theo bảng mapping Section 5
- Cập nhật hardcoded paths (xem Giai đoạn 3a bên dưới)

### Giai đoạn 3a — Cập nhật hardcoded runtime paths
Các file sau dùng `"./..."` paths cứng, cần đổi sang resolve từ workspace root:

| File gốc → đích | Constant | Path resolution |
|-----------------|----------|-----------------|
| `get_diff_update.py` → `watcher/src/watcher/diff.py` | `DIFF_TRACKER`, `DIFF_LOG`, `DIFF_REPORT`, `VERSION_LOG` | `Path(__file__).parents[3] / "data" / "..."` |
| `update_docs.py` → `core/src/core/update/docs.py` | `DIFF_REPORT` | `Path(__file__).parents[4] / "data" / "diff_report.json"` |
| `rag.py` → `rag/src/rag/search.py` | `TRACKER_FILE` | `Path(__file__).parents[3] / "data" / "file_tracker.json"` |
| `skills_loader.py` → `prompts/src/prompts/skills_loader.py` | `_DEFAULT_INDEX` (trỏ `docs_SKILL.md`) | `Path(__file__).parents[3] / "skills" / "docs_SKILL.md"` (sau khi move vào `skills/`) |

**Ghi chú độ sâu `parents`:**
- Package ở `<pkg>/src/<pkg>/file.py` → `parents[2]` = package root, `parents[3]` = workspace root
- Package ở `<pkg>/src/<pkg>/sub/file.py` (1 sub-level) → `parents[3]` = package root, `parents[4]` = workspace root

Hoặc dùng env var nhất quán: `DATA_DIR = Path(os.environ.get("MOD_DOCUMENT_DATA_DIR", workspace_root / "data"))`

### Giai đoạn 4 — Kiểm tra & dọn dẹp
- Chạy `uv run pytest core/tests/`, `rag/tests/`, `prompts/tests/`, `watcher/tests/`
- Chạy `uv run pytest` (toàn workspace)
- Xóa file gốc ở root sau khi tests pass
- Cập nhật `CLAUDE.md` (xem checklist bên dưới)

### CLAUDE.md Update Checklist
- [ ] Section "Key Components": cập nhật tất cả file paths (`rag_get_fnc_content.py` → `rag/src/rag/content.py`, v.v.)
- [ ] Section "Important Files": cập nhật path list
- [ ] Section "Common Development Commands": `python main.py` → `uv run mod-document`, `python get_diff_update.py` → `uv run mod-watcher`
- [ ] Section ".venv": cập nhật sang uv (`uv sync` thay `.venv/Scripts/Activate.ps1`)
- [ ] Section "Architecture Notes": cập nhật module names

---

## 7. Cách chạy sau migration

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

# Test toàn workspace
uv run pytest
```

---

## 8. Không thay đổi

- `dst-scripts/` — Lua source input
- `docs/` — generated Markdown output
- `skills/` — skills data (nhận thêm `docs_SKILL.md` từ root)
- `validator/` code — chỉ thêm `pyproject.toml`
- `dst_chroma_db/` — vector DB runtime (gitignored)
- `tmp/` — temp files (gitignored)
