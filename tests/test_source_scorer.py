"""Tests for the 9-category source quality scorer and its ranking behavior."""

from src.agents.generator import _ensure_report_structure
from src.quality.source_scorer import (
    CATEGORY_SCORES,
    classify_source,
    score_and_rank_sources,
)


def _doc(url: str, content: str = "some content") -> dict:
    return {"url": url, "raw_content": content, "title": url}


# ------------------------------------------------------------- classification

def test_peer_reviewed_classification() -> None:
    assert classify_source("https://proceedings.neurips.cc/paper/2026/x").category == "peer_reviewed"
    assert classify_source("https://aclanthology.org/2026.acl-long.1/").category == "peer_reviewed"
    assert classify_source("https://openreview.net/forum?id=abc").category == "peer_reviewed"


def test_arxiv_preprint_classification() -> None:
    assert classify_source("https://arxiv.org/abs/2606.01234").category == "arxiv_preprint"
    assert classify_source("https://www.semanticscholar.org/paper/x").category == "arxiv_preprint"


def test_official_classification() -> None:
    assert classify_source("https://docs.anthropic.com/en/docs/about-claude").category == "official"
    assert classify_source("https://huggingface.co/meta-llama/Llama-4").category == "official"
    assert classify_source("https://pytorch.org/docs/stable/").category == "official"
    # Generic docs. subdomain heuristic
    assert classify_source("https://docs.vllm.ai/en/latest/").category == "official"


def test_ai_lab_blog_paths_beat_official_domains() -> None:
    assert classify_source("https://openai.com/blog/new-model").category == "ai_lab_blog"
    assert classify_source("https://www.anthropic.com/news/release").category == "ai_lab_blog"
    assert classify_source("https://huggingface.co/blog/some-post").category == "ai_lab_blog"
    # Non-blog path on the same domain stays official.
    assert classify_source("https://openai.com/api/pricing").category == "official"


def test_github_engineering_forum_news() -> None:
    assert classify_source("https://github.com/vllm-project/vllm").category == "github_repo"
    assert classify_source("https://blog.cloudflare.com/workers-ai").category == "engineering_blog"
    assert classify_source("https://team.github.io/post").category == "engineering_blog"
    assert classify_source("https://news.ycombinator.com/item?id=1").category == "tech_forum"
    assert classify_source("https://techcrunch.com/2026/06/11/ai-funding").category == "news"


def test_low_quality_classification() -> None:
    assert classify_source("https://medium.com/@someone/ai-post").category == "low_quality"
    assert classify_source("https://www.linkedin.com/pulse/ai-trends").category == "low_quality"
    assert classify_source("https://someblog.substack.com/p/ai").category == "low_quality"
    assert classify_source("https://huggingface.co/learn/course1").category == "low_quality"
    assert classify_source("").category == "low_quality"
    assert classify_source("not-a-url").category == "low_quality"


def test_unknown_domain_is_uncategorized() -> None:
    result = classify_source("https://random-research-site.org/article")
    assert result.category == "uncategorized"
    assert result.score == CATEGORY_SCORES["uncategorized"]


def test_scores_are_ordered_by_trust() -> None:
    assert (
        CATEGORY_SCORES["official"]
        > CATEGORY_SCORES["peer_reviewed"]
        > CATEGORY_SCORES["arxiv_preprint"]
        > CATEGORY_SCORES["ai_lab_blog"]
        > CATEGORY_SCORES["github_repo"]
        > CATEGORY_SCORES["engineering_blog"]
        > CATEGORY_SCORES["tech_forum"]
        > CATEGORY_SCORES["news"]
        > CATEGORY_SCORES["low_quality"]
    )


# ------------------------------------------------------------------- ranking

def test_ranking_sorts_by_quality_score() -> None:
    docs = [
        _doc("https://techcrunch.com/post"),
        _doc("https://arxiv.org/abs/2606.00001"),
        _doc("https://github.com/org/repo"),
    ]
    ranked = score_and_rank_sources(docs)
    categories = [doc["source_category"] for doc in ranked]
    assert categories == ["arxiv_preprint", "github_repo", "news"]
    assert all("quality_score" in doc and "source_category_label" in doc for doc in ranked)


def test_low_quality_sources_are_excluded_when_alternatives_exist() -> None:
    docs = [
        _doc("https://medium.com/@x/post"),
        _doc("https://arxiv.org/abs/2606.00001"),
    ]
    ranked = score_and_rank_sources(docs)
    assert len(ranked) == 1
    assert ranked[0]["source_category"] == "arxiv_preprint"


def test_low_quality_only_results_are_kept_but_flagged() -> None:
    docs = [_doc("https://medium.com/@x/post"), _doc("https://dev.to/y/post")]
    ranked = score_and_rank_sources(docs)
    assert len(ranked) == 2
    assert all(doc["low_quality_only"] for doc in ranked)


def test_documents_without_content_are_dropped() -> None:
    docs = [{"url": "https://arxiv.org/abs/2606.00001", "raw_content": ""}]
    assert score_and_rank_sources(docs) == []


# ------------------------------------------- category labels flow to reports

def test_reference_section_shows_source_category_labels() -> None:
    context = [
        "### Source 1: Speculative Decoding Survey\n"
        "URL: https://arxiv.org/abs/2606.00001\n"
        "Category: arXiv/preprint\n"
        "Recommended citation: [Speculative Decoding Survey](https://arxiv.org/abs/2606.00001)\n"
        "Quality score: 80.00\n"
        "Relevant to query: speculative decoding\n"
        "Content:\nSurvey content."
    ]
    report = (
        "# Speculative decoding\n\n"
        "## Answer\nIt speeds up inference [1].\n\n"
        "## Sources\n- [1] Speculative Decoding Survey. https://arxiv.org/abs/2606.00001\n"
    )

    normalized = _ensure_report_structure(report, "Speculative decoding", context)

    assert "[Speculative Decoding Survey](https://arxiv.org/abs/2606.00001) — *arXiv/preprint*" in normalized
