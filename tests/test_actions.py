"""Tests for the Explain/Vet context actions (modes_redesign_plan.md Mục 4.5,
Trụ cột 5 + Giai đoạn 1.5). Neither touches ResearchState or workflow.py —
each is a single retrieval/scoring pipeline plus at most one LLM call.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.actions.explain import explain_passage
from src.actions.vet import vet_claim


def _cfg() -> SimpleNamespace:
    return SimpleNamespace(llm_model="test-model", llm_provider="openai", llm_kwargs={})


# --------------------------------------------------------------------- explain


@pytest.mark.asyncio
async def test_explain_calls_llm_for_a_normal_passage() -> None:
    llm_call = AsyncMock(return_value="Plain-language explanation of the passage.")

    result = await explain_passage(
        "Speculative decoding drafts multiple tokens with a small model, then verifies them in parallel.",
        cfg=_cfg(),
        llm_call=llm_call,
    )

    assert result["skipped"] is False
    assert result["explanation"] == "Plain-language explanation of the passage."
    llm_call.assert_awaited_once()
    assert llm_call.call_args.kwargs["report_type"] == "ask"


@pytest.mark.asyncio
async def test_explain_skips_llm_for_too_short_passage() -> None:
    """Mục 8.2 Explain edge case: 'đoạn văn quá ngắn/thiếu ngữ cảnh' —
    must not waste an LLM call guessing at a fragment."""
    llm_call = AsyncMock(side_effect=AssertionError("LLM must not be called"))

    result = await explain_passage("ok", cfg=_cfg(), llm_call=llm_call)

    assert result["skipped"] is True
    assert result["reason"] == "too_short"
    llm_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_explain_skips_llm_for_blank_passage() -> None:
    llm_call = AsyncMock(side_effect=AssertionError("LLM must not be called"))

    result = await explain_passage("   ", cfg=_cfg(), llm_call=llm_call)

    assert result["skipped"] is True
    assert result["reason"] == "too_short"
    llm_call.assert_not_awaited()


# ------------------------------------------------------------------------ vet


@pytest.mark.asyncio
async def test_vet_rejects_blank_claim() -> None:
    with pytest.raises(ValueError):
        await vet_claim("   ", cfg=_cfg())


@pytest.mark.asyncio
async def test_vet_returns_insufficient_evidence_when_nothing_found() -> None:
    """Mục 8.2 Vet edge case: '0 bằng chứng tìm được (khác với mâu thuẫn)' —
    must short-circuit to insufficient_evidence without an LLM call."""

    def _retriever_factory(query, include_domains=None):
        return SimpleNamespace(search=lambda max_results: [])

    llm_call = AsyncMock(side_effect=AssertionError("LLM must not be called"))

    result = await vet_claim(
        "GPT-5 was released in January 2026",
        cfg=_cfg(),
        retriever_factory=_retriever_factory,
        llm_call=llm_call,
    )

    assert result["verdict"] == "insufficient_evidence"
    assert result["evidence"] == []
    llm_call.assert_not_awaited()


@pytest.mark.asyncio
async def test_vet_scores_evidence_and_returns_llm_verdict() -> None:
    def _retriever_factory(query, include_domains=None):
        return SimpleNamespace(
            search=lambda max_results: [
                {"href": "https://arxiv.org/abs/1234", "title": "Paper A", "body": "supports the claim"},
                {"href": "https://medium.com/some-post", "title": "Blog B", "body": "unrelated"},
            ]
        )

    llm_call = AsyncMock(
        return_value='{"verdict": "confirmed", "explanation": "arXiv source supports it."}'
    )

    result = await vet_claim(
        "Speculative decoding speeds up LLM inference",
        cfg=_cfg(),
        retriever_factory=_retriever_factory,
        llm_call=llm_call,
    )

    assert result["verdict"] == "confirmed"
    assert result["explanation"] == "arXiv source supports it."
    assert len(result["evidence"]) == 2
    categories = {e["category"] for e in result["evidence"]}
    assert "arxiv_preprint" in categories
    assert "low_quality" in categories
    llm_call.assert_awaited_once()
    assert llm_call.call_args.kwargs["report_type"] == "compare"


@pytest.mark.asyncio
async def test_vet_fails_open_to_insufficient_evidence_on_malformed_llm_response() -> None:
    """Never fail toward a false-confidence verdict — a parse error must
    degrade to insufficient_evidence, not "confirmed"."""

    def _retriever_factory(query, include_domains=None):
        return SimpleNamespace(
            search=lambda max_results: [{"href": "https://arxiv.org/abs/1", "title": "P", "body": "x"}]
        )

    llm_call = AsyncMock(return_value="not valid json")

    result = await vet_claim(
        "some claim", cfg=_cfg(), retriever_factory=_retriever_factory, llm_call=llm_call
    )

    assert result["verdict"] == "insufficient_evidence"
    assert len(result["evidence"]) == 1
