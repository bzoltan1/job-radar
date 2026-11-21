"""Lever ATS source plugin."""

import json
import sys
import urllib.error
import urllib.request
from typing import List

from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


class LeverSource(BaseSource):
    ats_name = "lever"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        board_id = target.board or target.id
        hosts = ["api.lever.co", "api.eu.lever.co"]
        if target.site == "eu" or target.sub_domain == "eu":
            hosts = ["api.eu.lever.co", "api.lever.co"]

        data = None
        for host in hosts:
            url = f"https://{host}/v0/postings/{board_id}?mode=json"
            req = urllib.request.Request(url, headers={"User-Agent": "JobRadar/2.0"})
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    break
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    continue
                print(f"[-] Error fetching Lever ({board_id}) on {host}: {e}", file=sys.stderr)
                break
            except Exception as e:
                print(f"[-] Error fetching Lever ({board_id}) on {host}: {e}", file=sys.stderr)
                break

        if not data:
            return []

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
