from __future__ import annotations

import importlib
import logging
from typing import Any

from src.quality.evaluation.schemas import EvaluationInput, MetricResult

logger = logging.getLogger(__name__)


class RagasAdapter:
    """Optional RAGAS bridge with graceful degradation.

    RAGAS has changed public APIs across releases. This adapter treats it as an
    opportunistic scorer: if the package or expected API is unavailable, callers
    get an empty result and continue with ATLAS internal metrics.
    """

    def __init__(self) -> None:
        self.available = importlib.util.find_spec("ragas") is not None

    async def evaluate(self, input_data: EvaluationInput) -> dict[str, MetricResult]:
        if not self.available:
            return {}

        try:
            ragas = importlib.import_module("ragas")
            metrics_module = importlib.import_module("ragas.metrics")
        except (ImportError, RuntimeError) as exc:
            logger.info("RAGAS unavailable, using internal evaluation metrics: %s", exc)
            return {}

        try:
            return await self._evaluate_with_best_effort(ragas, metrics_module, input_data)
        except (AttributeError, TypeError, ValueError, RuntimeError, ImportError) as exc:
            logger.warning("RAGAS scoring failed, using internal evaluation metrics: %s", exc)
            return {}

    async def _evaluate_with_best_effort(
        self,
        ragas: Any,
        metrics_module: Any,
        input_data: EvaluationInput,
    ) -> dict[str, MetricResult]:
        try:
            from datasets import Dataset  # type: ignore[import-not-found]
        except ImportError:
            return {}

        metric_names = ["faithfulness", "response_relevancy", "context_precision", "context_recall"]
        metrics = [getattr(metrics_module, name) for name in metric_names if hasattr(metrics_module, name)]
        if not metrics or not hasattr(ragas, "evaluate"):
            return {}

        dataset = Dataset.from_list(
            [
                {
                    "question": input_data.query,
                    "answer": input_data.generated_output.response,
                    "contexts": [context.text for context in input_data.retrieved_contexts],
                    "ground_truth": input_data.ground_truth_answer or "",
                }
            ]
        )
        raw_result = ragas.evaluate(dataset, metrics=metrics)
        if hasattr(raw_result, "to_pandas"):
            row = raw_result.to_pandas().iloc[0].to_dict()
        elif isinstance(raw_result, dict):
            row = raw_result
        else:
            return {}

        normalized: dict[str, MetricResult] = {}
        for name, score in row.items():
            if isinstance(score, int | float):
                normalized[f"ragas_{name}"] = MetricResult(
                    name=f"ragas_{name}",
                    score=round(float(score), 4),
                    label="pass" if float(score) >= 0.75 else "warn" if float(score) >= 0.6 else "fail",
                    method="ragas",
                    reason="Computed by optional RAGAS adapter.",
                )
        return normalized
