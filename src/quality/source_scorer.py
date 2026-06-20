"""Source quality scoring — the trust core of ATLAS (decision D-008).

Deterministic, rule-based classification of every source URL into a fixed
taxonomy. Scores drive search-result ranking, low-quality exclusion, and the
category labels shown next to citations. No LLM involvement: the scorer must
be free, explainable, and unit-testable to function as a trust feature.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from urllib.parse import urlparse

logger = logging.getLogger(__name__)


# Fixed taxonomy (brief: Source Quality System). Score is 0-100.
CATEGORY_SCORES: dict[str, int] = {
    "official": 95,
    "peer_reviewed": 90,
    "arxiv_preprint": 80,
    "ai_lab_blog": 75,
    "github_repo": 70,
    "engineering_blog": 60,
    "tech_forum": 50,
    "uncategorized": 45,
    "news": 40,
    "low_quality": 10,
}

CATEGORY_LABELS: dict[str, str] = {
    "official": "Official source",
    "peer_reviewed": "Peer-reviewed paper",
    "arxiv_preprint": "arXiv/preprint",
    "ai_lab_blog": "AI lab blog",
    "github_repo": "GitHub repository",
    "engineering_blog": "Engineering blog",
    "tech_forum": "Technical forum",
    "uncategorized": "Web source",
    "news": "News article",
    "low_quality": "Low-quality source",
}

#: Categories that may never serve as primary evidence.
NON_PRIMARY_CATEGORIES = ("low_quality",)


@dataclass(frozen=True)
class SourceClassification:
    """The taxonomy category, numeric score, and display label for a source URL.

    Attributes:
      category: One of the keys in CATEGORY_SCORES (e.g. "official", "peer_reviewed").
      score: The 0-100 trust score for the category, from CATEGORY_SCORES.
      label: The human-readable citation label for the category, from CATEGORY_LABELS.
    """

    category: str
    score: int
    label: str


_PEER_REVIEWED_DOMAINS = (
    "proceedings.neurips.cc", "proceedings.mlr.press", "aclanthology.org",
    "openreview.net", "ieeexplore.ieee.org", "dl.acm.org", "jmlr.org",
    "ojs.aaai.org", "openaccess.thecvf.com", "nature.com", "science.org",
    "pnas.org", "link.springer.com", "sciencedirect.com",
)

_PREPRINT_DOMAINS = (
    "arxiv.org", "biorxiv.org", "ssrn.com", "semanticscholar.org",
    "paperswithcode.com", "alphaxiv.org",
)

_OFFICIAL_DOMAINS = (
    "openai.com", "anthropic.com", "deepmind.google", "ai.meta.com",
    "mistral.ai", "ai.google.dev", "platform.openai.com", "docs.anthropic.com",
    "huggingface.co", "pytorch.org", "tensorflow.org", "jax.dev",
    "developer.nvidia.com", "docs.python.org", "kubernetes.io",
    "modelcontextprotocol.io", "qwen.ai", "x.ai", "cohere.com", "deepseek.com",
)

_AI_LAB_BLOG_DOMAINS = (
    "ai.googleblog.com", "blog.research.google", "research.google",
    "bair.berkeley.edu", "crfm.stanford.edu", "hai.stanford.edu",
    "lilianweng.github.io", "distill.pub", "thegradient.pub",
    "alignmentforum.org", "epoch.ai", "interconnects.ai",
)

# Lab-blog paths on otherwise "official" domains.
_AI_LAB_BLOG_PATH_PREFIXES = (
    "openai.com/blog", "openai.com/index", "openai.com/research",
    "anthropic.com/news", "anthropic.com/research", "anthropic.com/engineering",
    "deepmind.google/discover", "ai.meta.com/blog", "mistral.ai/news",
    "huggingface.co/blog",
)

_GITHUB_DOMAINS = ("github.com", "gitlab.com", "codeberg.org")

_ENGINEERING_BLOG_DOMAINS = (
    "netflixtechblog.com", "eng.uber.com", "blog.cloudflare.com",
    "engineering.fb.com", "githubengineering.com", "dropbox.tech",
    "slack.engineering", "stripe.com", "vercel.com", "modal.com",
    "simonwillison.net", "eugeneyan.com", "chiphuyen.com",
    "newsletter.pragmaticengineer.com", "martinfowler.com",
)

_TECH_FORUM_DOMAINS = (
    "news.ycombinator.com", "stackoverflow.com", "stackexchange.com",
    "discuss.huggingface.co", "discuss.pytorch.org", "lesswrong.com",
    "reddit.com", "old.reddit.com", "lobste.rs",
)

_NEWS_DOMAINS = (
    "techcrunch.com", "venturebeat.com", "theverge.com", "wired.com",
    "zdnet.com", "reuters.com", "bloomberg.com", "theinformation.com",
    "arstechnica.com", "semafor.com", "axios.com", "nytimes.com",
    "theregister.com", "businessinsider.com", "cnbc.com", "forbes.com",
)

_LOW_QUALITY_DOMAINS = (
    "medium.com", "towardsdatascience.com", "dev.to", "hashnode.com",
    "quora.com", "pinterest.com", "linkedin.com", "facebook.com",
    "twitter.com", "x.com", "youtube.com", "tiktok.com", "instagram.com",
    "udemy.com", "coursera.org", "geeksforgeeks.org", "tutorialspoint.com",
    "w3schools.com", "blogspot.com", "wordpress.com", "substack.com",
    "viblo.asia", "salekit.io", "insoftex.com", "newhorizons.com",
)

# Path prefixes that downgrade otherwise-trusted domains (course pages, SEO).
_LOW_QUALITY_PATH_PREFIXES = (
    "huggingface.co/learn",
    "openai.com/vi-vn",
)


def _domain_matches(domain: str, table: tuple[str, ...]) -> bool:
    return any(domain == entry or domain.endswith(f".{entry}") for entry in table)


def classify_source(url: str) -> SourceClassification:
    """Classify a URL into the fixed source-quality taxonomy.

    Deterministic rule order: low-quality paths/domains, lab-blog paths,
    then domain tables from highest to lowest trust, then fallback.
    """

    def _result(category: str) -> SourceClassification:
        return SourceClassification(
            category=category,
            score=CATEGORY_SCORES[category],
            label=CATEGORY_LABELS[category],
        )

    if not url or not url.lower().startswith(("http://", "https://")):
        return _result("low_quality")

    url_lower = url.lower()
    parsed = urlparse(url_lower)
    domain = parsed.netloc.removeprefix("www.")
    domain_and_path = f"{domain}{parsed.path}"

    for prefix in _LOW_QUALITY_PATH_PREFIXES:
        if domain_and_path.startswith(prefix):
            return _result("low_quality")
    if _domain_matches(domain, _LOW_QUALITY_DOMAINS):
        return _result("low_quality")

    for prefix in _AI_LAB_BLOG_PATH_PREFIXES:
        if domain_and_path.startswith(prefix):
            return _result("ai_lab_blog")

    if _domain_matches(domain, _PEER_REVIEWED_DOMAINS):
        return _result("peer_reviewed")
    if _domain_matches(domain, _PREPRINT_DOMAINS):
        return _result("arxiv_preprint")
    if _domain_matches(domain, _OFFICIAL_DOMAINS):
        return _result("official")
    if _domain_matches(domain, _AI_LAB_BLOG_DOMAINS):
        return _result("ai_lab_blog")
    if _domain_matches(domain, _GITHUB_DOMAINS):
        return _result("github_repo")
    if _domain_matches(domain, _ENGINEERING_BLOG_DOMAINS):
        return _result("engineering_blog")
    if _domain_matches(domain, _TECH_FORUM_DOMAINS):
        return _result("tech_forum")
    if _domain_matches(domain, _NEWS_DOMAINS):
        return _result("news")

    if domain.startswith(("docs.", "developer.", "developers.")):
        return _result("official")
    if domain.startswith(("engineering.", "eng.", "tech.")):
        return _result("engineering_blog")
    if domain.endswith(".github.io"):
        return _result("engineering_blog")
    if domain.startswith("blog.") or "/blog/" in parsed.path:
        return _result("engineering_blog")

    return _result("uncategorized")


def score_and_rank_sources(
    documents: list[dict],
    *,
    drop_low_quality: bool = True,
) -> list[dict]:
    """Attach source-quality metadata to scraped documents and rank by score.

    Every document gains ``source_category``, ``source_category_label``, and a
    0-100 ``quality_score``. Low-quality sources are excluded from the result
    (they must never be primary evidence) unless *nothing else* survives — in
    that degraded case they are kept and flagged ``low_quality_only=True`` so
    the report layer can mark claims as unverified.
    """
    scored: list[dict] = []
    for document in documents:
        if not isinstance(document, dict):
            continue
        url = document.get("url", "")
        if not url or not document.get("raw_content"):
            continue
        classification = classify_source(url)
        scored.append(
            {
                **document,
                "source_category": classification.category,
                "source_category_label": classification.label,
                "quality_score": classification.score,
            }
        )

    primary = [doc for doc in scored if doc["source_category"] not in NON_PRIMARY_CATEGORIES]
    if primary or not drop_low_quality:
        result = primary if drop_low_quality else scored
        dropped = len(scored) - len(result)
        if dropped:
            logger.info("Source scorer dropped %s low-quality source(s)", dropped)
        return sorted(result, key=lambda doc: doc["quality_score"], reverse=True)

    logger.warning(
        "Only low-quality sources available (%s); keeping them flagged as non-primary evidence",
        len(scored),
    )
    return sorted(
        [{**doc, "low_quality_only": True} for doc in scored],
        key=lambda doc: doc["quality_score"],
        reverse=True,
    )
