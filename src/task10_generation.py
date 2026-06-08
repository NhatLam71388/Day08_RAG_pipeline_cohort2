"""
Task 10 — Generation Có Citation.

Pipeline:
    1. Retrieve context chunks (Task 9)
    2. Reorder chunks — tránh "lost in the middle" (Liu et al., 2023)
    3. Format context với source labels
    4. Inject vào prompt với SYSTEM_PROMPT
    5. Gọi LLM (Claude hoặc OpenAI)
    6. Return answer có citation

Tham số LLM:
    - top_k=5: đủ ngữ cảnh, không quá dài gây lost in the middle
    - top_p=0.9: nucleus sampling, đủ diverse nhưng không random quá
    - temperature=0.3: RAG cần factual, ít sáng tạo → temperature thấp
"""

import os
from dotenv import load_dotenv

load_dotenv()

from .task9_retrieval_pipeline import retrieve

TOP_K = 5
TOP_P = 0.9
TEMPERATURE = 0.3

SYSTEM_PROMPT = """Bạn là trợ lý pháp lý chuyên về pháp luật phòng chống ma tuý Việt Nam.
Hãy trả lời câu hỏi một cách toàn diện bằng tiếng Việt dựa trên context được cung cấp.

NGUYÊN TẮC:
1. Mỗi thông tin pháp lý/sự kiện PHẢI có citation ngay sau dạng [Nguồn, Năm]
   Ví dụ: [Bộ luật Hình sự 2015, Điều 249] hoặc [VnExpress, 2024]
2. Chỉ dùng thông tin từ context được cung cấp
3. Nếu context không đủ bằng chứng → trả lời: "Tôi không thể xác minh thông tin này từ nguồn hiện có"
4. Cấu trúc câu trả lời rõ ràng, có đoạn văn"""


def reorder_for_llm(chunks: list[dict]) -> list[dict]:
    """
    Sắp xếp chunks để tránh "lost in the middle" effect (Liu et al., 2023).

    LLM nhớ tốt nhất thông tin ở ĐẦU và CUỐI context.
    Strategy: đặt chunks quan trọng nhất ở đầu và cuối, kém nhất ở giữa.

    Input (sorted by score desc): [rank1, rank2, rank3, rank4, rank5]
    Output:                       [rank1, rank3, rank5, rank4, rank2]
    (Best first, worst middle, second-best last)
    """
    if len(chunks) <= 2:
        return chunks

    # Tách thành odd indices (đưa ra đầu) và even indices (đưa ra cuối, đảo ngược)
    odd_items = [chunks[i] for i in range(0, len(chunks), 2)]   # index 0,2,4,...
    even_items = [chunks[i] for i in range(1, len(chunks), 2)]  # index 1,3,5,...
    even_items.reverse()  # Đảo để item quan trọng hơn ở cuối

    return odd_items + even_items


def format_context(chunks: list[dict]) -> str:
    """
    Format chunks thành context string với source labels rõ ràng để LLM có thể cite.
    """
    parts = []
    for i, chunk in enumerate(chunks, 1):
        meta = chunk.get("metadata", {})
        source = meta.get("source", f"Source {i}")
        doc_type = meta.get("type", "unknown")
        type_label = "Pháp luật" if doc_type == "legal" else "Báo chí"
        parts.append(
            f"[Document {i} | {type_label} | {source}]\n{chunk['content']}"
        )
    return "\n\n---\n\n".join(parts)


def _call_llm_openai(system_prompt: str, user_message: str) -> str:
    """Gọi OpenAI API."""
    from openai import OpenAI
    client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
    response = client.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ],
        temperature=TEMPERATURE,
        top_p=TOP_P,
        max_tokens=1024,
    )
    return response.choices[0].message.content


def _call_llm_claude(system_prompt: str, user_message: str) -> str:
    """Gọi Claude API (Anthropic)."""
    import anthropic
    client = anthropic.Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
    response = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=1024,
        temperature=TEMPERATURE,
        system=system_prompt,
        messages=[{"role": "user", "content": user_message}],
    )
    return response.content[0].text


def _call_llm(system_prompt: str, user_message: str) -> str:
    """Gọi LLM — ưu tiên Claude, fallback OpenAI, fallback mock."""
    if os.getenv("ANTHROPIC_API_KEY"):
        try:
            return _call_llm_claude(system_prompt, user_message)
        except Exception as e:
            print(f"  ⚠ Claude API lỗi: {e}")

    if os.getenv("OPENAI_API_KEY"):
        try:
            return _call_llm_openai(system_prompt, user_message)
        except Exception as e:
            print(f"  ⚠ OpenAI API lỗi: {e}")

    # Mock response cho testing
    return (
        "Tôi không thể xác minh thông tin này từ nguồn hiện có "
        "(API key chưa được cấu hình trong .env)."
    )


def generate_with_citation(query: str, top_k: int = TOP_K) -> dict:
    """
    End-to-end RAG generation có citation.

    Args:
        query: Câu hỏi của user
        top_k: Số chunks đưa vào context

    Returns:
        {
            'answer': str,           # Câu trả lời có citation
            'sources': list[dict],   # Các chunks đã dùng
            'retrieval_source': str  # 'hybrid' hoặc 'pageindex'
        }
    """
    # Step 1: Retrieve
    chunks = retrieve(query, top_k=top_k)

    retrieval_source = "none"
    if chunks:
        retrieval_source = chunks[0].get("source", "hybrid")

    # Step 2: Reorder để tránh lost in the middle
    reordered = reorder_for_llm(chunks)

    # Step 3: Format context
    context = format_context(reordered)

    if not context.strip():
        return {
            "answer": "Tôi không thể xác minh thông tin này từ nguồn hiện có (không tìm được context liên quan).",
            "sources": [],
            "retrieval_source": "none",
        }

    # Step 4: Build prompt
    user_message = f"Context:\n\n{context}\n\n---\n\nCâu hỏi: {query}"

    # Step 5: Gọi LLM
    answer = _call_llm(SYSTEM_PROMPT, user_message)

    return {
        "answer": answer,
        "sources": chunks,
        "retrieval_source": retrieval_source,
    }


if __name__ == "__main__":
    test_queries = [
        "Hình phạt cho tội tàng trữ trái phép chất ma tuý theo pháp luật Việt Nam?",
        "Những nghệ sĩ nào đã bị bắt vì liên quan tới ma tuý?",
    ]

    for q in test_queries:
        print(f"\n{'='*70}")
        print(f"Q: {q}")
        print("=" * 70)
        result = generate_with_citation(q)
        print(f"\nA: {result['answer']}")
        print(f"\n[Sources: {len(result['sources'])} chunks | via {result['retrieval_source']}]")
