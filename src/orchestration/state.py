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
        run_id: Unique id for this workflow run, used to correlate
          plan-approval WebSocket round trips to the correct pending job
          (deep_dive only; see plan_gate_node).
        headless: True for non-interactive execution (e.g. Radar watches),
          where plan_gate_node must auto-approve rather than wait on a
          client response that will never arrive. Defaults to False
          (interactive) when absent.
        research_plan: Deep-dive research plan proposed by plan_gate_node
          for user approval: ``{"headings": list[str], "approach": str,
          "revision": int}``. Present only for report_type == "deep_dive".
        plan_approved: Set by plan_gate_node once the plan is approved
          (True) or rejected/timed out/disconnected (False).
        scored_sources: Deterministic, quality-scored source documents
          (url/title/source_category/source_category_label/quality_score)
          collected during search, stored verbatim from
          ``score_and_rank_sources`` output so downstream deep_dive nodes
          (contradiction_check_node) never need to re-derive scores by
          parsing ``context`` prose.
        contradictions: Deep-dive contradiction ledger entries produced by
          contradiction_check_node: ``[{"type": "cross_source"|"internal",
          "topic": str, "entries": [{"source_url": str, "claim": str}]}]``.
          Category/trust-score display data is joined from
          ``scored_sources`` at render time, not duplicated here.
        confidence_trace: Deterministic confidence assessment computed by
          contradiction_check_node from ``scored_sources`` category
          distribution: ``{"label": "High"|"Medium"|"Low",
          "category_counts": dict, "reasoning": str}``.
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
    run_id: NotRequired[str]
    headless: NotRequired[bool]
    research_plan: NotRequired[dict[str, Any]]
    plan_approved: NotRequired[bool]
    scored_sources: NotRequired[list[dict[str, Any]]]
    contradictions: NotRequired[list[dict[str, Any]]]
    confidence_trace: NotRequired[dict[str, Any]]
