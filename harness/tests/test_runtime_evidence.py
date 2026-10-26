import json
import shutil
from types import SimpleNamespace

import pytest

from harness import runtime_evidence, session, subscription
from harness.jobqueue import Job


@pytest.mark.skipif(not shutil.which("luajit"), reason="LuaJIT unavailable")
def test_real_probe_and_controller_injection(planned, monkeypatch):
    monkeypatch.setenv("LUA_INIT", "error('untrusted ambient initialization must not run')")
    policy = planned.settings.root / ".opencode/harness/skills/review-symbols/SKILL.md"
    policy.parent.mkdir(parents=True)
    policy.write_text("Frozen review rules", encoding="utf-8")
    planned.settings.values.update(review_runtime_evidence=1, final_review_backend="codex")
    def dispatch(ws, job, prompt, log, env, backend):
        assert 'string.format("%g","5") gives "5"' in prompt
        assert "do not defer these tested cases" in prompt
        artifact = json.loads(ws.report_path(f"runtime-evidence/{job.id}.json").read_text())
        assert artifact["source_sha"] == ws.git.rev_parse(ws.rev)
        assert artifact["stdout"].endswith("PROBE_COMPLETE\n")
        assert artifact["executable_sha256"] and artifact["probe_sha256"]
        return session.SessionResult(0, False, log)
    monkeypatch.setattr(subscription, "run_review", dispatch)
    session.run_agent(planned, Job("runtime-test", "resume-review", "components/health"),
                      "reviewer", "Review", "runtime-test")


@pytest.mark.parametrize("stdout,code", [("PROBE_COMPLETE\n", 0), ("runtime=LuaJIT fake\n", 0), ("", 1)])
def test_bad_probe_never_becomes_evidence(ws, tmp_path, monkeypatch, stdout, code):
    binary = tmp_path / "fake.exe"
    binary.write_bytes(b"fake")
    ws.settings.values["runtime_lua_bin"] = str(binary)
    monkeypatch.setattr(runtime_evidence.subprocess, "run", lambda *a, **k:
                        SimpleNamespace(returncode=code, stdout=stdout, stderr="failure"))
    with pytest.raises(ValueError, match="failed or output incomplete"):
        runtime_evidence.collect(ws, Job("j", "resume-review", "components/health"))
    assert not ws.report_path("runtime-evidence/j.json").exists()


def test_failed_probe_stops_before_model(planned, monkeypatch):
    policy = planned.settings.root / ".opencode/harness/skills/review-symbols/SKILL.md"
    policy.parent.mkdir(parents=True)
    policy.write_text("Review policy", encoding="utf-8")
    planned.settings.values.update(review_runtime_evidence=1, final_review_backend="codex")
    def fail(*args):
        raise ValueError("probe failed")
    monkeypatch.setattr(runtime_evidence, "collect", fail)
    monkeypatch.setattr(subscription, "run_review", lambda *a: pytest.fail("Model must not run"))
    with pytest.raises(ValueError, match="probe failed"):
        session.run_agent(planned, Job("j", "resume-review", "components/health"), "reviewer", "Review", "j")
