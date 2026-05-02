"""Runner — high-level entry point that wires config → workflow → execution."""

from __future__ import annotations

import logging
import time
from typing import Any, List, Optional

from src.config import Config
from src.memory import Memory
from src.orchestration.state import ResearchState
from src.orchestration.workflow import build_workflow

logger = logging.getLogger(__name__)


class LangGraphResearcher:
    """High-level researcher that configures and runs the LangGraph workflow."""

    def __init__(
        self,
        query: str,
        report_type: str = "research_report",
        source_urls: Optional[List[str]] = None,
        config_path: Optional[str] = None,
        websocket: Any = None,
        enable_parallel_search: Optional[bool] = None,
    ) -> None:
        self.query = query
        self.report_type = report_type
        self.source_urls = source_urls or []
        self.websocket = websocket

        self.cfg = Config(config_path)
        self.cfg.apply_mode_config(report_type)

        self.enable_parallel_search = (
            enable_parallel_search
            if enable_parallel_search is not None
            else self.cfg.enable_parallel_search
        )

        if self.enable_parallel_search:
            logger.info("Parallel search: ENABLED")
        else:
            logger.info("Parallel search: DISABLED")

        logger.info(
            "Researcher initialized mode=%s query_len=%s source_urls=%s provider=%s model=%s retriever=%s",
            self.report_type,
            len(self.query),
            len(self.source_urls),
            self.cfg.llm_provider,
            self.cfg.llm_model,
            self.cfg.retriever,
        )

        self.memory = Memory(self.cfg.embedding_provider)
        self.workflow = build_workflow(
            enable_parallel_search=self.enable_parallel_search,
            enable_evaluation=self.cfg.enable_evaluation,
        )

    def _initial_state(self) -> ResearchState:
        return {
            "query": self.query,
            "report_type": self.report_type,
            "source_urls": self.source_urls,
            "agent": "",
            "agent_role": "",
            "sub_queries": [],
            "current_query_index": 0,
            "search_results": [],
            "scraped_content": [],
            "context": [],
            "visited_urls": [],
            "report": "",
            "cfg": self.cfg,
            "websocket": self.websocket,
            "memory": self.memory,
        }

    async def run_with_state(self) -> ResearchState:
        """Execute the research workflow and return the final state."""
        initial_state = self._initial_state()

        final_state = None
        start = time.perf_counter()
        logger.info("Workflow start mode=%s source_urls=%s", self.report_type, len(self.source_urls))
        async for state in self.workflow.astream(initial_state):
            final_state = state
            if isinstance(state, dict) and state:
                node_name = list(state.keys())[-1]
                node_state = state[node_name]
                logger.info(
                    "Workflow node complete node=%s sub_queries=%s context_items=%s visited_urls=%s report_chars=%s elapsed_ms=%.1f",
                    node_name,
                    len(node_state.get("sub_queries", [])) if isinstance(node_state, dict) else 0,
                    len(node_state.get("context", [])) if isinstance(node_state, dict) else 0,
                    len(node_state.get("visited_urls", [])) if isinstance(node_state, dict) else 0,
                    len(node_state.get("report", "")) if isinstance(node_state, dict) else 0,
                    (time.perf_counter() - start) * 1000,
                )

        if final_state and isinstance(final_state, dict):
            last_node_key = list(final_state.keys())[-1]
            last_state = final_state[last_node_key]
            report = last_state.get("report", "")
            logger.info(
                "Workflow complete last_node=%s report_chars=%s elapsed_ms=%.1f",
                last_node_key,
                len(report),
                (time.perf_counter() - start) * 1000,
            )
            return last_state

        logger.warning("Workflow finished without final state elapsed_ms=%.1f", (time.perf_counter() - start) * 1000)
        return initial_state

    async def run(self) -> str:
        """Execute the research workflow and return the report."""
        final_state = await self.run_with_state()
        return final_state.get("report", "")
