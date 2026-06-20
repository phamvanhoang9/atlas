"""Shared state schema passed between nodes in the research LangGraph workflow."""

from typing import Any, NotRequired, TypedDict

from src.config import Config
from src.memory import Memory


class ResearchState(TypedDict):
    """State schema for the research agent workflow.

    Keep this schema stable: LangGraph nodes and routing depend on these keys.

    Attributes:
        query: The user's original research question.
        report_type: Mode id (e.g. ``quick``, ``research``, ``deep``) that
          drives config overrides and prompt selection.
        source_urls: User-supplied URLs to scrape directly, bypassing search
          query generation when non-empty.
        agent: Selected agent type/persona for this run.
        agent_role: Role description associated with the selected agent.
        sub_queries: Generated search queries derived from the main query.
        current_query_index: Index of the next sub-query to process during
          sequential search; compared against ``len(sub_queries)`` for
          loop termination in ``route_after_search``.
        search_results: Raw search engine results collected so far.
        scraped_content: Full text/content scraped from visited URLs.
        context: Compressed/selected context chunks used for report generation.
        visited_urls: URLs already scraped, used to avoid duplicate fetches.
        report: The generated report text (built up while streaming).
        cfg: The resolved ``Config`` for this run, including mode overrides.
        websocket: Active websocket connection used to stream progress, or
          ``None`` when running without a live client.
        memory: ``Memory`` instance used for embedding-backed operations.
        evaluation_result: Optional RAGAS evaluation metrics, present only
          when evaluation is enabled.
        history_id: Optional id of the persisted history record for this run.
        scope_refusal: Set by the scope gate when the query is judged
          out-of-scope, signaling the workflow to end early.
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
    scope_refusal: NotRequired[bool]
