"""Lightweight, deterministic grounding check for generated reports.

Validates a generated report against its source context by comparing cited
URLs and checking basic length/content heuristics. Produces a 0-1 score and
pass/fail warnings used to flag reports that may be ungrounded or too thin,
without requiring an LLM call.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Sequence


URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")


@dataclass(frozen=True)
class ReportQuality:
    """The grounding/quality verdict produced by ReportValidator.validate.

    Attributes:
      passed: Whether the report meets min_score and has no ungrounded URLs.
      score: Weighted 0-1 quality score (grounding, citation presence, length).
      report_url_count: Number of distinct URLs found in the report text.
      context_url_count: Number of distinct URLs found in the source context.
      grounded_url_count: Report URLs that also appear in the context.
      warnings: Human-readable (Vietnamese) warning messages, if any.
    """

    passed: bool
    score: float
    report_url_count: int
    context_url_count: int
    grounded_url_count: int
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        """Return the dataclass fields as a plain dict for JSON serialization."""
        return asdict(self)


class ReportValidator:
    """Deterministic, LLM-free validator that scores a report's grounding in its context."""

    min_score: float = 0.7

    def _extract_urls(self, text: str) -> set[str]:
        return {url.rstrip(".,;") for url in URL_PATTERN.findall(text)}

    def _context_text(self, context: Sequence[Any]) -> str:
        return "\n\n".join(str(item) for item in context)

    def validate(self, report: str, context: Sequence[Any]) -> ReportQuality:
        """Score a report's grounding against its source context.

        Args:
          report: The generated report text to validate.
          context: The source documents/chunks the report was generated from;
            each item is stringified before URL extraction.

        Returns:
          A ReportQuality with the computed score, warnings, and pass/fail verdict.
        """
        context_text = self._context_text(context)
        report_urls = self._extract_urls(report)
        context_urls = self._extract_urls(context_text)
        grounded_urls = report_urls.intersection(context_urls)
        warnings: list[str] = []

        if len(report.strip()) < 500:
            warnings.append("Bao cao ngan bat thuong; can kiem tra nguon va noi dung.")
        if context_urls and not report_urls:
            warnings.append("Bao cao chua co URL trich dan trong khi context co nguon.")
        if report_urls and context_urls and len(grounded_urls) < len(report_urls):
            warnings.append("Mot so URL trong bao cao khong xuat hien trong context.")
        if "khong co" in report.lower() and len(report.strip()) < 1200:
            warnings.append("Bao cao co nhieu thong tin thieu; can xem lai chat luong thu thap context.")

        grounding_score = 1.0
        if report_urls and context_urls:
            grounding_score = len(grounded_urls) / len(report_urls)
        citation_score = 1.0 if report_urls else 0.55
        length_score = min(1.0, len(report.strip()) / 1200)
        score = round((grounding_score * 0.5) + (citation_score * 0.3) + (length_score * 0.2), 3)

        return ReportQuality(
            passed=score >= self.min_score and not any("khong xuat hien" in warning for warning in warnings),
            score=score,
            report_url_count=len(report_urls),
            context_url_count=len(context_urls),
            grounded_url_count=len(grounded_urls),
            warnings=warnings,
        )
