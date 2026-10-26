from __future__ import annotations

import pytest

from harness import markdown as md
from harness import mdx, pages
from harness.checks import run_checks
from harness.codeindex import index_codebase
from harness.workspace import Workspace

HEALTH_ENTRIES = {
    "### `GetPercent()`": "* **Returns:** fraction.",
    "### `DoDelta(amount, overtime, cause)`": "Pushes `healthdelta`.",
    "### `Static(a, b)`": "Adds.",
}


def fill(ws: Workspace, page_id: str = "components/health") -> pages.Page:
    plan = pages.get_plan(ws)
    page = plan.page(page_id)
    for heading, body in HEALTH_ENTRIES.items():
        pages.write_section(ws, page, heading, body)
    for section in ("## Overview", "## Usage example", "## Dependencies & tags", "## Events & listeners"):
        pages.write_section(ws, page, section, f"Text for {section}.")
    pages.write_section(
        ws,
        page,
        "## Properties",
        "| Property | Type | Default Value | Description |\n| --- | --- | --- | --- |\n"
        "| `inst` | Entity | inst | Owner |\n| `maxhealth` | number | 100 | Maximum |\n"
        "| `currenthealth` | number | 100 | Current |",
    )
    import frontmatter

    post = frontmatter.loads(pages.ensure_draft(ws, page))
    post.metadata["description"] = "Health component."
    pages.write_draft(ws, page, frontmatter.dumps(post) + "\n")
    return page


def issue_codes(ws: Workspace, page: pages.Page) -> set[str]:
    plan = pages.get_plan(ws)
    return {i.code for i in run_checks(ws, plan, page, pages.ensure_draft(ws, page))}


def test_checklist_headings_and_sections(planned: Workspace) -> None:
    page = pages.get_plan(planned).page("components/health")
    items = pages.checklist(page, index_codebase(planned))
    assert {i.heading for i in items} == set(HEALTH_ENTRIES)
    assert pages.page_sections(page, items)[-2:] == ["## Main functions", "## Events & listeners"]


def test_skeleton_fails_then_filled_page_passes(planned: Workspace, no_mdx: None) -> None:
    page = pages.get_plan(planned).page("components/health")
    assert {"COVERAGE", "EMPTY_SECTION", "FM_SCHEMA"} <= issue_codes(planned, page)
    fill(planned)
    assert issue_codes(planned, page) == set()


def test_entries_land_under_their_parent_section(planned: Workspace, no_mdx: None) -> None:
    page = fill(planned)
    _, body = md.split_frontmatter(pages.ensure_draft(planned, page))
    main = md.section_text(body, "## Main functions") or ""
    assert "### `DoDelta(amount, overtime, cause)`" in main


def test_signature_phantom_link_placeholder(planned: Workspace, no_mdx: None) -> None:
    page = fill(planned)
    pages.write_section(planned, page, "### `GetPercent(extra)`", "wrong params")
    pages.write_section(planned, page, "## Overview", "Calls `Health:Explode()` see [x](../nope.md). TODO")
    found = issue_codes(planned, page)
    assert {"SIGNATURE", "PHANTOM", "LINKS", "PLACEHOLDER"} <= found


def test_mdx_errors_and_unavailable(planned: Workspace, monkeypatch: pytest.MonkeyPatch) -> None:
    page = fill(planned)
    monkeypatch.setattr(mdx, "compile_errors", lambda path, timeout=30: ["bad jsx"])
    assert "MDX_COMPILE" in issue_codes(planned, page)

    def unavailable(path: object, timeout: int = 30) -> list[str]:
        raise mdx.MdxUnavailableError("no node")

    monkeypatch.setattr(mdx, "compile_errors", unavailable)
    assert "MDX_UNAVAILABLE" in issue_codes(planned, page)


def test_bad_frontmatter(planned: Workspace, no_mdx: None) -> None:
    page = fill(planned)
    text = pages.ensure_draft(planned, page).replace("last_updated:", "last_updated: '25/10/2026'\nold:")
    pages.write_draft(planned, page, text)
    assert "FM_SCHEMA" in issue_codes(planned, page)
    pages.write_draft(planned, page, "---\n: [\n---\n# T\n")
    assert "FM_SCHEMA" in issue_codes(planned, page)


def test_draft_starts_from_published_page(planned: Workspace) -> None:
    page = pages.get_plan(planned).page("components/health")
    published = planned.settings.docs_dir / page.path
    published.parent.mkdir(parents=True, exist_ok=True)
    published.write_text("---\nid: health\n---\n# Old\n", encoding="utf-8")
    assert pages.ensure_draft(planned, page).startswith("---\nid: health")


def test_notes_roundtrip_and_missing_plan(ws: Workspace) -> None:
    pages.write_notes(ws, "a/b", "done: X")
    assert pages.read_notes(ws, "a/b") == "done: X"
    assert pages.read_notes(ws, "none") == ""
    with pytest.raises(pages.PlanMissingError):
        pages.get_plan(ws)


def test_model_style_section_arguments_preserve_entries(planned: Workspace, no_mdx: None) -> None:
    from harness.tools import api

    page = pages.get_plan(planned).page("components/health")
    for heading, content in HEALTH_ENTRIES.items():
        api.doc_write_section(page.id, heading, f"{heading}\n\n{content}", parent="Main functions")
    api.doc_write_section(page.id, "## Events & listeners", "## Events & listeners\n\nHealth events.")
    _, body = md.split_frontmatter(pages.ensure_draft(planned, page))
    main = md.section_text(body, "## Main functions") or ""
    for heading in HEALTH_ENTRIES:
        assert main.count(heading) == 1
    assert body.count("## Events & listeners") == 1
    assert "COVERAGE" not in issue_codes(planned, page)


@pytest.mark.parametrize("parent", ["Not a section", "## Events & listeners"])
def test_invalid_parent_does_not_mutate_draft(planned: Workspace, parent: str) -> None:
    page = fill(planned)
    before = pages.ensure_draft(planned, page)
    with pytest.raises(ValueError, match="parent"):
        pages.write_section(planned, page, "### `GetPercent()`", "replacement", parent)
    assert pages.read_draft(planned, page) == before


def test_duplicate_sections_fail_checks(planned: Workspace, no_mdx: None) -> None:
    page = fill(planned)
    text = pages.ensure_draft(planned, page) + "\n## Overview\n\nDuplicate.\n"
    pages.write_draft(planned, page, text)
    assert "DUPLICATE_HEADING" in issue_codes(planned, page)


def test_provenance_mismatch_is_rejected_and_metadata_tool_repairs(planned: Workspace, no_mdx: None) -> None:
    from harness.tools import api

    page = fill(planned)
    text = pages.read_draft(planned, page).replace("759671", "725977")
    pages.write_draft(planned, page, text)
    assert "PROVENANCE" in issue_codes(planned, page)
    api.doc_set_meta(page.id, "Health component", "health")
    assert "PROVENANCE" not in issue_codes(planned, page)


def test_missing_property_row_fails_even_when_functions_are_complete(
    planned: Workspace, no_mdx: None
) -> None:
    page = fill(planned)
    pages.write_section(planned, page, "## Properties", "No properties.")
    assert "PROPERTIES" in issue_codes(planned, page)
    assert "COVERAGE" not in issue_codes(planned, page)


def test_component_constructor_is_not_a_function_entry(planned: Workspace) -> None:
    page = pages.get_plan(planned).page("components/health")
    assert pages.property_names(planned, page) == {"inst", "maxhealth", "currenthealth"}
    assert not any(i.symbol.kind == "class" for i in pages.checklist(page, index_codebase(planned)))


def test_skeleton_build_comes_from_pinned_source(planned: Workspace) -> None:
    planned.settings.values["baseline_build"] = "000000"
    page = pages.get_plan(planned).page("components/health")
    assert "759671" in pages.ensure_draft(planned, page)
