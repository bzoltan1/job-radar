"""Greenhouse ATS source plugin."""

import json
import sys
import urllib.request
from typing import List

from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


def build_greenhouse_location(item: dict) -> str:
    loc_name = (item.get("location") or {}).get("name", "").strip()
    offices = [o.get("name", "").strip() for o in (item.get("offices") or []) if o and o.get("name")]
    meta_locs = []
    for m in (item.get("metadata") or []):
        if m and "location" in (m.get("name") or "").lower():
            val = m.get("value")
            if isinstance(val, list):
                meta_locs.extend([str(v).strip() for v in val if v])
            elif val:
                meta_locs.append(str(val).strip())

    all_places = []
    for p in offices + meta_locs:
        if p and p not in all_places and p.lower() != loc_name.lower():
            all_places.append(p)

    if all_places:
        if loc_name:
            return f"{loc_name} ({'; '.join(all_places)})"
        else:
            return "; ".join(all_places)
    return loc_name


class GreenhouseSource(BaseSource):
    ats_name = "greenhouse"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        board_id = target.board or target.id
        url = f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs?content=true"
        req = urllib.request.Request(url, headers={"User-Agent": "JobRadar/2.0"})
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                jobs = []
                for item in data.get("jobs", []):
                    loc = build_greenhouse_location(item)
                    jobs.append(
                        RawJob(
                            id=f"gh_{board_id}_{item['id']}",
                            company_id=target.id,
                            title=item.get("title", ""),
                            location=loc,
                            url=item.get("absolute_url", ""),
                            content=item.get("content", ""),
                            posted_date=parse_job_date(item.get("updated_at")),
                            metadata={"raw": item.get("metadata", [])},
                        )
                    )
                return jobs
        except Exception as e:
            print(f"[-] Error fetching Greenhouse ({board_id}): {e}", file=sys.stderr)
            return []
