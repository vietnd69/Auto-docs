_DIR_TO_TYPE: dict[str, str] = {
    "brains": "brains",
    "behaviours": "behaviours",
    "stategraphs": "stategraphs",
    "widgets": "widgets",
    "screens": "screens",
    "prefabs": "prefabs",
    "components": "components",
    "cameras": "cameras",
}
_DATA_CONFIG_DIRS: frozenset[str] = frozenset({"map", "languages", "util"})


def detect_lua_type(filepath: str) -> str:
    """Return the DST file type for a Lua path.

    Detection order:
    1. Filename ends with '_replica.lua' → 'replica' (regardless of directory)
    2. First directory component maps to a known type
    3. Unknown/root-level/data dirs → 'data_config'

    Accepts paths as produced by main.py: './dir/file.lua' or 'file.lua'.
    Handles backslashes and leading slashes.
    """
    normalized = filepath.replace("\\", "/")
    if normalized.startswith("./"):
        normalized = normalized[2:]
    elif normalized.startswith("/"):
        normalized = normalized.lstrip("/")

    basename = normalized.rsplit("/", 1)[-1]
    if basename.endswith("_replica.lua"):
        return "replica"

    parts = normalized.split("/")
    if len(parts) == 1:
        return "data_config"

    dir_name = parts[0].lower()
    if dir_name in _DATA_CONFIG_DIRS:
        return "data_config"
    return _DIR_TO_TYPE.get(dir_name, "data_config")
