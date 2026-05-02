from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


ExpectedBehavior = Literal["answer", "refuse", "ask_clarification"]
MetricLabel = Literal["pass", "warn", "fail", "skipped"]


class EvaluationRubric(BaseModel):
    model_config = ConfigDict(extra="allow")

    must_include: list[str] = Field(default_factory=list)
    must_not_include: list[str] = Field(default_factory=list)
    domain: Literal["qa", "paper_recommendation", "deep_analysis"] = "qa"
    language: Literal["vi", "en", "mixed"] = "mixed"
    difficulty: Literal["easy", "medium", "hard"] = "medium"
    out_of_scope: bool = False


class EvaluationSample(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    query: str
    expected_behavior: ExpectedBehavior = "answer"
    ground_truth_answer: str | None = None
    ground_truth_context: list[str] | None = None
    source_urls: list[str] = Field(default_factory=list)
    rubric: EvaluationRubric = Field(default_factory=EvaluationRubric)


class RetrievedContext(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str
    text: str
    source_url: str | None = None
    title: str | None = None
    score: float | None = None
    rank: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class GeneratedOutput(BaseModel):
    model_config = ConfigDict(extra="allow")

    response: str
    citations: list[str] = Field(default_factory=list)
    language: Literal["vi", "en", "mixed"] = "mixed"
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationThresholds(BaseModel):
    model_config = ConfigDict(extra="allow")

    min_faithfulness: float = 0.85
    warn_faithfulness: float = 0.70
    min_answer_relevance: float = 0.80
    min_context_relevance: float = 0.75
    min_context_recall: float = 0.75
    min_ndcg: float = 0.75
    max_unsupported_claims: int = 1
    min_refusal_accuracy: float = 1.0


class EvaluationInput(BaseModel):
    model_config = ConfigDict(extra="allow")

    sample_id: str | None = None
    query: str
    retrieved_contexts: list[RetrievedContext] = Field(default_factory=list)
    generated_output: GeneratedOutput
    expected_behavior: ExpectedBehavior = "answer"
    ground_truth_answer: str | None = None
    ground_truth_context: list[str] | None = None
    source_urls: list[str] = Field(default_factory=list)
    rubric: EvaluationRubric = Field(default_factory=EvaluationRubric)
    relevant_context_ids: list[str] | None = None
    relevance_scores: dict[str, float] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_sample(
        cls,
        sample: EvaluationSample,
        retrieved_contexts: list[RetrievedContext],
        generated_output: GeneratedOutput,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> "EvaluationInput":
        return cls(
            sample_id=sample.id,
            query=sample.query,
            retrieved_contexts=retrieved_contexts,
            generated_output=generated_output,
            expected_behavior=sample.expected_behavior,
            ground_truth_answer=sample.ground_truth_answer,
            ground_truth_context=sample.ground_truth_context,
            source_urls=sample.source_urls,
            rubric=sample.rubric,
            metadata=metadata or {},
        )


class MetricResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    name: str
    score: float | None = None
    label: MetricLabel = "skipped"
    method: str = "deterministic"
    reason: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    details: dict[str, Any] = Field(default_factory=dict)


class EvaluationResult(BaseModel):
    model_config = ConfigDict(extra="allow")

    sample_id: str
    query: str
    overall_score: float
    label: Literal["pass", "warn", "fail"]
    passed: bool
    metrics: dict[str, MetricResult] = Field(default_factory=dict)
    recommendations: list[str] = Field(default_factory=list)
    quality_check: dict[str, Any] | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class EvaluationRunSummary(BaseModel):
    model_config = ConfigDict(extra="allow")

    run_id: str
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    sample_count: int
    overall_score: float
    label: Literal["pass", "warn", "fail"]
    passed: bool
    results: list[EvaluationResult] = Field(default_factory=list)
    failed_samples: list[str] = Field(default_factory=list)
    top_failure_modes: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
