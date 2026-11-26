"""Workday ATS source plugin."""

import ssl
from typing import List

from radar.http import http_get_json
from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource


class WorkdaySource(BaseSource):
    ats_name = "workday"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        tenant = target.board or target.id
        site = target.site or "jobs"
        sub_domain = target.sub_domain or "wd5"
        base_host = "myworkdayjobs.com"

        raw_search = target.search_text or target.extra.get("search_text", "")
        if isinstance(raw_search, list):
            queries = [q.strip() for q in raw_search if q.strip()]
        elif " OR " in raw_search:
            queries = [q.strip() for q in raw_search.split(" OR ") if q.strip()]
        elif raw_search:
            queries = [raw_search.strip()]
        else:
            queries = [""]

        url = f"https://{tenant}.{sub_domain}.{base_host}/wday/cxs/{tenant}/{site}/jobs"
        headers = {
            "Accept": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
        }
        ssl_ctx = ssl.create_default_context()
        try:
            ssl_ctx.set_ciphers("ECDHE+AESGCM:ECDHE+CHACHA20:DHE+AESGCM:DHE+CHACHA20")
        except Exception:
            pass

        jobs_by_id = {}
        limit = 20  # Workday rejects larger pages
        max_pages = 100  # safety stop (2000 postings)

        for q in queries:
            offset = 0
            total = 0
            for _ in range(max_pages):
                # A failure on any page raises: a partial board would deactivate the rest of its jobs.
                data = http_get_json(
                    url,
                    json_body={"appliedFacets": {}, "limit": limit, "offset": offset, "searchText": q},
                    headers=headers,
                    context=ssl_ctx,
                    retry_429=True,
                )
                postings = data.get("jobPostings", [])
                if not postings:
                    break
                for item in postings:
                    ext_path = item.get("externalPath", "")
                    title = item.get("title", "")
                    if not title or not ext_path:
                        continue

                    loc = item.get("locationsText", "")
                    remote_type = item.get("remoteType", "")
                    path_loc = ext_path.split("/job/")[1].split("/")[0] if "/job/" in ext_path else ""
                    combined_loc = f"{loc} - {path_loc}" if path_loc and path_loc != loc else loc
                    full_loc = f"{combined_loc} ({remote_type})" if remote_type else combined_loc
                    job_id = ext_path.split("_")[-1] if "_" in ext_path else ext_path
                    raw_id = f"wd_{target.id}_{job_id}"

                    if raw_id not in jobs_by_id:
                        jobs_by_id[raw_id] = RawJob(
                            id=raw_id,
                            company_id=target.id,
                            title=title,
                            location=full_loc,
                            url=f"https://{tenant}.{sub_domain}.{base_host}/en-US/{site}{ext_path}",
                            content="",
                        )
                offset += limit
                total = max(total, data.get("total", 0))  # Workday may report total on the first page only
                if offset >= total:
                    break
        return list(jobs_by_id.values())
