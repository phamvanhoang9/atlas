# ATLAS — Product Requirements Document (PRD)

**Date:** 2026-06-11 · Phase 2 deliverable · Status: approved baseline for Phases 3–10.

## 1. Product vision

ATLAS is the self-hosted intelligence desk for AI builders: ask anything about AI and get source-graded, citation-linked answers; wake up to a daily verified briefing on what actually changed in AI. Trust is the product — every claim is traceable to a scored source or explicitly marked unverified.

## 2. ICP (ideal customer profile)

Primary: **working AI/ML engineer or technical founder**, English-speaking, self-hosts tools, has OpenAI/Tavily keys, tracks AI progress as part of the job, distrusts hype.
Secondary: AI researchers, AI-coding power users, dev teams sharing one deployment.

## 3. User stories

**Chat**
- As an AI engineer, I ask "Is KV-cache quantization production-ready?" in Quick Answer and get a concise cited answer in seconds.
- As a researcher, I run Research mode on "speculative decoding vs. Medusa heads" and get evidence grouped by source quality, with fact vs. interpretation vs. hype separated.
- As a founder, I run Deep Research on "open-weight model licensing landscape" and get an executive summary, impact on product/startups, risks, recommended actions, and a confidence level.
- As any user, when I ask a non-AI question ("best pizza in Hanoi"), ATLAS politely declines and offers an AI-relevant reframing.
- As a user, I see which sources were used, their categories and scores, and click any citation to reach the real source.

**Automation**
- As an operator, I enable the daily run, set 05:00 Asia/Ho_Chi_Minh, choose depth + topics, and set a recipient email.
- As an operator, I trigger a manual run and watch its status; I inspect run history and failure logs.
- As an operator, if SMTP isn't configured, reports still generate and are saved + viewable; email shows "mock/dev mode" in run history (no silent fake sends).

**History**
- As a user, I browse/search past chats and daily reports, reopen them, and delete entries.

## 4. Core workflows

1. **Quick Answer:** scope gate → 1–2 broad searches (trusted web) → source scoring → compact context → concise answer + citations. Target < ~30s.
2. **Research:** scope gate → 3–5 queries biased to papers/official/technical sources → scoring + ranking → structured report (Summary, Main analysis, Evidence, Trade-offs, Uncertainties, Next steps, Sources).
3. **Deep Research:** scope gate → planned multi-step search (initial + gap-filling iterations) → cross-source contradiction check → impact analysis → full report (Executive Summary, What Matters, Technical Analysis, Source-Based Evidence, Impact on AI Engineers / AI Coding / Product & Startups, Risks and Unknowns, Recommended Actions, Source List, Confidence Level).
4. **Daily automation:** scheduler fires at configured time/tz → Deep-Research-grade job on "last 24h in AI" scoped to configured topics → report saved to history → email (HTML + plain text) sent with retry → run recorded with status/logs.

## 5. Mode identifiers (technical contract)

Canonical mode ids are English snake-case strings: `quick`, `research`, `deep`. Legacy ids (`hỏi đáp`, `đề xuất bài báo`, `phân tích`) are accepted as deprecated aliases during migration and removed with the old UI. (Decision D-004.)

## 6. Non-goals

See `product.md`. Binding for MVP: no extra modes, no multi-user accounts, no non-AI domains, no marketing landing page, no fake UI/scores.

## 7. MVP scope

**In:** 3 chat modes (distinct backend behavior + UI), AI-scope refusal, 9-category source quality scoring affecting ranking and visible in output, claim-linked citations + unverified marking, daily automation (scheduler, config UI, manual run, run history, failure logs, email with dev/mock fallback, retry), history (existing, extended to daily reports), evaluation suite with thresholds, product-first UI, security/deployment docs, accurate README + launch assets.

**Out (future):** optional modes, watchlist feeds, Slack/webhook delivery, multi-user, localization, RSS/arXiv ingestion, vector DB.

## 8. Success metrics

As specified in `product.md` §Success metrics (citation coverage ≥80%, citation correctness ≥90%, refusal ≥90%, zero low-quality primary evidence, ≥95% scheduled-run success, suite green in CI).

## 9. Risks

Tracked in `risk-register.md`. Top: mode-string migration breakage (R-02), automation sending bad reports (R-03), citation overpromise (R-06), UI scope explosion (R-05), VI→EN pivot encoding/translation debt (R-07).

## 10. Release criteria

Release = all Definition-of-Done items in `atlas_rebuild_desc.md` §7 verified with evidence in `verification.md`, including: app runs locally; tests pass; eval runs with thresholds; modes distinct; citations linked; refusal works; automation configurable with run history and mock email; docs complete and accurate; `.env.example` complete; no hardcoded secrets; no encoding bugs.
