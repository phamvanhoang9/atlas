from src.quality.evaluation.refusal_metrics import (
    detect_refusal,
    over_answering_rate,
    refusal_accuracy,
    should_refuse,
)
from src.quality.evaluation.schemas import EvaluationInput, GeneratedOutput


def test_detect_refusal_english_and_vietnamese() -> None:
    assert detect_refusal("I cannot answer because there is not enough information.")
    assert detect_refusal("Khong du thong tin trong nguon da cung cap.")


def test_refusal_accuracy_for_expected_refuse() -> None:
    result = refusal_accuracy("refuse", "I cannot answer because the evidence is insufficient.")

    assert result.score == 1.0
    assert result.label == "pass"


def test_should_refuse_without_context() -> None:
    assert should_refuse("unknown query", [], "answer")


def test_over_answering_rate_flags_claims_when_refusal_expected() -> None:
    input_data = EvaluationInput(
        query="Tell me private data",
        expected_behavior="refuse",
        retrieved_contexts=[],
        generated_output=GeneratedOutput(response="The private value is definitely 12345."),
    )

    result = over_answering_rate(input_data)

    assert result.score == 1.0
    assert result.label == "fail"
