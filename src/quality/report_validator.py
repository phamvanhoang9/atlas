from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Any, Sequence


URL_PATTERN = re.compile(r"https?://[^\s)\]>\"']+")


@dataclass(frozen=True)
class ReportQuality:
    passed: bool
    score: float
    report_url_count: int
    context_url_count: int
    grounded_url_count: int
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReportValidator:
    min_score: float = 0.7

    def _extract_urls(self, text: str) -> set[str]:
        return {url.rstrip(".,;") for url in URL_PATTERN.findall(text)}

    def _context_text(self, context: Sequence[Any]) -> str:
        return "\n\n".join(str(item) for item in context)

    def validate(self, report: str, context: Sequence[Any]) -> ReportQuality:
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
