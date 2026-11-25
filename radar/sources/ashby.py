"""Ashby ATS source plugin."""

from typing import List

from radar.http import http_get_json
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
              compensationTierSummary
            }
          }
        }
        """
        data = http_get_json(
            url,
            json_body={
                "operationName": "ApiJobBoardWithTeams",
                "variables": {"organizationHostedJobsPageName": board_id},
                "query": query,
            },
        )
        job_postings = ((data.get("data") or {}).get("jobBoard") or {}).get("jobPostings", [])
        jobs = []
        for item in job_postings:
            loc = item.get("locationName", "")
            sec = [s.get("locationName", "") for s in item.get("secondaryLocations", [])]
            comp = item.get("compensationTierSummary") or ""
            jobs.append(
                RawJob(
                    id=f"ashby_{board_id}_{item['id']}",
                    company_id=target.id,
                    title=item.get("title", ""),
                    location="; ".join(filter(None, [loc] + sec)),
                    url=f"https://jobs.ashbyhq.com/{board_id}/{item['id']}",
                    content=f"Compensation: {comp}" if comp else "",
                )
            )
        return jobs
