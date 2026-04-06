"""
skills_loader — parse docs_SKILL.md index and load skill markdown files.

API:
    load_skill(name, *, index_path="docs_SKILL.md") -> str
    load_skills_for(target, *, index_path="docs_SKILL.md") -> dict[str, str]
"""
from pathlib import Path
from pathlib import Path as _Path
import os as _os

_DEFAULT_INDEX = str(_Path(__file__).parents[3] / "skills" / "docs_SKILL.md")


def _parse_index(index_path: str) -> dict[str, dict]:
    """
    Parse docs_SKILL.md and return {skill_name: {"file": str, "inject_into": list}}.

    Format expected:
        ---
        version: 1
        ---

        ## skill_name
        file: path/to/skill.md
        inject_into: [target1, target2]
    """
    import yaml

    path = Path(index_path)
    text = path.read_text(encoding="utf-8")

    # Split on newline + "## " to separate preamble from skill sections.
    # parts[0] = YAML preamble; parts[1:] = one section per skill.
    parts = text.split("\n## ")

    skills: dict[str, dict] = {}
    for part in parts[1:]:
        lines = [ln.strip() for ln in part.strip().splitlines()]
        if not lines:
            continue
        name = lines[0]
        entry: dict = {}
        for line in lines[1:]:
            if line.startswith("file:"):
                entry["file"] = line[len("file:"):].strip()
            elif line.startswith("inject_into:"):
                raw = line[len("inject_into:"):].strip()
                raw_list = yaml.safe_load(raw) or []
                if not isinstance(raw_list, list):
                    raw_list = [raw_list]
                entry["inject_into"] = raw_list

        if "file" not in entry:
            raise ValueError(f"Skill '{name}' in index missing 'file:' field")

        skills[name] = entry

    return skills


def load_skill(name: str, *, index_path: str = _DEFAULT_INDEX) -> str:
    """Load a single skill by name. Returns raw markdown content (utf-8).

    Raises:
        KeyError: if name not in index.
        FileNotFoundError: if the skill .md file does not exist.
        ValueError: if the index entry is malformed (missing file: field).
    """
    skills = _parse_index(index_path)
    if name not in skills:
        raise KeyError(f"Skill '{name}' not found in {index_path}")

    root = Path(index_path).parent
    file_path = root / skills[name]["file"]

    if not file_path.exists():
        raise FileNotFoundError(
            f"Skill file '{skills[name]['file']}' not found (resolved to {file_path})"
        )

    content = file_path.read_text(encoding="utf-8")
    # Strip the "# Skill: ..." metadata header if present
    lines = content.split("\n", 1)
    if lines[0].startswith("# Skill:"):
        content = lines[1].lstrip("\n") if len(lines) > 1 else ""
    return content


def load_skills_for(target: str, *, index_path: str = _DEFAULT_INDEX) -> dict[str, str]:
    """Return {name: content} for all skills whose inject_into includes target.

    Returns an empty dict if no skills match (not an error).
    """
    skills = _parse_index(index_path)
    root = Path(index_path).parent
    result = {}
    for name, entry in skills.items():
        if target in entry.get("inject_into", []):
            file_path = root / entry["file"]
            if not file_path.exists():
                raise FileNotFoundError(
                    f"Skill file '{entry['file']}' not found (resolved to {file_path})"
                )
            content = file_path.read_text(encoding="utf-8")
            # Strip the "# Skill: ..." metadata header if present
            lines = content.split("\n", 1)
            if lines[0].startswith("# Skill:"):
                content = lines[1].lstrip("\n") if len(lines) > 1 else ""
            result[name] = content
    return result


# ── New API (Phase 1) ────────────────────────────────────────────────────────

import logging as _logging

_log = _logging.getLogger(__name__)
_SKILLS_DIR = _Path(__file__).parents[3] / "skills"
_GROUP_ORDER = {"roles": 0, "knowledge": 1, "rules": 2}

# Module-level cache — populated on first call to _get_registry()
_registry: dict | None = None


def _parse_frontmatter(path: Path) -> dict:
    """Parse YAML frontmatter from a skill .md file."""
    import yaml

    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        raise ValueError(f"Skill file {path} missing YAML frontmatter")

    end = text.index("---", 3)
    fm = yaml.safe_load(text[3:end].strip()) or {}

    if "name" not in fm:
        raise ValueError(f"Skill file {path} missing 'name' in frontmatter")
    if "inject_into" not in fm:
        raise ValueError(f"Skill file {path} missing 'inject_into' in frontmatter")

    # Extract body: strip frontmatter block + optional "# Title" header line
    body = text[end + 3:].lstrip("\n")
    lines = body.split("\n", 1)
    if lines and lines[0].startswith("# "):
        body = lines[1].lstrip("\n") if len(lines) > 1 else ""

    group_name = path.parent.name
    group = _GROUP_ORDER.get(group_name)
    if group is None:
        raise ValueError(
            f"Skill file {path} in unknown subdirectory '{group_name}'"
        )

    inject = fm["inject_into"]
    if not isinstance(inject, list):
        inject = [inject]

    return {
        "name": fm["name"],
        "description": fm.get("description", ""),
        "inject_into": inject,
        "content": body,
        "group": group,
        "path": str(path),
    }


def _build_registry_new() -> dict[str, dict]:
    """Scan skills/ subdirectories and build {name: entry} registry."""
    registry: dict[str, dict] = {}
    for subdir in ("roles", "knowledge", "rules"):
        dir_path = _SKILLS_DIR / subdir
        if not dir_path.is_dir():
            continue
        for md_file in sorted(dir_path.glob("*.md")):
            entry = _parse_frontmatter(md_file)
            name = entry["name"]
            if name in registry:
                raise ValueError(
                    f"Duplicate skill name '{name}': {entry['path']} and {registry[name]['path']}"
                )
            registry[name] = entry
    return registry


def _build_registry_legacy() -> dict[str, dict]:
    """Bridge: build registry from old-format docs_SKILL.md."""
    index_path = str(_SKILLS_DIR / "docs_SKILL.md")
    index = _parse_index(index_path)
    root = _SKILLS_DIR
    registry: dict[str, dict] = {}
    for name, entry in index.items():
        file_path = root / entry["file"]
        content = file_path.read_text(encoding="utf-8")
        lines = content.split("\n", 1)
        if lines[0].startswith("# Skill:"):
            content = lines[1].lstrip("\n") if len(lines) > 1 else ""
        registry[name] = {
            "name": name,
            "description": "",
            "inject_into": entry.get("inject_into", []),
            "content": content,
            "group": 1,  # default: knowledge group
            "path": str(file_path),
        }
    return registry


def _get_registry(*, _override: dict | None = None) -> dict[str, dict]:
    """Return the skill registry, building on first call."""
    if _override is not None:
        return _override
    global _registry
    if _registry is None:
        if (_SKILLS_DIR / "roles").is_dir():
            _registry = _build_registry_new()
        else:
            _registry = _build_registry_legacy()
    return _registry


def _clear_cache() -> None:
    """Reset module-level registry cache. Call in test teardown."""
    global _registry
    _registry = None


def combine_skills(
    target: str,
    *,
    exclude: list[str] | None = None,
    _registry_override: dict | None = None,
) -> str:
    """Concatenate all skills matching target into a single string.

    Order: role (group 0) → knowledge (group 1) → rules (group 2).
    Within each group, sorted alphabetically by name.
    Separator: ``=== SKILL: {name} ===\\n`` prefix per block.
    """
    reg = _get_registry(_override=_registry_override)
    exclude_set = set(exclude) if exclude else set()

    matches = [
        e for e in reg.values()
        if target in e["inject_into"] and e["name"] not in exclude_set
    ]

    if not matches:
        _log.warning(
            "combine_skills(%r) matched 0 skills — possible typo in target name",
            target,
        )
        return ""

    matches.sort(key=lambda e: (e["group"], e["name"]))
    parts = []
    for entry in matches:
        parts.append(f"=== SKILL: {entry['name']} ===\n{entry['content']}")
    return "\n\n".join(parts)
