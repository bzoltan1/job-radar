"""Deel ATS source plugin."""

import re
from typing import List

from radar.http import FetchError, http_get_text
from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


class DeelSource(BaseSource):
    ats_name = "deel"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        company = target.board or target.id
        html = http_get_text(
            f"https://jobs.deel.com/{company}",
            headers={"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) JobRadar/2.0"},
        )
        raw = html.replace('\\"', '"')
        matches = re.findall(
            r'"ashby_id":"([^"]+)","job_id":"([^"]+)","title":"([^"]+)".*?'
            r'"location_name":"([^"]+)".*?"ashby_published_date":"([^"]+)".*?'
            r'"external_link":"([^"]+)"',
            raw,
        )
        if not matches:
            # shortcut: zero parsed postings is treated as a layout change, not "no openings"
            raise FetchError(f"Deel ({company}): no postings found in page; layout changed or wrong board?")
        return [
            RawJob(
                id=f"deel_{ashby_id}",
                company_id=target.id,
                title=title,
                location=loc,
                url=link,
                content="",
                posted_date=parse_job_date(pub_date) if pub_date else None,
            )
            for ashby_id, job_id, title, loc, pub_date, link in matches
        ]
