"""HTML scraper plugin for Fly.io (fly.io/jobs/)."""

import html
import re
from typing import List

from radar.http import FetchError
from radar.models import CompanyTarget, RawJob
from radar.scrapers.base import BaseHtmlScraper


class FlyIOScraper(BaseHtmlScraper):
    """Scraper for Fly.io careers page."""

    scraper_id = "flyio"
    name = "Fly.io Careers"
    default_url = "https://fly.io/jobs/"

    def scrape(self, target: CompanyTarget) -> List[RawJob]:
        url = target.extra.get("url") or self.default_url
        jobs: List[RawJob] = []

        html_content = self.fetch_html(url)

        articles = re.findall(r"<article[^>]*>(.*?)</article>", html_content, re.DOTALL)
        for a in articles:
            t_match = re.search(
                r"<dd[^>]*class=\"[^\"]*font-heading[^\"]*\"[^>]*>(.*?)</dd>",
                a,
                re.DOTALL,
            )
            if not t_match:
                continue
            title = self.clean_text(t_match.group(1))
            if not title:
                continue

            loc_match = re.search(r"<svg[^>]*>.*?</svg>\s*<div>(.*?)</div>", a, re.DOTALL)
            location = self.clean_text(loc_match.group(1)) if loc_match else "Remote"

            link_match = re.search(r"<a[^>]+href=[\"'](/jobs/[^\"']+)[\"']", a)
            link = f"https://fly.io{link_match.group(1)}" if link_match else url
            slug = (
                link_match.group(1).strip("/").split("/")[-1]
                if link_match
                else f"job_{len(jobs)}"
            )

            p_match = re.search(
                r"<p[^>]*class=\"[^\"]*line-clamp[^\"]*\"[^>]*>(.*?)</p>",
                a,
                re.DOTALL,
            )
            desc_summary = self.clean_text(p_match.group(1)) if p_match else ""

            content = f"{title}\nLocation: {location}\nCompany: Fly.io\n\n{desc_summary}"
            try:
                subpage_html = self.fetch_html(link, timeout=10)
                main_section = self.extract_section(
                    subpage_html,
                    start_marker="<main",
                    end_marker="</main>",
                )
                if main_section:
                    cleaned_body = self.clean_text(main_section)
                    content = f"{title}\nLocation: {location}\n\n{cleaned_body[:4000]}"
            except FetchError:
                pass  # subpage text is best-effort

            jobs.append(
                RawJob(
                    id=f"flyio_{slug}",
                    company_id=target.id,
                    title=title,
                    location=location,
                    url=link,
                    content=content,
                )
            )

        return jobs
