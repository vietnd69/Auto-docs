"""
ChromaDB vector store indexing for dst-scripts.

Separated from search.py so it can be called from anywhere (watcher, CLI, etc.)
without starting a FastAPI server.

All heavy imports (chromadb, torch, llama-index) only happen when reindex() is called,
not when the module is imported — safe for lazy import.
"""

import json
import gc
from pathlib import Path

from llm.settings import MODEL_EMBED as EMBED_MODEL_NAME


# === CONSTANTS ===
_WORKSPACE_ROOT = Path(__file__).parents[3]
_DATA_DIR = _WORKSPACE_ROOT / "data"

SCRIPTS_DIR = str(_WORKSPACE_ROOT / "dst-scripts")
CHROMA_DIR = str(_WORKSPACE_ROOT / "dst_chroma_db")
TRACKER_FILE = str(_DATA_DIR / "file_tracker.json")

EMBED_BATCH_SIZE = 16
CHUNK_SIZE = 512
CHUNK_OVERLAP = 100
COLLECTION_NAME = "dst_scripts"
BATCH_SIZE = 5


def reindex(
    scripts_dir: str | None = None,
    chroma_dir: str | None = None,
) -> dict:
    """
    Scan dst-scripts/ and update the ChromaDB vector store.
    Only indexes new files or files whose content has changed (hash check via file_tracker.json).

    Heavy imports (chromadb, torch, llama-index) happen inside this function,
    so module-level import is lightweight.

    Args:
        scripts_dir: Path to the directory containing .lua files. Default: dst-scripts/
        chroma_dir: Path to ChromaDB persistent storage. Default: dst_chroma_db/

    Returns:
        dict: {"processed": int, "skipped": int, "total_chunks": int}
    """
    # Heavy imports — only load when indexing is actually needed
    import chromadb
    from llama_index.vector_stores.chroma import ChromaVectorStore
    from llama_index.core import SimpleDirectoryReader, Settings
    from llama_index.embeddings.huggingface import HuggingFaceEmbedding
    from llama_index.core.ingestion import IngestionPipeline
    from llama_index.core.node_parser import TokenTextSplitter

    scripts_dir = scripts_dir or SCRIPTS_DIR
    chroma_dir = chroma_dir or CHROMA_DIR

    # 1. Setup embedding model
    Settings.embed_model = HuggingFaceEmbedding(
        model_name=EMBED_MODEL_NAME,
        embed_batch_size=EMBED_BATCH_SIZE,
    )

    # 2. Setup ChromaDB
    db = chromadb.PersistentClient(path=chroma_dir)
    chroma_collection = db.get_or_create_collection(COLLECTION_NAME)
    vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

    # 3. Load file tracker (prevent re-indexing unchanged files)
    try:
        with open(TRACKER_FILE, "r") as f:
            file_tracker = json.load(f)
        print("  [INDEX] File Tracker loaded")
    except (FileNotFoundError, json.JSONDecodeError):
        file_tracker = {}
        print("  [INDEX] Initializing new File Tracker")

    # 4. Scan files and filter out unchanged ones
    print(f"  [INDEX] Scanning {scripts_dir}...")
    documents = SimpleDirectoryReader(scripts_dir, filename_as_id=True).load_data()

    docs_to_process = [
        doc for doc in documents
        if doc.id_ not in file_tracker or file_tracker[doc.id_] != doc.hash
    ]

    stats = {
        "processed": len(docs_to_process),
        "skipped": len(documents) - len(docs_to_process),
        "total_chunks": 0,
    }

    if not docs_to_process:
        print(f"  [INDEX] All {len(documents)} files unchanged — skipping")
        return stats

    print(f"  [INDEX] {len(docs_to_process)} files need indexing/updating")

    # 5. Run ingestion pipeline in batches
    pipeline = IngestionPipeline(
        transformations=[
            TokenTextSplitter(chunk_size=CHUNK_SIZE, chunk_overlap=CHUNK_OVERLAP),
            Settings.embed_model,
        ],
        vector_store=vector_store,
    )

    for i in range(0, len(docs_to_process), BATCH_SIZE):
        batch_docs = docs_to_process[i : i + BATCH_SIZE]
        batch_num = i // BATCH_SIZE + 1
        print(f"  [INDEX] Batch {batch_num} ({len(batch_docs)} files)...", end=" ")

        nodes = pipeline.run(documents=batch_docs)
        print(f"→ {len(nodes)} chunks")
        stats["total_chunks"] += len(nodes)

        # Update tracker after each batch (checkpoint)
        for doc in batch_docs:
            file_tracker[doc.id_] = doc.hash
        with open(TRACKER_FILE, "w") as f:
            json.dump(file_tracker, f)

        # Free RAM & VRAM
        del batch_docs
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    print(f"  [INDEX] Done — {stats['total_chunks']} new chunks")
    return stats
