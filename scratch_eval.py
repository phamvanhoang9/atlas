import asyncio
import json
from pathlib import Path

from src.quality.evaluation.evaluator import EvaluationRunner, load_golden_dataset
from src.quality.evaluation.schemas import GeneratedOutput
from src.quality.evaluation.report import render_summary_markdown

def main():
    dataset_path = Path("examples/evaluation/golden_dataset.jsonl")
    samples = load_golden_dataset(dataset_path)

    outputs = {}
    for sample in samples:
        # Mock answers with citations to pass citation_coverage
        simulated_response = sample.ground_truth_answer or ""
        if sample.expected_behavior == "answer":
            simulated_response += " [1]" # Add fake citation
        outputs[sample.id] = GeneratedOutput(response=simulated_response)

    runner = EvaluationRunner(enable_ragas=False)
    summary = runner.evaluate_dataset(samples, outputs=outputs)
    
    print(render_summary_markdown(summary))
    
    print("\n--- Detailed Metrics for Sample 1 ---")
    for name, metric in summary.results[0].metrics.items():
        print(f"{name}: {metric.score} ({metric.label}) - {metric.reason}")

if __name__ == "__main__":
    main()
