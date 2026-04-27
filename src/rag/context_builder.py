"""Mode-aware context construction for research reports."""

from __future__ import annotations

import re
from typing import Any, Iterable


def _clean_text(value: str) -> str:
    text = re.sub(r"\s+", " ", value or "").strip()
    return text


def _document_score(document: dict[str, Any]) -> float:
    score = document.get("quality_score", 0)
    try:
        return float(score)
    except (TypeError, ValueError):
        return 0.0


def _rank_documents(documents: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(documents, key=_document_score, reverse=True)


def _source_reference(title: str, url: str) -> str:
    if not url:
        return title
    return f"[{title}]({url})"


def build_mode_context(
    documents: list[dict[str, Any]],
    query: str,
    report_type: str,
    *,
    max_documents: int | None = None,
    max_chars_per_document: int | None = None,
    max_total_chars: int | None = None,
) -> str:
    """Build bounded, source-rich context without embedding every chunk.

    This path is used for deep analysis and as a robust fallback when semantic
    compression is too expensive or returns no chunks. It favors reliability:
    keep the best ranked sources, preserve URLs, and cap total context size.
    """
    if not documents:
        return ""

    if report_type == "phân tích":
        max_documents = max_documents or 10
        max_chars_per_document = max_chars_per_document or 6000
        max_total_chars = max_total_chars or 50000
    elif report_type == "đề xuất bài báo":
        max_documents = max_documents or 12
        max_chars_per_document = max_chars_per_document or 3500
        max_total_chars = max_total_chars or 35000
    else:
        max_documents = max_documents or 5
        max_chars_per_document = max_chars_per_document or 1800
        max_total_chars = max_total_chars or 10000

    sections: list[str] = []
    total_chars = 0

    for index, document in enumerate(_rank_documents(documents)[:max_documents], start=1):
        raw_content = _clean_text(str(document.get("raw_content", "")))
        if not raw_content:
            continue

        clipped_content = raw_content[:max_chars_per_document]
        if len(raw_content) > max_chars_per_document:
            clipped_content += "\n[Đã rút gọn phần còn lại để giữ context ổn định.]"

        title = document.get("title") or document.get("url") or f"Nguồn {index}"
        url = document.get("url", "")
        score = _document_score(document)
        reference = _source_reference(str(title), str(url))
        section = (
            f"### Nguồn {index}: {title}\n"
            f"URL: {url}\n"
            f"Trích dẫn khuyến nghị: {reference}\n"
            f"Quality score: {score:.2f}\n"
            f"Liên quan tới truy vấn: {query}\n"
            f"Nội dung:\n{clipped_content}"
        )

        if total_chars + len(section) > max_total_chars:
            remaining = max_total_chars - total_chars
            if remaining <= 1000:
                break
            section = section[:remaining] + "\n[Context đã được cắt theo ngân sách ký tự.]"

        sections.append(section)
        total_chars += len(section)
        if total_chars >= max_total_chars:
            break

    return "\n\n---\n\n".join(sections)


__all__ = ["build_mode_context"]
