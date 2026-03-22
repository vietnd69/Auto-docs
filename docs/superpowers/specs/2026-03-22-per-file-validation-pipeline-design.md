# Design: Per-file Validation Pipeline Integration

**Date:** 2026-03-22
**Status:** Approved

## Goal

Integrate validation into the generation pipeline so each Lua file goes through:
`generate doc → content loop → format autofix → next file`

## Approach

Inline integration in `core/src/core/main.py` using the existing `validator.pipeline.process_file()`.

## Flow Per File

Replace the existing `if result: stats["processed"]++ ... else: stats["failed"]++` block with:

```python
# Step 1: generate (existing try/except KeyboardInterrupt block — unchanged)
try:
    if needs_chunking(prompt_text):
        result = process_chunked_file(...)
    else:
        result = generate_doc(...)
except KeyboardInterrupt:
    result = os.path.basename(md_filepath) if os.path.exists(md_filepath) else None

# Step 2: route on generate result
if not result:
    stats["failed"] += 1
    stats["failed_list"].append(filename)
    continue

# Step 3: skip validation if requested
if args.no_validate:
    stats["processed"] += 1
    continue

# Step 4: validate — uses md_filepath (full path), NOT result (which is basename only)
try:
    file_result = process_file(md_filepath, PipelineConfig(
        writer_model=MODEL_NAME,
        reviewer_model=MODEL_NAME,
    ))
except KeyboardInterrupt:
    # Do NOT re-raise — mirror existing generate block behavior.
    # Outer loop exits via shutdown.stop_requested on next iteration.
    stats["failed"] += 1
    stats["validate_failed"] += 1
    stats["failed_list"].append(filename)
    shutdown.request_stop()
    continue
except Exception as e:
    print(f"  [Lỗi validate] {filename}: {e}")
    stats["failed"] += 1
    stats["validate_failed"] += 1
    stats["failed_list"].append(filename)
    continue

# Step 5: handle validation outcome
if file_result.final_status in ("ok", "skipped_chunked"):
    stats["processed"] += 1
elif file_result.final_status == "content_failed":
    try:
        os.remove(md_filepath)
    except OSError as e:
        print(f"  [Cảnh báo] Không thể xóa {md_filepath}: {e}")
    stats["failed"] += 1
    stats["validate_failed"] += 1
    stats["failed_list"].append(filename)
elif file_result.final_status == "format_failed":
    # Keep file.md on disk — has content, just has remaining format errors
    stats["failed"] += 1
    stats["validate_failed"] += 1
    stats["failed_list"].append(filename)
```

## Known Limitations (no action required)

**Chunked threshold mismatch:** The generation pipeline chunks when the full prompt > 16K tokens. The validator skips content review (`skipped_chunked`) when Lua source itself > 32K tokens. These thresholds are independent — a file can go through chunked generation but still receive content review in the validator, or vice versa. This is acceptable: `skipped_chunked` reflects the validator's own capacity limit, not the generation pipeline's decision.

**`skipped_chunked` skips format autofix:** `pipeline.process_file()` returns early before running format autofix for `skipped_chunked` files. These files count as `processed` with no format check. This is a known limitation — users can run `uv run python -m validator --format-only` separately for chunked files.

**Pre-generate failures in stats:** `safe_read_lua()` returning `None` (lines 120–123 of existing main.py) increments `stats["failed"]` before the generate step. The summary `generate_fail = failed - validate_failed` will include these. "Generate fail" is used as a label for "failed before or during generation", which is acceptable.

**Content validation silent skip in pipeline:** If `pipeline.process_file()` cannot read the Lua source via `resolve_lua_path()`, content validation is silently skipped and the file may return `"ok"`. This is existing `validator/pipeline.py` behavior — out of scope for this change.

## CLI

```python
parser.add_argument(
    "--no-validate",
    action="store_true",
    help="Skip validation (generate only, no content loop or format fix)",
)
```
No short flag. Works in both batch mode and single-file mode, independent of `force_regen`.

## Stats

```python
stats = {
    "processed": 0,       # generate + validate OK (or generate-only with --no-validate)
    "skipped": 0,         # docs already exist
    "failed": 0,          # any failure (generate, pre-generate, or validation)
    "failed_list": [],    # relative .lua filenames — consistent for all failure types
    "validate_failed": 0, # subset of failed: caused by validation (not generation)
}
```

## Summary Display

```python
if stats["failed"] > 0:
    print(f"  Thất bại  : {stats['failed']} file")
    generate_fail = stats["failed"] - stats["validate_failed"]
    if not args.no_validate and stats["validate_failed"] > 0:
        print(f"    → Validation fail: {stats['validate_failed']}")
    if generate_fail > 0:
        print(f"    → Generate fail  : {generate_fail}")
if stats["failed_list"]:
    print(f"  Danh sách file lỗi: {', '.join(stats['failed_list'])}")
```

## What Changes

**`core/src/core/main.py` only:**
- Add `--no-validate` flag to `argparse`
- Add `from validator.pipeline import process_file, PipelineConfig`
- Add `validate_failed: 0` to `stats` dict
- Replace `if result: ... else: ...` block with flow above
- Update summary print with new display rules

## What Does NOT Change

`validator/pipeline.py`, content loop, format autofix, standard/chunked pipeline — all used as-is.
