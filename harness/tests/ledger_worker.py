from harness.config import Settings
from harness.ledger import Evidence, Ledger
from harness.workspace import make_workspace


def write_ledger(root, values, barrier, index):
    from pathlib import Path

    ws = make_workspace(Settings(Path(root), values), "HEAD")
    ledger = Ledger(ws, "components/health")
    barrier.wait(timeout=15)  # Both instances load BEFORE either process writes.
    evidence = Evidence("components/health.lua", 20, 25, 'self.inst:PushEvent("healthdelta"')
    for n in range(10):
        assert ledger.add(f"symbol-{index}-{n}", "field", "claim", evidence)[0]
    barrier.wait(timeout=15)
    for finding in ledger.open_findings():
        if finding.symbol.startswith(f"symbol-{index}-"):
            ledger.resolve(finding.id, "checked")
