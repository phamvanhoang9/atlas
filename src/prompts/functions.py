"""YAML-based prompt generators."""

from datetime import datetime

from src.prompts.registry import render_prompt


def auto_agent_instructions() -> str:
    """Load the agent selection prompt."""
    prompt = render_prompt("agent_selection", {})
    if prompt is None:
        raise ValueError("Missing agent_selection.yaml template")
    return prompt


def generate_search_queries_prompt(question: str, max_iterations: int = 1) -> str:
    """Load the search query generation prompt."""
    current_year = datetime.now().year
    
    format_example = '["query 1", "query 2"]' if max_iterations > 1 else '["query 1"]'
    good_example = '["RAG chunking strategies site:arxiv.org 2024", "retrieval augmented generation chunk size performance dataset"]'
    
    prompt = render_prompt(
        "query_generation",
        {
            "question": question,
            "max_iterations": max_iterations,
            "current_year": current_year,
            "previous_year": current_year - 1,
            "format_example": format_example,
            "good_example": good_example,
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


def get_report_by_type(report_type: str) -> callable:
    """Get the appropriate report generation prompt based on type."""
    def _render(query: str, context: list[str], report_format: str, total_words: int) -> str:
        # Context is passed as a list of strings and formatted by _normalize_value in render_prompt
        template_name = "qa_report"
        if report_type == "đề xuất bài báo":
            template_name = "paper_recommendation"
            
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


def generate_paper_analysis_prompt(query: str, context: list[str], report_format: str, total_words: int) -> str:
    """Load the paper analysis prompt."""
    prompt = render_prompt(
        "paper_analysis",
        {
            "question": query,
            "context": context,
            "report_format": report_format,
            "total_words": total_words,
            "current_year": datetime.now().year,
        },
    )
    if prompt is None:
        raise ValueError("Missing paper_analysis.yaml template")
    return prompt


def generate_topic_analysis_prompt(query: str, context: list[str], report_format: str, total_words: int) -> str:
    """Load the topic analysis prompt."""
    prompt = render_prompt(
        "topic_analysis",
        {
            "question": query,
            "context": context,
            "report_format": report_format,
            "total_words": total_words,
            "current_year": datetime.now().year,
        },
    )
    if prompt is None:
        raise ValueError("Missing topic_analysis.yaml template")
    return prompt
