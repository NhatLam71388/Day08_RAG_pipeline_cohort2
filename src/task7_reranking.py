"""
Task 7 — Reranking Module.

Implement 3 phương pháp reranking:

1. rerank_rrf (Reciprocal Rank Fusion) — MẶC ĐỊNH
   - Gộp kết quả từ nhiều ranked list
   - RRF(d) = Σ 1/(k + rank_r(d))
   - k=60 (từ paper Cormack et al. 2009)
   - Không cần model hay API, nhẹ và hiệu quả

2. rerank_cross_encoder — Local keyword-based scoring
   - Tính điểm dựa trên tỉ lệ từ khóa query khớp trong document
   - Không cần API, hoạt động offline

3. rerank_mmr (Maximal Marginal Relevance) — Tăng diversity
   - Cân bằng giữa relevance và diversity
   - MMR = λ * sim(q,d) - (1-λ) * max_sim(d, selected)
"""

import math
from typing import Optional


def rerank_cross_encoder(
    query: str, candidates: list[dict], top_k: int = 5
) -> list[dict]:
    """
    Rerank bằng keyword overlap scoring (không cần API).

    Tính điểm theo: |terms(query) ∩ terms(doc)| / |terms(query)|
    Kết hợp với điểm retrieval ban đầu để re-rank.
    """
    query_terms = set(query.lower().split())
    if not query_terms:
        return candidates[:top_k]

    results = []
    for c in candidates:
        content_terms = set(c["content"].lower().split())
        overlap = len(query_terms & content_terms)
        keyword_score = overlap / len(query_terms)

        # Kết hợp keyword score với retrieval score ban đầu
        orig_score = c.get("score", 0.0)
        combined = 0.6 * keyword_score + 0.4 * orig_score

        results.append({**c, "score": round(combined, 4)})

    return sorted(results, key=lambda x: x["score"], reverse=True)[:top_k]


def rerank_mmr(
    query_embedding: list[float],
    candidates: list[dict],
    top_k: int = 5,
    lambda_param: float = 0.7,
) -> list[dict]:
    """
    Maximal Marginal Relevance — chọn vừa relevant vừa diverse.

    MMR = λ * sim(query, doc) - (1-λ) * max(sim(doc, selected_docs))

    Args:
        query_embedding: Vector embedding của query (list[float])
        candidates: List of {'content': str, 'score': float, 'embedding': list, 'metadata': dict}
        top_k: Số lượng kết quả
        lambda_param: 1.0 = pure relevance, 0.0 = pure diversity
    """
    import numpy as np

    def cosine_sim(a, b):
        a, b = np.array(a), np.array(b)
        denom = np.linalg.norm(a) * np.linalg.norm(b)
        return float(np.dot(a, b) / denom) if denom > 0 else 0.0

    # Nếu candidates không có embedding, fallback về cross_encoder
    if not candidates or "embedding" not in candidates[0]:
        return rerank_cross_encoder("", candidates, top_k)

    selected_indices = []
    remaining = list(range(len(candidates)))

    for _ in range(min(top_k, len(candidates))):
        best_idx = None
        best_score = float("-inf")

        for idx in remaining:
            relevance = cosine_sim(query_embedding, candidates[idx]["embedding"])
            max_sim_to_selected = max(
                (cosine_sim(candidates[idx]["embedding"], candidates[s]["embedding"])
                 for s in selected_indices),
                default=0.0,
            )
            mmr_score = lambda_param * relevance - (1 - lambda_param) * max_sim_to_selected

            if mmr_score > best_score:
                best_score = mmr_score
                best_idx = idx

        if best_idx is not None:
            selected_indices.append(best_idx)
            remaining.remove(best_idx)

    return [
        {**candidates[i], "score": round(1.0 - (rank / len(selected_indices)), 4)}
        for rank, i in enumerate(selected_indices)
    ]


def rerank_rrf(
    ranked_lists: list[list[dict]], top_k: int = 5, k: int = 60
) -> list[dict]:
    """
    Reciprocal Rank Fusion — gộp kết quả từ nhiều ranker.

    RRF(d) = Σ 1 / (k + rank_r(d))

    Đây là phương pháp lý tưởng để merge dense + sparse search.
    Không cần re-embed hay gọi model, rất nhanh và hiệu quả.

    Args:
        ranked_lists: List of ranked result lists (mỗi list từ 1 ranker)
        top_k: Số lượng kết quả cuối cùng
        k: Smoothing constant (default=60)
    """
    rrf_scores: dict[str, float] = {}
    content_map: dict[str, dict] = {}

    for ranked_list in ranked_lists:
        for rank, item in enumerate(ranked_list, 1):
            key = item["content"]
            rrf_scores[key] = rrf_scores.get(key, 0.0) + 1.0 / (k + rank)
            if key not in content_map:
                content_map[key] = item

    sorted_items = sorted(rrf_scores.items(), key=lambda x: x[1], reverse=True)

    results = []
    for content, score in sorted_items[:top_k]:
        item = content_map[content].copy()
        item["score"] = round(score, 6)
        results.append(item)

    return results


def rerank(
    query: str,
    candidates: list[dict],
    top_k: int = 5,
    method: str = "cross_encoder",
) -> list[dict]:
    """
    Unified reranking interface.

    Args:
        query: Câu truy vấn
        candidates: Danh sách candidates từ retrieval
        top_k: Số kết quả sau rerank
        method: "cross_encoder" | "mmr" | "rrf"
    """
    if method == "cross_encoder":
        return rerank_cross_encoder(query, candidates, top_k)
    elif method == "mmr":
        # MMR cần query_embedding — gọi riêng rerank_mmr nếu cần
        return rerank_cross_encoder(query, candidates, top_k)
    elif method == "rrf":
        # RRF cần nhiều ranked lists — dùng cross_encoder khi chỉ có 1 list
        return rerank_cross_encoder(query, candidates, top_k)
    else:
        raise ValueError(f"Unknown rerank method: {method}")


if __name__ == "__main__":
    # Test RRF
    list1 = [
        {"content": "Điều 248: Tội tàng trữ trái phép chất ma tuý", "score": 0.8, "metadata": {}},
        {"content": "Hình phạt tù từ 2-7 năm cho tội tàng trữ", "score": 0.6, "metadata": {}},
        {"content": "Nghệ sĩ X bị bắt vì sử dụng ma tuý", "score": 0.5, "metadata": {}},
    ]
    list2 = [
        {"content": "Hình phạt tù từ 2-7 năm cho tội tàng trữ", "score": 0.9, "metadata": {}},
        {"content": "Điều 248: Tội tàng trữ trái phép chất ma tuý", "score": 0.7, "metadata": {}},
        {"content": "Ma tuý và hậu quả pháp lý", "score": 0.4, "metadata": {}},
    ]

    print("=== RRF Merge ===")
    rrf_results = rerank_rrf([list1, list2], top_k=3)
    for r in rrf_results:
        print(f"[RRF={r['score']:.4f}] {r['content'][:60]}")

    print("\n=== Cross-encoder Rerank ===")
    ce_results = rerank("hình phạt tàng trữ ma tuý", list1, top_k=2)
    for r in ce_results:
        print(f"[CE={r['score']:.4f}] {r['content'][:60]}")
