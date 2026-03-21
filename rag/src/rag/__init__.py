from rag.docs import (
    extract_lua_references,
    format_connected_section,
    clean_model_output,
    safe_read_lua,
    compute_source_hash,
    get_lua_files,
)
from rag.content import (
    extract_connected_content,
    extract_connected_for_chunk,
    extract_signatures_only,
    extract_compact_content,
    extract_require_stubs,
    compress_connected_content,
)

# search module NOT auto-imported (heavy side effects: ChromaDB, torch, etc.)
# Use: from rag.search import app  (or import rag.search)
