from __future__ import annotations

from harness.ledger import Evidence, Ledger
from harness.memory import Library, render_long_term, search
from harness.workspace import Workspace

GOOD = Evidence("components/health.lua", 20, 25, 'self.inst:PushEvent("healthdelta"')


def test_ledger_rejects_unverifiable_evidence(ws: Workspace) -> None:
    ledger = Ledger(ws, "components/health")
    assert (
        ledger.add("Health:DoDelta", "events", "x", Evidence("components/health.lua", 20, 25, "not there"))[0]
        is False
    )
    assert ledger.add("s", "f", "x", Evidence("components/health.lua", 9, 3, "abc"))[0] is False
    assert ledger.add("s", "f", "x", Evidence("components/health.lua", 1, 1, "a"))[0] is False
    assert ledger.add("s", "f", "x", Evidence("../etc/passwd", 1, 2, "root"))[0] is False


def test_ledger_lifecycle_blocks_same_evidence_reopen(ws: Workspace) -> None:
    ledger = Ledger(ws, "components/health")
    ok, message = ledger.add("Health:DoDelta", "events", "event missing", GOOD)
    assert ok and "opened" in message
    fid = ledger.open_findings()[0].id
    assert ledger.add("Health:DoDelta", "Events ", "reworded", GOOD)[1].startswith("updated")
    assert ledger.resolve(fid, "fixed") == f"{fid} → resolved"
    again = Ledger(ws, "components/health")  # reload from disk
    assert again.add("Health:DoDelta", "events", "same point again", GOOD)[0] is False
    other = Evidence("components/health.lua", 22, 22, "math.clamp")
    assert again.add("Health:DoDelta", "events", "new evidence", other)[1].startswith("reopened")
    assert "open" in again.render("open")
    assert again.resolve("nope", "x").startswith("unknown")
    assert again.resolve(fid, "x", "open").startswith("status must")


def test_memory_add_dedupe_cap_search(ws: Workspace) -> None:
    lib = Library(ws, "stategraph")
    assert lib.add("", "x", "y").startswith("rejected")
    assert lib.add(
        "documenting nested EventHandler in states", "list them under the state", "SGpig"
    ).startswith("added")
    assert lib.add(
        "documenting nested EventHandler inside states", "longer lesson text here", "SGwilson"
    ).startswith("confirmed")
    assert "WHEN documenting nested" in search(ws, "stategraph", "EventHandler states")
    assert search(ws, "brain", "nothing") == "no lessons yet for this domain"
    small = Library(ws, "brain")
    small.cap = 2
    for i in range(4):
        small.add(f"cue number {i} unique{i}", "lesson", "ev")
    assert len(Library(ws, "brain").entries) == 2
    rendered = render_long_term(ws, ["stategraph", "brain"], 5)
    assert rendered.startswith("# Long-term memory") and "[stategraph]" in rendered
