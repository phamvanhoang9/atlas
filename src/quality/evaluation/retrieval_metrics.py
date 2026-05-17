from __future__ import annotations

from collections.abc import Sequence

from src.quality.evaluation.metrics import (
    JudgeCallable,
    bilingual_query_coverage,
    build_judge_prompt,
    clamp,
    dcg,
    label_from_score,
    lexical_similarity,
    max_similarity,
    maybe_call_judge,
    normalize_label,
)
from src.quality.evaluation.schemas import EvaluationThresholds, MetricResult, RetrievedContext


def recall_at_k(retrieved_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    relevant = set(relevant_ids)
    if not relevant or k <= 0:
        return 0.0
    retrieved = set(retrieved_ids[:k])
    return round(len(retrieved.intersection(relevant)) / len(relevant), 4)


def precision_at_k(retrieved_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    if k <= 0:
        return 0.0
    relevant = set(relevant_ids)
    retrieved = list(retrieved_ids[:k])
    if not retrieved:
        return 0.0
    return round(sum(1 for item in retrieved if item in relevant) / min(k, len(retrieved)), 4)


def ndcg_at_k(
    retrieved_ids: Sequence[str],
    relevance_scores: dict[str, float] | Sequence[float],
    k: int,
) -> float:
    if k <= 0 or not retrieved_ids:
        return 0.0
    if isinstance(relevance_scores, dict):
        ranked_scores = [float(relevance_scores.get(item, 0.0)) for item in retrieved_ids[:k]]
        ideal_scores = sorted((float(score) for score in relevance_scores.values()), reverse=True)[:k]
    else:
        ranked_scores = [float(score) for score in list(relevance_scores)[:k]]
        ideal_scores = sorted((float(score) for score in relevance_scores), reverse=True)[:k]
    ideal = dcg(ideal_scores)
    if ideal == 0:
        return 0.0
    return round(clamp(dcg(ranked_scores) / ideal), 4)


def context_recall_from_ground_truth(
    retrieved_contexts: Sequence[RetrievedContext],
    ground_truth_context: Sequence[str] | None,
    *,
    similarity_threshold: float = 0.28,
) -> MetricResult:
    if not ground_truth_context:
        return MetricResult(
            name="context_recall",
            score=None,
            label="skipped",
            method="not_applicable",
            reason="No ground_truth_context was provided.",
        )

    retrieved_texts = [context.text for context in retrieved_contexts]
    matched = [
        truth
        for truth in ground_truth_context
        if max_similarity(truth, retrieved_texts) >= similarity_threshold
    ]
    score = len(matched) / len(ground_truth_context)
    return MetricResult(
        name="context_recall",
        score=round(score, 4),
        label=label_from_score(score, 0.75),
        method="embedding_proxy",
        reason=f"Matched {len(matched)} of {len(ground_truth_context)} ground-truth contexts.",
        details={"matched_count": len(matched), "ground_truth_count": len(ground_truth_context)},
    )


def deterministic_context_relevance(query: str, retrieved_contexts: Sequence[RetrievedContext]) -> float:
    if not retrieved_contexts:
        return 0.0
    # Use bilingual_query_coverage so Vietnamese queries score positively against
    # English-language contexts that share technical terms with the query.
    scores = [
        max(lexical_similarity(query, ctx.text), bilingual_query_coverage(query, ctx.text, threshold=0.25))
        for ctx in retrieved_contexts
    ]
    top_weighted = sum(score / (rank + 1) for rank, score in enumerate(scores))
    normalizer = sum(1 / (rank + 1) for rank in range(len(scores)))
    return round(clamp(top_weighted / normalizer), 4)


async def context_relevance_llm(
    query: str,
    retrieved_contexts: Sequence[RetrievedContext],
    *,
    judge: JudgeCallable | None = None,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
    thresholds = thresholds or EvaluationThresholds()
    contexts = [context.text for context in retrieved_contexts]
    prompt = build_judge_prompt(
        task="Score whether retrieved contexts are relevant and sufficient for the query.",
        query=query,
        contexts=contexts,
    )
    judged = await maybe_call_judge(judge, prompt)
    if judged and isinstance(judged.get("score"), int | float):
        score = clamp(float(judged["score"]))
        return MetricResult(
            name="context_relevance",
            score=round(score, 4),
            label=normalize_label(judged.get("label"), label_from_score(score, thresholds.min_context_relevance)),
            method="llm_judge",
            reason=str(judged.get("reason", "")),
            evidence=list(judged.get("evidence", [])) if isinstance(judged.get("evidence"), list) else [],
        )

    score = deterministic_context_relevance(query, retrieved_contexts)
    return MetricResult(
        name="context_relevance",
        score=score,
        label=label_from_score(score, thresholds.min_context_relevance),
        method="embedding_proxy",
        reason="Lexical similarity fallback was used because no usable LLM judge result was available.",
        details={"context_count": len(retrieved_contexts)},
    )


def context_precision_metric(
    retrieved_ids: Sequence[str],
    relevant_ids: Sequence[str] | None,
    *,
    k: int,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
    thresholds = thresholds or EvaluationThresholds()
    if not relevant_ids:
        return MetricResult(
            name="context_precision",
            score=None,
            label="skipped",
            method="not_applicable",
            reason="No relevant_context_ids were provided.",
        )
    score = precision_at_k(retrieved_ids, relevant_ids, k)
    return MetricResult(
        name="context_precision",
        score=score,
        label=label_from_score(score, thresholds.min_context_relevance),
        method="deterministic",
        reason=f"Precision@{k} over provided relevant context ids.",
        details={"k": k},
    )


def recall_at_k_metric(
    retrieved_ids: Sequence[str],
    relevant_ids: Sequence[str] | None,
    *,
    k: int,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
    thresholds = thresholds or EvaluationThresholds()
    if not relevant_ids:
        return MetricResult(
            name=f"recall@{k}",
            score=None,
            label="skipped",
            method="not_applicable",
            reason="No relevant_context_ids were provided.",
        )
    score = recall_at_k(retrieved_ids, relevant_ids, k)
    return MetricResult(
        name=f"recall@{k}",
        score=score,
        label=label_from_score(score, thresholds.min_context_recall),
        method="deterministic",
        reason=f"Recall@{k} over provided relevant context ids.",
        details={"k": k},
    )


def ndcg_at_k_metric(
    retrieved_ids: Sequence[str],
    relevance_scores: dict[str, float] | None,
    *,
    k: int,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
    thresholds = thresholds or EvaluationThresholds()
    if not relevance_scores:
        return MetricResult(
            name=f"ndcg@{k}",
            score=None,
            label="skipped",
            method="not_applicable",
            reason="No graded relevance scores were provided.",
        )
    score = ndcg_at_k(retrieved_ids, relevance_scores, k)
    return MetricResult(
        name=f"ndcg@{k}",
        score=score,
        label=label_from_score(score, thresholds.min_ndcg),
        method="deterministic",
        reason=f"nDCG@{k} over provided graded relevance scores.",
        details={"k": k},
    )


def noise_ratio_metric(
    query: str,
    retrieved_contexts: Sequence[RetrievedContext],
    *,
    relevance_threshold: float = 0.25,
) -> MetricResult:
    if not retrieved_contexts:
        return MetricResult(
            name="noise_ratio",
            score=1.0,
            label="fail",
            method="embedding_proxy",
            reason="No contexts were retrieved.",
        )
    # bilingual_query_coverage handles Vietnamese queries against English sources:
    # falls back to English technical-term matching when lexical coverage is low.
    relevant = [
        context
        for context in retrieved_contexts
        if bilingual_query_coverage(query, context.text, relevance_threshold) >= relevance_threshold
    ]
    noise = 1 - (len(relevant) / len(retrieved_contexts))
    label = "pass" if noise <= 0.30 else "warn" if noise <= 0.55 else "fail"
    return MetricResult(
        name="noise_ratio",
        score=round(noise, 4),
        label=label,
        method="embedding_proxy",
        reason=f"{len(retrieved_contexts) - len(relevant)} of {len(retrieved_contexts)} contexts look noisy.",
        details={"relevant_count": len(relevant), "context_count": len(retrieved_contexts)},
    )
