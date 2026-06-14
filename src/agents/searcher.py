"""Searcher agent — search, scrape, and context compression."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.context.compression import ContextCompressor
from src.modes import DEEP, get_mode_spec, normalize_mode
from src.orchestration.state import ResearchState
from src.quality.source_scorer import score_and_rank_sources
from src.rag.context_builder import build_mode_context
from src.transport.streaming import stream_output

logger = logging.getLogger(__name__)


def _include_domains_for_mode(report_type: str) -> list[str] | None:
    """Search domain policy comes from the mode registry."""
    domains = get_mode_spec(report_type).search_include_domains
    return list(domains) if domains else None


def _get_retriever(name: str) -> Any:
    from src.retrievers import TavilySearch
    if name == "tavily":
        return TavilySearch
    raise ValueError(f"Retriever not found: {name}")


def _scrape_urls(urls: list[str], cfg: Any = None) -> list[dict[str, Any]]:
    from src.scraper import Scraper
    ua = cfg.user_agent if cfg else "Mozilla/5.0"
    try:
        return Scraper(urls, ua).run()
    except (RuntimeError, OSError, ValueError) as exc:
        logger.error("scrape_urls error: %s", exc)
        return []


def _max_urls_for_mode(report_type: str) -> int:
    return get_mode_spec(report_type).max_scrape_urls


async def _parallel_search(queries, retriever_name, max_results=7, ws=None, include_domains=None):
    logger.info("Parallel search start queries=%s retriever=%s max_results=%s", len(queries), retriever_name, max_results)

    async def _one(q):
        try:
            await stream_output("logs", f"Searching in parallel: '{q}'...", ws)
            loop = asyncio.get_running_loop()
            r = _get_retriever(retriever_name)(q, include_domains=include_domains)
            res = await loop.run_in_executor(None, r.search, max_results)
            logger.info("Search query complete query=%r results=%s", q, len(res))
            await stream_output("logs", f"Found {len(res)} results for '{q}'", ws)
            return q, res
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning("search '%s': %s", q, exc)
            return q, []

    await stream_output("logs", f"Starting parallel search for {len(queries)} queries...", ws)
    results = await asyncio.gather(*[_one(q) for q in queries], return_exceptions=True)
    out: dict[str, list] = {}
    for r in results:
        if isinstance(r, BaseException):
            continue
        out[r[0]] = r[1]
    total = sum(len(v) for v in out.values())
    logger.info("Parallel search complete queries=%s successful_queries=%s total_results=%s", len(queries), len(out), total)
    await stream_output("logs", f"Done: {total} results from {len(out)} queries", ws)
    return out


async def _filter_academic(scraped, ws=None):
    """Score, rank, and filter sources by the 9-category quality taxonomy."""
    try:
        filtered = score_and_rank_sources(scraped)
        logger.info("Source scoring complete input=%s output=%s", len(scraped), len(filtered))
        if filtered:
            avg = sum(r.get("quality_score", 0) for r in filtered) / len(filtered)
            if filtered[0].get("low_quality_only"):
                await stream_output(
                    "logs",
                    f"Warning: only low-quality sources found ({len(filtered)}); claims will be unverified\n",
                    ws,
                )
            else:
                await stream_output("logs", f"{len(filtered)} sources kept - avg quality score: {avg:.0f}/100\n", ws)
            if ws:
                try:
                    await ws.send_json({
                        "type": "sources",
                        "output": [
                            {
                                "url": doc.get("url", ""),
                                "title": (doc.get("title") or doc.get("url", ""))[:160],
                                "category": doc.get("source_category", "uncategorized"),
                                "category_label": doc.get("source_category_label", "Web source"),
                                "score": doc.get("quality_score", 0),
                            }
                            for doc in filtered[:24]
                        ],
                    })
                except (RuntimeError, OSError):
                    pass
            return filtered
        await stream_output("logs", "No usable sources after scoring; using raw results\n", ws)
        return scraped
    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        await stream_output("logs", f"Source scoring error: {exc}\n", ws)
        return scraped


async def parallel_search_and_scrape_node(state: ResearchState) -> dict[str, Any]:
    """Search and scrape all sub-queries in parallel."""
    sub_queries = state.get("sub_queries", [])
    if not sub_queries:
        await stream_output("logs", "No sub-queries to search\n", state.get("websocket"))
        return state

    ws, cfg = state.get("websocket"), state["cfg"]
    logger.info("Parallel search node start sub_queries=%s", len(sub_queries))
    await stream_output("logs", f"\nSearching {len(sub_queries)} queries in parallel...\n", ws)

    try:
        srd = await _parallel_search(
            sub_queries, cfg.retriever, cfg.max_search_results_per_query, ws,
            include_domains=_include_domains_for_mode(state["report_type"]),
        )
    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        logger.warning("parallel search: %s", exc)
        return state

    visited = set(state.get("visited_urls", []))
    seen = set(visited)
    all_urls = []
    for results in srd.values():
        for r in results:
            url = r.get("href")
            if url and url not in seen:
                seen.add(url)
                all_urls.append(url)
                await stream_output("logs", f"Added URL: {url}\n", ws)

    if not all_urls:
        logger.warning("Parallel search node found no new URLs")
        return state

    max_urls = _max_urls_for_mode(state["report_type"])
    if len(all_urls) > max_urls:
        logger.info("Parallel search node capped URLs mode=%s from=%s to=%s", state["report_type"], len(all_urls), max_urls)
        await stream_output("logs", f"Capping at the {max_urls} best URLs to keep analysis stable.\n", ws)
        all_urls = all_urls[:max_urls]

    logger.info("Parallel search node scraping urls=%s", len(all_urls))
    await stream_output("logs", f"Scraping {len(all_urls)} URLs...\n", ws)
    loop = asyncio.get_running_loop()
    scraped = await loop.run_in_executor(None, _scrape_urls, all_urls, cfg)
    if not scraped:
        logger.warning("Parallel search node scrape returned no documents urls=%s", len(all_urls))
        return {**state, "visited_urls": all_urls}

    filtered = await _filter_academic(scraped, ws)
    await stream_output("logs", f"Building context for {len(sub_queries)} queries...\n", ws)

    if normalize_mode(state["report_type"]) == DEEP:
        context_content = build_mode_context(filtered, state["query"], state["report_type"])
        logger.info("Deep-research context built without embedding compression docs=%s chars=%s", len(filtered), len(context_content))
        if context_content:
            await stream_output("logs", f"Prepared deep-research context from {min(len(filtered), 10)} quality sources.\n", ws)
            return {
                **state,
                "context": [context_content],
                "visited_urls": state.get("visited_urls", []) + all_urls,
                "current_query_index": len(sub_queries),
            }
        logger.warning("Analysis context builder returned empty context, falling back to compression")

    all_contexts: list[str] = []
    try:
        comp = ContextCompressor(documents=filtered, embeddings=state["memory"].get_embeddings(), cfg=cfg)

        async def _ctx(q):
            try:
                return await asyncio.wait_for(loop.run_in_executor(None, comp.get_context, q, 8), timeout=60.0)
            except (asyncio.TimeoutError, RuntimeError, OSError, ValueError, TypeError, KeyError):
                return ""

        contexts = await asyncio.gather(*[_ctx(q) for q in sub_queries], return_exceptions=True)
        all_contexts = [c for c in contexts if isinstance(c, str) and c]
        if not all_contexts:
            fallback_context = build_mode_context(filtered, state["query"], state["report_type"])
            if fallback_context:
                all_contexts = [fallback_context]
                logger.info("Parallel search node used mode context fallback chars=%s", len(fallback_context))
        logger.info("Parallel search node context complete contexts=%s", len(all_contexts))
        await stream_output("logs", f"{len(all_contexts)} contexts built from parallel search\n", ws)
    except (RuntimeError, OSError, ValueError, TypeError, KeyError):
        fallback_context = build_mode_context(filtered, state["query"], state["report_type"])
        all_contexts = [fallback_context] if fallback_context else [
            f"Source: {p.get('url')}\nContent: {p.get('raw_content', '')[:1000]}..." for p in filtered[:5]
        ]

    return {
        **state,
        "context": all_contexts,
        "visited_urls": state.get("visited_urls", []) + all_urls,
        "current_query_index": len(sub_queries),
    }


async def search_and_scrape_node(state: ResearchState) -> dict[str, Any]:
    """Search, scrape, and compress context for a single sub-query iteration."""
    idx = state.get("current_query_index", 0)
    ws, cfg = state.get("websocket"), state["cfg"]
    logger.info(
        "Sequential search node start index=%s sub_queries=%s source_urls=%s",
        idx,
        len(state.get("sub_queries", [])),
        len(state.get("source_urls", [])),
    )

    if state.get("source_urls") and idx == 0:
        urls_to_scrape, sub_query = state["source_urls"], state["query"]
    elif idx < len(state.get("sub_queries", [])):
        sub_query = state["sub_queries"][idx]
        await stream_output("logs", f"\nSearching '{sub_query}'...", ws)
        r = _get_retriever(cfg.retriever)(
            sub_query,
            include_domains=_include_domains_for_mode(state["report_type"]),
        )
        loop = asyncio.get_running_loop()
        sr = await loop.run_in_executor(None, r.search, cfg.max_search_results_per_query)
        urls_to_scrape = [u.get("href") for u in sr]
        logger.info("Sequential search query complete query=%r results=%s urls=%s", sub_query, len(sr), len(urls_to_scrape))
    else:
        return {**state, "current_query_index": idx + 1}

    visited = set(state.get("visited_urls", []))
    new_urls = []
    for url in urls_to_scrape:
        if url and url not in visited:
            visited.add(url)
            new_urls.append(url)
    if not new_urls:
        logger.info("Sequential search node no new URLs index=%s", idx)
        return {**state, "current_query_index": idx + 1}

    max_urls = _max_urls_for_mode(state["report_type"])
    if len(new_urls) > max_urls:
        logger.info("Sequential search node capped URLs mode=%s from=%s to=%s", state["report_type"], len(new_urls), max_urls)
        new_urls = new_urls[:max_urls]

    logger.info("Sequential search node scraping index=%s urls=%s", idx, len(new_urls))
    await stream_output("logs", f"Scraping {len(new_urls)} URLs...\n", ws)
    loop = asyncio.get_running_loop()
    scraped = await loop.run_in_executor(None, _scrape_urls, new_urls, cfg)
    if not scraped:
        logger.warning("Sequential search node scrape returned no documents index=%s urls=%s", idx, len(new_urls))
        return {**state, "current_query_index": idx + 1, "visited_urls": new_urls}

    filtered = await _filter_academic(scraped, ws)
    await stream_output("logs", f"Building context for: {sub_query}...\n", ws)

    context_content = ""
    if filtered:
        try:
            has_urls = bool(state.get("source_urls"))
            is_deep = normalize_mode(state["report_type"]) == DEEP
            if has_urls and is_deep:
                await stream_output("logs", "Preparing full source content...\n", ws)
                context_content = build_mode_context(filtered, state["query"], state["report_type"])
            else:
                comp = ContextCompressor(documents=filtered, embeddings=state["memory"].get_embeddings(), cfg=cfg)
                context_content = await asyncio.wait_for(
                    loop.run_in_executor(None, comp.get_context, sub_query, 8), timeout=60.0
                )
            logger.info("Sequential search node context built index=%s chars=%s", idx, len(context_content))
        except asyncio.TimeoutError:
            context_content = build_mode_context(filtered, state["query"], state["report_type"])
        except (RuntimeError, OSError, ValueError, TypeError, KeyError):
            context_content = build_mode_context(filtered, state["query"], state["report_type"])

    return {
        **state,
        "context": [context_content] if context_content else [],
        "visited_urls": state.get("visited_urls", []) + new_urls,
        "current_query_index": idx + 1,
    }
