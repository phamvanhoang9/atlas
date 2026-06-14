# ATLAS User Guide

> Phase 10 deliverable. How to use ATLAS day-to-day. Setup is in the README;
> deployment in `docs/deployment.md`.

**Last updated:** 2026-06-12

## 1. Research view

Type a question about AI — models, papers, tooling, infrastructure, agents,
benchmarks — pick a mode, hit **Run**.

### Choosing a mode

| Use | Mode | Example |
| --- | --- | --- |
| Direct question, fast answer | **Quick Answer** | "How does speculative decoding speed up LLM inference?" |
| Reading list / structured overview | **Research** | "Recommend recent papers on agentic RAG with code or benchmarks" |
| Full topic analysis or source deep-dive | **Deep Research** | "Compare GraphRAG, RAPTOR, and vector RAG for long-context QA" |
| Analyze specific papers/pages | **Deep Research** + paste URLs into the query | "Analyze this paper: https://arxiv.org/abs/…" |

When the query contains URLs, ATLAS skips search and reads those sources directly.

### While it runs

The progress card shows what the system is doing (planning → searching → reading
sources → ranking by quality → building context → writing) plus a raw log stream.
The report streams in as it is written.

### Reading the result

- **Sources panel** — every source ATLAS kept, ranked by its 0–100 quality score,
  with a category chip (Peer-reviewed, Official, arXiv/preprint, GitHub, News, …).
  Low-quality sources (Medium, SEO farms, social) are dropped unless nothing else
  exists — in that degraded case ATLAS warns you and marks claims unverified.
- **Citations** — `[N]` markers in the text are clickable and jump to the Sources
  section, which is rebuilt from URLs ATLAS actually read (it cannot contain a
  fabricated link). Each reference carries its category label.
- **Grounding/Evaluation note** — when enabled, a verification summary appears
  under the report.
- **Copy / PDF** — copy the report text or download the exported PDF.
- **Follow-up questions** — click one to load it into the query box.

### Out-of-scope questions

ATLAS only researches AI. Anything else ("best cake recipe", "workout plan") gets
an explicit refusal card with a suggested AI-angle reframe. This is deliberate:
a focused tool that refuses honestly beats a general tool that guesses.

## 2. Automation view — Daily AI Intelligence

1. Set **time** (24h) and **IANA timezone** (e.g. `Asia/Ho_Chi_Minh`).
2. Set the **recipient email**.
3. List your **topics**, one per line (e.g. "new LLM releases and benchmarks").
4. Pick **depth** — Deep is the intended daily briefing; Quick/Research are
   cheaper alternatives.
5. Toggle **Daily report enabled** and **Save settings**.

The chip at the top tells you whether email delivery is **real (SMTP)** or
**mock** (logged only — set `SMTP_*` env vars to go real).

- **Run now** triggers a report immediately (one at a time).
- **Recent runs** shows status (`success`/`failed`/`running`), email delivery
  state, duration, and a **View report** link into the stored report.
- Missed schedules (app was down) are caught up same-day on restart; a day is
  never sent twice.

## 3. History view

- Every chat report and daily report, newest first.
- Filter: **All / Chat / Daily reports**; search box filters by query/preview.
- Click a card to open the stored report (with its follow-up questions and PDF
  link). Delete removes one entry; **Export** downloads all history as JSON;
  **Clear all** wipes it (confirmed, irreversible).

## 4. Authentication (shared deployments)

If the server sets `ATLAS_AUTH_TOKEN`, the browser must present it. Set it once
in the browser console:

```js
localStorage.setItem("atlas_auth_token", "<your token>")
```

All API calls and the research WebSocket then authenticate automatically.

## 5. Tips

- Quick Answer is tuned for speed: ~1 extra search query, small context. If the
  answer feels thin, re-run in Research mode.
- Deep Research auto-upgrades the model (e.g. gpt-4o-mini → gpt-4o).
- Reports answer in the language of your question; sources are usually English.
- Everything is stored locally (SQLite + `outputs/`) — see `docs/deployment.md`
  for backup paths.
