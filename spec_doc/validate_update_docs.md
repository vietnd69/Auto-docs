# Spec: Validate MD Docs — Update Phase

> Mục tiêu: Mở rộng validator hiện tại để kiểm tra đặc thù của từng action (added/modified/deleted/moved) sau khi LLM sinh/cập nhật doc trong `update_docs.py`.

---

## 1. Tổng quan

Validator hiện tại (`validate_full`) kiểm tra static structure của bất kỳ `.md` nào.  
Phase update cần thêm **context-aware validation** — tức là validate dựa vào *action* và *dữ liệu từ diff_report.json*.

### Hai tầng cần bổ sung

| Tầng | Loại | Khi chạy |
|------|------|-----------|
| **Tầng A** | Action-specific structural checks | Ngay sau `generate_doc()` trong `update_docs.py` |
| **Tầng B** | Cross-reference checks (hash, version, path) | Sau khi toàn bộ batch hoàn tất |

---

## 2. Tầng A — Action-specific checks

### 2.1 Hàm mới: `validate_update(filepath, action, meta)`

```python
def validate_update(
    filepath: str,
    action: str,           # "added" | "modified" | "deleted" | "moved"
    meta: dict,            # subset từ diff_report change entry
) -> list[str]:
    """
    Chạy validate_full() + các check đặc thù theo action.
    Trả về list errors (empty = OK).
    """
```

`meta` chứa các key cần thiết:
```python
meta = {
    "build_version": new_ver,
    "old_path": ...,
    "new_path": ...,
    "source_hash": ...,
    "content_changed": bool,
    "unified_diff": ...,     # optional, dùng cho modified/moved
}
```

---

### 2.2 Check theo từng action

#### ACTION: `added`
| Check | Mô tả | Severity |
|-------|-------|----------|
| `change_status == "new"` | Frontmatter phải có `change_status: new` | error |
| `build_version == new_ver` | Đúng version vừa update | error |
| `source_hash` khớp với hash thực tế của file Lua | Không bị hallucinate | error |
| Không chứa `*(Changed in build ...)*` hay `~~...~~` | Doc mới không được có inline change notes | warning |

#### ACTION: `modified`
| Check | Mô tả | Severity |
|-------|-------|----------|
| `change_status == "updated"` | | error |
| `build_version == new_ver` | | error |
| `source_hash` khớp hash thực tế | | error |
| Tồn tại ít nhất 1 inline change note | Nếu có diff mà doc không có ghi chú gì → LLM bỏ sót | warning |
| Inline note chứa đúng `build_version` | Không bị nhầm version cũ | warning |
| Không có `## Changelog` section | LLM bị dặn không được thêm | error |

#### ACTION: `deleted`
| Check | Mô tả | Severity |
|-------|-------|----------|
| `change_status == "deprecated"` | | error |
| Tồn tại block `> [!WARNING]` sau `## Overview` | Deprecation notice bắt buộc | error |
| Block WARNING chứa đúng `build_version` | | error |
| `source_hash` không bị thay đổi so với existing_doc | Spec yêu cầu giữ hash cũ | error |
| Các section chính vẫn còn nguyên (không bị xóa) | LLM không được restructure | warning |

#### ACTION: `moved` (content_changed: true)
| Check | Mô tả | Severity |
|-------|-------|----------|
| `change_status == "moved"` | | error |
| `build_version == new_ver` | | error |
| `source_hash` khớp hash thực tế của `new_path` | | error |
| Tồn tại ít nhất 1 inline change note | Nếu có diff | warning |
| Không có `## Changelog` section | | error |

#### ACTION: `moved` (content_changed: false)
| Check | Mô tả | Severity |
|-------|-------|----------|
| `change_status == "moved"` | | error |
| `moved_from` field tồn tại trong frontmatter | | error |
| `moved_in` field tồn tại trong frontmatter | | error |
| Tồn tại block `> [!NOTE]` chứa relocated notice | | error |
| Body không có inline change notes | Doc không được thêm ghi chú khi không có thay đổi | warning |

---

## 3. Tầng B — Cross-reference checks (batch)

Chạy sau toàn bộ batch, đọc lại `diff_report.json` và quét toàn bộ docs liên quan.

### 3.1 Hàm: `validate_batch(diff_report_path, docs_dir)`

| Check | Mô tả |
|-------|-------|
| Tất cả file trong `changes` đều tồn tại trong docs (trừ deleted) | Phát hiện file bị bỏ sót |
| File `deleted` không bị xóa thực sự khỏi docs | Phải còn nhưng có `deprecated` |
| File `moved` cũ (`old_path`) không còn tồn tại trong docs | Đã được rename |
| Không có file nào có `change_status: new` với `build_version` cũ hơn `new_ver` | Orphan docs |

---

## 4. Integration vào `update_docs.py`

### 4.1 Sau mỗi `generate_doc()`

```python
from validator.validate_update import validate_update

result = generate_doc(prompt=prompt, md_filepath=md_filepath, ...)
if result:
    errors = validate_update(
        filepath=md_filepath,
        action=action,
        meta={
            "build_version": new_ver,
            "old_path": old_path,
            "new_path": new_path,
            "source_hash": source_hash,
            "content_changed": c.get("content_changed", False),
            "unified_diff": unified_diff,
        }
    )
    
    hard_errors = [e for e in errors if not e.startswith("[warning")]
    warnings    = [e for e in errors if e.startswith("[warning")]
    
    if hard_errors:
        print(f"  - Validation FAILED ({len(hard_errors)} errors):")
        for e in hard_errors: print(f"    {e}")
        stats["failed"] += 1
        # Ghi vào validation_errors.log để fix sau
        append_to_validation_log(md_filepath, action, hard_errors)
    else:
        if warnings:
            for w in warnings: print(f"    ⚠ {w}")
        stats[action] += 1
```

### 4.2 Sau khi toàn batch xong

```python
from validator.validate_update import validate_batch
validate_batch(DIFF_REPORT, DOCS_DIR)
```

---

## 5. File mới cần tạo

```
validator/
├── validate_update.py       # Tầng A + B (hàm mới)
├── validator.py             # Giữ nguyên (không sửa)
├── autofix_mdx.py           # Giữ nguyên
├── constants.py             # Giữ nguyên
└── validate_mdx.mjs         # Giữ nguyên
```

`validate_update.py` import `validate_full` từ `validator.py` và bổ sung logic trên.

---

## 6. Output log

Tạo `validator/validation_update_errors.log` — format:

```
[2025-01-15 14:32] MODIFIED | components/health.md
  [yaml] change_status should be 'updated', got 'new'
  [warning:inline] No inline change notes found but diff is non-empty

[2025-01-15 14:33] DELETED | components/old_component.md
  [format] Missing [!WARNING] block after ## Overview
```

File này được `fix_format.py` đọc như `format_errors.txt` hiện tại — tích hợp vào pipeline fix sẵn có, không cần viết thêm fix runner.

---

## 7. Thứ tự implement

1. `validate_update.py` — viết `validate_update()` với các check tầng A
2. Tích hợp vào `update_docs.py` (sau `generate_doc()`)
3. Viết `validate_batch()` — tầng B
4. Tích hợp batch check vào cuối `main()` của `update_docs.py`
5. Verify với dry-run trên 1 batch nhỏ (~5 file mỗi action)