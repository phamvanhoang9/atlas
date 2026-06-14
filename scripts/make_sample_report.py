"""Generate the deterministic sample research report in docs/samples/.

Feeds fixed scraped-document fixtures through the real production pipeline:
``score_and_rank_sources`` -> ``build_mode_context`` -> ``_ensure_report_structure``.
The report prose is fixture text (no LLM call), but source ranking, low-quality
exclusion, context assembly, citation anchors, and the rebuilt Sources section
are produced by the same code paths ATLAS uses at runtime.

Regenerate with:
    .venv\\Scripts\\python scripts\\make_sample_report.py
"""

from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.agents.generator import _ensure_report_structure  # noqa: E402
from src.quality.source_scorer import classify_source, score_and_rank_sources  # noqa: E402
from src.rag.context_builder import build_mode_context  # noqa: E402

QUERY = "What is speculative decoding and how much does it speed up LLM inference?"

FIXTURE_DOCS = [
    {
        "url": "https://medium.com/@blogger/speculative-decoding-explained-1a2b3c",
        "title": "Speculative Decoding Explained (Medium)",
        "raw_content": "A casual explainer of speculative decoding with unverified speedup claims.",
    },
    {
        "url": "https://techcrunch.com/2026/05/01/llm-inference-costs-are-falling/",
        "title": "LLM inference costs are falling",
        "raw_content": "Industry coverage: providers attribute falling inference costs partly to "
        "speculative decoding rollouts across serving stacks.",
    },
    {
        "url": "https://arxiv.org/abs/2211.17192",
        "title": "Fast Inference from Transformers via Speculative Decoding",
        "raw_content": "We introduce speculative decoding: a smaller draft model proposes tokens "
        "that the target model verifies in parallel, preserving the exact output "
        "distribution. Experiments show 2-3x wall-clock speedups on T5-XXL without "
        "quality loss.",
    },
    {
        "url": "https://docs.vllm.ai/en/latest/features/spec_decode.html",
        "title": "Speculative Decoding - vLLM documentation",
        "raw_content": "vLLM supports speculative decoding with draft models, n-gram lookup, and "
        "Medusa-style heads. Acceptance rate determines realized speedup; typical "
        "configurations yield 1.5-2.8x throughput gains depending on workload.",
    },
    {
        "url": "https://github.com/vllm-project/vllm",
        "title": "vllm-project/vllm",
        "raw_content": "vLLM is a high-throughput and memory-efficient inference engine for LLMs. "
        "Includes speculative decoding support; see benchmarks/ for reproduction scripts.",
    },
]

# Fixture stand-in for the LLM-generated report (prose only; linking is real).
# Citation numbers follow the prompt contract: [N] refers to the N-th ranked
# context source ("### Source N"), i.e. ranking order, not arbitrary order.
RAW_REPORT = """# Speculative decoding: what it is and measured speedups

## Answer

Speculative decoding speeds up LLM inference by letting a small draft model propose
several tokens that the large target model then verifies in one parallel pass; accepted
tokens are emitted and rejected ones fall back to normal decoding, so the output
distribution is provably unchanged [2]. The original paper reports 2-3x wall-clock
speedups on T5-XXL with no quality loss [2]. Production serving stacks confirm the
range: vLLM documents typical 1.5-2.8x throughput gains depending on draft acceptance
rate and workload [1], with reproduction scripts available in the project repository [3].
Industry coverage attributes part of the recent drop in inference prices to these
rollouts, though vendor-reported numbers there are not independently verified [4].

## Key takeaways

- Exactness: verification preserves the target model's distribution - this is a
  lossless optimization, not an approximation [2].
- Realized speedup is workload-dependent: it hinges on the draft model's acceptance
  rate, not a fixed constant [1].

## Sources
- [1] Speculative Decoding - vLLM documentation. https://docs.vllm.ai/en/latest/features/spec_decode.html
- [2] Fast Inference from Transformers via Speculative Decoding. https://arxiv.org/abs/2211.17192
- [3] vllm-project/vllm. https://github.com/vllm-project/vllm
- [4] LLM inference costs are falling. https://techcrunch.com/2026/05/01/llm-inference-costs-are-falling/
"""


def main() -> None:
    ranked = score_and_rank_sources(FIXTURE_DOCS)
    context = build_mode_context(ranked, QUERY, "research")
    final_report = _ensure_report_structure(RAW_REPORT, QUERY, [context])

    ranking_rows = []
    for doc in FIXTURE_DOCS:
        cls = classify_source(doc["url"])
        kept = any(r["url"] == doc["url"] for r in ranked)
        ranking_rows.append(
            f"| {doc['url']} | {cls.label} | {cls.score} | {'kept' if kept else 'dropped (low quality)'} |"
        )

    out = Path(__file__).resolve().parents[1] / "docs" / "samples" / "research-mode-sample.md"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        f"""<!-- Generated by scripts/make_sample_report.py on {date.today().isoformat()}. Do not edit by hand. -->

# Sample output - Research mode

**Query:** {QUERY}

This sample is generated offline from fixture documents. The report prose is fixture
text, but **source classification, ranking, low-quality exclusion, context assembly,
citation anchors, and the rebuilt Sources section below are produced by the real ATLAS
pipeline code** (`score_and_rank_sources` -> `build_mode_context` -> `_ensure_report_structure`).

## Source ranking (real scorer output)

| URL | Category | Score | Decision |
| --- | --- | --- | --- |
{chr(10).join(ranking_rows)}

The Medium post is excluded: `low_quality` sources are never used as primary evidence
when better sources exist. Remaining sources are ranked by trust score and the context
builder consumes them in that order.

## Final report (real citation linking)

---

{final_report}
""",
        encoding="utf-8",
    )
    print(f"Wrote {out}")
    print(f"Ranked sources: {[(r['source_category'], r['quality_score']) for r in ranked]}")


if __name__ == "__main__":
    main()
