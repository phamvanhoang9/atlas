"""LangChain retriever adapter over pre-fetched search results."""

from typing import Dict, List

from langchain_core.callbacks.manager import CallbackManagerForRetrieverRun
from langchain_core.documents import Document
from langchain_core.retrievers import BaseRetriever


class SearchAPIRetriever(BaseRetriever):
    """Wraps already-fetched search result pages as a LangChain retriever.

    Ignores the query for retrieval purposes; it exists so `pages` (set by
    the caller before invocation) can be fed into LangChain compression
    pipelines like `ContextualCompressionRetriever`, which expect a
    `BaseRetriever`.
    """
    pages: List[Dict] = []

    def _get_relevant_documents(
        self, query: str, *, run_manager: CallbackManagerForRetrieverRun
    ) -> List[Document]:
        """Convert `self.pages` into `Document` objects, ignoring `query`."""

        docs = [
            Document(
                page_content=page.get("raw_content", ""),
                metadata={
                    "title": page.get("title", ""),
                    "source": page.get("url", ""),
                },
            )
            for page in self.pages
        ]

        return docs