"""Offline deterministic evaluation benchmark — no network, no LLM, no RAGAS.

Loads fixture samples from ``evals/benchmark.json`` and runs the real
``EvaluationRunner`` over each with the LLM judge, translator, and RAGAS
disabled, so every metric uses its deterministic/lexical implementation.
Each sample asserts expected labels for deterministic metrics only; LLM-judge
metrics (context_relevance, answer_relevance) fall back to pessimistic lexical
proxies offline and are reported but not asserted. For full-fidelity online
evaluation use ``run_eval.py``.

Usage:
    python run_benchmark.py            # exit 0 when all expectations hold
    python run_benchmark.py -v         # also print every metric per sample
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
from pathlib import Path

if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

BENCHMARK_PATH = Path(__file__).resolve().parent / "evals" / "benchmark.json"


async def run() -> int:
    parser = argparse.ArgumentParser(description="Run the offline ATLAS evaluation benchmark.")
    parser.add_argument("-v", "--verbose", action="store_true", help="Print every metric per sample.")
    args = parser.parse_args()

    from src.quality.evaluation.evaluator import EvaluationRunner
    from src.quality.evaluation.schemas import EvaluationInput

    payload = json.loads(BENCHMARK_PATH.read_text(encoding="utf-8"))
    samples = payload["samples"]
    runner = EvaluationRunner(judge=None, translator=None, enable_ragas=False)

    failures: list[str] = []
    print(f"ATLAS offline benchmark — {len(samples)} samples ({BENCHMARK_PATH.name})")
    print("=" * 78)

    for sample in samples:
        input_data = EvaluationInput.model_validate(sample["input"])
        result = await runner.aevaluate_single(input_data)

        sample_failures: list[str] = []
        for metric_name, expected_label in sample["expected_metrics"].items():
            metric = result.metrics.get(metric_name)
            actual = metric.label if metric else "missing"
            if actual != expected_label:
                sample_failures.append(f"{metric_name}: expected {expected_label}, got {actual}")

        status = "OK " if not sample_failures else "FAIL"
        print(f"[{status}] {sample['id']:<22} overall={result.overall_score:.3f} ({result.label})")
        if args.verbose:
            for name, metric in result.metrics.items():
                asserted = "*" if name in sample["expected_metrics"] else " "
                print(f"      {asserted} {name:<28} score={metric.score!s:<8} label={metric.label}")
        for failure in sample_failures:
            print(f"      !! {failure}")
        failures.extend(f"{sample['id']}: {failure}" for failure in sample_failures)

    print("=" * 78)
    if failures:
        print(f"BENCHMARK FAILED — {len(failures)} expectation(s) not met:")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("BENCHMARK PASSED — all deterministic metric expectations hold.")
    return 0


if __name__ == "__main__":
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        sys.exit(loop.run_until_complete(run()))
    finally:
        loop.close()
