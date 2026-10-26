"""Importable subprocess worker for the draft transaction regression tests."""
from contextlib import suppress
from pathlib import Path
from threading import BrokenBarrierError

from harness import pages
from harness.config import Settings
from harness.tools import api
from harness.workspace import make_workspace


def _write_concurrently(root, values, barrier, action):
    ws = make_workspace(Settings(Path(root), values), "HEAD")
    api.use_workspace(ws)
    original = pages.ensure_draft

    def synchronized_read(*args, **kwargs):
        text = original(*args, **kwargs)
        # Before the fix both processes read the old draft before either writes.
        # A real transaction serializes the second read; the barrier then times out.
        with suppress(BrokenBarrierError):
            barrier.wait(timeout=1)
        return text

    pages.ensure_draft = synchronized_read
    if action == "metadata":
        api.doc_set_meta("components/health", "Concurrent metadata survives", "health")
    else:
        api.doc_write_section("components/health", action, f"Content for {action}")
