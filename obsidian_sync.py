#!/usr/bin/env python3
"""Job Radar to Obsidian Vault Exporter & Notifier with Company Intelligence Dossiers."""

import argparse
import datetime
import os
import re
import sqlite3
import sys
import yaml

from matcher import compute_freshness

DEFAULT_VAULT_PATH = "~/sync/ObsidianNotes"
DB_PATH = os.path.join(os.path.dirname(__file__), "jobs.db")
INTEL_FILE = os.path.join(os.path.dirname(__file__), "company_intel.yaml")


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:80]


def load_company_intel():
    if not os.path.exists(INTEL_FILE):
        return {}
    with open(INTEL_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return data.get("companies", {})


def get_jobs(min_score: int, by_salary: bool = False, by_profile: bool = False, italy_only: bool = False):
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    query = """
        SELECT j.*, c.name as company_name, c.entity_in_italy, c.eor_supported
        FROM jobs j
        LEFT JOIN (
            SELECT 'canonical' as id, 'Canonical' as name, 0 as entity_in_italy, 1 as eor_supported UNION ALL
            SELECT 'redhat', 'Red Hat', 1, 1 UNION ALL
            SELECT 'cloudflare', 'Cloudflare', 1, 1 UNION ALL
            SELECT 'datadog', 'Datadog', 1, 1 UNION ALL
            SELECT 'sysdig', 'Sysdig', 1, 1 UNION ALL
            SELECT 'purestorage', 'Pure Storage', 1, 1 UNION ALL
            SELECT 'mongodb', 'MongoDB', 1, 1 UNION ALL
            SELECT 'palantir', 'Palantir', 1, 1 UNION ALL
            SELECT 'docker', 'Docker', 0, 1 UNION ALL
            SELECT 'grafanalabs', 'Grafana Labs', 0, 1 UNION ALL
            SELECT 'elastic', 'Elastic', 1, 1 UNION ALL
            SELECT 'gitlab', 'GitLab', 0, 1
        ) c ON j.company_id = c.id
        WHERE j.active = 1 AND j.score >= ?
    """
    params = [min_score]
    if italy_only:
        query += " AND j.is_italy_direct = 1"

    if by_salary:
        query += " ORDER BY j.salary_norm_max DESC, j.score DESC"
    elif by_profile:
        query += " ORDER BY j.profile_match_pct DESC, j.score DESC"
    else:
        query += " ORDER BY j.score DESC, j.salary_norm_max DESC"

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return rows


def parse_existing_frontmatter(content: str):
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not m:
        return {}, content
    yaml_text, body = m.group(1), m.group(2)
    meta = {}
    for line in yaml_text.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            k, v = line.split(":", 1)
            meta[k.strip()] = v.strip().strip('"').strip("'")
    return meta, body


def export_company_dossiers(vault_path: str, intel_data: dict, jobs):
    """Generate dedicated company dossier markdown notes in Obsidian."""
    comp_dir = os.path.join(vault_path, "companies")
    os.makedirs(comp_dir, exist_ok=True)

    for cid, info in intel_data.items():
        comp_name = info["name"]
        file_path = os.path.join(comp_dir, f"{comp_name}.md")

        # Find active jobs for this company
        comp_jobs = [j for j in jobs if j["company_id"] == cid]
        jobs_md = ""
        for cj in comp_jobs[:10]:
            sal = cj["salary_display"] if cj["salary_display"] else "Not disclosed"
            base_job = sanitize_filename(f"{comp_name} - {cj['title']}")
            jobs_md += f"- [[{base_job}|{cj['title']}]] — `{sal}` (Score: {cj['score']}, Match: {cj['profile_match_pct']}%)\n"

        if not jobs_md:
            jobs_md = "_No roles matching current score threshold._\n"

        stages_md = "\n".join(f"- {s}" for s in info["interview_process"]["stages"])
        pros_md = "\n".join(f"  + {p}" for p in info["culture_and_wlb"]["pros"])
        cons_md = "\n".join(f"  - {c}" for c in info["culture_and_wlb"]["cons"])

        content = f"""---
title: "{comp_name}"
tier: "{info['tier']}"
glassdoor_rating: {info['glassdoor_rating']}
recommend_rate: "{info['recommend_to_friend']}"
ceo_approval: "{info['ceo_approval']}"
italy_legal_entity: "{info['italy_legal_entity']}"
contract_type: "{info['contract_type']}"
remote_policy: "{info['remote_policy']}"
emea_staff_comp: "{info['emea_staff_comp_range']}"
tags:
  - company-intel
  - company/{cid}
---

# 🏛️ {comp_name} — Company Intelligence & Interview Dossier

- **Tier**: `{info['tier']}`
- **Glassdoor**: **{info['glassdoor_rating']}/5.0** (Recommend: {info['recommend_to_friend']}, CEO Approval: {info['ceo_approval']})
- **Italian Legal Entity**: `{info['italy_legal_entity']}` ({info['contract_type']})
- **Remote Policy**: `{info['remote_policy']}`
- **EMEA Staff Comp Benchmark**: **{info['emea_staff_comp_range']}**

---

## 🎭 Culture & Work-Life Balance
{info['culture_and_wlb']['summary']}

**Pros:**
{pros_md}

**Cons:**
{cons_md}

---

## 🎯 Interview Process & Stages
{stages_md}

---

## 💡 Tailored Preparation for Candidate
> {info['interview_process']['insider_tips']}

---

## 💼 Active Tracked Positions
{jobs_md}
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")


def update_frontmatter_for_archive(content: str, today_str: str) -> str:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not m:
        return f'---\nstatus: "archived"\nactive: false\narchived_date: "{today_str}"\n---\n' + content
    yaml_text, body = m.group(1), m.group(2)
    lines = yaml_text.splitlines()
    new_lines = []
    has_status = False
    has_active = False
    has_arch_date = False
    for line in lines:
        if line.startswith("status:"):
            val = line.split(":", 1)[1].strip().strip('"').strip("'")
            if val in ("applied", "interviewing", "offer"):
                new_lines.append('status: "closed"')
            else:
                new_lines.append('status: "archived"')
            has_status = True
        elif line.startswith("active:"):
            new_lines.append("active: false")
            has_active = True
        elif line.startswith("archived_date:"):
            new_lines.append(f'archived_date: "{today_str}"')
            has_arch_date = True
        else:
            new_lines.append(line)
    if not has_status:
        new_lines.append('status: "archived"')
    if not has_active:
        new_lines.append("active: false")
    if not has_arch_date:
        new_lines.append(f'archived_date: "{today_str}"')
    return f"---\n{chr(10).join(new_lines)}\n---\n" + body


def prune_obsidian_jobs(vault_path: str, max_archive_days: int = 365):
    """
    1. Scan vault/jobs/ for roles that are no longer active in jobs.db:
       Move them to vault/jobs/archive/ with status updated to 'archived' (or 'closed').
    2. Scan vault/jobs/archive/ for roles archived longer than max_archive_days (default 365):
       Permanently delete them.
    """
    jobs_dir = os.path.join(vault_path, "jobs")
    archive_dir = os.path.join(jobs_dir, "archive")
    if not os.path.exists(jobs_dir):
        return

    os.makedirs(archive_dir, exist_ok=True)

    conn = sqlite3.connect(DB_PATH)
    active_urls = set(r[0] for r in conn.execute("SELECT url FROM jobs WHERE active = 1"))
    conn.close()

    today = datetime.date.today()
    today_str = today.isoformat()
    archived_count = 0
    purged_count = 0

    # Step 1: Move inactive jobs from jobs/ to jobs/archive/
    for fname in os.listdir(jobs_dir):
        fp = os.path.join(jobs_dir, fname)
        if not os.path.isfile(fp) or not fname.endswith(".md"):
            continue

        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
        except Exception:
            continue

        m = re.search(r'url:\s*"([^"]+)"', content)
        job_url = m.group(1) if m else None

        # If not active in database, archive it
        if job_url and job_url not in active_urls:
            archived_content = update_frontmatter_for_archive(content, today_str)
            target_path = os.path.join(archive_dir, fname)
            try:
                with open(target_path, "w", encoding="utf-8") as f:
                    f.write(archived_content)
                os.remove(fp)
                archived_count += 1
            except Exception as e:
                print(f"[-] Error archiving {fname}: {e}", file=sys.stderr)

    # Step 2: Purge files from jobs/archive/ older than max_archive_days
    for fname in os.listdir(archive_dir):
        fp = os.path.join(archive_dir, fname)
        if not os.path.isfile(fp) or not fname.endswith(".md"):
            continue

        try:
            with open(fp, "r", encoding="utf-8") as f:
                content = f.read()
            m_date = re.search(r'archived_date:\s*"([^"]+)"', content)
            if m_date:
                arch_dt = datetime.date.fromisoformat(m_date.group(1))
                age_days = (today - arch_dt).days
            else:
                mtime_dt = datetime.date.fromtimestamp(os.path.getmtime(fp))
                age_days = (today - mtime_dt).days

            if age_days >= max_archive_days:
                os.remove(fp)
                purged_count += 1
        except Exception as e:
            print(f"[-] Error purging archived note {fname}: {e}", file=sys.stderr)

    if archived_count > 0 or purged_count > 0:
        print(f"[+] Pruning complete: {archived_count} moved to archive, {purged_count} purged (> {max_archive_days}d).")


def export_to_obsidian(vault_path: str, min_score: int = 75, by_salary: bool = False, by_profile: bool = False, prune: bool = True, max_archive_days: int = 365):
    jobs_dir = os.path.join(vault_path, "jobs")
    os.makedirs(jobs_dir, exist_ok=True)

    intel_data = load_company_intel()
    jobs = get_jobs(min_score, by_salary=by_salary, by_profile=by_profile)
    print(f"[*] Exporting {len(jobs)} jobs (min score: {min_score}) to Obsidian at: {jobs_dir}")

    # Export Company dossiers first
    export_company_dossiers(vault_path, intel_data, jobs)

    exported_count = 0
    updated_count = 0

    for j in jobs:
        cid = j["company_id"]
        c_info = intel_data.get(cid, {})
        comp_display = c_info.get("name", cid.capitalize())
        title = j["title"]
        base_name = sanitize_filename(f"{comp_display} - {title}")
        file_path = os.path.join(jobs_dir, f"{base_name}.md")

        status = "new"
        user_notes = ""

        if os.path.exists(file_path):
            with open(file_path, "r", encoding="utf-8") as f:
                existing_content = f.read()
            existing_meta, existing_body = parse_existing_frontmatter(existing_content)
            status = existing_meta.get("status", "new")
            if "## My Notes" in existing_body:
                user_notes = existing_body.split("## My Notes", 1)[1]
            updated_count += 1
        else:
            exported_count += 1

        salary_disp = j["salary_display"] if j["salary_display"] else "Not disclosed"
        eur_est = f"€{j['salary_norm_max']:,}" if j["salary_norm_max"] > 0 else "N/A"
        it_entity = c_info.get("italy_legal_entity") or ("YES" if j["is_italy_direct"] or (j["tags"] and "legal:it_entity" in j["tags"]) else "NO")
        eor = "YES" if j["tags"] and "legal:eor" in j["tags"] else "NO"
        fresh = compute_freshness(j["first_seen"])
        match_pct = j["profile_match_pct"] or 0
        matched_skills = j["matched_skills"] or ""
        pitch_bullets = j["pitch_bullets"] or ""
        rating_str = f"{c_info.get('glassdoor_rating', 'N/A')}/5.0" if c_info else "N/A"

        pitch_md = "\n".join(f"- {p}" for p in pitch_bullets.splitlines() if p.strip()) if pitch_bullets else "- Emphasize many years Linux engineering experience and current <employer> platform foundation."

        # Quick interview summary if available
        interview_snippet = ""
        if c_info and "interview_process" in c_info:
            stages_short = "<br/>".join(c_info["interview_process"]["stages"][:3])
            interview_snippet = f"""
---

## 🏛️ Company Dossier & Interview Prep: [[{comp_display}]]
- **Glassdoor**: `{rating_str}` | **Entity**: `{it_entity}` ({c_info.get('contract_type', 'Contract')})
- **Typical Interview Pipeline**:
  {c_info['interview_process']['stages'][0]}
  {c_info['interview_process']['stages'][1]}
- 👉 **Full Company Dossier & Strategy**: [[{comp_display}]]
"""

        note_content = f"""---
title: "{title}"
company: "{cid}"
company_note: "{comp_display}"
score: {j['score']}
profile_match_pct: {match_pct}
salary: "{salary_disp}"
salary_norm_eur: {j['salary_norm_max']}
location: "{j['location']}"
italy_direct: {bool(j['is_italy_direct'])}
italy_entity: "{it_entity}"
freshness: "{fresh['status']}"
status: "{status}"
url: "{j['url']}"
date_updated: "{datetime.date.today().isoformat()}"
tags:
  - job-radar
  - company/{cid}
  - score/{j['score']}
  - match/{match_pct}pct
---

# [{j['score']}] {title} — [[{comp_display}]]

- **Company**: [[{comp_display}]] (Rating: `{rating_str}`)
- **Location**: `{j['location']}`
- **Compensation**: **{salary_disp}** (est. EUR: {eur_est})
- **Profile Alignment**: **{match_pct}%** (`{matched_skills}`)
- **Freshness**: `{fresh['status']}`
- **Legal Entity (Italy)**: `{it_entity}`
- **Application Link**: [Open Job Posting]({j['url']})

---

## 🎯 Tailored Application Pitch (Candidate)
{pitch_md}
{interview_snippet}
---

## 📋 Evaluation & Signals
- **Total Radar Score**: {j['score']}/130
- **Status**: **{status.upper()}** (Options: `new`, `reviewing`, `applied`, `interviewing`, `offer`, `archived`)
- **Signals**: `{j['tags']}`

---

## My Notes
{user_notes if user_notes.strip() else "- Initial impression:\n- Key skills to highlight in CV:\n- Questions for recruiter:\n"}
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(note_content.strip() + "\n")

    # Generate Obsidian Dashboard
    dashboard_path = os.path.join(vault_path, "Job Radar Dashboard.md")
    write_dashboard(dashboard_path, jobs, intel_data)
    print(f"[+] Obsidian export complete: {exported_count} new, {updated_count} refreshed.")
    print(f"[+] Company dossiers written to: {os.path.join(vault_path, 'companies')}")
    print(f"[+] Dashboard updated: {dashboard_path}")

    if prune:
        prune_obsidian_jobs(vault_path, max_archive_days=max_archive_days)


def write_dashboard(path: str, jobs, intel_data):
    content = f"""---
title: "Job Radar Dashboard"
date_updated: "{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
tags:
  - dashboard
  - job-radar
---

# 🎯 Job Radar: Active Pipeline & Opportunities (Candidate)

> Updated: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}` | Tracked High-Match Jobs: **{len(jobs)}**

---

## 🏛️ Tracked Company Dossiers (Reviews & Interview Guides)
"""
    for cid, c_info in intel_data.items():
        content += f"- [[{c_info['name']}]] — `{c_info['glassdoor_rating']}⭐` | Entity: `{c_info['italy_legal_entity']}` | Staff Range: `{c_info['emea_staff_comp_range']}`\n"

    content += """
---

## 📊 Dataview Pipeline (If Dataview Installed)

```dataview
TABLE score AS "Score", profile_match_pct AS "Match %", salary AS "Salary", company_note AS "Company", location AS "Location", freshness AS "Freshness", status AS "Status", url AS "Link"
FROM "jobs"
WHERE status != "archived"
SORT score DESC, profile_match_pct DESC
```

---

## 🚀 Top Rated Positions (Static Table)

| Score | Match | Salary | Company | Role | Location | Freshness | Note Link |
|:-----:|:-----:|:------:|:-------:|:-----|:---------|:---------:|:---------:|
"""
    for j in jobs[:35]:
        sal = j["salary_display"] if j["salary_display"] else "—"
        cid = j["company_id"]
        c_name = intel_data.get(cid, {}).get("name", cid.capitalize())
        title = j["title"][:36]
        base_name = sanitize_filename(f"{c_name} - {j['title']}")
        loc = (j["location"][:22] + "..") if len(j["location"]) > 22 else j["location"]
        match_str = f"{j['profile_match_pct']}%" if j['profile_match_pct'] else "—"
        fresh = compute_freshness(j["first_seen"])
        age_badge = f"`{fresh['days_active']}d`" if fresh["days_active"] > 0 else "`fresh`"
        content += f"| **{j['score']}** | `{match_str}` | `{sal}` | [[{c_name}\\|{c_name}]] | {title} | {loc} | {age_badge} | [[{base_name}\\|Note]] |\n"

    content += """
---

## 📌 Workflow in Obsidian
1. Click any **Company** link to review Glassdoor feedback, company culture, and 5-stage interview prep.
2. Click any **Note** link to inspect job details and custom application pitch.
3. Update frontmatter `status`:
   - `new` → `reviewing` → `applied` → `interviewing` → `offer` / `archived`
4. Add personal notes under `## My Notes` (re-syncing will **never** overwrite your notes!).
"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")


def send_notification(jobs, min_score=95):
    top_picks = [j for j in jobs if j["score"] >= min_score or j["salary_norm_max"] >= 150000]
    if not top_picks:
        print("[*] No notifications to send (no new jobs above threshold).")
        return

    summary = f"Job Radar: Found {len(top_picks)} top offers (Score >={min_score} or Sal >=150k)"
    print(f"\n[ALERT] {summary}")
    for j in top_picks[:5]:
        sal = j["salary_display"] if j["salary_display"] else "No salary listed"
        match_pct = j["profile_match_pct"] or 0
        print(f"  ⚡ [{j['score']} | {match_pct}% match] {j['company_id'].capitalize()}: {j['title']} ({sal}) -> {j['url']}")

    if os.path.exists("/usr/bin/notify-send"):
        try:
            top = top_picks[0]
            os.system(f'/usr/bin/notify-send "Job Radar: Top Match [{top["score"]}]" "{top["company_id"].capitalize()}: {top["title"]}"')
        except Exception:
            pass


def main():
    parser = argparse.ArgumentParser(description="Export Job Radar to Obsidian")
    parser.add_argument("--vault", default=DEFAULT_VAULT_PATH, help=f"Path to Obsidian vault (default: {DEFAULT_VAULT_PATH})")
    parser.add_argument("--min-score", type=int, default=80, help="Minimum score to export (default: 80)")
    parser.add_argument("--by-salary", action="store_true", help="Sort highest paying first")
    parser.add_argument("--by-profile", action="store_true", help="Sort highest profile match first")
    parser.add_argument("--notify", action="store_true", help="Send desktop notification for top picks")
    parser.add_argument("--no-prune", dest="prune", action="store_false", default=True, help="Disable pruning of inactive jobs")
    parser.add_argument("--max-archive-days", type=int, default=365, help="Days to retain archived jobs before deletion (default: 365)")

    args = parser.parse_args()
    jobs = get_jobs(args.min_score, by_salary=args.by_salary, by_profile=args.by_profile)
    export_to_obsidian(
        args.vault,
        min_score=args.min_score,
        by_salary=args.by_salary,
        by_profile=args.by_profile,
        prune=args.prune,
        max_archive_days=args.max_archive_days,
    )

    if args.notify:
        send_notification(jobs, min_score=args.min_score)


if __name__ == "__main__":
    main()
