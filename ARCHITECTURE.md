# Job Radar: Systems & Platform Architecture

Target: Automated discovery, scoring, and tracking of Linux/Systems/Cloud Platform engineering roles for Italy-based resident (Employee contract priority: Italian entity or EOR; no freelance/B2B).

---

## 1. Core Architecture

Pipeline 4 stages:

```
[Company Discovery] → [ATS Job Fetcher] → [Filter & Scoring Engine] → [Alert / UI / SQLite]
        │                     │                        │
  - CNCF / LF           - Greenhouse             - Role Relevance
  - GitHub orgs         - Lever                  - Contract Type (CCNL/EOR vs B2B)
  - Peer Graphs         - Ashby                  - Location Filter (IT / EMEA Remote)
                        - Workday                - Tier Weight (Big Tech > Scaleup)
```

---

## 2. Scraping Strategy: Don't Scrape HTML

Raw HTML scraping brittle. 90% target tech companies use standard ATS with public JSON REST APIs:

| ATS | API Pattern | Auth | Blocking Risk |
|---|---|---|---|
| **Greenhouse** | `GET https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true` | None | Very Low |
| **Lever** | `GET https://api.lever.co/v0/postings/{company}?mode=json` | None | Very Low |
| **Ashby** | `POST https://api.ashbyhq.com/posting-api/job-board/{company}` | None | Very Low |
| **SmartRecruiters** | `GET https://api.smartrecruiters.com/v1/companies/{company}/postings` | None | Low |
| **Workday** | `POST https://{tenant}.wd3.myworkdayjobs.com/wday/cxs/{company}/{board}/jobs` | None | Medium (Session/headers) |
| **Amazon Jobs** | `GET https://www.amazon.jobs/en/search.json?base_query={query}&country={country}` | None | Low |
| **Sidero Labs** | Direct career extraction via `https://www.siderolabs.com/careers/` | None | Low |
| **Dynatrace** | SuccessFactors query via `https://apply.careers.dynatrace.com/search/` | None | Low |
| **Proxmox** | Direct portal extraction via `https://www.proxmox.com/en/about/careers` | None | Low |

**Rule**: Target ATS JSON endpoints first. Fallback to headless browser (Playwright) only for custom career pages.

---

## 3. Company Discovery Engine (Finding peer companies)

How to find companies similar to <employer> without manual search:

1. **CNCF Landscape & Linux Foundation Members**:
   - `landscape.cncf.io/data.json` contains complete machine-readable graph of cloud native / systems companies grouped by layer (Runtime, Orchestration, Observability, Storage).
   - Filter by: Enterprise members, Gold/Platinum sponsors, Kubernetes contributors.
2. **Linux & Open Source Ecosystem**:
   - Red Hat, Canonical, Cloudflare, Fastly, Datadog, Grafana Labs, Docker, Elastic, Cisco (Isovalent/Cilium), SchedMD, Intel, AMD, Arm, Oracle, AWS, Google Cloud, Microsoft Azure.
3. **Company Profiling & Tiering**:
   - **Tier 1 (Big Tech / Established Enterprise Infra)**: Score weight: 1.0. (Red Hat, AWS, Google, Microsoft, Cloudflare, Datadog, Cisco, Oracle, Canonical).
   - **Tier 2 (Solid Scaleup / Late-Stage Infrastructure)**: Score weight: 0.6. (Grafana Labs, Elastic, HashiCorp/IBM, GitLab, Docker, Temporal, Chainguard).
   - **Tier 3 (Early Startup / Seed / Series A)**: Disqualified (Score: 0 / dropped). Unstable, usually lack EOR or Italian legal presence.

---

## 4. Italy Hiring & Contract Validation (Critical Gate)

Goal: Full employee status (`contratto a tempo indeterminato` via local S.r.l./branch or EOR like Deel/Remote.com). Reject B2B / Partita IVA traps.

### Detection Heuristics:
1. **Location Tag Parsing**:
   - Match: `"Italy"`, `"Remote - Italy"`, `"EMEA Remote"`, `"Anywhere in Europe"`, `"Milan"`, `"Rome"`.
   - Reject: `"US Only"`, `"UK Only"`, `"Germany Only"`, `"Americas"`, `"APAC"`.
2. **Contract Type NLP / Keyword Extraction**:
   - Positive indicators (+Score):
     - `"Employee of Record"`, `"Deel"`, `"Remote.com"`, `"Oyster"`, `"Omnipresent"`.
     - `"Local contract"`, `"permanent contract"`, `"benefits package"`, `"PTO"`, `"CCNL"`.
   - Negative indicators (-Penalty or Drop):
     - `"Contractor only"`, `"B2B only"`, `"freelance"`, `"independent contractor"`, `"invoice"`, `"VAT number"`.
3. **Italian Entity Registry DB**:
   - Curated lookup of known tech companies with active Italian subsidiaries (e.g., Red Hat Italy S.r.l., Amazon Italia Services S.r.l., Google Italy S.r.l., Cisco Systems Italy S.r.l., Microsoft Italia S.r.l., Datadog Italy S.r.l., Oracle Italia S.r.l.).
   - If company on entity list → 100% contract confidence.

---

## 5. Scoring Model

$$\text{Final Score} = \text{Tier Score} + \text{Role Match Score} + \text{Entity Score} - \text{Contract Penalty}$$

- **Tier Score**:
  - Big Tech / Enterprise Leader: +40 pts
  - Established Infra Scaleup: +20 pts
  - Early Stage / Unknown: 0 pts (filtered out)
- **Role Match Score (Systems / Platform focus)**:
  - Keywords in title (`Systems`, `Linux`, `Platform`, `Kernel`, `Infrastructure`, `eBPF`, `Site Reliability`, `Core OS`, `Runtime`): +30 pts
  - Stack in description (`Go`, `Golang`, `C`, `systemd`, `Kubernetes`, `Containers`, `ELF`, `low-level`): +20 pts
  - Non-systems / Application level (`React`, `Frontend`, `Marketing`, `Sales`, `Product Manager`): -100 pts (auto-drop)
- **Legal / Contract Score**:
  - Confirmed Italian Entity: +40 pts
  - Explicit EOR (Deel/Remote) stated: +30 pts
  - Remote EMEA / Italy generic: +10 pts
  - Contractor / B2B required: Disqualify (drop)

---

## 6. Storage & Notification

- **Database**: SQLite (single file `jobs.db`). Clean schema:
  - `companies` (id, name, website, ats_type, ats_id, tier, has_italian_entity, eor_supported)
  - `jobs` (id, company_id, title, location, remote_type, url, score, contract_type, first_seen, last_seen, active)
  - `job_history` (job_id, status_change, timestamp)
- **Notification**:
  - Daily summary via Telegram bot or local terminal report (`job-radar review`).
  - Score threshold: Only notify if Score >= 70.

---

## 7. Production Roadmap & Implementation Phases

1. **Dynamic Target Resolution**: Eliminate hardcoded SQL `UNION ALL` subqueries in `obsidian_sync.py`; query metadata dynamically from `targets.yaml`.
2. **Delta Notification Tracking**: Track `notified_at` in `jobs.db` to only dispatch notifications on newly discovered roles rather than spamming existing matches.
3. **Telegram Alert Dispatcher**: Direct Telegram bot alert integration (`chat_id: <chat_id>`) with markdown formatting for mobile notification on cron runs.
4. **Application Status Management CLI**: Bi-directional status CLI (`radar.py status <job_id> applied|interviewing|offer|archived`) updating SQLite and Obsidian note frontmatter simultaneously.
5. **Cover Letter & Pitch Drafter**: CLI generator (`radar.py draft <job_id>`) producing markdown application pitches and cold introduction letters tailored to the candidate's <employer>, LTP, a QEMU VM runner, and binary-coverage research background.
