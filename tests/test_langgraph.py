import inspect

import pytest

from src.agents.planner import choose_agent_node
from src.orchestration.router import route_after_agent_selection
from src.orchestration.runner import LangGraphResearcher
from src.orchestration.state import ResearchState
from src.transport.manager import run_agent


@pytest.mark.asyncio
async def test_workflow_structure():
    researcher = LangGraphResearcher(
        query="test query",
        report_type="research_report",
    )

    assert researcher.workflow is not None


@pytest.mark.asyncio
async def test_state_initialization():
    researcher = LangGraphResearcher(
        query="test query",
        report_type="research_report",
    )

    assert researcher.query == "test query"
    assert researcher.report_type == "research_report"
    assert researcher.cfg is not None
    assert researcher.memory is not None


@pytest.mark.asyncio
async def test_node_execution():
    researcher = LangGraphResearcher(
        query="What is machine learning?",
        report_type="research_report",
    )

    test_state = {
        "query": "What is machine learning?",
        "report_type": "research_report",
        "source_urls": [],
        "agent": "",
        "agent_role": "",
        "sub_queries": [],
        "current_query_index": 0,
        "search_results": [],
        "scraped_content": [],
        "context": [],
        "visited_urls": [],
        "report": "",
        "cfg": researcher.cfg,
        "websocket": None,
        "memory": researcher.memory,
    }

    result = await choose_agent_node(test_state)
    assert "agent" in result
    assert "agent_role" in result

    route = route_after_agent_selection(result)
    assert route in ["use_provided_urls", "generate_queries"]


@pytest.mark.asyncio
async def test_imports():
    from langgraph.checkpoint.memory import MemorySaver
    from langgraph.graph import END, StateGraph

    assert LangGraphResearcher is not None
    assert ResearchState is not None
    assert StateGraph is not None
    assert END is not None
    assert MemorySaver is not None


@pytest.mark.asyncio
async def test_websocket_integration():
    source = inspect.getsource(run_agent)
    assert "LangGraphResearcher" in source
