# ATLAS — Product Definition

**Date:** 2026-06-11 · Phase 2 deliverable. Companion docs: `competitive-analysis.md`, `prd.md`.

## Positioning

> ATLAS is an open-source AI intelligence and verified research platform for AI builders who need trustworthy daily AI updates, source-grounded research, and actionable technical impact reports.

ATLAS is **not** a generic chatbot. It is a focused, self-hosted research instrument for the AI domain with two product wedges:

1. **Verified AI Research Chat** — Quick Answer / Research / Deep Research modes with source-quality scoring and claim-linked citations.
2. **Daily AI Intelligence Automation** — scheduled deep research over the last 24h of AI developments, delivered by email.

## Target users

| User | Job to be done |
| --- | --- |
| AI/ML engineers | "What changed in AI this week and what should I actually adopt?" |
| AI researchers | "Which papers matter for my area; what is verified vs hype?" |
| AI coding users | "Which model/tool is best for my coding workflow right now?" |
| AI product builders / technical founders | "What does this release mean for my product and costs?" |
| Developer teams adopting AI | "Give the team one trustworthy daily digest instead of 12 newsletters." |

## Pain points addressed

- AI news volume is unmanageable; signal/noise is poor; hype dominates.
- Chat assistants answer confidently without verifiable sources; citations often don't support the claim.
- Closed research tools (ChatGPT/Claude/Perplexity) are not self-hostable, not scriptable, and not transparent about source selection.
- Newsletters are generic — not filtered by the reader's technical concerns and never claim-verified.

## Differentiation (why ATLAS can matter)

1. **Verifiability as the core mechanic** — 9-category source taxonomy, scores that visibly affect ranking, claim-level citations, explicit "unverified" marking. Closed tools assert; ATLAS shows its evidence.
2. **AI-domain focus** — scope gate refuses off-domain queries; prompts, source lists, and report structures are AI-specific, so depth beats breadth.
3. **Automation as a product, not a feature** — the daily 5:00 AM intelligence report is a standing work product with run history and failure logs, not a chat session you must remember to start.
4. **Open source + self-hosted** — your keys, your data, inspectable pipeline, extensible workflow (LangGraph).

## Main use cases

1. Quick factual check on an AI topic with citations (Quick Answer).
2. Structured analysis of a technique/model/tool decision (Research).
3. Standing deep-dive: "state of X" with impact analysis and confidence levels (Deep Research).
4. Daily automated AI intelligence email; review history of past reports.
5. Search and revisit past research in history.

## Non-goals

- Generic all-topic chatbot or consumer assistant.
- Multi-tenant SaaS, billing, team accounts (MVP is single-operator self-hosted).
- Marketing-first landing page.
- Mobile apps.
- Optional chat modes (Paper Explainer, Model Comparison, etc.) before the core 3 are solid.
- Proprietary content or paywalled data sources.

## Success metrics (MVP)

| Metric | Target |
| --- | --- |
| Citation coverage (claims with ≥1 citation in Research/Deep) | ≥ 80% on eval set |
| Citation correctness (citation links to a source that supports the claim) | ≥ 90% on eval set |
| Refusal accuracy on non-AI queries | ≥ 90% on eval set |
| Low-quality sources used as primary evidence | 0 on eval set |
| Daily report generation success rate (with retry) | ≥ 95% of scheduled runs |
| Time-to-first-token, Quick Answer | < 10s with warm cache |
| Test suite | green in CI |

## Language decision

**English is the default product language** (UI, prompts, reports): the ICP is the global AI engineer, and the GitHub audience is English-first. Vietnamese remains a supported research *output* language only if asked in Vietnamese (LLM follows query language for the answer body); UI localization is future scope. (Decision D-003 in `decision-log.md`.)

## Future scope (post-MVP)

- Optional modes: Paper Explainer, Model Comparison, AI Coding Research, Benchmark Analysis.
- Watchlist topics with per-topic feeds; webhook/Slack delivery.
- Multi-user auth; UI localization (VI and others); RSS/arXiv listing ingestion alongside web search.
