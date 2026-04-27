# LangGraph Guide

## What is LangGraph?

LangGraph is a library for building stateful, multi-agent applications with LLMs. It provides:

- **State Management**: Centralized state with type safety
- **Graph-based Workflows**: Nodes and edges define execution flow
- **Conditional Routing**: Dynamic path selection based on state
- **Checkpointing**: Save and resume workflow execution
- **Observability**: Clear visualization of workflow structure

## Architecture 

```python
class LangGraphResearcher:
    def _build_workflow(self):
        workflow = StateGraph(ResearchState)
        
        # Define nodes
        workflow.add_node("choose_agent", self._choose_agent_node)
        workflow.add_node("generate_sub_queries", self._generate_sub_queries_node)
        workflow.add_node("search_and_scrape", self._search_and_scrape_node)
        workflow.add_node("process_context", self._process_context_node)
        workflow.add_node("generate_report", self._generate_report_node)
        
        # Define flow
        workflow.set_entry_point("choose_agent")
        workflow.add_conditional_edges("choose_agent", self._route_after_agent_selection)
        workflow.add_edge("generate_sub_queries", "search_and_scrape")
        workflow.add_conditional_edges("search_and_scrape", self._route_after_search)
        workflow.add_edge("process_context", "generate_report")
        workflow.add_edge("generate_report", END)
        
        # Compile without checkpointer (cfg, websocket, memory are not serializable)
        return workflow.compile()
```

**Benefits:**
- Centralized state schema (`ResearchState`)
- Each step is an isolated, testable node
- Clear workflow visualization
- Built-in checkpointing
- Easy to extend with new nodes

## Workflow Visualization

```
START
  │
  └──> [choose_agent]
         │
         ├─(conditional)─> Has source URLs?
         │                 │
         │                 ├─ YES ──> [search_and_scrape]
         │                 │
         │                 └─ NO ───> [generate_sub_queries]
         │                              │
         │                              └──> [search_and_scrape]
         │                                      │
         │                                      ├─(conditional)─> More queries?
         │                                      │                 │
         │                                      │                 ├─ YES ──> [search_and_scrape] (loop)
         │                                      │                 │
         │                                      │                 └─ NO ───> [process_context]
         │                                      │                              │
         │                                      │                              └──> [generate_report]
         │                                      │                                      │
         │                                      │                                      └──> END
```

## State Schema

```python
class ResearchState(TypedDict):
    # Input
    query: str
    report_type: str
    source_urls: List[str]
    
    # Agent selection
    agent: str
    agent_role: str
    
    # Search and retrieval
    sub_queries: List[str]
    current_query_index: int
    search_results: List[dict]
    scraped_content: List[dict]
    
    # Context (uses operator.add to append)
    context: Annotated[List[str], operator.add]
    visited_urls: Annotated[List[str], operator.add]
    
    # Output
    report: str
    
    # Configuration
    cfg: Config
    websocket: any
    memory: Memory
```

### Key Features

- **Type Safety**: TypedDict provides IDE autocomplete and type checking
- **Immutability**: Each node returns new state (functional style)
- **Annotations**: `operator.add` enables list appending across nodes
- **Shared Context**: All nodes access same centralized state

## Node Descriptions

### 1. choose_agent
**Purpose**: Select the appropriate research agent based on query

**Input State**: `query`, `cfg`

**Output State**: `agent`, `agent_role`

**Logic**:
```python
async def _choose_agent_node(self, state: ResearchState) -> ResearchState:
    response = await create_chat_completion(
        model=state['cfg'].llm_model,
        messages=[{"role": "system", "content": auto_agent_instructions()}, ...],
        ...
    )
    agent_dict = json.loads(cleaned_response)
    return {**state, "agent": agent_dict["server"], "agent_role": agent_dict["agent_role_prompt"]}
```

### 2. generate_sub_queries
**Purpose**: Break down main query into focused sub-queries

**Input State**: `query`, `cfg`

**Output State**: `sub_queries`, `current_query_index`

**Logic**:
```python
async def _generate_sub_queries_node(self, state: ResearchState) -> ResearchState:
    response = await create_chat_completion(...)
    sub_queries = json.loads(cleaned_response)
    sub_queries.append(state['query'])  # Include original query
    return {**state, "sub_queries": sub_queries, "current_query_index": 0}
```

### 3. search_and_scrape
**Purpose**: Search web, scrape URLs, filter academic sources, extract context

**Input State**: `sub_queries`, `current_query_index`, `visited_urls`, `cfg`

**Output State**: `context` (appended), `visited_urls` (appended), `current_query_index` (incremented)

**Logic**:
```python
async def _search_and_scrape_node(self, state: ResearchState) -> ResearchState:
    current_index = state['current_query_index']
    sub_query = state['sub_queries'][current_index]
    
    # Search
    retriever = get_retriever(state['cfg'].retriever)
    search_results = retriever(sub_query).search(...)
    
    # Scrape
    scraped_results = scrape_urls(new_urls, state['cfg'])
    
    # Filter academic
    filtered_results = academic_filter.filter_and_rank_sources(scraped_results)
    
    # Extract context
    context_compressor = ContextCompressor(documents=filtered_results, ...)
    context_content = context_compressor.get_context(sub_query, 8)
    
    return {
        **state,
        "context": [context_content],  # Appended via operator.add
        "visited_urls": new_urls,      # Appended via operator.add
        "current_query_index": current_index + 1
    }
```

**Note**: This node can loop multiple times via conditional routing.

### 4. process_context
**Purpose**: Validate and consolidate collected context

**Input State**: `context`

**Output State**: (no changes, validation only)

**Logic**:
```python
async def _process_context_node(self, state: ResearchState) -> ResearchState:
    if not state.get('context') or all(not c for c in state['context']):
        await stream_output("logs", "⚠️ Không có context để xử lý\n", ...)
    return state
```

### 5. generate_report
**Purpose**: Synthesize final research report from context

**Input State**: `query`, `context`, `agent_role`, `report_type`, `cfg`

**Output State**: `report`

**Logic**:
```python
async def _generate_report_node(self, state: ResearchState) -> ResearchState:
    generate_prompt = get_report_by_type(state['report_type'])
    
    report = await create_chat_completion(
        model=state['cfg'].llm_model,
        messages=[
            {"role": "system", "content": state['agent_role']},
            {"role": "user", "content": generate_prompt(state['query'], state['context'], ...)}
        ],
        stream=True,
        websocket=state['websocket'],
        ...
    )
    
    return {**state, "report": report}
```

## Routing Functions

### _route_after_agent_selection
```python
def _route_after_agent_selection(self, state: ResearchState) -> str:
    if state.get('source_urls') and len(state['source_urls']) > 0:
        return "use_provided_urls"  # Skip query generation
    else:
        return "generate_queries"    # Generate sub-queries
```

### _route_after_search
```python
def _route_after_search(self, state: ResearchState) -> str:
    current_index = state['current_query_index']
    total_queries = len(state['sub_queries'])
    
    if current_index < total_queries:
        return "continue_search"    # Loop back to search_and_scrape
    else:
        return "process_context"    # Move to next stage
```

## Usage

### Basic Usage

```python
from src.orchestration.runner import LangGraphResearcher

# Create researcher
researcher = LangGraphResearcher(
    query="Tôi nên đọc bài báo nào về xây dựng hệ thống Agentic RAG",
    report_type="research_report",
    websocket=websocket
)

# Run workflow
report = await researcher.run()
print(report)
```

### With Source URLs

```python
researcher = LangGraphResearcher(
    query="Phân tích những bài báo này",
    report_type="research_report",
    source_urls=["https://arxiv.org/abs/1234.5678", ...],
    websocket=websocket
)
report = await researcher.run()
```

### Accessing Workflow Graph

```python
python visualization/workflow_graph.py
```

## Testing

### Unit Testing Nodes
```python
# Run the langgraph test script
python tests/test_langgraph.py
```

## Debugging

### Enable Verbose Logging

```python
import logging
logging.basicConfig(level=logging.DEBUG)

# Run workflow
researcher = LangGraphResearcher(...)
report = await researcher.run()
```

### Inspect State at Each Step

```python
config = {"configurable": {"thread_id": "debug_thread"}}

async for state_update in researcher.workflow.astream(initial_state, config):
    print(f"Node output: {state_update}")
    # Inspect state at each node transition
```

## Performance Considerations

### Memory Usage
- State is immutable, each node creates new state dict
- For large contexts, consider streaming or chunking
- MemorySaver checkpointer stores full state history

### Latency
- Each node transition has small overhead (~1-5ms)
- Async execution allows concurrent I/O operations
- Conditional routing adds negligible overhead

### Scalability
- Can process multiple queries in parallel with different thread_ids
- Checkpointing enables distributed execution
- Add caching layer for repeated queries

## Future Enhancements

### 1. Parallel Search
```python
workflow.add_node("parallel_search", self._parallel_search_node)

async def _parallel_search_node(self, state):
    tasks = [self._search_single_query(q) for q in state['sub_queries']]
    results = await asyncio.gather(*tasks)
    return {**state, "search_results": results}
```

### 2. Human-in-the-Loop
```python
workflow.add_node("review_context", self._review_context_node)

async def _review_context_node(self, state):
    # Wait for human approval
    await state['websocket'].send_json({"type": "review_request", ...})
    approval = await state['websocket'].receive_json()
    return {**state, "approved": approval['approved']}
```

### 3. Multi-Agent Collaboration
```python
workflow.add_node("specialist_agent_1", self._specialist_1_node)
workflow.add_node("specialist_agent_2", self._specialist_2_node)
workflow.add_node("orchestrator", self._orchestrator_node)

# Orchestrator delegates to specialists
workflow.add_conditional_edges("orchestrator", self._route_to_specialist)
```

## Troubleshooting

### Issue: "Cannot import LangGraphResearcher"
**Solution**: Ensure langgraph is installed:
```bash
pip install langgraph langgraph-checkpoint
```

### Issue: "State type mismatch"
**Solution**: Check ResearchState TypedDict matches your data:
```python
# Debug state
print(f"State keys: {state.keys()}")
print(f"Expected: {ResearchState.__annotations__.keys()}")
```

### Issue: "Workflow hangs"
**Solution**: Check for infinite loops in conditional routing:
```python
def _route_after_search(self, state):
    # Ensure index increments
    assert state['current_query_index'] < len(state['sub_queries'])
    ...
```

## Resources

- [LangGraph Documentation](https://langchain-ai.github.io/langgraph/)
- [LangGraph Tutorials](https://langchain-ai.github.io/langgraph/tutorials/)
- [State Machine Patterns](https://langchain-ai.github.io/langgraph/concepts/#state-machine)
