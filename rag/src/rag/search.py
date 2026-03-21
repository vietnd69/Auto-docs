"""
FastAPI server cho vector similarity search trên dst-scripts.

Chỉ chứa logic query — indexing được tách sang indexer.py.
Khi chạy trực tiếp (__main__), sẽ gọi reindex() trước khi khởi động server.
"""

import chromadb
from llama_index.vector_stores.chroma import ChromaVectorStore
from llama_index.core import VectorStoreIndex, Settings
from llama_index.embeddings.huggingface import HuggingFaceEmbedding
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from rag.indexer import (
    CHROMA_DIR,
    COLLECTION_NAME,
    EMBED_MODEL_NAME,
    EMBED_BATCH_SIZE,
)

# Setup embedding model (cần cho query — embed câu hỏi thành vector)
Settings.embed_model = HuggingFaceEmbedding(
    model_name=EMBED_MODEL_NAME,
    embed_batch_size=EMBED_BATCH_SIZE,
)

# Kết nối ChromaDB (chỉ đọc, không index)
db = chromadb.PersistentClient(path=CHROMA_DIR)
chroma_collection = db.get_or_create_collection(COLLECTION_NAME)
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

# Khởi tạo Retriever (chỉ dùng embedding local, KHÔNG gọi LLM)
index = VectorStoreIndex.from_vector_store(vector_store)
retriever = index.as_retriever(similarity_top_k=50)

app = FastAPI(title="DST RAG API")


class QueryRequest(BaseModel):
    question: str


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
    from rag.indexer import reindex

    # Index trước khi chạy server
    print("\n--- Cập nhật vector store ---")
    reindex()

    print("\n Khởi động RAG API Server...")
    print("Truy cập http://localhost:8000/docs để test API bằng giao diện Swagger UI")
    uvicorn.run(app, host="0.0.0.0", port=8000)
