from __future__ import annotations

import json
from collections import Counter

from src.quality.evaluation.schemas import EvaluationResult, EvaluationRunSummary


def evaluation_result_to_json(result: EvaluationResult) -> str:
    return json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2)


def evaluation_summary_to_json(summary: EvaluationRunSummary) -> str:
    return json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2)


def render_result_markdown(result: EvaluationResult) -> str:
    lines = [
        f"# Evaluation Result: {result.sample_id}",
        "",
        f"- Overall score: {result.overall_score:.3f}",
        f"- Status: {result.label.upper()}",
        "",
        "## Metrics",
        "",
        "| Metric | Score | Label | Method | Reason |",
        "| --- | ---: | --- | --- | --- |",
    ]
    for metric in result.metrics.values():
        score = "-" if metric.score is None else f"{metric.score:.3f}"
        reason = metric.reason.replace("|", "\\|")
        lines.append(f"| {metric.name} | {score} | {metric.label} | {metric.method} | {reason} |")

    if result.recommendations:
        lines.extend(["", "## Recommended Fixes", ""])
        lines.extend(f"- {item}" for item in result.recommendations)
    return "\n".join(lines)


def render_summary_markdown(summary: EvaluationRunSummary) -> str:
    lines = [
        f"# Evaluation Run: {summary.run_id}",
        "",
        f"- Created at: {summary.created_at}",
        f"- Samples: {summary.sample_count}",
        f"- Overall score: {summary.overall_score:.3f}",
        f"- Status: {summary.label.upper()}",
        "",
        "## Metric Summary",
        "",
        "| Sample | Score | Label | Failed Metrics |",
        "| --- | ---: | --- | --- |",
    ]
    for result in summary.results:
        failed = [name for name, metric in result.metrics.items() if metric.label == "fail"]
        lines.append(
            f"| {result.sample_id} | {result.overall_score:.3f} | "
            f"{result.label} | {', '.join(failed) or '-'} |"
        )

    if summary.failed_samples:
        lines.extend(["", "## Failed Samples", ""])
        lines.extend(f"- {sample_id}" for sample_id in summary.failed_samples)

    if summary.top_failure_modes:
        lines.extend(["", "## Top Failure Modes", ""])
        lines.extend(f"- {mode}" for mode in summary.top_failure_modes)

    if summary.recommendations:
        lines.extend(["", "## Recommended Fixes", ""])
        lines.extend(f"- {item}" for item in summary.recommendations)
    return "\n".join(lines)


def summarize_failure_modes(results: list[EvaluationResult]) -> list[str]:
    counter: Counter[str] = Counter()
    for result in results:
        for name, metric in result.metrics.items():
            if metric.label == "fail":
                counter[name] += 1
    return [f"{name}: {count}" for name, count in counter.most_common(5)]
