"""SmartRecruiters ATS source plugin."""

import json
import sys
import urllib.request
from typing import List

from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


class SmartRecruitersSource(BaseSource):
    ats_name = "smartrecruiters"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        board_id = target.board or target.id
        base_url = f"https://api.smartrecruiters.com/v1/companies/{board_id}/postings"
        headers = {"User-Agent": "JobRadar/2.0", "Accept": "application/json"}
        jobs = []
        limit = 100
        offset = 0
        max_pages = 5

        for _ in range(max_pages):
            url = f"{base_url}?limit={limit}&offset={offset}"
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    postings = data.get("content", [])
                    if not postings:
                        break
                    for item in postings:
                        loc_obj = item.get("location") or {}
                        full_loc = loc_obj.get("fullLocation") or f"{loc_obj.get('city', '')}, {loc_obj.get('country', '')}"
                        if loc_obj.get("remote"):
                            full_loc = f"{full_loc} (Remote)"
                        comp_id = (item.get("company") or {}).get("identifier") or board_id
                        job_id = item.get("id", "")

                        jobs.append(
                            RawJob(
                                id=f"sr_{board_id}_{job_id}",
                                company_id=target.id,
                                title=item.get("name", ""),
                                location=full_loc,
                                url=f"https://jobs.smartrecruiters.com/{comp_id}/{job_id}",
                                content="",
                                posted_date=parse_job_date(item.get("releasedDate")),
                            )
                        )
                    offset += limit
                    if offset >= data.get("totalFound", 0):
                        break
            except Exception as e:
                print(f"[-] Error fetching SmartRecruiters ({board_id}): {e}", file=sys.stderr)
                break
        return jobs
