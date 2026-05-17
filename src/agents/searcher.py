"""Searcher agent — search, scrape, and context compression."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from src.context.compression import ContextCompressor
from src.orchestration.state import ResearchState
from src.quality.academic_filter import academic_filter
from src.rag.context_builder import build_mode_context
from src.transport.streaming import stream_output

logger = logging.getLogger(__name__)


_QA_INCLUDE_DOMAINS = [
    "huggingface.co",
    "openai.com",
    "anthropic.com",
    "deepmind.google",
    "research.google",
    "ai.meta.com",
    "ai.googleblog.com",
    "blog.research.google",
    "lilianweng.github.io",
    "arxiv.org",
    "openreview.net",
]

_PAPER_REC_INCLUDE_DOMAINS = [
    "arxiv.org",
    "semanticscholar.org",
    "paperswithcode.com",
    "openreview.net",
    "proceedings.neurips.cc",
    "proceedings.mlr.press",
    "aclanthology.org",
    "openaccess.thecvf.com",
    "aaai.org",
    "scholar.google.com",
]


def _include_domains_for_mode(report_type: str) -> list[str] | None:
    if report_type == "hỏi đáp":
        return _QA_INCLUDE_DOMAINS
    if report_type == "đề xuất bài báo":
        return _PAPER_REC_INCLUDE_DOMAINS
    return None  # phân tích uses TavilySearch defaults (broad academic)


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
    if report_type == "phân tích":
        return 18
    if report_type == "đề xuất bài báo":
        return 24
    return 8


async def _parallel_search(queries, retriever_name, max_results=7, ws=None, include_domains=None):
    logger.info("Parallel search start queries=%s retriever=%s max_results=%s", len(queries), retriever_name, max_results)

    async def _one(q):
        try:
            await stream_output("logs", f"Đang tìm kiếm song song: '{q}'...", ws)
            loop = asyncio.get_running_loop()
            r = _get_retriever(retriever_name)(q, include_domains=include_domains)
            res = await loop.run_in_executor(None, r.search, max_results)
            logger.info("Search query complete query=%r results=%s", q, len(res))
            await stream_output("logs", f"Tìm thấy {len(res)} kết quả cho '{q}'", ws)
            return q, res
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning("search '%s': %s", q, exc)
            return q, []

    await stream_output("logs", f"Bắt đầu tìm kiếm song song cho {len(queries)} truy vấn...", ws)
    results = await asyncio.gather(*[_one(q) for q in queries], return_exceptions=True)
    out: dict[str, list] = {}
    for r in results:
        if isinstance(r, BaseException):
            continue
        out[r[0]] = r[1]
    total = sum(len(v) for v in out.values())
    logger.info("Parallel search complete queries=%s successful_queries=%s total_results=%s", len(queries), len(out), total)
    await stream_output("logs", f"Hoàn thành: {total} kết quả từ {len(out)} truy vấn", ws)
    return out


async def _filter_academic(scraped, ws=None):
    try:
        filtered = academic_filter.filter_and_rank_sources(scraped)
        logger.info("Academic filter complete input=%s output=%s", len(scraped), len(filtered))
        if filtered:
            avg = sum(r.get("quality_score", 0) for r in filtered) / len(filtered)
            await stream_output("logs", f"✅ {len(filtered)} nguồn học thuật - Điểm TB: {avg:.2f}\n", ws)
            return filtered
        await stream_output("logs", "⚠️ Không tìm thấy nguồn học thuật, dùng kết quả gốc\n", ws)
        return scraped
    except (RuntimeError, OSError, ValueError, TypeError, KeyError) as exc:
        await stream_output("logs", f"⚠️ Lỗi lọc nguồn: {exc}\n", ws)
        return scraped


async def parallel_search_and_scrape_node(state: ResearchState) -> dict[str, Any]:
    """Search and scrape all sub-queries in parallel."""
    sub_queries = state.get("sub_queries", [])
    if not sub_queries:
        await stream_output("logs", "⚠️ Không có sub-queries\n", state.get("websocket"))
        return state

    ws, cfg = state.get("websocket"), state["cfg"]
    logger.info("Parallel search node start sub_queries=%s", len(sub_queries))
    await stream_output("logs", f"\n🚀 Tìm kiếm song song {len(sub_queries)} queries...\n", ws)

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
                await stream_output("logs", f"✅ Thêm URL: {url}\n", ws)

    if not all_urls:
        logger.warning("Parallel search node found no new URLs")
        return state

    max_urls = _max_urls_for_mode(state["report_type"])
    if len(all_urls) > max_urls:
        logger.info("Parallel search node capped URLs mode=%s from=%s to=%s", state["report_type"], len(all_urls), max_urls)
        await stream_output("logs", f"⚖️ Giới hạn {max_urls} URL tốt nhất để giữ phân tích ổn định.\n", ws)
        all_urls = all_urls[:max_urls]

    logger.info("Parallel search node scraping urls=%s", len(all_urls))
    await stream_output("logs", f"📝 Đang quét {len(all_urls)} urls...\n", ws)
    loop = asyncio.get_running_loop()
    scraped = await loop.run_in_executor(None, _scrape_urls, all_urls, cfg)
    if not scraped:
        logger.warning("Parallel search node scrape returned no documents urls=%s", len(all_urls))
        return {**state, "visited_urls": all_urls}

    filtered = await _filter_academic(scraped, ws)
    await stream_output("logs", f"📃 Đang xử lý context cho {len(sub_queries)} queries...\n", ws)

    if state["report_type"] == "phân tích":
        context_content = build_mode_context(filtered, state["query"], state["report_type"])
        logger.info("Analysis context built without embedding compression docs=%s chars=%s", len(filtered), len(context_content))
        if context_content:
            await stream_output("logs", f"✅ Đã chuẩn bị context phân tích từ {min(len(filtered), 10)} nguồn chất lượng.\n", ws)
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
        await stream_output("logs", f"✅ {len(all_contexts)} contexts từ parallel search\n", ws)
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
        await stream_output("logs", f"\n🔎 Đang tìm kiếm '{sub_query}'...", ws)
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
    await stream_output("logs", f"📝 Đang quét {len(new_urls)} url...\n", ws)
    loop = asyncio.get_running_loop()
    scraped = await loop.run_in_executor(None, _scrape_urls, new_urls, cfg)
    if not scraped:
        logger.warning("Sequential search node scrape returned no documents index=%s urls=%s", idx, len(new_urls))
        return {**state, "current_query_index": idx + 1, "visited_urls": new_urls}

    filtered = await _filter_academic(scraped, ws)
    await stream_output("logs", f"📃 Đang lấy context cho: {sub_query}...\n", ws)

    context_content = ""
    if filtered:
        try:
            has_urls = bool(state.get("source_urls"))
            is_analysis = state["report_type"] == "phân tích"
            if has_urls and is_analysis:
                await stream_output("logs", "📖 Chuẩn bị nội dung đầy đủ...\n", ws)
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
