"""YAML-based prompt generators."""

from datetime import datetime

from src.modes import ASK, COMPARE, DEEP_DIVE, get_mode_spec, normalize_mode
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


_SCOPE_INSTRUCTIONS = {
    "ai_native": (
        "Default to IN SCOPE. Accept any knowledge, technical, or research "
        "task that an AI builder or AI shipper might plausibly bring — even "
        "if it never says the word \"AI\" — including questions in another "
        "domain (e.g. healthcare, finance, law) that they may be evaluating "
        "for an AI application, and adjacent engineering/research/technical "
        "questions. Only mark OUT OF SCOPE when the query has no research, "
        "technical, or professional knowledge angle at all: spam, personal "
        "lifestyle chit-chat, entertainment, sports scores, recipes, travel "
        "planning, or general news with nothing to research or build."
    ),
    "ai_strict": (
        "Only mark IN SCOPE when artificial intelligence is the central "
        "subject: machine learning, LLMs, AI models, AI tooling, AI "
        "infrastructure, AI agents, AI coding tools, AI research papers, AI "
        "products, AI policy/safety, or the engineering/business "
        "implications of AI systems. Queries about software engineering, "
        "data, math, or hardware count as in scope ONLY when AI is central "
        "to the question. General knowledge, lifestyle, travel, food, "
        "sports, medicine, finance, or news questions without an AI angle "
        "are out of scope."
    ),
}


def generate_scope_gate_prompt(query: str, scope_mode: str = "ai_native") -> str:
    """Load the scope gate prompt for *scope_mode* ("ai_native" soft-default,
    or "ai_strict" hard AI-only block; unrecognized values fall back to
    "ai_native" the same way normalize_mode() falls back for research modes)."""
    instructions = _SCOPE_INSTRUCTIONS.get(scope_mode, _SCOPE_INSTRUCTIONS["ai_native"])
    prompt = render_prompt("scope_gate", {"query": query, "scope_instructions": instructions})
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
    if canonical == COMPARE:
        return (
            "You are a decision-support analyst building a structured comparison, not "
            "writing an essay. Score every option against the same criteria, cite the "
            "evidence behind each cell, and never declare a winner the sources don't "
            "actually support."
        )
    return (
        "You are an AI research analyst. Prioritize primary sources, separate fact "
        "from interpretation and hype, and tie every claim to a citation."
    )


def generate_explain_prompt(passage: str, context: str = "") -> str:
    """Load the "Explain this" prompt (Trụ cột 5, modes_redesign_plan.md Mục 4.5).

    A single fast-tier LLM call, deliberately outside LangGraph/state.py.
    """
    prompt = render_prompt("explain", {"passage": passage, "context": context})
    if prompt is None:
        raise ValueError("Missing explain.yaml template")
    return prompt


def generate_plan_prompt(question: str, feedback: str = "") -> str:
    """Load the Deep Dive plan-gate prompt (modes_redesign_plan.md Mục 7 Giai đoạn 4).

    *feedback* carries the user's "regenerate" request text, if any.
    """
    feedback_block = (
        f"The user asked for a different plan, with this feedback: {feedback}"
        if feedback
        else ""
    )
    prompt = render_prompt("plan_generation", {"question": question, "feedback_block": feedback_block})
    if prompt is None:
        raise ValueError("Missing plan_generation.yaml template")
    return prompt


def generate_contradiction_check_prompt(question: str, context: list[str]) -> str:
    """Load the Deep Dive contradiction-check prompt."""
    prompt = render_prompt("contradiction_check", {"question": question, "context": context})
    if prompt is None:
        raise ValueError("Missing contradiction_check.yaml template")
    return prompt


def generate_vet_verdict_prompt(claim: str, evidence: list[dict]) -> str:
    """Load the "Vet this" verdict prompt.

    *evidence* must already be retrieved and scored by source_scorer
    (deterministic) — this prompt only asks the LLM for the final verdict
    over evidence it cannot expand.
    """
    lines = [
        f"- [{item.get('quality_score', '?')}/100 · {item.get('source_category_label', 'Web source')}] "
        f"{item.get('title') or item.get('url', 'Untitled')} — {item.get('snippet', '')}".strip()
        for item in evidence
    ]
    evidence_block = "\n".join(lines) if lines else "(no evidence retrieved)"
    prompt = render_prompt("vet_verdict", {"claim": claim, "evidence": evidence_block})
    if prompt is None:
        raise ValueError("Missing vet_verdict.yaml template")
    return prompt
