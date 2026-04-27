import logging
import os
import tempfile
import warnings
from concurrent.futures.thread import ThreadPoolExecutor
from contextlib import contextmanager
from functools import partial
from typing import Any, Iterator

import requests
from bs4 import BeautifulSoup
from langchain_community.document_loaders import PyMuPDFLoader
from langchain_community.retrievers import ArxivRetriever

from src.config import Config


logger = logging.getLogger(__name__)

warnings.filterwarnings("ignore")


@contextmanager
def suppress_libxml2_warnings() -> Iterator[None]:
    """
    Context manager to suppress libxml2 encoding warnings from PDF parsing.
    """
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        yield


class Scraper:
    """
    Scraper class to extract content from links.
    """

    def __init__(self, urls: list[str], user_agent: str) -> None:
        self.urls = urls
        self.session = requests.Session()
        self.session.headers.update(
            {
                "User-Agent": user_agent,
                "Accept": "application/pdf,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Upgrade-Insecure-Requests": "1",
            }
        )
        self.config = Config()

    def run(self) -> list[dict[str, Any]]:
        """
        Extracts content from all configured links.
        """
        partial_extract = partial(self.extract_data_from_link, session=self.session)
        with ThreadPoolExecutor(max_workers=getattr(self.config, "max_workers", 16)) as executor:
            contents = executor.map(partial_extract, self.urls)
        return [content for content in contents if content["raw_content"] is not None]

    def extract_data_from_link(self, link: str, session: requests.Session) -> dict[str, Any]:
        """
        Extracts data from one link.
        """
        content = ""
        try:
            if link.endswith(".pdf"):
                content = self.scrape_pdf_with_pymupdf(link)
            elif "arxiv.org" in link:
                doc_num = link.split("/")[-1].replace("v1", "").replace("v2", "").replace("v3", "").replace("v4", "")
                pdf_url = f"https://arxiv.org/pdf/{doc_num}.pdf"
                content = self.scrape_pdf_with_pymupdf(pdf_url)
            elif link:
                content = self.scrape_text_with_bs(link, session)

            if len(content) < 100:
                logger.warning("Scraped content is too short from %s", link)
                return {"url": link, "raw_content": None}
            return {"url": link, "raw_content": content}
        except (requests.exceptions.RequestException, RuntimeError, OSError, ValueError) as exc:
            logger.warning("Failed to scrape %s: %s", link, exc)
            return {"url": link, "raw_content": None}

    def scrape_text_with_bs(self, link: str, session: requests.Session) -> str:
        response = session.get(link, timeout=4)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "lxml", from_encoding=response.encoding)

        for script_or_style in soup(["script", "style"]):
            script_or_style.extract()

        raw_content = self.get_content_from_url(soup)
        lines = (line.strip() for line in raw_content.splitlines())
        chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
        return "\n".join(chunk for chunk in chunks if chunk)

    def scrape_pdf_with_pymupdf(self, url: str) -> str:
        """
        Scrape a PDF with PyMuPDF.
        """
        try:
            if "ieee.org" in url or "ieeexplore" in url:
                return self._scrape_blocking_pdf_host(url)

            with suppress_libxml2_warnings():
                loader = PyMuPDFLoader(url)
                doc = loader.load()
            if doc:
                content = str(doc)
                logger.info("PyMuPDF scraped %s chars from %s", len(content), url)
                return content

            logger.warning("PyMuPDF returned no content for %s", url)
            return ""
        except requests.exceptions.RequestException as exc:
            logger.warning("Network error downloading PDF from %s: %s", url, exc)
            return ""
        except (RuntimeError, OSError, ValueError) as exc:
            error_msg = str(exc)
            if "418" in error_msg:
                logger.warning("IEEE server blocked scraping for %s", url)
            else:
                logger.warning("PyMuPDF failed for %s: %s", url, error_msg)
            return ""

    def _scrape_blocking_pdf_host(self, url: str) -> str:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
            ),
            "Accept": "application/pdf",
            "Referer": "https://ieeexplore.ieee.org/",
        }
        response = requests.get(url, headers=headers, timeout=30)

        if response.status_code == 418:
            logger.warning("IEEE server blocked scraping with status 418 for %s", url)
            return ""
        if response.status_code != 200:
            logger.warning("Failed to download PDF from %s with status %s", url, response.status_code)
            return ""

        temp_path = ""
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as temp_file:
                temp_file.write(response.content)
                temp_path = temp_file.name

            with suppress_libxml2_warnings():
                loader = PyMuPDFLoader(temp_path)
                doc = loader.load()
            if doc:
                content = str(doc)
                logger.info("PyMuPDF scraped %s chars from %s", len(content), url)
                return content
            return ""
        finally:
            if temp_path:
                try:
                    os.unlink(temp_path)
                except OSError:
                    logger.debug("Failed to remove temporary PDF %s", temp_path, exc_info=True)

    def scrape_pdf_with_arxiv(self, query: str) -> str:
        """
        Scrape a PDF with ArxivRetriever.
        """
        try:
            with suppress_libxml2_warnings():
                retriever = ArxivRetriever(load_max_docs=2, doc_content_chars_max=None)
                docs = retriever.get_relevant_documents(query=query)
            if docs:
                logger.info("ArxivRetriever retrieved %s chars for %s", len(docs[0].page_content), query)
                return docs[0].page_content

            logger.warning("ArxivRetriever returned no documents for %s", query)
            return ""
        except (RuntimeError, OSError, ValueError) as exc:
            logger.warning("ArxivRetriever failed for %s: %s", query, exc)
            return ""

    def get_content_from_url(self, soup: BeautifulSoup) -> str:
        """
        Get text from parsed HTML.
        """
        text = ""
        tags = ["p", "h1", "h2", "h3", "h4", "h5"]
        for element in soup.find_all(tags):
            text += element.text + "\n"
        return text
