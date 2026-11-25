"""Generic ATS source adapter for custom HTML scrapers."""

from typing import List

from radar.http import FetchError
from radar.models import CompanyTarget, RawJob
from radar.scrapers import get_scraper
from radar.sources.base import BaseSource


class HtmlScraperSource(BaseSource):
    """Source adapter delegating to custom HTML scrapers registered in radar.scrapers."""

    ats_name = "scraper"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        scraper_id = target.extra.get("scraper") or target.board or target.id
        scraper = get_scraper(scraper_id)
        if not scraper:
            raise FetchError(f"no HTML scraper plugin registered for '{scraper_id}' (target: '{target.id}')")

        return scraper.scrape(target)


class GenericHtmlScraperAliasSource(HtmlScraperSource):
    """Alias allowing 'ats: html_scraper' in targets.yaml."""

    ats_name = "html_scraper"
