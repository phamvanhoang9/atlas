from __future__ import annotations

import logging
import re
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
        translator: Callable[[str], Awaitable[str] | str] | None = None,
        enable_ragas: bool = True,
    ) -> None:
        self.thresholds = thresholds or EvaluationThresholds()
        self.top_k = top_k
        self.judge = judge
        self.translator = translator
        self.ragas = RagasAdapter() if enable_ragas else None

    @classmethod
    def from_config(cls, cfg: Any) -> "EvaluationRunner":
        judge = _build_llm_judge_from_config(cfg)
        translator = _build_llm_translator_from_config(cfg)
        return cls(
            thresholds=EvaluationThresholds.model_validate(
                getattr(cfg, "eval_fail_thresholds", {}) or {}
            ),
            top_k=int(getattr(cfg, "eval_top_k", 3)),
            judge=judge,
            translator=translator,
        )

    async def aevaluate_single(self, input_data: EvaluationInput) -> EvaluationResult:
        retrieved_ids = [context.id for context in input_data.retrieved_contexts]
        metrics: dict[str, MetricResult] = {}

        # Translate Vietnamese query to English once so LLM-judge and lexical
        # metrics don't compare Vietnamese tokens against English context text.
        query_for_scoring = input_data.query
        if self.translator and _is_vietnamese(input_data.query):
            translated = await _translate_to_english(input_data.query, self.translator)
            if translated and translated != input_data.query:
                query_for_scoring = translated
                logger.info("Query translated for scoring: %r → %r", input_data.query, query_for_scoring)

        # --- RAG Triad (core blocking metrics) ---
        metrics["context_relevance"] = await context_relevance_llm(
            query_for_scoring,
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
            query_for_scoring,
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
        metrics["noise_ratio"] = noise_ratio_metric(query_for_scoring, input_data.retrieved_contexts)

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
            input_data.generated_output.response,
            input_data.retrieved_contexts,
            faithfulness_result=metrics.get("faithfulness"),
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
        result_metadata = {**input_data.metadata}
        if query_for_scoring != input_data.query:
            result_metadata["query_en"] = query_for_scoring
        return EvaluationResult(
            sample_id=input_data.sample_id or str(uuid.uuid4()),
            query=input_data.query,
            overall_score=overall_score,
            label=label,
            passed=label == "pass",
            metrics=metrics,
            recommendations=_recommendations(metrics),
            quality_check=quality_check,
            metadata=result_metadata,
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

    _MODE_DOMAINS = {
        "quick": "qa",
        "deep": "deep_analysis",
        "research": "paper_recommendation",
    }

    try:
        from src.modes import normalize_mode

        report_type = normalize_mode(state.get("report_type", ""))
        contexts = contexts_from_strings(state.get("context", []), state.get("visited_urls", []))
        from .schemas import EvaluationRubric
        # Answers follow the query language (D-003): only apply Vietnamese
        # quality checks when the query itself is Vietnamese.
        rubric = EvaluationRubric(
            domain=_MODE_DOMAINS.get(report_type, "qa"),
            language="vi" if _is_vietnamese(state.get("query", "")) else "en",
        )
        input_data = EvaluationInput(
            sample_id=state.get("history_id"),
            query=state.get("query", ""),
            retrieved_contexts=contexts,
            generated_output=GeneratedOutput(response=state.get("report", "")),
            expected_behavior="answer",
            source_urls=state.get("visited_urls", []),
            rubric=rubric,
            metadata={"report_type": report_type},
        )
        result = await EvaluationRunner.from_config(cfg).aevaluate_single(input_data)
        payload = result.model_dump(mode="json")

        metric_lines = "\n".join(
            f"  {name:<30} score={m.score!s:<6} label={m.label}"
            for name, m in result.metrics.items()
        )
        recs = "\n".join(f"  - {r}" for r in result.recommendations) or "  (none)"
        logger.info(
            "\n=== EVALUATION RESULT ===\n"
            "Query   : %s\n"
            "Overall : %.4f  [%s]\n"
            "Metrics :\n%s\n"
            "Recommendations:\n%s\n"
            "=========================",
            result.query,
            result.overall_score,
            result.label.upper(),
            metric_lines,
            recs,
        )

        websocket = state.get("websocket")
        if websocket:
            await websocket.send_json({"type": "evaluation", "output": payload})
        return {**state, "evaluation_result": payload}
    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("Online evaluation failed; continuing workflow: %s", exc)
        return {**state, "evaluation_result": {"error": str(exc)}}


_INVERTED_METRICS = frozenset({"noise_ratio", "over_answering_rate"})

# unsupported_claim_count is derived from faithfulness evidence and is already
# captured by the faithfulness score. Excluding it avoids double-counting the
# same grounding signal in the average.
_SKIP_IN_OVERALL = frozenset({"unsupported_claim_count"})


def _overall_score(metrics: dict[str, MetricResult]) -> float:
    import math
    scores = []
    for metric in metrics.values():
        if metric.name in _SKIP_IN_OVERALL:
            continue
        if metric.score is None or (isinstance(metric.score, float) and math.isnan(metric.score)):
            continue
        if metric.name in _INVERTED_METRICS:
            scores.append(max(0.0, min(1.0, 1.0 - metric.score)))
        else:
            scores.append(metric.score)
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


_VI_PATTERN = re.compile(
    r"[àáảãạăằắẳẵặâầấẩẫậđèéẻẽẹêềếểễệìíỉĩịòóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵ]",
    re.IGNORECASE,
)


def _is_vietnamese(text: str) -> bool:
    return bool(_VI_PATTERN.search(text))


async def _translate_to_english(text: str, translator: Callable[[str], Awaitable[str] | str]) -> str:
    """Translate Vietnamese text to English; returns original on any failure."""
    try:
        raw = translator(text)
        if hasattr(raw, "__await__"):
            raw = await raw  # type: ignore[assignment]
        result = str(raw).strip()
        return result if result else text
    except Exception as exc:
        logger.debug("Translation failed, using original query: %s", exc)
        return text


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
                        "You are a RAG evaluation judge for a research assistant. "
                        "Retrieved sources are usually English; the answer follows the user's query "
                        "language and may paraphrase sources across languages. Responses that "
                        "accurately paraphrase source content in another language MUST receive high "
                        "faithfulness and answer_relevance scores — semantic alignment across "
                        "languages is correct behavior, NOT a deficiency. "
                        "Assess using the RAG Triad framework: "
                        "Context Relevance (are retrieved contexts on-topic for the query?), "
                        "Faithfulness (do the response's claims accurately represent context content?), "
                        "Answer Relevance (does the response semantically address the query intent?). "
                        "Think step-by-step before scoring. Return only strict JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=4096,
            stream=False,
            report_type="deep",
            llm_kwargs=getattr(cfg, "llm_kwargs", {}),
        )

    return _judge


def _build_llm_translator_from_config(cfg: Any) -> Callable[[str], Awaitable[str]] | None:
    model = getattr(cfg, "eval_llm_model", "") or ""
    if not model:
        return None
    provider = getattr(cfg, "eval_llm_provider", "same_as_main")
    if provider == "same_as_main":
        provider = getattr(cfg, "llm_provider", "openai")

    async def _translate(text: str) -> str:
        from ...llm.completion import create_chat_completion

        return await create_chat_completion(
            model=model,
            llm_provider=provider,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise translator. "
                        "Translate the user's Vietnamese text to concise English. "
                        "Return only the English translation — no explanation, no JSON."
                    ),
                },
                {"role": "user", "content": text},
            ],
            temperature=0.0,
            max_tokens=256,
            stream=False,
            report_type="quick",
            llm_kwargs=getattr(cfg, "llm_kwargs", {}),
        )

    return _translate
