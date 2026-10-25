from __future__ import annotations

from pathlib import Path

import pytest

from harness import markdown as md
from harness.safepath import PathOutsideRootError, confine, normalize_rel
from harness.textutil import estimate_tokens, short_hash, truncate
from harness.timeutil import now_iso, today_iso

DOC = (
    "---\nid: x\n---\n# T\n\n## A\n\ntext\n\n```lua\n## not a heading\n```\n\n"
    "### `f()`\n\nbody\n\n## B\n\nb\n"
)


def test_split_frontmatter_and_headings() -> None:
    front, body = md.split_frontmatter(DOC)
    assert front.startswith("---") and body.startswith("# T")
    assert [(h.level, h.text) for h in md.headings(body)] == [(1, "T"), (2, "A"), (3, "`f()`"), (2, "B")]
    assert md.split_frontmatter("# no front") == ("", "# no front")


def test_section_text_includes_subsections() -> None:
    _, body = md.split_frontmatter(DOC)
    text = md.section_text(body, "## A") or ""
    assert "### `f()`" in text and "## B" not in text
    assert md.section_text(body, "## Missing") is None


def test_upsert_replaces_inserts_under_parent_and_appends() -> None:
    _, body = md.split_frontmatter(DOC)
    replaced = md.upsert_section(body, "### `f()`", "new body")
    assert "new body" in replaced and "\nbody\n" not in replaced
    inserted = md.upsert_section(body, "### `g()`", "g body", parent="## A")
    assert inserted.index("### `g()`") < inserted.index("## B")
    appended = md.upsert_section(body, "## C", "c")
    assert appended.rstrip().endswith("c")


def test_safepath() -> None:
    assert normalize_rel("\\a\\b.lua") == "a/b.lua"
    for bad in ("../x", "a/../../x", ""):
        with pytest.raises(PathOutsideRootError):
            normalize_rel(bad)
    assert confine(Path("/tmp"), "a/b").name == "b"


def test_text_and_time_helpers() -> None:
    assert estimate_tokens("abcdefg") == 2
    assert truncate("abcdef", 3, "more").startswith("abc\n…[truncated 3 chars] more")
    assert truncate("ab", 3) == "ab"
    assert len(short_hash("x", 8)) == 8
    assert now_iso().endswith("Z") and len(today_iso()) == 10
