"""Explicit two-subscription final-review comparison on an unchanged counter draft."""
import argparse
import hashlib
import json
import shutil
from datetime import datetime
from pathlib import Path

from harness.config import Settings, load_settings
from harness.runner import run_page
from harness.subscription import auth_status
from harness.workspace import make_workspace

from harness import checkpoint

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "outputs/harness2-trial-20261027-011200"
SHA = "b729a8f68d4b635c21279e71723b9627f24c5c38"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--backend", choices=("codex", "claude-code"))
    parser.add_argument("--claude-model", default="claude-sonnet-5-5")
    args = parser.parse_args()
    cfg = load_settings(ROOT)
    original = make_workspace(Settings(ROOT, dict(cfg.values,
        state_dir=str(SOURCE / "policy-review-012727/state"), scripts_dir="D:/code/dst-scripts")), SHA)
    original_tree = SOURCE / "retry-011514/harnesses/candidate"
    checkpoint.validate_resume(original, "components/counter", original_tree)
    area = ROOT / "outputs" / ("harness2-trial-" + datetime.now().strftime("%Y%m%d-%H%M%S") + "-subscriptions")
    area.mkdir()
    frozen = area / "harness"
    shutil.copytree(original_tree, frozen)
    summary = {"source_attempt": str(SOURCE / "policy-review-012727"), "source_sha": SHA,
               "billing_mode": "subscription", "cost_usd": None,
               "notes_policy": "prior PASS notes omitted from both independent reviews",
               "promoted": False, "published": False, "runs": []}
    print("ARTIFACT_DIR", area, flush=True)
    for backend, model, effort in (("codex", "gpt-6.1-sol", "medium"), ("claude-code", args.claude_model, "high")):
        if args.backend and backend != args.backend:
            continue
        label = "sol-medium" if backend == "codex" else "sonnet-high"
        dest = area / label
        values = dict(cfg.values, state_dir=str(dest / "state"), docs_dir=str(dest / "docs"),
                      scripts_dir="D:/code/dst-scripts", final_review_backend=backend,
                      codex_subscription_model="gpt-6.1-sol", codex_subscription_effort="medium",
                      claude_subscription_model=args.claude_model, claude_subscription_effort="high",
                      final_review_seconds=240, max_wall_minutes=4, reflect=0)
        ws = make_workspace(Settings(ROOT, values), SHA)
        for name in ("drafts", "ledger"):
            shutil.copytree(original.settings.state_dir / name, ws.settings.state_dir / name)
        shutil.copyfile(original.plan_path, ws.plan_path)
        draft = ws.draft_path("components/counter.md")
        before = hashlib.sha256(draft.read_bytes()).hexdigest()
        checkpoint.save_checkpoint(ws, "components/counter", frozen, "identical-imported-counter")
        record = {"backend": backend, "model": model, "effort": effort, "draft_sha256": before}
        print("START", label, flush=True)
        try:
            record["auth"] = auth_status(ws.settings, backend)
            run_page(ws, "components/counter", tree=frozen, result_path=dest / "result.json",
                     events_path=dest / "events.jsonl", publish_page=False, resume_review=True)
            record.update(json.loads((dest / "result.json").read_text(encoding="utf-8")))
        except Exception as exc:  # noqa: BLE001 - no raw provider output or credentials printed.
            record.update(status="ERROR", error_type=type(exc).__name__)
        record["draft_unchanged"] = hashlib.sha256(draft.read_bytes()).hexdigest() == before
        shutil.copytree(ws.settings.state_dir / "drafts", dest / "docs")
        summary["runs"].append(record)
        (area / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("END", label, record["status"], "open_findings", record.get("open_findings"), flush=True)


if __name__ == "__main__":
    main()
