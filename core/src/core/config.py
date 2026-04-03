from datetime import datetime
from llm.paths import PROJECT_ROOT, read_build_version

# === PATHS ===
CHECKPOINT_DIR = str(PROJECT_ROOT / ".cache" / "chunked_checkpoints")

# === MODEL SETTINGS ===
VERSION = read_build_version(fallback="unknown")
TODAY_DATE = datetime.now().strftime("%Y-%m-%d")


def get_shared_file_tree(max_depth=3):
    """Sinh cây thư mục thu gọn cho prompt content."""
    from core.utils.tree import generate_slim_tree
    from llm.paths import BASE_LUA_DIR
    return generate_slim_tree(BASE_LUA_DIR, max_depth=max_depth)
