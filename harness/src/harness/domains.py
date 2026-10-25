"""Domain (file-type) classification. Domains key the self-improvement library."""

from __future__ import annotations

_DIR_DOMAINS = {
    "components": "component",
    "prefabs": "prefab",
    "stategraphs": "stategraph",
    "brains": "brain",
    "behaviours": "behaviour",
    "widgets": "widget",
    "screens": "screen",
    "cameras": "core",
    "map": "map",
    "scenarios": "scenario",
}

DOMAINS = (*sorted(set(_DIR_DOMAINS.values())), "replica", "data", "core")


def domain_of(path: str, is_data: bool = False) -> str:
    """Classify a ``dst-scripts`` relative path into a documentation domain."""
    parts = path.replace("\\\\", "/").split("/")
    if parts[-1].endswith("_replica.lua"):
        return "replica"
    if is_data:
        return "data"
    if len(parts) > 1:
        return _DIR_DOMAINS.get(parts[0].lower(), "core")
    return "core"


def update_domain(domain: str) -> str:
    """Library domain used for update jobs of ``domain`` files."""
    return f"update-{domain}"
