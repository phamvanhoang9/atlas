"""Tests for the deterministic Contradiction Ledger / Confidence Level
rendering (Giai đoạn 4) and the plan-driven deep_research.yaml headings.

Confidence and contradiction data must reach the report VERBATIM from
deterministic computation — the LLM is instructed to restate them, not
recompute them (D-008 lineage: trust must stay deterministic).
"""

from src.agents.deep_dive import render_confidence_block, render_contradiction_ledger
from src.prompts.functions import get_report_by_type


def test_render_contradiction_ledger_empty():
    assert "No contradictions" in render_contradiction_ledger([])


def test_render_contradiction_ledger_distinguishes_cross_source_and_internal():
    contradictions = [
        {
            "type": "cross_source",
            "topic": "latency",
            "entries": [
                {"source_url": "https://a.example", "claim": "fast", "source_category": "official", "quality_score": 95},
                {"source_url": "https://b.example", "claim": "slow", "source_category": "engineering_blog", "quality_score": 60},
            ],
        },
        {
            "type": "internal",
            "topic": "self-contradiction",
            "entries": [
                {"source_url": "https://c.example", "claim": "X works", "source_category": None, "quality_score": None},
            ],
        },
    ]

    rendered = render_contradiction_ledger(contradictions)

    assert "Cross-source" in rendered
    assert "Same-source" in rendered
    assert "https://a.example" in rendered
    assert "https://b.example" in rendered
    assert "fast" in rendered and "slow" in rendered
    # both sides shown, neither declared a winner (no "wrong"/"incorrect"/"winner" language)
    assert "winner" not in rendered.lower()


def test_render_confidence_block_includes_label_and_reasoning():
    trace = {"label": "High", "reasoning": "Average source quality score 90/100 across 5 sources."}
    rendered = render_confidence_block(trace)
    assert "High" in rendered
    assert "90/100" in rendered


def test_deep_research_prompt_includes_plan_headings():
    render = get_report_by_type("deep_dive")
    prompt = render(
        "test topic",
        ["some context"],
        "APA",
        1500,
        research_plan={"headings": ["Custom Heading X"], "approach": "y"},
    )
    assert "Custom Heading X" in prompt


def test_deep_research_prompt_includes_contradiction_ledger_and_confidence():
    render = get_report_by_type("deep_dive")
    prompt = render(
        "test topic",
        ["some context"],
        "APA",
        1500,
        contradiction_ledger="LEDGER-MARKER-XYZ",
        confidence_block="CONFIDENCE-MARKER-XYZ",
    )
    assert "LEDGER-MARKER-XYZ" in prompt
    assert "CONFIDENCE-MARKER-XYZ" in prompt


def test_ask_prompt_unaffected_by_new_optional_kwargs():
    """quick_answer.yaml has no plan/ledger/confidence placeholders — passing
    the new kwargs must not break it or leak literal $variable text."""
    render = get_report_by_type("ask")
    prompt = render("test topic", ["some context"], "APA", 500)
    assert "$plan_headings_block" not in prompt
    assert "$contradiction_ledger_block" not in prompt
    assert "$confidence_block" not in prompt
