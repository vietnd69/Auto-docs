# Per-file Validation Pipeline Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate validation (content loop + format autofix) into `uv run mod-document` so each Lua file is validated immediately after its doc is generated.

**Architecture:** Inline integration in `core/src/core/main.py` — after successful generation, call `validator.pipeline.process_file()`. No new modules. Add `--no-validate` flag to skip. On content failure, delete the generated `.md` file.

**Tech Stack:** Python 3.11, `uv run pytest`, `unittest.mock`

**Spec:** `docs/superpowers/specs/2026-03-22-per-file-validation-pipeline-design.md`

---

## Chunk 1: Tests and Implementation

### Task 1: Move `count_tokens` import to module level in `main.py`

**Files:**
- Modify: `core/src/core/main.py`

Currently `count_tokens` is imported inside the loop body (line 161). Move it to module level so it can be patched in tests.

- [ ] **Step 1: Move the import**

Remove this line from inside the `for filename in file_list:` loop body (line ~161):
```python
        from llm.tokens import count_tokens
```

Add at the top of `main.py` with the other imports (after `from core.pipeline.chunked import process_chunked_file`):
```python
from llm.tokens import count_tokens
```

- [ ] **Step 2: Verify the system still runs**

```bash
cd /d/code/mod-document && uv run mod-document --help
```

Expected: help text prints without error.

- [ ] **Step 3: Commit**

```bash
git add core/src/core/main.py
git commit -m "refactor(main): move count_tokens import to module level"
```

---

### Task 2: Write failing tests for the new routing logic

**Files:**
- Create: `core/tests/test_main_validate_routing.py`

- [ ] **Step 1: Create the test file**

```python
# core/tests/test_main_validate_routing.py
"""
Unit tests for the post-generate validation routing in main.py.
Uses unittest.mock to avoid any LLM or filesystem calls.
"""
import argparse
from dataclasses import dataclass
from unittest.mock import MagicMock, patch
import pytest


@dataclass
class FakeFileResult:
    final_status: str


# Shared patch targets — all module-level names in core.main that touch I/O or LLM.
# process_chunked_file is always patched to prevent real chunked pipeline calls.
COMMON_PATCHES = [
    "core.main.generate_doc",
    "core.main.process_chunked_file",
    "core.main.needs_chunking",
    "core.main.get_lua_files",
    "core.main.safe_read_lua",
    "core.main.extract_lua_references",
    "core.main.format_connected_section",
    "core.main.extract_connected_content",
    "core.main.build_prompt",
    "core.main.count_tokens",
    "core.main.compute_source_hash",
]


def apply_common_patches(tmp_path, extra_patches=None):
    """Return a list of patch context managers with sensible defaults."""
    patches = {
        "core.main.generate_doc": MagicMock(return_value="out.md"),
        "core.main.process_chunked_file": MagicMock(return_value="out.md"),
        "core.main.needs_chunking": MagicMock(return_value=False),
        "core.main.get_lua_files": MagicMock(return_value=["combat.lua"]),
        "core.main.safe_read_lua": MagicMock(return_value="lua code"),
        "core.main.extract_lua_references": MagicMock(return_value=[]),
        "core.main.format_connected_section": MagicMock(return_value=""),
        "core.main.extract_connected_content": MagicMock(return_value=""),
        "core.main.build_prompt": MagicMock(return_value="prompt"),
        "core.main.count_tokens": MagicMock(return_value=100),
        "core.main.compute_source_hash": MagicMock(return_value="abc"),
        "core.main.BASE_DOCS_DIR": str(tmp_path),
        "core.main.BASE_LUA_DIR": str(tmp_path),
    }
    if extra_patches:
        patches.update(extra_patches)
    return patches


class TestNoValidateFlag:
    """--no-validate: process_file is never called; successful generate → processed."""

    def test_process_file_not_called(self, tmp_path):
        patches = apply_common_patches(tmp_path)
        with patch("core.main.process_file") as mock_pf, \
             *[patch(k, v) for k, v in patches.items()], \
             patch("sys.argv", ["mod-document", "--no-validate"]):
            from core.main import main
            main()
        mock_pf.assert_not_called()


class TestValidationRouting:
    """With validation enabled (default), test all four final_status paths."""

    def _run(self, tmp_path, final_status):
        md_file = tmp_path / "out.md"
        md_file.write_text("content")
        fake_result = FakeFileResult(final_status=final_status)
        patches = apply_common_patches(tmp_path)
        with patch("core.main.process_file", return_value=fake_result), \
             *[patch(k, v) for k, v in patches.items()], \
             patch("sys.argv", ["mod-document"]):
            from core.main import main
            main()
        return md_file

    def test_ok_file_survives(self, tmp_path):
        md_file = self._run(tmp_path, "ok")
        assert md_file.exists()

    def test_skipped_chunked_file_survives(self, tmp_path):
        md_file = self._run(tmp_path, "skipped_chunked")
        assert md_file.exists()

    def test_content_failed_deletes_md_file(self, tmp_path):
        md_file = self._run(tmp_path, "content_failed")
        assert not md_file.exists(), "content_failed must delete the .md file"

    def test_format_failed_keeps_md_file(self, tmp_path):
        md_file = self._run(tmp_path, "format_failed")
        assert md_file.exists(), "format_failed must keep the .md file on disk"


class TestValidationException:
    """process_file raises unexpected exception → failed+validate_failed, loop continues."""

    def test_exception_does_not_crash_loop(self, tmp_path):
        """Two files: first triggers exception, second succeeds. Loop must not crash."""
        call_count = 0
        def flaky(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise RuntimeError("disk error")
            return FakeFileResult(final_status="ok")

        patches = apply_common_patches(
            tmp_path,
            {"core.main.get_lua_files": MagicMock(return_value=["a.lua", "b.lua"])}
        )
        with patch("core.main.process_file", side_effect=flaky), \
             *[patch(k, v) for k, v in patches.items()], \
             patch("sys.argv", ["mod-document"]):
            from core.main import main
            main()  # must not raise


class TestGenerateFailSkipsValidation:
    """generate returns None → process_file never called."""

    def test_generate_fail_skips_validate(self, tmp_path):
        patches = apply_common_patches(
            tmp_path,
            {"core.main.generate_doc": MagicMock(return_value=None)}
        )
        with patch("core.main.process_file") as mock_pf, \
             *[patch(k, v) for k, v in patches.items()], \
             patch("sys.argv", ["mod-document"]):
            from core.main import main
            main()
        mock_pf.assert_not_called()
```

- [ ] **Step 2: Run tests — expect failures**

```bash
cd /d/code/mod-document && uv run pytest core/tests/test_main_validate_routing.py -v 2>&1 | head -40
```

Expected: errors about missing `--no-validate` flag or `core.main.process_file` not found.

- [ ] **Step 3: Commit the failing tests**

```bash
git add core/tests/test_main_validate_routing.py
git commit -m "test(main): add failing tests for per-file validation routing"
```

---

### Task 3: Implement the changes in `main.py`

**Files:**
- Modify: `core/src/core/main.py`

- [ ] **Step 1: Add validator import**

Add after line 19 (`from core.pipeline.chunked import process_chunked_file`):

```python
from validator.pipeline import process_file, PipelineConfig
```

- [ ] **Step 2: Add `--no-validate` CLI flag**

Add after the `--force` argument block (after line 37):

```python
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip validation (generate only, no content loop or format fix)",
    )
```

- [ ] **Step 3: Add `validate_failed` to stats dict**

Replace line 85:
```python
    stats = {"processed": 0, "skipped": 0, "failed": 0, "failed_list": []}
```
With:
```python
    stats = {"processed": 0, "skipped": 0, "failed": 0, "failed_list": [], "validate_failed": 0}
```

- [ ] **Step 4: Replace the post-generate routing block**

Replace the existing block (lines ~200–204):
```python
        if result:
            stats["processed"] += 1
        else:
            stats["failed"] += 1
            stats["failed_list"].append(filename)
```

With:
```python
        if not result:
            stats["failed"] += 1
            stats["failed_list"].append(filename)
            continue

        if args.no_validate:
            stats["processed"] += 1
            continue

        # --- Validation ---
        try:
            file_result = process_file(md_filepath, PipelineConfig(
                writer_model=MODEL_NAME,
                reviewer_model=MODEL_NAME,
            ))
        except KeyboardInterrupt:
            # Do NOT re-raise — outer loop exits via shutdown.stop_requested.
            stats["failed"] += 1
            stats["validate_failed"] += 1
            stats["failed_list"].append(filename)
            shutdown.request_stop()
            continue
        except Exception as e:
            # Unexpected validator error (e.g. disk issue) — counts as validate_failed.
            print(f"  [Lỗi validate] {filename}: {e}")
            stats["failed"] += 1
            stats["validate_failed"] += 1
            stats["failed_list"].append(filename)
            continue

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
            stats["failed"] += 1
            stats["validate_failed"] += 1
            stats["failed_list"].append(filename)
```

- [ ] **Step 5: Update summary display**

Replace the summary block (lines ~207–214):
```python
    print("\n" + "=" * 60)
    print(f"[Thống kê] Hoàn tất!")
    print(f"  Đã xử lý : {stats['processed']} file")
    print(f"  Đã bỏ qua: {stats['skipped']} file")
    print(f"  Thất bại : {stats['failed']} file")
    if stats["failed_list"]:
        print(f"  Danh sách file lỗi: {', '.join(stats['failed_list'])}")
    print("=" * 60)
```

With:
```python
    print("\n" + "=" * 60)
    print(f"[Thống kê] Hoàn tất!")
    print(f"  Đã xử lý : {stats['processed']} file")
    print(f"  Đã bỏ qua: {stats['skipped']} file")
    if stats["failed"] > 0:
        print(f"  Thất bại  : {stats['failed']} file")
        generate_fail = stats["failed"] - stats["validate_failed"]
        if not args.no_validate and stats["validate_failed"] > 0:
            print(f"    → Validation fail: {stats['validate_failed']}")
        if generate_fail > 0:
            print(f"    → Generate fail  : {generate_fail}")
    else:
        print(f"  Thất bại  : 0 file")
    if stats["failed_list"]:
        print(f"  Danh sách file lỗi: {', '.join(stats['failed_list'])}")
    print("=" * 60)
```

- [ ] **Step 6: Run the tests — expect all pass**

```bash
cd /d/code/mod-document && uv run pytest core/tests/test_main_validate_routing.py -v
```

Expected: all tests PASS

- [ ] **Step 7: Run full test suite for regressions**

```bash
cd /d/code/mod-document && uv run pytest core/tests/ validator/tests/ -v --ignore=core/tests/chunked_test.py --ignore=core/tests/test.py --ignore=core/tests/test_per_chunk.py --ignore=core/tests/test_file_type_detection.py
```

Expected: all existing tests still pass

- [ ] **Step 8: Commit the implementation**

```bash
git add core/src/core/main.py
git commit -m "feat(main): integrate per-file validation into generation pipeline

- Add --no-validate flag to skip content + format validation
- After successful generate: run validator.pipeline.process_file()
- content_failed → delete .md, count as failed+validate_failed
- format_failed → keep .md, count as failed+validate_failed
- ok / skipped_chunked → count as processed
- except Exception in process_file → count as failed+validate_failed
- Add validate_failed counter with breakdown in summary"
```

---

## Chunk 2: Smoke Test

### Task 4: Manual smoke test

- [ ] **Step 1: Verify CLI help shows new flag**

```bash
cd /d/code/mod-document && uv run mod-document --help
```

Expected output includes:
```
  --no-validate         Skip validation (generate only, no content loop or format fix)
```

- [ ] **Step 2: Verify `--no-validate` skips validation in single-file mode**

Pick any `.lua` file that already has a corresponding `.md` in `dst-api-webdocs/docs/`, delete the `.md`, then run:

```bash
uv run mod-document <path-to.lua> --no-validate
```

Expected: doc generated, no `[content]` or `[pipeline]` lines in output, summary shows `Đã xử lý: 1 file`, `Thất bại: 0 file`.

- [ ] **Step 3: Empty commit as sign-off**

```bash
git commit --allow-empty -m "chore: smoke test passed for per-file validation pipeline"
```
