# Feature: Topic & Paper Analysis in "Phân tích" mode

## Overview

The "Phân tích" mode now supports **2 use cases**:

### 1. **Specific Paper Analysis**
- **When**: User provides paper URLs
- **Operation**: Detailed analysis of **ONE** specific paper
- **Focus**: Deep explanation of the paper, implementation guidance
- **Prompt used**: `generate_paper_analysis_prompt`

### 2. **Topic Analysis**
- **When**: User enters a topic (e.g.: "Ứng dụng của GraphRAG trong hệ thống RAG") without providing URLs
- **Operation**: Search and analyze **COMPREHENSIVELY** about the topic
- **Focus**: Stay focused on the topic, **DO NOT wander** to other topics
- **Prompt used**: `generate_topic_analysis_prompt`

---

## How it works

### Flow for Topic Analysis

```
User enters: "GraphRAG Applications"
    ↓
[Select mode: Analysis]
    ↓
[Check: Any URLs?]
    ↓ NO
[Topic Analysis Mode]
    ↓
[Generate search queries focused on topic]
    ↓
[Search for related papers]
    ↓
[Scrape and collect context]
    ↓
[Analyze FOCUSED on topic]
    ↓ (Using generate_topic_analysis_prompt)
[Output: Comprehensive analysis report on topic]
```

### Flow for Paper Analysis

```
User enters URLs or paper links
    ↓
[Select mode: Analysis]
    ↓
[Check: Any URLs?]
    ↓ YES
[Paper Analysis Mode]
    ↓
[Scrape content from URLs]
    ↓
[Detailed analysis of specific paper]
    ↓ (Using generate_paper_analysis_prompt)
[Output: Deep analysis report on paper]
```

---

## Comparison of 2 Use Cases

| Aspect | Paper Analysis | Topic Analysis |
|--------|----------------|----------------|
| **Input** | Paper URLs | Topic/keyword |
| **Number of papers** | 1 specific paper | Multiple papers (8-10+) |
| **Depth** | Very detailed about 1 paper | Comprehensive about topic |
| **Focus** | Paper content only | Topic-focused from multiple sources |
| **Length** | 3000+ words | 3000+ words |
| **Sections** | Method, Results, Implementation | Approaches, SOTA, Trends, Insights |
| **External knowledge** | ❌ NOT used | ✅ Synthesized from multiple papers |

---

## Topic Analysis Prompt Characteristics

### Design Principles

1. **🎯 Absolute focus**
   - Only analyze the asked topic
   - Do not wander to other topics
   - Filter out unrelated information

2. **📊 Multi-source synthesis**
   - Use insights from multiple papers
   - Compare different approaches
   - Build big picture from multiple perspectives

3. **📝 Depth and comprehensiveness**
   - Minimum 3000 words
   - Analyze approaches (800-1200 words)
   - State-of-the-art and trends
   - Practical considerations

4. **💻 Implementation-focused**
   - Code availability
   - Tools and frameworks
   - Real-world applications
   - Getting started guide

### Output Structure

```markdown
# 🔬 [Topic Name]

## 🎯 Topic Overview
## 📋 Research Context and Motivation
## 💡 Current Main Approaches
   ⭐ This section is VERY LONG (800-1200 words)
   - Approach 1: Details...
   - Approach 2: Details...
   - Compare approaches
## 🔬 Datasets and Benchmarks
## 📊 State-of-the-art and Trends [current year]
## 💻 Practical Aspects
## 💪 Key Insights and Lessons
## 📚 Important Papers to Read
## ⚡ Executive Summary
```

---

## Usage Examples

### Example 1: Topic Analysis

**Input:**
```
Query: "GraphRAG Applications in RAG systems"
Mode: Analysis
URLs: [none]
```

**Output:**
- Comprehensive analysis of GraphRAG
- Comparison with traditional RAG
- Current approaches (Knowledge Graph + RAG, etc.)
- Benchmarks and datasets
- SOTA and trends in current year
- Real-world use cases
- Recommended papers to read

### Example 2: Paper Analysis

**Input:**
```
Query: "Analyze this paper"
Mode: Analysis
URLs: ["https://arxiv.org/abs/2401.xxxxx"]
```

**Output:**
- Detailed analysis of 1 paper from URL
- Method, architecture, experiments
- Strengths, limitations
- Implementation guide
- Based entirely on paper content

---

## Implementation Details

### `src/master/langgraph_agent.py`
- ✅ Updated `_generate_report_node()`
- Logic to differentiate 2 cases:
  ```python
  if is_analysis_mode:
      if has_source_urls:
          # Paper Analysis
          generate_prompt = generate_paper_analysis_prompt
      else:
          # Topic Analysis
          generate_prompt = generate_topic_analysis_prompt
  ```

### Configuration

Topic Analysis uses the "analysis" mode config:
```json
{
    "max_iterations": 5,
    "max_search_results_per_query": 7,
    "token_limit": 12000,
    "total_words": 3000,
    "temperature": 0.3,
    "enable_parallel_search": true
}
```

---

## Testing

### Test Case 1: Topic Analysis
```python
# Test topic analysis
query = "Transfer learning in computer vision"
report_type = "phân tích"
source_urls = []  # No URLs

# Expected: Use generate_topic_analysis_prompt
# Output: Comprehensive analysis of transfer learning from multiple papers
```

### Test Case 2: Paper Analysis
```python
# Test specific paper analysis
query = "Analyze ResNet paper"
report_type = "phân tích"
source_urls = ["https://arxiv.org/abs/1512.03385"]

# Expected: Use generate_paper_analysis_prompt
# Output: Detailed analysis of ResNet paper
```

---

## Important Notes

### For Topic Analysis:
1. ⚠️ **MUST focus on topic** - Prompt has strict checklist
2. ✅ Synthesize from multiple papers (8-10+ papers)
3. ✅ Analyze diverse approaches
4. ✅ Include current SOTA and trends
5. ❌ DO NOT use training knowledge outside context

### For Paper Analysis:
1. ⚠️ **ONLY use information from paper** - No knowledge base
2. ✅ Focus on single paper only
3. ✅ Detailed about method and implementation
4. ❌ DO NOT compare with other papers if paper doesn't mention

---

## Benefits

### ✅ Advantages of Topic Analysis

1. **Comprehensive Coverage**: Analysis from multiple papers
2. **Focused Research**: Stay focused on topic, no wandering
3. **Multiple Perspectives**: Multiple approaches and insights
4. **Current Trends**: Latest SOTA and trends
5. **Practical**: Code, tools, real-world applications

### ✅ Advantages of Paper Analysis

1. **Deep Dive**: Extremely detailed analysis of 1 paper
2. **Implementation Ready**: Specific implementation guidance
3. **Accurate**: Only uses paper content, no fabrication
4. **Educational**: Teaches every aspect of the paper thoroughly

---

## Summary

**The "Phân tích" mode is now smarter:**

- 🔗 **With URLs** → Specific paper analysis (Paper Analysis)
- 🔍 **Without URLs** → Topic analysis (Topic Analysis)

**Both provide:**
- High depth (3000+ words)
- Implementation-focused
- Academic rigor
- No fabricated information

**Differences:**
- Paper Analysis: 1 paper, very detailed
- Topic Analysis: Multiple papers, comprehensive overview, FOCUSED on topic

---

**Created Date**: 2026-02-16  
**Author**: stevehoang  
**Version**: 1.0
