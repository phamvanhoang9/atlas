import asyncio
from pathlib import Path
from dotenv import load_dotenv

from src.quality.evaluation.evaluator import EvaluationRunner, load_golden_dataset
from src.quality.evaluation.schemas import GeneratedOutput
from src.quality.evaluation.report import render_summary_markdown

class MockConfig:
    enable_evaluation = True
    evaluation_mode = "both"
    eval_llm_model = "gpt-4o-mini"
    eval_llm_provider = "openai"
    llm_kwargs = {}
    eval_fail_thresholds = {}
    eval_top_k = 3

def main():
    load_dotenv()
    dataset_path = Path("examples/evaluation/golden_dataset.jsonl")
    samples = load_golden_dataset(dataset_path)

    outputs = {}
    for sample in samples:
        simulated_response = sample.ground_truth_answer or ""
        if sample.expected_behavior == "answer":
            simulated_response += " [1]"
        outputs[sample.id] = GeneratedOutput(response=simulated_response)

    print("Running evaluation using LLM Judge (gpt-4o-mini)...\n")
    
    runner = EvaluationRunner.from_config(MockConfig())
    summary = runner.evaluate_dataset(samples, outputs=outputs)
    
    print(render_summary_markdown(summary))
    
    print("\n--- Detailed Metrics for Sample 1 ---")
    for name, metric in summary.results[0].metrics.items():
        print(f"{name}: {metric.score} ({metric.label}) - {metric.reason}")

if __name__ == "__main__":
    main()
