"""Quick eval runner — always runs evaluation regardless of ENABLE_EVALUATION env var.

Runs the full online pipeline (search → scrape → report) and the in-workflow
evaluation step against real APIs. For the offline, deterministic benchmark use
``run_benchmark.py`` instead.

Usage:
    python run_eval.py                                  # default query, quick mode
    python run_eval.py deep                             # default query, deep mode
    python run_eval.py research "your query here"       # custom mode and query
    python run_eval.py --all                            # benchmark all 3 modes
"""
import argparse
import asyncio
import io
import logging
import os
import sys

# Force UTF-8 stdout/stderr so non-ASCII output prints correctly on Windows.
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

# Force evaluation on before any src imports read the env var.
os.environ["ENABLE_EVALUATION"] = "true"

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    stream=sys.stdout,
)

# Mode-specific default queries chosen to be unambiguous so Tavily returns
# on-topic inference/latency sources rather than training-optimization ones.
_MODE_QUERIES: dict[str, str] = {
    "quick": "How does Graph RAG differ from traditional RAG?",
    "deep": (
        "Analyze the main techniques for optimizing LLM inference latency: "
        "KV cache, continuous batching, speculative decoding, and quantization"
    ),
    "research": (
        "Recommend recent research papers on optimizing large language model "
        "inference speed (LLM serving, throughput, latency)"
    ),
}

# Canonical ids plus accepted shorthands and deprecated legacy ids (D-004).
_MODE_ALIASES: dict[str, str] = {
    "quick": "quick",
    "research": "research",
    "deep": "deep",
    # English shorthands
    "qa": "quick",
    "paper": "research",
    "analysis": "deep",
    # Deprecated Vietnamese mode ids
    "hỏi đáp": "quick",
    "đề xuất bài báo": "research",
    "phân tích": "deep",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run ATLAS online evaluation without a WebSocket server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Modes: quick | research | deep  (aliases: qa, paper, analysis)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Benchmark all 3 research modes sequentially using their default queries.",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="quick",
        help="Research mode: quick | research | deep  (default: quick)",
    )
    parser.add_argument(
        "query",
        nargs="?",
        default=None,
        help="Research query (default: mode-specific built-in query)",
    )
    args = parser.parse_args()

    if not args.all:
        resolved = _MODE_ALIASES.get(args.mode)
        if resolved is None:
            parser.error(f"Unknown mode {args.mode!r}. Choose from: quick, research, deep")
        args.mode = resolved
        if args.query is None:
            args.query = _MODE_QUERIES[args.mode]

    return args


async def run_mode(mode: str, query: str) -> None:
    from src.orchestration.runner import LangGraphResearcher

    separator = "=" * 70
    print(f"\n{separator}")
    print(f"MODE : {mode}")
    print(f"QUERY: {query}")
    print(separator)
    researcher = LangGraphResearcher(query=query, report_type=mode)
    await researcher.run()


async def main() -> None:
    args = parse_args()

    if args.all:
        for mode, query in _MODE_QUERIES.items():
            await run_mode(mode, query)
    else:
        await run_mode(args.mode, args.query)


if __name__ == "__main__":
    # asyncio.run() in Python 3.14 calls shutdown_default_executor with a timeout,
    # which uses asyncio.timeout() internally. nest_asyncio (pulled in by ragas)
    # patches run_until_complete in a way that breaks the task-context check in
    # Python 3.14, raising RuntimeError("Timeout should be used inside a task").
    # Using a manual loop avoids that cleanup path entirely.
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    try:
        loop.run_until_complete(main())
    finally:
        loop.close()
