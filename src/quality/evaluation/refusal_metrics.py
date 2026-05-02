from __future__ import annotations

from collections.abc import Sequence

from src.quality.evaluation.generation_metrics import source_scope_adherence_metric
from src.quality.evaluation.metrics import (
    extract_information_claims,
    label_from_score,
    lexical_similarity,
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
    normalized = strip_accents(response.lower())
    return any(marker in normalized for marker in _REFUSAL_MARKERS)


def detect_clarification_request(response: str) -> bool:
    normalized = strip_accents(response.lower())
    return any(marker in normalized for marker in _CLARIFICATION_MARKERS) or response.strip().endswith("?")


def should_refuse(
    query: str,
    retrieved_contexts: Sequence[RetrievedContext],
    expected_behavior: ExpectedBehavior = "answer",
    source_scope: bool | None = None,
) -> bool:
    if expected_behavior == "refuse":
        return True
    if expected_behavior == "ask_clarification":
        return False
    if source_scope is False:
        return True
    if not retrieved_contexts:
        return True
    best = max(lexical_similarity(query, context.text) for context in retrieved_contexts)
    return best < 0.06


def refusal_accuracy(
    expected_behavior: ExpectedBehavior,
    response: str,
    *,
    thresholds: EvaluationThresholds | None = None,
) -> MetricResult:
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
    response = input_data.generated_output.response
    must_refuse = should_refuse(
        input_data.query,
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


def source_scope_adherence(response: str, contexts: Sequence[RetrievedContext]) -> MetricResult:
    return source_scope_adherence_metric(response, contexts)


def vietnamese_quality_check(response: str, expected_language: str = "mixed") -> MetricResult:
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
    has_mojibake = any(marker in response for marker in ("Ã", "Ä", "áº", "á»"))
    too_long = any(len(sentence.split()) > 70 for sentence in sentences)
    vague_translation = any(marker in normalized for marker in ("may hoc sau", "hoc may sau")) and "deep learning" in normalized
    penalties = sum([has_mojibake, too_long, vague_translation])
    score = max(0.0, 1.0 - (penalties * 0.34))
    return MetricResult(
        name="vietnamese_quality_check",
        score=round(score, 4),
        label=label_from_score(score, 0.80, 0.65),
        method="deterministic",
        reason="Checked basic Vietnamese clarity, encoding, and technical-term translation issues.",
        details={
            "has_mojibake": has_mojibake,
            "has_overlong_sentence": too_long,
            "possible_term_mistranslation": vague_translation,
        },
    )
