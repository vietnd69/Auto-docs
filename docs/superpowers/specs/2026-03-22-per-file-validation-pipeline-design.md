# Design: Per-file Validation Pipeline Integration

**Date:** 2026-03-22
**Status:** Approved

## Problem

Currently `uv run mod-document` only generates documentation. Validation (`uv run python -m validator`) is a separate manual step. This means a doc can be "generated" but invalid — requiring the user to re-run the validator and track failures separately.

## Goal

Integrate validation into the generation pipeline so each Lua file goes through:

```
generate doc → content loop → format autofix → next file
```

## Approach

Inline integration in `core/src/core/main.py` using the existing `validator.pipeline.process_file()` function. No new modules or abstraction layers needed.

## Flow Per File

```
for each .lua file:

  1. generate_doc() / process_chunked_file()
       fail  → stats["failed"]++, continue
       success → file.md written to disk

  2. [skip entirely if --no-validate]
     validator.pipeline.process_file(md_filepath, PipelineConfig)

     content loop (LLM review → patch → repeat, max 3 iterations):
       → approved          → proceed to format fix
       → not approved      → DELETE file.md, stats["failed"]++, stats["validate_failed"]++, continue
       → skipped_chunked   → proceed to format fix (chunked files skip content by design)

     format autofix:
       → remaining_errors  → stats["failed"]++, stats["validate_failed"]++, file stays on disk
       → no errors         → stats["processed"]++

  3. next file
```

## CLI Changes

Add to `argparse` in `main.py`:

```python
parser.add_argument(
    "--no-validate", "-n",
    action="store_true",
    help="Skip validation (generate only, no content loop or format fix)",
)
```

## Stats Changes

```python
stats = {
    "processed": 0,        # generate + validate OK (or generate OK when --no-validate)
    "skipped": 0,          # docs already exist, skipped
    "failed": 0,           # generate fail OR validation fail
    "failed_list": [],     # filenames of all failures
    "validate_failed": 0,  # breakdown: how many failures were due to validation
}
```

## Summary Output

```
============================================================
[Thống kê] Hoàn tất!
  Đã xử lý : 42 file
  Đã bỏ qua: 10 file
  Thất bại  : 3 file
    → Validation fail: 2
    → Generate fail  : 1
  Danh sách file lỗi: ...
============================================================
```

When `--no-validate` is used, the "Validation fail" breakdown line is omitted.

## What Changes

### `core/src/core/main.py`
- Add `--no-validate` / `-n` CLI flag
- Import `validator.pipeline.process_file` and `PipelineConfig`
- After successful generate: if not `--no-validate`, call `process_file(md_filepath, PipelineConfig())`
- Handle `final_status`:
  - `"content_failed"` → `os.remove(md_filepath)`, count `failed` + `validate_failed`
  - `"format_failed"` → count `failed` + `validate_failed` (file stays on disk)
  - `"ok"` or `"skipped_chunked"` → count `processed`
- Update summary print to include `validate_failed` breakdown

## What Does NOT Change

- `validator/pipeline.py` — used as-is
- `validator/content/loop.py` — used as-is
- `validator/format/autofix.py` — used as-is
- `core/pipeline/standard.py` — used as-is
- `core/pipeline/chunked.py` — used as-is

## Constraints

- `PipelineConfig` defaults: `content_max_iterations=3`, models from existing config
- Chunked files (Lua source ≥ 32K tokens) skip content loop automatically — this is existing behavior in `validator/pipeline.py`, no special handling needed in `main.py`
- `--no-validate` when used with single-file mode (`uv run mod-document file.lua`) also works — validation is simply skipped
