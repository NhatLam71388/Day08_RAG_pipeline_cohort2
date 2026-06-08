"""
DrugLaw RAG Chatbot — Streamlit UI
Bài nhóm Day 8 RAG Pipeline v2

Tính năng:
    - Chat interface trả lời câu hỏi về pháp luật ma tuý và tin tức nghệ sĩ
    - Câu trả lời có citation [Nguồn, Năm]
    - Conversation memory (lưu lịch sử chat trong session)
    - Hiển thị source documents đã dùng
    - So sánh kết quả Hybrid vs Dense-only

Chạy:
    streamlit run app.py
"""

import streamlit as st
import sys
from pathlib import Path

# Thêm project root vào path
sys.path.insert(0, str(Path(__file__).parent))

st.set_page_config(
    page_title="DrugLaw RAG Chatbot",
    page_icon="⚖️",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ============================================================================
# CSS tùy chỉnh
# ============================================================================

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"], .stApp {
        font-family: 'Inter', sans-serif !important;
    }
    
    .main-header {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 6px solid #2563eb;
        padding: 24px;
        border-radius: 12px;
        margin-bottom: 24px;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.05), 0 2px 4px -2px rgba(0, 0, 0, 0.05);
    }
    .main-header h1 {
        color: #0f172a !important;
        font-size: 2.2rem !important;
        font-weight: 700 !important;
        margin: 0 0 8px 0 !important;
    }
    .main-header p {
        color: #475569 !important;
        font-size: 1rem !important;
        margin: 0 !important;
    }
    .source-card {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        border-left: 4px solid #2563eb;
        padding: 12px;
        margin: 8px 0;
        border-radius: 8px;
        font-size: 0.85em;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
        transition: transform 0.2s, box-shadow 0.2s;
    }
    .source-card:hover {
        transform: translateY(-1px);
        box-shadow: 0 4px 8px -2px rgba(0, 0, 0, 0.1);
    }
    .legal-badge {
        background: #dbeafe;
        color: #1e40af;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75em;
        font-weight: 600;
        border: 1px solid #bfdbfe;
        display: inline-block;
        margin-bottom: 6px;
    }
    .news-badge {
        background: #fef3c7;
        color: #92400e;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75em;
        font-weight: 600;
        border: 1px solid #fde68a;
        display: inline-block;
        margin-bottom: 6px;
    }
    .metric-box {
        background: #ffffff;
        border: 1px solid #e2e8f0;
        padding: 14px;
        border-radius: 10px;
        text-align: center;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05);
    }
    .retrieval-info {
        background: #f8fafc;
        border: 1px solid #e2e8f0;
        border-radius: 8px;
        padding: 10px 14px;
        font-size: 0.8em;
        color: #475569;
        margin-top: 10px;
        box-shadow: 0 1px 2px 0 rgba(0, 0, 0, 0.02);
    }
</style>
""", unsafe_allow_html=True)

# ============================================================================
# Session state khởi tạo
# ============================================================================

if "messages" not in st.session_state:
    st.session_state.messages = []

if "last_sources" not in st.session_state:
    st.session_state.last_sources = []

if "search_mode" not in st.session_state:
    st.session_state.search_mode = "hybrid"

if "pipeline_ready" not in st.session_state:
    st.session_state.pipeline_ready = False

# ============================================================================
# Load pipeline (cached)
# ============================================================================

@st.cache_resource(show_spinner="Đang tải RAG pipeline...")
def load_pipeline():
    """Load RAG pipeline một lần duy nhất."""
    try:
        from src.task9_retrieval_pipeline import retrieve
        from src.task10_generation import generate_with_citation, format_context, reorder_for_llm
        return {
            "retrieve": retrieve,
            "generate": generate_with_citation,
            "format_context": format_context,
            "reorder": reorder_for_llm,
            "status": "ok"
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


def generate_response_with_history(query: str, history: list[dict], pipeline: dict, top_k: int = 5) -> dict:
    """
    Generate câu trả lời có xét đến lịch sử hội thoại.

    Conversation memory: inject N lượt gần nhất vào prompt.
    """
    import os
    from src.task9_retrieval_pipeline import retrieve
    from src.task10_generation import (
        SYSTEM_PROMPT, TEMPERATURE, TOP_P,
        reorder_for_llm, format_context, _call_llm
    )

    # Retrieve
    chunks = retrieve(query, top_k=top_k)
    retrieval_source = chunks[0].get("source", "hybrid") if chunks else "none"

    # Reorder để tránh lost in the middle
    reordered = reorder_for_llm(chunks)
    context = format_context(reordered)

    # Xây dựng conversation history (tối đa 3 lượt gần nhất)
    history_text = ""
    if history:
        recent = history[-6:]  # 3 pairs = 6 messages
        history_parts = []
        for msg in recent:
            role = "Người dùng" if msg["role"] == "user" else "Trợ lý"
            history_parts.append(f"{role}: {msg['content'][:300]}")
        history_text = "\n".join(history_parts)

    # Build prompt với history
    user_message = ""
    if history_text:
        user_message += f"Lịch sử hội thoại gần nhất:\n{history_text}\n\n---\n\n"
    user_message += f"Context (tài liệu tham khảo):\n\n{context}\n\n---\n\nCâu hỏi hiện tại: {query}"

    answer = _call_llm(SYSTEM_PROMPT, user_message)

    return {
        "answer": answer,
        "sources": chunks,
        "retrieval_source": retrieval_source,
    }


# ============================================================================
# Sidebar
# ============================================================================

with st.sidebar:
    st.markdown("## ⚙️ Cấu hình")

    search_mode = st.selectbox(
        "Chế độ tìm kiếm",
        options=["hybrid", "dense_only"],
        format_func=lambda x: "🔀 Hybrid (BM25 + Semantic)" if x == "hybrid" else "🧠 Dense-only (Semantic)",
        index=0,
    )
    st.session_state.search_mode = search_mode

    top_k = st.slider("Số chunks context", min_value=3, max_value=10, value=5)

    st.markdown("---")
    st.markdown("### 📊 Thống kê phiên")
    n_turns = len([m for m in st.session_state.messages if m["role"] == "user"])
    st.metric("Số lượt hỏi", n_turns)

    if st.button("🗑️ Xóa lịch sử chat", use_container_width=True):
        st.session_state.messages = []
        st.session_state.last_sources = []
        st.rerun()

    st.markdown("---")
    st.markdown("### 📚 Nguồn tài liệu")
    st.markdown("""
    **Pháp luật:**
    - Luật PCMT 2021 (73/2021/QH15)
    - Nghị định 105/2021/NĐ-CP
    - BLHS 2015 Chương XX

    **Báo chí:**
    - VnExpress, Tuổi Trẻ, Thanh Niên
    - Dân Trí, VietnamNet
    """)

    st.markdown("---")
    st.markdown("### 🔍 Nguồn tài liệu lần hỏi gần nhất")
    if st.session_state.last_sources:
        for i, src in enumerate(st.session_state.last_sources[:5], 1):
            meta = src.get("metadata", {})
            source_name = meta.get("source", f"Source {i}")
            doc_type = meta.get("type", "unknown")
            score = src.get("score", 0)
            badge = "legal-badge" if doc_type == "legal" else "news-badge"
            label = "Pháp luật" if doc_type == "legal" else "Báo chí"
            st.markdown(f"""
            <div class="source-card">
                <span class="{badge}">{label}</span>
                <b>{source_name}</b><br>
                Score: {score:.3f}
            </div>
            """, unsafe_allow_html=True)
    else:
        st.info("Chưa có câu hỏi nào")

# ============================================================================
# Header
# ============================================================================

st.markdown("""
<div class="main-header">
    <h1>⚖️ DrugLaw RAG Chatbot</h1>
    <p>Hỏi đáp về <b>pháp luật phòng chống ma tuý Việt Nam</b> và <b>tin tức nghệ sĩ liên quan</b></p>
</div>
""", unsafe_allow_html=True)

# ============================================================================
# Load pipeline
# ============================================================================

pipeline = load_pipeline()

if pipeline.get("status") == "error":
    st.error(f"❌ Lỗi tải pipeline: {pipeline.get('error')}")
    st.info("Đảm bảo đã chạy Task 4 (chunking & indexing) trước khi dùng chatbot.")
    st.stop()

# ============================================================================
# Gợi ý câu hỏi
# ============================================================================

if not st.session_state.messages:
    st.markdown("### 💡 Gợi ý câu hỏi")
    col1, col2, col3 = st.columns(3)

    sample_questions = [
        "Hình phạt tội tàng trữ ma tuý theo Điều 249 là gì?",
        "Thời gian cai nghiện bắt buộc theo Luật PCMT 2021?",
        "Tội mua bán ma tuý bị xử lý như thế nào?",
        "Châu Việt Cường bị bắt vì ma tuý năm nào?",
        "Nghệ sĩ vi phạm ma tuý bị xử lý pháp lý như thế nào?",
        "Bộ VHTTDL xử lý nghệ sĩ vi phạm ma tuý ra sao?",
    ]

    for i, (col, q) in enumerate(zip([col1, col2, col3, col1, col2, col3], sample_questions)):
        with col:
            if st.button(q, key=f"sample_{i}", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": q})
                st.rerun()

    st.markdown("---")

# ============================================================================
# Hiển thị lịch sử chat
# ============================================================================

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])
        if msg["role"] == "assistant" and "retrieval_info" in msg:
            info = msg["retrieval_info"]
            st.markdown(f"""
            <div class="retrieval-info">
                🔍 <b>Nguồn:</b> {info.get('retrieval_source', 'hybrid')} |
                📄 <b>Số chunks:</b> {info.get('n_sources', 0)} |
                ⚙️ <b>Mode:</b> {info.get('search_mode', 'hybrid')}
            </div>
            """, unsafe_allow_html=True)

# ============================================================================
# Chat input
# ============================================================================

if prompt := st.chat_input("Nhập câu hỏi về pháp luật ma tuý hoặc tin tức nghệ sĩ..."):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    with st.chat_message("assistant"):
        with st.spinner("Đang tìm kiếm và tổng hợp thông tin..."):
            # Lấy lịch sử để truyền vào LLM (conversation memory)
            history = st.session_state.messages[:-1]  # Không tính câu hỏi hiện tại

            try:
                result = generate_response_with_history(
                    query=prompt,
                    history=history,
                    pipeline=pipeline,
                    top_k=top_k,
                )
                answer = result["answer"]
                sources = result["sources"]
                retrieval_source = result["retrieval_source"]
            except Exception as e:
                answer = f"Xảy ra lỗi khi xử lý câu hỏi: {str(e)}"
                sources = []
                retrieval_source = "error"

        st.markdown(answer)

        retrieval_info = {
            "retrieval_source": retrieval_source,
            "n_sources": len(sources),
            "search_mode": st.session_state.search_mode,
        }
        st.markdown(f"""
        <div class="retrieval-info">
            🔍 <b>Nguồn:</b> {retrieval_source} |
            📄 <b>Số chunks:</b> {len(sources)} |
            ⚙️ <b>Mode:</b> {st.session_state.search_mode}
        </div>
        """, unsafe_allow_html=True)

        # Hiển thị source expander
        if sources:
            with st.expander(f"📚 Xem {len(sources)} nguồn tài liệu đã dùng"):
                for i, src in enumerate(sources[:5], 1):
                    meta = src.get("metadata", {})
                    source_name = meta.get("source", f"Source {i}")
                    doc_type = meta.get("type", "unknown")
                    score = src.get("score", 0)
                    label = "⚖️ Pháp luật" if doc_type == "legal" else "📰 Báo chí"
                    st.markdown(f"**{i}. {label} | {source_name}** (score: {score:.3f})")
                    st.markdown(f"> {src['content'][:300]}...")
                    st.markdown("---")

    # Lưu vào session state
    st.session_state.messages.append({
        "role": "assistant",
        "content": answer,
        "retrieval_info": retrieval_info,
    })
    st.session_state.last_sources = sources

# ============================================================================
# Footer
# ============================================================================

st.markdown("---")
st.markdown(
    "<small>⚖️ DrugLaw RAG Chatbot | Day 8 RAG Pipeline v2 | "
    "Dữ liệu: Luật PCMT 2021, BLHS 2015, Báo chí VN</small>",
    unsafe_allow_html=True,
)
