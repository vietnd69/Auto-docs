from __future__ import annotations

from pathlib import Path

import pytest

from harness.builds import BuildNotFoundError, list_builds, parse_build_number, resolve_build
from harness.gitsource import GitError, GitSource
from helpers import git, write_sources


@pytest.mark.parametrize(
    ("subject", "number"),
    [
        ("759671 - Don't Starve Together: From Beyond", "759671"),
        ("725977: Add new WX-78 behaviors", "725977"),
        ("Hotfix 714014: Enhance action functions", "714014"),
        ("756039", "756039"),
        ("Bot: Update DST Scripts 759671 - Out Now!", "759671"),
        ("Merge branch 'main'", None),
        ("1234 too short", None),
    ],
)
def test_parse_build_number(subject: str, number: str | None) -> None:
    assert parse_build_number(subject) == number


def test_list_and_resolve_builds(scripts_repo: Path) -> None:
    base = git(scripts_repo, "rev-parse", "HEAD")
    (scripts_repo / "components" / "health.lua").write_text("return {}\n", encoding="utf-8")
    git(scripts_repo, "commit", "-qam", "Hotfix 760001: fix\n\nnotes")
    git(scripts_repo, "commit", "-q", "--allow-empty", "-m", "Merge branch 'x'")
    source = GitSource(scripts_repo)
    builds = list_builds(source, base, "HEAD")
    assert [b.number for b in builds] == ["759671", "760001"]
    assert builds[0].notes.startswith("Patch notes")
    assert builds[1].is_hotfix
    assert resolve_build(builds, "760001").sha == git(scripts_repo, "rev-parse", "HEAD~1")
    assert resolve_build(builds, base[:8]).number == "759671"
    with pytest.raises(BuildNotFoundError, match="latest builds"):
        resolve_build(builds, "999999")


def test_git_source_reads(scripts_repo: Path) -> None:
    source = GitSource(scripts_repo)
    files = source.ls_files("HEAD")
    assert "components/health.lua" in files
    many = source.show_many("HEAD", ["components/health.lua", "missing.lua"])
    assert "Health" in many["components/health.lua"] and "missing.lua" not in many
    assert source.exists("HEAD", "strings_small.lua") and not source.exists("HEAD", "nope.lua")
    assert any("DoDelta" in row for row in source.grep("HEAD", "DoDelta"))
    assert source.grep("HEAD", "no_such_symbol_xyz") == []
    with pytest.raises(GitError):
        source.show("HEAD", "nope.lua")
    with pytest.raises(GitError):
        source.rev_parse("not-a-rev")


def test_diff_name_status_with_rename(scripts_repo: Path) -> None:
    source = GitSource(scripts_repo)
    old = source.rev_parse("HEAD")
    git(scripts_repo, "mv", "strings_small.lua", "strings_renamed.lua")
    write_sources(scripts_repo, {"components/new.lua": "function New() end\n", "notes.txt": "x"})
    git(scripts_repo, "add", "-A")
    git(scripts_repo, "commit", "-qm", "760100")
    changes = {c.path: c for c in source.diff_name_status(old, "HEAD")}
    assert changes["strings_renamed.lua"].status == "R"
    assert changes["strings_renamed.lua"].old_path == "strings_small.lua"
    assert changes["components/new.lua"].status == "A"
    assert "notes.txt" not in changes
    assert source.is_ancestor(old, "HEAD")
