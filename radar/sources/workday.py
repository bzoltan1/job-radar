"""Workday ATS source plugin."""

import json
import sys
import urllib.request
from typing import List

from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource


class WorkdaySource(BaseSource):
    ats_name = "workday"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        tenant = target.board or target.id
        site = target.site or "jobs"
        sub_domain = target.sub_domain or "wd5"
        base_host = "myworkdayjobs.com"

        url = f"https://{tenant}.{sub_domain}.{base_host}/wday/cxs/{tenant}/{site}/jobs"
        headers = {"Content-Type": "application/json", "User-Agent": "JobRadar/2.0"}
        jobs = []
        limit = 20
        offset = 0
        max_pages = 5

        for _ in range(max_pages):
            payload = json.dumps({
                "appliedFacets": {},
                "limit": limit,
                "offset": offset,
                "searchText": "",
            }).encode("utf-8")
            req = urllib.request.Request(url, data=payload, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    postings = data.get("jobPostings", [])
                    if not postings:
                        break
                    for item in postings:
                        loc = item.get("locationsText", "")
                        remote_type = item.get("remoteType", "")
                        ext_path = item.get("externalPath", "")
                        path_loc = ext_path.split("/job/")[1].split("/")[0] if "/job/" in ext_path else ""
                        combined_loc = f"{loc} - {path_loc}" if path_loc and path_loc != loc else loc
                        full_loc = f"{combined_loc} ({remote_type})" if remote_type else combined_loc
                        job_id = ext_path.split("_")[-1] if "_" in ext_path else ext_path

                        jobs.append(
                            RawJob(
                                id=f"wd_{tenant}_{job_id}",
                                company_id=target.id,
                                title=item.get("title", ""),
                                location=full_loc,
                                url=f"https://{tenant}.{sub_domain}.{base_host}/en-US/{site}{ext_path}",
                                content="",
                            )
                        )
                    offset += limit
                    if offset >= data.get("total", 0):
                        break
            except Exception as e:
                print(f"[-] Error fetching Workday ({tenant}): {e}", file=sys.stderr)
                break
        return jobs
