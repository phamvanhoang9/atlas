import importlib.util

import pytest

from src.quality.evaluation import (
    EvaluationInput,
    EvaluationRunner,
    GeneratedOutput,
    RetrievedContext,
)
from src.quality.evaluation.ragas_adapter import RagasAdapter
from src.quality.evaluation.schemas import EvaluationThresholds


@pytest.mark.asyncio
async def test_evaluator_end_to_end_with_fake_contexts() -> None:
    runner = EvaluationRunner(
        thresholds=EvaluationThresholds(
            min_faithfulness=0.5,
            min_answer_relevance=0.05,
            min_context_relevance=0.05,
        ),
        top_k=2,
        enable_ragas=False,
    )
    input_data = EvaluationInput(
        sample_id="sample-1",
        query="What is RAG?",
        retrieved_contexts=[
            RetrievedContext(
                id="ctx-1",
                text="RAG retrieves relevant context before generating an answer.",
                source_url="https://example.com/rag",
            ),
            RetrievedContext(id="ctx-2", text="Unrelated cooking context."),
        ],
        generated_output=GeneratedOutput(
            response=(
                "RAG retrieves relevant context before generating an answer "
                "[source](https://example.com/rag)."
            )
        ),
        relevant_context_ids=["ctx-1"],
        relevance_scores={"ctx-1": 3.0, "ctx-2": 0.0},
    )

    result = await runner.aevaluate_single(input_data)

    assert result.sample_id == "sample-1"
    assert result.metrics["context_precision"].score == 0.5
    assert result.metrics["faithfulness"].score is not None
    assert "quality_check" in result.model_dump()


@pytest.mark.asyncio
async def test_evaluator_translates_vietnamese_query_for_scoring() -> None:
    calls: list[str] = []

    async def translator(text: str) -> str:
        calls.append(text)
        return "What is retrieval augmented generation?"

    runner = EvaluationRunner(
        thresholds=EvaluationThresholds(
            min_faithfulness=0.05,
            min_answer_relevance=0.05,
            min_context_relevance=0.05,
        ),
        translator=translator,
        enable_ragas=False,
    )
    input_data = EvaluationInput(
        sample_id="sample-vi",
        query="RAG là gì?",
        retrieved_contexts=[
            RetrievedContext(
                id="ctx-1",
                text="Retrieval augmented generation retrieves context before answering.",
            )
        ],
        generated_output=GeneratedOutput(
            response="RAG retrieves relevant context before generating an answer."
        ),
        relevant_context_ids=["ctx-1"],
        relevance_scores={"ctx-1": 3.0},
    )

    result = await runner.aevaluate_single(input_data)

    assert calls == ["RAG là gì?"]
    assert result.query == "RAG là gì?"
    assert result.metadata["query_en"] == "What is retrieval augmented generation?"


@pytest.mark.asyncio
async def test_evaluator_does_not_translate_english_query() -> None:
    calls: list[str] = []

    def translator(text: str) -> str:
        calls.append(text)
        return "Unexpected translation"

    runner = EvaluationRunner(translator=translator, enable_ragas=False)
    input_data = EvaluationInput(
        sample_id="sample-en",
        query="What is RAG?",
        retrieved_contexts=[
            RetrievedContext(
                id="ctx-1",
                text="RAG retrieves relevant context before generating an answer.",
            )
        ],
        generated_output=GeneratedOutput(response="RAG retrieves relevant context."),
    )

    result = await runner.aevaluate_single(input_data)

    assert calls == []
    assert "query_en" not in result.metadata


@pytest.mark.asyncio
async def test_evaluator_keeps_original_query_when_translation_fails() -> None:
    def translator(_: str) -> str:
        raise RuntimeError("translator unavailable")

    runner = EvaluationRunner(translator=translator, enable_ragas=False)
    input_data = EvaluationInput(
        sample_id="sample-translation-fallback",
        query="RAG là gì?",
        retrieved_contexts=[
            RetrievedContext(
                id="ctx-1",
                text="Retrieval augmented generation retrieves context before answering.",
            )
        ],
        generated_output=GeneratedOutput(response="RAG retrieves relevant context."),
    )

    result = await runner.aevaluate_single(input_data)

    assert result.query == "RAG là gì?"
    assert "query_en" not in result.metadata


@pytest.mark.asyncio
async def test_ragas_adapter_falls_back_when_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(importlib.util, "find_spec", lambda name: None if name == "ragas" else object())
    adapter = RagasAdapter()

    result = await adapter.evaluate(
        EvaluationInput(
            query="What is RAG?",
            retrieved_contexts=[],
            generated_output=GeneratedOutput(response="RAG retrieves context."),
        )
    )

    assert result == {}
