"""
FastAPI server for vector similarity search over dst-scripts.

Contains only query logic — indexing is separated into indexer.py.
When run directly (__main__), calls reindex() before starting the server.
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

# Setup embedding model (required for query — embeds the question into a vector)
Settings.embed_model = HuggingFaceEmbedding(
    model_name=EMBED_MODEL_NAME,
    embed_batch_size=EMBED_BATCH_SIZE,
)

# Connect to ChromaDB (read-only, no indexing)
db = chromadb.PersistentClient(path=CHROMA_DIR)
chroma_collection = db.get_or_create_collection(COLLECTION_NAME)
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

# Initialize Retriever (uses local embedding only, does NOT call LLM)
index = VectorStoreIndex.from_vector_store(vector_store)
retriever = index.as_retriever(similarity_top_k=50)

app = FastAPI(title="DST RAG API")


class QueryRequest(BaseModel):
    question: str


@app.post("/query")
def query_rag(request: QueryRequest):
    try:
        print(f"\n Received question: {request.question}")

        # Vector similarity search only (local, no LLM call)
        nodes = retriever.retrieve(request.question)

        # Parse source file list (deduplicate, keep highest score)
        seen = {}
        for node in nodes:
            fname = node.metadata.get('file_name', 'Unknown')
            score = float(node.score) if node.score else 0.0
            if fname not in seen or score > seen[fname]:
                seen[fname] = score

        # Sort by score descending
        sources = [{"file_name": k, "score": v} for k, v in sorted(seen.items(), key=lambda x: x[1], reverse=True)]

        print(f"--- Sources: {len(sources)} files ---")
        for s in sources[:10]:
            print(f"  - {s['file_name']} (score: {s['score']:.4f})")
        if len(sources) > 10:
            print(f"  ... and {len(sources) - 10} more files")
        print("-------------------\n")

        return {
            "sources": sources
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


if __name__ == "__main__":
    import uvicorn
    from rag.indexer import reindex

    # Index before starting server
    print("\n--- Updating vector store ---")
    reindex()

    print("\n Starting RAG API Server...")
    print("Visit http://localhost:8000/docs to test the API via Swagger UI")
    uvicorn.run(app, host="0.0.0.0", port=8000)
