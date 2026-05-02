# ATLAS Agent Guidance

## Project Overview
- ATLAS is a FastAPI web app for research workflows: plan a user task, search academic sources, scrape/PDF-extract content, compress/build context, generate a cited report, export Markdown/PDF, and store searchable history.
- The main workflow is a LangGraph state machine in `src/orchestration/workflow.py`. Nodes live in `src/agents/`; routing lives in `src/orchestration/router.py`; the shared state schema is `src/orchestration/state.py`.
- Runtime surface: FastAPI app factory in `src/api/app.py`, WebSocket job route in `src/api/routes/websocket.py`, history REST API in `src/api/routes/history.py`, and static/Jinja UI in `frontend/`.
- Generated reports, SQLite history, and caches are runtime data under `outputs/`, `.atlas_data/`, and `.atlas_cache/`; do not treat them as source.

## Commands
- Install: `python -m pip install --upgrade pip` then `pip install -r requirements.txt`.
- Run locally: copy `.env.example` to `.env`, copy `config.json.example` to `config.json`, then `python main.py` or `python -m uvicorn src.api.server:app --reload`.
- Checks used by CI: `python -m compileall -q src main.py`, `ruff check src tests main.py`, and `python -m pytest`.
- Docker dev: `docker compose up -d --build`.
- Production-style Docker: `docker compose -f docker-compose.prod.yml up -d --build`.

## Directory Map
- `src/api/`: FastAPI app setup, auth middleware, WebSocket and history routes.
- `src/orchestration/`: LangGraph workflow assembly, routers, runner, and state contract.
- `src/agents/`: planner, search/scrape, context processing, report generation nodes. Files such as `query_planner.py` and `report_generator.py` are compatibility re-exports.
- `src/config/`: config loading, validation, and mode-specific overrides.
- `src/prompts/templates/`: YAML prompt templates. `src/prompts/functions.py` and `registry.py` render them.
- `src/retrievers/`, `src/scraper/`, `src/scraping/`: Tavily/DDG search and extraction helpers. `src/scraping/scraper.py` re-exports `src.scraper.Scraper`.
- `src/rag/`, `src/context/`, `src/memory/`: context construction, compression, embeddings, reranking, and SQLite TTL cache integration.
- `src/storage/`: SQLite history and cache stores.
- `frontend/`: Jinja-served HTML, CSS, JS, and PDF styling.
- `.github/workflows/`: CI and tag-driven GitHub Release automation.
- `docs/agent-memory/`: tracked project memory for future agent sessions.
- `RELEASE.md`: release tagging and secret-safety guide.
- `tests/`: pytest suite; add focused tests near the changed behavior.

## Conventions
- Prefer Python 3.12 behavior; `pyproject.toml` allows 3.10+, but CI and Docker use 3.12.
- Use `requirements.txt` as the dependency source for local/CI installs. `pyproject.toml` currently holds metadata and Ruff config only.
- Preserve exact Vietnamese mode strings: `hỏi đáp`, `đề xuất bài báo`, and `phân tích`. These drive mode profiles, prompt selection, model routing, and context limits.
- Config precedence is environment defaults first, then `config.json`, then mode-specific overrides from `src/config/mode_profiles.py` when `LangGraphResearcher` calls `apply_mode_config`.
- The web research runner passes `config_path="config.json"` explicitly, so the web UI path expects a real `config.json`; tests and direct `Config()` usage tolerate a missing default config file.
- Prompt behavior should usually be changed in YAML templates and covered by prompt registry/function tests.

## Testing Expectations
- For workflow/routing changes, update `tests/test_langgraph.py` or add targeted orchestration tests.
- For config behavior, update `tests/test_config.py`.
- For prompt changes, update `tests/test_prompt_registry.py`.
- For retriever/cache changes, update `tests/test_retrievers.py` or storage/cache tests.
- For API auth/history changes, update `tests/test_server_auth.py` or history manager tests.
- Disable expensive runtime features in tests with `ENABLE_SEARCH_CACHE=false`, `ENABLE_EMBEDDING_CACHE=false`, and `ENABLE_CROSS_ENCODER_RERANKING=false`; `tests/conftest.py` sets these defaults.

## Agent Memory
- This repo uses file-based long-term memory under `docs/agent-memory/`.
- `AGENTS.md`, `RELEASE.md`, and `docs/` are project documentation intended to be tracked and pushed to GitHub.

Before starting non-trivial work:
- Read `docs/agent-memory/PROJECT_STATE.md`.
- Read `docs/agent-memory/DECISIONS.md`.
- Read `docs/agent-memory/NEXT_STEPS.md`.
- Skim recent entries in `docs/agent-memory/TASK_LOG.md`.

After completing work:
- Update `PROJECT_STATE.md` if the current state changed.
- Add durable architectural, product, or process choices to `DECISIONS.md`.
- Update `NEXT_STEPS.md` with remaining work.
- Add a dated entry to `TASK_LOG.md` describing what changed, what was tested, and any issues found.

Do not store secrets, credentials, raw environment values, generated reports, SQLite/cache contents, or sensitive personal data in memory files. Keep memory concise, factual, and repo-specific.

## Quirks And Traps
- Do not read or store real `.env` values. Refer only to variable names such as `OPENAI_API_KEY`, `TAVILY_API_KEY`, `GEMINI_API_KEY`, and `ATLAS_AUTH_TOKEN`.
- `docs/` currently contains agent memory, not full implementation docs. Check file existence before relying on old or historical doc references.
- Historical memory entries mention a RAG evaluation package and `examples/evaluation/`; current tracked source does not include those files. Verify with `rg --files` before using evaluation commands or datasets.
- `.gitignore` excludes runtime data, config secrets, SQLite files, caches, and `outputs/`; keep generated files out of source changes.
- `.dockerignore` excludes docs and Markdown from Docker build context even though these files are tracked by Git.
- There are duplicate-looking legacy modules (`src/llm_provider/*`, `src/utils/academic_filter.py`) alongside newer paths (`src/llm/providers/*`, `src/quality/academic_filter.py`). Check imports before editing and avoid changing only one duplicate unless callers prove it is the active path.
- `create_chat_completion` caps `max_tokens` at `12001` and routes models based on report type; `phân tích` may upgrade OpenAI `gpt-4o-mini` to `gpt-4o`.
- Tavily search requires `TAVILY_API_KEY` even though search can fall back to DuckDuckGo after Tavily initialization.
- Production Docker pre-downloads the cross-encoder model and sets Hugging Face offline flags; changing reranking model names can affect image builds.

## Do Not
- Do not commit or memorialize secrets, raw environment values, generated reports, SQLite DBs, caches, or local `config.json`.
- Do not replace Vietnamese mode labels with English aliases unless the full routing, UI, tests, and prompt selection are updated together.
- Do not assume README-referenced docs exist without checking the filesystem.
- Do not edit compatibility re-export modules when the implementation lives in another file, unless the compatibility API itself is the target.
