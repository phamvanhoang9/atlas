"""Mode registry — canonical research modes and legacy alias handling.

Canonical mode ids are the stable technical contract (PRD §5, decision D-004):
``quick`` (Quick Answer), ``research`` (Research), ``deep`` (Deep Research).

Legacy Vietnamese mode strings remain accepted as deprecated aliases so stored
history entries and in-flight clients keep working during the migration.
"""

from __future__ import annotations

from dataclasses import dataclass


QUICK = "quick"
RESEARCH = "research"
DEEP = "deep"

CANONICAL_MODE_IDS: tuple[str, ...] = (QUICK, RESEARCH, DEEP)

#: Deprecated aliases (old product modes) → canonical ids.
LEGACY_MODE_ALIASES: dict[str, str] = {
    "hỏi đáp": QUICK,
    "đề xuất bài báo": RESEARCH,
    "phân tích": DEEP,
}


@dataclass(frozen=True)
class ModeSpec:
    """Behavioral contract for one research mode."""

    id: str
    label: str
    description: str
    report_template: str
    url_report_template: str
    search_include_domains: tuple[str, ...] | None
    max_scrape_urls: int
    priority_note: str


# Research mode searches are biased toward high-quality primary sources.
# Quick/deep search broadly; ranking is handled by the source quality scorer.
_RESEARCH_INCLUDE_DOMAINS: tuple[str, ...] = (
    "arxiv.org",
    "openreview.net",
    "aclanthology.org",
    "proceedings.neurips.cc",
    "proceedings.mlr.press",
    "openaccess.thecvf.com",
    "semanticscholar.org",
    "paperswithcode.com",
    "huggingface.co",
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "research.google",
    "ai.meta.com",
    "mistral.ai",
    "github.com",
)

MODES: dict[str, ModeSpec] = {
    QUICK: ModeSpec(
        id=QUICK,
        label="Quick Answer",
        description="Fast, source-aware answers for AI questions with citations.",
        report_template="quick_answer",
        url_report_template="quick_answer",
        search_include_domains=None,
        max_scrape_urls=8,
        priority_note="PRIORITY: Speed > Accuracy > Conciseness",
    ),
    RESEARCH: ModeSpec(
        id=RESEARCH,
        label="Research",
        description="Structured analysis grounded in papers, official sources, and technical reports.",
        report_template="research_report",
        url_report_template="research_report",
        search_include_domains=_RESEARCH_INCLUDE_DOMAINS,
        max_scrape_urls=24,
        priority_note="PRIORITY: Source quality > Depth > Accuracy",
    ),
    DEEP: ModeSpec(
        id=DEEP,
        label="Deep Research",
        description="Multi-step research with impact analysis, contradiction checks, and confidence levels.",
        report_template="deep_research",
        url_report_template="source_analysis",
        search_include_domains=None,
        max_scrape_urls=18,
        priority_note="PRIORITY: Depth > Evidence > Impact analysis > Structure",
    ),
}


def is_known_mode(mode: str | None) -> bool:
    """Return True when *mode* is a canonical id or a known legacy alias."""
    if not mode:
        return False
    return mode in MODES or mode in LEGACY_MODE_ALIASES


def normalize_mode(mode: str | None, default: str = RESEARCH) -> str:
    """Map any accepted mode string to its canonical id.

    Unknown values fall back to *default* so internal report_type values that
    predate the registry (e.g. "research_report") degrade gracefully.
    """
    if not mode:
        return default
    if mode in MODES:
        return mode
    return LEGACY_MODE_ALIASES.get(mode, default)


def get_mode_spec(mode: str | None) -> ModeSpec:
    """Return the ModeSpec for any accepted mode string."""
    return MODES[normalize_mode(mode)]
