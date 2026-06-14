# ATLAS Roadmap

> Phase 10 deliverable. Post-rebuild direction; items ordered by leverage on the
> trust story. Nothing here is promised — see `docs/decision-log.md` for what got
> rejected/postponed and why.

**Last updated:** 2026-06-12

## Near term (hardening)

- **Citation-number verification** — the one honest gap in the trust story:
  inline `[N]` numbering trusts the LLM. Add an offline checker that maps each
  cited claim to its source via the eval layer, surface mismatches in the
  grounding note. (R-06; research-system.md §7.)
- **Grow the offline benchmark** beyond 5 samples — add multilingual,
  multi-source-conflict, and stale-information cases; keep per-metric assertions.
- **Run the prod Docker build in CI** (R-09) and add a GitHub Actions workflow:
  ruff + pytest + `run_benchmark.py` as the PR gate.
- **Rate limiting** at the app level (R-10) instead of relying on the proxy.

## Mid term (product depth)

- **Source-panel persistence** — store the ranked source list with each history
  entry so stored reports show the same panel as live runs.
- **Daily report diffing** — "what changed since yesterday" sections computed
  from history instead of fresh-search-only.
- **Runtime NLI claim checking** (postponed in D-008/Phase 6): entailment-check
  claims against their cited source at generation time; mark failures unverified.
- **Per-user topic profiles** for automation (multiple recipients/digests) —
  first step beyond the single-operator model.
- **Vietnamese UI localization** — restore VI as a first-class UI language
  (D-003 made EN the default; the mode-alias layer already preserves VI data).

## Long term (platform)

- Pluggable retrievers (arXiv API, Semantic Scholar, HF papers) feeding the same
  scorer taxonomy.
- Multi-step deep-research planner with explicit iteration loops (today's deep
  mode is bigger context + better prompts, not true iterative planning —
  critique.md "Technical risks").
- Webhook/Slack delivery for daily intelligence in addition to email.

## Explicitly not planned (MVP discipline, per brief)

- More chat modes before the three core ones are excellent.
- Multi-user accounts / OAuth.
- LLM-judged source credibility (rejected, D-008 — breaks determinism of the
  trust story).
