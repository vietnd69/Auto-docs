# Thiết kế: DST Docs Harness trên OpenCode + Harness²

- **Ngày:** 2026-10-25
- **Trạng thái:** Draft, chờ review
- **Phạm vi:** Bộ harness mới, chạy song song với pipeline hiện tại. Không sửa code cũ.

---

## 1. Bối cảnh và vấn đề

Pipeline hiện tại (`core/`, `validator/`, `rag/`, `prompts/`) gặp 3 vấn đề gốc:

1. **Vòng review không hội tụ.** `validator/content/loop.py` mỗi vòng review lại toàn bộ tài liệu với `reviewer_temperature = 0.8`. Vì không có định danh ổn định cho finding, reviewer đẻ ra issue mới hoặc diễn đạt lại issue cũ, và `_find_oscillating_issues` (so khớp từ khóa trong dấu nháy) bỏ sót. Tiêu chí "approved" hoàn toàn do LLM quyết định. Không có ngân sách theo job: một file có thể tốn 12 vòng × (review + 3 lượt writer + correction + jury 5 lượt gọi).
2. **Context gửi cứng.** `build_reviewer_prompt` và `build_prompt` luôn gửi toàn bộ `lua_source`, `connected_content`, toàn bộ doc và file tree. LLM không có cách tự lấy thêm thứ nó cần hay bỏ thứ không cần.
3. **Không tự cải thiện.** Skills (`skills/`) do người sửa tay. Bài học từ file trước không được dùng cho file sau.

Quy mô ở build `759671` (`vietnd69/dst-scripts@b729a8f`):

| Chỉ số | Giá trị |
|---|---|
| File `.lua` | 4084 |
| > 20 KB / > 40 KB / > 80 KB / > 200 KB | 452 / 170 / 60 / 33 |
| Lớn nhất | `map/static_layouts/maxwellhome.lua` 1.1 MB, `stategraphs/SGwilson.lua` 1.0 MB, `strings.lua` 865 KB |
| Trang docs hiện có | 3975 (ánh xạ 1 file Lua → 1 trang) |

## 2. Mục tiêu

| # | Mục tiêu | Tiêu chí đo |
|---|---|---|
| G1 | Kết quả là tài liệu dev dùng trong **Docusaurus** | 100% trang compile MDX, frontmatter đúng schema, sidebar sinh tự động, không có link nội bộ gãy |
| G2 | Harness tự quyết định **chia codebase thành bao nhiêu trang** | Có `doc-plan.json`, mỗi symbol public thuộc đúng 1 trang, mỗi trang nằm trong ngân sách token |
| G3 | Xử lý được **file rất dài** | Không prompt nào chứa nguyên một file > ngân sách. Agent làm việc theo symbol hoặc range |
| G4 | Nội dung **đúng và đủ** | Coverage 100% theo checklist, 0 tên bịa, 0 finding có bằng chứng còn mở |
| G5 | **Cập nhật docs theo source** khi có build mới, kể cả big update | Chỉ trang bị ảnh hưởng mới bị sửa. Diff thô không bao giờ được gửi nguyên khối cho LLM |
| G6 | **Tự cải thiện skill và memory** trong lúc làm việc | Library theo domain tăng dần. Skill mới chỉ được đưa vào dùng khi qua regression gate |
| G7 | **Không lặp vô hạn** | Mọi phiên có trần cứng về step, token và thời gian. Trạng thái kết thúc luôn là PASS, FAIL hoặc ESCALATED |

### Ngoài phạm vi

- Không sửa hay xóa code cũ (`core/`, `validator/`, `rag/`, `prompts/`, `watcher/`, `llm/`). Harness mới chỉ **import** chúng.
- Không hỗ trợ các build trước `759671`. Mốc baseline là build mới nhất hiện tại.
- Không giữ URL cũ. Cấu trúc trang có thể đổi tự do và không cần redirect.
- Không sửa repo crawler `vietnd69/dst-steam-auto-crawl-update`.

## 3. Ràng buộc

- **Nền chạy agent:** OpenCode.
- **Tối ưu harness:** fork `google-research/harness2`. Fork bắt buộc vì `cli/_common.py` hardcode `BENCHES = ("jb", "wb", "lab")`.
- **Model:** Ollama Cloud (mặc định `qwen3.5:cloud`), giữ cơ chế xoay nhiều tài khoản và cooldown khi gặp 429 (`llm/router.py`).
- **Python:** Auto-docs dùng 3.11 (uv workspace, `.python-version = 3.11`). Harness² cần ≥ 3.12, nên là một project uv riêng trong repo, có `.venv` riêng. Chi tiết ở mục 3.1.
- **Runtime phụ:** Node.js 20+ (OpenCode, `validate_mdx.mjs`, `budget.ts`), cài cục bộ trong repo, không cài global.
- **Quy chuẩn code:** theo các tiêu chuẩn ISO/IEC liên quan, ánh xạ thành luật kiểm tra được. Chi tiết ở mục 3.2.

### 3.1 Môi trường chạy (tất cả nằm trong repo)

Mọi thứ chạy bằng uv hoặc venv ngay trong repo, không cài gì global ngoài `uv` và Node.js. Theo `CLAUDE.md`, lệnh luôn gọi trực tiếp vào `.venv`. Trên Windows dùng `.venv/Scripts/`, trên Linux/macOS dùng `.venv/bin/`.

| Thành phần | Cách cài | Cách chạy |
|---|---|---|
| `harness/` (Python 3.11) | Thêm `"harness"` vào `members` của `[tool.uv.workspace]`, rồi `uv sync` | `.venv/Scripts/mod-harness`, `.venv/Scripts/dst-tools-mcp`, `.venv/Scripts/ollama-proxy`, `.venv/Scripts/pytest harness/tests/` |
| `harness2-dst/` (Python 3.12) | Project uv **độc lập**, không thuộc workspace, có `.python-version = 3.12`. Chạy `uv sync --project harness2-dst` (uv tự cài Python 3.12 nếu chưa có) | `harness2-dst/.venv/Scripts/harness2 --bench dst ...` |
| OpenCode | `package.json` ở gốc repo, pin version OpenCode. Chạy `npm ci`, cài vào `node_modules/` (git-excluded) | `node_modules/.bin/opencode` (Windows: `node_modules\.bin\opencode.cmd`) |
| `budget.ts` | Nằm trong `.opencode/plugin/`, OpenCode tự nạp | Test bằng `npx vitest` (hoặc bun test nếu đã có bun) |

`mod-harness` tự tìm đường dẫn `.venv` và `node_modules` theo hệ điều hành, nên người dùng không phải gõ đường dẫn của từng công cụ.

**Lưu ý về Windows:** Harness² ghi "Use Linux" cho các lần chạy benchmark. Lý do chính là các benchmark có sẵn cần pandoc, poppler và Docker. Benchmark `dst` không cần những thứ đó, nhưng chưa được kiểm chứng trên Windows. P5 sẽ kiểm tra; nếu không chạy được thì `harness2-dst` chạy qua WSL. Phần còn lại (P0–P4) không phụ thuộc Harness².

### 3.2 Quy chuẩn kỹ thuật (ISO/IEC)

Các tiêu chuẩn dưới đây được dùng làm **khung tham chiếu**. Mỗi tiêu chuẩn được ánh xạ thành luật cụ thể, có công cụ kiểm tra tự động trong CI hoặc pre-commit. Không nhắm tới chứng nhận.

| Tiêu chuẩn | Áp dụng cho | Luật cụ thể trong repo |
|---|---|---|
| **ISO/IEC 25010** (mô hình chất lượng sản phẩm) | Toàn bộ `harness/` | Mỗi đặc tính có thước đo: *functional suitability* = verdict PASS rate; *reliability* = resume sau ngắt, không mất state; *performance efficiency* = token/trang, thời gian/trang; *maintainability* = độ phức tạp và coverage bên dưới; *security* = mục ISO/IEC 27001/27034 |
| **ISO/IEC 5055** (đo chất lượng mã nguồn: reliability, security, performance, maintainability) | Code Python và TS | `ruff` (bộ luật `E,F,W,I,B,UP,SIM,C90,S,PL,RUF`); độ phức tạp cyclomatic ≤ 10 mỗi hàm (`C901`); file ≤ 400 dòng, hàm ≤ 60 dòng; không `except:` trần, không nuốt lỗi im lặng; TS dùng `tsc --strict` + `eslint` |
| **ISO/IEC/IEEE 29119** (kiểm thử phần mềm) | `harness/tests/`, test của plugin | Mỗi tool MCP có test theo kỹ thuật phân lớp tương đương và giá trị biên (29119-4); coverage nhánh ≥ 85% cho `harness/` (`pytest-cov --cov-branch --cov-fail-under=85`); test E2E tách riêng bằng marker `e2e`; báo cáo test lưu ở `.harness/reports/` |
| **ISO/IEC/IEEE 12207** (quy trình vòng đời phần mềm) | Quy trình làm việc | Mỗi giai đoạn P0–P5 có spec → plan → triển khai → verification → review. Mỗi thay đổi đi qua branch và PR, commit theo Conventional Commits |
| **ISO/IEC/IEEE 42010** (mô tả kiến trúc) | Tài liệu thiết kế | Tài liệu này nêu rõ stakeholder, concern (G1–G7) và các view (thành phần, luồng dữ liệu, triển khai). Mỗi quyết định kiến trúc lớn về sau được ghi thành ADR trong `docs/adr/` |
| **ISO/IEC 27001 (Annex A 8.28 Secure coding) / ISO/IEC 27034** (an toàn ứng dụng) | Proxy, MCP server, xử lý source | API key chỉ đọc từ `.env`, không log và không ghi vào debug dump; proxy chỉ bind `127.0.0.1`; mọi đường dẫn file từ tool đều được chuẩn hóa và giới hạn trong `dst-scripts/` và `dst-api-webdocs/` (chống path traversal); gọi git bằng `subprocess` với danh sách tham số, không `shell=True`; `ruff` nhóm `S` (bandit); `pip-audit`/`uv` lock pin toàn bộ phụ thuộc |
| **ISO/IEC/IEEE 26514** (thiết kế và phát triển tài liệu người dùng) | Docs đầu ra (G1, G4) | Cấu trúc trang nhất quán theo loại trang; mỗi symbol có mô tả, tham số, giá trị trả về, ví dụ; thuật ngữ thống nhất (glossary trong skill); những luật này nằm trong `run_checks` (`HEADINGS`, `COVERAGE`, `SIGNATURE`) và skill của writer |
| **ISO 8601** (ngày giờ) | Frontmatter, log, state | `last_updated` dạng `YYYY-MM-DD`; timestamp trong log, ledger và queue dạng `YYYY-MM-DDTHH:MM:SSZ` (UTC) |

Các luật bổ sung không thuộc ISO nhưng được dùng để thực thi những điều trên:

- **Python:** PEP 8 (`ruff format`), type hint đầy đủ, `mypy --strict` cho `harness/`, docstring kiểu Google cho mọi hàm public.
- **Pre-commit** chạy: `ruff check`, `ruff format --check`, `mypy`, `pytest -m "not e2e"`, `tsc --noEmit`.
- **Đường dẫn:** code luôn dùng `pathlib`, không nối chuỗi đường dẫn theo kiểu `/` của POSIX, để chạy được trên cả Windows và Linux.
- **Source:** `dst-scripts/` là clone của `vietnd69/dst-scripts`. Repo này do crawler push 3 tiếng một lần, mỗi build là một commit với message `"<build> - <tiêu đề>\n\n<patch notes Steam>"`. Commit cũ không có quy ước thống nhất.

## 4. Kiến trúc tổng thể

```
Auto-docs/
├── .opencode/                         # OpenCode là nền
│   ├── opencode.json                  # provider → ollama-proxy; mcp → dst-tools; tool gate
│   ├── agent/
│   │   ├── orchestrator.md            # nhận job, chia việc, gọi subagent
│   │   ├── planner.md                 # G2
│   │   ├── writer.md                  # G1, G3
│   │   ├── reviewer.md                # G4 (subagent, chỉ đọc)
│   │   ├── updater.md                 # G5
│   │   └── reflector.md               # G6
│   ├── skills/<name>/SKILL.md         # harness hiện hành (promote từ library)
│   ├── plugin/budget.ts               # G7: trần step/token/thời gian, chặn edit lặp
│   ├── systemprompt.md, guardrails.md, LongTermMEMORY.md
│   └── tool_descriptions/tool_guidance.md
├── harness/                           # uv workspace member mới (Python 3.11)
│   ├── pyproject.toml                 # scripts: mod-harness, dst-tools-mcp, ollama-proxy
│   ├── src/harness/
│   │   ├── cli.py                     # mod-harness bootstrap|generate|update|status|improve
│   │   ├── proxy.py                   # OpenAI-compatible → Ollama Cloud, xoay key
│   │   ├── mcp_server.py              # MCP "dst-tools", đăng ký các tool trong tools/
│   │   ├── tools/
│   │   │   ├── lua_index.py           # outline, symbol, read, grep, refs, deps, table_schema
│   │   │   ├── plan.py                # index_codebase, plan_get/put, validate_plan
│   │   │   ├── page.py                # page_checklist, doc_read/write_section, notes
│   │   │   ├── verdict.py             # run_checks (tất định), ledger
│   │   │   ├── source.py              # build_list, build_resolve, diff_overview, symbol_diff, impact_map
│   │   │   └── memory.py              # memory_search, memory_add
│   │   ├── lua_parse.py               # parser Lua nhẹ: symbol + range dòng + chữ ký
│   │   ├── queue.py                   # hàng đợi job + checkpoint
│   │   ├── session.py                 # chạy `opencode run` cho 1 job, đọc kết quả
│   │   └── improve.py                 # cầu nối sang Harness² + regression gate
│   └── tests/
├── harness2-dst/                      # project uv độc lập, Python 3.12, .venv riêng
│   ├── pyproject.toml, .python-version
│   ├── harness2/                      # git submodule → fork vietnd69/harness2
│   └── README.md
├── package.json, package-lock.json    # pin OpenCode + công cụ TS (node_modules/ git-excluded)
├── docs/adr/                          # Architecture Decision Records (ISO/IEC/IEEE 42010)
└── .harness/                          # state runtime (git-excluded trừ plan + library)
    ├── doc-plan.json                  # (tracked) cấu trúc trang
    ├── sync-state.json                # (tracked) SHA đã đồng bộ theo trang và symbol
    ├── library/<domain>/              # (tracked) harness đã chọn + EXPERIENCE.md
    ├── ledger/<page-id>.jsonl         # finding theo trang
    ├── notes/<page-id>.md             # bộ nhớ làm việc của từng trang
    └── queue/<job-id>.jsonl
```

### Nguyên tắc

1. **Tất định trước, LLM sau.** Mọi thứ đo được bằng code (coverage, chữ ký, MDX, link, tên bịa) đều do tool quyết định. LLM chỉ viết và chỉ ra lỗi ngữ nghĩa có bằng chứng.
2. **Context theo nhu cầu.** Prompt khởi đầu của mỗi job chỉ gồm: loại job, `page_id`, danh sách nguồn và checklist. Mọi thứ khác agent lấy qua tool.
3. **Một luồng cho cả generate và update.** Generate là update từ trạng thái rỗng. Planner, writer, verdict và memory dùng chung.
4. **Mọi vòng lặp đều có trần.** Không có trường hợp "chờ LLM tự approve".

## 5. Thành phần

### 5.1 Ollama proxy (`harness/proxy.py`)

- Server HTTP local, expose `POST /v1/chat/completions` theo chuẩn OpenAI. OpenCode cấu hình nó là một provider tương thích OpenAI (`ollama-proxy/qwen3.5:cloud`).
- Forward request **nguyên dạng** tới endpoint OpenAI-compatible của Ollama Cloud. Không dịch format, nên `tools` và `tool_calls` đi thẳng qua.
- Chọn key bằng `llm.router.select_key`. Gặp 429 thì gọi `mark_rate_limited` và thử key khác. Gặp timeout hoặc lỗi 5xx thì xoay key, theo đúng logic của `llm/client.py`. Sau mỗi lượt gọi thành công, chạy `record_call` với số token trả về.
- Log token theo job (header `X-Harness-Job`) để `budget.ts` và báo cáo dùng.

### 5.2 MCP server `dst-tools`

Tất cả tool chạy tất định, đọc source qua `git show <sha>:<path>` (không phụ thuộc working tree) và có giới hạn kích thước đầu ra. Đầu ra quá giới hạn bị cắt và kèm con trỏ để đọc tiếp.

**Nhóm đọc source (G3)**

| Tool | Đầu vào → đầu ra |
|---|---|
| `lua_outline(file, rev?)` | Danh sách symbol `{kind, name, qualname, line_start, line_end, tokens, signature}`. `kind` gồm: `function`, `method`, `class`, `state`, `event_handler`, `action`, `table`, `constant` |
| `lua_symbol(file, qualname, rev?)` | Mã nguồn của một symbol, kèm số dòng |
| `lua_read(file, from, to, rev?)` | Đọc theo khoảng dòng, tối đa `READ_MAX_TOKENS` (mặc định 4000) |
| `lua_grep(pattern, path_glob?, rev?)` | Kết quả `file:line:text`, tối đa N dòng |
| `lua_refs(name, rev?)` | Nơi định nghĩa và nơi gọi trên toàn codebase |
| `lua_deps(file, rev?)` | Các `require` và `components.X` mà file dùng, kèm stub chữ ký (dùng lại `rag.content.extract_compact_content`, `extract_signatures_only`) |
| `lua_table_schema(file, table, rev?)` | Với **file dữ liệu**: mô tả cấu trúc bảng (các key, kiểu giá trị, số phần tử, 3 mẫu đại diện), không trả về toàn bộ bảng |

`lua_parse.py` là parser tối thiểu, chỉ nhận diện các mẫu DST: `local function`, `function X:Y`, `X.Y = function`, `Class(...)`, `State{ name = ... }`, `EventHandler("...")`, `ActionHandler(...)`, `return { ... }` và các bảng top-level. Phần lõi là test fixture viết từ các file thật (`SGwilson.lua`, `combat.lua`, `tuning.lua`, `strings.lua`).

**Nhóm plan (G2)**: `index_codebase()`, `plan_get(page_id?)`, `plan_put(patch)`, `validate_plan()`. Xem mục 5.4.

**Nhóm trang**

| Tool | Mô tả |
|---|---|
| `page_checklist(page_id)` | Danh sách symbol trang **bắt buộc** phải có, kèm chữ ký chuẩn lấy từ parser |
| `doc_read(page_id, heading?)` | Đọc toàn trang hoặc một section |
| `doc_write_section(page_id, heading, markdown)` | Ghi hoặc thay một section (`##` hoặc `###`). Chạy check cục bộ ngay: MDX của đoạn đó, tên symbol có tồn tại hay không |
| `notes_read(page_id)`, `notes_write(page_id, text)` | Bộ nhớ làm việc của trang, gồm tiến độ và các symbol đã xong. Dùng để resume khi bị ngắt |

**Nhóm verdict (G4, G7)**: `run_checks(page_id)`, `ledger_add(page_id, finding)`, `ledger_list(page_id)`, `ledger_resolve(id, note)`. Xem mục 5.6.

**Nhóm source/build (G5)**: `build_list()`, `build_resolve(build)`, `diff_overview(from, to)`, `symbol_diff(file, qualname, from, to)`, `impact_map(from, to)`, `patch_notes(build)`. Xem mục 5.7.

**Nhóm memory (G6)**: `memory_search(domain, query, k)`, `memory_add(domain, cue, lesson, evidence)`. Xem mục 5.8.

### 5.3 OpenCode workspace (`.opencode/`)

- **Agent:**
  - `orchestrator` là agent chính.
  - `planner`, `writer`, `updater` là subagent có quyền ghi qua tool.
  - `reviewer` là subagent chỉ đọc. Nó chỉ được gọi `lua_*`, `doc_read` và `ledger_add`.
  - `reflector` chạy cuối mỗi job để rút ra EXPERIENCE.
- **Tool gate trong `opencode.json`:** tắt `bash`, `write`, `edit` và `webfetch` của OpenCode cho tất cả agent. Agent chỉ được ghi docs qua `doc_write_section`, nên mọi thay đổi đều đi qua check.
- **`plugin/budget.ts`** (component c8 của Harness², lớp "model không thể bỏ qua"):
  - Trần mặc định cho mỗi job: `max_steps = 80`, `max_tokens = 400k`, `max_wall = 30 phút`.
  - Chặn một lượt gọi tool khi lượt đó trùng hệt (tên và tham số) lượt trước đó trong 3 lượt gần nhất.
  - Chặn `doc_write_section` khi nội dung ghi vào một section trùng với một phiên bản đã ghi trước đó cho chính section ấy (dao động A → B → A).
  - Khi chạm trần, plugin buộc phiên kết thúc với trạng thái `BUDGET_EXHAUSTED`.
- **Skills:** chuyển đổi từ `skills/` hiện tại (`rules/`, `roles/`, `knowledge/few_shot_*`) sang định dạng `skills/<name>/SKILL.md` có frontmatter `name` và `description` (đúng surface c6 của Harness²). Skill few-shot theo loại file được nạp theo domain.

### 5.4 Planner (G2)

**`index_codebase()`** chạy tất định trên toàn bộ file, kết quả được cache theo SHA. Với mỗi file, nó trả về: `path`, `domain`, `tokens`, `kind` (`code` hoặc `data`), danh sách symbol public, event, `require` và component được dùng.

- **Domain** (theo đường dẫn, mở rộng từ `prompts/type_detect.py`): `component`, `prefab`, `stategraph`, `brain`, `behaviour`, `widget`, `screen`, `map`, `data`, `util`, `core`.
- **`kind = data`** khi hơn 80% token nằm trong literal table, ví dụ `strings.lua`, `skins_defs_data.lua`, `map/static_layouts/*`, `tuning.lua`.

**`doc-plan.json`** có schema như sau:

```json
{
  "baseline": {"build": "759671", "sha": "b729a8f68d4b635c21279e71723b9627f24c5c38"},
  "pages": [
    {
      "id": "stategraphs/sgwilson/combat-states",
      "path": "stategraphs/sgwilson/combat-states.md",
      "title": "SGwilson — Combat states",
      "domain": "stategraph",
      "category": ["Stategraphs", "SGwilson"],
      "sources": [
        {"file": "stategraphs/SGwilson.lua", "symbols": ["State:attack", "State:hit"]}
      ],
      "budget_tokens": 12000
    }
  ]
}
```

**Quy tắc chia trang** (planner LLM đề xuất, `validate_plan` kiểm tra):

| Trường hợp | Cách chia |
|---|---|
| File code ≤ `PAGE_SOURCE_MAX` (mặc định 12k token) | 1 file thành 1 trang |
| File code lớn hơn mức đó | Tách theo nhóm symbol có liên quan (state theo chủ đề, method theo trách nhiệm), kèm một trang tổng quan `index` link tới các trang con |
| Nhiều file nhỏ cùng thư mục, cùng mẫu | Gộp thành 1 trang (ví dụ `map/rooms/*`, `prefabs/*_skins`) |
| File `data` | 1 trang "data reference": mô tả schema bằng `lua_table_schema`, bảng key quan trọng và cách mod truy cập. **Không** liệt kê toàn bộ dữ liệu |

**`validate_plan()`** chạy tất định. Plan sai thì planner phải sửa lại.

- Mỗi symbol public được gán cho **đúng 1** trang.
- Không có trang rỗng.
- `id` không trùng nhau.
- `path` hợp lệ với Docusaurus.
- Tổng token nguồn của trang ≤ `budget_tokens`.
- File `data` được gán cho trang loại data reference.

Sau khi plan hợp lệ, tool sinh `_category_.json` cho từng thư mục từ `category`.

### 5.5 Writer với file dài (G1, G3)

Writer làm việc theo trang, mỗi lần một symbol:

1. Gọi `page_checklist` để biết trang cần những symbol nào, và `notes_read` để biết symbol nào đã làm xong.
2. Với mỗi symbol chưa xong:
   - Gọi `lua_symbol` để lấy thân symbol.
   - Gọi `lua_refs`/`lua_deps` khi cần context.
   - Gọi `memory_search` để lấy bài học của domain.
   - Ghi kết quả bằng `doc_write_section`, rồi `notes_write` để đánh dấu đã xong.
3. Viết các section tổng hợp (`Overview`, `Usage example`, `Dependencies & tags`) **sau** khi các symbol đã xong. Lúc này writer đọc `notes` và `lua_outline`, không đọc lại toàn bộ source.
4. Gọi `run_checks`. Nếu có lỗi tất định thì sửa đúng section bị lỗi.

Nhờ cách làm này, `SGwilson.lua` (khoảng 250k token) được xử lý mà không prompt nào vượt quá vài chục nghìn token. Nếu phiên bị ngắt, `notes` cho phép chạy tiếp từ symbol dở dang.

### 5.6 Verdict và ledger (G4, G7)

**`run_checks(page_id)`** chạy tất định và trả về danh sách lỗi có mã:

| Mã | Kiểm tra |
|---|---|
| `FM_SCHEMA` | Frontmatter có đủ `id`, `title`, `description`, `tags`, `sidebar_position`, `last_updated`, `build_version`, `source_sha`, `sources` |
| `MDX_COMPILE` | Compile qua `validator/format/validate_mdx.mjs` |
| `HEADINGS` | Có các heading bắt buộc theo loại trang |
| `COVERAGE` | Mọi symbol trong `page_checklist` đều có `###` tương ứng |
| `SIGNATURE` | Tham số trong doc khớp chữ ký do parser trích ra |
| `PHANTOM` | Mọi tên hàm, event, tag được nêu trong doc đều tồn tại trong source hoặc deps |
| `LINKS` | Link nội bộ trỏ tới trang có trong plan |
| `FORMAT` | Các luật trong `validator/format/checks.py` (import, không sửa) |

**Reviewer (ngữ nghĩa):** reviewer được giao từng nhóm symbol, không phải cả trang. Mỗi finding gửi qua `ledger_add` phải có dạng:

```json
{"symbol": "Combat:GetAttacked", "field": "returns", "claim": "...",
 "evidence": {"file": "components/combat.lua", "lines": [412, 418], "quote": "return true"}}
```

`ledger_add` từ chối finding nếu `quote` không khớp source tại các dòng đã nêu. Ledger gán ID ổn định theo `hash(symbol, field)`. Một finding đã `resolved` chỉ được mở lại khi có `evidence` **khác** với lần trước. Điều này loại bỏ hiện tượng reviewer nêu lại lỗi cũ dưới dạng câu chữ mới, vốn là gốc của vòng lặp vô hạn hiện nay.

**Trạng thái của một trang:**

- `PASS`: `run_checks` không có lỗi và ledger không còn finding `open`.
- `FAIL`: hết số vòng sửa (mặc định 3 vòng writer↔reviewer cho mỗi nhóm symbol) mà vẫn còn lỗi. Lỗi được ghi lại và trang chuyển sang leo thang (mục 5.8).
- `BUDGET_EXHAUSTED`: chạm trần của `budget.ts`, xử lý như `FAIL`.

Chỉ trang `PASS` mới được ghi vào `dst-api-webdocs/docs/`. Trang `FAIL` được giữ ở `.harness/drafts/` kèm báo cáo.

### 5.7 Updater (G5)

**Mốc và dò build**

- Baseline là build `759671` = `b729a8f`. Các build cũ hơn bị bỏ qua.
- `build_list()` chỉ liệt kê các commit **sau** baseline trên `main`, theo thứ tự lịch sử git. Số build lấy từ dòng đầu của message bằng regex `^(?:Hotfix\s+)?(\d{5,7})\b` (crawler ghi `"<build> - <tiêu đề>"`, hoặc `"<build>"` khi không lấy được RSS).
- `build_resolve(build)` trả về SHA. Nếu không tìm thấy thì báo lỗi kèm danh sách ứng viên, không đoán.
- `sync-state.json` lưu **SHA** đã đồng bộ cho mỗi trang và mỗi symbol, kèm `source_hash` theo symbol. `mod-harness update` mặc định chạy từ SHA nhỏ nhất đã đồng bộ tới `origin/main`.

**Diff theo symbol** (không bao giờ gửi diff thô cho LLM)

1. `diff_overview(from, to)` dựa trên `git diff --name-status -M`. File bị sửa được chạy `lua_outline` ở cả hai revision để so khớp symbol, cho ra `{added, removed, renamed, signature_changed, body_changed}` theo từng file. Đầu ra là bản tóm tắt, có phân trang nếu quá lớn.
2. `impact_map(from, to)` giao diff symbol với `doc-plan.json`, cho ra danh sách `page → [symbol, change]`, cùng danh sách symbol mới chưa thuộc trang nào và các trang trở nên rỗng.
3. `symbol_diff(file, qualname, from, to)` trả về hunk cũ và mới của đúng một symbol.
4. `patch_notes(build)` trả về phần thân commit message (patch notes Steam). Updater dùng nó làm context về ý đồ thay đổi, và changelog dùng nó làm nguồn mô tả.

**Luồng chạy**

1. `planner` cập nhật plan theo `impact_map`: gán symbol mới vào trang có sẵn hoặc tạo trang mới, gỡ symbol bị xóa, chuyển symbol bị đổi tên, xóa trang rỗng. Sau đó chạy `validate_plan`.
2. `queue.py` sinh một job cho mỗi trang bị ảnh hưởng, ghi vào `.harness/queue/<from>..<to>.jsonl`. Job có checkpoint và chạy song song tối đa `N = số key đang khả dụng`.
3. `updater` xử lý từng trang. Với mỗi symbol bị đổi, nó gọi `symbol_diff`, rồi `doc_write_section` cho đúng section đó, rồi `run_checks`. Reviewer chỉ xét các symbol vừa đổi.
4. Trang `PASS` được ghi vào docs và cập nhật `sync-state.json` cùng frontmatter (`build_version`, `source_sha`, `last_updated`).
5. Cuối đợt, sinh entry changelog cho `dst-api-webdocs/change-log.md` từ diff symbol (API thêm/xóa/đổi chữ ký) cộng với `patch_notes`.

Big update chỉ khác ở số lượng job trong hàng đợi. Mỗi job vẫn nhỏ và có trần.

### 5.8 Tự cải thiện (G6) với Harness²

**Domain:** `<loại>` cho generate (ví dụ `stategraph`) và `update/<loại>` cho update.

**Tầng 1, chạy với mọi job (rẻ):**

- Sau mỗi job, `reflector` đọc báo cáo job (lỗi check, finding, số step, kết quả) rồi gọi `memory_add(domain, cue, lesson, evidence)`. Cấu trúc này giống EXPERIENCE trong `harness2/core/library.py`.
- `memory_add` loại các bài học trùng (so khớp với `cue` sẵn có) và giữ tối đa K mục cho mỗi domain. Mục ít được dùng nhất bị loại trước.
- Writer và updater tra bài học qua `memory_search` trước khi làm.
- `LongTermMEMORY.md` (luôn được nạp) chỉ chứa phần tóm tắt top-N bài học. Phần này được sinh lại sau mỗi đợt, không ghi tay.

**Tầng 2, leo thang khi `FAIL` hoặc `BUDGET_EXHAUSTED` (đắt):**

- `improve.py` gọi task-level recursion của Harness² (`core/recursion.py`, mode `seq`, `k = 2`) trên **chính trang đó**. Proposer đề xuất biến thể cho các component c1 (systemprompt), c2 (guardrails), c4 (tool_guidance) và c6 (skills). Mỗi biến thể được chạy thử qua OpenCode. Selector (`core/selection.py`) chọn biến thể tốt nhất, với điểm do `run_checks` và ledger chấm.
- Harness thắng được lưu vào `.harness/library/<domain>/harnesses/<page>/` kèm `EXPERIENCE.md`.
- Chi phí: Harness² lập lịch 4k rollout và 3k stage cải thiện cho mỗi mode, nên với `k = 2` một trang leo thang tốn khoảng 8 phiên OpenCode. Vì vậy tầng 2 có cờ bật/tắt (`--escalate`) và trần số trang leo thang cho mỗi đợt (mặc định 20).

**Regression gate trước khi promote skill:**

- Regression set gồm khoảng 3 trang mẫu cho mỗi domain, tổng khoảng 20–30 trang, được ghi cố định trong `.harness/regression.json`.
- `mod-harness improve --promote <domain>` chạy harness ứng viên trên regression set của domain đó. Ứng viên chỉ được copy vào `.opencode/skills/` khi (a) số trang `PASS` không giảm và (b) tổng token không tăng quá 20%.
- Lệnh promote chạy thủ công hoặc theo lịch, **không tự chạy giữa một đợt update**. Như vậy skill không bị trôi giữa chừng.

### 5.9 Fork Harness² (`harness2-dst/`)

Patch trên fork được giữ ở mức nhỏ:

1. Thêm `"dst"` vào `BENCHES` và `make_adapter` (`cli/_common.py`).
2. Thêm `harness2/benchmarks/dst.py`, gồm `BenchSpec` và `DstAdapter`:
   - Task là một `page_id`.
   - Launcher gọi `mod-harness run-page --harness-dir <staged>`.
   - Grade gọi `run_checks` và đọc ledger.
3. Dùng `OpencodeSubstrate` với install mode `workspace_config` (`opencode.json` có tool gate) sẵn có của Harness².
4. Cấu hình model: `HARNESS2_SOLVER_MODEL` và `HARNESS2_IMPROVER_MODEL` = `ollama-proxy/<model>`, `HARNESS2_JUDGE_BASE_URL` trỏ tới proxy.

Python 3.11 gọi Harness² bằng subprocess vào venv 3.12, không import trực tiếp.

## 6. Luồng chạy chính

### 6.1 Bootstrap (một lần, tại baseline `759671`)

1. Chạy `mod-harness bootstrap`: clone hoặc kiểm tra `dst-scripts` tại `b729a8f`, rồi chạy `index_codebase`.
2. Planner sinh `doc-plan.json`, sau đó `validate_plan`.
3. **Tái sử dụng docs cũ:** với trang mà nguồn trùng 1:1 với một file cũ trong `dst-api-webdocs/docs/`, nội dung cũ được nạp làm bản nháp. Verdict chạy trên bản nháp; chỉ những section lỗi mới được viết lại. Trang mới, trang tách hoặc trang gộp thì viết từ đầu.
4. Hàng đợi chạy toàn bộ trang. Kết thúc có `sync-state.json` và báo cáo.

### 6.2 Update (mỗi khi crawler push build mới)

`mod-harness update [--to <build|sha>]` chạy theo luồng ở mục 5.7. Lệnh có thể chạy tay hoặc theo lịch. Tích hợp tự động với crawler, ví dụ bằng `repository_dispatch`, nằm ngoài phạm vi bản đầu.

### 6.3 Một job (generate hoặc update một trang)

```
orchestrator
  ├─ memory_search(domain)            ← bài học
  ├─ writer|updater (theo symbol)     ← lua_* / symbol_diff / doc_write_section / notes
  ├─ run_checks                       ← lỗi tất định → sửa đúng section
  ├─ reviewer (theo nhóm symbol)      ← ledger_add có evidence
  ├─ writer sửa finding open          ← tối đa 3 vòng/nhóm
  ├─ run_checks + ledger → PASS | FAIL
  └─ reflector → memory_add
budget.ts bao toàn bộ phiên: hết trần → BUDGET_EXHAUSTED
FAIL/BUDGET_EXHAUSTED → improve.py (Harness² recursion) nếu được bật
```

## 7. Xử lý lỗi

| Tình huống | Cách xử lý |
|---|---|
| Ollama 429, timeout hoặc 5xx | Proxy xoay key (logic sẵn có). Hết key thì job chuyển sang `PAUSED` và hàng đợi chờ cooldown |
| Model gọi tool sai schema | MCP trả lỗi có cấu trúc. `budget.ts` tính vào số step |
| Phiên bị ngắt (Ctrl+C, crash) | `notes` và checkpoint của hàng đợi cho phép chạy tiếp ở mức job và symbol |
| Parser Lua không nhận ra một cấu trúc | Symbol đó được đánh dấu `unparsed` trong index. Planner gán file vào trang ở mức file, và verdict bỏ qua `SIGNATURE` cho symbol này nhưng vẫn kiểm tra `COVERAGE` theo tên |
| Commit không dò ra số build | `build_resolve` báo lỗi. Riêng `update` vẫn chạy được bằng SHA |
| Harness² lỗi hoặc tốn quá ngân sách | Leo thang bị hủy. Trang giữ ở trạng thái `FAIL` kèm báo cáo, không chặn hàng đợi |

## 8. Kiểm thử

- **Unit (pytest, `harness/tests/`):**
  - `lua_parse` trên fixture lấy từ file thật.
  - `validate_plan`, `run_checks` (từng mã lỗi).
  - Ledger: từ chối evidence sai, không mở lại finding khi evidence trùng.
  - `build_resolve` với các mẫu commit message thật.
  - `diff_overview` và `impact_map` trên một repo git giả.
- **Contract:** proxy chuyển tiếp `tools`/`tool_calls` đúng định dạng, xoay key khi nhận 429 giả lập.
- **Plugin:** test `budget.ts` bằng bun test, gồm chặn khi chạm trần, chặn lượt gọi trùng và chặn dao động A → B → A.
- **E2E (có gắn cờ, cần API key):** chạy một trang nhỏ, một trang `SGwilson` và một trang data. Kết quả phải là `PASS` trong giới hạn budget.
- **Spike đầu tiên (rủi ro lớn nhất):** kiểm tra `qwen3.5:cloud` gọi tool MCP ổn định trong OpenCode qua proxy, đo tỉ lệ tool call hợp lệ. Nếu tỉ lệ thấp, đổi model mặc định trước khi xây các phần còn lại.

## 9. Lộ trình triển khai (mỗi giai đoạn có plan riêng)

| Giai đoạn | Nội dung | Kết quả kiểm chứng |
|---|---|---|
| P0 | Spike: OpenCode + proxy + 1 tool MCP + model Ollama | Tỉ lệ tool call hợp lệ ≥ 95% trên 50 lượt |
| P1 | `harness/` package: proxy, `lua_parse`, nhóm tool đọc source, `run_checks`, ledger. Dựng khung quy chuẩn (ruff, mypy, pytest-cov, pre-commit) | Unit test pass, coverage nhánh ≥ 85%, chạy được `run_checks` trên docs hiện có |
| P2 | `.opencode/`: agent writer/reviewer, `budget.ts`, skill chuyển đổi. Lệnh `run-page` | 3 trang E2E đạt `PASS` |
| P3 | Planner + `doc-plan.json` + bootstrap | Plan hợp lệ cho toàn bộ 4084 file, chạy bootstrap trên 1 thư mục |
| P4 | Updater: build/diff/impact/queue/changelog | Chạy được update giả lập từ một nhánh test |
| P5 | Tự cải thiện: memory, fork Harness², `improve`, regression gate | Một vòng promote có số liệu trước và sau |

## 10. Rủi ro và câu hỏi mở

1. **Khả năng gọi tool của model Ollama Cloud.** Đây là rủi ro lớn nhất, P0 xử lý trước tiên.
2. **Endpoint OpenAI-compatible của Ollama Cloud** cần xác minh trong P0 (đường dẫn `/v1/chat/completions` và việc hỗ trợ `tools`). Nếu không dùng được, proxy chuyển sang dịch format qua `ollama.Client.chat`.
3. **Chi phí bootstrap** cho khoảng 4000 trang chưa được đo. P3 sẽ đo trên một thư mục rồi ngoại suy trước khi chạy toàn bộ.
4. **Harness² là code nghiên cứu** (3 commit trên `main`). Fork được pin commit và chỉ merge upstream khi cần.
5. **Bảo mật:** Harness² cảnh báo executor có mạng không giới hạn. Tool gate tắt `bash` và `webfetch` của OpenCode, nên agent chỉ thao tác qua MCP.
6. **Harness² trên Windows** chưa được kiểm chứng (mục 3.1). Phương án dự phòng là WSL.

## 11. Ghi chú triển khai (2026-10-25)

Các điểm khác so với thiết kế ban đầu, phát sinh khi code:

| Thiết kế | Thực tế | Lý do |
|---|---|---|
| Fork Harness² làm submodule | `harness2-dst/PIN` (commit `1cfe254`) cùng `patches/0001-add-dst-bench.patch`. Lệnh `mod-harness setup-harness2` clone vào `harness2-dst/vendor/` rồi apply patch | Không cần tạo repo fork; patch chỉ ~10 dòng và dễ rebase |
| Skill nằm ở `.opencode/skills/` | Nguồn thật là `.opencode/harness/` (đúng surface c1..c8 của Harness²). `mod-harness sync-opencode` sinh ra `.opencode/skills`, `agent` và `plugin`; `opencode.json` khai báo `skills.paths` | Harness² và OpenCode dùng chung một cây, nên promote chỉ là thay cây rồi materialise lại |
| `orchestrator` là một subagent có thể sửa | `orchestrator` và `reflector` là agent cố định (`.opencode/agent/`); hành vi được điều khiển bằng `systemprompt.md` (c1) | Harness² yêu cầu `sub_agents/*` có `mode: subagent` |
| Plugin export class và helper | Plugin chỉ export `default`; class và helper được gắn kèm làm thuộc tính | OpenCode 1.18 gọi **mọi** hàm được export như một plugin |
| Đường dẫn MCP cố định | `"command": ["{env:HARNESS_MCP_BIN}"]`; `session.py` đặt biến này theo hệ điều hành | `.venv/bin` (Linux) khác `.venv/Scripts` (Windows) |
| Đếm token bằng tiktoken | Ước lượng ≈3.5 ký tự/token (`textutil.estimate_tokens`) | Nhanh, tất định, không cần tải encoding; index 4084 file mất khoảng 35 giây và được cache theo SHA |
| `source_hash` trong frontmatter | `source_sha` (commit) và `sources` (danh sách file); hash theo từng symbol nằm trong `sync-state.json` | Trang có thể gồm nhiều file |

Đã kiểm chứng trong môi trường dev:
- OpenCode 1.18.35 nạp đủ agent và skill, kết nối được MCP `dst-tools`.
- Harness² nhận `--bench dst` và validate cây harness hợp lệ.
- Plan cho 4084 file ra 4114 trang, `validate_plan` không có lỗi.
- 71 test pytest pass (coverage nhánh 90%), 7 test plugin pass, `ruff`, `mypy --strict` và `tsc --strict` sạch.

**Chưa kiểm chứng:** P0 spike với model thật (tỉ lệ tool call hợp lệ của `qwen3.5:cloud` qua proxy) cần API key Ollama Cloud, mà môi trường dev không có.
