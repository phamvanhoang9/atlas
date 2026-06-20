"""Retrieval-quality metrics: ranking metrics (recall/precision/nDCG) and context relevance.

Ranking metrics (recall_at_k, precision_at_k, ndcg_at_k) are pure functions
over ids and need ground-truth relevance to be meaningful; the *_metric
wrappers return "skipped" MetricResults when that ground truth is absent.
context_relevance_llm prefers an LLM judge, falling back to a bilingual
lexical-coverage heuristic.
"""

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
    """Return the fraction of relevant_ids found within the top k retrieved_ids."""
    relevant = set(relevant_ids)
    if not relevant or k <= 0:
        return 0.0
    retrieved = set(retrieved_ids[:k])
    return round(len(retrieved.intersection(relevant)) / len(relevant), 4)


def precision_at_k(retrieved_ids: Sequence[str], relevant_ids: Sequence[str], k: int) -> float:
    """Return the fraction of the top k retrieved_ids that are relevant."""
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
    """Compute normalized discounted cumulative gain at rank k.

    Args:
      retrieved_ids: The ranked list of retrieved item ids.
      relevance_scores: Graded relevance per item id (dict), or a parallel
        sequence of relevance scores aligned with retrieved_ids.
      k: The rank cutoff.

    Returns:
      nDCG@k in [0, 1]; 0.0 if k <= 0, retrieved_ids is empty, or the ideal
      DCG is 0 (no relevance signal).
    """
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
    """Score the fraction of ground-truth context snippets matched by retrieval.

    A ground-truth snippet counts as matched if its lexical_similarity to
    any retrieved context exceeds similarity_threshold.

    Args:
      retrieved_contexts: The contexts actually retrieved for the query.
      ground_truth_context: The expected context snippets, if known.
      similarity_threshold: Minimum lexical_similarity to count as a match.

    Returns:
      A MetricResult named "context_recall", "skipped" if no ground truth
      was provided.
    """
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
    """Score how relevant retrieved_contexts are to query without an LLM, rank-weighted.

    Each context's relevance is the max of lexical_similarity and
    bilingual_query_coverage, then averaged with rank-based weighting
    (1/(rank+1)) so earlier-ranked contexts count more.
    """
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
    """Score whether retrieved_contexts are relevant and sufficient for query.

    Uses the LLM judge if one is configured and returns a usable score;
    otherwise falls back to deterministic_context_relevance.

    Args:
      query: The user query.
      retrieved_contexts: The contexts retrieved for the query.
      judge: Optional LLM judge callable.
      thresholds: Pass/warn thresholds; defaults to EvaluationThresholds().

    Returns:
      A MetricResult named "context_relevance".
    """
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
    """Wrap precision_at_k as a MetricResult, "skipped" if relevant_ids is absent."""
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
    """Wrap recall_at_k as a MetricResult, "skipped" if relevant_ids is absent."""
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
    """Wrap ndcg_at_k as a MetricResult, "skipped" if relevance_scores is absent."""
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
    """Score the fraction of retrieved_contexts that are off-topic ("noisy") for query.

    A context counts as noisy when its bilingual_query_coverage against
    query falls below relevance_threshold.

    Returns:
      A MetricResult named "noise_ratio"; higher scores mean more noise
      (this metric is inverted when folded into an overall average).
    """
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
