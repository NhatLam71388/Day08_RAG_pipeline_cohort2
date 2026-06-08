"""
Task 5 — Semantic Search Module (Dense Retrieval).

Sử dụng ChromaDB + sentence-transformers/all-MiniLM-L6-v2
(cùng model và vector store với Task 4).
"""

from pathlib import Path

CHROMA_DIR = Path(__file__).parent.parent / "data" / "chroma_db"
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
COLLECTION_NAME = "drug_law_docs"

_embed_fn = None
_collection = None


def _get_embed_fn():
    """Load embedding function — cùng logic với Task 4."""
    global _embed_fn
    if _embed_fn is not None:
        return _embed_fn

    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        _embed_fn = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        return _embed_fn
    except Exception:
        pass

    try:
        from sentence_transformers import SentenceTransformer
        _model = SentenceTransformer(EMBEDDING_MODEL)
        _embed_fn = lambda texts: _model.encode(texts).tolist()
        return _embed_fn
    except Exception:
        pass

    import hashlib, math
    def _dummy(texts):
        dim = 384
        results = []
        for t in texts:
            h = int(hashlib.md5(t.encode()).hexdigest(), 16)
            vec = [math.sin(h * (i + 1) * 0.01) for i in range(dim)]
            norm = math.sqrt(sum(x * x for x in vec)) or 1
            results.append([x / norm for x in vec])
        return results
    _embed_fn = _dummy
    return _embed_fn


def _get_collection():
    global _collection
    if _collection is None:
        import chromadb
        client = chromadb.PersistentClient(path=str(CHROMA_DIR))
        _collection = client.get_collection(name=COLLECTION_NAME)
    return _collection


def semantic_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Tìm kiếm ngữ nghĩa sử dụng vector cosine similarity.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,   # cosine similarity [0, 1]
            'metadata': dict
        }
        Sorted by score descending.
    """
    if not CHROMA_DIR.exists():
        print("⚠ ChromaDB chưa được index. Chạy Task 4 trước.")
        return []

    embed_fn = _get_embed_fn()
    query_embedding = embed_fn([query])[0]

    collection = _get_collection()
    results = collection.query(
        query_embeddings=[query_embedding],
        n_results=min(top_k, collection.count()),
        include=["documents", "metadatas", "distances"],
    )

    output = []
    if results and results["documents"] and results["documents"][0]:
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB trả về cosine distance [0,2], chuyển thành similarity [0,1]
            similarity = max(0.0, 1.0 - dist / 2.0)
            output.append({
                "content": doc,
                "score": similarity,
                "metadata": meta,
            })

    # Sorted descending by score (ChromaDB đã sort theo distance, cần đảo)
    output.sort(key=lambda x: x["score"], reverse=True)
    return output[:top_k]


if __name__ == "__main__":
    results = semantic_search("hình phạt cho tội tàng trữ ma tuý", top_k=5)
    for r in results:
        print(f"[{r['score']:.3f}] [{r['metadata'].get('type', '?')}] {r['content'][:100]}...")
