import os
import json
import chromadb
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core import StorageContext, VectorStoreIndex, SimpleDirectoryReader, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from llama_index.core.ingestion import IngestionPipeline
from llama_index.core.node_parser import TokenTextSplitter
import gc
import torch
from pathlib import Path

# 1. Cấu hình mô hình (chỉ embedding, không cần LLM vì chỉ dùng vector search)
# Đã thêm device="cuda" để ép chạy Card màn hình NVIDIA (VRAM)
Settings.embed_model = HuggingFaceEmbedding(
    model_name="BAAI/bge-small-en-v1.5",
    embed_batch_size=16,
    # device="cuda"
)

# 2. Thiết lập ChromaDB
db = chromadb.PersistentClient(path="./dst_chroma_db")
chroma_collection = db.get_or_create_collection("dst_scripts")
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

# 3. QUẢN LÝ CACHE MỚI (File Tracker - Chống nạp lặp tuyệt đối)
_WORKSPACE_ROOT = Path(__file__).parents[3]
TRACKER_FILE = str(_WORKSPACE_ROOT / "data" / "file_tracker.json")
try:
    with open(TRACKER_FILE, "r") as f:
        file_tracker = json.load(f)
    print("--- Đã tải bộ nhớ theo dõi File (File Tracker) ---")
except (FileNotFoundError, json.JSONDecodeError):
    file_tracker = {}
    print("--- Khởi tạo bộ nhớ File Tracker mới ---")

# 4. Quét file và Lọc file chưa bị thay đổi
print("--- Đang quét dữ liệu ổ cứng... ---")
documents = SimpleDirectoryReader("./dst-scripts", filename_as_id=True).load_data()

# Chỉ lấy những file mới hoặc file bị sửa đổi nội dung (Hash thay đổi)
docs_to_process = []
for doc in documents:
    if doc.id_ not in file_tracker or file_tracker[doc.id_] != doc.hash:
        docs_to_process.append(doc)

# 5. Chạy Pipeline để nạp dữ liệu (Chỉ chạy phần file mới)
if not docs_to_process:
    print(f"BỎ QUA: Toàn bộ {len(documents)} file không có gì thay đổi. Đã có sẵn trong DB!")
else:
    print(f"Phát hiện {len(docs_to_process)} file cần nạp/cập nhật!")

    pipeline = IngestionPipeline(
        transformations=[
            TokenTextSplitter(chunk_size=512, chunk_overlap=100),
            Settings.embed_model,
        ],
        vector_store=vector_store,
    )

    BATCH_SIZE = 5
    total_nodes = 0

    for i in range(0, len(docs_to_process), BATCH_SIZE):
        batch_docs = docs_to_process[i : i + BATCH_SIZE]
        print(f"Đang xử lý mẻ {i // BATCH_SIZE + 1} (File {i} đến {i + len(batch_docs)})...", end=" ")

        # Chạy pipeline
        nodes = pipeline.run(documents=batch_docs)

        print(f"Đã nạp {len(nodes)} chunks mới")
        total_nodes += len(nodes)

        # Cập nhật Hash vào tracker sau mỗi mẻ (Save game)
        for doc in batch_docs:
            file_tracker[doc.id_] = doc.hash
        with open(TRACKER_FILE, "w") as f:
            json.dump(file_tracker, f)

        # DỌN RÁC RAM & VRAM NGAY LẬP TỨC
        del batch_docs
        gc.collect()
        if torch.cuda.is_available():
            torch.cuda.empty_cache()

    print(f"\n--- Hoàn tất! Đã thêm mới/cập nhật {total_nodes} đoạn code vào database ---")

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

app = FastAPI(title="DST RAG API")

class QueryRequest(BaseModel):
    question: str

# 6. Khởi tạo Retriever (chỉ dùng embedding local, KHÔNG gọi LLM)
index = VectorStoreIndex.from_vector_store(vector_store)
retriever = index.as_retriever(similarity_top_k=50)

@app.post("/query")
def query_rag(request: QueryRequest):
    try:
        print(f"\n Nhận câu hỏi: {request.question}")

        # Chỉ tìm kiếm vector similarity (local, không gọi LLM)
        nodes = retriever.retrieve(request.question)

        # Parse danh sách source files (lọc trùng, giữ score cao nhất)
        seen = {}
        for node in nodes:
            fname = node.metadata.get('file_name', 'Unknown')
            score = float(node.score) if node.score else 0.0
            if fname not in seen or score > seen[fname]:
                seen[fname] = score

        # Sắp xếp theo score giảm dần
        sources = [{"file_name": k, "score": v} for k, v in sorted(seen.items(), key=lambda x: x[1], reverse=True)]

        print(f"--- Sources: {len(sources)} files ---")
        for s in sources[:10]:
            print(f"  - {s['file_name']} (score: {s['score']:.4f})")
        if len(sources) > 10:
            print(f"  ... và {len(sources) - 10} file khác")
        print("-------------------\n")

        return {
            "sources": sources
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

if __name__ == "__main__":
    import uvicorn
    # Mở server ở port 8000
    print("\n Khởi động RAG API Server...")
    print("Truy cập http://localhost:8000/docs để test API bằng giao diện Swagger UI")
    uvicorn.run(app, host="0.0.0.0", port=8000)
