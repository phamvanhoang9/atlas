from __future__ import annotations

import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from .. import ReportValidator
from .generation_metrics import (
    answer_relevance_llm,
    citation_coverage_metric,
    conversational_faithfulness_llm,
    unsupported_claim_count_metric,
)
from .ragas_adapter import RagasAdapter
from .refusal_metrics import (
    over_answering_rate,
    refusal_accuracy,
    source_scope_adherence,
    vietnamese_quality_check,
)
from .retrieval_metrics import (
    context_precision_metric,
    context_recall_from_ground_truth,
    context_relevance_llm,
    ndcg_at_k_metric,
    noise_ratio_metric,
    recall_at_k_metric,
)
from .schemas import (
    EvaluationInput,
    EvaluationResult,
    EvaluationThresholds,
    GeneratedOutput,
    MetricResult,
    RetrievedContext,
)

logger = logging.getLogger(__name__)


class EvaluationRunner:
    def __init__(
        self,
        *,
        thresholds: EvaluationThresholds | None = None,
        top_k: int = 3,
        judge: Callable[[str], Awaitable[str] | str] | None = None,
        enable_ragas: bool = True,
    ) -> None:
        self.thresholds = thresholds or EvaluationThresholds()
        self.top_k = top_k
        self.judge = judge
        self.ragas = RagasAdapter() if enable_ragas else None

    @classmethod
    def from_config(cls, cfg: Any) -> "EvaluationRunner":
        judge = _build_llm_judge_from_config(cfg)
        return cls(
            thresholds=EvaluationThresholds.model_validate(
                getattr(cfg, "eval_fail_thresholds", {}) or {}
            ),
            top_k=int(getattr(cfg, "eval_top_k", 3)),
            judge=judge,
        )

    async def aevaluate_single(self, input_data: EvaluationInput) -> EvaluationResult:
        retrieved_ids = [context.id for context in input_data.retrieved_contexts]
        metrics: dict[str, MetricResult] = {}

        # --- RAG Triad (core blocking metrics) ---
        metrics["context_relevance"] = await context_relevance_llm(
            input_data.query,
            input_data.retrieved_contexts,
            judge=self.judge,
            thresholds=self.thresholds,
        )
        metrics["faithfulness"] = await conversational_faithfulness_llm(
            input_data.generated_output.response,
            input_data.retrieved_contexts,
            judge=self.judge,
            thresholds=self.thresholds,
        )
        metrics["answer_relevance"] = await answer_relevance_llm(
            input_data.query,
            input_data.generated_output.response,
            judge=self.judge,
            thresholds=self.thresholds,
        )

        # --- Supporting retrieval metrics ---
        metrics["context_precision"] = context_precision_metric(
            retrieved_ids,
            input_data.relevant_context_ids,
            k=self.top_k,
            thresholds=self.thresholds,
        )
        metrics[f"recall@{self.top_k}"] = recall_at_k_metric(
            retrieved_ids,
            input_data.relevant_context_ids,
            k=self.top_k,
            thresholds=self.thresholds,
        )
        metrics[f"ndcg@{self.top_k}"] = ndcg_at_k_metric(
            retrieved_ids,
            input_data.relevance_scores,
            k=self.top_k,
            thresholds=self.thresholds,
        )
        metrics["context_recall"] = context_recall_from_ground_truth(
            input_data.retrieved_contexts,
            input_data.ground_truth_context,
        )
        metrics["noise_ratio"] = noise_ratio_metric(input_data.query, input_data.retrieved_contexts)

        # --- Supporting generation metrics ---
        metrics["unsupported_claim_count"] = unsupported_claim_count_metric(
            metrics["faithfulness"],
            thresholds=self.thresholds,
        )
        metrics["citation_coverage"] = citation_coverage_metric(
            input_data.generated_output.response, metrics["faithfulness"]
        )

        # --- Safety / behavior metrics ---
        metrics["refusal_accuracy"] = refusal_accuracy(
            input_data.expected_behavior,
            input_data.generated_output.response,
            thresholds=self.thresholds,
        )
        metrics["over_answering_rate"] = over_answering_rate(input_data)
        metrics["source_scope_adherence"] = source_scope_adherence(
            input_data.generated_output.response, input_data.retrieved_contexts
        )
        metrics["vietnamese_quality_check"] = vietnamese_quality_check(
            input_data.generated_output.response,
            input_data.rubric.language,
        )

        if self.ragas is not None:
            metrics.update(await self.ragas.evaluate(input_data))

        quality_check = ReportValidator().validate(
            input_data.generated_output.response,
            [context.text for context in input_data.retrieved_contexts],
        ).to_dict()

        overall_score = _overall_score(metrics)
        label = _overall_label(metrics, overall_score)
        return EvaluationResult(
            sample_id=input_data.sample_id or str(uuid.uuid4()),
            query=input_data.query,
            overall_score=overall_score,
            label=label,
            passed=label == "pass",
            metrics=metrics,
            recommendations=_recommendations(metrics),
            quality_check=quality_check,
            metadata=input_data.metadata,
        )


def contexts_from_strings(contexts: Sequence[str], source_urls: Sequence[str] | None = None) -> list[RetrievedContext]:
    urls = list(source_urls or [])
    return [
        RetrievedContext(
            id=str(index),
            text=context,
            source_url=urls[index] if index < len(urls) else None,
            rank=index + 1,
        )
        for index, context in enumerate(contexts)
    ]


async def evaluate_state_node(state: dict[str, Any]) -> dict[str, Any]:
    cfg = state.get("cfg")
    if not getattr(cfg, "enable_evaluation", False):
        return state
    if getattr(cfg, "evaluation_mode", "online") not in {"online", "both"}:
        return state

    try:
        contexts = contexts_from_strings(state.get("context", []), state.get("visited_urls", []))
        input_data = EvaluationInput(
            sample_id=state.get("history_id"),
            query=state.get("query", ""),
            retrieved_contexts=contexts,
            generated_output=GeneratedOutput(response=state.get("report", "")),
            expected_behavior="answer",
            source_urls=state.get("visited_urls", []),
            metadata={"report_type": state.get("report_type")},
        )
        result = await EvaluationRunner.from_config(cfg).aevaluate_single(input_data)
        payload = result.model_dump(mode="json")
        websocket = state.get("websocket")
        if websocket:
            await websocket.send_json({"type": "evaluation", "output": payload})
        return {**state, "evaluation_result": payload}
    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Online evaluation failed; continuing workflow: %s", exc)
        return {**state, "evaluation_result": {"error": str(exc)}}


def _overall_score(metrics: dict[str, MetricResult]) -> float:
    scores = [
        metric.score
        for metric in metrics.values()
        if metric.score is not None and metric.name != "unsupported_claim_count"
    ]
    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 4)


def _overall_label(metrics: dict[str, MetricResult], overall_score: float) -> str:
    blocking = {"faithfulness", "answer_relevance", "context_relevance", "refusal_accuracy"}
    if any(metric.label == "fail" and name in blocking for name, metric in metrics.items()):
        return "fail"
    if any(metric.label == "fail" for metric in metrics.values()) or overall_score < 0.70:
        return "warn"
    if any(metric.label == "warn" for metric in metrics.values()) or overall_score < 0.82:
        return "warn"
    return "pass"


def _recommendations(metrics: dict[str, MetricResult]) -> list[str]:
    recommendations: list[str] = []
    failed = {name for name, metric in metrics.items() if metric.label == "fail"}
    if failed.intersection({"context_relevance", "context_precision", "context_recall", "recall@3", "recall@5"}):
        recommendations.append("Retrieval issue: improve query planning, source filtering, or reranking.")
    if failed.intersection({"faithfulness", "unsupported_claim_count", "source_scope_adherence"}):
        recommendations.append("Generation hallucination: tighten grounding prompts and require source support.")
    if "citation_coverage" in failed:
        recommendations.append("Weak citation/source support: require inline citations for key claims.")
    if failed.intersection({"refusal_accuracy", "over_answering_rate"}):
        recommendations.append("Refusal issue: add evidence insufficiency and out-of-scope handling.")
    if "vietnamese_quality_check" in failed:
        recommendations.append("Vietnamese clarity issue: review terminology, encoding, and sentence length.")
    return recommendations


def _build_llm_judge_from_config(cfg: Any) -> Callable[[str], Awaitable[str]] | None:
    model = getattr(cfg, "eval_llm_model", "") or ""
    if not model:
        return None
    provider = getattr(cfg, "eval_llm_provider", "same_as_main")
    if provider == "same_as_main":
        provider = getattr(cfg, "llm_provider", "openai")

    async def _judge(prompt: str) -> str:
        from ...llm.completion import create_chat_completion

        return await create_chat_completion(
            model=model,
            llm_provider=provider,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a RAG evaluation judge. "
                        "Assess each metric using the RAG Triad framework: "
                        "Context Relevance (are retrieved contexts on-topic?), "
                        "Faithfulness (are claims grounded in context?), "
                        "Answer Relevance (does the answer address the question?). "
                        "Think step-by-step before scoring. Return only strict JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=1200,
            stream=False,
            report_type="hỏi đáp",
            llm_kwargs=getattr(cfg, "llm_kwargs", {}),
        )

    return _judge
