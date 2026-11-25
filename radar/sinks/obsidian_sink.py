"""Obsidian vault export sink plugin."""

import datetime
import hashlib
import json
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


def yq(value: Any) -> str:
    """Quote a value as a YAML double-quoted scalar (JSON strings are valid YAML)."""
    return json.dumps(str(value), ensure_ascii=False)


def company_note_name(cid: str, info: dict) -> str:
    return sanitize_filename(info.get("name", cid.capitalize()))


def assign_note_names(offers_dir: str, jobs: List[Job], intel_data: dict) -> Dict[str, str]:
    """Map job id -> unique note filename (without .md).

    Jobs sharing "<company> - <title>" (same role in several locations) would overwrite one
    note. The first claimant keeps the plain name (so existing notes stay put); others get a
    stable hash suffix. A note on disk is owned by the job_id in its frontmatter.
    """
    claimed: Dict[str, str] = {}
    names: Dict[str, str] = {}
    for j in jobs:
        comp = company_note_name(j.company_id, intel_data.get(j.company_id, {}))
        name = sanitize_filename(f"{comp} - {j.title}")
        owner = claimed.get(name) or _disk_owner(os.path.join(offers_dir, f"{name}.md"))
        if owner not in (None, j.id):
            name = f"{name} {hashlib.sha1(j.id.encode()).hexdigest()[:6]}"
        claimed[name] = j.id
        names[j.id] = name
    return names


def _disk_owner(path: str) -> Optional[str]:
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        return parse_existing_frontmatter(f.read())[0].get("job_id") or None


def parse_existing_frontmatter(content: str) -> Tuple[Dict[str, str], str]:
    m = re.match(r"^---\n(.*?)\n---\n(.*)$", content, re.DOTALL)
    if not m:
        return {}, content
    yaml_text, body = m.group(1), m.group(2)
    meta = {}
    for line in yaml_text.splitlines():
        if ":" in line and not line.startswith(" ") and not line.startswith("-"):
            k, v = line.split(":", 1)
            v = v.strip()
            try:
                meta[k.strip()] = json.loads(v) if v.startswith('"') else v.strip("'")
            except ValueError:
                meta[k.strip()] = v.strip('"')
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


def export_company_dossiers(vault_path: str, intel_data: dict, jobs: List[Job], note_names: Dict[str, str]):
    comp_dir = os.path.join(vault_path, "jobs", "companies")
    os.makedirs(comp_dir, exist_ok=True)
    cand_info = get_candidate_info()
    cand_name = cand_info.get("name", "Candidate")
    loc_cfg = get_location_config()
    country_name = loc_cfg["home_country"].capitalize()

    for cid, info in intel_data.items():
        comp_name = company_note_name(cid, info)
        file_path = os.path.join(comp_dir, f"{comp_name}.md")

        comp_jobs = [j for j in jobs if j.company_id == cid]
        jobs_md = ""
        for cj in comp_jobs[:10]:
            sal = cj.salary.display if cj.salary.display else "Not disclosed"
            base_job = note_names[cj.id]
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
title: {yq(comp_name)}
tier: {yq(info.get('tier', 'Unknown'))}
glassdoor_rating: {info.get('glassdoor_rating', 0.0)}
recommend_rate: {yq(info.get('recommend_to_friend', 'N/A'))}
ceo_approval: {yq(info.get('ceo_approval', 'N/A'))}
home_legal_entity: {yq(entity_val)}
contract_type: {yq(info.get('contract_type', 'N/A'))}
remote_policy: {yq(info.get('remote_policy', 'N/A'))}
emea_staff_comp: {yq(info.get('emea_staff_comp_range', 'N/A'))}
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


def write_dashboard(path: str, jobs: List[Job], intel_data: dict, note_names: Dict[str, str]):
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
        name = company_note_name(cid, c_info)
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
        comp_display = company_note_name(j.company_id, intel_data.get(j.company_id, {}))
        base_name = note_names[j.id]
        sal_disp = j.salary.display if j.salary.display else "—"
        content += f"| **{j.score}** | {j.profile.match_pct}% | {sal_disp} | [[{comp_display}]] | [{j.title}]({j.url}) | `{j.location[:25]}` | [[{base_name}]] |\n"

    with open(path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")


class ObsidianSink(BaseSink):
    name = "obsidian"

    def export(self, jobs: List[Job], context: Dict[str, Any]):
        vault_path = context.get("vault_path") or get_obsidian_vault_path()
        if not vault_path:
            print("[-] Obsidian: vault not configured (OBSIDIAN_VAULT_PATH); skipping.", file=sys.stderr)
            return
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
        note_names = assign_note_names(offers_dir, jobs, intel_data)
        export_company_dossiers(vault_path, intel_data, jobs, note_names)

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
            comp_display = company_note_name(cid, c_info)
            title = j.title
            file_path = os.path.join(offers_dir, f"{note_names[j.id]}.md")

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
job_id: {yq(j.id)}
title: {yq(title)}
company: {yq(cid)}
company_note: {yq(comp_display)}
score: {j.score}
profile_match_pct: {match_pct}
salary: {yq(salary_disp)}
salary_norm_eur: {j.salary.norm_max_eur}
location: {yq(j.location)}
home_direct: {bool(is_direct_home)}
home_entity: {yq(home_entity)}
status: {yq(status)}
url: {yq(j.url)}
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
        write_dashboard(dashboard_path, jobs, intel_data, note_names)
        print(f"[+] Obsidian export: {exported_count} new, {updated_count} updated.")
