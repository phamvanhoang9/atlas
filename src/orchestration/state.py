from typing import Any, NotRequired, TypedDict

from src.config import Config
from src.memory import Memory


class ResearchState(TypedDict):
    """
    State schema for the research agent workflow.

    Keep this schema stable: LangGraph nodes and routing depend on these keys.
    """

    query: str
    report_type: str
    source_urls: list[str]
    agent: str
    agent_role: str
    sub_queries: list[str]
    current_query_index: int
    search_results: list[dict]
    scraped_content: list[dict]
    context: list[str]
    visited_urls: list[str]
    report: str
    cfg: Config
    websocket: Any
    memory: Memory
    evaluation_result: NotRequired[dict[str, Any]]
    history_id: NotRequired[str]
