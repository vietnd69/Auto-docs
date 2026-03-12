# Vision: Pre-Synthesis — Tách structured fields ra khỏi LLM merge

---

## Vấn đề

LLM merge hiện tại nhận toàn bộ chunk results (~1,000 dòng) và phải làm tất cả
trong 1 lần:

- Viết `description` — tóm tắt toàn bộ component thành 1 câu
- Dedup và chọn lọc `tags` — từ hàng trăm tags lặp lại qua 6 chunks
- Quyết định `system_scope` — chọn 1 trong 14 giá trị hợp lệ
- Tổng hợp `dependencies` — list tất cả component references không trùng
- Viết `## Main functions` — phần quan trọng nhất, cần hiểu semantic sâu
- Viết `## Overview` và `## Usage example` — cần nhìn toàn bộ API

Kết quả thực tế trong `actions.md` cho thấy LLM không xử lý tốt khi bị overload:
tags bị lặp hàng chục lần, description chung chung, dependencies bị thiếu.
Nguyên nhân không phải model kém — mà là **attention budget bị phân tán** vào
những việc có thể làm bằng code.

---

## Insight

Không phải tất cả fields trong output đều cần LLM để tổng hợp.

| Field | Cần LLM? | Lý do |
|-------|----------|-------|
| `description` | ✅ Có — nhưng input nhỏ | Cần hiểu ngữ nghĩa, nhưng chỉ cần 6 câu thay vì 1,000 dòng |
| `tags` | ❌ Không | Dedup bằng Python set là đủ |
| `system_scope` | ❌ Không | Majority vote từ suggestions của từng chunk |
| `dependencies` | ❌ Không | Union của tất cả dependency sections |
| `## Main functions` | ✅ Có — và cần toàn bộ attention | Cần hiểu semantic, cross-chunk relationship |
| `## Overview` | ✅ Có | Cần nhìn toàn bộ component |
| `## Usage example` | ✅ Có | Cần biết đủ API mới viết được |

**Kết luận:** 4 fields đầu có thể pre-fill bằng code + 1 LLM call nhỏ.
LLM merge chỉ cần tập trung vào 3 fields cuối — đây mới là giá trị thực.

---

## Giải pháp

Tách pipeline thành 2 giai đoạn rõ ràng:

### Giai đoạn 1 — Extraction (code + 1 LLM call nhỏ)

Sau khi có đủ chunk results, trước khi gọi LLM merge:

```
chunk results
      ↓
Python parser
      ↓
{
  partial_descriptions: [câu 1, câu 2, ..., câu 6]   ← parse từ chunk output
  tags:         {set đã dedup}                        ← parse + Python set
  system_scope: "player"                              ← majority vote
  dependencies: {set đã dedup}                        ← parse + Python set
}
      ↓
synthesize_description()  ← 1 LLM call, input chỉ 6 câu
      ↓
prefilled = {
  description: "Defines and manages player interaction actions...",
  tags: ["actions", "combat", "player"],
  system_scope: "player",
  dependencies: ["health", "combat", "inventory", ...]
}
```

### Giai đoạn 2 — LLM merge (focused)

LLM merge nhận prompt đã có prefilled values — chỉ cần viết:
- `## Overview` — mô tả toàn bộ component
- `## Main functions` — tổng hợp và document tất cả functions
- `## Usage example` — code snippet minh họa

Không còn phải đọc 200 tags lặp lại hay tự quyết định scope.

---

## Kết quả kỳ vọng

### Chất lượng

`tags` trong `actions.md` hiện tại:
```
not_participant, ALREADY_MARKED, ITEMMIMIC, NOCLICK, ... (lặp 10+ lần)
```

Sau pre-synthesis:
```
tags: [actions, combat, crafting, inventory, player]
```

`description` hiện tại — LLM viết từ 1,000 dòng, attention bị chia:
```
description: Defines and manages player interaction actions...  (chung chung)
```

Sau pre-synthesis — LLM chỉ nhận 6 câu ngắn để merge:
```
description: Defines the core action system for DST player interactions,
             implementing execution logic, range checks, and ECS integration
             for 200+ actions across combat, crafting, and world interaction.
```

### Focus

LLM merge hiện tại phân bổ attention:
```
tags dedup          ████░░░░░░  ~20%
description         ██░░░░░░░░  ~10%
scope decision      █░░░░░░░░░  ~5%
dependencies list   ██░░░░░░░░  ~10%
Main functions      █████░░░░░  ~55%   ← đây mới là phần quan trọng
```

Sau pre-synthesis:
```
Main functions      █████████░  ~90%   ← gần như toàn bộ attention
Overview/Example    █░░░░░░░░░  ~10%
```

---

## Scope

### Trong spec này

- Parse `tags`, `system_scope`, `dependencies` từ chunk results bằng Python
- Thêm `## Partial description` và `## Suggested scope` vào chunk prompt
- `synthesize_description()` — 1 LLM call nhỏ, input chỉ là partial descriptions
- Inject prefilled values vào `build_merge_prompt()`

### Ngoài scope

- Parallel chunk analysis — spec riêng (#3)
- Pre-fill `## Main functions` — quá phức tạp, cần LLM để dedup semantic
- Pre-fill `## Usage example` — cần biết full API mới viết được

---

## Rủi ro

**Parse sai format** — nếu LLM chunk không output đúng section header, parser
trả về empty → graceful degrade: merge prompt nhận placeholder rỗng như hiện tại,
LLM merge tự điền. Không break pipeline.

**`synthesize_description` fail** — tương tự, fallback về placeholder rỗng.
LLM merge vẫn chạy bình thường, chỉ mất đi lợi ích của pre-synthesis.

**Overhead** — thêm 1 LLM call/file (synthesize_description). Với file ngắn
(không cần chunking) thì không trigger — chỉ áp dụng cho chunked pipeline.
