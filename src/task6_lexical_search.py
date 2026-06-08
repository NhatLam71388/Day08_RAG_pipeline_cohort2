"""
Task 6 — Lexical Search Module (BM25).

Sử dụng BM25Okapi từ rank-bm25.

BM25 hoạt động:
    - TF (Term Frequency): từ xuất hiện nhiều → điểm cao hơn, nhưng có saturation
    - IDF (Inverse Document Frequency): từ hiếm qua nhiều document → quan trọng hơn
    - Length normalization: chuẩn hoá theo độ dài document để không ưu tiên doc dài
    - Formula: score(q,d) = Σ IDF(qi) * tf(qi,d)*(k1+1) / (tf(qi,d) + k1*(1-b+b*|d|/avgdl))
    - k1=1.5 (term saturation), b=0.75 (length normalization) - giá trị chuẩn

Corpus được load từ data/chunks.json (tạo bởi Task 4).

Bonus: Giải thích BM25 trong demo → +5 điểm
"""

import json
from pathlib import Path

CHUNKS_FILE = Path(__file__).parent.parent / "data" / "chunks.json"

_corpus: list[dict] = []
_bm25 = None


def _load_corpus() -> list[dict]:
    """Load corpus từ chunks.json."""
    global _corpus
    if _corpus:
        return _corpus
    if CHUNKS_FILE.exists():
        data = json.loads(CHUNKS_FILE.read_text(encoding="utf-8"))
        _corpus = data
        print(f"  ✓ BM25 corpus loaded: {len(_corpus)} chunks")
    else:
        print("  ⚠ chunks.json chưa tồn tại. Chạy Task 4 trước.")
        _corpus = []
    return _corpus


def build_bm25_index(corpus: list[dict] | None = None):
    """
    Xây dựng BM25Okapi index từ corpus.

    Tokenize đơn giản bằng split() — đủ dùng cho tiếng Việt trong context học tập.
    Production nên dùng underthesea hoặc pyvi để tách từ tiếng Việt.
    """
    from rank_bm25 import BM25Okapi

    if corpus is None:
        corpus = _load_corpus()

    tokenized = [doc["content"].lower().split() for doc in corpus]
    return BM25Okapi(tokenized)


def _get_bm25():
    """Lazy-load BM25 index."""
    global _bm25, _corpus
    if _bm25 is None:
        _load_corpus()
        if _corpus:
            _bm25 = build_bm25_index(_corpus)
    return _bm25


def lexical_search(query: str, top_k: int = 10) -> list[dict]:
    """
    Tìm kiếm từ khóa sử dụng BM25Okapi.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả tối đa

    Returns:
        List of {
            'content': str,
            'score': float,   # BM25 score
            'metadata': dict
        }
        Sorted by score descending.
    """
    import numpy as np

    corpus = _load_corpus()
    if not corpus:
        return []

    bm25 = _get_bm25()
    tokenized_query = query.lower().split()
    scores = bm25.get_scores(tokenized_query)

    top_indices = np.argsort(scores)[::-1][:top_k]

    results = []
    for idx in top_indices:
        score = float(scores[idx])
        if score > 0:
            results.append({
                "content": corpus[idx]["content"],
                "score": score,
                "metadata": corpus[idx]["metadata"],
            })

    # Đã sorted descending by score
    return results


if __name__ == "__main__":
    results = lexical_search("Điều 248 tàng trữ trái phép chất ma tuý", top_k=5)
    for r in results:
        print(f"[{r['score']:.3f}] {r['content'][:100]}...")
