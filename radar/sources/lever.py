"""Lever ATS source plugin."""

from typing import List

from radar.http import FetchError, http_get_json
from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


class LeverSource(BaseSource):
    ats_name = "lever"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        board_id = target.board or target.id
        hosts = ["api.lever.co", "api.eu.lever.co"]
        if target.site == "eu" or target.sub_domain == "eu":
            hosts = ["api.eu.lever.co", "api.lever.co"]

        # A board lives on one region only: 404 means "try the other host".
        for host in hosts:
            try:
                data = http_get_json(f"https://{host}/v0/postings/{board_id}?mode=json")
                break
            except FetchError as e:
                if e.status != 404:
                    raise
        else:
            raise FetchError(f"Lever board '{board_id}' not found on {' or '.join(hosts)}", status=404)

        jobs = []
        for item in data:
            loc = (item.get("categories") or {}).get("location", "")
            workplace = (item.get("categories") or {}).get("workplaceType", "")
            full_loc = f"{loc} ({workplace})" if workplace else loc

            desc = item.get("descriptionPlain", "") or ""
            add = item.get("additionalPlain", "") or ""
            lists_text = " ".join(
                f"{li.get('text', '')} {li.get('content', '')}"
                for li in (item.get("lists") or [])
            )
            full_content = f"{desc}\n{add}\n{lists_text}"

            jobs.append(
                RawJob(
                    id=f"lever_{board_id}_{item['id']}",
                    company_id=target.id,
                    title=item.get("text", ""),
                    location=full_loc,
                    url=item.get("hostedUrl", ""),
                    content=full_content,
                    posted_date=parse_job_date(item.get("createdAt")),
                )
            )
        return jobs
