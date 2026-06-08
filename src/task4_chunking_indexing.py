"""
Task 4 — Chunking & Indexing vào Vector Store.

Lựa chọn thiết kế:
    Chunking: RecursiveCharacterTextSplitter
        - chunk_size=500: đủ ngữ cảnh, không quá dài gây nhiễu
        - chunk_overlap=50: giảm mất context ở ranh giới chunk
        - Separators theo thứ tự ưu tiên: đoạn văn → dòng → câu → từ

    Embedding: sentence-transformers/all-MiniLM-L6-v2
        - 384 dimensions, nhẹ (~90MB), chạy tốt trên CPU
        - Multilingual support đủ cho tiếng Việt
        - Tốc độ nhanh, phù hợp cho học tập

    Vector Store: ChromaDB (persistent local)
        - Không cần Docker, chạy local dễ dàng
        - Hỗ trợ cosine similarity built-in
        - Lưu persistent vào data/chroma_db/
"""

import json
from pathlib import Path

STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"
CHROMA_DIR = Path(__file__).parent.parent / "data" / "chroma_db"
CHUNKS_FILE = Path(__file__).parent.parent / "data" / "chunks.json"

# Chunking: RecursiveCharacterTextSplitter, an toàn và hiệu quả cho văn bản pháp luật
CHUNK_SIZE = 500
CHUNK_OVERLAP = 50
CHUNKING_METHOD = "recursive"

# Embedding: all-MiniLM-L6-v2, nhẹ, nhanh, multilingual
EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384

COLLECTION_NAME = "drug_law_docs"


def load_documents() -> list[dict]:
    """
    Đọc toàn bộ markdown files từ data/standardized/.

    Returns:
        List of {'content': str, 'metadata': {'source': str, 'type': str}}
    """
    documents = []
    for md_file in STANDARDIZED_DIR.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if not content.strip():
                continue
            doc_type = "legal" if "legal" in str(md_file) else "news"
            documents.append({
                "content": content,
                "metadata": {
                    "source": md_file.name,
                    "type": doc_type,
                    "path": str(md_file),
                }
            })
        except Exception as e:
            print(f"  ⚠ Lỗi đọc {md_file.name}: {e}")
    return documents


def _recursive_split(text: str, separators: list[str], chunk_size: int, chunk_overlap: int) -> list[str]:
    """
    RecursiveCharacterTextSplitter tự implement — không cần langchain.
    Thử tách theo separator ưu tiên cao nhất, nếu chunk vẫn dài thì thử separator tiếp theo.
    """
    chunks = []
    if len(text) <= chunk_size:
        return [text] if text.strip() else []

    separator = separators[0] if separators else ""
    next_separators = separators[1:] if len(separators) > 1 else []

    parts = text.split(separator)
    current = ""

    for part in parts:
        candidate = (current + separator + part).strip() if current else part.strip()
        if len(candidate) <= chunk_size:
            current = candidate
        else:
            if current:
                if len(current) > chunk_size and next_separators:
                    chunks.extend(_recursive_split(current, next_separators, chunk_size, chunk_overlap))
                else:
                    chunks.append(current)
                # Overlap: carry tail of current into next chunk
                overlap_start = max(0, len(current) - chunk_overlap)
                current = current[overlap_start:] + (separator + part).strip() if current[overlap_start:] else part.strip()
            else:
                if len(part) > chunk_size and next_separators:
                    chunks.extend(_recursive_split(part, next_separators, chunk_size, chunk_overlap))
                    current = ""
                else:
                    current = part.strip()

    if current.strip():
        chunks.append(current.strip())

    return chunks


def chunk_documents(documents: list[dict]) -> list[dict]:
    """
    Chunk documents theo RecursiveCharacterTextSplitter (tự implement).

    Chunking strategy: RecursiveCharacterTextSplitter
        - chunk_size=500: đủ context, không quá dài
        - chunk_overlap=50: tránh mất context ở ranh giới
        - Separator ưu tiên: đoạn văn → dòng → câu → từ

    Returns:
        List of {'content': str, 'metadata': dict}
    """
    separators = ["\n\n", "\n", ". ", " "]
    chunks = []
    for doc in documents:
        splits = _recursive_split(doc["content"], separators, CHUNK_SIZE, CHUNK_OVERLAP)
        for i, chunk_text in enumerate(splits):
            if chunk_text.strip():
                chunks.append({
                    "content": chunk_text.strip(),
                    "metadata": {
                        **doc["metadata"],
                        "chunk_index": i,
                    }
                })
    return chunks


def _get_embedding_function():
    """
    Trả về embedding function tương thích.
    Ưu tiên: chromadb built-in → sentence-transformers → dummy.
    """
    # Option 1: ChromaDB's built-in SentenceTransformer embedding (khuyến nghị)
    try:
        from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction
        ef = SentenceTransformerEmbeddingFunction(model_name=EMBEDDING_MODEL)
        print(f"  ✓ Dùng ChromaDB SentenceTransformerEmbeddingFunction: {EMBEDDING_MODEL}")
        return ef
    except Exception:
        pass

    # Option 2: sentence-transformers trực tiếp
    try:
        from sentence_transformers import SentenceTransformer

        class _STEmbeddingFunction:
            def __init__(self):
                self.model = SentenceTransformer(EMBEDDING_MODEL)
            def __call__(self, texts):
                return self.model.encode(texts).tolist()

        print(f"  ✓ Dùng SentenceTransformer trực tiếp: {EMBEDDING_MODEL}")
        return _STEmbeddingFunction()
    except Exception:
        pass

    # Option 3: Dummy embedding (fallback, chỉ để test)
    import hashlib
    import math

    class _DummyEmbeddingFunction:
        DIM = EMBEDDING_DIM
        def __call__(self, texts):
            results = []
            for t in texts:
                h = int(hashlib.md5(t.encode()).hexdigest(), 16)
                vec = [math.sin(h * (i + 1) * 0.01) for i in range(self.DIM)]
                norm = math.sqrt(sum(x * x for x in vec)) or 1
                results.append([x / norm for x in vec])
            return results

    print("  ⚠ Dùng dummy embedding (semantic search không chính xác, chỉ để test)")
    return _DummyEmbeddingFunction()


def embed_chunks(chunks: list[dict]) -> list[dict]:
    """
    Embed toàn bộ chunks.

    Returns:
        Mỗi chunk được thêm key 'embedding': list[float]
    """
    ef = _get_embedding_function()
    texts = [c["content"] for c in chunks]
    print(f"  Embedding {len(texts)} chunks...")
    batch_size = 32
    embeddings = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i:i + batch_size]
        embeddings.extend(ef(batch))
        print(f"  → {min(i + batch_size, len(texts))}/{len(texts)}", end="\r")
    print()
    for chunk, emb in zip(chunks, embeddings):
        chunk["embedding"] = emb
    return chunks


def index_to_vectorstore(chunks: list[dict]):
    """
    Lưu chunks vào ChromaDB persistent store.
    Dùng precomputed embeddings (không dùng chromadb built-in embedder).
    """
    import chromadb

    CHROMA_DIR.mkdir(parents=True, exist_ok=True)
    client = chromadb.PersistentClient(path=str(CHROMA_DIR))

    try:
        client.delete_collection(name=COLLECTION_NAME)
        print(f"  → Đã xóa collection cũ: {COLLECTION_NAME}")
    except Exception:
        pass

    collection = client.create_collection(
        name=COLLECTION_NAME,
        metadata={"hnsw:space": "cosine"},
    )

    batch_size = 100
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i + batch_size]
        collection.add(
            ids=[f"chunk_{i + j}" for j in range(len(batch))],
            embeddings=[c["embedding"] for c in batch],
            documents=[c["content"] for c in batch],
            metadatas=[{k: str(v) for k, v in c["metadata"].items()} for c in batch],
        )
    print(f"  ✓ Indexed {len(chunks)} chunks vào ChromaDB: {CHROMA_DIR}")


def save_chunks_json(chunks: list[dict]):
    """Lưu chunks (không có embedding) ra JSON cho BM25 dùng sau."""
    chunks_data = [
        {"content": c["content"], "metadata": c["metadata"]}
        for c in chunks
    ]
    CHUNKS_FILE.parent.mkdir(parents=True, exist_ok=True)
    CHUNKS_FILE.write_text(json.dumps(chunks_data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  ✓ Saved chunks.json: {len(chunks_data)} chunks → {CHUNKS_FILE}")


def run_pipeline():
    """Chạy toàn bộ pipeline: load → chunk → embed → index."""
    print("=" * 60)
    print("Task 4: Chunking & Indexing")
    print(f"  Chunking: {CHUNKING_METHOD} (size={CHUNK_SIZE}, overlap={CHUNK_OVERLAP})")
    print(f"  Embedding: {EMBEDDING_MODEL} (dim={EMBEDDING_DIM})")
    print(f"  Vector Store: ChromaDB")
    print("=" * 60)

    docs = load_documents()
    print(f"\n✓ Loaded {len(docs)} documents từ {STANDARDIZED_DIR}")

    if not docs:
        print("⚠ Không có documents! Chạy Task 1, 2, 3 trước.")
        return []

    chunks = chunk_documents(docs)
    print(f"✓ Created {len(chunks)} chunks")

    save_chunks_json(chunks)

    chunks = embed_chunks(chunks)
    print(f"✓ Embedded {len(chunks)} chunks")

    index_to_vectorstore(chunks)
    print("✓ Pipeline hoàn thành!")
    return chunks


if __name__ == "__main__":
    run_pipeline()
