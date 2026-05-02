from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable, Sequence
from pathlib import Path
from typing import Any

from src.quality import ReportValidator
from src.quality.evaluation.generation_metrics import (
    answer_correctness_metric,
    answer_relevance_llm,
    citation_coverage_metric,
    conversational_faithfulness_llm,
    unsupported_claim_count_metric,
)
from src.quality.evaluation.ragas_adapter import RagasAdapter
from src.quality.evaluation.refusal_metrics import (
    over_answering_rate,
    refusal_accuracy,
    source_scope_adherence,
    vietnamese_quality_check,
)
from src.quality.evaluation.report import summarize_failure_modes
from src.quality.evaluation.retrieval_metrics import (
    context_precision_metric,
    context_recall_from_ground_truth,
    context_relevance_llm,
    ndcg_at_k_metric,
    noise_ratio_metric,
    recall_at_k_metric,
)
from src.quality.evaluation.schemas import (
    EvaluationInput,
    EvaluationResult,
    EvaluationRunSummary,
    EvaluationSample,
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

    def evaluate_single(self, input_data: EvaluationInput) -> EvaluationResult:
        return _run_blocking(self.aevaluate_single(input_data))

    async def aevaluate_single(self, input_data: EvaluationInput) -> EvaluationResult:
        retrieved_ids = [context.id for context in input_data.retrieved_contexts]
        metrics: dict[str, MetricResult] = {}

        metrics["context_relevance"] = await context_relevance_llm(
            input_data.query,
            input_data.retrieved_contexts,
            judge=self.judge,
            thresholds=self.thresholds,
        )
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

        response = input_data.generated_output.response
        metrics["answer_relevance"] = await answer_relevance_llm(
            input_data.query,
            response,
            judge=self.judge,
            thresholds=self.thresholds,
        )
        metrics["answer_correctness"] = answer_correctness_metric(
            response,
            input_data.ground_truth_answer,
            thresholds=self.thresholds,
        )
        metrics["faithfulness"] = await conversational_faithfulness_llm(
            response,
            input_data.retrieved_contexts,
            judge=self.judge,
            thresholds=self.thresholds,
        )
        metrics["unsupported_claim_count"] = unsupported_claim_count_metric(
            metrics["faithfulness"],
            thresholds=self.thresholds,
        )
        metrics["citation_coverage"] = citation_coverage_metric(response, metrics["faithfulness"])

        metrics["refusal_accuracy"] = refusal_accuracy(
            input_data.expected_behavior,
            response,
            thresholds=self.thresholds,
        )
        metrics["over_answering_rate"] = over_answering_rate(input_data)
        metrics["source_scope_adherence"] = source_scope_adherence(response, input_data.retrieved_contexts)
        metrics["vietnamese_quality_check"] = vietnamese_quality_check(
            response,
            input_data.rubric.language,
        )

        if self.ragas is not None:
            metrics.update(await self.ragas.evaluate(input_data))

        quality_check = ReportValidator().validate(
            response,
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

    def evaluate_dataset(
        self,
        samples: list[EvaluationSample],
        *,
        outputs: dict[str, GeneratedOutput] | None = None,
        retrieved_contexts: dict[str, list[RetrievedContext]] | None = None,
    ) -> EvaluationRunSummary:
        return _run_blocking(
            self.aevaluate_dataset(samples, outputs=outputs, retrieved_contexts=retrieved_contexts)
        )

    async def aevaluate_dataset(
        self,
        samples: list[EvaluationSample],
        *,
        outputs: dict[str, GeneratedOutput] | None = None,
        retrieved_contexts: dict[str, list[RetrievedContext]] | None = None,
    ) -> EvaluationRunSummary:
        outputs = outputs or {}
        retrieved_contexts = retrieved_contexts or {}
        results: list[EvaluationResult] = []
        for sample in samples:
            generated = outputs.get(sample.id) or GeneratedOutput(response="")
            contexts = retrieved_contexts.get(sample.id) or [
                RetrievedContext(id=str(index), text=text)
                for index, text in enumerate(sample.ground_truth_context or [])
            ]
            result = await self.aevaluate_single(
                EvaluationInput.from_sample(sample, contexts, generated)
            )
            results.append(result)
        return _summary_from_results(results)

    def evaluate_history_entry(self, history_manager: Any, history_id: str) -> EvaluationResult | None:
        entry = history_manager.get_entry(history_id)
        if entry is None:
            return None
        input_data = EvaluationInput(
            sample_id=history_id,
            query=entry["query"],
            retrieved_contexts=[],
            generated_output=GeneratedOutput(response=entry.get("report", "")),
            expected_behavior="answer",
            metadata={"mode": entry.get("mode"), "history_id": history_id},
        )
        return self.evaluate_single(input_data)


def load_golden_dataset(path: str | Path) -> list[EvaluationSample]:
    dataset_path = Path(path)
    rows: list[EvaluationSample] = []
    for line_number, line in enumerate(dataset_path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            rows.append(EvaluationSample.model_validate_json(line))
        except ValueError as exc:
            raise ValueError(f"Invalid evaluation sample at line {line_number}: {exc}") from exc
    return rows


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


def _run_blocking(coro: Awaitable[Any]) -> Any:
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(coro)
    raise RuntimeError("Use the async aevaluate_* methods when an event loop is already running.")


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


def _summary_from_results(results: list[EvaluationResult]) -> EvaluationRunSummary:
    overall = round(sum(result.overall_score for result in results) / len(results), 4) if results else 0.0
    label = "fail" if any(result.label == "fail" for result in results) else "warn" if overall < 0.82 else "pass"
    failed = [result.sample_id for result in results if result.label == "fail"]
    failure_modes = summarize_failure_modes(results)
    return EvaluationRunSummary(
        run_id=str(uuid.uuid4()),
        sample_count=len(results),
        overall_score=overall,
        label=label,
        passed=label == "pass",
        results=results,
        failed_samples=failed,
        top_failure_modes=failure_modes,
        recommendations=_summary_recommendations(failure_modes),
    )


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


def _summary_recommendations(failure_modes: list[str]) -> list[str]:
    names = {item.split(":", 1)[0] for item in failure_modes}
    synthetic = {
        name: MetricResult(name=name, label="fail")
        for name in names
    }
    return _recommendations(synthetic)


def _build_llm_judge_from_config(cfg: Any) -> Callable[[str], Awaitable[str]] | None:
    model = getattr(cfg, "eval_llm_model", "") or ""
    if not model:
        return None
    provider = getattr(cfg, "eval_llm_provider", "same_as_main")
    if provider == "same_as_main":
        provider = getattr(cfg, "llm_provider", "openai")

    async def _judge(prompt: str) -> str:
        from src.llm.completion import create_chat_completion

        return await create_chat_completion(
            model=model,
            llm_provider=provider,
            messages=[
                {"role": "system", "content": "You are an evaluation judge. Return only strict JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.0,
            max_tokens=1200,
            stream=False,
            report_type="hỏi đáp",
            llm_kwargs=getattr(cfg, "llm_kwargs", {}),
        )

    return _judge


if __name__ == "__main__":
    import argparse

    from src.quality.evaluation.report import evaluation_summary_to_json, render_summary_markdown

    parser = argparse.ArgumentParser(description="Run ATLAS golden dataset evaluation.")
    parser.add_argument("dataset", help="Path to a JSONL golden evaluation dataset.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown instead of JSON.")
    args = parser.parse_args()

    runner = EvaluationRunner(enable_ragas=False)
    summary = runner.evaluate_dataset(load_golden_dataset(args.dataset))
    print(render_summary_markdown(summary) if args.markdown else evaluation_summary_to_json(summary))
