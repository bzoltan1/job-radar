"""Ashby ATS source plugin."""

import json
import sys
import urllib.request
from typing import List

from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource


class AshbySource(BaseSource):
    ats_name = "ashby"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        board_id = target.board or target.id
        url = "https://jobs.ashbyhq.com/api/non-user-graphql?op=ApiJobBoardWithTeams"
        query = """
        query ApiJobBoardWithTeams($organizationHostedJobsPageName: String!) {
          jobBoard: jobBoardWithTeams(organizationHostedJobsPageName: $organizationHostedJobsPageName) {
            jobPostings {
              id
              title
              locationName
              secondaryLocations { locationName }
              employmentType
            }
          }
        }
        """
        payload = json.dumps({
            "operationName": "ApiJobBoardWithTeams",
            "variables": {"organizationHostedJobsPageName": board_id},
            "query": query,
        }).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=payload,
            headers={"Content-Type": "application/json", "User-Agent": "JobRadar/2.0"},
        )
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                job_postings = (data.get("data", {}).get("jobBoard") or {}).get("jobPostings", [])
                jobs = []
                for item in job_postings:
                    loc = item.get("locationName", "")
                    sec = [s.get("locationName", "") for s in item.get("secondaryLocations", [])]
                    full_loc = "; ".join(filter(None, [loc] + sec))
                    jobs.append(
                        RawJob(
                            id=f"ashby_{board_id}_{item['id']}",
                            company_id=target.id,
                            title=item.get("title", ""),
                            location=full_loc,
                            url=f"https://jobs.ashbyhq.com/{board_id}/{item['id']}",
                            content="",
                        )
                    )
                return jobs
        except Exception as e:
            print(f"[-] Error fetching Ashby ({board_id}): {e}", file=sys.stderr)
            return []
