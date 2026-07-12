"""Mode registry — canonical research modes.

Canonical mode ids are the stable technical contract (PRD §5, decision
D-004, superseded 2026-07-12 — see modes_redesign_plan.md Mục 8.1 #4):
``ask`` (Ask), ``compare`` (Compare), ``deep_dive`` (Deep Dive).

The previous ids (``quick``/``research``/``deep``, and before them the
Vietnamese product strings) are fully retired — ``normalize_mode()`` does
not map them to anything; an unknown string just falls back to the
``compare`` default.
"""

from __future__ import annotations

from dataclasses import dataclass


ASK = "ask"
COMPARE = "compare"
DEEP_DIVE = "deep_dive"

CANONICAL_MODE_IDS: tuple[str, ...] = (ASK, COMPARE, DEEP_DIVE)


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


# Compare mode searches are biased toward high-quality primary sources.
# Ask/deep_dive search broadly; ranking is handled by the source quality scorer.
_COMPARE_INCLUDE_DOMAINS: tuple[str, ...] = (
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
    ASK: ModeSpec(
        id=ASK,
        label="Ask",
        description="Fast, source-aware answers for AI questions with citations.",
        report_template="quick_answer",
        url_report_template="quick_answer",
        search_include_domains=None,
        max_scrape_urls=8,
        priority_note="PRIORITY: Speed > Accuracy > Conciseness",
    ),
    COMPARE: ModeSpec(
        id=COMPARE,
        label="Compare",
        description="Structured analysis grounded in papers, official sources, and technical reports.",
        report_template="research_report",
        url_report_template="research_report",
        search_include_domains=_COMPARE_INCLUDE_DOMAINS,
        max_scrape_urls=24,
        priority_note="PRIORITY: Source quality > Depth > Accuracy",
    ),
    DEEP_DIVE: ModeSpec(
        id=DEEP_DIVE,
        label="Deep Dive",
        description="Multi-step research with impact analysis, contradiction checks, and confidence levels.",
        report_template="deep_research",
        url_report_template="source_analysis",
        search_include_domains=None,
        max_scrape_urls=18,
        priority_note="PRIORITY: Depth > Evidence > Impact analysis > Structure",
    ),
}


def is_known_mode(mode: str | None) -> bool:
    """Return True when *mode* is a canonical mode id."""
    return bool(mode) and mode in MODES


def normalize_mode(mode: str | None, default: str = COMPARE) -> str:
    """Return *mode* if it is a canonical id, else *default*.

    Unknown values fall back to *default* so internal report_type values that
    predate the registry (e.g. "research_report"), and retired mode ids
    (Vietnamese product strings, or the old quick/research/deep ids),
    degrade gracefully.
    """
    if mode in MODES:
        return mode
    return default


def get_mode_spec(mode: str | None) -> ModeSpec:
    """Return the ModeSpec for any accepted mode string."""
    return MODES[normalize_mode(mode)]
