# Design: Fix Data Config File Pattern in Prompt Skills

**Date:** 2026-03-20
**Scope:** `skills/quality_rules.md`, `skills/few_shot_data.md`, `docs_SKILL.md`
**Problem:** LLM gen docs cho data config files (no constructor, returns plain table/array) vẫn bỏ sót record schema trong Properties table, dù rule đã tồn tại.

---

## Root Cause

1. **Classification không explicit** — model phải tự suy ra "đây là data config file" từ ngữ cảnh. Không có trigger rõ ràng buộc model switch sang data config rules trước khi viết.
2. **Rule prominence thấp** — `DATA CONFIG FILE PROPERTIES` rule nằm giữa nhiều rules khác, không có `MUST`/`NEVER` đủ mạnh.
3. **few_shot_data.md chưa đủ mạnh** — field names trừu tượng (`platform`, `numeric`), thiếu detection cue ở đầu file, và header detection chưa được link đến classification block trong quality_rules.md.
4. **Chunked pipeline injection gap** — `few_shot_data.md` hiện chỉ inject vào `single_prompt`, không có trong `merge_prompt`. Data config files hiếm khi vượt 32K tokens nên đây là low-risk, nhưng cần fix để coverage đầy đủ.

---

## Approach: A + B + docs_SKILL.md patch

### A — Strengthen `quality_rules.md`

**1. Thêm FILE TYPE CLASSIFICATION block** ngay trên PROPERTIES TABLE section. Block này phải xuất hiện trước tất cả section-specific rules để model classify trước khi viết bất cứ section nào:

```
FILE TYPE CLASSIFICATION (determine before writing any section):
- DATA CONFIG FILE: no Class() constructor, no self.inst, returns a plain table/array.
  → MUST apply ALL [Data config] rules. Do NOT use [Component] patterns.
  → Consult the HOW TO DETECT note at the top of the data config few-shot example.
- COMPONENT FILE: has Class(function(self, ...) ... end) constructor.
  → MUST apply ALL [Component] rules. Do NOT use [Data config] patterns.
When signals are mixed (e.g., local helper functions that resemble constructors),
check: does the file's top-level return value contain a plain array/table, not a class instance?
If yes → DATA CONFIG FILE.
```

**2. Rewrite DATA CONFIG FILE PROPERTIES rule** với MUST/NEVER language:

```
DATA CONFIG FILE PROPERTIES:
MUST document TWO groups of rows in this order:
  1. The top-level container variable (the returned global/local table).
  2. One row per key in each record entry (e.g., name, id.steam, id.psn).
NEVER document only the container and omit the record schema.
NEVER use a real default value for record fields — always write "—" (em dash).
```

**3. Back-reference trong OVERVIEW WRITING và USAGE EXAMPLE WRITING** — giữ nguyên các inline `[Component]` / `[Data config]` labels hiện có, thêm một dòng reminder (không xóa labels cũ):

```
(As classified above — see FILE TYPE CLASSIFICATION.)
```

Giữ labels cũ để tránh mất context inline; back-reference chỉ là reminder, không phải re-trigger classification.

---

### B — Rewrite `few_shot_data.md`

**1. Thêm HOW TO DETECT header** ngay dòng đầu tiên (trước example content):

```
HOW TO DETECT: source file has NO Class() constructor, no self.inst,
and returns a plain table/array at top level → use this example, NOT the component example.
```

**2. Cập nhật Properties table** — dùng field names gần DST (`steam`/`psn`), show rõ 2 groups:

| Property | Type | Default Value | Description |
|---|---|---|---|
| `SampleRegistry` | table | — | Array-indexed global table of record tables; position corresponds to numeric ID order. |
| `name` | string | — | Internal lowercase underscore-separated name used in code (e.g., `"entry_alpha"`). |
| `id.steam` | string | — | Steam identifier, formatted as `<id>_<name>` (e.g., `"1_entry_alpha"`). |
| `id.psn` | number | — | PSN numeric ID from the platform definition file. |

**3. Cập nhật ENTRY() parameter description** — show rõ cả 2 platform behaviors:

```
- `id` (string or number) — base identifier; stored as string for steam
  via tostring(id).."_"..name concatenation; kept as-is (number) for psn.
- `name` (string) — internal name used in code.
```

---

### docs_SKILL.md patch

Thêm `few_shot_data` vào `inject_into: [merge_prompt]` để coverage chunked pipeline:

```yaml
## few_shot_data
file: skills/few_shot_data.md
inject_into: [single_prompt, merge_prompt]   # was: [single_prompt]
```

---

## Files Changed

| File | Change |
|---|---|
| `skills/quality_rules.md` | Add classification trigger block; strengthen DATA CONFIG PROPERTIES rule; add back-references (keeping inline labels) |
| `skills/few_shot_data.md` | Add HOW TO DETECT header; update field names to steam/psn; clarify parameter descriptions |
| `docs_SKILL.md` | Add `merge_prompt` to few_shot_data inject_into |

## Files NOT Changed

| File | Reason |
|---|---|
| `skills/dst_conventions.md` | DST conventions không liên quan đến classification issue |
| `skills/function_format.md` | Function format đúng, không cần sửa |
| `skills/few_shot.md` | Component example đúng, không cần sửa |

---

## Success Criteria

**Fix verification (data config file — achievements.lua):**
1. Properties table có đủ 4 rows: `Achievements`, `name`, `id.steam`, `id.psn`
2. Usage example dùng array index (`Achievements[1]`), không dùng string key
3. Overview không chứa các từ "AddComponent", "ECS", "entity", "component" trong context mô tả file này
4. ACHIEVEMENT() params section phải reference cả `tostring(id).."_"..name` concatenation behavior (Steam) VÀ numeric passthrough (`psn = id`) explicitly

**Regression verification (component file):**
5. Gen lại một component file đã biết kết quả đúng → Properties table vẫn dùng constructor-sourced fields, không xuất hiện two-group schema của data config
