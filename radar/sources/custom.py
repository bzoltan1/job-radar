"""Custom career site source plugins for Amazon, Dynatrace, Proxmox, and Sidero."""

import html
import json
import re
import sys
import urllib.request
from typing import Dict, List

from radar.config import get_location_config
from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource, parse_job_date

AMAZON_COUNTRY_CODES: Dict[str, str] = {
    "italy": "ITA",
    "germany": "DEU",
    "france": "FRA",
    "spain": "ESP",
    "united kingdom": "GBR",
    "uk": "GBR",
    "austria": "AUT",
    "ireland": "IRL",
    "poland": "POL",
    "netherlands": "NLD",
    "canada": "CAN",
    "united states": "USA",
    "us": "USA",
}


class AmazonSource(BaseSource):
    ats_name = "amazon"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        loc_cfg = get_location_config()
        primary_country = loc_cfg.get("primary_country", "Italy").lower()
        country_code = AMAZON_COUNTRY_CODES.get(primary_country, "ITA")

        queries = [
            "https://www.amazon.jobs/en/search.json?base_query=bottlerocket&result_limit=50",
            "https://www.amazon.jobs/en/search.json?base_query=amazon+linux&result_limit=50",
            "https://www.amazon.jobs/en/search.json?base_query=firecracker&result_limit=50",
            f"https://www.amazon.jobs/en/search.json?country={country_code}&category[]=software-development&result_limit=50",
            f"https://www.amazon.jobs/en/search.json?country={country_code}&base_query=linux&result_limit=50",
            f"https://www.amazon.jobs/en/search.json?country={country_code}&base_query=systems&result_limit=50",
            "https://www.amazon.jobs/en/search.json?base_query=linux+kernel&result_limit=50",
        ]
        headers = {"User-Agent": "JobRadar/2.0"}
        jobs_by_id = {}
        for q_url in queries:
            req = urllib.request.Request(q_url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=15) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
                    for item in data.get("jobs", []):
                        icims_id = item.get("id_icims")
                        if not icims_id:
                            continue
                        jid = f"amazon_{icims_id}"
                        if jid in jobs_by_id:
                            continue
                        loc = item.get("location", "")
                        norm_loc = item.get("normalized_location", "")
                        country = item.get("country_code", "")
                        if country == country_code or primary_country in norm_loc.lower():
                            full_loc = f"{loc}, {primary_country.capitalize()}"
                        else:
                            full_loc = f"{loc} ({norm_loc})" if norm_loc and norm_loc != loc else loc

                        desc = item.get("description", "") or ""
                        basic = item.get("basic_qualifications", "") or ""
                        pref = item.get("preferred_qualifications", "") or ""
                        content = f"{desc}\n{basic}\n{pref}"

                        jobs_by_id[jid] = RawJob(
                            id=jid,
                            company_id=target.id,
                            title=item.get("title", ""),
                            location=full_loc,
                            url=f"https://www.amazon.jobs{item.get('job_path', '')}",
                            content=content,
                            posted_date=parse_job_date(item.get("posted_date")),
                        )
            except Exception as e:
                print(f"[-] Error querying Amazon Jobs ({q_url}): {e}", file=sys.stderr)

        return list(jobs_by_id.values())


class DynatraceSource(BaseSource):
    ats_name = "dynatrace"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        url_base = "https://apply.careers.dynatrace.com/search/"
        headers = {"User-Agent": "JobRadar/2.0"}
        jobs = []
        startrow = 0
        per_page = 25
        max_pages = 5

        for _ in range(max_pages):
            url = f"{url_base}?q=&startrow={startrow}"
            req = urllib.request.Request(url, headers=headers)
            try:
                with urllib.request.urlopen(req, timeout=20) as resp:
                    html_text = resp.read().decode("utf-8")
                tiles = re.findall(
                    r'<li class="job-tile job-id-(\d+)[^"]*" data-url="([^"]+)".*?'
                    r'<a class="jobTitle-link[^"]*"[^>]*>(.*?)</a>.*?'
                    r'<div id="job-\d+-desktop-section-location-value">(.*?)</div>',
                    html_text,
                    re.DOTALL,
                )
                if not tiles:
                    break
                for jid, url_path, title, loc in tiles:
                    t = html.unescape(title).strip()
                    l = html.unescape(loc).strip()
                    jobs.append(
                        RawJob(
                            id=f"dynatrace_{jid}",
                            company_id=target.id,
                            title=t,
                            location=l,
                            url=f"https://apply.careers.dynatrace.com{url_path}",
                            content="",
                        )
                    )
                startrow += per_page
            except Exception as e:
                print(f"[-] Error fetching Dynatrace: {e}", file=sys.stderr)
                break
        return jobs


class SideroSource(BaseSource):
    ats_name = "sidero"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        url = "https://www.siderolabs.com/careers/"
        headers = {"User-Agent": "JobRadar/2.0"}
        req = urllib.request.Request(url, headers=headers)
        jobs = []
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                page = resp.read().decode("utf-8")
            cards = re.findall(
                r'href="(/careers/[^"/]+/)"[^>]*class="[^"]*rd-vacancy-card[^"]*"[^>]*>(.*?)</a>',
                page,
                re.DOTALL,
            )
            for path, inner in cards:
                title_m = re.search(r'<h3[^>]*>(.*?)</h3>', inner)
                title = html.unescape(title_m.group(1)).strip() if title_m else ""
                meta_tags = re.findall(r'<span class="rd-vacancy-card__tag">(.*?)</span>', inner)
                loc = html.unescape(meta_tags[1]).strip() if len(meta_tags) > 1 else (meta_tags[0].strip() if meta_tags else "")
                job_url = f"https://www.siderolabs.com{path}"
                slug = path.strip("/").split("/")[-1]

                content = ""
                try:
                    sub_req = urllib.request.Request(job_url, headers=headers)
                    with urllib.request.urlopen(sub_req, timeout=10) as sr:
                        sub_page = sr.read().decode("utf-8")
                        clean = re.sub(r"<style[^>]*>.*?</style>", "", sub_page, flags=re.DOTALL)
                        clean = re.sub(r"<script[^>]*>.*?</script>", "", clean, flags=re.DOTALL)
                        clean = re.sub(r"<[^>]+>", " ", clean)
                        content = " ".join(clean.split())
                except Exception:
                    pass

                jobs.append(
                    RawJob(
                        id=f"sidero_{slug}",
                        company_id=target.id,
                        title=title,
                        location=loc,
                        url=job_url,
                        content=content,
                    )
                )
        except Exception as e:
            print(f"[-] Error fetching Sidero Labs: {e}", file=sys.stderr)

        return jobs


class ProxmoxSource(BaseSource):
    ats_name = "proxmox"

    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        url = "https://www.proxmox.com/en/about/careers"
        headers = {"User-Agent": "JobRadar/2.0"}
        req = urllib.request.Request(url, headers=headers)
        jobs = []
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                page = resp.read().decode("utf-8")

            sections = re.split(r"(<h2[^>]*>.*?</h2>)", page)
            for i in range(1, len(sections), 2):
                h2_tag = sections[i]
                chunk = sections[i + 1] if i + 1 < len(sections) else ""
                title = re.sub(r"<[^>]+>", "", h2_tag).strip()
                if not any(k in title for k in ["(m/f/d)", "(Canada)", "Developer", "Engineer", "Manager", "Specialist", "Representative"]):
                    continue

                loc = "Vienna, Austria"
                if "Canada" in title or "Kingston" in chunk[:500]:
                    loc = "Kingston, Ontario, Canada"
                elif "Remote" in chunk[:500]:
                    loc = "Remote / Vienna, Austria"

                clean = re.sub(r"<style[^>]*>.*?</style>", "", chunk, flags=re.DOTALL)
                clean = re.sub(r"<script[^>]*>.*?</script>", "", clean, flags=re.DOTALL)
                clean = re.sub(r"<[^>]+>", " ", clean)
                clean_content = " ".join(clean.split())

                slug = re.sub(r"[^a-zA-Z0-9]+", "-", title.lower()).strip("-")
                jobs.append(
                    RawJob(
                        id=f"proxmox_{slug}",
                        company_id=target.id,
                        title=title,
                        location=loc,
                        url="https://www.proxmox.com/en/about/careers",
                        content=f"{title}\n{clean_content[:2000]}",
                    )
                )
        except Exception as e:
            print(f"[-] Error fetching Proxmox: {e}", file=sys.stderr)

        return jobs
