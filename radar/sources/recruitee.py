"""Recruitee ATS source plugin."""

from typing import List

from radar.http import http_get_json
from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


class RecruiteeSource(BaseSource):
    ats_name = "recruitee"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        company = target.board or target.id
        data = http_get_json(f"https://{company}.recruitee.com/api/offers/")
        jobs = []
        for item in data.get("offers", []):
            jid = str(item.get("id"))
            loc_parts = [
                p for p in [item.get("location") or "", item.get("city") or "", item.get("country") or "",
                            "Remote" if item.get("remote") else ""] if p
            ]
            jobs.append(
                RawJob(
                    id=f"recruitee_{company}_{jid}",
                    company_id=target.id,
                    title=item.get("title", ""),
                    location=", ".join(dict.fromkeys(loc_parts)),
                    url=item.get("careers_url") or f"https://{company}.recruitee.com/o/{item.get('slug', jid)}",
                    content=item.get("description", "") or "",
                    posted_date=parse_job_date(item.get("created_at")),
                )
            )
        return jobs
