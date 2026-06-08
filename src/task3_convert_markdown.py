"""
Task 3 — Convert toàn bộ file trong data/landing/ thành Markdown.

Sử dụng MarkItDown của Microsoft:
    https://github.com/microsoft/markitdown

Xử lý:
    - PDF/DOCX trong data/landing/legal/ → data/standardized/legal/
    - JSON trong data/landing/news/ → data/standardized/news/
"""

import json
from pathlib import Path

LANDING_DIR = Path(__file__).parent.parent / "data" / "landing"
OUTPUT_DIR = Path(__file__).parent.parent / "data" / "standardized"


def convert_legal_docs():
    """Convert PDF/DOCX files trong data/landing/legal/ sang markdown."""
    legal_dir = LANDING_DIR / "legal"
    output_dir = OUTPUT_DIR / "legal"
    output_dir.mkdir(parents=True, exist_ok=True)

    try:
        from markitdown import MarkItDown
        md = MarkItDown()
        use_markitdown = True
    except ImportError:
        print("  ⚠ markitdown chưa cài, fallback sang python-docx")
        use_markitdown = False

    converted = 0
    for filepath in legal_dir.iterdir():
        if not filepath.is_file():
            continue
        if filepath.suffix.lower() not in (".pdf", ".docx", ".doc"):
            continue

        output_path = output_dir / f"{filepath.stem}.md"
        if output_path.exists():
            print(f"  ↳ Đã tồn tại: {output_path.name}")
            converted += 1
            continue

        print(f"  Converting: {filepath.name}")
        try:
            if use_markitdown:
                result = md.convert(str(filepath))
                content = result.text_content
            else:
                content = _docx_to_markdown(filepath)

            output_path.write_text(content, encoding="utf-8")
            print(f"  ✓ Saved: {output_path.name} ({len(content):,} chars)")
            converted += 1
        except Exception as e:
            print(f"  ✗ Lỗi convert {filepath.name}: {e}")

    print(f"  → {converted} file legal đã convert")
    return converted


def _docx_to_markdown(filepath: Path) -> str:
    """Fallback: dùng python-docx để đọc DOCX và chuyển sang markdown đơn giản."""
    try:
        from docx import Document
        doc = Document(str(filepath))
        lines = []
        for para in doc.paragraphs:
            text = para.text.strip()
            if not text:
                lines.append("")
                continue
            style = para.style.name.lower()
            if "heading 1" in style:
                lines.append(f"# {text}")
            elif "heading 2" in style:
                lines.append(f"## {text}")
            elif "heading 3" in style:
                lines.append(f"### {text}")
            elif "title" in style:
                lines.append(f"# {text}")
            else:
                lines.append(text)
        return "\n\n".join(lines)
    except Exception as e:
        return f"# {filepath.stem}\n\n[Lỗi đọc file: {e}]"


def convert_news_articles():
    """Convert JSON crawled articles trong data/landing/news/ sang markdown."""
    news_dir = LANDING_DIR / "news"
    output_dir = OUTPUT_DIR / "news"
    output_dir.mkdir(parents=True, exist_ok=True)

    converted = 0
    for filepath in news_dir.iterdir():
        if not filepath.is_file() or filepath.name.startswith("."):
            continue

        output_path = output_dir / f"{filepath.stem}.md"
        if output_path.exists():
            print(f"  ↳ Đã tồn tại: {output_path.name}")
            converted += 1
            continue

        print(f"  Converting: {filepath.name}")
        try:
            if filepath.suffix.lower() == ".json":
                data = json.loads(filepath.read_text(encoding="utf-8"))
                title = data.get("title", "Unknown")
                url = data.get("url", "N/A")
                crawled = data.get("date_crawled", "N/A")
                body = data.get("content_markdown", "")

                header = f"# {title}\n\n"
                header += f"**Source:** {url}\n"
                header += f"**Crawled:** {crawled}\n\n---\n\n"
                content = header + body

            elif filepath.suffix.lower() in (".html", ".htm"):
                try:
                    from bs4 import BeautifulSoup
                    soup = BeautifulSoup(filepath.read_text(encoding="utf-8"), "html.parser")
                    content = soup.get_text(separator="\n")
                except ImportError:
                    content = filepath.read_text(encoding="utf-8")
            else:
                content = filepath.read_text(encoding="utf-8")

            output_path.write_text(content, encoding="utf-8")
            print(f"  ✓ Saved: {output_path.name} ({len(content):,} chars)")
            converted += 1
        except Exception as e:
            print(f"  ✗ Lỗi convert {filepath.name}: {e}")

    print(f"  → {converted} file news đã convert")
    return converted


def convert_all():
    """Convert toàn bộ files."""
    print("=" * 60)
    print("Task 3: Convert to Markdown (MarkItDown)")
    print("=" * 60)

    print("\n--- Legal Documents ---")
    n_legal = convert_legal_docs()

    print("\n--- News Articles ---")
    n_news = convert_news_articles()

    total = n_legal + n_news
    print(f"\n✓ Done! Tổng {total} files đã convert → {OUTPUT_DIR}")
    return total


if __name__ == "__main__":
    convert_all()
