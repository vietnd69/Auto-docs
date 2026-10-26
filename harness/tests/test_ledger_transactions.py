import multiprocessing

import pytest

from harness.ledger import Ledger, LedgerCorruptError
from harness.verdict import evaluate
from ledger_worker import write_ledger
from test_pages_checks import fill


def test_separate_processes_preserve_additions_and_resolutions(ws):
    ctx = multiprocessing.get_context("spawn")
    barrier = ctx.Barrier(2)
    processes = [ctx.Process(target=write_ledger,
                 args=(str(ws.settings.root), ws.settings.values, barrier, i)) for i in range(2)]
    try:
        for process in processes:
            process.start()
        for process in processes:
            process.join(timeout=30)
            assert process.exitcode == 0
    finally:
        for process in processes:
            if process.is_alive():
                process.terminate()
                process.join()
    items = Ledger(ws, "components/health").items
    assert len(items) == 20
    assert all(f.status == "resolved" for f in items.values())


def test_corrupt_ledger_preserved_and_verdict_fails_closed(planned, no_mdx):
    from harness.pages import get_plan

    page = fill(planned)
    path = planned.ledger_path(page.id)
    damaged = b'tername] or 0 end"], "note": ""}\n'
    path.write_bytes(damaged)
    with pytest.raises(LedgerCorruptError, match="line 1"):
        Ledger(planned, page.id)
    verdict = evaluate(planned, get_plan(planned), page)
    assert verdict.status == "FAIL"
    assert any(i.code == "LEDGER_CORRUPT" for i in verdict.issues)
    assert path.read_bytes() == damaged
