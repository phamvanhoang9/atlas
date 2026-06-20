"""Mode-aware context construction for research reports."""

from __future__ import annotations

import re
from typing import Any, Iterable

from src.modes import DEEP, RESEARCH, normalize_mode


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

    Args:
      documents: Candidate source documents, each expected to provide
        `raw_content`, `title`/`url`, and optionally `quality_score` and
        `source_category_label`.
      query: The research query the context is being assembled for; included
        in each source section for downstream relevance grounding.
      report_type: Mode identifier (e.g. "quick", "research", "deep") used to
        select default document/character caps when explicit overrides are
        not provided.
      max_documents: Maximum number of top-ranked documents to include.
        Defaults to a mode-specific value when omitted.
      max_chars_per_document: Maximum characters kept per document before
        truncation. Defaults to a mode-specific value when omitted.
      max_total_chars: Maximum total characters across all sections.
        Defaults to a mode-specific value when omitted.

    Returns:
      A string of newline-separated source sections (each with title, URL,
      quality score, and clipped content), or an empty string if no
      documents have usable content.
    """
    if not documents:
        return ""

    canonical_mode = normalize_mode(report_type)
    if canonical_mode == DEEP:
        max_documents = max_documents or 10
        max_chars_per_document = max_chars_per_document or 6000
        max_total_chars = max_total_chars or 50000
    elif canonical_mode == RESEARCH:
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
            clipped_content += "\n[Remaining content truncated to keep context stable.]"

        title = document.get("title") or document.get("url") or f"Source {index}"
        url = document.get("url", "")
        score = _document_score(document)
        category_label = document.get("source_category_label", "")
        category_line = f"Category: {category_label}\n" if category_label else ""
        reference = _source_reference(str(title), str(url))
        section = (
            f"### Source {index}: {title}\n"
            f"URL: {url}\n"
            f"{category_line}"
            f"Recommended citation: {reference}\n"
            f"Quality score: {score:.2f}\n"
            f"Relevant to query: {query}\n"
            f"Content:\n{clipped_content}"
        )

        if total_chars + len(section) > max_total_chars:
            remaining = max_total_chars - total_chars
            if remaining <= 1000:
                break
            section = section[:remaining] + "\n[Context trimmed to fit the character budget.]"

        sections.append(section)
        total_chars += len(section)
        if total_chars >= max_total_chars:
            break

    return "\n\n---\n\n".join(sections)


__all__ = ["build_mode_context"]
