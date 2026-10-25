"""DST build ↔ commit mapping for the crawler-fed ``dst-scripts`` repository.

The crawler commits each Steam build as ``"<build> - <title>\\n\\n<patch notes>"`` (or just
``"<build>"`` when the RSS lookup failed). Only builds after the configured baseline count.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from harness.gitsource import Commit, GitSource

_BUILD_RE = re.compile(r"^(?:Bot:\s*Update DST Scripts\s+)?(?:Hotfix\s+)?(\d{5,7})\b", re.IGNORECASE)


class BuildNotFoundError(LookupError):
    """No commit matches the requested build."""


@dataclass(frozen=True)
class Build:
    number: str
    sha: str
    date: str
    title: str
    notes: str
    is_hotfix: bool


def parse_build_number(subject: str) -> str | None:
    """Extract the build number from a commit subject, or ``None``."""
    match = _BUILD_RE.match(subject.strip())
    return match.group(1) if match else None


def _to_build(commit: Commit) -> Build | None:
    number = parse_build_number(commit.subject)
    if number is None:
        return None
    title = re.sub(r"^\D*\d+\s*[-:]?\s*", "", commit.subject, count=1).strip()
    return Build(
        number=number,
        sha=commit.sha,
        date=commit.date,
        title=title,
        notes=commit.body.strip(),
        is_hotfix=commit.subject.lower().startswith("hotfix"),
    )


def list_builds(git: GitSource, baseline_sha: str, head: str) -> list[Build]:
    """Baseline build followed by every later build up to ``head`` (history order)."""
    builds: list[Build] = []
    base = _to_build(git.message(baseline_sha))
    if base is not None:
        builds.append(base)
    for commit in git.log(f"{baseline_sha}..{head}"):
        build = _to_build(commit)
        if build is not None:
            builds.append(build)
    return builds


def resolve_build(builds: list[Build], ref: str) -> Build:
    """Find a build by number or SHA prefix; never guesses."""
    ref = ref.strip()
    for build in builds:
        if build.number == ref or (len(ref) >= 7 and build.sha.startswith(ref)):
            return build
    nearest = ", ".join(b.number for b in builds[-5:]) or "none"
    raise BuildNotFoundError(f"build {ref!r} not found after baseline; latest builds: {nearest}")
