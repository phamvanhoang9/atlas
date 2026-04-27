"""HTML/text content cleaning helpers."""

from __future__ import annotations

from bs4 import BeautifulSoup

from src.utils.text_processing import normalize_whitespace


def html_to_text(html: str) -> str:
    """Convert HTML into normalized readable text."""
    soup = BeautifulSoup(html or "", "html.parser")
    for tag in soup(["script", "style", "nav", "footer", "header"]):
        tag.decompose()
    return normalize_whitespace(soup.get_text(" "))

