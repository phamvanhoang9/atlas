"""
Academic source filter and prioritizer for research papers.
"""

import logging
import re
from typing import Any, Optional
from urllib.parse import urlparse


logger = logging.getLogger(__name__)


class AcademicFilter:
    """
    Filter and prioritize academic sources for AI research.
    """

    TIER_1_DOMAINS = [
        "arxiv.org",
        "openreview.net",
        "aclanthology.org",
        "ojs.aaai.org",
        "proceedings.neurips.cc",
        "proceedings.mlr.press",
        "openaccess.thecvf.com",
    ]

    TIER_2_DOMAINS = [
        "ieeexplore.ieee.org",
        "dl.acm.org",
        "springer.com",
        "link.springer.com",
        "sciencedirect.com",
        "elsevier.com",
        "wiley.com",
        "tandfonline.com",
        "nature.com",
        "science.org",
        "pnas.org",
        "jmlr.org",
    ]

    TIER_3_DOMAINS = [
        "scholar.google.com",
        "semanticscholar.org",
        "researchgate.net",
        "dblp.org",
        "paperswithcode.com",
        "huggingface.co",
    ]

    # URL path prefixes that identify non-academic content even on known domains.
    BLACKLIST_URL_PATHS = [
        "huggingface.co/learn/",
        "huggingface.co/datasets/",
        "openai.com/index/",
        "openai.com/vi-vn/",
        "openai.com/blog/",
    ]

    TIER_4_DOMAINS = [
        "ai.googleblog.com",
        "openai.com",
        "deepmind.google",
        "meta.ai",
        "microsoft.com",
        "amazon.science",
    ]

    BLACKLIST_DOMAINS = [
        "medium.com",
        "substack.com",
        "towardsdatascience.com",
        "dev.to",
        "hashnode.com",
        "blog.",
        "forbes.com",
        "techcrunch.com",
        "venturebeat.com",
        "thenextweb.com",
        "zdnet.com",
        "wired.com",
        "linkedin.com",
        "youtube.com",
        "reddit.com",
        "facebook.com",
        "twitter.com",
        "x.com",
        "discord.com",
        "stackexchange.com",
        "stackoverflow.com",
        "udemy.com",
        "coursera.org",
        "edx.org",
        "kaggle.com",
        "cloud.google.com",
        "aws.amazon.com",
        "azure.microsoft.com",
        "engineering.",
        "viblo.asia",
        "hr1tech.com",
        "fpt.ai",
        "fpt.com",
        "fpt-is.com",
        "digital.fpt.com",
        "vinbigdata.com",
        "vnexpress.net",
        "salekit.io",
        "insoftex.com",
        "akka.io",
        "newhorizons.com",
    ]

    TOP_CONFERENCES = [
        "NeurIPS",
        "ICML",
        "ICLR",
        "CVPR",
        "ICCV",
        "ECCV",
        "ACL",
        "EMNLP",
        "NAACL",
        "AAAI",
        "IJCAI",
        "KDD",
        "ICRA",
        "IROS",
        "CoRL",
        "AISTATS",
        "COLT",
        "COLING",
        "EACL",
        "UAI",
        "KDD",
        "WWW",
        "CIKM",
        "RSS",
    ]

    def __init__(self) -> None:
        self.tier_1_domains = self.TIER_1_DOMAINS
        self.tier_2_domains = self.TIER_2_DOMAINS
        self.tier_3_domains = self.TIER_3_DOMAINS
        self.tier_4_domains = self.TIER_4_DOMAINS
        self.blacklist = self.BLACKLIST_DOMAINS
        self.blacklist_url_paths = self.BLACKLIST_URL_PATHS
        self.top_conferences = self.TOP_CONFERENCES

    def is_academic_source(self, url: str) -> bool:
        """Check if URL is from an academic source."""
        if not url:
            return False

        url_lower = url.lower()
        domain = urlparse(url_lower).netloc

        for path_prefix in self.blacklist_url_paths:
            if path_prefix in url_lower:
                return False

        for blacklisted in self.blacklist:
            if blacklisted in domain:
                return False

        for tier in [self.tier_1_domains, self.tier_2_domains, self.tier_3_domains, self.tier_4_domains]:
            for academic_domain in tier:
                if academic_domain in domain:
                    return True

        return url.endswith(".pdf")

    def get_source_tier(self, url: str) -> int:
        """Get tier ranking of source (1=best, 5=worst)."""
        if not url:
            return 5

        domain = urlparse(url.lower()).netloc

        for blacklisted in self.blacklist:
            if blacklisted in domain:
                return 5

        for academic_domain in self.tier_1_domains:
            if academic_domain in domain:
                return 1

        for academic_domain in self.tier_2_domains:
            if academic_domain in domain:
                return 2

        for academic_domain in self.tier_3_domains:
            if academic_domain in domain:
                return 3

        for academic_domain in self.tier_4_domains:
            if academic_domain in domain:
                return 4

        return 5

    def extract_paper_indicators(self, content: str) -> dict[str, Any]:
        """Extract indicators that suggest this is a research paper."""
        if not content:
            return {"is_paper": False, "confidence": 0.0, "bonus_points": 0.0}

        content_lower = content.lower()
        indicators = {
            "has_abstract": bool(re.search(r"\babstract\b", content_lower[:5000], re.IGNORECASE)),
            "has_introduction": bool(re.search(r"\b(introduction|background)\b", content_lower[:10000], re.IGNORECASE)),
            "has_methodology": bool(re.search(r"\b(method|approach|algorithm|architecture)\b", content_lower, re.IGNORECASE)),
            "has_results": bool(re.search(r"\b(results|experiments|evaluation|benchmark)\b", content_lower, re.IGNORECASE)),
            "has_references": bool(re.search(r"\b(references|bibliography|citations?)\b", content_lower, re.IGNORECASE)),
            "has_authors": bool(re.search(r"\b(author|et al\.)\b", content[:2500], re.IGNORECASE)),
            "has_arxiv": bool(re.search(r"arxiv", content_lower)),
            "has_conference": any(conf.lower() in content_lower for conf in self.top_conferences),
        }

        bonus_points = 0.0
        if re.search(r"\b(2024|2025|2026)\b", content[:3000]):
            bonus_points += 0.5

        conference_count = sum(1 for conf in self.top_conferences if conf.lower() in content_lower)
        if conference_count >= 2:
            bonus_points += 0.3

        if re.search(r"\bcite\{|\[[\d,\s]+\]|\(\d{4}\)", content[:10000]):
            bonus_points += 0.3

        if re.search(r"\b(equation|theorem|lemma|proof|\\begin\{|\\[a-z]+\{)", content[:15000]):
            bonus_points += 0.3

        if re.search(r"\b(accuracy|precision|recall|f1[-\s]score|perplexity)\b.*[\d.]+%?", content_lower[:20000]):
            bonus_points += 0.2

        confidence = sum(indicators.values()) / len(indicators)

        return {
            "is_paper": confidence >= 0.4,
            "confidence": confidence,
            "indicators": indicators,
            "bonus_points": bonus_points,
        }

    def filter_and_rank_sources(self, sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """
        Filter and rank sources by academic quality.
        """
        if not sources:
            logger.warning("No sources to filter")
            return []

        academic_sources = []
        total = len(sources)
        skipped_no_content = 0
        skipped_non_academic = 0

        for idx, source in enumerate(sources):
            if idx % 2 == 0 and idx > 0:
                logger.info("Analyzed %s/%s sources", idx, total)

            if not isinstance(source, dict):
                continue

            url = source.get("url", "")
            content = source.get("raw_content", "")

            if not url or not content:
                skipped_no_content += 1
                logger.warning("Skipping %s because it has no content", url)
                continue

            if not self.is_academic_source(url):
                skipped_non_academic += 1
                domain = urlparse(url.lower()).netloc
                logger.warning("Skipping %s because it is not academic; domain=%s", url, domain)
                continue

            tier = self.get_source_tier(url)
            paper_info = self.extract_paper_indicators(content)

            tier_scores = {1: 5.0, 2: 3.5, 3: 2.0, 4: 1.5, 5: 0.0}
            tier_score = tier_scores.get(tier, 0.0)
            content_score = paper_info["confidence"] * 3.5
            bonus_score = paper_info.get("bonus_points", 0.0)
            total_score = tier_score + content_score + bonus_score

            academic_sources.append(
                {
                    **source,
                    "academic_tier": tier,
                    "is_paper": paper_info["is_paper"],
                    "paper_confidence": paper_info["confidence"],
                    "quality_score": round(total_score, 2),
                    "bonus_points": bonus_score,
                }
            )

        logger.info(
            "Academic filter summary: total=%s skipped_no_content=%s skipped_non_academic=%s accepted=%s",
            total,
            skipped_no_content,
            skipped_non_academic,
            len(academic_sources),
        )

        academic_sources.sort(key=lambda source: source.get("quality_score", 0), reverse=True)
        return academic_sources

    def get_arxiv_id(self, url: str) -> Optional[str]:
        """Extract arXiv ID from URL."""
        if "arxiv.org" not in url.lower():
            return None

        match = re.search(r"(\d{4}\.\d{4,5})", url)
        if match:
            return match.group(1)
        return None

    def format_academic_citation(self, source: dict[str, Any]) -> str:
        """Format source as academic citation."""
        url = source.get("url", "")
        title = source.get("title", "Untitled")
        arxiv_id = self.get_arxiv_id(url)

        if arxiv_id:
            return f"[{title}](https://arxiv.org/abs/{arxiv_id})"
        return f"[{title}]({url})"


academic_filter = AcademicFilter()
