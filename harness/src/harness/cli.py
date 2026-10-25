"""``mod-harness`` command line: plan, generate, update, inspect, improve."""

from __future__ import annotations

import argparse
import sys
from collections import Counter

from harness import memory
from harness.autoplan import auto_plan
from harness.builds import list_builds, resolve_build
from harness.changelog import build_entry, prepend_entry
from harness.codeindex import index_codebase
from harness.diffing import diff_overview, impact_map, render_overview
from harness.domains import DOMAINS, update_domain
from harness.jobqueue import Job, JobQueue
from harness.pages import get_plan
from harness.plan import save_plan, validate_plan
from harness.planupdate import apply_impact
from harness.runner import RunOptions, run_queue
from harness.syncstate import SyncState
from harness.tools import api
from harness.verdict import remove_stale_pages, write_categories
from harness.workspace import Workspace, make_workspace


def _parallel(ws: Workspace, requested: int) -> int:
    if requested:
        return requested
    configured = ws.settings.get_int("parallel")
    if configured:
        return configured
    try:
        from llm.client import OLLAMA_API_KEYS
    except ImportError:
        return 1
    return max(1, len(OLLAMA_API_KEYS))


def cmd_index(ws: Workspace, args: argparse.Namespace) -> int:
    api.use_workspace(ws)
    print(api.index_summary())
    return 0


def cmd_plan(ws: Workspace, args: argparse.Namespace) -> int:
    if ws.plan_path.exists() and not args.force:
        print(f"{ws.plan_path} exists; use --force to regenerate (the planner agent refines it)")
        return 1
    index = index_codebase(ws)
    baseline = {"build": ws.settings.get_str("baseline_build"), "sha": ws.git.rev_parse(ws.rev)}
    plan = auto_plan(index, baseline, ws.settings.get_int("page_source_max"))
    save_plan(plan, ws.plan_path)
    issues = validate_plan(plan, index)
    print(f"{len(plan.pages)} pages {dict(Counter(p.kind for p in plan.pages))}; {len(issues)} issues")
    for issue in issues[:30]:
        print(f"  [{issue.code}] {issue.message}")
    return 0


def _queue_pages(ws: Workspace, name: str, page_ids: list[str], kind: str, old: str, new: str) -> JobQueue:
    queue = JobQueue(ws.queue_path(name))
    for page_id in page_ids:
        queue.add(
            Job(
                id=f"{kind}-{page_id}".replace("/", "__"),
                kind=kind,
                page_id=page_id,
                from_rev=old,
                to_rev=new,
            )
        )
    return queue


def cmd_generate(ws: Workspace, args: argparse.Namespace) -> int:
    plan = get_plan(ws)
    synced = SyncState(ws).pages
    ids = [p.id for p in plan.pages if p.id.startswith(args.prefix) and (args.force or p.id not in synced)]
    ids = ids[: args.limit] if args.limit else ids
    sha = ws.git.rev_parse(ws.rev)
    queue = _queue_pages(ws, f"generate-{sha[:10]}", ids, "generate", "", sha)
    opts = RunOptions(
        ws.settings.get_str("baseline_build"),
        not args.no_publish,
        bool(ws.settings.get_int("reflect")),
        args.escalate,
    )
    print(f"queued {len(ids)} pages")
    print(run_queue(ws, queue, opts, _parallel(ws, args.parallel)))
    write_categories(ws, plan)
    return 0


def cmd_update(ws: Workspace, args: argparse.Namespace) -> int:
    state = SyncState(ws)
    old = args.from_rev or state.head or ws.settings.get_str("baseline_sha")
    builds = list_builds(ws.git, ws.settings.get_str("baseline_sha"), ws.settings.get_str("source_branch"))
    target = resolve_build(builds, args.to) if args.to else builds[-1]
    new = target.sha
    if ws.git.rev_parse(old) == new:
        print(f"already at build {target.number}")
        return 0
    new_ws = make_workspace(ws.settings, new)
    diffs = diff_overview(new_ws, old, new)
    print(render_overview(diffs))
    if args.dry_run:
        return 0
    plan = get_plan(new_ws)
    index = index_codebase(new_ws, new)
    touched = apply_impact(
        plan, index, diffs, impact_map(plan, index, diffs), new_ws.settings.get_int("page_source_max")
    )
    save_plan(plan, new_ws.plan_path)
    removed = remove_stale_pages(new_ws, plan)
    queue = _queue_pages(new_ws, f"update-{old[:10]}-{new[:10]}", sorted(touched), "update", old, new)
    opts = RunOptions(target.number, True, bool(ws.settings.get_int("reflect")), args.escalate)
    print(f"{len(touched)} pages to update, {len(removed)} stale pages removed")
    counts = run_queue(new_ws, queue, opts, _parallel(ws, args.parallel))
    print(counts)
    write_categories(new_ws, plan)
    changelog = new_ws.settings.path("changelog_file")
    prepend_entry(changelog, build_entry(target, old, diffs))
    if not counts.get("pending"):
        state = SyncState(new_ws)
        state.head = new
        state.save()
    return 0 if set(counts) <= {"PASS"} else 2


def cmd_status(ws: Workspace, args: argparse.Namespace) -> int:
    state = SyncState(ws)
    print(f"source head synced: {state.head or '(baseline)'}; published pages: {len(state.pages)}")
    for path in sorted(ws.settings.state_dir.joinpath("queue").glob("*.jsonl")):
        print(f"  queue {path.stem}: {JobQueue(path).counts()}")
    return 0


def cmd_builds(ws: Workspace, args: argparse.Namespace) -> int:
    api.use_workspace(ws)
    print(api.build_list())
    return 0


def cmd_page(ws: Workspace, args: argparse.Namespace) -> int:
    api.use_workspace(ws)
    fn = {"checks": api.run_checks_tool, "verdict": api.verdict, "checklist": api.page_checklist}[args.what]
    print(fn(args.page_id))
    return 0


def cmd_memory(ws: Workspace, args: argparse.Namespace) -> int:
    domains = [*DOMAINS, *(update_domain(d) for d in DOMAINS)]
    text = memory.render_long_term(ws, domains, ws.settings.get_int("memory_top_n"))
    target = ws.settings.root / ".opencode" / "harness" / "LongTermMEMORY.md"
    target.write_text(text, encoding="utf-8")
    print(f"wrote {target}")
    return 0


def cmd_improve(ws: Workspace, args: argparse.Namespace) -> int:
    from harness import improve

    if args.promote:
        return improve.promote(ws, args.promote, args.candidate)
    plan = get_plan(ws)
    return 0 if improve.escalate(ws, plan.page(args.page_id)) else 1


def cmd_run_page(ws: Workspace, args: argparse.Namespace) -> int:
    from pathlib import Path

    from harness.runner import isolated_workspace, run_page

    if args.state_dir:
        ws = isolated_workspace(ws, Path(args.state_dir))
    status, report = run_page(
        ws,
        args.page_id,
        tree=Path(args.harness_tree) if args.harness_tree else None,
        result_path=Path(args.result) if args.result else None,
        events_path=Path(args.events) if args.events else None,
        publish_page=args.publish,
    )
    print(report)
    return 0 if status == "PASS" else 2


def cmd_setup_harness2(ws: Workspace, args: argparse.Namespace) -> int:
    from harness.improve import setup_harness2

    return setup_harness2(ws)


def cmd_sync_opencode(ws: Workspace, args: argparse.Namespace) -> int:
    from harness.opencode_sync import materialise

    written = materialise(ws.settings.root / ".opencode")
    print(f"materialised {len(written)} OpenCode files from .opencode/harness/")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="mod-harness", description=__doc__)
    parser.add_argument("--rev", default="", help="source revision (default HEAD of dst-scripts)")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("index", help="index the codebase and print statistics").set_defaults(fn=cmd_index)
    p = sub.add_parser("plan", help="create the default doc-plan.json")
    p.add_argument("--force", action="store_true")
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("generate", help="write/refresh pages through OpenCode")
    p.add_argument("--prefix", default="")
    p.add_argument("--limit", type=int, default=0)
    p.add_argument("--parallel", type=int, default=0)
    p.add_argument("--force", action="store_true", help="include pages already published")
    p.add_argument("--no-publish", action="store_true")
    p.add_argument("--escalate", action="store_true", help="run Harness² recursion on failing pages")
    p.set_defaults(fn=cmd_generate)
    p = sub.add_parser("update", help="update docs for new builds")
    p.add_argument("--to", default="", help="build number or SHA (default: latest)")
    p.add_argument("--from-rev", default="")
    p.add_argument("--parallel", type=int, default=0)
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--escalate", action="store_true")
    p.set_defaults(fn=cmd_update)
    p = sub.add_parser("run-page", help="run one page job (used by Harness² rollouts)")
    p.add_argument("page_id")
    p.add_argument("--state-dir", default="", help="isolated state directory")
    p.add_argument("--harness-tree", default="", help="candidate .opencode/harness tree")
    p.add_argument("--result", default="", help="write result JSON here")
    p.add_argument("--events", default="", help="copy the OpenCode event log here")
    p.add_argument("--publish", action="store_true", help="publish on PASS")
    p.set_defaults(fn=cmd_run_page)
    sub.add_parser("setup-harness2", help="clone pinned Harness² and apply the dst patch").set_defaults(
        fn=cmd_setup_harness2
    )
    sub.add_parser("status", help="sync state and queues").set_defaults(fn=cmd_status)
    sub.add_parser("builds", help="list builds since the baseline").set_defaults(fn=cmd_builds)
    p = sub.add_parser("page", help="inspect one page")
    p.add_argument("what", choices=["checks", "verdict", "checklist"])
    p.add_argument("page_id")
    p.set_defaults(fn=cmd_page)
    sub.add_parser("memory", help="render .opencode/harness/LongTermMEMORY.md").set_defaults(fn=cmd_memory)
    sub.add_parser("sync-opencode", help="materialise .opencode/harness into OpenCode layout").set_defaults(
        fn=cmd_sync_opencode
    )
    p = sub.add_parser("improve", help="Harness² escalation or skill promotion")
    p.add_argument("page_id", nargs="?", default="")
    p.add_argument("--promote", default="", help="domain whose candidate harness to promote")
    p.add_argument("--candidate", default="", help="candidate harness directory")
    p.set_defaults(fn=cmd_improve)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    ws = make_workspace(rev=args.rev or None)
    result: int = args.fn(ws, args)
    return result


if __name__ == "__main__":
    sys.exit(main())
