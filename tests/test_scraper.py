"""Tests for `Scraper`: HTML/PDF extraction, content filtering, and the run loop."""

import pytest
from unittest.mock import MagicMock, patch
from src.scraper.scraper import Scraper

@pytest.fixture
def scraper():
    """Provide a `Scraper` configured with a single test URL and user agent."""
    return Scraper(urls=["https://example.com"], user_agent="test-agent")

def test_scraper_initialization(scraper):
    assert scraper.urls == ["https://example.com"]
    assert scraper.session.headers["User-Agent"] == "test-agent"

@patch("src.scraper.scraper.requests.Session.get")
def test_scrape_text_with_bs(mock_get, scraper):
    # Mock response
    mock_response = MagicMock()
    # Content >= 100 chars to avoid "Nội dung quá ngắn" skip
    mock_response.content = ("<html><body><h1>Title</h1>" + "<p>Paragraph</p>" * 20 + "</body></html>").encode('utf-8')
    mock_response.encoding = "utf-8"
    mock_get.return_value = mock_response
    
    content = scraper.scrape_text_with_bs("https://example.com", scraper.session)
    
    assert "Title" in content
    assert "Paragraph" in content

def test_get_content_from_url(scraper):
    from bs4 import BeautifulSoup
    html = "<html><body><h1>Header</h1><p>Text</p><span>Ignore</span></body></html>"
    soup = BeautifulSoup(html, "lxml")
    content = scraper.get_content_from_url(soup)
    
    assert "Header" in content
    assert "Text" in content
    assert "Ignore" not in content

@patch("src.scraper.scraper.Scraper.scrape_text_with_bs")
@patch("src.scraper.scraper.Scraper.scrape_pdf_with_pymupdf")
def test_extract_data_from_link(mock_pdf, mock_text, scraper):
    long_content = "This is a very long content that is definitely more than one hundred characters long to pass the length check in the scraper function."
    
    # Test HTML link
    mock_text.return_value = long_content
    result = scraper.extract_data_from_link("https://example.com/page", scraper.session)
    assert result["url"] == "https://example.com/page"
    assert result["raw_content"] == long_content
    
    # Test PDF link
    mock_pdf.return_value = long_content
    result = scraper.extract_data_from_link("https://example.com/file.pdf", scraper.session)
    assert result["url"] == "https://example.com/file.pdf"
    assert result["raw_content"] == long_content
    
    # Test Arxiv link
    result = scraper.extract_data_from_link("https://arxiv.org/abs/2101.00001", scraper.session)
    assert "arxiv.org" in result["url"]
    assert result["raw_content"] == long_content

@patch("src.scraper.scraper.Scraper.extract_data_from_link")
def test_scraper_run(mock_extract, scraper):
    scraper.urls = ["url1", "url2"]
    mock_extract.side_effect = [
        {"url": "url1", "raw_content": "content1"},
        {"url": "url2", "raw_content": "content2"}
    ]
    
    results = scraper.run()
    assert len(results) == 2
    assert results[0]["raw_content"] == "content1"
    assert results[1]["raw_content"] == "content2"
