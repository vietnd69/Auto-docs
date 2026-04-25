"""
skills_loader — YAML frontmatter registry and combine_skills API.

API:
    combine_skills(target, *, exclude=None) -> str
    load_skill(name) -> str
    load_skills_for(target, *, exclude=None) -> dict[str, str]
    few_shot_excludes(lua_type) -> list[str]
    load_trimmed_writing_guide(lua_type) -> str
"""
import logging as _logging
import re as _re
from pathlib import Path
from pathlib import Path as _Path

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


def _build_registry() -> dict[str, dict]:
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


def _get_registry(*, _override: dict | None = None) -> dict[str, dict]:
    """Return the skill registry, building on first call."""
    if _override is not None:
        return _override
    global _registry
    if _registry is None:
        _registry = _build_registry()
    return _registry


def _clear_cache() -> None:
    """Reset module-level registry cache. Call in test teardown."""
    global _registry
    _registry = None


def load_skill(name: str, *, _registry_override: dict | None = None) -> str:
    """Load single skill by name. Raises KeyError if not found."""
    reg = _get_registry(_override=_registry_override)
    if name not in reg:
        raise KeyError(f"Skill '{name}' not found in registry")
    return reg[name]["content"]


def load_skills_for(
    target: str,
    *,
    exclude: list[str] | None = None,
    _registry_override: dict | None = None,
) -> dict[str, str]:
    """Return {name: content} for all skills matching target."""
    reg = _get_registry(_override=_registry_override)
    exclude_set = set(exclude) if exclude else set()
    return {
        name: entry["content"]
        for name, entry in reg.items()
        if target in entry["inject_into"] and name not in exclude_set
    }


def combine_skills(
    target: str,
    *,
    exclude: list[str] | None = None,
    _registry_override: dict | None = None,
) -> str:
    """Concatenate all skills matching target into a single string.

    Order: role (group 0) -> knowledge (group 1) -> rules (group 2).
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
            "combine_skills(%r) matched 0 skills -- possible typo in target name",
            target,
        )
        return ""

    matches.sort(key=lambda e: (e["group"], e["name"]))
    parts = []
    for entry in matches:
        parts.append(f"=== SKILL: {entry['name']} ===\n{entry['content']}")
    return "\n\n".join(parts)


_ALL_FEW_SHOTS: frozenset[str] = frozenset({
    "few_shot",
    "few_shot_brain",
    "few_shot_behaviour",
    "few_shot_stategraph",
    "few_shot_widget",
    "few_shot_screen",
    "few_shot_prefab",
    "few_shot_data",
})

_FEW_SHOT_FOR_TYPE: dict[str, str] = {
    "brains": "few_shot_brain",
    "behaviours": "few_shot_behaviour",
    "stategraphs": "few_shot_stategraph",
    "widgets": "few_shot_widget",
    "screens": "few_shot_screen",
    "prefabs": "few_shot_prefab",
    "components": "few_shot",
    "replica": "few_shot",
    "cameras": "few_shot",
    "data_config": "few_shot_data",
}

_TYPE_BLOCK_RE = _re.compile(
    r"<!-- type:(\w+) -->\n?(.*?)<!-- /type -->",
    _re.DOTALL,
)


def few_shot_excludes(lua_type: str) -> list[str]:
    """Return exclude list for combine_skills() — all few-shots except the one for lua_type."""
    keep = _FEW_SHOT_FOR_TYPE.get(lua_type, "few_shot")
    return sorted(_ALL_FEW_SHOTS - {keep})


def load_trimmed_writing_guide(
    lua_type: str,
    *,
    _registry_override: dict | None = None,
) -> str:
    """Return writing_guide content with only the type-specific section for lua_type.

    Strips all <!-- type:X -->...<!-- /type --> blocks except the one matching lua_type.
    For types with no dedicated section, strips all type blocks.
    HTML comment markers are removed from the output.
    """
    reg = _get_registry(_override=_registry_override)
    if "writing_guide" not in reg:
        return ""
    content = reg["writing_guide"]["content"]

    def _keep_or_strip(m: _re.Match) -> str:
        return m.group(2).rstrip("\n") if m.group(1) == lua_type else ""

    result = _TYPE_BLOCK_RE.sub(_keep_or_strip, content)
    result = _re.sub(r"\n{3,}", "\n\n", result)
    return result.strip()
