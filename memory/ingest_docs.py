"""Index documents: Markdown/text/HTML by line range, PDFs by page.

Usage: python -m memory.ingest_docs path/to/docs [more paths] [--reset]
PDF support needs: pip install -e ".[docs]"
"""

import html
import re
from pathlib import Path

from memory.chunking import chunk_lines, chunk_pages, chunk_paragraphs
from memory.common import read_text, run_cli

DOC_EXTS = {".md", ".markdown", ".txt", ".rst", ".html", ".htm", ".pdf", ".csv"}


def html_to_text(raw: str) -> str:
    raw = re.sub(r"(?is)<(script|style).*?</\1>", "", raw)
    raw = re.sub(r"(?i)<br\s*/?>|</(p|div|li|h[1-6]|tr)>", "\n", raw)
    return html.unescape(re.sub(r"<[^>]+>", "", raw))


def to_chunks(path: Path, source: str):
    ext = path.suffix.lower()
    if ext == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as e:
            raise RuntimeError('pypdf not installed: pip install -e ".[docs]"') from e
        pages = [p.extract_text() or "" for p in PdfReader(path).pages]
        return chunk_pages(pages, source)
    text = read_text(path)
    if ext == ".csv":  # no paragraph breaks: window by rows instead
        return chunk_lines(text, source, "doc", max_lines=40, overlap=0, format="csv")
    if ext in {".html", ".htm"}:
        text = html_to_text(text)
    return chunk_paragraphs(text, source, "doc", max_chars=1200, format=ext.lstrip("."))


if __name__ == "__main__":
    run_cli(__doc__, DOC_EXTS, to_chunks)
