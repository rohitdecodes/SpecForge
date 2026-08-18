"""HTML / PDF parsing and text chunking — Phase 2.

Parses fetched HTML (BeautifulSoup) or PDF (PyMuPDF / fitz) into plain
extractable text, then chunks it for embedding.
"""
from __future__ import annotations

import io
import re
from typing import Union


def extract_text(page_content: Union[str, bytes], is_pdf: bool = False) -> str:
    """Extract clean plain text from HTML or PDF content.

    Args:
        page_content: Raw HTML string or PDF bytes.
        is_pdf: True if content is PDF binary.

    Returns:
        Cleaned plain text suitable for embedding, or empty string on failure.
    """
    if is_pdf:
        content_bytes = (
            page_content.encode("utf-8") if isinstance(page_content, str) else page_content
        )
        return _extract_pdf_text(content_bytes)
    return _extract_html_text(str(page_content))


def _extract_html_text(html: str) -> str:
    """Parse HTML, strip nav/script/style, keep spec-table content."""
    from bs4 import BeautifulSoup
    try:
        soup = BeautifulSoup(html, "html.parser")
    except Exception:
        return ""
    for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
        tag.decompose()
    text = soup.get_text(separator="\n")
    return _clean_text(text)


def _extract_pdf_text(pdf_bytes: bytes) -> str:
    """Extract text from PDF using PyMuPDF."""
    try:
        import fitz
    except ImportError:
        return ""
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    except Exception:
        return ""
    pages: list[str] = []
    for page in doc:
        try:
            pages.append(page.get_text())
        except Exception:
            continue
    doc.close()
    return _clean_text("\n".join(pages))


def _clean_text(text: str) -> str:
    """Remove excess whitespace and blank lines."""
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    lines = [line.strip() for line in text.splitlines()]
    return "\n".join(line for line in lines if line)


def chunk_text(text: str, chunk_size: int = 300, overlap: int = 50) -> list[str]:
    """Split text into overlapping chunks of approximately chunk_size words.

    Args:
        text: Cleaned text to chunk.
        chunk_size: Target word count per chunk.
        overlap: Word overlap between consecutive chunks.

    Returns:
        List of chunk strings.
    """
    words = text.split()
    if not words:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size, len(words))
        chunks.append(" ".join(words[start:end]))
        start += chunk_size - overlap
    return chunks
