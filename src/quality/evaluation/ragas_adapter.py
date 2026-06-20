"""Optional bridge to the RAGAS library for the RAG Triad metrics.

RagasAdapter wraps RAGAS's faithfulness/answer_relevancy/context_relevancy
metrics when the `ragas` package is installed, supporting both the modern
(v0.2+) and legacy Dataset-based APIs. Used as a supplementary signal
alongside this codebase's own deterministic/LLM-judge metrics; never raises
on failure, so a RAGAS or dependency issue can't break evaluation.
"""

from __future__ import annotations

import importlib
import logging
import math
from typing import Any

from .schemas import EvaluationInput, MetricResult

logger = logging.getLogger(__name__)

# RAGAS v0.2+ Triad metric names
_TRIAD_METRICS = ["faithfulness", "answer_relevancy", "context_relevancy"]
_RAGAS_PASS_THRESHOLD = 0.75
_RAGAS_WARN_THRESHOLD = 0.55


def _label(score: float) -> str:
    """Map a RAGAS metric score to "pass"/"warn"/"fail" using the RAGAS-specific thresholds."""
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

    _MIN_CONTEXTS = 2  # RAGAS ContextRelevance requires ≥2 contexts to avoid NaN

    async def evaluate(self, input_data: EvaluationInput) -> dict[str, MetricResult]:
        """Score input_data with RAGAS, if available and enough contexts were retrieved.

        Args:
          input_data: The evaluation sample, including query, contexts, and response.

        Returns:
          A dict of "ragas_<metric>" name to MetricResult. Empty if RAGAS is
          not installed or scoring failed; metrics are "skipped" (not absent)
          if there weren't enough retrieved contexts for stable RAGAS scoring.
        """
        if not self.available:
            return {}
        if len(input_data.retrieved_contexts) < self._MIN_CONTEXTS:
            reason = (
                f"Skipped: only {len(input_data.retrieved_contexts)} context(s) retrieved "
                f"— need ≥{self._MIN_CONTEXTS} for stable RAGAS metrics."
            )
            logger.info("RAGAS skipped: %s", reason)
            return {
                f"ragas_{m}": MetricResult(name=f"ragas_{m}", score=None, label="skipped", method="ragas", reason=reason)
                for m in ("faithfulness", "answer_relevancy", "nv_context_relevance")
            }
        try:
            return await self._run(input_data)
        except Exception as exc:  # noqa: BLE001
            logger.warning("RAGAS scoring failed, using internal metrics: %s", exc)
            return {}

    async def _run(self, input_data: EvaluationInput) -> dict[str, MetricResult]:
        """Run RAGAS, trying the modern API first and falling back to the legacy API."""
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
        import asyncio
        import os
        from functools import partial

        from langchain_openai import ChatOpenAI, OpenAIEmbeddings  # type: ignore[import-not-found]
        from ragas import EvaluationDataset, SingleTurnSample, evaluate  # type: ignore[import-not-found]
        from ragas.embeddings import LangchainEmbeddingsWrapper  # type: ignore[import-not-found]
        from ragas.llms import LangchainLLMWrapper  # type: ignore[import-not-found]
        from ragas.metrics import AnswerRelevancy, ContextRelevance, Faithfulness  # type: ignore[import-not-found]
        from ragas.run_config import RunConfig  # type: ignore[import-not-found]

        # Explicitly wrap langchain objects so RAGAS doesn't call removed methods
        # (embed_query / agenerate_text) that were dropped in langchain-openai ≥1.0.
        llm = LangchainLLMWrapper(ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini")))
        embeddings = LangchainEmbeddingsWrapper(OpenAIEmbeddings())

        # Use English translation when available so RAGAS metrics (which use an
        # English LLM internally) score query↔context relevance correctly.
        query_for_ragas = input_data.metadata.get("query_en") or input_data.query
        sample = SingleTurnSample(
            user_input=query_for_ragas,
            response=input_data.generated_output.response,
            retrieved_contexts=[ctx.text for ctx in input_data.retrieved_contexts],
            reference=input_data.ground_truth_answer or "",
        )
        dataset = EvaluationDataset(samples=[sample])
        metrics = [Faithfulness(), AnswerRelevancy(), ContextRelevance()]
        # ragas.evaluate() is synchronous and calls asyncio.run() internally.
        # Running it in a thread gives it an isolated event loop so it doesn't
        # conflict with the outer loop (which nest_asyncio has already patched).
        # RunConfig caps retries/timeout so a rate-limit doesn't cause an infinite hang.
        run_config = RunConfig(timeout=60, max_retries=2, max_wait=30)
        fn = partial(
            evaluate,
            dataset,
            metrics=metrics,
            llm=llm,
            embeddings=embeddings,
            run_config=run_config,
        )
        result = await asyncio.to_thread(fn)
        return _parse_result(result)

    async def _run_legacy(self, input_data: EvaluationInput) -> dict[str, MetricResult]:
        from datasets import Dataset  # type: ignore[import-not-found]
        from ragas import evaluate  # type: ignore[import-not-found]
        from ragas.metrics import answer_relevancy, context_relevancy, faithfulness  # type: ignore[import-not-found]

        query_for_ragas = input_data.metadata.get("query_en") or input_data.query
        dataset = Dataset.from_list([
            {
                "question": query_for_ragas,
                "answer": input_data.generated_output.response,
                "contexts": [ctx.text for ctx in input_data.retrieved_contexts],
                "ground_truth": input_data.ground_truth_answer or "",
            }
        ])
        result = evaluate(dataset, metrics=[faithfulness, answer_relevancy, context_relevancy])
        return _parse_result(result)


def _parse_result(raw_result: Any) -> dict[str, MetricResult]:
    """Normalize a RAGAS evaluate() result (DataFrame-like or dict) into MetricResults.

    NaN scores (from an LLM or embeddings error inside RAGAS) become
    "skipped" results rather than being treated as a real 0.0 score.
    """
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
        if isinstance(score, float) and math.isnan(score):
            normalized[f"ragas_{name}"] = MetricResult(
                name=f"ragas_{name}",
                score=None,
                label="skipped",
                method="ragas",
                reason="RAGAS returned NaN (LLM or embeddings error).",
            )
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
