
## Search Engines
The project uses the following search engines:
- **Tavily**: A search engine that provides an API for retrieving web search results. It is used in the `TavilySearch` retriever class.
- **DuckDuckGo Search (DDGS)**: A Python library that allows querying the DuckDuckGo search engine. It is used in the `DuckDuckGoSearch` retriever class.

Tavily is the default search engine used by the project. Whether Tavily failes or is not configured, the system falls back to using DuckDuckGo Search.

Refer to the respective retriever classes in the `src/retrievers` directory for implementation details.
