import asyncio
import sys
from pathlib import Path
from dotenv import load_dotenv

from src.quality.evaluation.evaluator import EvaluationRunner, load_golden_dataset
from src.quality.evaluation.schemas import GeneratedOutput
from src.quality.evaluation.report import render_summary_markdown
from src.llm.completion import create_chat_completion

class MockConfig:
    enable_evaluation = True
    evaluation_mode = "both"
    eval_llm_model = "gpt-4o-mini"
    eval_llm_provider = "openai"
    llm_provider = "openai"
    llm_kwargs = {}
    eval_fail_thresholds = {}
    eval_top_k = 3

async def run_pipeline():
    sys.stdout.reconfigure(encoding='utf-8')
    load_dotenv()
    dataset_path = Path("examples/evaluation/golden_dataset.jsonl")
    samples = load_golden_dataset(dataset_path)

    # Pick only the first sample
    sample = samples[0]
    print(f"Query: {sample.query}")
    
    context_str = "\n".join(sample.ground_truth_context or [])
    prompt = f"Ngữ cảnh:\n{context_str}\n\nCâu hỏi: {sample.query}\nTrả lời chi tiết dựa trên ngữ cảnh và thêm trích dẫn [1] vào cuối ý chính."
    
    print("\nGenerating real answer using gpt-4o-mini...")
    real_response = await create_chat_completion(
        messages=[
            {"role": "system", "content": "Bạn là trợ lý AI hữu ích."},
            {"role": "user", "content": prompt}
        ],
        model="gpt-4o-mini",
        llm_provider="openai",
        temperature=0.7,
        max_tokens=1000,
        stream=False,
    )
    
    print(f"\nGenerated Answer:\n{real_response}\n")

    outputs = {sample.id: GeneratedOutput(response=real_response)}

    print("Running evaluation using LLM Judge (gpt-4o-mini)...")
    runner = EvaluationRunner.from_config(MockConfig())
    summary = await runner.aevaluate_dataset([sample], outputs=outputs)
    
    print("\n" + render_summary_markdown(summary))
    
    print("\n--- Detailed Metrics for Sample 1 ---")
    for name, metric in summary.results[0].metrics.items():
        print(f"{name}: {metric.score} ({metric.label}) - {metric.reason}")

def main():
    asyncio.run(run_pipeline())

if __name__ == "__main__":
    main()
