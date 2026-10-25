"""Shared fixtures: a throw-away dst-scripts git repo and a workspace bound to it."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from harness.config import Settings, load_settings
from harness.tools import api
from harness.workspace import Workspace, make_workspace
from helpers import BASE_FILES, fixture_text, git, write_sources


@pytest.fixture()
def scripts_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "dst-scripts"
    repo.mkdir()
    git(repo, "init", "-q", "-b", "main")
    write_sources(repo, {rel: fixture_text(src) for rel, src in BASE_FILES.items()})
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "759671 - Cursed Confrontation\n\nPatch notes line one.\nLine two.")
    return repo


@pytest.fixture()
def settings_obj(tmp_path: Path, scripts_repo: Path) -> Settings:
    root = tmp_path / "root"
    (root / "dst-api-webdocs" / "docs").mkdir(parents=True)
    base = load_settings(root)
    values = dict(
        base.values,
        scripts_dir=str(scripts_repo),
        baseline_sha=git(scripts_repo, "rev-parse", "HEAD"),
        source_branch="main",
        page_source_max=12000,
    )
    return Settings(root=root, values=values)


@pytest.fixture()
def ws(settings_obj: Settings) -> Iterator[Workspace]:
    workspace = make_workspace(settings_obj, "HEAD")
    api.use_workspace(workspace)
    yield workspace
    api.use_workspace(None)


@pytest.fixture()
def planned(ws: Workspace) -> Workspace:
    from harness.autoplan import auto_plan
    from harness.codeindex import index_codebase
    from harness.plan import save_plan

    plan = auto_plan(index_codebase(ws), {"build": "759671", "sha": "x"}, 12000)
    save_plan(plan, ws.plan_path)
    return ws


@pytest.fixture()
def no_mdx(monkeypatch: pytest.MonkeyPatch) -> None:
    from harness import mdx

    monkeypatch.setattr(mdx, "compile_errors", lambda path, timeout=30: [])
