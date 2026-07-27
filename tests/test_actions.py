"""Tests for the Explain/Vet context actions (modes_redesign_plan.md Mục 4.5,
Trụ cột 5 + Giai đoạn 1.5). Neither touches ResearchState or workflow.py —
each is a single retrieval/scoring pipeline plus at most one LLM call.
"""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.actions.explain import explain_passage


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
