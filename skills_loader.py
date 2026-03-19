"""
skills_loader — parse docs_SKILL.md index and load skill markdown files.

API:
    load_skill(name, *, index_path="docs_SKILL.md") -> str
    load_skills_for(target, *, index_path="docs_SKILL.md") -> dict[str, str]
"""
from pathlib import Path


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
                entry["inject_into"] = yaml.safe_load(raw) or []

        if "file" not in entry:
            raise ValueError(f"Skill '{name}' in index missing 'file:' field")

        skills[name] = entry

    return skills


def load_skill(name: str, *, index_path: str = "docs_SKILL.md") -> str:
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

    return file_path.read_text(encoding="utf-8")


def load_skills_for(target: str, *, index_path: str = "docs_SKILL.md") -> dict[str, str]:
    """Return {name: content} for all skills whose inject_into includes target.

    Returns an empty dict if no skills match (not an error).
    """
    skills = _parse_index(index_path)
    return {
        name: load_skill(name, index_path=index_path)
        for name, entry in skills.items()
        if target in entry.get("inject_into", [])
    }
