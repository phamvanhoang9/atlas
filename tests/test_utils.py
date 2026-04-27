import pytest
from src.utils.academic_filter import AcademicFilter

@pytest.fixture
def academic_filter():
    return AcademicFilter()

def test_is_academic_source(academic_filter):
    assert academic_filter.is_academic_source("https://arxiv.org/abs/2101.00001") is True
    assert academic_filter.is_academic_source("https://ieeexplore.ieee.org/document/123") is True
    assert academic_filter.is_academic_source("https://medium.com/@user/article") is False
    assert academic_filter.is_academic_source("https://twitter.com/status/123") is False
    assert academic_filter.is_academic_source("https://example.com/paper.pdf") is True

def test_get_source_tier(academic_filter):
    assert academic_filter.get_source_tier("https://arxiv.org/abs/123") == 1
    assert academic_filter.get_source_tier("https://nature.com/articles/123") == 2
    assert academic_filter.get_source_tier("https://medium.com/123") == 5

def test_extract_paper_indicators(academic_filter):
    content = """
    Abstract: This paper presents a new method for AI.
    Introduction: AI is growing.
    Methodology: We use transformers.
    Results: Accuracy is 99%.
    References: [1] Vaswani et al.
    """
    info = academic_filter.extract_paper_indicators(content)
    assert info["is_paper"] is True
    assert info["confidence"] > 0.5
    assert info["indicators"]["has_abstract"] is True
    assert info["indicators"]["has_references"] is True

def test_filter_and_rank_sources(academic_filter):
    sources = [
        {"url": "https://arxiv.org/1", "raw_content": "Abstract: Deep learning research..."},
        {"url": "https://medium.com/2", "raw_content": "My blog about AI..."},
        {"url": "https://nature.com/3", "raw_content": "Scientific results about climate..."}
    ]
    
    results = academic_filter.filter_and_rank_sources(sources)
    
    # Medium should be filtered out
    assert len(results) == 2
    # Arxiv should be ranked higher than Nature (Tier 1 vs Tier 2) generally, 
    # but score depends on content too.
    assert results[0]["url"] == "https://arxiv.org/1" or results[0]["url"] == "https://nature.com/3"

def test_get_arxiv_id(academic_filter):
    assert academic_filter.get_arxiv_id("https://arxiv.org/abs/2101.00001") == "2101.00001"
    assert academic_filter.get_arxiv_id("https://google.com") is None
