# ATLAS Research System — Source Quality, Citations, Trust

> Phase 6 deliverable. Describes the implemented trust pipeline: how sources are
> classified, ranked, excluded, cited, and surfaced. All behavior described here is
> covered by tests (`tests/test_source_scorer.py`, `tests/test_generator.py`) or the
> generated sample (`docs/samples/research-mode-sample.md`).

**Last updated:** 2026-06-12

## 1. Trust pipeline overview

```
search (Tavily) → scrape → score_and_rank_sources (9-category scorer)
    → build_mode_context (context with Category lines, ranking order)
    → generate_report (prompt contract: cite [N] = context Source N)
    → _ensure_report_structure (link [N] → [[N]](#source-N), rebuild ## Sources
      from authoritative context URLs, append category labels)
    → WS "sources" message (per-source category + score for the UI panel)
```

Key modules:

- `src/quality/source_scorer.py` — deterministic classifier + ranker (D-008)
- `src/agents/searcher.py::_filter_academic` — wiring + low-quality warning + WS `sources` message
- `src/rag/context_builder.py` — `Category:` line per source section
- `src/agents/generator.py` — citation anchors, reference rebuild, category suffixes

## 2. The 9-category source taxonomy

| Category | Score | Examples | Rationale |
| --- | --- | --- | --- |
| `official` | 95 | docs.anthropic.com, pytorch.org, `docs.*` subdomains | Primary documentation; authoritative for capability/API claims |
| `peer_reviewed` | 90 | NeurIPS/ACL proceedings, IEEE, Nature | Reviewed evidence; strongest for scientific claims |
| `arxiv_preprint` | 80 | arxiv.org, OpenReview-less preprints | Primary research, not yet reviewed |
| `ai_lab_blog` | 75 | openai.com/blog, anthropic.com/news, BAIR | First-party announcements; authoritative but promotional |
| `github_repo` | 70 | github.com, gitlab.com | Verifiable code/benchmarks; not prose evidence |
| `engineering_blog` | 60 | blog.cloudflare.com, simonwillison.net | Serious practitioner experience |
| `tech_forum` | 50 | HN, StackOverflow, r/ML | Useful signal, unvetted |
| `uncategorized` | 45 | unknown domains | Conservative default between forum and news |
| `news` | 40 | TechCrunch, The Verge | Secondary reporting; often vendor-sourced |
| `low_quality` | 10 | medium.com, SEO farms, social | Never primary evidence |

Classification (`classify_source`) is **deterministic and rule-ordered**: low-quality
paths/domains first, then lab-blog path overrides (e.g. `openai.com/blog` beats the
`official` domain match), then domain tables from highest to lowest trust, then
heuristics (`docs.`/`developer.` → official; `blog.`/`*.github.io` → engineering blog),
then `uncategorized`. Non-URL input is `low_quality`.

## 3. Low-quality handling

`score_and_rank_sources` (tested in `tests/test_source_scorer.py`):

1. Documents without URL or content are dropped.
2. `low_quality` sources are **excluded** whenever at least one better source survives.
3. If *only* low-quality sources exist, they are kept but every document is flagged
   `low_quality_only=True`; the searcher streams a warning
   ("only low-quality sources found … claims will be unverified") instead of the
   normal quality summary.
4. Ranking is strictly by score, descending; the context builder consumes that order.

## 4. Citation system

- The prompt templates instruct the model to cite `[N]` where N is the context source
  number (`### Source N`), i.e. ranking order.
- `_ensure_report_structure` converts inline `[N]` → `[[N]](#source-N)` clickable
  anchors and **rebuilds** the `## Sources` section from the authoritative context
  URLs (never trusting LLM-fabricated links). LLM-written titles are reused only when
  they match a context URL (`_merge_sources`, URL-keyed with position fallback).
- Each rebuilt reference gets its category label as a suffix, e.g.
  `[title](url) — *arXiv/preprint*` (`_extract_source_categories` reads the
  `Category:` lines that `build_mode_context` emits).
- The searcher sends a WS message `{type: "sources", output: [{url, title, category,
  category_label, score}]}` so the UI can render a source panel (consumed in Phase 8).

Sample demonstrating ranking + exclusion + anchors + labels:
`docs/samples/research-mode-sample.md` — regenerate with
`.venv\Scripts\python scripts\make_sample_report.py` (offline, deterministic).

## 5. Research-backed rationale (per D-009)

### 5.1 Deterministic rule-based source scoring (adopted)

- **Sources used:** W3C Credibility Coalition "Credibility Signals" working drafts
  (inspectable, rule-style credibility indicators); the prior in-repo `AcademicFilter`
  (domain-tier ranking, the baseline); GPT-Researcher's source curation approach
  (open-source competitor — curates but exposes no per-source scoring).
- **Core idea:** classify sources by transparent domain/path rules into a fixed
  taxonomy with fixed scores, instead of an opaque ML/LLM judgment.
- **Why it applies to ATLAS:** trust is the product wedge; a score the user cannot
  inspect or reproduce is marketing, not trust. Deterministic rules are free,
  offline-testable, and explainable in docs.
- **Expected benefit:** reproducible ranking, zero per-query cost, honest labels in
  references and UI.
- **Implementation cost:** one module + table maintenance (~250 lines, 13 tests).
- **Risks:** rule tables go stale; unknown domains mis-bucketed. Mitigated by the
  conservative `uncategorized` default and table-driven tests.
- **How to test:** `tests/test_source_scorer.py` (per-category classification,
  ranking, exclusion, flagged fallback, label rendering).
- **Baseline comparison:** see §6.

### 5.2 Inline numbered citations with rebuilt references (kept & extended)

- **Sources used:** ALCE — "Enabling Large Language Models to Generate Text with
  Citations" (Gao et al., EMNLP 2023, arXiv:2305.14627): citation quality must be
  measured as recall/precision against retrieved sources, and models fabricate
  references when allowed to emit free-form links. "Attributed Question Answering"
  (Bohnet et al., arXiv:2212.08037): attribution to identifiable sources as the
  unit of trustworthiness.
- **Core idea:** never let the LLM emit reference URLs; it only emits `[N]` markers
  bound to retrieved sources, and the system rebuilds the reference list from the
  URLs it actually retrieved.
- **Why it applies:** fabricated links are the single fastest way to lose research
  users; the rebuild guarantees every reference URL was actually scraped.
- **Expected benefit:** zero fabricated reference URLs by construction.
- **Cost:** regex/normalization logic in `generator.py` (already existed; Phase 6
  added category labels).
- **Risks:** the LLM can still *mis-number* inline citations (claim cited to the
  wrong source). Marked as a known limitation (§7) and measured in Phase 7 eval.
- **How to test:** `tests/test_generator.py` + `tests/test_source_scorer.py::
  test_reference_section_shows_source_category_labels`.

### 5.3 Rejected/postponed for now

- **LLM-judged source credibility** — rejected (D-008): per-result cost and
  non-determinism undermine the trust story.
- **Claim-level NLI/entailment verification** (e.g. ALCE-style NLI citation
  checking at runtime) — postponed: real but heavy; Phase 7 evaluates citation
  correctness offline first; runtime NLI is a roadmap item, not MVP.

## 6. Baseline comparison: `AcademicFilter` → `source_scorer`

| Aspect | Baseline (`src/quality/academic_filter.py`) | New (`src/quality/source_scorer.py`) |
| --- | --- | --- |
| Taxonomy | 5 academic-centric tiers | 9 product-relevant categories |
| AI-lab blogs / official docs | bucketed as generic non-academic | first-class high-trust categories |
| Low-quality policy | down-ranked but kept | excluded unless nothing else; flagged `low_quality_only` |
| User-visible output | none | category label per reference + WS `sources` panel |
| Tests | 5 (in deleted `tests/test_utils.py`) | 13 table-driven |

Comparison method: same fixture URL set run through both classifiers during
development; the baseline mis-bucketed `openai.com/blog`, `docs.vllm.ai`, and news
domains into a single "non-academic" band, producing no usable label for the UI.
This is a **behavioral/maintainability comparison, not a quantitative retrieval
benchmark** — quantitative citation/grounding metrics land in Phase 7
(`docs/evaluation.md`). Per D-009 this qualifies via "improves maintainability and
product capability without regression" (full suite green after swap; old filter
removed: `src/quality/academic_filter.py`, legacy `src/utils/academic_filter.py`,
orphan `tests/test_utils.py`).

## 7. Known limitations (honest)

1. **Inline citation numbering trusts the LLM.** Anchors and reference URLs are
   system-controlled, but if the model writes `[2]` while describing source 3, the
   link goes to the wrong (real) source. Measured in Phase 7; runtime NLI checking
   is roadmap.
2. **Rule tables require maintenance** as the AI publishing landscape shifts.
3. **`uncategorized` (45) is a guess** for unknown domains; deliberately between
   forum and news.
4. The sample report's prose is fixture text (clearly labeled); only the pipeline
   mechanics in it are real. A live end-to-end sample is part of Phase 10 samples.
