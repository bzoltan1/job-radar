"""HTML scraper plugin for PagoPA (pagopa.it/it/lavora-con-noi/)."""

import re
import sys
from typing import List

from radar.models import CompanyTarget, RawJob
from radar.scrapers.base import BaseHtmlScraper


class PagoPAScraper(BaseHtmlScraper):
    """Scraper for PagoPA S.p.A. careers page."""

    scraper_id = "pagopa"
    name = "PagoPA Careers"
    default_url = "https://www.pagopa.it/it/lavora-con-noi/"

    def scrape(self, target: CompanyTarget) -> List[RawJob]:
        url = target.extra.get("url") or self.default_url
        jobs: List[RawJob] = []

        try:
            html_content = self.fetch_html(url)
        except Exception as e:
            print(f"[-] Error fetching PagoPA careers page ({url}): {e}", file=sys.stderr)
            return jobs

        open_section = self.extract_section(
            html_content,
            start_marker="Posizioni aperte",
            end_marker="Posizioni chiuse",
        )
        if not open_section:
            # Fallback if markers differ slightly
            open_section = html_content

        entry_pattern = re.compile(
            r'<a\s+href="([^"]+)"[^>]*>\s*<article\s+class="job-entry">(.*?)</article>\s*</a>',
            re.DOTALL,
        )

        matches = entry_pattern.findall(open_section)
        for href, inner in matches:
            # Extract clean title (remove badge spans like NEW or STILL ACTIVE)
            title_match = re.search(
                r'<h3[^>]*class="[^"]*job-entry__title[^"]*"[^>]*>(.*?)</h3>',
                inner,
                re.DOTALL,
            )
            if not title_match:
                continue

            raw_title = title_match.group(1)
            raw_title = re.sub(r"<span>.*?</span>", "", raw_title, flags=re.DOTALL)
            title = self.clean_text(raw_title)
            if not title:
                continue

            date_match = re.search(r"Data di apertura:\s*([\d-]+)", inner)
            posted_date = date_match.group(1) if date_match else None

            full_url = f"https://www.pagopa.it{href}" if href.startswith("/") else href
            job_slug = href.strip("/").split("/")[-1]
            job_id = f"pagopa_{job_slug}" if job_slug else f"pagopa_{len(jobs)}"

            # PagoPA standard location: all positions offer 100% smart working / remote Italy
            location = "Italy (Remote / Smart Working)"

            # Attempt to fetch rich job description from subpage
            content = f"{title}\nSede: {location}\nPagoPA S.p.A.\n"
            try:
                subpage_html = self.fetch_html(full_url, timeout=10)
                main_section = self.extract_section(
                    subpage_html,
                    start_marker="<main",
                    end_marker="</main>",
                )
                if main_section:
                    cleaned_body = self.clean_text(main_section)
                    content = f"{title}\n{cleaned_body[:4000]}"
            except Exception:
                # Subpage fetch is best-effort
                pass

            jobs.append(
                RawJob(
                    id=job_id,
                    company_id=target.id,
                    title=title,
                    location=location,
                    url=full_url,
                    content=content,
                    posted_date=posted_date,
                )
            )

        return jobs
