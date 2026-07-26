"""Tests that search nodes store deterministic quality-scored sources into
state['scored_sources'] (Giai đoạn 4), so contradiction_check_node never has
to re-derive scores by parsing context prose.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.agents.searcher import parallel_search_and_scrape_node, search_and_scrape_node


def _cfg():
    cfg = MagicMock()
    cfg.retriever = "tavily"
    cfg.max_search_results_per_query = 5
    cfg.user_agent = "test-agent"
    return cfg


def _base_state(**overrides):
    state = {
        "query": "test query",
        "report_type": "deep_dive",
        "source_urls": [],
        "agent": "",
        "agent_role": "",
        "sub_queries": ["q1"],
        "current_query_index": 0,
        "search_results": [],
        "scraped_content": [],
        "context": [],
        "visited_urls": [],
        "report": "",
        "cfg": _cfg(),
        "websocket": None,
        "memory": MagicMock(),
    }
    state.update(overrides)
    return state


_SCRAPED = [{"url": "https://arxiv.org/abs/1234", "title": "A Paper", "raw_content": "content " * 50}]


@pytest.mark.asyncio
async def test_parallel_search_stores_scored_sources():
    state = _base_state()

    with patch(
        "src.agents.searcher._parallel_search",
        new_callable=lambda: __import__("unittest.mock", fromlist=["AsyncMock"]).AsyncMock(
            return_value={"q1": [{"href": "https://arxiv.org/abs/1234"}]}
        ),
    ), patch("src.agents.searcher._scrape_urls", return_value=_SCRAPED):
        result = await parallel_search_and_scrape_node(state)

    assert "scored_sources" in result
    assert len(result["scored_sources"]) == 1
    assert result["scored_sources"][0]["url"] == "https://arxiv.org/abs/1234"
    assert "quality_score" in result["scored_sources"][0]


@pytest.mark.asyncio
async def test_sequential_search_stores_scored_sources():
    # source_urls set so the "has_urls and is_deep" branch takes the cheap
    # build_mode_context path rather than ContextCompressor (which needs a
    # real embeddings backend to construct a text splitter).
    state = _base_state(current_query_index=0, source_urls=["https://arxiv.org/abs/1234"])

    fake_retriever_instance = MagicMock()
    fake_retriever_instance.search.return_value = [{"href": "https://arxiv.org/abs/1234"}]
    fake_retriever_cls = MagicMock(return_value=fake_retriever_instance)

    with patch("src.agents.searcher._get_retriever", return_value=fake_retriever_cls), patch(
        "src.agents.searcher._scrape_urls", return_value=_SCRAPED
    ):
        result = await search_and_scrape_node(state)

    assert "scored_sources" in result
    assert len(result["scored_sources"]) == 1
    assert result["scored_sources"][0]["url"] == "https://arxiv.org/abs/1234"


@pytest.mark.asyncio
async def test_sequential_search_accumulates_scored_sources_across_iterations():
    """scored_sources must accumulate like visited_urls, not overwrite each iteration."""
    state = _base_state(
        current_query_index=0,
        source_urls=["https://arxiv.org/abs/1234"],
        scored_sources=[{"url": "https://existing.example/prior", "quality_score": 10}],
    )

    fake_retriever_instance = MagicMock()
    fake_retriever_instance.search.return_value = [{"href": "https://arxiv.org/abs/1234"}]
    fake_retriever_cls = MagicMock(return_value=fake_retriever_instance)

    with patch("src.agents.searcher._get_retriever", return_value=fake_retriever_cls), patch(
        "src.agents.searcher._scrape_urls", return_value=_SCRAPED
    ):
        result = await search_and_scrape_node(state)

    urls = {s["url"] for s in result["scored_sources"]}
    assert "https://existing.example/prior" in urls
    assert "https://arxiv.org/abs/1234" in urls
