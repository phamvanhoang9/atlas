from __future__ import annotations

import importlib
import logging
from typing import Any

from .schemas import EvaluationInput, MetricResult

logger = logging.getLogger(__name__)

# RAGAS v0.2+ Triad metric names
_TRIAD_METRICS = ["faithfulness", "answer_relevancy", "context_relevancy"]
_RAGAS_PASS_THRESHOLD = 0.75
_RAGAS_WARN_THRESHOLD = 0.55


def _label(score: float) -> str:
    if score >= _RAGAS_PASS_THRESHOLD:
        return "pass"
    if score >= _RAGAS_WARN_THRESHOLD:
        return "warn"
    return "fail"


class RagasAdapter:
    """Optional RAGAS v0.2+ bridge focused on the RAG Triad.

    Attempts to use the modern SingleTurnSample / evaluate API.
    Falls back silently to internal metrics if RAGAS is absent or the API
    has changed between releases.
    """

    def __init__(self) -> None:
        self.available = importlib.util.find_spec("ragas") is not None

    async def evaluate(self, input_data: EvaluationInput) -> dict[str, MetricResult]:
        if not self.available:
            return {}
        try:
            return await self._run(input_data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RAGAS scoring failed, using internal metrics: %s", exc)
            return {}

    async def _run(self, input_data: EvaluationInput) -> dict[str, MetricResult]:
        # Try modern v0.2+ API first (SingleTurnSample + EvaluationDataset)
        try:
            return await self._run_v2(input_data)
        except (ImportError, AttributeError):
            pass
        # Fall back to legacy Dataset-based API
        try:
            return await self._run_legacy(input_data)
        except (ImportError, AttributeError, TypeError) as exc:
            logger.info("RAGAS legacy API also unavailable: %s", exc)
            return {}

    async def _run_v2(self, input_data: EvaluationInput) -> dict[str, MetricResult]:
        from ragas import EvaluationDataset, SingleTurnSample, evaluate  # type: ignore[import-not-found]
        from ragas.metrics import AnswerRelevancy, ContextRelevance, Faithfulness  # type: ignore[import-not-found]

        sample = SingleTurnSample(
            user_input=input_data.query,
            response=input_data.generated_output.response,
            retrieved_contexts=[ctx.text for ctx in input_data.retrieved_contexts],
            reference=input_data.ground_truth_answer or "",
        )
        dataset = EvaluationDataset(samples=[sample])
        metrics = [Faithfulness(), AnswerRelevancy(), ContextRelevance()]
        result = evaluate(dataset, metrics=metrics)
        return _parse_result(result)

    async def _run_legacy(self, input_data: EvaluationInput) -> dict[str, MetricResult]:
        from datasets import Dataset  # type: ignore[import-not-found]
        from ragas import evaluate  # type: ignore[import-not-found]
        from ragas.metrics import answer_relevancy, context_relevancy, faithfulness  # type: ignore[import-not-found]

        dataset = Dataset.from_list([
            {
                "question": input_data.query,
                "answer": input_data.generated_output.response,
                "contexts": [ctx.text for ctx in input_data.retrieved_contexts],
                "ground_truth": input_data.ground_truth_answer or "",
            }
        ])
        result = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_relevancy])
        return _parse_result(result)


def _parse_result(raw_result: Any) -> dict[str, MetricResult]:
    if hasattr(raw_result, "to_pandas"):
        row: dict[str, Any] = raw_result.to_pandas().iloc[0].to_dict()
    elif isinstance(raw_result, dict):
        row = raw_result
    else:
        return {}

    normalized: dict[str, MetricResult] = {}
    for name, score in row.items():
        if not isinstance(score, int | float):
            continue
        score_f = round(float(score), 4)
        normalized[f"ragas_{name}"] = MetricResult(
            name=f"ragas_{name}",
            score=score_f,
            label=_label(score_f),
            method="ragas",
            reason="Computed by RAGAS adapter (RAG Triad).",
        )
    return normalized
