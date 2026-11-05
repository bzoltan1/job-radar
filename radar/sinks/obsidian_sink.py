"""Obsidian vault export sink plugin."""

import datetime
import os
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

from radar.config import (
    get_candidate_info,
    get_location_config,
    get_obsidian_vault_path,
    load_all_intel,
)
from radar.models import Job
from radar.sinks.base import BaseSink


def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:80]


def parse_existing_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
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


def export_company_dossiers(vault_path: str, intel_data: dict, jobs: List[Job]):
    comp_dir = os.path.join(vault_path, "jobs", "companies")
    os.makedirs(comp_dir, exist_ok=True)
    cand_info = get_candidate_info()
    cand_name = cand_info.get("name", "Candidate")
    loc_cfg = get_location_config()
    country_name = loc_cfg["home_country"].capitalize()

    for cid, info in intel_data.items():
        comp_name = info.get("name", cid.capitalize())
        file_path = os.path.join(comp_dir, f"{comp_name}.md")

        comp_jobs = [j for j in jobs if j.company_id == cid]
        jobs_md = ""
        for cj in comp_jobs[:10]:
            sal = cj.salary.display if cj.salary.display else "Not disclosed"
            base_job = sanitize_filename(f"{comp_name} - {cj.title}")
            jobs_md += f"- [[{base_job}|{cj.title}]] — `{sal}` (Score: {cj.score}, Match: {cj.profile.match_pct}%)\n"

        if not jobs_md:
            jobs_md = "_No roles matching current score threshold._\n"

        stages_md = "\n".join(f"- {s}" for s in (info.get("interview_process", {}).get("stages") or []))
        pros_md = "\n".join(f"  + {p}" for p in (info.get("culture_and_wlb", {}).get("pros") or []))
        cons_md = "\n".join(f"  - {c}" for c in (info.get("culture_and_wlb", {}).get("cons") or []))

        interview_tips = (
            info.get("interview_process", {}).get("insider_tips")
            or info.get("interview_process", {}).get("candidate_tips")
            or info.get("interview_process", {}).get("interview_tips")
            or ""
        )

        entity_val = info.get("home_legal_entity", "N/A")

        content = f"""---
title: "{comp_name}"
tier: "{info.get('tier', 'Unknown')}"
glassdoor_rating: {info.get('glassdoor_rating', 0.0)}
recommend_rate: "{info.get('recommend_to_friend', 'N/A')}"
ceo_approval: "{info.get('ceo_approval', 'N/A')}"
home_legal_entity: "{entity_val}"
contract_type: "{info.get('contract_type', 'N/A')}"
remote_policy: "{info.get('remote_policy', 'N/A')}"
emea_staff_comp: "{info.get('emea_staff_comp_range', 'N/A')}"
tags:
  - company-intel
  - company/{cid}
---

# 🏛️ {comp_name} — Company Intelligence & Interview Dossier

- **Tier**: `{info.get('tier', 'Unknown')}`
- **Glassdoor**: **{info.get('glassdoor_rating', 'N/A')}/5.0** (Recommend: {info.get('recommend_to_friend', 'N/A')}, CEO Approval: {info.get('ceo_approval', 'N/A')})
- **{country_name} Legal Entity**: `{entity_val}` ({info.get('contract_type', 'N/A')})
- **Remote Policy**: `{info.get('remote_policy', 'N/A')}`
- **EMEA Staff Comp Benchmark**: **{info.get('emea_staff_comp_range', 'N/A')}**

---

## 🎭 Culture & Work-Life Balance
{info.get('culture_and_wlb', {}).get('summary', '')}

**Pros:**
{pros_md}

**Cons:**
{cons_md}

---

## 🎯 Interview Process & Stages
{stages_md}

---

## 💡 Tailored Preparation for {cand_name}
> {interview_tips}

---

## 💼 Active Tracked Positions
{jobs_md}
"""
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content.strip() + "\n")


def write_dashboard(path: str, jobs: List[Job], intel_data: dict):
    cand_info = get_candidate_info()
    cand_name = cand_info.get("name", "Candidate")
    loc_cfg = get_location_config()
    country_name = loc_cfg["home_country"].capitalize()

    content = f"""---
title: "Job Radar Dashboard"
date_updated: "{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}"
tags:
  - dashboard
  - job-radar
---

# 🎯 Job Radar: Active Pipeline & Opportunities ({cand_name})

> Updated: `{datetime.datetime.now().strftime('%Y-%m-%d %H:%M')}` | Tracked High-Match Jobs: **{len(jobs)}**

---

## 🏛️ Tracked Company Dossiers (Reviews & Interview Guides)
"""
    for cid, c_info in intel_data.items():
        name = c_info.get("name", cid.capitalize())
        rating = c_info.get("glassdoor_rating", "N/A")
        entity = c_info.get("home_legal_entity", "N/A")
        comp = c_info.get("emea_staff_comp_range", "N/A")
        content += f"- [[{name}]] — `{rating}⭐` | Entity: `{entity}` | Staff Range: `{comp}`\n"

    content += """
---

## 📊 Dataview Pipeline (If Dataview Installed)

```dataview
TABLE score AS "Score", profile_match_pct AS "Match %", salary AS "Salary", company_note AS "Company", location AS "Location", status AS "Status", url AS "Link"
FROM "jobs/offers"
WHERE status != "archived"
SORT score DESC, profile_match_pct DESC
```

---

## 🚀 Top Rated Positions (Static Table)

| Score | Match | Salary | Company | Role | Location | Note Link |
|:-----:|:-----:|:------:|:-------:|:-----|:---------|:---------:|
"""
    sorted_jobs = sorted(jobs, key=lambda x: x.score, reverse=True)
    for j in sorted_jobs[:25]:
        comp_display = intel_data.get(j.company_id, {}).get("name", j.company_id.capitalize())
        base_name = sanitize_filename(f"{comp_display} - {j.title}")
        sal_disp = j.salary.display if j.salary.display else "—"
        content += f"| **{j.score}** | {j.profile.match_pct}% | {sal_disp} | [[{comp_display}]] | [{j.title}]({j.url}) | `{j.location[:25]}` | [[{base_name}]] |\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")


class ObsidianSink(BaseSink):
    name = "obsidian"

    def export(self, jobs: List[Job], context: Dict[str, Any]):
        vault_path = context.get("vault_path") or get_obsidian_vault_path()
        if not os.path.exists(vault_path):
            try:
                os.makedirs(vault_path, exist_ok=True)
            except Exception:
                print(f"[-] Obsidian vault path does not exist: {vault_path}", file=sys.stderr)
                return

        jobs_root = os.path.join(vault_path, "jobs")
        offers_dir = os.path.join(jobs_root, "offers")
        companies_dir = os.path.join(jobs_root, "companies")
        os.makedirs(offers_dir, exist_ok=True)
        os.makedirs(companies_dir, exist_ok=True)

        intel_data = load_all_intel()
        export_company_dossiers(vault_path, intel_data, jobs)

        cand_info = get_candidate_info()
        cand_name = cand_info.get("name", "Candidate")
        cand_headline = cand_info.get("headline", "Systems Engineering")

        loc_cfg = get_location_config()
        country_name = loc_cfg["home_country"].capitalize()

        exported_count = 0
        updated_count = 0

        for j in jobs:
            cid = j.company_id
            c_info = intel_data.get(cid, {})
            comp_display = c_info.get("name", cid.capitalize())
            title = j.title
            base_name = sanitize_filename(f"{comp_display} - {title}")
            file_path = os.path.join(offers_dir, f"{base_name}.md")

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

            salary_disp = j.salary.display if j.salary.display else "Not disclosed"
            eur_est = f"€{j.salary.norm_max_eur:,}" if j.salary.norm_max_eur > 0 else "N/A"
            tags_str = ";".join(j.tags)

            is_direct_home = j.is_home_direct
            has_legal_entity = "legal:home_entity" in tags_str
            home_entity = (
                c_info.get("home_legal_entity")
                or ("YES" if (is_direct_home or has_legal_entity) else "NO")
            )

            match_pct = j.profile.match_pct
            matched_skills = ", ".join(j.profile.matched_skills)
            rating_str = f"{c_info.get('glassdoor_rating', 'N/A')}/5.0" if c_info else "N/A"

            pitch_md = (
                "\n".join(f"- {p}" for p in j.profile.pitch_bullets)
                if j.profile.pitch_bullets
                else f"- Highlight relevant experience in {cand_headline}."
            )

            note_content = f"""---
title: "{title}"
company: "{cid}"
company_note: "{comp_display}"
score: {j.score}
profile_match_pct: {match_pct}
salary: "{salary_disp}"
salary_norm_eur: {j.salary.norm_max_eur}
location: "{j.location}"
home_direct: {bool(is_direct_home)}
home_entity: "{home_entity}"
status: "{status}"
url: "{j.url}"
date_updated: "{datetime.date.today().isoformat()}"
tags:
  - job-radar
  - company/{cid}
  - score/{j.score}
  - match/{match_pct}pct
---

# [{j.score}] {title} — [[{comp_display}]]

- **Company**: [[{comp_display}]] (Rating: `{rating_str}`)
- **Location**: `{j.location}`
- **Compensation**: **{salary_disp}** (est. EUR: {eur_est})
- **Profile Alignment**: **{match_pct}%** (`{matched_skills}`)
- **Legal Entity ({country_name})**: `{home_entity}`
- **Application Link**: [Open Job Posting]({j.url})

---

## 🎯 Tailored Application Pitch ({cand_name})
{pitch_md}

---

## 📋 Evaluation & Signals
- **Total Radar Score**: {j.score}
- **Status**: **{status.upper()}**
- **Signals**: `{tags_str}`

---

## My Notes
{user_notes if user_notes.strip() else "- Initial impression:\n- Key skills to highlight in CV:\n- Questions for recruiter:\n"}
"""
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(note_content.strip() + "\n")

        dashboard_path = os.path.join(jobs_root, "Job Radar Dashboard.md")
        write_dashboard(dashboard_path, jobs, intel_data)
        print(f"[+] Obsidian export: {exported_count} new, {updated_count} updated.")
