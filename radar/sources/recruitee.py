"""Recruitee ATS source plugin."""

import json
import sys
import urllib.request
from typing import List

from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


class RecruiteeSource(BaseSource):
    ats_name = "recruitee"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        company = target.board or target.id
        url = f"https://{company}.recruitee.com/api/offers/"
        headers = {"User-Agent": "JobRadar/2.0"}
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                offers = data.get("offers", [])
                jobs = []
                for item in offers:
                    jid = str(item.get("id"))
                    loc = item.get("location") or ""
                    city = item.get("city") or ""
                    country = item.get("country") or ""
                    remote = "Remote" if item.get("remote") else ""
                    loc_parts = [p for p in [loc, city, country, remote] if p]
                    full_loc = ", ".join(dict.fromkeys(loc_parts))
                    jobs.append(
                        RawJob(
                            id=f"recruitee_{company}_{jid}",
                            company_id=target.id,
                            title=item.get("title", ""),
                            location=full_loc,
                            url=item.get("careers_url") or f"https://{company}.recruitee.com/o/{item.get('slug', jid)}",
                            content=item.get("description", "") or "",
                            posted_date=parse_job_date(item.get("created_at")),
                        )
                    )
                return jobs
        except Exception as e:
            print(f"[-] Error fetching Recruitee ({company}): {e}", file=sys.stderr)
            return []
