# Update Tracking & Doc Sync System

## Bối cảnh

Sau khi toàn bộ docs (~1400 file .md) đã được generate từ dst-scripts Lua, khi game update lên version mới, cần:
1. **Tracking** — Phát hiện chính xác các loại thay đổi trong Lua source
2. **Update Prompt** — Tạo prompt LLM phù hợp để cập nhật .md docs tương ứng

### Hiện trạng codebase

| File | Vai trò | Trạng thái |
|------|---------|------------|
| `get_diff_update.py` | So sánh SHA-256 hash giữa 2 snapshot → ADDED / MODIFIED / DELETED | ✅ Hoạt động |
| `diff_tracker.json` | Lưu hash snapshot (3946 file) | ✅ Có dữ liệu |
| `update_prompt.py` | Prompt LLM cho 3 action: added/modified/deleted | ✅ Đã viết |
| `update_docs_olm.py` | Pipeline chạy update | ❌ Trống (0 byte) |
| `prompt.py` | Prompt tạo doc mới (initial generation) | ✅ Hoạt động |
| `main.py` | Pipeline chính tạo doc mới | ✅ Hoạt động |

---

## Quyết định đã thống nhất

| Hạng mục | Quyết định |
|----------|-----------|
| Tracking approach | **Phương án A** — Hash + Unified Diff |
| Lưu trữ old source | **Giải pháp 1** — Snapshot nén trong tracker (zlib + base64, ~9.3 MB) |
| Move detection | **Có** — phân biệt MOVED vs ADDED/DELETED |
| DELETED handling | **Giữ lại** + thêm deprecation notice, không xóa file |
| Doc format khi update | Inline change notes, không dùng `## Changelog` section |

---

## Proposed Changes

### 1. `diff_tracker.json` — Format mới

**Format cũ:**
```json
{
  "components/combat.lua": "abc123..."
}
```

**Format mới:**
```json
{
  "components/combat.lua": {
    "hash": "abc123...",
    "content_z": "eJzLSM3JyVcozy/KSQEAGgsEHQ=="
  }
}
```

**Migration:** Lần chạy đầu tiên, `get_diff_update.py` tự detect format cũ (`{path: string}`) và rebuild toàn bộ với `content_z`. Ước tính ~30 giây cho 3,930 file.

**Dung lượng ước tính:** ~400 KB (hash only) → ~9.3 MB (với content_z)

---

### 2. `get_diff_update.py` — Mở rộng 3 tầng

#### Tầng 1 — Hash check (giữ nguyên logic hiện tại)

So sánh hash giữa `diff_tracker.json` và new snapshot. Phân loại sơ bộ:
- Key mới → candidate `ADDED`
- Key mất → candidate `DELETED`
- Hash khác → `MODIFIED`

#### Tầng 2 — Move detection (thêm mới)

Trước khi kết luận ADDED/DELETED, cross-check giữa 2 tập:

```
candidates_added   = {path: hash}  ← key mới xuất hiện
candidates_deleted = {path: hash}  ← key cũ biến mất

Với mỗi file trong candidates_deleted:
  1. Tìm trong candidates_added file có hash EXACT MATCH → MOVED (content_changed: false)
  2. Nếu không exact match → tính similarity với difflib.SequenceMatcher
     similarity ≥ 0.8 → MOVED (content_changed: true)
  3. Không match → giữ DELETED
```

> [!NOTE]
> Exact match trước để tránh false positive. Similarity chỉ dùng khi không có exact match.
> RENAMED = trường hợp đặc biệt của MOVED (cùng thư mục, khác tên file).

#### Tầng 3 — Unified diff (thêm mới)

Chỉ áp dụng cho file `MODIFIED`:

```python
old_content = zlib.decompress(base64.b64decode(tracker[path]["content_z"]))
new_content = open(new_path).read()
diff = difflib.unified_diff(
    old_content.splitlines(keepends=True),
    new_content.splitlines(keepends=True),
    fromfile=f"a/{path}",
    tofile=f"b/{path}"
)
```

**Diff summary** được tính thêm:
- Số dòng thêm (`+`)
- Số dòng xóa (`-`)
- Danh sách function headers xuất hiện trong diff (dòng bắt đầu bằng `@@`)

#### Output: `diff_report.json`

```json
{
  "version": {"old": "714014", "new": "720000"},
  "date": "2026-03-15",
  "changes": [
    {
      "action": "modified",
      "path": "components/combat.lua",
      "old_hash": "abc123",
      "new_hash": "def456",
      "diff_summary": "+15 lines, -3 lines",
      "unified_diff": "--- a/components/combat.lua\n+++ b/components/combat.lua\n@@..."
    },
    {
      "action": "moved",
      "old_path": "components/oldname.lua",
      "new_path": "components/newname.lua",
      "content_changed": false
    },
    {
      "action": "moved",
      "old_path": "components/helper.lua",
      "new_path": "utils/helper.lua",
      "content_changed": true,
      "unified_diff": "..."
    },
    {
      "action": "added",
      "path": "components/newcomp.lua"
    },
    {
      "action": "deleted",
      "path": "components/removed.lua"
    }
  ]
}
```

---

### 3. `update_prompt.py` — Bổ sung params & strategies

#### Params mới

| Param | Type | Dùng cho |
|-------|------|----------|
| `existing_doc` | string | MODIFIED, DELETED, MOVED |
| `unified_diff` | string | MODIFIED, MOVED (content_changed: true) |
| `old_path` | string | MOVED |
| `new_path` | string | MOVED |
| `build_version` | string | Tất cả (ghi vào change notes) |

#### Strategy theo từng action

**`MODIFIED`**

Input cho LLM:
- `existing_doc` — doc hiện tại
- `new_source` — source Lua mới
- `unified_diff` — unified diff

Yêu cầu LLM:
- Cập nhật frontmatter: `last_updated`, `build_version`, `change_status: updated`, `source_hash`
- Với mỗi thay đổi phát hiện từ diff, áp dụng inline change notes theo format đã thống nhất (xem mục **Doc Format** bên dưới)
- Không thêm `## Changelog` section
- Không rewrite phần không thay đổi

**`ADDED`**

Giống `prompt.py` hiện tại (tạo doc mới hoàn toàn). Frontmatter: `change_status: new`.

**`DELETED`**

Input cho LLM:
- `existing_doc` — doc hiện tại

Yêu cầu LLM:
- Cập nhật frontmatter: `change_status: deprecated`, `deprecated_in: <build>`, `deprecated_date: <date>`
- Thêm deprecation notice block ngay sau `## Overview`:

```markdown
> [!WARNING]
> **Deprecated in build 720000** — `filename.lua` đã bị xóa khỏi codebase.
> Tài liệu này được giữ lại để tham khảo cho các build cũ hơn.
```

- Không xóa, không sửa bất kỳ nội dung nào khác

**`MOVED` (content_changed: false)**

Không gọi LLM. Pipeline tự xử lý:
- Rename file `.md` theo `new_path`
- Cập nhật frontmatter: `source_file`, `change_status: moved`, `moved_from`, `moved_in`
- Thêm note nhỏ sau title:

```markdown
> [!NOTE]
> **Moved in build 720000** — Source file relocated from
> `old/path.lua` → `new/path.lua`. No logic changes.
```

**`MOVED` (content_changed: true)**

Kết hợp MOVED + MODIFIED:
- Rename file `.md`
- Gọi LLM với strategy giống MODIFIED + thêm note path thay đổi

---

### 4. Doc Format — Inline change notes (đã thống nhất)

Format áp dụng thống nhất trong `## Dependencies & tags`, `## Properties`, `## Main functions`, `## Events & listeners`.

#### Dependencies & tags

```markdown
**Components used:**
`existing_component`, `another_component`,
`new_component` *(Added in build 720000)*,
~~`removed_component`~~ *(Removed in build 720000)*

**Tags added:**
`existing_tag`,
`new_tag` *(Added in build 720000)*,
~~`removed_tag`~~ *(Removed in build 720000)*
```

#### Properties

```markdown
| Property | Type | Default Value | Description |
|----------|------|---------------|-------------|
| `existingprop` | table | `{}` | Unchanged property. |
| `newprop` | number | `0` | *(Added in build 720000)* Description of new property. |
| ~~`removedprop`~~ | ~~number~~ | ~~`0`~~ | ~~Old description.~~ *(Removed in build 720000, replaced by `newprop`)* |
```

#### Main functions

**CHANGED:**
```markdown
### `FunctionName(param1, param2)`
> *(Changed in build 720000)*
> - `param1`: Mô tả thay đổi cụ thể — behavior cũ → behavior mới.
> - Logic X: Replaced inline handler with call to `NewHelper()`.

- **Description:** Mô tả đầy đủ, update nếu behavior thực sự đổi.
- **Parameters:**
    `param1` (type) — Mô tả; *(Changed in build 720000)* note thay đổi cụ thể.
    `param2` (type) — *(Added in build 720000)* Mô tả param mới.
    `param3` (type) — ~~Mô tả param cũ.~~ *Deprecated in build 720000, now ignored.*
- **Returns:** Giữ nguyên hoặc update nếu đổi.
- **Error states:** Giữ nguyên hoặc update nếu đổi.
```

**ADDED:**
```markdown
### `NewFunction(param1)` *(Added in build 720000)*
> *(Added in build 720000)* Mô tả lý do thêm, replace logic nào nếu có.

- **Description:** Mô tả đầy đủ.
- **Parameters:**
    `param1` (type) — Mô tả.
- **Returns:** Giá trị trả về.
- **Error states:** Các edge case.
```

**REMOVED:**
```markdown
### ~~`RemovedFunction(param1)`~~ *(Removed in build 720000)*
> *(Removed in build 720000)* Lý do xóa. Migrate to: `replacement_call()`.

- ~~**Description:** Mô tả cũ.~~
- ~~**Parameters:** `param1` (type) — Mô tả cũ.~~
- ~~**Returns:** Nothing.~~
- ~~**Error states:** Edge case cũ.~~
```

**SIGNATURE CHANGED:**
```markdown
### `FunctionName(param1, param2, newparam)` *(Signature changed in build 720000)*
> *(Signature changed in build 720000)*
> - Added param `newparam` (string). Previously inferred from internal state.
> - `oldparam`: Now deprecated, kept for backward compatibility but ignored.

- **Description:** Mô tả đầy đủ.
- **Parameters:**
    `param1` (type) — Mô tả.
    `oldparam` (boolean) — ~~Mô tả cũ.~~ *Deprecated in build 720000, now ignored.*
    `newparam` (string) — *(Added in build 720000)* Mô tả param mới.
- **Returns:** Nothing.
- **Error states:** Giữ nguyên.
```

#### Events & listeners

```markdown
## Events & listeners
- **Listens to:**
    `existing_event` — triggers `ExistingHandler()` (mô tả).
    `new_event` — triggers `NewHandler()` (mô tả). *(Added in build 720000)*
    ~~`removed_event` — triggers `RemovedHandler()` (mô tả).~~ *(Removed in build 720000)*

- **Pushes:**
    `existing_push` — fired when condition.
    `new_push` — fired when new condition. *(Added in build 720000)*
    ~~`removed_push` — fired when old condition.~~ *(Removed in build 720000)*
```

#### Frontmatter khi MODIFIED

```markdown
---
last_updated: 2026-03-15      # ← cập nhật
build_version: 720000         # ← cập nhật
change_status: updated        # stable → updated
source_hash: 9af32c11         # ← cập nhật
---
```

#### Tóm tắt `change_status` values

| Value | Khi nào dùng |
|-------|-------------|
| `stable` | Không thay đổi |
| `updated` | Có sửa nội dung (MODIFIED) |
| `new` | File mới thêm vào (ADDED) |
| `deprecated` | File bị xóa khỏi source (DELETED) |
| `moved` | Đổi path (MOVED) |

---

### 5. `update_docs.py` — Pipeline chính (thay thế `update_docs_olm.py`)

```
Flow:
1. Đọc diff_report.json
2. Với mỗi change theo thứ tự ưu tiên:
   │
   ├─ MOVED (content_changed: false)
   │     → Rename .md file
   │     → Update frontmatter + thêm moved notice
   │     → Không gọi LLM
   │
   ├─ MOVED (content_changed: true)
   │     → Rename .md file
   │     → Gọi LLM: existing_doc + new_source + unified_diff
   │     → Ghi file
   │
   ├─ ADDED
   │     → Gọi prompt.py pipeline (giống main.py)
   │     → Ghi file mới
   │
   ├─ MODIFIED
   │     → Đọc existing .md doc
   │     → Gọi LLM: existing_doc + new_source + unified_diff
   │     → Ghi file (overwrite)
   │
   └─ DELETED
         → Đọc existing .md doc
         → Gọi LLM: existing_doc → append deprecation block
         → Ghi file (giữ nguyên path)

3. In thống kê kết quả:
   MOVED: X | ADDED: X | MODIFIED: X | DELETED: X | ERRORS: X
```

**Flags:**
- `--dry-run` — Chạy toàn bộ logic nhưng không ghi file, in diff preview ra console
- `--filter <action>` — Chỉ xử lý 1 action type (ví dụ: `--filter modified`)
- `--limit <n>` — Giới hạn số file xử lý (dùng để test)

---

## Verification Plan

### Test tracking

```bash
# Giả lập thay đổi trong dst-scripts:
# - Thêm 1 file mới
# - Sửa nội dung 1 file
# - Xóa 1 file
# - Move 1 file (đổi path)
# - Rename 1 file (cùng thư mục, đổi tên)

py get_diff_update.py

# Verify diff_report.json:
# ✓ action types đúng (added/modified/deleted/moved)
# ✓ unified_diff có nội dung cho MODIFIED
# ✓ MOVED detect đúng (không xuất hiện trong ADDED + DELETED)
# ✓ content_changed đúng cho MOVED
```

### Test pipeline

```bash
# Test dry-run trên 1 file mỗi loại
py update_docs.py --dry-run --limit 1 --filter modified
py update_docs.py --dry-run --limit 1 --filter added
py update_docs.py --dry-run --limit 1 --filter deleted
py update_docs.py --dry-run --limit 1 --filter moved

# Verify output doc:
# ✓ Frontmatter cập nhật đúng (build_version, change_status, source_hash)
# ✓ Inline change notes đúng format (blockquote, strikethrough, inline note)
# ✓ Phần không thay đổi giữ nguyên
# ✓ DELETED có deprecation notice block
# ✓ MOVED có moved notice + file đã rename
```

---

## Thứ tự implement

1. **Migrate `diff_tracker.json`** → format `{hash, content_z}` — nền tảng cho mọi thứ còn lại
2. **Tầng 1 + 2** trong `get_diff_update.py` — hash check + move detection
3. **Tầng 3** trong `get_diff_update.py` — unified diff + output `diff_report.json`
4. **`update_prompt.py`** — bổ sung params + strategies cho từng action
5. **`update_docs.py`** — pipeline với `--dry-run` flag
6. **Verification** — test từng action type với sample thực tế