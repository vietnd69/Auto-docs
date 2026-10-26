from __future__ import annotations

import json
import sqlite3

import pytest

from harness.checks import _format_contract_issue, _phantom_issues
from harness.codeindex import index_codebase
from harness.improve import Score
from harness.usage import regression_cost


def test_reference_without_call_is_checked(planned):
    index = index_codebase(planned)
    assert _phantom_issues("Use `Health:Nonexistent` here.", index)
    assert not _phantom_issues("Use `Health:GetPercent` here.", index)


def test_numeric_format_contract_is_narrow():
    source = 'function Sensor:GetDebugString()\n return string.format("value:%f", self.value)\nend'
    assert _format_contract_issue(source, "* **Error states:** None -- harmless.")
    assert not _format_contract_issue(source, "* **Error states:** Invalid field types may raise.")
    assert not _format_contract_issue(
        source.replace("return string", 'if type(self.value) ~= "number" then return "" end\n return string'),
        "* **Error states:** None",
    )
    assert not _format_contract_issue(source.replace("%f", "%s"), "* **Error states:** None")
    assert _format_contract_issue(source, "* **Error states:** Errors for a non-number.")
    assert not _format_contract_issue(
        source, "* **Error states:** Invalid values raise; numeric strings are accepted."
    )


@pytest.mark.parametrize(
    "candidate",
    [
        Score(0, 0, 0),
        Score(1, 0, 1, {"a": "PASS"}, 0.01),
        Score(2, 0, 2, {"a": "PASS", "b": "PASS"}, None),
        Score(2, 0, 2, {"a": "PASS", "b": "PASS"}, 0.11),
        Score(2, 0, 2, {"a": "PASS", "b": "PASS"}, 0.1),
        Score(2, 0, 2, {"a": "PASS", "c": "PASS"}, 0.01),
        Score(2, 0, 2, {"a": "PASS", "b": "FAIL"}, 0.01),
        Score(2, 0, 2, {"a": "PASS", "b": "PASS"}, float("nan")),
    ],
)
def test_promotion_rejects_insufficient_or_regressing_evidence(candidate):
    assert not candidate.at_least(Score(2, 0, 2, {"a": "PASS", "b": "PASS"}, 0.1))


def test_usage_includes_all_agents_and_rejects_unknown_model(tmp_path):
    database = tmp_path / "opencode.db"
    with sqlite3.connect(database) as conn:
        conn.execute("CREATE TABLE message (data TEXT)")
        for agent in ("orchestrator", "writer"):
            conn.execute(
                "INSERT INTO message VALUES (?)",
                (
                    json.dumps(
                        dict(
                            role="assistant",
                            agent=agent,
                            finish="stop",
                            providerID="deepseek",
                            modelID="deepseek-flash",
                            tokens={"input": 1000, "output": 100, "reasoning": 20},
                        )
                    ),
                ),
            )
    assert regression_cost(database) == pytest.approx(0.000888)
    with sqlite3.connect(database) as conn:
        conn.execute(
            "INSERT INTO message VALUES (?)",
            (json.dumps(dict(role="assistant", finish="stop", providerID="unknown", modelID="unknown")),),
        )
    assert regression_cost(database) is None


def test_failed_candidate_evaluation_does_not_mutate_live_tree(planned, monkeypatch, tmp_path):
    from harness import improve
    from test_opencode_runner import make_opencode

    oc = make_opencode(planned.settings.root)
    before = (oc / "harness/systemprompt.md").read_text()
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "systemprompt.md").write_text("bad")
    monkeypatch.setattr(improve, "regression_pages", lambda *args: ["a", "b"])

    def score(ws, pages, label, **kwargs):
        assert (oc / "harness/systemprompt.md").read_text() == before
        if label == "candidate":
            raise RuntimeError("candidate failed")
        return Score(2, 0, 2, {"a": "PASS", "b": "PASS"}, 0.1)

    monkeypatch.setattr(improve, "score_harness", score)
    with pytest.raises(RuntimeError, match="candidate failed"):
        improve.promote(planned, "component", str(candidate))
    assert (oc / "harness/systemprompt.md").read_text() == before


@pytest.mark.parametrize("error", ['{"type":"error","error":"provider failed"}', "BUDGET_EXHAUSTED"])
def test_session_failure_cannot_publish_passing_draft(planned, no_mdx, monkeypatch, error):
    from harness import session
    from harness.jobqueue import Job
    from harness.runner import RunOptions, run_job
    from test_pages_checks import fill

    page = fill(planned)
    log = planned.report_path("session-error.jsonl")
    log.write_text(error)
    monkeypatch.setattr(session, "run_agent", lambda *args: session.SessionResult(0, False, log))
    status, _ = run_job(
        planned,
        Job(id="failure", kind="generate", page_id=page.id),
        RunOptions("759671", publish=True, reflect=False),
    )
    assert status in ("ERROR", "BUDGET_EXHAUSTED")
    assert not (planned.settings.docs_dir / page.path).exists()


def test_install_failure_restores_live_tree(planned, tmp_path, monkeypatch):
    from harness import opencode_sync
    from test_opencode_runner import make_opencode

    oc = make_opencode(planned.settings.root)
    original = (oc / "harness/systemprompt.md").read_text()
    candidate = tmp_path / "candidate"
    candidate.mkdir()
    (candidate / "systemprompt.md").write_text("new")
    materialise = opencode_sync.materialise
    calls = []

    def fail_once(path):
        calls.append(path)
        if len(calls) == 1:
            raise RuntimeError("installation failed")
        return materialise(path)

    monkeypatch.setattr(opencode_sync, "materialise", fail_once)
    with pytest.raises(RuntimeError, match="installation failed"):
        opencode_sync.replace_tree(oc, candidate)
    assert (oc / "harness/systemprompt.md").read_text() == original



def test_unguarded_deferred_transform_error_contract():
    from harness.checks import _deferred_transform_issue

    source = """function Saved:Apply(angle)
    self.inst:DoTaskInTime(0, function(inst)
        inst.Transform:SetRotation(angle)
    end)
end"""
    assert _deferred_transform_issue(source, "* **Error states:** None -- merely forwards angle.")
    assert not _deferred_transform_issue(source, "* **Error states:** Missing Transform raises in callback.")
    guarded = source.replace("inst.Transform:SetRotation(angle)",
                             "if inst.Transform then inst.Transform:SetRotation(angle) end")
    assert not _deferred_transform_issue(guarded, "* **Error states:** None")


def test_example_coordinates_require_setup_or_documented_precondition():
    from harness.checks import _example_coordinate_issues

    example = "## Usage example\n\n```lua\ninst.Transform:SetPosition(x, y, z)\n```\n"
    assert _example_coordinate_issues(example)[0].code == "EXAMPLE_PRECONDITION"
    declared = example.replace("inst.Transform", "local x, y, z = 1, 0, 2\ninst.Transform")
    assert not _example_coordinate_issues(declared)
    assert not _example_coordinate_issues(example.replace("```lua", "Given coordinates x, y, z.\n```lua"))
    assert not _example_coordinate_issues(example.replace("(x, y, z)", "(0, 0, 0)"))



def test_pinned_repair_item_and_caller_cases():
    from harness.semantic_cases import PINNED_SHA, audit_cases

    wrong = "---\ndescription: A material repairable with wood.\n---\n# Boards"
    assert audit_cases(PINNED_SHA, {"prefabs/boards.lua"}, wrong)[0][0] == "REPAIR_ROLE"
    assert not audit_cases("other-revision", {"prefabs/boards.lua"}, wrong)
    assert not audit_cases(PINNED_SHA, {"prefabs/other.lua"}, wrong)
    repaired = wrong.replace("repairable with wood", "used for wood repair")
    assert not audit_cases(PINNED_SHA, {"prefabs/boards.lua"}, repaired)
    caller = "### `LoadPostPass(newents, data)`\n* **Error states:** nil data errors (arrowsign guards it)."
    assert audit_cases(PINNED_SHA, {"components/savedrotation.lua"}, caller)[0][0] == "CALLER_CONTRACT"
    corrected = caller.replace(
        "arrowsign guards it", "arrowsign guards data for ApplyPostPassRotation instead"
    )
    assert not audit_cases(PINNED_SHA, {"components/savedrotation.lua"}, corrected)
