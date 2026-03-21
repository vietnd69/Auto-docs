from datetime import datetime
from llm.paths import PROJECT_ROOT

# === LLM CONFIG ===
MODEL_NAME = "qwen3.5:cloud"

# === PATHS ===
CHECKPOINT_DIR = str(PROJECT_ROOT / ".cache" / "chunked_checkpoints")

# === MODEL SETTINGS ===
VERSION = "714014"
TODAY_DATE = datetime.now().strftime("%Y-%m-%d")

# === VALIDATOR & CACHE ===
MDX_NODE_TIMEOUT = 20

# === TIMING ===
CHUNK_SLEEP = 10
MERGE_SLEEP = 40
NORMAL_SLEEP = 20


def get_shared_file_tree(max_depth=3):
    """Sinh cây thư mục thu gọn cho prompt content."""
    from core.utils.tree import generate_slim_tree
    from llm.paths import BASE_LUA_DIR
    return generate_slim_tree(BASE_LUA_DIR, max_depth=max_depth)
