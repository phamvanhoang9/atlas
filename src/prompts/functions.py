"""YAML-based prompt generators."""

from datetime import datetime

from src.modes import ASK, DEEP_DIVE, get_mode_spec, normalize_mode
from src.prompts.registry import render_prompt


_SEARCH_POLICIES = {
    "ask": (
        "Broad, trustworthy web coverage: official docs, AI lab blogs, GitHub\n"
        "repos, credible engineering blogs, and technical discussions. Do NOT\n"
        "restrict to academic papers. Avoid SEO spam and content farms."
    ),
    "compare": (
        "High-quality primary sources: papers, preprints, benchmarks, model\n"
        "cards, and official announcements. Include at least one strong\n"
        "academic operator per query when sensible: site:arxiv.org, paper,\n"
        "benchmark, NeurIPS, ICML, ICLR, ACL. Prefer 'github', 'benchmark',\n"
        "'dataset', 'evaluation' terms when relevant."
    ),
    "deep_dive": (
        "Mixed multi-angle coverage: combine academic queries (site:arxiv.org,\n"
        "paper, benchmark) with official announcements, GitHub repositories,\n"
        "and credible engineering analyses. Cover technical mechanisms,\n"
        "real-world adoption, costs, and criticisms across the query set."
    ),
}

_GOOD_EXAMPLES = {
    "ask": '["LLM KV cache quantization production support", "vLLM KV cache quantization docs"]',
    "compare": '["RAG chunking strategies site:arxiv.org 2026", "retrieval augmented generation chunk size benchmark dataset"]',
    "deep_dive": '["speculative decoding paper benchmark 2026", "speculative decoding vLLM TensorRT-LLM adoption", "speculative decoding limitations production"]',
}


def auto_agent_instructions() -> str:
    """Load the agent selection prompt."""
    prompt = render_prompt("agent_selection", {})
    if prompt is None:
        raise ValueError("Missing agent_selection.yaml template")
    return prompt


def generate_scope_gate_prompt(query: str) -> str:
    """Load the AI-domain scope gate prompt."""
    prompt = render_prompt("scope_gate", {"query": query})
    if prompt is None:
        raise ValueError("Missing scope_gate.yaml template")
    return prompt


def generate_search_queries_prompt(question: str, max_iterations: int = 1, mode: str | None = None) -> str:
    """Load the search query generation prompt with the mode's search policy."""
    current_year = datetime.now().year
    canonical = normalize_mode(mode) if mode else ASK

    format_example = '["query 1", "query 2"]' if max_iterations > 1 else '["query 1"]'

    prompt = render_prompt(
        "query_generation",
        {
            "question": question,
            "max_iterations": max_iterations,
            "current_year": current_year,
            "previous_year": current_year - 1,
            "format_example": format_example,
            "search_policy": _SEARCH_POLICIES[canonical],
            "good_example": _GOOD_EXAMPLES[canonical],
        },
    )
    if prompt is None:
        raise ValueError("Missing query_generation.yaml template")
    return prompt


def generate_suggested_questions_prompt(query: str, report: str, report_type: str) -> str:
    """Load the suggested questions prompt."""
    prompt = render_prompt(
        "suggested_questions",
        {
            "query": query,
            "report": report[:2400],
            "report_type": report_type,
            "current_year": datetime.now().year,
        },
    )
    if prompt is None:
        raise ValueError("Missing suggested_questions.yaml template")
    return prompt


def get_report_by_type(report_type: str, has_source_urls: bool = False) -> callable:
    """Get the report generation prompt renderer for a mode.

    Mode → template mapping lives in the mode registry. Deep research with
    user-provided URLs uses the source-analysis template instead of the
    broad deep-research one.
    """
    spec = get_mode_spec(report_type)
    template_name = spec.url_report_template if has_source_urls else spec.report_template

    def _render(query: str, context: list[str], report_format: str, total_words: int) -> str:
        # Context is passed as a list of strings and formatted by _normalize_value in render_prompt
        prompt = render_prompt(
            template_name,
            {
                "question": query,
                "context": context,
                "report_format": report_format,
                "total_words": total_words,
                "current_year": datetime.now().year,
            },
        )
        if prompt is None:
            raise ValueError(f"Missing {template_name}.yaml template")
        return prompt

    return _render


def system_role_for_mode(report_type: str, has_source_urls: bool = False) -> str:
    """Default system role per mode, used when agent selection yields none."""
    canonical = normalize_mode(report_type)
    if canonical == DEEP_DIVE and has_source_urls:
        return (
            "You are an AI researcher explaining the provided source documents in depth. "
            "Use ONLY information from the provided sources, never training knowledge. "
            "Guide the reader to understand and apply the work."
        )
    if canonical == DEEP_DIVE:
        return (
            "You are a senior AI intelligence analyst. Stay strictly on the asked topic. "
            "Synthesize insights across sources, analyze contradictions, and assess "
            "engineering and product impact with explicit confidence levels."
        )
    if canonical == ASK:
        return (
            "You are a precise AI research assistant. Answer directly, ground every "
            "claim in the provided sources, and flag uncertainty honestly."
        )
    return (
        "You are an AI research analyst. Prioritize primary sources, separate fact "
        "from interpretation and hype, and tie every claim to a citation."
    )
