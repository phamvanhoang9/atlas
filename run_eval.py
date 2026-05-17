"""Quick eval runner — always runs evaluation regardless of ENABLE_EVALUATION env var.

Usage:
    python run_eval.py                                      # default query, hỏi đáp mode
    python run_eval.py "phân tích"                         # default query, custom mode
    python run_eval.py "hỏi đáp" "your query here"        # custom mode and query
    python run_eval.py --all                               # benchmark all 3 modes
"""
import argparse
import asyncio
import io
import logging
import os
import sys

# Force UTF-8 stdout/stderr so Vietnamese characters print correctly on Windows.
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
# on-topic inference/latency papers rather than training-optimization papers.
_MODE_QUERIES: dict[str, str] = {
    "hỏi đáp": (
        "Graph RAG khác với RAG truyền thống ở điểm nào?"
    ),
    "phân tích": (
        "Phân tích các kỹ thuật tối ưu hóa inference latency của LLM: "
        "KV cache, continuous batching, speculative decoding và quantization"
    ),
    "đề xuất bài báo": (
        "Đề xuất các bài báo nghiên cứu mới nhất về tối ưu hóa tốc độ inference "
        "của mô hình ngôn ngữ lớn (LLM serving, throughput, latency)"
    ),
}

_MODE_ALIASES: dict[str, str] = {
    # English aliases
    "qa":       "hỏi đáp",
    "analysis": "phân tích",
    "paper":    "đề xuất bài báo",
    # Vietnamese names (direct)
    "hỏi đáp":         "hỏi đáp",
    "phân tích":        "phân tích",
    "đề xuất bài báo":  "đề xuất bài báo",
}


def parse_args() -> argparse.Namespace:
    aliases = ", ".join(f"{k} → {v}" for k, v in _MODE_ALIASES.items() if k in {"qa", "analysis", "paper"})
    parser = argparse.ArgumentParser(
        description="Run ATLAS evaluation without a WebSocket server.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=f"Mode aliases (English shorthand):\n  {aliases}",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Benchmark all 3 research modes sequentially using their default queries.",
    )
    parser.add_argument(
        "mode",
        nargs="?",
        default="qa",
        help="Research mode: qa | analysis | paper  (default: qa)",
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
            parser.error(f"Unknown mode {args.mode!r}. Choose from: qa, analysis, paper")
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
