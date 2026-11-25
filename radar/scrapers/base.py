"""Base contract and utilities for generic HTML scraping plugins."""

from abc import ABC, abstractmethod
import html
import re
from typing import Dict, List, Optional
import urllib.request

from radar.models import CompanyTarget, RawJob


class BaseHtmlScraper(ABC):
    """Abstract base class for custom website HTML scrapers."""

    scraper_id: str
    name: str = ""
    default_headers: Dict[str, str] = {
        "User-Agent": "JobRadar/2.0 (compatible; generic-html-scraper; +https://github.com/ilmanzo/job-radar)",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    }

    def fetch_html(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        timeout: int = 20,
    ) -> str:
        """Fetch raw HTML string from target URL."""
        req_headers = {**self.default_headers, **(headers or {})}
        req = urllib.request.Request(url, headers=req_headers)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw_bytes = resp.read()
            charset = resp.headers.get_content_charset() or "utf-8"
            return raw_bytes.decode(charset, errors="replace")

    @staticmethod
    def clean_text(html_text: str) -> str:
        """Strip HTML tags and normalize whitespace."""
        if not html_text:
            return ""
        # Remove script and style tags completely
        text = re.sub(
            r"<(script|style)[^>]*>.*?</\1>",
            "",
            html_text,
            flags=re.DOTALL | re.IGNORECASE,
        )
        # Remove all other HTML tags
        text = re.sub(r"<[^>]+>", " ", text)
        # Unescape HTML entities
        text = html.unescape(text)
        # Normalize whitespace
        return " ".join(text.split()).strip()

    @staticmethod
    def extract_section(
        content: str,
        start_marker: str,
        end_marker: Optional[str] = None,
    ) -> str:
        """Extract a substring between two markers."""
        if start_marker not in content:
            return ""
        after_start = content.split(start_marker, 1)[1]
        if end_marker and end_marker in after_start:
            return after_start.split(end_marker, 1)[0]
        return after_start

    @abstractmethod
    def scrape(self, target: CompanyTarget) -> List[RawJob]:
        """Fetch and parse HTML for a target company, returning RawJob objects."""
        pass
