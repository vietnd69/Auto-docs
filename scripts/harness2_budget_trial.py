"""Isolated, serial Harness2 smoke experiment with a shared prepaid request gate.

Run using .venv/Scripts/python.exe. No production skill promotion or publication.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [
    str(ROOT / p)
    for p in (
        "harness/src",
        "llm/src",
        "harness2-dst/src",
        "harness2-dst/vendor/harness2",
    )
]

import httpx
from dst_bench.adapter import (
    DstAdapter,
    validate_skill_generalization,
    validate_skill_only_tree,
)
from harness.config import Settings, load_settings
from harness.plan import DocPlan, Page, SourceRef, save_plan
from harness.role_config import credentials, runtime_config
from harness.runner import run_page
from harness.workspace import make_workspace
from harness2.core import tree
from harness2.core.ledger import Ledger
from harness2.core.proposer import Proposer, _opencode_stdout
from harness2.core.recursion import _roll, run_sequential
from harness2.core.spec import ChannelSpec

from harness import checkpoint, session


class SpendGate:
    """Reserve before network IO; unknown usage retains the entire reservation."""

    def __init__(self, path, secret, cap=0.45):
        self.path, self.secret, self.cap = path, secret, cap
        self.lock = threading.Lock()
        self.rows = json.loads(path.read_text()) if path.exists() else []
        self.blocked = any(row.get("status") == "budget_rejected" for row in self.rows)

    @property
    def spent(self):
        return sum(r["charged_upper_usd"] for r in self.rows)

    def save(self):
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.rows, indent=2), encoding="utf-8")
        temp.replace(self.path)

    def request(self, body, purpose="unspecified"):
        with self.lock:
            alias = body.get("model")
            models = {
                "deepseek-flash": "deepseek-flash",
                "reviewer": "gpt-oss:120b",
                "planner": "gpt-oss:120b",
                "reflector": "gemma4:31b",
            }
            if alias not in models:
                raise ValueError("MODEL_DISABLED_IN_BUDGET_TRIAL")
            body = dict(body, model=models[alias], stream=False, max_tokens=4096)
            body.pop("stream_options", None)
            body.pop("max_completion_tokens", None)
            if purpose == "proposer":
                body["thinking"] = {"type": "disabled"}
            # UTF-8 bytes overbound ordinary tokenizer input; include template overhead.
            reserve = (
                (len(json.dumps(body, ensure_ascii=False).encode()) + 16384) * 0.30
                + 4096 * 1.20
            ) / 1e6
            if self.blocked or self.spent + reserve > self.cap:
                self.blocked = True
                self.rows.append(
                    {
                        "role_model": alias,
                        "model": body["model"],
                        "purpose": purpose,
                        "charged_upper_usd": 0,
                        "status": "budget_rejected",
                    }
                )
                self.save()
                raise ValueError("BUDGET_EXHAUSTED: shared USD cap; request not sent")
            row = {
                "role_model": alias,
                "purpose": purpose,
                "model": body["model"],
                "reserved_usd": reserve,
                "charged_upper_usd": reserve,
                "status": "reserved",
            }
            self.rows.append(row)
            self.save()
            ds = body["model"] == "deepseek-flash"
            if ds:
                url, key = "https://api.deepseek.com", self.secret["DEEPSEEK_API_KEY"]
            else:
                url = "https://ollama.com/v1"
                key = self.secret.get("OLLAMA_API_KEY") or self.secret.get(
                    "ACCOUNT_1", ""
                )
            with httpx.Client(timeout=150) as client:
                response = client.post(
                    url + "/chat/completions",
                    json=body,
                    headers={"Authorization": "Bearer " + key},
                )
                if not ds and response.status_code in (402, 403, 429):
                    row["quota_fallback"] = response.status_code
                    body.update(model="deepseek-flash", thinking={"type": "disabled"})
                    row["model"] = body["model"]
                    ds = True
                    response = client.post(
                        "https://api.deepseek.com/chat/completions",
                        json=body,
                        headers={
                            "Authorization": "Bearer " + self.secret["DEEPSEEK_API_KEY"]
                        },
                    )
            row["http_status"] = response.status_code
            if not response.is_success:
                row["status"] = "upstream_error_reserved"
                self.save()
                raise ValueError("UPSTREAM_ERROR_" + str(response.status_code))
            data = response.json()
            usage = data.get("usage", {})
            if "prompt_tokens" in usage and "completion_tokens" in usage:
                inp, out = usage["prompt_tokens"], usage["completion_tokens"]
                cached = usage.get(
                    "prompt_cache_hit_tokens",
                    usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
                )
                rates = (
                    (0.30, 0.006, 1.20)
                    if ds
                    else (
                        (0.15, 0.014, 0.60)
                        if "gpt-oss" in body["model"]
                        else (0.14, 0.05, 0.40)
                    )
                )
                cost = (
                    (inp - cached) * rates[0] + cached * rates[1] + out * rates[2]
                ) / 1e6
                row.update(usage=usage, charged_upper_usd=cost, status="accounted")
                if cost > reserve:
                    row["reservation_violation"] = True
                    self.cap = 0  # fail closed for all further calls
            else:
                row["status"] = "missing_usage_reserved"
            self.save()
            return data


def completed_proposal(stdout: str, answer: Path, returncode: int) -> tuple[str, str]:
    """Introductory prose is not a successful proposal after an error/step limit."""
    _, error = _opencode_stdout(stdout)
    if error or returncode != 0:
        return "", error or f"proposer exited with {returncode}"
    if not answer.is_file() or not answer.read_text(encoding="utf-8").strip():
        return "", "PROPOSAL_INCOMPLETE: required output/answer.md is missing or empty"
    return answer.read_text(encoding="utf-8"), ""


def prepare_review_continuation(area, cfg, run_id="c1"):
    """Copy a timed-out rollout; preserve original artifacts and the shared ledger."""
    if not re.fullmatch(r"[A-Za-z0-9_-]+", run_id):
        raise ValueError("Invalid rollout ID")
    original = area / "rollouts" / run_id
    result = json.loads((original / "result.json").read_text(encoding="utf-8"))
    if not result.get("page_id") or result.get("status") == "PASS":
        raise ValueError("Review continuation requires an unfinished page")
    if result.get("execution", {}).get("reason") != "timeout":
        raise ValueError("Only a time-limited final rollout can continue review")
    candidate = area / "experiment/harnesses/c1"
    if run_id != "c1":
        summary = json.loads((area / "summary.json").read_text(encoding="utf-8"))
        record = next((r for r in summary.get("runs", []) if r.get("run_id") == run_id), None)
        if not record or record.get("label") not in ("baseline", "candidate"):
            raise ValueError("Rollout is not in the paired trial manifest")
        if record.get("page_id") != result["page_id"]:
            raise ValueError("Rollout page does not match the manifest")
        candidate = area / "harnesses" / record["label"]
    target = make_workspace(
        Settings(ROOT, dict(cfg.values, state_dir=str(original / "state"))),
        "b729a8f68d4b635c21279e71723b9627f24c5c38",
    )
    # Legacy trial migration: verify original pinned identity before making a copy.
    import frontmatter
    from harness.plan import load_plan

    plan = load_plan(target.plan_path)
    page = plan.page(result["page_id"])
    post = frontmatter.loads(target.draft_path(page.path).read_text(encoding="utf-8"))
    if post.get("source_sha") != target.rev or plan.baseline.get("sha") != target.rev:
        raise ValueError("Trial source identity mismatch")
    installed = original / "state/oc-project/.opencode/harness"
    surface = DstAdapter().substrate.surface()
    if tree.read_tree(surface, installed) != tree.read_tree(surface, candidate):
        raise ValueError("Candidate differs from the interrupted rollout harness")
    stored_checkpoint = checkpoint.checkpoint_path(target, page.id)
    if stored_checkpoint.exists():
        checkpoint.validate_resume(target, page.id, candidate)
    destination = area / ("review-" + run_id + "-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
    destination.mkdir()
    values = dict(cfg.values, state_dir=str(destination / "state"), trial_role="resume-review:" + run_id)
    ws = make_workspace(Settings(ROOT, values), target.rev)
    for name in ("drafts", "ledger", "notes"):
        source = original / "state" / name
        if source.exists():
            shutil.copytree(source, ws.settings.state_dir / name)
    shutil.copyfile(target.plan_path, ws.plan_path)
    checkpoint.save_checkpoint(ws, page.id, candidate, "imported-interrupted-" + run_id)
    return ws, page.id, candidate, destination


def run_holdout_trial(area, cfg, gate):
    """Paired, frozen baseline/candidate rollouts; no skill tuning on held-out answers."""
    from harness.plan import load_plan

    bundle = ROOT / "outputs/harness2-trial-20261027-reviewed-candidate"
    holdout = load_plan(bundle / "holdout/doc-plan.json")
    surface = DstAdapter().substrate.surface()
    baseline = ROOT / "outputs/harness2-trial-20261026-232322/experiment/harnesses/base"
    paths = {"baseline": baseline, "candidate": bundle / "harness"}
    for label, path in paths.items():
        frozen = tree.read_tree(surface, path)
        tree.validate(surface, frozen)
        tree.write_tree(surface, frozen, area / "harnesses" / label)
    save_plan(holdout, area / "doc-plan.json")
    # Small lifecycle component and prefab first, then more expensive APIs if budget permits.
    order = ["components/savedrotation", "prefabs/boards", "components/counter", "components/timer"]
    summary = {"kind": "frozen paired holdout", "cap_usd": gate.cap, "user_budget_usd": 0.50,
               "source_sha": holdout.baseline["sha"], "runs": [], "skipped": [],
               "promoted": False, "published": False}
    for index, page_id in enumerate(order):
        if gate.blocked or gate.cap - gate.spent < 0.14:
            summary["skipped"].extend(order[index:])
            break
        page = holdout.page(page_id)
        # Alternate order to reduce a systematic first-run/cache advantage.
        labels = ("baseline", "candidate") if index % 2 == 0 else ("candidate", "baseline")
        for label in labels:
            if gate.blocked:
                summary["runs"].append({"page_id": page_id, "label": label, "status": "NOT_RUN_BUDGET"})
                continue
            run_id = page_id.replace("/", "__") + "-" + label
            folder = area / "rollouts" / run_id
            values = dict(cfg.values, state_dir=str(folder / "state"), trial_role=run_id)
            ws = make_workspace(Settings(ROOT, values), holdout.baseline["sha"])
            save_plan(DocPlan(holdout.baseline, [page]), ws.plan_path)
            before = gate.spent
            print("HOLDOUT_START", run_id, "spent_upper", before, flush=True)
            try:
                run_page(ws, page_id, tree=area / "harnesses" / label,
                         result_path=folder / "result.json", events_path=folder / "events.jsonl",
                         publish_page=False)
                result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
            except Exception as exc:  # noqa: BLE001 - preserve partial trial results without provider secrets
                result = {"status": "ERROR", "exception_type": type(exc).__name__}
            result.update(page_id=page_id, label=label, run_id=run_id,
                          charged_upper_usd=gate.spent - before)
            summary["runs"].append(result)
            draft = ws.draft_path(page.path)
            if draft.exists():
                dest = area / "docs" / label / page.path
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(draft, dest)
            summary["charged_upper_usd"] = gate.spent
            (area / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
            print("HOLDOUT_END", run_id, result["status"], "spent_upper", gate.spent, flush=True)
    summary["charged_upper_usd"] = gate.spent
    (area / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("HOLDOUT_DONE", "spent_upper", gate.spent, "skipped", summary["skipped"], flush=True)


def run_review_evaluation(area, cfg, gate):
    """Exercise real bounded review on corrected docs, then one unseen generated page."""
    from harness.plan import load_plan

    bundle = ROOT / "outputs/harness2-trial-20261027-reviewed-candidate"
    corrected = ROOT / "outputs/harness2-trial-20261027-bounded-review/docs-reviewed/candidate"
    prior = ROOT / "outputs/harness2-trial-20261027-000934"
    surface = DstAdapter().substrate.surface()
    candidate = area / "harnesses/candidate"
    frozen = tree.read_tree(surface, bundle / "harness")
    # General protocol correction, frozen before evaluation; no page-specific answers.
    review_rules = (ROOT / "docs/review-protocol-rules.md").read_text(encoding="utf-8")
    frozen["skills/review-symbols/SKILL.md"] += "\n" + review_rules
    frozen["skills/function-format/SKILL.md"] += (
        "\nVerify every worked example by substituting actual defaults and branch conditions. "
        "Distinguish Lua table reads from writes, false/nil fallbacks, and runtime numeric coercion; "
        "do not claim all non-number values throw without tracing the actual expression.\n"
    )
    from dst_bench.adapter import (
        validate_skill_generalization,
        validate_skill_only_tree,
    )
    original = tree.read_tree(surface, bundle / "harness")
    validate_skill_only_tree(frozen, original, surface)
    validate_skill_generalization(frozen, original, ["components/counter.lua", "components/savedrotation.lua", "prefabs/boards.lua"])
    tree.write_tree(surface, frozen, candidate)
    sha = "b729a8f68d4b635c21279e71723b9627f24c5c38"
    summary = {"kind": "bounded final-review live evaluation", "cap_usd": gate.cap,
               "user_budget_usd": 0.5, "runs": [], "promoted": False, "published": False,
               "skill_provenance": "manual generic protocol correction frozen before evaluation; no autonomous tuning"}

    def execute(ws, page_id, label, resume, provenance):
        if gate.blocked:
            summary["runs"].append({"label": label, "status": "NOT_RUN_BUDGET"})
            return
        folder = area / "results" / label
        before = gate.spent
        print("REVIEW_EVAL_START", label, "spent_upper", before, flush=True)
        try:
            run_page(ws, page_id, tree=candidate, result_path=folder / "result.json",
                     events_path=folder / "events.jsonl", publish_page=False, resume_review=resume)
            result = json.loads((folder / "result.json").read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001 - no provider detail disclosure
            result = {"status": "ERROR", "exception_type": type(exc).__name__}
        result.update(label=label, input_provenance=provenance,
                      charged_upper_usd=gate.spent - before)
        summary["runs"].append(result)
        page = load_plan(ws.plan_path).page(page_id)
        draft = ws.draft_path(page.path)
        if draft.exists():
            dest = area / "docs" / label / page.path
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(draft, dest)
        summary["charged_upper_usd"] = gate.spent
        (area / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
        print("REVIEW_EVAL_END", label, result["status"], "spent_upper", gate.spent, flush=True)

    for page_id in ("components/savedrotation", "prefabs/boards"):
        if gate.blocked:
            break
        label = "review-" + page_id.replace("/", "__")
        ws = make_workspace(Settings(ROOT, dict(cfg.values, state_dir=str(area / "states" / label),
                            trial_role=label)), sha)
        plan = load_plan(prior / "rollouts" / (page_id.replace("/", "__") + "-candidate") / "state/doc-plan.json")
        save_plan(plan, ws.plan_path)
        page = plan.page(page_id)
        shutil.copyfile(corrected / page.path, ws.draft_path(page.path))
        checkpoint.save_checkpoint(ws, page_id, candidate, "manual-reviewed-input")
        execute(ws, page_id, label, True, "manually corrected prior draft; tests final review, not generation")

    if not gate.blocked and gate.cap - gate.spent >= 0.16:
        plan = load_plan(bundle / "holdout/doc-plan.json")
        page = plan.page("components/counter")
        label = "fresh-counter"
        ws = make_workspace(Settings(ROOT, dict(cfg.values, state_dir=str(area / "states" / label),
                            trial_role=label)), sha)
        save_plan(DocPlan(plan.baseline, [page]), ws.plan_path)
        execute(ws, page.id, label, False, "fresh model generation on a previously observed regression page; no draft imported")
        if not gate.blocked and ws.draft_path(page.path).exists():
            review_ws = make_workspace(Settings(ROOT, dict(ws.settings.values, trial_role="final-review-counter")), sha)
            execute(review_ws, page.id, "final-review-counter", True, "same freshly generated draft, no manual repairs")
    else:
        summary["skipped_fresh_counter"] = "insufficient shared headroom"
    summary["charged_upper_usd"] = gate.spent
    (area / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print("REVIEW_EVAL_DONE", gate.spent, flush=True)


def run_existing_review(area, cfg, gate, run_id, code_version):
    """Re-review a preserved regression draft with the same paid request ledger."""
    if not re.fullmatch(r"retry-[0-9]+", run_id):
        raise ValueError("Expected retry directory ID")
    original = area / run_id
    candidate = original / "harnesses/candidate"
    source = make_workspace(Settings(ROOT, dict(cfg.values,
                            state_dir=str(original / "states/fresh-counter"))),
                            "b729a8f68d4b635c21279e71723b9627f24c5c38")
    prior = checkpoint.validate_resume(source, "components/counter", candidate)
    destination = area / ("policy-review-" + datetime.now().strftime("%H%M%S"))
    destination.mkdir()
    ws = make_workspace(Settings(ROOT, dict(cfg.values, state_dir=str(destination / "state"),
                        trial_role="policy-review-counter")), source.rev)
    for name in ("drafts", "ledger", "notes"):
        folder = source.settings.state_dir / name
        if folder.exists():
            shutil.copytree(folder, ws.settings.state_dir / name)
    shutil.copyfile(source.plan_path, ws.plan_path)
    checkpoint.save_checkpoint(ws, "components/counter", candidate, "imported-" + prior["job_id"])
    (destination / "execution-version.json").write_text(json.dumps({
        "code_sha256": code_version, "shared_usage": str(area / "usage.json"),
        "source_attempt": str(original), "manual_doc_changes": False,
    }), encoding="utf-8")
    print("POLICY_REVIEW_DIR", destination, "SHARED_USD", gate.spent, flush=True)
    run_page(ws, "components/counter", tree=candidate, result_path=destination / "result.json",
             events_path=destination / "events.jsonl", publish_page=False, resume_review=True)
    shutil.copytree(ws.settings.state_dir / "drafts", destination / "docs")
    print("POLICY_REVIEW_DONE", gate.spent, flush=True)


def main():
    existing_review = len(sys.argv) == 4 and sys.argv[1] == "--review-existing"
    evaluation_mode = len(sys.argv) in (2, 3) and sys.argv[1] == "--review-eval"
    holdout_mode = sys.argv[1:] == ["--holdout"]
    review_only = len(sys.argv) in (3, 4) and sys.argv[1] == "--resume-review"
    if len(sys.argv) != 1 and not evaluation_mode and not holdout_mode and not review_only and not existing_review and not (
        len(sys.argv) == 3 and sys.argv[1] in ("--resume", "--resume-review")
    ):
        raise ValueError("Expected --holdout, --resume AREA, --resume-review AREA or no arguments; no calls sent")
    digest = hashlib.sha256(Path(__file__).read_bytes())
    for directory in (
        ROOT / "harness/src",
        ROOT / "harness2-dst/src",
        ROOT / "harness2-dst/vendor/harness2/harness2/core",
    ):
        for source in sorted(directory.rglob("*.py")):
            digest.update(source.relative_to(ROOT).as_posix().encode())
            digest.update(source.read_bytes())
    code_version = digest.hexdigest()
    if existing_review or review_only or (len(sys.argv) == 3 and sys.argv[1] in ("--resume", "--review-eval")):
        area = Path(sys.argv[2]).resolve()
        if (
            area.parent != (ROOT / "outputs").resolve()
            or not (area / "usage.json").exists()
        ):
            raise ValueError(
                "Resume must name an existing trial directory with a usage ledger"
            )
    else:
        area = (
            ROOT
            / "outputs"
            / ("harness2-trial-" + datetime.now().strftime("%Y%m%d-%H%M%S"))
        )
        area.mkdir(parents=True)
    manifest = area / "execution-version.json"
    if len(sys.argv) == 3 and sys.argv[1] == "--resume":
        if (
            not manifest.exists()
            or json.loads(manifest.read_text()).get("code_sha256") != code_version
        ):
            raise ValueError(
                "Cannot reuse results from a different runner/checker version; no model calls sent"
            )
    elif not existing_review and not review_only and not (evaluation_mode and len(sys.argv) == 3):
        manifest.write_text(json.dumps({"code_sha256": code_version}), encoding="utf-8")
    print("ARTIFACT_DIR", area, flush=True)
    base = load_settings()
    gate = SpendGate(area / "usage.json", credentials(base))

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            try:
                if not self.path.endswith("/chat/completions"):
                    raise ValueError("ENDPOINT_DISABLED")
                body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                data = gate.request(
                    body, self.headers.get("X-Trial-Role", "unspecified")
                )
                if body.get("stream"):
                    choice = data["choices"][0]
                    delta = choice["message"]
                    for i, tool in enumerate(delta.get("tool_calls", [])):
                        tool["index"] = i
                    common = {
                        k: data[k] for k in ("id", "created", "model") if k in data
                    }
                    chunk = dict(
                        common,
                        object="chat.completion.chunk",
                        choices=[{"index": 0, "delta": delta, "finish_reason": None}],
                    )
                    end = dict(
                        common,
                        object="chat.completion.chunk",
                        choices=[
                            {
                                "index": 0,
                                "delta": {},
                                "finish_reason": choice.get("finish_reason", "stop"),
                            }
                        ],
                        usage=data.get("usage", {}),
                    )
                    payload = (
                        "".join("data: " + json.dumps(c) + "\n\n" for c in (chunk, end))
                        + "data: [DONE]\n\n"
                    )
                    content_type = "text/event-stream"
                else:
                    payload, content_type = json.dumps(data), "application/json"
                self.send_response(200)
            except (ValueError, KeyError, TypeError, OSError, httpx.HTTPError) as exc:
                payload = json.dumps(
                    {"error": {"message": str(exc), "type": "budget_trial_error"}}
                )
                content_type = "application/json"
                self.send_response(400)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(payload.encode())))
            self.end_headers()
            try:
                self.wfile.write(payload.encode())
            except (BrokenPipeError, ConnectionResetError):
                pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    port = server.server_port
    sha = "b729a8f68d4b635c21279e71723b9627f24c5c38"
    cfg = Settings(
        ROOT,
        dict(
            base.values,
            baseline_sha=sha,
            baseline_build="759671",
            scripts_dir="D:/code/dst-scripts",
            docs_dir=str(area / "docs"),
            state_dir=str(area / "state"),
            deepseek_base_url=f"http://127.0.0.1:{port}/v1",
            proxy_port=port,
            final_review_backend="opencode",  # All paid trial calls must pass the shared USD gate.
            max_wall_minutes=6,
            max_steps=60,
            output_token_max=4096,
            reflect=0,
        ),
    )
    ws = make_workspace(cfg, sha)
    plan = DocPlan(
        {"build": "759671", "sha": sha},
        [
            Page(
                "components/boatdrag",
                "components/boatdrag.md",
                "BoatDrag",
                "components",
                "api",
                ["components"],
                [SourceRef("components/boatdrag.lua")],
            )
        ],
    )
    if not existing_review and not review_only and not holdout_mode and not evaluation_mode:
        save_plan(plan, ws.plan_path)
        save_plan(plan, area / "doc-plan.json")

    def local_config(settings):
        result = runtime_config(settings)
        result["provider"]["anthropic"]["options"] = {
            "baseURL": f"http://127.0.0.1:{port}/disabled",
            "apiKey": "trial",
        }
        result["enabled_providers"] = ["deepseek", "dst-proxy"]
        for provider in ("deepseek", "dst-proxy"):
            result["provider"][provider]["options"].setdefault("headers", {})[
                "X-Trial-Role"
            ] = settings.values.get("trial_role", "rollout")
        return result

    def local_env(settings):
        env = dict(os.environ)
        for key in list(env):
            if any(
                word in key.upper() for word in ("API_KEY", "AUTH_TOKEN")
            ) or key.startswith("ACCOUNT_"):
                del env[key]
        env.update(
            DEEPSEEK_API_KEY="trial",
            ANTHROPIC_API_KEY="disabled",
            CLAUDE_API_KEY="disabled",
        )
        for kind in ("DATA", "CONFIG", "CACHE", "STATE"):
            env[f"XDG_{kind}_HOME"] = str(area / "opencode" / kind.lower())
        return env

    session.runtime_config = local_config
    session.credentials = local_env
    if existing_review:
        try:
            run_existing_review(area, cfg, gate, sys.argv[3], code_version)
        finally:
            server.shutdown()
        return
    if evaluation_mode:
        try:
            evaluation_area = area
            if len(sys.argv) == 3:
                evaluation_area = area / ("retry-" + datetime.now().strftime("%H%M%S"))
                evaluation_area.mkdir()
                (evaluation_area / "execution-version.json").write_text(
                    json.dumps({"code_sha256": code_version, "shared_usage": str(area / "usage.json")}),
                    encoding="utf-8",
                )
                print("RETRY_DIR", evaluation_area, "SHARED_USD", gate.spent, flush=True)
            run_review_evaluation(evaluation_area, cfg, gate)
        finally:
            server.shutdown()
        return

    if holdout_mode:
        try:
            run_holdout_trial(area, cfg, gate)
        finally:
            server.shutdown()
        return

    if review_only:
        try:
            if gate.blocked:
                raise ValueError("Existing shared budget is exhausted; no new trial or cap reset")
            review_ws, page_id, candidate, destination = prepare_review_continuation(
                area, cfg, sys.argv[3] if len(sys.argv) == 4 else "c1"
            )
            (destination / "execution-version.json").write_text(
                json.dumps({"code_sha256": code_version}), encoding="utf-8"
            )
            print("REVIEW_DIR", destination, "spent_upper", gate.spent, flush=True)
            run_page(
                review_ws, page_id, tree=candidate, result_path=destination / "result.json",
                events_path=destination / "events.jsonl", publish_page=False, resume_review=True,
            )
            (destination / "usage-summary.json").write_text(
                json.dumps({"shared_ledger": str(area / "usage.json"),
                            "charged_upper_usd": gate.spent, "cap_usd": gate.cap}), encoding="utf-8"
            )
        finally:
            server.shutdown()
        return

    frozen = tree.read_tree(
        DstAdapter().substrate.surface(), ROOT / ".opencode/harness"
    )

    completed_trees = {}

    class Adapter(DstAdapter):
        def task_prompt(self, task_id):
            return "Document components/boatdrag.lua from DST build 759671 for mod developers."

        def domain_of(self, task_id):
            return "components"

        def execute(self, task_id, harness_dir, run_id, *, timeout=None):
            path = area / "rollouts" / run_id
            signature = json.dumps(
                tree.read_tree(self.substrate.surface(), harness_dir), sort_keys=True
            )
            if signature in completed_trees:
                previous = completed_trees[signature]
                print("IDENTICAL_TREE_REUSED", run_id, previous.name, flush=True)
                return previous
            if gate.blocked:
                path.mkdir(parents=True, exist_ok=True)
                (path / "result.json").write_text(
                    json.dumps(
                        {
                            "status": "BUDGET_EXHAUSTED",
                            "issues": 0,
                            "open_findings": 0,
                            "skipped": True,
                        }
                    ),
                    encoding="utf-8",
                )
                return path
            if (path / "result.json").exists():
                print("ROLLOUT_REUSED", run_id, flush=True)
                return path
            path.mkdir(parents=True, exist_ok=True)
            values = dict(cfg.values, state_dir=str(path / "state"), trial_role=run_id)
            target = make_workspace(Settings(ROOT, values), sha)
            save_plan(plan, target.plan_path)
            print("ROLLOUT_START", run_id, "spent_upper", gate.spent, flush=True)
            run_page(
                target,
                task_id,
                tree=harness_dir,
                result_path=path / "result.json",
                events_path=path / "events.jsonl",
                publish_page=False,
            )
            print("ROLLOUT_END", run_id, (path / "result.json").read_text(), flush=True)
            if json.loads((path / "result.json").read_text()).get("status") == "PASS":
                completed_trees[signature] = path
            for name, content in self.deliverable_files(path).items():
                dest = area / "docs" / run_id / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_text(content, encoding="utf-8")
            return path

        def validate_tree(self, candidate):
            super().validate_tree(candidate)
            validate_skill_generalization(
                candidate,
                frozen,
                [source.file for page in plan.pages for source in page.sources],
            )
            validate_skill_only_tree(candidate, frozen, self.substrate.surface())

    class NativeProposer(Proposer):
        def _opencode(self, cwd, mission, system, wall):
            if gate.blocked:
                return "", 0.0, "BUDGET_EXHAUSTED: no further proposer calls"
            (cwd / "MISSION.md").write_text(
                system
                + "\n\n"
                + mission
                + "\nOnly edit context/harness/skills/**/*.md. Preserve other files. Runtime generates new skill triggers. "
                "Keep task-specific source paths, defaults and finding IDs out of shared skills. "
                "Read only the relevant skills and evidence snippets; avoid reading the entire tree. "
                "Reserve steps to validate edits and write output/answer.md. If no change is justified, "
                "write KEEP_BASE with evidence to output/answer.md and finish.",
                encoding="utf-8",
            )
            (cwd / "output").mkdir(exist_ok=True)
            config = local_config(cfg)
            config["provider"]["deepseek"]["options"]["headers"]["X-Trial-Role"] = (
                "proposer"
            )
            config.update(
                agent={"build": {"steps": 24}},
                permission={
                    "bash": "deny",
                    "webfetch": "deny",
                    "task": "deny",
                    "external_directory": "deny",
                },
            )
            env = local_env(cfg)
            env.update(
                OPENCODE_CONFIG_CONTENT=json.dumps(config),
                OPENCODE_EXPERIMENTAL_OUTPUT_TOKEN_MAX="4096",
                OPENCODE_DISABLE_EXTERNAL_SKILLS="1",
                OPENCODE_DISABLE_CLAUDE_CODE_SKILLS="1",
            )
            before = gate.spent
            proc = subprocess.run(
                [
                    session.opencode_bin(ws),
                    "run",
                    "Read MISSION.md, carry out the edits, and save your final answer to output/answer.md.",
                    "--dir",
                    str(cwd),
                    "--model",
                    "deepseek/deepseek-flash",
                    "--format",
                    "json",
                ],
                cwd=cwd,
                env=env,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=300,
                check=False,
            )
            (area / "proposer-events").mkdir(exist_ok=True)
            (area / "proposer-events" / f"{len(gate.rows)}.jsonl").write_text(
                proc.stdout + "\n" + proc.stderr, encoding="utf-8"
            )
            answer = cwd / "output/answer.md"
            text, error = completed_proposal(proc.stdout, answer, proc.returncode)
            print("PROPOSAL_END", "spent_upper", gate.spent, "error", error, flush=True)
            return text, gate.spent - before, error

    adapter = Adapter()
    prop = NativeProposer(
        ChannelSpec("opencode", "deepseek/deepseek-flash", steps=24, timeout=300),
        audit_dir=area / "proposals-fixed",
        attempts=1,
    )
    work = area / "experiment"
    work.mkdir(exist_ok=True)
    try:
        base_run = _roll(
            adapter,
            Ledger(mode="seq", task_id="components/boatdrag", k=1),
            "components/boatdrag",
            "base",
            frozen,
            lambda label: label,
            work,
        )
        result = run_sequential(
            "components/boatdrag",
            1,
            [base_run],
            adapter=adapter,
            prop=prop,
            work_dir=work,
            run_id_of=lambda label: label,
            base_tree=frozen,
            propose_workers=1,
            rollout_workers=1,
        )
        (area / "experiment.json").write_text(
            json.dumps(result.to_dict(), indent=2, default=str), encoding="utf-8"
        )
        scores = {
            name: adapter.score(view.run_dir, "components/boatdrag")
            for name, view in result.rollouts.items()
        }
        (area / "summary.json").write_text(
            json.dumps(
                {
                    "scores": scores,
                    "rollout_sources": {
                        label: str(view.run_dir)
                        for label, view in result.rollouts.items()
                    },
                    "all_rollouts_passed": all(
                        score and score.get("status") == "PASS"
                        for score in scores.values()
                    ),
                    "charged_upper_usd": gate.spent,
                    "cap_usd": gate.cap,
                    "user_budget_usd": 0.50,
                    "promoted": False,
                    "published": False,
                    "scope": "One page, sequential k=1; skill-only candidates; no cross-page regression proof",
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        print("SUMMARY", json.dumps(scores), "USD_UPPER", gate.spent, flush=True)
    finally:
        server.shutdown()


if __name__ == "__main__":
    main()
