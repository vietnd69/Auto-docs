# Cấu trúc chuẩn của một Claude Skill

> Tài liệu tham khảo để tạo và hiểu cấu trúc một skill trong hệ thống Claude.

---

## Tổng quan

Một skill là một thư mục chứa hướng dẫn và tài nguyên giúp Claude thực hiện một loại tác vụ chuyên biệt.
Claude đọc skill trước khi thực hiện, rồi làm theo hướng dẫn bên trong.

```
my-skill/
├── SKILL.md                ← BẮT BUỘC — hướng dẫn chính
├── scripts/                ← tùy chọn — code Python/Bash chạy được
│   ├── __init__.py
│   ├── process.py
│   └── utils.py
├── references/             ← tùy chọn — tài liệu Claude đọc khi cần
│   ├── api-reference.md
│   └── domain-rules.md
└── assets/                 ← tùy chọn — template, font, icon dùng cho output
    ├── output_template.md
    └── base_layout.html
```

---

## SKILL.md — File bắt buộc

### Cấu trúc đầy đủ

```markdown
---
name: tên-skill-dạng-kebab-case
description: >
  [1-2 câu mô tả skill làm gì.]

  USE THIS SKILL whenever a user asks to:
  - "[cụm từ trigger 1]", "[cụm từ trigger 2]"
  - "[ngữ cảnh cụ thể khi nào dùng]"
  Trigger even if phrasing is informal like "[ví dụ câu hỏi không formal]".
compatibility:              ← tùy chọn, ít dùng
  tools: [bash, python]
  python: ">=3.10"
---

# Tên Skill (Heading chính)

Một đoạn mô tả ngắn mục đích và tinh thần của skill.
Viết cho Claude đọc, không phải cho người dùng cuối.

---

## Workflow

### Step 1 — [Tên bước]

Hướng dẫn cụ thể. Viết ở dạng imperative (ra lệnh).

### Step 2 — [Tên bước]

...

---

## Output Format

Mô tả rõ định dạng đầu ra mong muốn.
Dùng template tường minh nếu có:

    ALWAYS use this exact structure:
    # [Title]
    ## Section A
    ## Section B

---

## Examples

**Example 1:**
Input: ...
Output: ...

---

## Quality Checklist

- [ ] Tiêu chí kiểm tra 1
- [ ] Tiêu chí kiểm tra 2

---

## Error Handling

- Tình huống lỗi A: xử lý như thế nào.
- Tình huống lỗi B: xử lý như thế nào.
```

### Giải thích từng phần

#### YAML Frontmatter (phần `---`)

| Field | Bắt buộc | Mô tả |
|---|---|---|
| `name` | ✅ | Identifier dạng `kebab-case`, khớp với tên thư mục |
| `description` | ✅ | **Cơ chế trigger chính.** Phải ghi rõ cả "làm gì" lẫn "khi nào dùng". Viết hơi "pushy" vì Claude có xu hướng undertrigger. |
| `compatibility` | ❌ | Chỉ dùng khi skill cần tool/dependency đặc biệt |

> **Quy tắc vàng cho `description`:** Đừng chỉ mô tả chức năng — phải chỉ rõ ngữ cảnh trigger.
> Thay vì *"Generate a report"*, viết *"Generate a report. Use this skill whenever the user wants any kind of data report, even if they say 'summary', 'breakdown', or 'overview'."*

#### Body của SKILL.md

| Phần | Khi nào cần | Ghi chú |
|---|---|---|
| Mô tả mở đầu | Luôn có | 1-2 câu định hướng tinh thần |
| Workflow / Steps | Luôn có | Imperative, có số thứ tự |
| Output Format | Khi output có cấu trúc cố định | Dùng template tường minh |
| Examples | Khi format phức tạp | Input → Output cụ thể |
| Quality Checklist | Khuyến khích | Claude tự kiểm tra trước khi trả |
| Error Handling | Khi có nhiều edge case | Liệt kê tình huống + cách xử lý |
| Source Priority | Khi dùng nhiều nguồn dữ liệu | Bảng ưu tiên khi conflict |

**Giới hạn:** SKILL.md nên dưới **500 lines**. Nếu vượt quá, tách nội dung ra `references/` và trỏ link từ SKILL.md.

---

## `scripts/` — Code chạy được

### Khi nào dùng

Dùng khi tác vụ là **deterministic và lặp lại** — không cần LLM reasoning:
- Xử lý file (parse, transform, convert)
- Gọi API, tính toán số liệu
- Generate output từ template
- Bất kỳ logic nào >30 lines mà không có judgment call

### Cấu trúc mẫu

```
scripts/
├── __init__.py             ← bắt buộc nếu gọi bằng `python -m scripts.tên`
├── main.py                 ← entry point chính
├── utils.py                ← helper functions dùng chung
├── process_input.py        ← xử lý input
└── templates/              ← XML/HTML/text template dùng bởi script
    └── base.xml
```

### Cách gọi từ SKILL.md

```markdown
## Step 2 — Generate output

Run the processor script:
```bash
python -m scripts.main --input "{input_path}" --output "{output_path}"
```

Arguments:
- `--input`: path to the uploaded file
- `--output`: save to `/mnt/user-data/outputs/result.docx`
```

### Ví dụ thực tế (từ skill `docx`)

```
docx/scripts/
├── __init__.py
├── accept_changes.py       ← xử lý tracked changes trong Word
├── comment.py              ← thêm/xóa/reply comment
└── office/                 ← thư viện XML helpers cho Office format
```

---

## `references/` — Tài liệu Claude đọc khi cần

### Khi nào dùng

Dùng cho kiến thức **tĩnh, dài** mà không cần load vào context mọi lúc:
- API documentation
- Domain rules, business logic
- Hướng dẫn theo variant/domain (AWS vs GCP vs Azure)
- JSON schema definitions

### Cấu trúc mẫu

```
references/
├── api-reference.md        ← đầy đủ API endpoints + params
├── domain-rules.md         ← quy tắc business logic
└── error-codes.md          ← bảng mã lỗi và cách xử lý
```

**Multi-domain pattern** — khi skill hỗ trợ nhiều variant:

```
references/
├── aws.md                  ← chỉ đọc khi deploy lên AWS
├── gcp.md                  ← chỉ đọc khi deploy lên GCP
└── azure.md                ← chỉ đọc khi deploy lên Azure
```

### Cách trỏ từ SKILL.md

```markdown
## Step 1 — Load relevant reference

Identify the deployment target, then read the appropriate file:
- AWS → `references/aws.md`
- GCP → `references/gcp.md`
- Azure → `references/azure.md`

Do NOT read all three — only the one that matches.
```

### Quy tắc

- File >300 lines → thêm **Table of Contents** ở đầu file
- SKILL.md phải nói **khi nào** và **điều kiện gì** thì đọc file nào
- Không load tất cả references vào context nếu không cần thiết

---

## `assets/` — File tĩnh dùng trong output

### Khi nào dùng

Dùng cho những file Claude sẽ **copy, điền vào, hoặc inject data**:
- Markdown/HTML template có placeholder
- Base layout mà script sẽ inject data vào
- Font files, SVG icon cho generated documents

### Cấu trúc mẫu

```
assets/
├── output_template.md      ← template Claude điền vào từng section
├── report_base.html        ← HTML skeleton cho generated report
└── icon_set/
    ├── warning.svg
    └── success.svg
```

### Ví dụ thực tế

```
dota2-hero-research/assets/
└── hero_template.md        ← template với các section cố định
                               Claude fetch dữ liệu rồi điền vào
```

### Cách dùng từ SKILL.md

```markdown
## Step 2 — Fill the template

Read the template from: `assets/output_template.md`

Replace each `{placeholder}` with data from Step 1.
Do not add or remove sections from the template.
```

---

## Hệ thống 3 lớp loading (Progressive Disclosure)

Đây là cơ chế quan trọng nhất — kiểm soát **bao nhiêu context** Claude cần đọc:

```
Lớp 1 — METADATA (luôn có trong context)
┌─────────────────────────────────────────┐
│ name + description (~100 words)         │
│ → Claude dùng để quyết định trigger     │
└─────────────────────────────────────────┘
         ↓ (khi skill được trigger)
Lớp 2 — SKILL.md BODY (load khi trigger)
┌─────────────────────────────────────────┐
│ Workflow, Output Format, Examples       │
│ Quality Checklist, Error Handling       │
│ Giới hạn: <500 lines                   │
└─────────────────────────────────────────┘
         ↓ (khi workflow yêu cầu)
Lớp 3 — BUNDLED RESOURCES (load theo nhu cầu)
┌─────────────────────────────────────────┐
│ scripts/ → chạy trực tiếp              │
│ references/ → đọc khi cần              │
│ assets/ → dùng khi generate output     │
│ Không giới hạn kích thước              │
└─────────────────────────────────────────┘
```

**Nguyên tắc thiết kế:** Đặt ở lớp thấp nhất có thể. Chỉ đưa lên lớp cao hơn khi thực sự cần thiết.

---

## Thư mục tùy chỉnh

Ngoài 3 thư mục trên, skill có thể dùng tên bất kỳ tùy mục đích:

| Tên thư mục | Mục đích | Ví dụ |
|---|---|---|
| `agents/` | Prompt cho subagent chuyên biệt | `agents/grader.md`, `agents/analyzer.md` |
| `themes/` | Preset data theo variant | `themes/dark.md`, `themes/minimal.md` |
| `evals/` | Test cases để benchmark skill | `evals/evals.json` |
| `eval-viewer/` | UI tool cho human review | HTML + Python script |

---

## Ví dụ đầy đủ — Skill giả định

Skill `report-generator` tạo báo cáo phân tích từ file CSV:

```
report-generator/
├── SKILL.md
├── scripts/
│   ├── __init__.py
│   ├── parse_csv.py         ← đọc CSV, validate, trả về dict
│   ├── compute_stats.py     ← tính mean, median, trend
│   └── render_html.py       ← inject data vào base template
├── references/
│   ├── chart-types.md       ← khi nào dùng bar vs line vs pie
│   └── formatting-rules.md  ← quy tắc format số, ngày tháng
└── assets/
    ├── report_template.html ← HTML skeleton
    └── styles.css           ← stylesheet cho report
```

**SKILL.md** của skill này sẽ:
1. Frontmatter định nghĩa trigger khi user đề cập "report", "phân tích CSV", "báo cáo dữ liệu"
2. Workflow: parse → compute → chọn chart type → render
3. Trỏ đến `references/chart-types.md` ở bước chọn chart
4. Trỏ đến `assets/report_template.html` ở bước render
5. Gọi `python -m scripts.parse_csv` ở bước đầu

---

## Checklist khi tạo skill mới

- [ ] `SKILL.md` có YAML frontmatter với `name` và `description`
- [ ] `description` bao gồm cả "làm gì" lẫn "khi nào trigger" — đủ pushy
- [ ] Workflow viết ở dạng imperative, có step numbers rõ ràng
- [ ] SKILL.md dưới 500 lines — nếu vượt thì tách ra `references/`
- [ ] Mọi reference file đều được trỏ từ SKILL.md với điều kiện rõ ràng
- [ ] Reference file >300 lines có Table of Contents
- [ ] Scripts có `__init__.py` nếu gọi bằng `-m`
- [ ] Asset template không có placeholder bị bỏ trống trong output
- [ ] Có Quality Checklist hoặc Error Handling nếu workflow phức tạp