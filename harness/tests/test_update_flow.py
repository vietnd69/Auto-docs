"""Symbol diffs → impact → plan update → changelog (goal G5)."""

from __future__ import annotations

from harness.builds import Build
from harness.changelog import build_entry, prepend_entry
from harness.codeindex import build_file_index, index_codebase
from harness.diffing import compare_files, diff_overview, impact_map, render_overview, symbol_diff
from harness.pages import get_plan
from harness.planupdate import apply_impact
from harness.workspace import Workspace, make_workspace
from helpers import git, write_sources

NEW_HEALTH = """local Health = Class(function(self, inst)
    self.inst = inst
end)

function Health:GetPercent(precise)
    return 1
end

function Health:DoDelta(amount, overtime, cause)
    self.inst:PushEvent("healthdelta", {})
    return amount * 2
end

function Health:Kill()
end

function Health.Add(a, b)
    return a + b
end

return Health
"""


def make_update(ws: Workspace) -> tuple[str, str]:
    repo = ws.settings.scripts_dir
    old = git(repo, "rev-parse", "HEAD")
    write_sources(
        repo, {"components/health.lua": NEW_HEALTH, "components/shiny.lua": "function Shiny() end\n"}
    )
    git(repo, "rm", "-q", "strings_small.lua")
    git(repo, "add", "-A")
    git(repo, "commit", "-qm", "760500 - Big update\n\nNew stuff.")
    return old, git(repo, "rev-parse", "HEAD")


def test_compare_files_classifies_changes() -> None:
    old_src = "function A(x) return x end\nfunction B() return 1 end\nfunction C() return 9 end\n"
    new_src = (
        "function A(x, y) return x end\nfunction B() return 2 end\n"
        "function D() return 9 end\nfunction E() end\n"
    )
    changes = compare_files(
        build_file_index("f.lua", old_src), old_src, build_file_index("f.lua", new_src), new_src
    )
    assert changes == {
        "added": ["E"],
        "renamed": ["C -> D"],
        "signature_changed": ["A"],
        "body_changed": ["B"],
    }


def test_overview_impact_plan_update_changelog(planned: Workspace) -> None:
    old, new = make_update(planned)
    new_ws = make_workspace(planned.settings, new)
    diffs = diff_overview(new_ws, old, new)
    by_path = {d.path: d for d in diffs}
    assert by_path["components/shiny.lua"].status == "A"
    assert by_path["strings_small.lua"].status == "D"
    health = by_path["components/health.lua"].symbols
    assert "Health:Kill" in health["added"] and "Health:GetPercent" in health["signature_changed"]
    assert "Health.Static -> Health.Add" in health["renamed"]
    assert "files changed" in render_overview(diffs)
    assert "+    return amount * 2" in symbol_diff(
        new_ws, "components/health.lua", "Health:DoDelta", old, new
    )
    assert "no changes" in symbol_diff(new_ws, "components/ambient.lua", "Ambient:OnUpdate", old, new)

    plan = get_plan(new_ws)
    index = index_codebase(new_ws, new)
    impact = impact_map(plan, index, diffs)
    assert "components/health" in impact.pages and impact.removed_files == ["strings_small.lua"]
    touched = apply_impact(plan, index, diffs, impact, 12000)
    ids = {p.id for p in plan.pages}
    assert "strings_small" not in ids and "components/shiny" in ids
    assert {"components/health", "components/shiny"} <= touched

    build = Build("760500", new, "2026-10-23", "Big update", "Use {braces} <b>", False)
    entry = build_entry(build, old, diffs)
    assert "## Build 760500" in entry and "`Health:Kill`" in entry and "\\{braces\\}" in entry
    changelog = planned.settings.root / "change-log.md"
    changelog.write_text("---\ntitle: x\n---\n# Change log\n\n## Build 759671\n", encoding="utf-8")
    prepend_entry(changelog, entry)
    text = changelog.read_text(encoding="utf-8")
    assert text.index("## Build 760500") < text.index("## Build 759671")
