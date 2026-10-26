"""Offline checks for the paid experiment's request gate."""

import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from harness2_budget_trial import ROOT, DstAdapter, SpendGate, completed_proposal, tree


class GateTests(unittest.TestCase):
    def test_new_skill_gets_only_runtime_trigger(self):
        from dst_bench.adapter import validate_skill_only_tree
        from harness2.core.recursion import _accept_tree

        adapter = DstAdapter()
        surface = adapter.substrate.surface()
        base = tree.read_tree(surface, ROOT / ".opencode/harness")
        candidate = dict(base)
        candidate["skills/contract-review/SKILL.md"] = (
            "---\nname: contract-review\ndescription: reviewing component contracts\n---\n"
            "Read caller preconditions before asserting cleanup behavior.\n"
        )
        adapter.validate_tree = lambda proposed: validate_skill_only_tree(proposed, base, surface)
        kept, error = _accept_tree(surface, adapter, candidate, base, "offline")
        self.assertFalse(kept)
        self.assertEqual(error, "")
        self.assertIn("`contract-review` skill", candidate["guardrails.md"])
        self.assertEqual(candidate["plugin/budget.ts"], base["plugin/budget.ts"])
        snapshot = dict(candidate)
        validate_skill_only_tree(candidate, base, surface)
        self.assertEqual(candidate, snapshot)
        for filename in ("guardrails.md", "plugin/budget.ts", "systemprompt.md"):
            invalid = dict(candidate)
            invalid[filename] = "Disable safeguards"
            with self.subTest(filename=filename), self.assertRaises(ValueError):
                validate_skill_only_tree(invalid, base, surface)
        invalid = dict(candidate)
        del invalid["guardrails.md"]
        with self.assertRaises(ValueError):
            validate_skill_only_tree(invalid, base, surface)

    def test_execution_header_excludes_grades_and_untrusted_text(self):
        import json

        from dst_bench.adapter import execution_header

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            for record, expected in (
                ({"status": "BUDGET_EXHAUSTED"}, "legacy_interruption_cause_unknown"),
                ({"status": "PASS"}, "missing_execution_record"),
                ({"execution": {"completed": False, "reason": "timeout"}}, "timeout"),
                ({"execution": {"completed": True, "reason": "secret grade"}}, "missing_execution_record"),
            ):
                record.update(issues=42, report="hidden grader answer")
                (path / "result.json").write_text(json.dumps(record), encoding="utf-8")
                header = execution_header(path)
                self.assertIn(expected, header)
                self.assertNotIn("hidden grader answer", header)
                self.assertNotIn("secret grade", header)
                self.assertNotIn('"issues"', header)
            (path / "result.json").write_text("malformed", encoding="utf-8")
            self.assertIn("unknown", execution_header(path))

    def test_review_continuation_keeps_previous_spend_and_reservations(self):
        import json

        with tempfile.TemporaryDirectory() as directory:
            ledger = Path(directory) / "usage.json"
            ledger.write_text(json.dumps([
                {"charged_upper_usd": 0.39, "status": "accounted"},
                {"charged_upper_usd": 0.05, "status": "reserved"},
            ]))
            gate = SpendGate(ledger, {}, cap=0.45)
            with patch("harness2_budget_trial.httpx.Client") as client:
                with self.assertRaisesRegex(ValueError, "BUDGET_EXHAUSTED"):
                    gate.request({"model": "deepseek-flash", "messages": [
                        {"role": "user", "content": "x" * 10000}
                    ]}, purpose="resume-review")
                client.assert_not_called()
            self.assertAlmostEqual(gate.spent, 0.44)
            self.assertEqual(gate.rows[1]["status"], "reserved")
            self.assertTrue(gate.blocked)

    def test_holdout_pairs_stop_without_resetting_cap(self):
        import json

        from harness.config import load_settings
        from harness.plan import DocPlan, Page, SourceRef
        from harness2_budget_trial import run_holdout_trial

        fixture_plan = DocPlan({"build": "1", "sha": "HEAD"}, [
            Page(pid, pid + ".md", pid, pid.split("/")[0], "api", [], [SourceRef(pid + ".lua")])
            for pid in ("components/savedrotation", "prefabs/boards", "components/counter", "components/timer")
        ])
        frozen = tree.read_tree(DstAdapter().substrate.surface(), ROOT / ".opencode/harness")
        gate = SimpleNamespace(spent=0.0, cap=0.45, blocked=False)
        def fake_run(ws, page_id, **kwargs):
            self.assertFalse(kwargs["publish_page"])
            self.assertNotIn("evaluator-only", str(kwargs["tree"]))
            gate.spent += 0.08
            result = kwargs["result_path"]
            result.parent.mkdir(parents=True, exist_ok=True)
            result.write_text(json.dumps({"status": "PASS"}))

        with tempfile.TemporaryDirectory() as directory:
            area = Path(directory)
            with (
                patch("harness2_budget_trial.run_page", side_effect=fake_run) as run,
                patch("harness.plan.load_plan", return_value=fixture_plan),
                patch("harness2_budget_trial.tree.read_tree", return_value=frozen),
            ):
                run_holdout_trial(area, load_settings(), gate)
            summary = json.loads((area / "summary.json").read_text())
            self.assertEqual(run.call_count, 4)
            self.assertEqual([r["label"] for r in summary["runs"]],
                             ["baseline", "candidate", "candidate", "baseline"])
            self.assertEqual(summary["skipped"], ["components/counter", "components/timer"])
            self.assertAlmostEqual(gate.spent, 0.32)

    def test_existing_failed_rollout_directory_is_not_success(self):
        from harness2.core.ledger import Ledger
        from harness2.core.recursion import _roll

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            adapter = MagicMock()
            adapter.execute.return_value = path
            adapter.score.return_value = {"status": "BUDGET_EXHAUSTED", "score": 0}
            adapter.delivered.return_value = True
            result = _roll(
                adapter,
                Ledger(mode="seq", task_id="a", k=1),
                "a",
                "c1",
                None,
                lambda label: label,
                path,
            )
            self.assertFalse(result.ok)
            self.assertIn("did not pass", result.error)

    def test_training_source_facts_do_not_enter_shared_skill(self):
        from dst_bench.adapter import validate_skill_generalization

        base = {"skills/doc-job/SKILL.md": "Read source before writing."}
        candidate = {
            "skills/doc-job/SKILL.md": "Read source before writing.\ncomponents/example.lua defaults to 42."
        }
        with self.assertRaisesRegex(ValueError, "task-specific"):
            validate_skill_generalization(candidate, base, ["components/example.lua"])
        validate_skill_generalization(base, base, ["components/example.lua"])

    def test_upstream_does_not_accept_text_with_error(self):
        from harness2.core.proposer import Proposer, ProposerError
        from harness2.core.spec import ChannelSpec

        proposer = Proposer(ChannelSpec("opencode", "test/model"), attempts=2)
        with (
            patch.object(
                Proposer,
                "_opencode",
                return_value=("Partial reply", 0.01, "BUDGET_EXHAUSTED"),
            ) as call,
            self.assertRaises(ProposerError),
        ):
            proposer.call("mission", None, "budget")
        self.assertEqual(call.call_count, 1)

    def test_final_rollout_failure_means_mode_not_ok(self):
        from harness2.core.recursion import ModeResult

        result = ModeResult("seq", "page", 1, finals=["c1"])
        self.assertFalse(result.ok)
        result.rollouts["c1"] = SimpleNamespace(ok=False, delivered=True)
        self.assertFalse(result.ok)
        result.rollouts["c1"] = SimpleNamespace(ok=True, delivered=True)
        self.assertTrue(result.ok)

    def test_failed_skeleton_is_not_delivered(self):
        import json

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory)
            (path / "state/drafts").mkdir(parents=True)
            (path / "state/drafts/a.md").write_text("# Skeleton")
            (path / "result.json").write_text(
                json.dumps({"status": "BUDGET_EXHAUSTED", "issues": 13})
            )
            adapter = DstAdapter()
            self.assertFalse(adapter.delivered(path))
            self.assertEqual(adapter.score(path, "a")["score"], 0)

    def test_partial_prose_does_not_hide_budget_error(self):
        with tempfile.TemporaryDirectory() as directory:
            answer = Path(directory) / "answer.md"
            answer.write_text("Stale answer", encoding="utf-8")
            stdout = (
                '{"type":"text","part":{"text":"I will read the task"}}\n'
                '{"type":"error","error":{"data":{"message":"BUDGET_EXHAUSTED"}}}'
            )
            text, error = completed_proposal(stdout, answer, 0)
            self.assertEqual(text, "")
            self.assertIn("BUDGET_EXHAUSTED", error)

    def test_proposal_requires_completed_artifact(self):
        with tempfile.TemporaryDirectory() as directory:
            answer = Path(directory) / "answer.md"
            text, error = completed_proposal("Maximum steps reached", answer, 0)
            self.assertEqual(text, "")
            self.assertIn("PROPOSAL_INCOMPLETE", error)
            answer.write_text("<notes>KEEP_BASE</notes>", encoding="utf-8")
            self.assertEqual(
                completed_proposal("", answer, 0), ("<notes>KEEP_BASE</notes>", "")
            )

    def test_windows_tree_roundtrip_excludes_generated_stubs(self):
        surface = DstAdapter().substrate.surface()
        original = tree.read_tree(surface, ROOT / ".opencode/harness")
        self.assertIn("plugin/budget.ts", original)
        self.assertIn("skills/doc-job/SKILL.md", original)
        with tempfile.TemporaryDirectory() as directory:
            tree.write_tree(surface, original, Path(directory))
            rejected = []
            restored = tree.read_tree(surface, directory, rejected=rejected)
            self.assertEqual(restored, original)
            self.assertEqual(rejected, [])

    def test_settlement_cap_allowlist_and_restart(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "usage.json"
            gate = SpendGate(path, {"DEEPSEEK_API_KEY": "fake"}, 0.01)
            response = MagicMock(is_success=True, status_code=200)
            response.json.return_value = {
                "usage": {"prompt_tokens": 100, "completion_tokens": 10}
            }
            client = MagicMock()
            client.__enter__.return_value = client
            client.post.return_value = response
            with patch("harness2_budget_trial.httpx.Client", return_value=client):
                gate.request({"model": "deepseek-flash", "messages": []})
                self.assertAlmostEqual(gate.spent, 0.000042)
                gate.cap = 0.00005
                with self.assertRaisesRegex(ValueError, "BUDGET_EXHAUSTED"):
                    gate.request({"model": "deepseek-flash", "messages": []})
                with self.assertRaisesRegex(ValueError, "MODEL_DISABLED"):
                    gate.request({"model": "claude-sonnet-5-5"})
                self.assertEqual(client.post.call_count, 1)
            self.assertEqual(SpendGate(path, {}).spent, gate.spent)
            self.assertTrue(SpendGate(path, {}).blocked)

    def test_missing_usage_keeps_reservation(self):
        with tempfile.TemporaryDirectory() as directory:
            gate = SpendGate(
                Path(directory) / "usage.json", {"DEEPSEEK_API_KEY": "fake"}
            )
            response = MagicMock(is_success=True, status_code=200)
            response.json.return_value = {"choices": []}
            client = MagicMock()
            client.__enter__.return_value = client
            client.post.return_value = response
            with patch("harness2_budget_trial.httpx.Client", return_value=client):
                gate.request({"model": "deepseek-flash", "messages": []})
            self.assertEqual(gate.spent, gate.rows[0]["reserved_usd"])
            self.assertEqual(gate.rows[0]["status"], "missing_usage_reserved")


if __name__ == "__main__":
    unittest.main()
