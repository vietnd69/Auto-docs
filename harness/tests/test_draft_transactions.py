"""Separate MCP processes must not overwrite each other's sections or metadata."""
from __future__ import annotations

import multiprocessing

import frontmatter
import pytest

from draft_worker import _write_concurrently
from harness import file_transaction, pages


@pytest.mark.parametrize("second_action", ["## Usage example", "metadata"])
def test_concurrent_process_updates_preserve_both_changes(planned, second_action):
    page = pages.get_plan(planned).page("components/health")
    pages.ensure_draft(planned, page)
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    processes = [
        ctx.Process(target=_write_concurrently, args=(str(planned.settings.root),
                    planned.settings.values, barrier, action))
        for action in ("## Overview", second_action)
    ]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=15)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
    text = pages.read_draft(planned, page)
    assert "Content for ## Overview" in text
    if second_action == "metadata":
        assert frontmatter.loads(text).metadata["description"] == "Concurrent metadata survives"
    else:
        assert "Content for ## Usage example" in text


def test_failed_atomic_replace_preserves_original_and_cleans_temp(tmp_path, monkeypatch):
    draft = tmp_path / "draft.md"
    draft.write_text("original", encoding="utf-8")

    def fail_replace(*args):
        raise OSError("simulated replacement failure")

    monkeypatch.setattr(file_transaction.os, "replace", fail_replace)
    with pytest.raises(OSError, match="simulated"), file_transaction.file_transaction(draft):
        file_transaction.atomic_write(draft, "replacement")
    assert draft.read_text(encoding="utf-8") == "original"
    assert not list(tmp_path.glob("*.tmp"))
    # An exception must release the transaction too.
    with file_transaction.file_transaction(draft):
        assert draft.read_text(encoding="utf-8") == "original"
