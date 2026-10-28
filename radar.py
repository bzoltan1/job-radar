#!/usr/bin/env python3
"""Job Radar: Intelligent Systems & Platform Engineering Job Scraper & Scorer."""

import argparse
import datetime
import html
import json
import os
import re
import sqlite3
import sys
import urllib.request
import urllib.error
import yaml

from matcher import evaluate_profile_match, compute_freshness, generate_rss_feed

DB_PATH = os.path.join(os.path.dirname(__file__), "jobs.db")
TARGETS_FILE = os.path.join(os.path.dirname(__file__), "targets.yaml")
INTEL_FILE = os.path.join(os.path.dirname(__file__), "company_intel.yaml")
FEED_PATH = os.path.join(os.path.dirname(__file__), "feed.xml")

# Regex heuristics
TITLE_EXCLUDE_RE = re.compile(
    r"\b("
    r"sales|pre-?sales|solutions?\s+engineer(?:ing)?|solutions?\s+architect(?:ure)?|"
    r"customer\s+success|customer\s+engineer(?:ing)?|technical\s+account\s+manager|\btam\b|"
    r"account\s+executive|\bae\b|account\s+manager|\bam\b|business\s+development|\bbdr\b|\bsdr\b|"
    r"gtm\b|go-to-market|revops\b|revenue\s+operations|renewals?|"
    r"commercial|partner\s+engineer|partner\s+solutions|partner\s+architect|partner\s+manager|alliances?|"
    r"marketing|recruiter|recruiting|talent|legal|counsel|attorney|"
    r"accountant|accounting|payroll|people\s+partner|hr\b|copywriter|content\s+writer|office\s+manager|"
    r"frontend|front-end|react|angular|ui/ux|product\s+designer|graphic\s+designer|finance\s+director|"
    r"deal\s+desk|sales\s+ops|technical\s+enablement|curriculum\s+developer|"
    r"interns?|internships?|students?|co-ops?|working\s+students?|apprentices?|loss\s+prevention|"
    r"construction|vendor\s+manager|retail|facility\s+manager|warehouse"
    r")\b",
    re.IGNORECASE,
)

ENGINEERING_TITLE_RE = re.compile(
    r"\b(software|developer|engineer|architect|sre|devops|technician)\b",
    re.IGNORECASE,
)

SYSTEMS_TITLE_RE = re.compile(
    r"\b(systems|platform|linux|kernel|ebpf|bpf|infrastructure|infra|sre|site reliability|"
    r"distributed|runtime|virtualization|container|core os|low-level|storage|networking|"
    r"cloud platform|kubernetes|cloud infrastructure)\b",
    re.IGNORECASE,
)

TECH_STACK_RE = re.compile(
    r"\b(golang|go\b|c\b|c\+\+|linux|ebpf|systemd|kernel|kubernetes|docker|perf|syscall|posix)\b",
    re.IGNORECASE,
)

LOCATION_ITALY_RE = re.compile(
    r"\b(italy|italia|milan|milano|rome|roma)\b",
    re.IGNORECASE,
)

LOCATION_EMEA_REMOTE_RE = re.compile(
    r"\b(emea|europe|worldwide|distributed|anywhere|global)\b",
    re.IGNORECASE,
)

LOCATION_DISQUALIFY_RE = re.compile(
    r"\b(us only|united states only|americas only|apac only|canada only|india only|latam only|"
    r"uk only|germany only|france only|singapore only|japan only|australia only)\b",
    re.IGNORECASE,
)

SINGLE_COUNTRY_REMOTE_RE = re.compile(
    r"\bremote[\s-]+(us\b|usa\b|united states|uk\b|united kingdom|ca\b|canada|germany|france|spain|poland|netherlands|austria|sweden|brazil|brasilia|india|singapore|australia|japan)\b",
    re.IGNORECASE,
)

LOCATION_AUSTRIA_RE = re.compile(
    r"\b(austria|vienna|wien|linz|graz)\b",
    re.IGNORECASE,
)

B2B_RE = re.compile(
    r"\b(b2b|contractor only|independent contractor|freelance|vat number|partita iva)\b",
    re.IGNORECASE,
)

EOR_RE = re.compile(
    r"\b(deel|remote\.com|oyster|omnipresent|employee of record|eor|local contract|permanent contract)\b",
    re.IGNORECASE,
)


def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                title TEXT,
                location TEXT,
                is_italy_direct INTEGER,
                is_emea_remote INTEGER,
                score INTEGER,
                url TEXT,
                tags TEXT,
                salary_min INTEGER DEFAULT 0,
                salary_max INTEGER DEFAULT 0,
                salary_currency TEXT DEFAULT '',
                salary_display TEXT DEFAULT '',
                salary_norm_max INTEGER DEFAULT 0,
                profile_match_pct INTEGER DEFAULT 0,
                matched_skills TEXT DEFAULT '',
                pitch_bullets TEXT DEFAULT '',
                first_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                last_seen TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                active INTEGER DEFAULT 1
            )
        """)
        # Schema migration check
        cursor = conn.execute("PRAGMA table_info(jobs)")
        existing_cols = {row["name"] for row in cursor.fetchall()}
        for col, col_def in [
            ("salary_min", "INTEGER DEFAULT 0"),
            ("salary_max", "INTEGER DEFAULT 0"),
            ("salary_currency", "TEXT DEFAULT ''"),
            ("salary_display", "TEXT DEFAULT ''"),
            ("salary_norm_max", "INTEGER DEFAULT 0"),
            ("profile_match_pct", "INTEGER DEFAULT 0"),
            ("matched_skills", "TEXT DEFAULT ''"),
            ("pitch_bullets", "TEXT DEFAULT ''"),
        ]:
            if col not in existing_cols:
                conn.execute(f"ALTER TABLE jobs ADD COLUMN {col} {col_def}")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS fetch_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                company_id TEXT,
                fetched_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                jobs_found INTEGER,
                jobs_matched INTEGER
            )
        """)
    return conn


def load_targets():
    if not os.path.exists(TARGETS_FILE):
        sys.exit(f"Targets file not found: {TARGETS_FILE}")
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("companies", [])


def load_company_intel():
    if not os.path.exists(INTEL_FILE):
        return {}
    with open(INTEL_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("companies", {})


def normalize_to_eur(val, currency):
    rates = {
        "EUR": 1.0,
        "USD": 0.92,
        "GBP": 1.18,
        "CHF": 1.05,
    }
    return int(val * rates.get(currency.upper(), 0.92))


def extract_salary(job_item):
    """Extract compensation from structured metadata or content text."""
    meta = job_item.get("metadata") or []
    for m in meta:
        if m.get("value_type") == "currency_range" and m.get("value"):
            v = m["value"]
            unit = v.get("unit", "USD").upper()
            try:
                vmin = int(float(v.get("min_value", 0)))
                vmax = int(float(v.get("max_value", 0)))
                if vmax > 0:
                    norm = normalize_to_eur(vmax, unit)
                    disp = f"{unit} {vmin//1000}k-{vmax//1000}k" if vmin > 0 else f"{unit} {vmax//1000}k"
                    return vmin, vmax, unit, disp, norm
            except (ValueError, TypeError):
                pass

    content = html.unescape(job_item.get("content", "") or "")
    if not content:
        return 0, 0, "", "", 0

    text = re.sub(r"<[^>]+>", " ", content)

    p1 = re.compile(
        r"([€$£]|EUR|USD|GBP|CHF)\s*([0-9]{2,3}(?:[,\.][0-9]{3})+)\s*(?:-|to|–|and)\s*([€$£]|EUR|USD|GBP|CHF)?\s*([0-9]{2,3}(?:[,\.][0-9]{3})+)",
        re.IGNORECASE,
    )
    p2 = re.compile(
        r"([0-9]{2,3}(?:[,\.][0-9]{3})+)\s*(?:-|to|–|and)\s*([0-9]{2,3}(?:[,\.][0-9]{3})+)\s*([€$£]|EUR|USD|GBP|CHF)",
        re.IGNORECASE,
    )
    p3 = re.compile(
        r"([€$£]|EUR|USD|GBP|CHF)?\s*([0-9]{2,3})\s*k\s*(?:-|to|–|and)\s*([€$£]|EUR|USD|GBP|CHF)?\s*([0-9]{2,3})\s*k",
        re.IGNORECASE,
    )

    matches = []
    for m in p1.finditer(text):
        c1, s1, c2, s2 = m.groups()
        curr = c1 if c1 in ["$", "€", "£", "EUR", "USD", "GBP", "CHF"] else (c2 or "USD")
        curr = {"$": "USD", "€": "EUR", "£": "GBP"}.get(curr, curr.upper())
        v1 = int(re.sub(r"[,.]", "", s1))
        v2 = int(re.sub(r"[,.]", "", s2))
        vmin, vmax = min(v1, v2), max(v1, v2)
        if 25000 <= vmax <= 700000:
            matches.append((vmin, vmax, curr))

    for m in p2.finditer(text):
        s1, s2, curr = m.groups()
        curr = {"$": "USD", "€": "EUR", "£": "GBP"}.get(curr, curr.upper())
        v1 = int(re.sub(r"[,.]", "", s1))
        v2 = int(re.sub(r"[,.]", "", s2))
        vmin, vmax = min(v1, v2), max(v1, v2)
        if 25000 <= vmax <= 700000:
            matches.append((vmin, vmax, curr))

    for m in p3.finditer(text):
        c1, s1, c2, s2 = m.groups()
        curr = c1 or c2 or "USD"
        curr = {"$": "USD", "€": "EUR", "£": "GBP"}.get(curr, curr.upper())
        v1 = int(s1) * 1000
        v2 = int(s2) * 1000
        vmin, vmax = min(v1, v2), max(v1, v2)
        if 25000 <= vmax <= 700000:
            matches.append((vmin, vmax, curr))

    if matches:
        eur_matches = [m for m in matches if m[2] == "EUR"]
        chosen = max(eur_matches, key=lambda x: x[1]) if eur_matches else max(matches, key=lambda x: x[1])
        vmin, vmax, curr = chosen
        norm = normalize_to_eur(vmax, curr)
        disp = f"{curr} {vmin//1000}k-{vmax//1000}k" if vmin != vmax else f"{curr} {vmax//1000}k"
        return vmin, vmax, curr, disp, norm

    return 0, 0, "", "", 0


def parse_job_date(raw_date):
    """Parse various ATS date formats into ISO YYYY-MM-DD HH:MM:SS string."""
    if not raw_date:
        return None
    try:
        if isinstance(raw_date, (int, float)):
            if raw_date > 1e11:  # ms
                raw_date = raw_date / 1000.0
            dt = datetime.datetime.fromtimestamp(raw_date, datetime.timezone.utc)
            return dt.strftime("%Y-%m-%d %H:%M:%S")

        raw_str = str(raw_date).strip()
        if "T" in raw_str:
            clean = raw_str.split(".")[0].split("+")[0].replace("Z", "")
            if len(clean) > 19:
                clean = clean[:19]
            return clean.replace("T", " ")

        for fmt in ("%B %d, %Y", "%b %d, %Y", "%Y-%m-%d"):
            try:
                dt = datetime.datetime.strptime(raw_str, fmt)
                return dt.strftime("%Y-%m-%d %H:%M:%S")
            except ValueError:
                pass
    except Exception:
        pass
    return None


def fetch_greenhouse(board_id):
    url = f"https://boards-api.greenhouse.io/v1/boards/{board_id}/jobs?content=true"
    req = urllib.request.Request(url, headers={"User-Agent": "JobRadar/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            jobs = []
            for item in data.get("jobs", []):
                loc = (item.get("location") or {}).get("name", "")
                jobs.append({
                    "id": f"gh_{board_id}_{item['id']}",
                    "title": item.get("title", ""),
                    "location": loc,
                    "url": item.get("absolute_url", ""),
                    "content": item.get("content", ""),
                    "metadata": item.get("metadata", []),
                    "posted_date": parse_job_date(item.get("updated_at")),
                })
            return jobs
    except Exception as e:
        print(f"[-] Error fetching Greenhouse ({board_id}): {e}", file=sys.stderr)
        return []


def fetch_ashby(board_id):
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
        headers={"Content-Type": "application/json", "User-Agent": "JobRadar/1.0"},
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
                jobs.append({
                    "id": f"ashby_{board_id}_{item['id']}",
                    "title": item.get("title", ""),
                    "location": full_loc,
                    "url": f"https://jobs.ashbyhq.com/{board_id}/{item['id']}",
                    "content": "",
                })
            return jobs
    except Exception as e:
        print(f"[-] Error fetching Ashby ({board_id}): {e}", file=sys.stderr)
        return []


def fetch_lever(board_id):
    url = f"https://api.lever.co/v0/postings/{board_id}?mode=json"
    req = urllib.request.Request(url, headers={"User-Agent": "JobRadar/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
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

                jobs.append({
                    "id": f"lever_{board_id}_{item['id']}",
                    "title": item.get("text", ""),
                    "location": full_loc,
                    "url": item.get("hostedUrl", ""),
                    "content": full_content,
                    "posted_date": parse_job_date(item.get("createdAt")),
                })
            return jobs
    except Exception as e:
        print(f"[-] Error fetching Lever ({board_id}): {e}", file=sys.stderr)
        return []


def fetch_workday(tenant, site, base_host="myworkdayjobs.com", sub_domain="wd5"):
    url = f"https://{tenant}.{sub_domain}.{base_host}/wday/cxs/{tenant}/{site}/jobs"
    headers = {"Content-Type": "application/json", "User-Agent": "JobRadar/1.0"}
    jobs = []
    limit = 20
    offset = 0
    max_pages = 5

    for page in range(max_pages):
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
                    jobs.append({
                        "id": f"wd_{tenant}_{job_id}",
                        "title": item.get("title", ""),
                        "location": full_loc,
                        "url": f"https://{tenant}.{sub_domain}.{base_host}/en-US/{site}{ext_path}",
                        "content": "",
                    })
                offset += limit
                if offset >= data.get("total", 0):
                    break
        except Exception as e:
            print(f"[-] Error fetching Workday ({tenant}): {e}", file=sys.stderr)
            break
    return jobs


def fetch_smartrecruiters(board_id):
    if board_id.lower() == "dynatrace":
        return fetch_dynatrace()

    base_url = f"https://api.smartrecruiters.com/v1/companies/{board_id}/postings"
    headers = {"User-Agent": "JobRadar/1.0", "Accept": "application/json"}
    jobs = []
    limit = 100
    offset = 0
    max_pages = 5

    for _ in range(max_pages):
        url = f"{base_url}?limit={limit}&offset={offset}"
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                postings = data.get("content", [])
                if not postings:
                    break
                for item in postings:
                    loc_obj = item.get("location") or {}
                    full_loc = loc_obj.get("fullLocation") or f"{loc_obj.get('city', '')}, {loc_obj.get('country', '')}"
                    if loc_obj.get("remote"):
                        full_loc = f"{full_loc} (Remote)"
                    comp_id = (item.get("company") or {}).get("identifier") or board_id
                    job_id = item.get("id", "")
                    jobs.append({
                        "id": f"sr_{board_id}_{job_id}",
                        "title": item.get("name", ""),
                        "location": full_loc,
                        "url": f"https://jobs.smartrecruiters.com/{comp_id}/{job_id}",
                        "content": "",
                        "posted_date": parse_job_date(item.get("releasedDate")),
                    })
                offset += limit
                if offset >= data.get("totalFound", 0):
                    break
        except Exception as e:
            print(f"[-] Error fetching SmartRecruiters ({board_id}): {e}", file=sys.stderr)
            break
    return jobs


def fetch_dynatrace():
    url_base = "https://apply.careers.dynatrace.com/search/"
    headers = {"User-Agent": "JobRadar/1.0"}
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
                jobs.append({
                    "id": f"dynatrace_{jid}",
                    "title": t,
                    "location": l,
                    "url": f"https://apply.careers.dynatrace.com{url_path}",
                    "content": "",
                })
            startrow += per_page
        except Exception as e:
            print(f"[-] Error fetching Dynatrace: {e}", file=sys.stderr)
            break
    return jobs


def fetch_amazon(board_id="amazon"):
    queries = [
        "https://www.amazon.jobs/en/search.json?base_query=bottlerocket&result_limit=50",
        "https://www.amazon.jobs/en/search.json?base_query=amazon+linux&result_limit=50",
        "https://www.amazon.jobs/en/search.json?base_query=firecracker&result_limit=50",
        "https://www.amazon.jobs/en/search.json?country=ITA&category[]=software-development&result_limit=50",
        "https://www.amazon.jobs/en/search.json?country=ITA&base_query=linux&result_limit=50",
        "https://www.amazon.jobs/en/search.json?country=ITA&base_query=systems&result_limit=50",
        "https://www.amazon.jobs/en/search.json?base_query=linux+kernel&result_limit=50",
    ]
    headers = {"User-Agent": "JobRadar/1.0"}
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
                    if country == "ITA" or "italy" in norm_loc.lower():
                        full_loc = f"{loc}, Italy"
                    else:
                        full_loc = f"{loc} ({norm_loc})" if norm_loc and norm_loc != loc else loc

                    desc = item.get("description", "") or ""
                    basic = item.get("basic_qualifications", "") or ""
                    pref = item.get("preferred_qualifications", "") or ""
                    content = f"{desc}\n{basic}\n{pref}"

                    jobs_by_id[jid] = {
                        "id": jid,
                        "title": item.get("title", ""),
                        "location": full_loc,
                        "url": f"https://www.amazon.jobs{item.get('job_path', '')}",
                        "content": content,
                        "posted_date": parse_job_date(item.get("posted_date")),
                    }
        except Exception as e:
            print(f"[-] Error querying Amazon Jobs ({q_url}): {e}", file=sys.stderr)

    return list(jobs_by_id.values())


def fetch_sidero(board_id="siderolabs"):
    url = "https://www.siderolabs.com/careers/"
    headers = {"User-Agent": "JobRadar/1.0"}
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

            jobs.append({
                "id": f"sidero_{slug}",
                "title": title,
                "location": loc,
                "url": job_url,
                "content": content,
            })
    except Exception as e:
        print(f"[-] Error fetching Sidero Labs: {e}", file=sys.stderr)

    return jobs


def fetch_proxmox(board_id="proxmox"):
    url = "https://www.proxmox.com/en/about/careers"
    headers = {"User-Agent": "JobRadar/1.0"}
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
            jobs.append({
                "id": f"proxmox_{slug}",
                "title": title,
                "location": loc,
                "url": "https://www.proxmox.com/en/about/careers",
                "content": f"{title}\n{clean_content[:2000]}",
            })
    except Exception as e:
        print(f"[-] Error fetching Proxmox: {e}", file=sys.stderr)

    return jobs


def score_job(job, company, first_seen=None):
    title = job["title"]
    location = job["location"]
    content = job.get("content", "")

    # 1. Hard title exclusion
    if TITLE_EXCLUDE_RE.search(title):
        return None, 0, [], (0, 0, "", "", 0), {}

    # Must be engineering / technical or match tech stack
    is_eng = bool(ENGINEERING_TITLE_RE.search(title))
    is_sys = bool(SYSTEMS_TITLE_RE.search(title))
    has_tech = bool(TECH_STACK_RE.search(f"{title} {content}"))
    if not (is_eng or is_sys or has_tech):
        return None, 0, [], (0, 0, "", "", 0), {}

    # 2. Location check
    is_direct_italy = bool(LOCATION_ITALY_RE.search(location))
    is_emea_remote = bool(LOCATION_EMEA_REMOTE_RE.search(f"{title} {location}")) or (location.strip().lower() == "remote")
    is_austria = bool(LOCATION_AUSTRIA_RE.search(location)) if company.get("allow_austria") else False

    # Multi-country European remote check (e.g. GitLab, Elastic)
    parts = [p.strip() for p in location.split(";") if p.strip()]
    EU_COUNTRIES = (
        "ireland", "france", "germany", "netherlands", "spain", "united kingdom",
        "uk", "austria", "poland", "sweden", "switzerland", "italy", "belgium",
        "portugal", "denmark", "norway", "finland", "czech", "romania", "emea", "europe",
    )
    eu_matches = [c for c in EU_COUNTRIES if c in location.lower()]
    is_multi_eu = len(parts) >= 2 and len(eu_matches) >= 2
    if is_multi_eu:
        is_emea_remote = True

    is_disqualified = bool(LOCATION_DISQUALIFY_RE.search(location))

    if is_multi_eu or is_austria:
        is_single_country_foreign = False
    elif len(parts) <= 1:
        is_single_country_foreign = bool(SINGLE_COUNTRY_REMOTE_RE.search(location))
    else:
        is_single_country_foreign = not is_emea_remote

    if (is_disqualified or is_single_country_foreign) and not (is_direct_italy or is_austria):
        return None, 0, [], (0, 0, "", "", 0), {}

    if not (is_direct_italy or is_emea_remote or is_austria):
        return None, 0, [], (0, 0, "", "", 0), {}

    # 3. Contract check
    if B2B_RE.search(content):
        return None, 0, [], (0, 0, "", "", 0), {}

    score = 0
    tags = []

    # Company tier
    tier = company.get("tier", "")
    if tier == "big_tech":
        score += 35
        tags.append("tier:big_tech")
    elif tier == "enterprise_infra":
        score += 30
        tags.append("tier:enterprise_infra")
    elif tier == "scaleup":
        score += 15
        tags.append("tier:scaleup")

    # Legal entity & EOR
    if company.get("entity_in_italy"):
        score += 35
        tags.append("legal:it_entity")
    elif company.get("eor_supported"):
        score += 25
        tags.append("legal:eor")

    if is_direct_italy:
        score += 25
        tags.append("loc:italy_direct")
    elif is_emea_remote:
        score += 10
        tags.append("loc:emea_remote")
    elif is_austria:
        score += 15
        tags.append("loc:austria")

    # Systems role relevance
    if SYSTEMS_TITLE_RE.search(title):
        score += 30
        tags.append("role:systems_platform")
    elif re.search(r"\b(software engineer|senior engineer|staff engineer|principal engineer)\b", title, re.IGNORECASE):
        score += 10
        tags.append("role:swe")

    # Tech stack match
    matches = TECH_STACK_RE.findall(f"{title} {content}")
    if matches:
        unique_matches = sorted(list(set(m.lower() for m in matches)))
        score += min(len(unique_matches) * 5, 25)
        tags.append(f"tech:{','.join(unique_matches[:4])}")

    # Salary extraction & 85k baseline scoring
    salary_info = extract_salary(job)
    vmin, vmax, curr, disp, norm = salary_info
    if norm >= 150000:
        score += 35
        tags.append(f"pay:{disp}(>150k)")
    elif norm >= 120000:
        score += 25
        tags.append(f"pay:{disp}(>120k)")
    elif norm > 85000:
        score += 15
        tags.append(f"pay:{disp}(>85k)")
    elif 0 < norm <= 85000:
        score -= 10
        tags.append(f"pay:{disp}(<=85k)")

    # Profile semantic match
    prof_eval = evaluate_profile_match(title, content, company.get("id", ""))
    match_pct = prof_eval["match_pct"]
    if match_pct >= 80:
        score += 15
        tags.append(f"match:{match_pct}%")
    elif match_pct >= 50:
        score += 5
        tags.append(f"match:{match_pct}%")

    # Freshness priority & staleness decay (fewer applicants for fresh roles)
    eff_date = job.get("posted_date") or first_seen
    age_days = 0
    if eff_date:
        try:
            clean_date = str(eff_date).split(".")[0]
            dt = datetime.datetime.strptime(clean_date, "%Y-%m-%d %H:%M:%S")
            now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
            age_days = max(0, (now_utc - dt).days)
        except Exception:
            age_days = 0

    if age_days <= 7:
        score += 20
        tags.append("age:fresh(<7d)")
    elif age_days <= 21:
        score += 10
        tags.append("age:recent(<=21d)")
    elif age_days <= 45:
        # Active baseline
        pass
    elif age_days <= 75:
        score -= 15
        tags.append("age:aging(>45d)")
    else:
        score -= 30
        tags.append(f"age:stale(>75d)")

    return tags, score, (is_direct_italy, is_emea_remote or is_austria), salary_info, prof_eval


def cmd_sync(args):
    conn = get_db()
    targets = load_targets()
    total_fetched = 0
    total_matched = 0

    print(f"[*] Syncing {len(targets)} target companies...")
    for comp in targets:
        cid = comp["id"]
        ats = comp.get("ats")
        board = comp.get("board", cid)

        if ats == "greenhouse":
            raw_jobs = fetch_greenhouse(board)
        elif ats == "ashby":
            raw_jobs = fetch_ashby(board)
        elif ats == "lever":
            raw_jobs = fetch_lever(board)
        elif ats == "workday":
            site = comp.get("site", "jobs")
            sub_domain = comp.get("sub_domain", "wd5")
            raw_jobs = fetch_workday(board, site, sub_domain=sub_domain)
        elif ats == "smartrecruiters":
            raw_jobs = fetch_smartrecruiters(board)
        elif ats == "dynatrace":
            raw_jobs = fetch_dynatrace()
        elif ats == "amazon":
            raw_jobs = fetch_amazon(board)
        elif ats == "sidero":
            raw_jobs = fetch_sidero(board)
        elif ats == "proxmox":
            raw_jobs = fetch_proxmox(board)
        else:
            print(f"[!] Unknown ATS: {ats} for {cid}")
            continue

        matched_count = 0
        total_fetched += len(raw_jobs)

        with conn:
            conn.execute("UPDATE jobs SET active = 0 WHERE company_id = ?", (cid,))
            existing_first_seen = {
                r["id"]: r["first_seen"]
                for r in conn.execute("SELECT id, first_seen FROM jobs WHERE company_id = ?", (cid,)).fetchall()
            }
            for rj in raw_jobs:
                jid = rj["id"]
                prev_seen = existing_first_seen.get(jid)
                ats_date = rj.get("posted_date")
                if ats_date and prev_seen:
                    effective_date = min(ats_date, prev_seen)
                else:
                    effective_date = ats_date or prev_seen

                tags, score, loc_info, sal_info, prof_eval = score_job(rj, comp, first_seen=effective_date)
                if tags is None or score < args.min_score:
                    continue

                is_it, is_emea = loc_info
                s_min, s_max, s_curr, s_disp, s_norm = sal_info
                tags_str = ";".join(tags)

                match_pct = prof_eval.get("match_pct", 0)
                matched_skills_str = ", ".join(prof_eval.get("matched_skills", []))
                pitch_str = "\n".join(prof_eval.get("pitch_bullets", []))

                if effective_date:
                    conn.execute("""
                        INSERT INTO jobs (
                            id, company_id, title, location, is_italy_direct, is_emea_remote,
                            score, url, tags, salary_min, salary_max, salary_currency,
                            salary_display, salary_norm_max, profile_match_pct, matched_skills,
                            pitch_bullets, active, first_seen, last_seen
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, CURRENT_TIMESTAMP)
                        ON CONFLICT(id) DO UPDATE SET
                            title=excluded.title,
                            location=excluded.location,
                            is_italy_direct=excluded.is_italy_direct,
                            is_emea_remote=excluded.is_emea_remote,
                            score=excluded.score,
                            url=excluded.url,
                            tags=excluded.tags,
                            salary_min=excluded.salary_min,
                            salary_max=excluded.salary_max,
                            salary_currency=excluded.salary_currency,
                            salary_display=excluded.salary_display,
                            salary_norm_max=excluded.salary_norm_max,
                            profile_match_pct=excluded.profile_match_pct,
                            matched_skills=excluded.matched_skills,
                            pitch_bullets=excluded.pitch_bullets,
                            first_seen=CASE WHEN excluded.first_seen IS NOT NULL AND excluded.first_seen < jobs.first_seen THEN excluded.first_seen ELSE jobs.first_seen END,
                            active=1,
                            last_seen=CURRENT_TIMESTAMP
                    """, (
                        rj["id"], cid, rj["title"], rj["location"], int(is_it), int(is_emea),
                        score, rj["url"], tags_str, s_min, s_max, s_curr, s_disp, s_norm,
                        match_pct, matched_skills_str, pitch_str, effective_date
                    ))
                else:
                    conn.execute("""
                        INSERT INTO jobs (
                            id, company_id, title, location, is_italy_direct, is_emea_remote,
                            score, url, tags, salary_min, salary_max, salary_currency,
                            salary_display, salary_norm_max, profile_match_pct, matched_skills,
                            pitch_bullets, active, last_seen
                        )
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
                        ON CONFLICT(id) DO UPDATE SET
                            title=excluded.title,
                            location=excluded.location,
                            is_italy_direct=excluded.is_italy_direct,
                            is_emea_remote=excluded.is_emea_remote,
                            score=excluded.score,
                            url=excluded.url,
                            tags=excluded.tags,
                            salary_min=excluded.salary_min,
                            salary_max=excluded.salary_max,
                            salary_currency=excluded.salary_currency,
                            salary_display=excluded.salary_display,
                            salary_norm_max=excluded.salary_norm_max,
                            profile_match_pct=excluded.profile_match_pct,
                            matched_skills=excluded.matched_skills,
                            pitch_bullets=excluded.pitch_bullets,
                            active=1,
                            last_seen=CURRENT_TIMESTAMP
                    """, (
                        rj["id"], cid, rj["title"], rj["location"], int(is_it), int(is_emea),
                        score, rj["url"], tags_str, s_min, s_max, s_curr, s_disp, s_norm,
                        match_pct, matched_skills_str, pitch_str
                    ))
                matched_count += 1

            conn.execute(
                "INSERT INTO fetch_log (company_id, jobs_found, jobs_matched) VALUES (?, ?, ?)",
                (cid, len(raw_jobs), matched_count),
            )
        total_matched += matched_count
        print(f"  + {comp['name']:<24} | Found: {len(raw_jobs):<4} | Matched: {matched_count}")

    # Generate RSS Feed
    all_active = conn.execute("""
        SELECT * FROM jobs WHERE active = 1 ORDER BY score DESC, salary_norm_max DESC LIMIT 50
    """).fetchall()
    feed_jobs = [dict(r) for r in all_active]
    generate_rss_feed(feed_jobs, FEED_PATH)
    print(f"\n[+] Sync complete. Total scanned: {total_fetched}, Matched: {total_matched}")
    print(f"[+] RSS Feed generated: {FEED_PATH}")


def cmd_company(args):
    """Display company intelligence dossier."""
    intel_data = load_company_intel()
    cid = args.company_id.lower()
    comp = intel_data.get(cid)
    if not comp:
        print(f"[-] No dossier found for '{cid}'. Available companies:")
        for k in sorted(intel_data.keys()):
            print(f"  - {k}")
        return

    print(f"\n{'='*75}")
    print(f"🏛️  {comp['name'].upper()} — COMPANY INTELLIGENCE DOSSIER")
    print(f"{'='*75}")
    print(f"⭐ Glassdoor Rating: {comp['glassdoor_rating']}/5.0 (Recommend: {comp['recommend_to_friend']}, CEO Approval: {comp['ceo_approval']})")
    print(f"🇮🇹 Italy Entity:     {comp['italy_legal_entity']} ({comp['contract_type']})")
    print(f"🏠 Remote Policy:    {comp['remote_policy']}")
    print(f"💰 EMEA Staff Comp:  {comp['emea_staff_comp_range']}")
    print(f"\n--- CULTURE & REVIEWS ---")
    print(f"{comp['culture_and_wlb']['summary']}")
    print("Pros:")
    for p in comp['culture_and_wlb']['pros']:
        print(f"  + {p}")
    print("Cons:")
    for c in comp['culture_and_wlb']['cons']:
        print(f"  - {c}")

    print(f"\n--- INTERVIEW PROCESS (5 Stages) ---")
    for s in comp['interview_process']['stages']:
        print(f"  {s}")

    print(f"\n--- TAILORED STRATEGY FOR CANDIDATE ---")
    print(f"{comp['interview_process']['insider_tips']}")
    print(f"{'='*75}\n")


def cmd_top(args):
    conn = get_db()
    query = """
        SELECT company_id, title, location, score, salary_display, salary_norm_max,
               profile_match_pct, matched_skills, first_seen, url, tags
        FROM jobs
        WHERE active = 1 AND score >= ?
    """
    params = [args.min_score]
    if args.italy_only:
        query += " AND is_italy_direct = 1"
    if args.has_salary:
        query += " AND salary_norm_max > 0"
    if args.min_salary > 0:
        query += " AND salary_norm_max >= ?"
        params.append(args.min_salary)
    if args.min_match > 0:
        query += " AND profile_match_pct >= ?"
        params.append(args.min_match)

    if args.by_salary:
        query += " ORDER BY salary_norm_max DESC, score DESC LIMIT ?"
    elif args.by_profile:
        query += " ORDER BY profile_match_pct DESC, score DESC LIMIT ?"
    else:
        query += " ORDER BY score DESC, salary_norm_max DESC LIMIT ?"

    params.append(args.limit)

    rows = conn.execute(query, params).fetchall()
    if not rows:
        print("No jobs found matching criteria.")
        return

    print(f"\n{'SCORE':<5} | {'MATCH':<5} | {'SALARY':<15} | {'COMPANY':<12} | {'TITLE':<38} | {'AGE'}")
    print("-" * 115)
    for r in rows:
        sal = r['salary_display'] if r['salary_display'] else "—"
        fresh = compute_freshness(r['first_seen'])
        age_str = f"{fresh['days_active']}d" if fresh['days_active'] > 0 else "today"
        title = (r['title'][:36] + '..') if len(r['title']) > 36 else r['title']
        match_str = f"{r['profile_match_pct']}%"

        print(f"[{r['score']:>3}]  | {match_str:<5} | {sal:<15} | {r['company_id']:<12} | {title:<38} | {age_str}")
        print(f"        SKILLS: {r['matched_skills']}")
        print(f"        URL:    {r['url']}")
        print()


def cmd_review(args):
    conn = get_db()
    intel_data = load_company_intel()
    rows = conn.execute("""
        SELECT company_id, title, location, score, salary_display, salary_norm_max,
               profile_match_pct, matched_skills, pitch_bullets, first_seen, url, tags
        FROM jobs
        WHERE active = 1 AND score >= ?
        ORDER BY score DESC, salary_norm_max DESC
        LIMIT ?
    """, (args.min_score, args.limit)).fetchall()

    if not rows:
        print("No jobs found for review.")
        return

    print(f"\n=== INTERACTIVE JOB REVIEW ({len(rows)} top roles) ===")
    for idx, r in enumerate(rows, 1):
        sal = r['salary_display'] if r['salary_display'] else "Not disclosed"
        fresh = compute_freshness(r['first_seen'])
        cid = r['company_id']
        comp_info = intel_data.get(cid, {})
        rating = f" (GD: {comp_info.get('glassdoor_rating', 'N/A')}⭐)" if comp_info else ""
        entity = comp_info.get('italy_legal_entity', 'Verified Entity/EOR')

        print(f"\n[{idx}/{len(rows)}] [{r['score']} pts | {r['profile_match_pct']}% match] {cid.upper()}{rating}: {r['title']}")
        print(f"  * Legal Entity: {entity}")
        print(f"  * Location:     {r['location']}")
        print(f"  * Compensation: {sal}")
        print(f"  * Freshness:    {fresh['status']}")
        print(f"  * Key Skills:   {r['matched_skills']}")
        print(f"  * URL:          {r['url']}")
        print("  * Custom Pitch:")
        for p in (r['pitch_bullets'] or '').splitlines():
            print(f"    - {p}")


def cmd_stats(args):
    conn = get_db()
    total_active = conn.execute("SELECT count(*) FROM jobs WHERE active = 1").fetchone()[0]
    total_it = conn.execute("SELECT count(*) FROM jobs WHERE active = 1 AND is_italy_direct = 1").fetchone()[0]
    total_sal = conn.execute("SELECT count(*) FROM jobs WHERE active = 1 AND salary_norm_max > 0").fetchone()[0]
    high_match = conn.execute("SELECT count(*) FROM jobs WHERE active = 1 AND profile_match_pct >= 75").fetchone()[0]

    print(f"Active tracked jobs in DB: {total_active}")
    print(f"Jobs with direct Italy location: {total_it}")
    print(f"Jobs with salary disclosed: {total_sal}")
    print(f"Jobs with >=75% profile match to the candidate: {high_match}")

    print("\nBreakdown by company:")
    rows = conn.execute("""
        SELECT company_id, count(*) as cnt, max(score) as max_score,
               max(profile_match_pct) as max_match,
               sum(CASE WHEN salary_norm_max > 0 THEN 1 ELSE 0 END) as sal_count
        FROM jobs WHERE active = 1
        GROUP BY company_id ORDER BY cnt DESC
    """).fetchall()
    for r in rows:
        print(f"  - {r['company_id']:<16}: {r['cnt']} jobs (max match: {r['max_match']}%, salary listed: {r['sal_count']}, max score: {r['max_score']})")


def main():
    parser = argparse.ArgumentParser(description="Job Radar CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    p_sync = sub.add_parser("sync", help="Fetch, extract salary, score, and evaluate profile match")
    p_sync.add_argument("--min-score", type=int, default=50, help="Minimum score to store (default: 50)")

    p_top = sub.add_parser("top", help="Show top scored jobs")
    p_top.add_argument("--min-score", type=int, default=50, help="Minimum score filter")
    p_top.add_argument("--italy-only", action="store_true", help="Only show direct Italy locations")
    p_top.add_argument("--by-salary", action="store_true", help="Sort highest paying jobs first")
    p_top.add_argument("--by-profile", action="store_true", help="Sort highest profile match first")
    p_top.add_argument("--has-salary", action="store_true", help="Only show jobs with disclosed salary")
    p_top.add_argument("--min-salary", type=int, default=0, help="Minimum salary in EUR (e.g. 100000)")
    p_top.add_argument("--min-match", type=int, default=0, help="Minimum profile match percentage (0-100)")
    p_top.add_argument("--limit", type=int, default=25, help="Number of jobs to list")

    p_rev = sub.add_parser("review", help="Detailed review of top matches with custom pitch bullets")
    p_rev.add_argument("--min-score", type=int, default=110, help="Minimum score (default: 110)")
    p_rev.add_argument("--limit", type=int, default=10, help="Limit number of roles (default: 10)")

    p_comp = sub.add_parser("company", help="View company intelligence dossier (reviews, interview process, legal entity)")
    p_comp.add_argument("company_id", help="Company ID (e.g. cloudflare, sysdig, redhat, purestorage)")

    sub.add_parser("stats", help="Database statistics")

    args = parser.parse_args()
    if args.command == "sync":
        cmd_sync(args)
    elif args.command == "top":
        cmd_top(args)
    elif args.command == "review":
        cmd_review(args)
    elif args.command == "company":
        cmd_company(args)
    elif args.command == "stats":
        cmd_stats(args)


if __name__ == "__main__":
    main()
