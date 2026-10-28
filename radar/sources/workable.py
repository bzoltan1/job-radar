"""Workable ATS source plugin."""

import json
import re
import sys
import urllib.request
from typing import List

from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


class WorkableSource(BaseSource):
    ats_name = "workable"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        account_slug = target.board or target.id
        url = f"https://apply.workable.com/api/v3/accounts/{account_slug}/jobs"
        headers = {"Content-Type": "application/json", "User-Agent": "JobRadar/2.0"}
        jobs = []
        try:
            req = urllib.request.Request(url, data=b"{}", headers=headers)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                for item in data.get("results", []):
                    shortcode = item.get("shortcode") or str(item.get("id"))
                    loc_list = []
                    for loc in (item.get("locations") or []):
                        c = loc.get("country", "")
                        city = loc.get("city", "")
                        if c or city:
                            loc_list.append(f"{city}, {c}".strip(", "))
                    if not loc_list and item.get("location"):
                        c = item["location"].get("country", "")
                        city = item["location"].get("city", "")
                        if c or city:
                            loc_list.append(f"{city}, {c}".strip(", "))

                    is_remote = bool(item.get("remote") or item.get("workplace") == "remote")
                    if is_remote and loc_list:
                        full_loc = f"Remote ({'; '.join(loc_list)})"
                    elif is_remote:
                        full_loc = "Remote"
                    else:
                        full_loc = "; ".join(loc_list) if loc_list else "On-site"

                    content = ""
                    try:
                        det_url = f"https://apply.workable.com/api/v2/accounts/{account_slug}/jobs/{shortcode}"
                        det_req = urllib.request.Request(det_url, headers={"User-Agent": "JobRadar/2.0"})
                        with urllib.request.urlopen(det_req, timeout=8) as det_resp:
                            det_data = json.loads(det_resp.read().decode("utf-8"))
                            desc = det_data.get("description", "")
                            reqs = det_data.get("requirements", "")
                            content = re.sub(r"<[^>]+>", " ", f"{desc} {reqs}")
                            content = " ".join(content.split())
                    except Exception:
                        pass

                    jobs.append(
                        RawJob(
                            id=f"workable_{account_slug}_{shortcode}",
                            company_id=target.id,
                            title=item.get("title", ""),
                            location=full_loc,
                            url=f"https://apply.workable.com/{account_slug}/j/{shortcode}/",
                            content=content,
                            posted_date=parse_job_date(item.get("published")),
                        )
                    )
                return jobs
        except Exception as e:
            print(f"[-] Error fetching Workable ({account_slug}): {e}", file=sys.stderr)
            return []
