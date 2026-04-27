"""PDF text extraction helpers."""

from __future__ import annotations

from pathlib import Path

try:
    import fitz
except ImportError:  # pragma: no cover
    fitz = None


def extract_pdf_text(path: str) -> str:
    """Extract text from a local PDF path using PyMuPDF."""
    if fitz is None:
        return ""
    with fitz.open(Path(path)) as document:
        return "\n".join(page.get_text() for page in document)

