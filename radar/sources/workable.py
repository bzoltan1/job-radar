"""Workable ATS source plugin."""

import re
from concurrent.futures import ThreadPoolExecutor
from typing import List

from radar.http import FetchError, http_get_json
from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date


def _location_names(locations) -> List[str]:
    names = []
    for loc in locations:
        c, city = loc.get("country", ""), loc.get("city", "")
        if c or city:
            names.append(f"{city}, {c}".strip(", "))
    return names


class WorkableSource(BaseSource):
    ats_name = "workable"

    def _description(self, account_slug: str, shortcode: str) -> str:
        """Best-effort job text: a failed detail request only costs this job its description."""
        try:
            det = http_get_json(f"https://apply.workable.com/api/v2/accounts/{account_slug}/jobs/{shortcode}", timeout=8)
        except FetchError:
            return ""
        text = re.sub(r"<[^>]+>", " ", f"{det.get('description', '')} {det.get('requirements', '')}")
        return " ".join(text.split())

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        account_slug = target.board or target.id
        data = http_get_json(
            f"https://apply.workable.com/api/v3/accounts/{account_slug}/jobs", json_body={}, timeout=15
        )
        items = data.get("results", [])
        shortcodes = [item.get("shortcode") or str(item.get("id")) for item in items]
        with ThreadPoolExecutor(max_workers=8) as pool:  # one detail request per job, so overlap them
            contents = list(pool.map(lambda sc: self._description(account_slug, sc), shortcodes))

        jobs = []
        for item, shortcode, content in zip(items, shortcodes, contents):
            loc_list = _location_names(item.get("locations") or [])
            if not loc_list and item.get("location"):
                loc_list = _location_names([item["location"]])

            is_remote = bool(item.get("remote") or item.get("workplace") == "remote")
            if is_remote and loc_list:
                full_loc = f"Remote ({'; '.join(loc_list)})"
            elif is_remote:
                full_loc = "Remote"
            else:
                full_loc = "; ".join(loc_list) if loc_list else "On-site"

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
