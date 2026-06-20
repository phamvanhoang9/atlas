"""Safety/behavior metrics: refusal detection, over-answering, and scope adherence.

Checks whether the response refused/asked for clarification when it should
have (or answered when it shouldn't have), using marker-string detection
rather than an LLM, plus a basic Vietnamese clarity heuristic.
"""

from __future__ import annotations

from collections.abc import Sequence

from src.quality.evaluation.generation_metrics import source_scope_adherence_metric
from src.quality.evaluation.metrics import (
    bilingual_query_coverage,
    extract_information_claims,
    label_from_score,
    strip_accents,
)
from src.quality.evaluation.schemas import (
    EvaluationInput,
    EvaluationThresholds,
    ExpectedBehavior,
    MetricResult,
    RetrievedContext,
)


_REFUSAL_MARKERS = (
    "khong du thong tin",
    "khong co du thong tin",
    "khong the tra loi",
    "khong co bang chung",
    "ngoai pham vi",
    "toi khong the",
    "i cannot answer",
    "i can't answer",
    "not enough information",
    "insufficient evidence",
    "outside the scope",
)

_CLARIFICATION_MARKERS = (
    "ban co the lam ro",
    "vui long lam ro",
    "can them thong tin",
    "could you clarify",
    "please clarify",
    "need more details",
)


def detect_refusal(response: str) -> bool:
    """Check whether response contains a refusal marker (Vietnamese or English)."""
    normalized = strip_accents(response.lower())
    return any(marker in normalized for marker in _REFUSAL_MARKERS)


def detect_clarification_request(response: str) -> bool:
    """Check whether response asks the user for clarification, or simply ends in a question."""
    normalized = strip_accents(response.lower())
    return any(marker in normalized for marker in _CLARIFICATION_MARKERS) or response.strip().endswith("?")


def should_refuse(
    query: str,
    retrieved_contexts: Sequence[RetrievedContext],
    expected_behavior: ExpectedBehavior = "answer",
    source_scope: bool | None = None,
) -> bool:
    """Determine whether a response to query should have refused, given the available evidence.

    Args:
      query: The user query.
      retrieved_contexts: The contexts retrieved for the query.
      expected_behavior: The rubric's expected behavior; "refuse" and
        "ask_clarification" short-circuit the evidence check.
      source_scope: Optional override — False forces a refusal (e.g. rubric
        marks the query as out_of_scope).

    Returns:
      True if the response should have refused to answer.
    """
    if expected_behavior == "refuse":
        return True
    if expected_behavior == "ask_clarification":
        return False
    if source_scope is False:
        return True
    if not retrieved_contexts:
        return True
    # bilingual_query_coverage handles Vietnamese queries vs English sources;
    # falls back to English technical-term matching when lexical coverage is low.
    best = max(bilingual_query_coverage(query, context.text) for context in retrieved_contexts)
    return best < 0.20


def refusal_accuracy(
    expected_behavior: ExpectedBehavior,
    response: str,
    *,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
    """Score whether response's refuse/clarify/answer behavior matches expected_behavior.

    Args:
      expected_behavior: The rubric's expected behavior for this sample.
      response: The generated response to check.
      thresholds: Supplies min_refusal_accuracy; defaults to EvaluationThresholds().

    Returns:
      A MetricResult named "refusal_accuracy" with a binary 0.0/1.0 score.
    """
    thresholds = thresholds or EvaluationThresholds()
    refused = detect_refusal(response)
    clarified = detect_clarification_request(response)
    if expected_behavior == "refuse":
        score = 1.0 if refused else 0.0
        reason = "Response refused as expected." if refused else "Response should refuse but did not."
    elif expected_behavior == "ask_clarification":
        score = 1.0 if clarified and not extract_information_claims(response) else 0.0
        reason = (
            "Response asked for clarification as expected."
            if score == 1.0
            else "Response should ask for clarification without inventing an answer."
        )
    else:
        score = 0.0 if refused else 1.0
        reason = "Response answered as expected." if score == 1.0 else "Response refused an answerable query."

    return MetricResult(
        name="refusal_accuracy",
        score=score,
        label=label_from_score(score, thresholds.min_refusal_accuracy),
        method="deterministic",
        reason=reason,
        details={"detected_refusal": refused, "detected_clarification": clarified},
    )


def over_answering_rate(input_data: EvaluationInput) -> MetricResult:
    """Detect whether the response answered with claims when it should have refused.

    Returns:
      A MetricResult named "over_answering_rate"; score 1.0 ("fail") if the
      response should have refused but instead made factual claims without
      refusing, otherwise 0.0 ("pass").
    """
    response = input_data.generated_output.response
    # Use English-translated query for coverage check when available so
    # Vietnamese tokens don't register as near-zero against English contexts.
    query = input_data.metadata.get("query_en") or input_data.query
    must_refuse = should_refuse(
        query,
        input_data.retrieved_contexts,
        input_data.expected_behavior,
        source_scope=not input_data.rubric.out_of_scope,
    )
    has_claims = bool(extract_information_claims(response))
    over_answered = must_refuse and has_claims and not detect_refusal(response)
    score = 1.0 if over_answered else 0.0
    return MetricResult(
        name="over_answering_rate",
        score=score,
        label="fail" if over_answered else "pass",
        method="deterministic",
        reason="Response over-answered without enough evidence." if over_answered else "No over-answering detected.",
        details={"should_refuse": must_refuse, "information_claims": has_claims},
    )


def source_scope_adherence(
    response: str,
    contexts: Sequence[RetrievedContext],
    *,
    faithfulness_result: "MetricResult | None" = None,
) -> MetricResult:
    """Score the fraction of response's claims that stay within contexts' scope.

    Thin wrapper around source_scope_adherence_metric, kept in this module
    alongside the other safety/behavior metrics.
    """
    return source_scope_adherence_metric(response, contexts, faithfulness_result=faithfulness_result)


def vietnamese_quality_check(response: str, expected_language: str = "mixed") -> MetricResult:
    """Run basic Vietnamese-clarity heuristics on response (overlong sentences, term mistranslation).

    Args:
      response: The generated response to check.
      expected_language: The rubric's expected language; the check is
        skipped for purely "en" outputs.

    Returns:
      A MetricResult named "vietnamese_quality_check", "skipped" if
      expected_language is "en".
    """
    if expected_language not in {"vi", "mixed"}:
        return MetricResult(
            name="vietnamese_quality_check",
            score=None,
            label="skipped",
            method="not_applicable",
            reason="Vietnamese quality check applies only to Vietnamese or mixed outputs.",
        )

    normalized = strip_accents(response.lower())
    sentences = [sentence for sentence in response.split(".") if sentence.strip()]
    too_long = any(len(sentence.split()) > 120 for sentence in sentences)
    vague_translation = any(marker in normalized for marker in ("may hoc sau", "hoc may sau")) and "deep learning" in normalized
    penalties = sum([too_long, vague_translation])
    score = max(0.0, 1.0 - (penalties * 0.34))
    return MetricResult(
        name="vietnamese_quality_check",
        score=round(score, 4),
        label=label_from_score(score, 0.80, 0.65),
        method="deterministic",
        reason="Checked basic Vietnamese clarity and technical-term translation issues.",
        details={
            "has_overlong_sentence": too_long,
            "possible_term_mistranslation": vague_translation,
        },
    )
