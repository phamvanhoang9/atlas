"""Tests for generation-quality metrics: claim extraction, faithfulness, relevance, citations."""

import pytest

from src.quality.evaluation.generation_metrics import (
    answer_relevance_llm,
    citation_coverage_metric,
    faithfulness_llm,
    unsupported_claim_extraction,
)
from src.quality.evaluation.schemas import MetricResult, RetrievedContext


@pytest.mark.asyncio
async def test_claim_extraction_with_mocked_judge() -> None:
    async def judge(_: str) -> str:
        return """
        {
          "score": 0.5,
          "label": "warn",
          "reason": "mixed support",
          "evidence": [
            {"claim": "RAG uses retrieval.", "status": "supported", "supporting_context_ids": ["c1"]},
            {"claim": "RAG always removes hallucination.", "status": "not_enough_evidence", "supporting_context_ids": []}
          ]
        }
        """

    evidence = await unsupported_claim_extraction(
        "RAG uses retrieval. RAG always removes hallucination.",
        [RetrievedContext(id="c1", text="RAG uses retrieval before generation.")],
        judge=judge,
    )

    assert [item["status"] for item in evidence] == ["supported", "not_enough_evidence"]


@pytest.mark.asyncio
async def test_faithfulness_scores_supported_claims() -> None:
    result = await faithfulness_llm(
        "RAG retrieves context before answering. It uses context to ground answers.",
        [
            RetrievedContext(
                id="c1",
                text="Retrieval augmented generation retrieves context and uses it to ground answers.",
            )
        ],
    )

    assert result.score is not None
    assert result.score >= 0.5


@pytest.mark.asyncio
async def test_answer_relevance_uses_judge_when_available() -> None:
    async def judge(_: str) -> str:
        return '{"score": 0.91, "label": "pass", "reason": "answers intent", "evidence": []}'

    result = await answer_relevance_llm("What is RAG?", "RAG combines retrieval and generation.", judge=judge)

    assert result.score == 0.91
    assert result.method == "llm_judge"


def test_citation_coverage_counts_nearby_markers() -> None:
    faithfulness = MetricResult(
        name="faithfulness",
        evidence=[
            {"claim": "RAG retrieves context before answering", "status": "supported"},
        ],
    )

    result = citation_coverage_metric(
        "RAG retrieves context before answering [1](https://example.com).",
        faithfulness,
    )

    assert result.score == 1.0
