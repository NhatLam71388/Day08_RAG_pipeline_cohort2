"""
Task 8 — PageIndex Vectorless RAG.

PageIndex (https://pageindex.ai/) là giải pháp RAG không cần vector store.
Thay vì embedding, nó hiểu cấu trúc tài liệu (heading, section, table)
và tìm kiếm dựa trên structural understanding.

Ưu điểm so với vector RAG:
    - Không cần embedding computation
    - Tìm kiếm chính xác hơn cho tài liệu có cấu trúc (pháp luật, báo cáo)
    - Không mất ngữ cảnh do chunking

Cài đặt:
    pip install pageindex

Nếu không có PAGEINDEX_API_KEY: module trả về kết quả fallback từ BM25.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

PAGEINDEX_API_KEY = os.getenv("PAGEINDEX_API_KEY", "")
STANDARDIZED_DIR = Path(__file__).parent.parent / "data" / "standardized"


def upload_documents():
    """Upload toàn bộ markdown documents lên PageIndex."""
    if not PAGEINDEX_API_KEY:
        print("⚠ PAGEINDEX_API_KEY chưa được set. Bỏ qua upload.")
        return

    try:
        from pageindex import PageIndex
        pi = PageIndex(api_key=PAGEINDEX_API_KEY)

        for md_file in STANDARDIZED_DIR.rglob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            pi.upload(
                content=content,
                metadata={
                    "filename": md_file.name,
                    "type": md_file.parent.name,
                }
            )
            print(f"  ✓ Uploaded: {md_file.name}")
    except ImportError:
        print("  ⚠ pageindex chưa được cài: pip install pageindex")
    except Exception as e:
        print(f"  ✗ Lỗi upload: {e}")


def _pageindex_api_search(query: str, top_k: int) -> list[dict]:
    """Gọi PageIndex API nếu có API key."""
    from pageindex import PageIndex
    pi = PageIndex(api_key=PAGEINDEX_API_KEY)
    results = pi.query(query=query, top_k=top_k)
    return [
        {
            "content": r.text if hasattr(r, "text") else str(r),
            "score": float(r.score) if hasattr(r, "score") else 0.5,
            "metadata": r.metadata if hasattr(r, "metadata") else {},
            "source": "pageindex",
        }
        for r in results
    ]


def _bm25_fallback_search(query: str, top_k: int) -> list[dict]:
    """
    Fallback khi không có PageIndex API key.
    Dùng BM25 trên standardized markdown files để mô phỏng vectorless search.
    """
    from rank_bm25 import BM25Okapi

    docs = []
    for md_file in STANDARDIZED_DIR.rglob("*.md"):
        try:
            content = md_file.read_text(encoding="utf-8")
            if content.strip():
                docs.append({
                    "content": content,
                    "metadata": {
                        "filename": md_file.name,
                        "type": md_file.parent.name,
                    }
                })
        except Exception:
            continue

    if not docs:
        return []

    tokenized = [d["content"].lower().split() for d in docs]
    bm25 = BM25Okapi(tokenized)

    import numpy as np
    scores = bm25.get_scores(query.lower().split())
    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        if scores[idx] > 0:
            # Trả về excerpt (500 ký tự) thay vì full document
            content = docs[idx]["content"]
            results.append({
                "content": content[:500].strip() + "..." if len(content) > 500 else content,
                "score": float(scores[idx]),
                "metadata": docs[idx]["metadata"],
                "source": "pageindex",
            })

    return results


def pageindex_search(query: str, top_k: int = 5) -> list[dict]:
    """
    Vectorless retrieval sử dụng PageIndex.
    Fallback sang BM25 nếu không có API key.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,
            'metadata': dict,
            'source': 'pageindex'
        }
    """
    if PAGEINDEX_API_KEY:
        try:
            return _pageindex_api_search(query, top_k)
        except ImportError:
            print("  ⚠ pageindex chưa cài, dùng BM25 fallback")
        except Exception as e:
            print(f"  ⚠ PageIndex API lỗi: {e}, dùng BM25 fallback")

    return _bm25_fallback_search(query, top_k)


if __name__ == "__main__":
    if PAGEINDEX_API_KEY:
        print("Uploading documents to PageIndex...")
        upload_documents()
    else:
        print("ℹ PAGEINDEX_API_KEY chưa set → dùng BM25 fallback")

    print("\nTest pageindex_search:")
    results = pageindex_search("hình phạt sử dụng ma tuý", top_k=3)
    for r in results:
        print(f"[{r['score']:.3f}] [{r['source']}] {r['content'][:100]}...")
