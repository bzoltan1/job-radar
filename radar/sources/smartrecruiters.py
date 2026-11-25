"""SmartRecruiters ATS source plugin."""

from typing import List

from radar.http import http_get_json
from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


class SmartRecruitersSource(BaseSource):
    ats_name = "smartrecruiters"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        board_id = target.board or target.id
        base_url = f"https://api.smartrecruiters.com/v1/companies/{board_id}/postings"
        headers = {"Accept": "application/json"}
        jobs = []
        limit = 100
        offset = 0
        max_pages = 100  # safety stop (10k postings)

        for _ in range(max_pages):
            data = http_get_json(f"{base_url}?limit={limit}&offset={offset}", headers=headers)
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
        return jobs
