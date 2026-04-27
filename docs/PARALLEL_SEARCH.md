# Parallel Search Documentation

## Overview

ATLAS implements **parallel search** functionality to execute multiple search queries simultaneously, significantly improving research performance. This feature leverages Python's `asyncio` for concurrent execution of I/O-bound search operations.

## Architecture

### Components

1. **`parallel_search()`** - Core function for parallel query execution
2. **`parallel_scrape_urls()`** - Parallel scraping of multiple URL batches  
3. **`_parallel_search_and_scrape_node()`** - LangGraph workflow node
4. **`_route_search_mode()`** - Router to select parallel vs sequential execution

### Workflow

```
┌─────────────────────────────────────────────────────────────┐
│                    Generate Sub-Queries                      │
│                  (e.g., 4 research queries)                  │
└────────────────────────┬────────────────────────────────────┘
                         │
                         ▼
                    ┌─────────┐
                    │ Router  │
                    └────┬────┘
                         │
           ┌─────────────┴──────────────┐
           │                            │
           ▼                            ▼
   ┌───────────────┐          ┌──────────────────┐
   │ Parallel Mode │          │ Sequential Mode  │
   │ (>1 query)    │          │ (1 query)        │
   └───────┬───────┘          └────────┬─────────┘
           │                            │
           ▼                            ▼
   ┌───────────────────────────┐  ┌────────────────┐
   │ Search all queries        │  │ Search query   │
   │ simultaneously            │  │ one by one     │
   │                           │  │                │
   │ Query 1 ─┐                │  │ Query 1        │
   │ Query 2  ├─→ asyncio      │  │    ↓           │
   │ Query 3  │   .gather()    │  │ Done           │
   │ Query 4 ─┘                │  │                │
   └───────────┬───────────────┘  └────────┬───────┘
               │                            │
               └────────────┬───────────────┘
                            │
                            ▼
                   ┌────────────────┐
                   │ Scrape URLs    │
                   │ Filter Results │
                   │ Process Context│
                   └────────────────┘
```
