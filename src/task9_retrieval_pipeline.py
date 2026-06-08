"""
Task 9 — Retrieval Pipeline Hoàn Chỉnh.

Pipeline:
    Query
      ├→ Semantic Search (Task 5) ─┐
      ├→ Lexical Search (Task 6)  ─┴→ RRF Merge → Rerank → Results
      │
      └→ Nếu best_score < threshold → Fallback: PageIndex (Task 8)

Merge strategy: Reciprocal Rank Fusion (RRF)
    - Không cần normalize scores từ các ranker khác nhau
    - Stable và hiệu quả, được dùng rộng rãi trong RAG production

Rerank: Cross-encoder keyword scoring (Task 7)
"""

from .task5_semantic_search import semantic_search
from .task6_lexical_search import lexical_search
from .task7_reranking import rerank, rerank_rrf
from .task8_pageindex_vectorless import pageindex_search

SCORE_THRESHOLD = 0.3
DEFAULT_TOP_K = 5
RERANK_METHOD = "cross_encoder"


def retrieve(
    query: str,
    top_k: int = DEFAULT_TOP_K,
    score_threshold: float = SCORE_THRESHOLD,
    use_reranking: bool = True,
) -> list[dict]:
    """
    Retrieval pipeline hoàn chỉnh với fallback logic.

    Args:
        query: Câu truy vấn
        top_k: Số lượng kết quả cuối cùng
        score_threshold: Ngưỡng điểm tối thiểu (nếu thấp hơn → fallback PageIndex)
        use_reranking: Có áp dụng reranking hay không

    Returns:
        List of {
            'content': str,
            'score': float,
            'metadata': dict,
            'source': 'hybrid' | 'pageindex'
        }
    """
    candidates_per_ranker = top_k * 2

    # Step 1: Song song chạy semantic + lexical search
    try:
        dense_results = semantic_search(query, top_k=candidates_per_ranker)
    except Exception as e:
        print(f"  ⚠ Semantic search lỗi: {e}")
        dense_results = []

    try:
        sparse_results = lexical_search(query, top_k=candidates_per_ranker)
    except Exception as e:
        print(f"  ⚠ Lexical search lỗi: {e}")
        sparse_results = []

    # Step 2: Merge bằng RRF
    if dense_results or sparse_results:
        ranked_lists = [lst for lst in [dense_results, sparse_results] if lst]
        merged = rerank_rrf(ranked_lists, top_k=candidates_per_ranker)
        for item in merged:
            item["source"] = "hybrid"
    else:
        merged = []

    # Step 3: Rerank nếu có kết quả
    if use_reranking and merged:
        final_results = rerank(query, merged, top_k=top_k, method=RERANK_METHOD)
    else:
        final_results = merged[:top_k]

    # Step 4: Check threshold → fallback PageIndex
    best_score = final_results[0]["score"] if final_results else 0.0
    if not final_results or best_score < score_threshold:
        print(f"  ⚠ Hybrid score ({best_score:.3f}) < threshold ({score_threshold}). "
              f"Fallback → PageIndex")
        try:
            fallback = pageindex_search(query, top_k=top_k)
            return fallback if fallback else final_results
        except Exception as e:
            print(f"  ✗ PageIndex fallback lỗi: {e}")
            return final_results

    return final_results[:top_k]


if __name__ == "__main__":
    test_queries = [
        "Hình phạt cho tội tàng trữ trái phép chất ma tuý",
        "Nghệ sĩ nào bị bắt vì sử dụng ma tuý năm 2024",
        "Luật phòng chống ma tuý 2021 quy định gì về cai nghiện",
    ]

    for q in test_queries:
        print(f"\nQuery: {q}")
        print("-" * 60)
        results = retrieve(q, top_k=3)
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r['score']:.3f}] [{r['source']}] {r['content'][:80]}...")
