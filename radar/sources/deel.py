"""Deel ATS source plugin."""

import re
import sys
import urllib.request
from typing import List

from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


class DeelSource(BaseSource):
    ats_name = "deel"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        company = target.board or target.id
        url = f"https://jobs.deel.com/{company}"
        headers = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) JobRadar/2.0"}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                html = resp.read().decode("utf-8", errors="ignore")
            raw = html.replace('\\"', '"')
            matches = re.findall(
                r'"ashby_id":"([^"]+)","job_id":"([^"]+)","title":"([^"]+)".*?'
                r'"location_name":"([^"]+)".*?"ashby_published_date":"([^"]+)".*?'
                r'"external_link":"([^"]+)"',
                raw,
            )
            jobs = []
            for ashby_id, job_id, title, loc, pub_date, link in matches:
                jobs.append(
                    RawJob(
                        id=f"deel_{ashby_id}",
                        company_id=target.id,
                        title=title,
                        location=loc,
                        url=link,
                        content="",
                        posted_date=parse_job_date(pub_date) if pub_date else None,
                    )
                )
            return jobs
        except Exception as e:
            print(f"[-] Error fetching Deel ({company}): {e}", file=sys.stderr)
            return []
