"""
Indexing ChromaDB vector store cho dst-scripts.

Tách riêng từ search.py để có thể gọi từ bất kỳ đâu (watcher, CLI, etc.)
mà không cần khởi động FastAPI server.

Tất cả heavy imports (chromadb, torch, llama-index) chỉ xảy ra khi gọi reindex(),
không phải khi import module — an toàn cho lazy import.
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
    Quét dst-scripts/ và cập nhật ChromaDB vector store.
    Chỉ index file mới hoặc file có nội dung thay đổi (hash check via file_tracker.json).

    Heavy imports (chromadb, torch, llama-index) xảy ra bên trong hàm này,
    nên import module-level là nhẹ.

    Args:
        scripts_dir: Đường dẫn đến thư mục chứa file .lua. Default: dst-scripts/
        chroma_dir: Đường dẫn đến ChromaDB persistent storage. Default: dst_chroma_db/

    Returns:
        dict: {"processed": int, "skipped": int, "total_chunks": int}
    """
    # Heavy imports — chỉ load khi thực sự cần index
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

    # 3. Load file tracker (chống nạp lặp)
    try:
        with open(TRACKER_FILE, "r") as f:
            file_tracker = json.load(f)
        print("  [INDEX] Đã tải File Tracker")
    except (FileNotFoundError, json.JSONDecodeError):
        file_tracker = {}
        print("  [INDEX] Khởi tạo File Tracker mới")

    # 4. Quét file và lọc file chưa thay đổi
    print(f"  [INDEX] Đang quét {scripts_dir}...")
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
        print(f"  [INDEX] Toàn bộ {len(documents)} file không thay đổi — bỏ qua")
        return stats

    print(f"  [INDEX] {len(docs_to_process)} file cần index/cập nhật")

    # 5. Chạy ingestion pipeline theo batch
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
        print(f"  [INDEX] Mẻ {batch_num} ({len(batch_docs)} files)...", end=" ")

        nodes = pipeline.run(documents=batch_docs)
        print(f"→ {len(nodes)} chunks")
        stats["total_chunks"] += len(nodes)

        # Cập nhật tracker sau mỗi mẻ (checkpoint)
        for doc in batch_docs:
            file_tracker[doc.id_] = doc.hash
        with open(TRACKER_FILE, "w") as f:
            json.dump(file_tracker, f)

        # Dọn RAM & VRAM
        del batch_docs
        gc.collect()
        try:
            import torch
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except ImportError:
            pass

    print(f"  [INDEX] Hoàn tất — {stats['total_chunks']} chunks mới")
    return stats
