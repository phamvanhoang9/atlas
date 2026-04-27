# 🎯 ATLAS Operating Modes

ATLAS operates in **three distinct modes**, each optimized for different research needs. Each mode has its own priority hierarchy and behavior characteristics.

---

## 📋 Mode Overview

| Mode | Icon | Priority | Use Case | Speed | Depth |
|------|------|----------|----------|-------|-------|
| **Hỏi đáp** | ⚡ | Speed first | Quick answers to specific questions | ⚡⚡⚡ | ⭐ |
| **Đề xuất bài báo** | 📚 | Depth first | Comprehensive paper recommendations | ⚡⚡ | ⭐⭐⭐ |
| **Phân tích** | 🔬 | Maximum depth | Deep analysis via specific paper URLs or general topics | ⚡ | ⭐⭐⭐⭐⭐ |

---

## ⚡ Mode 1: Hỏi đáp (Q&A Mode)

### 🎯 Objective
**Provide the fastest possible answers while maintaining accuracy**

### Priority Hierarchy
1. **SPEED** (⚡⚡⚡) - Top priority, minimize latency
2. **ACCURACY** (✅) - No hallucination, use only provided context
3. **CONCISENESS** (✂️) - Minimal formatting, short sentences

### Example Use Cases
- "What is LoRA?"
- "How does RLHF work?"
- "What are the main differences between GPT-3 and GPT-4?"
- "Explain attention mechanism in transformers"

---

## 📚 Mode 2: Đề xuất bài báo (Paper Recommendation Mode)

### 🎯 Objective
**Provide comprehensive, well-researched paper recommendations with complete details**

### Priority Hierarchy
1. **DEPTH** (📖) - Comprehensive analysis of each paper
2. **ACCURACY** (✅✅) - Verify all citations, authors, venues, links
3. **THOROUGHNESS** (🔍) - Complete information for every paper

### Example Use Cases
- "Find papers on Vision Transformers"
- "Latest research on diffusion models"
- "Papers about multi-agent reinforcement learning with code"
- "Recent LLM fine-tuning methods"

---

## 🔬 Mode 3: Phân tích (Analysis Mode)

### 🎯 Objective
**Provide maximum depth analysis with structured reasoning, comparisons, and insights**

### Priority Hierarchy
1. **DEPTH** (🧠) - Multi-layered reasoning and analysis
2. **ACCURACY** (✅✅✅) - Evidence-based with citations
3. **INSIGHTS** (💡) - Synthesize trends, comparisons, implications
4. **STRUCTURE** (📊) - Organized, logical flow

### Example Use Cases
- "Compare LoRA vs Full Fine-tuning vs Adapter methods"
- "Analyze the evolution of attention mechanisms in transformers"
- "Evaluate different approaches to RLHF"
- "Compare multi-agent coordination strategies in robotics"

---

## 🔄 Mode Switching

### When to Switch Modes

**Use Hỏi đáp (⚡) when:**
- You need a quick answer
- The question is specific and narrow
- Speed matters more than depth
- You're doing initial exploration

**Use Đề xuất bài báo (📚) when:**
- You need a reading list for a research topic
- You want papers with code implementations
- You need comprehensive coverage of recent papers
- You're starting a new research direction

**Use Phân tích (🔬) when:**
- You need deep understanding of a field
- You want to compare multiple approaches
- You need insights and synthesis
- You're writing a literature review
- Speed doesn't matter, quality does

---

## 🎓 Best Practices

### For Researchers
1. **Start with Hỏi đáp** for quick exploration
2. **Use Đề xuất bài báo** when you know the topic
3. **Use Phân tích** for deep dives and comparisons
4. **Don't use Phân tích** for simple questions - waste of time
5. **Don't use Hỏi đáp** for literature reviews - insufficient depth

### For System Optimization
1. **Never mix mode behaviors** - each mode is strictly independent
2. **Respect priority hierarchies** - they're designed for optimal results
3. **Don't override mode configs** without good reason - they're carefully tuned
4. **Monitor response times** - ensure modes stay within target ranges

---

## 📝 Summary

ATLAS's three-mode system provides:
- ⚡ **Fast answers** when you need speed (Hỏi đáp)
- 📚 **Comprehensive paper lists** when you need coverage (Đề xuất bài báo)
- 🔬 **Deep analysis** when you need understanding (Phân tích)

Each mode is **strictly independent** and follows its own **priority hierarchy**. Choose the right mode for your research needs!
