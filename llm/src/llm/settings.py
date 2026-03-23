import os
import tomllib
from llm.paths import PROJECT_ROOT

_CONFIG_PATH = PROJECT_ROOT / "config.toml"


def _load() -> dict:
    if _CONFIG_PATH.exists():
        with open(_CONFIG_PATH, "rb") as f:
            return tomllib.load(f)
    return {}


_cfg = _load()


def _get(section: str, key: str, default):
    """TOML value → env override MOD_DOC_<SECTION>_<KEY> → default.

    Type casting: env values are cast to type(default). Supports int and str.
    WARNING: Do NOT add bool defaults — bool("false") == True in Python.
    """
    env_key = f"MOD_DOC_{section.upper()}_{key.upper()}"
    toml_val = _cfg.get(section, {}).get(key, default)
    env_val = os.environ.get(env_key)
    if env_val is None:
        return toml_val
    return type(default)(env_val)


# === Model ===
MODEL_MAIN: str     = _get("model", "main",     "qwen3.5:cloud")
MODEL_UPDATE: str   = _get("model", "update",   "qwen3-coder-next:cloud")
MODEL_EMBED: str    = _get("model", "embed",    "BAAI/bge-small-en-v1.5")
MODEL_COMPRESS: str = _get("model", "compress", "qwen3.5:cloud")

# === Tokens ===
PROMPT_TOKEN_LIMIT: int      = _get("tokens", "prompt_limit",     16000)
MERGE_TOKEN_LIMIT: int       = _get("tokens", "merge_limit",      20000)
CONTEXT_RESERVE: int         = _get("tokens", "context_reserve",  7000)
STUB_FULL_THRESHOLD: int     = _get("tokens", "stub_threshold",   400)
CHUNKED_TOKEN_THRESHOLD: int = _get("tokens", "chunked_validate", 16000)
OLLAMA_NUM_CTX: int          = _get("tokens", "ollama_ctx",       256000)

# === Timing ===
CHUNK_SLEEP: int           = _get("timing", "chunk_sleep",     10)
MERGE_SLEEP: int           = _get("timing", "merge_sleep",     40)
NORMAL_SLEEP: int          = _get("timing", "normal_sleep",    20)
OLLAMA_TIMEOUT: float      = _get("timing", "ollama_timeout",  300.0)
OLLAMA_TIMEOUT_RETRIES: int = _get("timing", "timeout_retries", 2)

# === Validator ===
VALIDATOR_MAX_ITERATIONS: int      = _get("validator", "max_iterations",      10)
VALIDATOR_LOOP_MAX_ITERATIONS: int = _get("validator", "loop_max_iterations", 5)
MDX_NODE_TIMEOUT: int              = _get("validator", "mdx_timeout",         20)
LUA_CONTEXT_TOKENS: int            = _get("validator", "lua_context_tokens",  8000)
SECTION_TOKEN_THRESHOLD: int      = _get("validator", "section_token_threshold",    4000)
BATCH_TOKEN_LIMIT: int            = _get("validator", "batch_token_limit",           2000)
SECTION_LUA_CONTEXT_TOKENS: int   = _get("validator", "section_lua_context_tokens",  3500)
VALIDATOR_CALL_SLEEP: int         = _get("validator", "call_sleep",                    3)
BAD_RESPONSE_RETRIES: int         = _get("validator", "bad_response_retries",           3)

# === Debug ===
# Set MOD_DOC_DEBUG_PROMPTS=1 (or debug.prompts=1 in config.toml) to dump full prompts to .cache/debug_prompts/
DEBUG_PROMPTS: int = _get("debug", "prompts", 0)
