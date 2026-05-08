# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

**ATLAS** (Agentic Task & Literature Analysis System) — a FastAPI + LangGraph research assistant that turns a user query into searched sources, compressed context, a grounded report, PDF export, and searchable history. The UI targets Vietnamese research users; three research modes drive most runtime behavior.

## Commands

```bash
# Install
pip install -r requirements.txt

# Run locally (loads .env automatically)
python main.py
# or
python -m uvicorn src.api.server:app --reload

# Docker
docker compose up -d --build
docker compose -f docker-compose.prod.yml up -d --build

# Lint
ruff check src tests main.py

# Compile check (no deps needed)
python -m compileall -q src main.py

# Run all tests
python -m pytest

# Run a single test file
python -m pytest tests/test_langgraph.py

# Run a single test by name
python -m pytest tests/test_config.py::test_mode_profiles -v
```

**Minimum env vars** (copy `.env.example` → `.env`):
- `OPENAI_API_KEY` — default LLM and embeddings
- `TAVILY_API_KEY` — web search (required for real searches)
- `ATLAS_AUTH_TOKEN` — optional; omit for open local dev

Also copy `config.json.example` → `config.json` for runtime config.

## Architecture

### Request lifecycle

1. Browser connects to `/ws` (WebSocket).
2. `src/api/routes/websocket.py` authenticates and calls `deps.manager.start_streaming()`.
3. `src/transport/manager.py` runs `LangGraphResearcher.invoke()` from `src/orchestration/runner.py`.
4. The runner applies mode-specific config overrides (`src/config/mode_profiles.py`) and executes the LangGraph workflow built by `src/orchestration/workflow.py`.
5. Progress is streamed back to the browser via `stream_output()` (`src/transport/streaming.py`).
6. The finished report is saved to SQLite history (`src/storage/history.py`) and PDF export is triggered.

### LangGraph workflow (`src/orchestration/workflow.py`)

```
choose_agent
  → route_after_agent_selection
      ├─ source_urls provided → search_and_scrape (use those URLs)
      └─ no URLs → generate_sub_queries
           → route_search_mode
               ├─ parallel_search_and_scrape  (multiple queries)
               └─ search_and_scrape (sequential, loops until exhausted)
  → process_context     (semantic compression or mode-aware context builder)
  → generate_report     (streams LLM output, enforces references section)
  → evaluate_state      (optional RAGAS metrics, if ENABLE_EVALUATION=true)
  → END
```

State schema lives in `src/orchestration/state.py` (`ResearchState` TypedDict). **Keep its keys stable** — all agent nodes and routing functions depend on exact key names.

### Research modes

The three mode strings are load-bearing throughout the codebase (prompt selection, model routing, config profiles, context sizing). Do not change them:

| Mode string | Meaning | Behavior |
|---|---|---|
| `hỏi đáp` | Q&A | Fast, 1 extra query, small context |
| `đề xuất bài báo` | Paper recommendations | Broad academic search, reading list |
| `phân tích` | Deep analysis | URL analysis or full topic deep dive |

Mode-specific config overrides (`max_iterations`, `max_search_results`, `word_count`, token limits) are defined in `src/config/mode_profiles.py` and applied by the runner at invoke time.

### Config system

`src/config/config.py` holds the `Config` dataclass and validation. Precedence: env-var defaults → `config.json` → mode overrides applied by `apply_mode_config()` at runtime. `src/config/settings.py` is a compatibility shim; prefer `config.py` for new code.

### LLM layer (`src/llm/`)

- `completion.py` — `create_chat_completion()`: unified entry point, retries with exponential backoff, streams tokens to WebSocket, caps `max_tokens` at 12001.
- `router.py` — `route_model()`: upgrades gpt-4o-mini → gpt-4o and gemini-1.5-flash → gemini-1.5-pro for `phân tích` mode.
- `providers/litellm_provider.py` — unified wrapper; `openai_provider.py` and `google_provider.py` are provider-specific.

`src/llm_provider/` is a legacy directory; new LLM code belongs in `src/llm/`.

### Retrieval & context pipeline

- **Search**: `src/retrievers/tavily_search/` (Tavily with DuckDuckGo fallback, SQLite cache).
- **Scraping**: `src/scraper/scraper.py` (BeautifulSoup + PyMuPDF for PDFs).
- **Academic filter**: `src/quality/academic_filter.py` ranks sources by domain authority.
- **Compression**: `src/context/compression.py` (`ContextCompressor`) uses embeddings similarity + optional CrossEncoderReranker to select relevant chunks.
- **Mode-aware context**: `src/rag/context_builder.py` (`build_mode_context()`) applies per-mode doc/char limits without requiring embeddings.

`src/utils/academic_filter.py` is a legacy path; use `src/quality/academic_filter.py`.

### Prompts

Templates are YAML files in `src/prompts/templates/`. Use `render_prompt(name, variables)` from `src/prompts/registry.py` (Template.safe_substitute under the hood). Do not hard-code prompt strings in agent nodes.

### API surface

| Route | Purpose |
|---|---|
| `GET /` | Serves frontend (Jinja) |
| `GET /health` | `{"status": "ok"}` |
| `WS /ws` | Research job + streaming |
| `GET /api/history` | Paginated history list |
| `GET /api/history/{id}` | Single entry |
| `DELETE /api/history/{id}` | Remove entry |
| `GET /api/history/search/{term}` | Full-text search |

Auth: `Authorization: Bearer <token>` header or `?token=<token>` query param. Disabled when `ATLAS_AUTH_TOKEN` is unset.

### Tests

`tests/conftest.py` disables search cache, embedding cache, and cross-encoder reranking for all tests. Tests use `pytest`; no special fixtures beyond conftest are needed for unit tests. Integration tests that call real APIs are skipped when keys are absent.
