# 🗺️ ATLAS
**Agentic Task & Literature Analysis System**

> *AI Research Assistant with Multi-Agent Orchestration*

ATLAS is an intelligent research platform designed for AI researchers and engineers. It uses a multi-agent architecture to automate literature review, paper recommendation, and in-depth analysis. Built with a LangGraph-based workflow, ATLAS provides structured, high-quality outputs in various formats.

ATLAS is open-source and serves the Vietnamese AI research community, but it can be easily adapted for global use. The system prioritizes academic sources and provides real-time streaming of research progress.

*The initial idea of this project originated from:* 
- The open-source project: [GPT Researcher](https://github.com/assafelovic/gpt-researcher) - Based on this project, I have made significant modifications to the architecture, workflow, and output formats to better suit the needs of AI researchers, especially in the Vietnamese community. 
- My experience as an AI Engineer working on NLP projects at the company, where I deeply understood the company's product and what the customers needed with our product, and I wanted to build my own research assistant that forwards and centers around the needs of an AI researcher or engineer.

## ✨ Key Features

- 🤖 **Multi-Agent Orchestration**: Specialized agents for different research tasks (Q&A, Paper Recommendations, Paper Analysis)
- 🔄 **LangGraph Architecture**: State machine-based workflow for better maintainability and observability
- 📊 **3 Output Formats**: Q&A, Paper Recommendations, Paper Analysis via provided URLs or general topic
- 🔍 **Academic-First Search**: Prioritizes arXiv, OpenReview, major conferences
- 🚀 **Parallel Search**: Search multiple queries simultaneously for improved performance
- ⚡ **Real-time Streaming**: WebSocket-based live research progress
- 🎯 **Quality Filtering**: Academic source ranking with tier-based scoring
- 🇻🇳 **Vietnamese Support**: Built for Vietnamese AI research community


## Installation

### Prerequisites
- Python 3.12+
- OpenAI API Key
- Tavily API Key (for web search)

### Setup

1. **Clone the repository**
   ```bash
   git clone https://github.com/yourusername/atlas-research.git
   cd atlas
   ```

2. **Create Python environment**
   ```bash
   python3 -m venv venv
   source venv/bin/activate  # On Windows: venv\Scripts\activate
   ```

3. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

4. **Set environment variables**
   ```bash
   # Create .env file
   echo "OPENAI_API_KEY=your_key_here" >> .env
   echo "TAVILY_API_KEY=your_key_here" >> .env
   ```

## 🚀 Usage

### Run Locally

**Method 1: Direct Python**
```bash
python main.py
```

**Method 2: Uvicorn (recommended)**
```bash
python -m uvicorn src.api.server:app --reload
```

**Method 3: Docker**
```bash
docker-compose up -d --build
```

Then open `http://localhost:8000` in your browser.

### Choose Research Mode

ATLAS operates in **three distinct modes**, each optimized for different research needs:

1. ⚡ **Hỏi đáp (Q&A)** - Fast, concise answers (Priority: Speed > Accuracy > Conciseness)
   - 2 total sub-queries (1 generated + original), ~700 words
   - Use when: You need quick answers to specific questions
   
2. 📚 **Đề xuất bài báo (Paper Recommendations)** - Comprehensive paper lists (Priority: Depth > Accuracy > Thoroughness)
   - 4 total sub-queries (3 generated + original), ~2000 words
   - Use when: You need a reading list with papers + code
   
3. 🔬 **Phân tích (Analysis)** - Deep analysis with comparisons (Priority: Depth > Accuracy > Insights > Structure)
   - 6 total sub-queries (5 generated + original), ~3000 words
   - Use when: You need comprehensive analysis, comparisons, and insights

## 🏗️ Architecture

### LangGraph Workflow

ATLAS uses a **LangGraph-based architecture** to orchestrate the multi-agent workflow. Each research task is represented as a node in the graph, with defined inputs, outputs, and state transitions.

![LangGraph Workflow Diagram](images/langgraph_workflow.png)

### System Components

```
ATLAS
├── Mode Configuration
│   ├── Hỏi đáp (Q&A) — Quick answers
│   ├── Đề xuất bài báo — Comprehensive recommendations
│   └── Phân tích — In-depth analysis (specific paper via URLs or a general topic)
│
├── LangGraph Workflow Engine
│   ├── State Schema (TypedDict)
│   ├── Nodes (choose_agent, generate_sub_queries, search_and_scrape, etc.)
│   ├── Conditional Routing (parallel / sequential search)
│   ├── Context Processing (semantic compression, relevance scoring)
│   └── Output Formatting & Summarization
│
├── Search & Retrieval
│   ├── Parallel Search Engine (asyncio-based)
│   ├── Sequential Search (fallback)
│   └── Tavily Search Integration
│
├── Academic Filter (Tier-based scoring)
│   ├── Tier 1: arXiv, OpenReview, ACL Anthology, etc.
│   ├── Tier 2: IEEE, ACM, Springer, Nature, Science, etc.
│   ├── Tier 3: Google Scholar, ResearchGate, etc.
│   ├── Tier 4: Google Blog, DeepMind, Meta AI, etc.
│   └── Blacklist: Medium, TowardsDataScience, etc.
│
├── Context Management
│   └── Semantic Compression
│
└── Output Generation
    └── 4 specialized formats
```

## 🤝 Contributing

This project serves the Vietnamese AI research community. Contributions welcome!

## 📄 License

MIT License - See LICENSE file for details.

---

**Built with ❤️ for the AI research community**
