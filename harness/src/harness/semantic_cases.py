"""Source-pinned semantic regressions from seen evaluation pages.

These intentionally narrow cases are not a general natural-language verifier.
Keep page-specific facts here, outside reusable agent skills. Other revisions
require re-auditing the facts rather than silently carrying expectations forward.
"""

from __future__ import annotations

import re

import frontmatter

from harness import markdown as md
from harness.plan import Page
from harness.workspace import Workspace

PINNED_SHA = "b729a8f68d4b635c21279e71723b9627f24c5c38"


def audit_cases(source_sha: str, files: set[str], text: str) -> list[tuple[str, str]]:
    if source_sha != PINNED_SHA:
        return []
    issues = []
    post = frontmatter.loads(text)
    if "prefabs/boards.lua" in files:
        description = str(post.metadata.get("description", ""))
        if re.search(r"\brepairable\s+(?:with|using|by)\s+wood\b", description, re.IGNORECASE):
            issues.append((
                "REPAIR_ROLE", "boards.lua adds repairer (repair item), not repairable (target). "
                "Describe boards as a wood repair item; do not reverse the relationship."
            ))
    if "components/savedrotation.lua" in files:
        entry = md.section_text(post.content, "### `LoadPostPass(newents, data)`") or ""
        errors = re.search(r"\*\*Error states:\*\*(.*)", entry, re.DOTALL)
        if errors and "arrowsign" in errors[1] and "ApplyPostPassRotation" not in errors[1]:
            issues.append((
                "CALLER_CONTRACT", "arrowsign's postpass data guard feeds ApplyPostPassRotation. "
                "EntityScript:LoadPostPass dispatches the component LoadPostPass hook. "
                "Do not attribute one call path's guard to the other."
            ))
    return issues


def source_cases(ws: Workspace, page: Page, text: str) -> list[tuple[str, str]]:
    files = {source.file for source in page.sources}
    if not files.intersection({"prefabs/boards.lua", "components/savedrotation.lua"}):
        return []
    return audit_cases(ws.git.rev_parse(ws.rev), files, text)
