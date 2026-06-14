# ATLAS Rebuild — Critique & Self-Review

> Required by `atlas_rebuild_desc.md` §4.5. Challenge weak assumptions. Update whenever a better idea or flaw is found.

**Last updated:** 2026-06-11

## Challenge to the product strategy (Phase 2 gate requirement)

The strategy assumes AI engineers want *another* tool. The strongest counter-argument: the ICP already pays for ChatGPT/Claude and reads free newsletters — switching cost is real and ATLAS's synthesis quality will be strictly worse than frontier closed tools. The strategy survives only if (a) the trust mechanics are visibly real (inspectable scores, claim-linked citations, honest "unverified" labels — things closed tools structurally won't expose), and (b) the daily automation works reliably enough to become a habit. If either is faked or flaky, ATLAS is a portfolio demo, not a product — acceptable as a fallback outcome, but the build should aim at the product bar. Concretely this means: invest disproportionately in Phases 6–7 (trust + eval) over UI polish.

## Amendment (2026-06-12, D-009)

The advice above ("invest disproportionately in Phases 6–7 over UI polish") is amended by the operator's updated requirements: UI/UX is now a hard product bar, not a nice-to-have. Both legs — trust mechanics *and* a daily-use-grade frontend — are gate criteria. The honest risk reading: Phase 8 is now the most likely phase to slip; mitigate by building the app shell incrementally on the existing vanilla-JS stack instead of redesigning from zero.

## Product risks

- **Crowded space.** Perplexity, ChatGPT Deep Research, GPT Researcher already do "research with citations". ATLAS's only defensible wedge is the *combination*: AI-domain focus + verifiable source-quality system + daily automation that lands in email. If any leg is weak, the product reads as a demo.
- **Daily report quality ceiling.** A daily AI digest is only valuable if it beats free newsletters (e.g. AINews, TLDR AI) on signal/noise. Automation alone is not differentiation; source-quality grounding + impact analysis is.

## Technical risks

- Single LLM-call pipeline quality depends heavily on search result quality (Tavily). A bad search day = a bad report, automated.
- LangGraph workflow is linear; Deep Research multi-step synthesis will need real iteration loops, not just bigger prompts.

## UX concerns

- Current UI is a single-page Vietnamese chat with researcher mascot images — far from "serious, dense, professional" bar. Full UI rebuild needed, which is the largest single work item.
- Language pivot: brief targets global AI engineers (English-first), current UI is Vietnamese-first. Need explicit decision on default language.

## Trust/reliability concerns

- Citations must link claim→source. Current report generator appends a references section; claim-level mapping is weaker. Don't fake it: mark unverified claims instead.

## Competitive weaknesses

- No proprietary data; everything rests on open web search. Honest framing: "open-source, self-hosted, verifiable" vs closed competitors.

## Things that look impressive but are not actually valuable

- RAGAS metric dashboards without action thresholds.
- Adding more chat modes before the 3 core modes are solid (brief explicitly forbids this).

## Features that should be cut or postponed

- Paper Explainer / Model Comparison / Benchmark Analysis modes — postpone (per brief).
- Multi-user accounts, OAuth — out of MVP; single-operator self-hosted tool first.
