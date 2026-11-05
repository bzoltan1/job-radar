# Job Radar

Automated job discovery, ATS scraping, and semantic scoring engine targeting Linux, Kernel, Systems, Observability, and Cloud Platform engineering roles.

**Key Highlights:**
- **Zero HTML Scraping**: Queries public REST / GraphQL ATS endpoints directly (Greenhouse, Lever, Ashby, Workday, Deel, Recruitee, Workable, SmartRecruiters).
- **Multi-Stage Scoring Pipeline**: Filters non-engineering roles, evaluates geographic eligibility & legal entity status, normalizes compensation, and scores candidate skill alignment.
- **Custom Application Pitch Generator**: Dynamically crafts tailored CV & interview pitch bullets based on candidate profile.
- **Multiple Output Sinks**: SQLite database, RSS 2.0 feed, Obsidian markdown vault (with Dataview dashboard), Telegram bot notifications, and desktop alerts.

---

## 🚀 Quickstart & Adoption Guide

### 1. Prerequisites & Installation

Clone the repository and set up a Python 3.10+ virtual environment:

```bash
git clone https://github.com/your-username/job-radar.git
cd job-radar

python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure Environment (`.env`)

Copy `.env.example` to `.env`:

```bash
cp .env.example .env
```

Edit `.env` to configure your credentials, paths, and country:

```bash
# --- Candidate Location & Eligibility ---
# Primary country of residence (e.g. Italy, Germany, France, Spain, United Kingdom, Canada, US, etc.)
CANDIDATE_COUNTRY="Italy"
# Comma-separated secondary countries for direct employment or relocation
CANDIDATE_ALLOWED_COUNTRIES="Austria"

# --- Telegram Notifications (Optional) ---
TELEGRAM_BOT_TOKEN="your_bot_token_from_botfather"
TELEGRAM_CHAT_ID="your_telegram_chat_id"

# Minimum score or salary to trigger a Telegram alert
JOB_RADAR_NOTIFY_MIN_SCORE=85
JOB_RADAR_NOTIFY_MIN_SALARY=90000

# --- Obsidian Vault Export (Optional) ---
OBSIDIAN_VAULT_PATH="~/vault/career"

# --- Candidate Profile Overrides (Optional) ---
# Path to custom profile YAML (defaults to data/profile.local.yaml, data/profile.yaml, or data/profile.example.yaml)
# JOB_RADAR_PROFILE="data/profile.yaml"
```

### 3. Customize Candidate Profile (`data/profile.yaml`)

Job Radar uses your career profile to calculate semantic match percentages and generate tailored application pitches.

Copy the template:
```bash
cp data/profile.example.yaml data/profile.yaml
```

Edit `data/profile.yaml`:
- **`candidate`**: Set your name, headline, current role, years of experience, and home country.
- **`compensation`**: Define target salary tiers (in EUR equivalent) for scoring boosts.
- **`deep_domain_expertise`**: Define your core technical pillars.
- **`scoring_weights`**: Customize keyword bonuses for titles and job descriptions.
- **`skill_matrix`** (Optional): Add custom regex patterns and tailored pitch suggestions.

> **Tip:** You can also save a private local override at `data/profile.local.yaml`, which is automatically recognized and ignored by git.

### 4. Customize Target Companies (`data/targets.yaml`)

`data/targets.yaml` defines the companies and ATS endpoints to track. Over 50 top tech companies (Cloudflare, Datadog, GitLab, Nebius, ElevenLabs, etc.) are pre-configured.

To add a new company:
```yaml
companies:
  - id: examplecorp
    name: "Example Corp"
    tier: scaleup
    category: "Cloud Infrastructure"
    ats: greenhouse         # greenhouse, lever, ashby, workday, deel, recruitee
    board: examplecorp      # ATS board identifier
    entity_in_home_country: false  # Home-country legal entity presence
    eor_supported: true     # Supports Employer of Record
    notes: "Distributed systems, Go & Rust."
```

Or discover and add companies interactively via CLI:
```bash
python3 radar.py discover list
python3 radar.py discover cncf "runtime"
python3 radar.py discover add sysdig
```

---

## 💻 CLI Usage

### Sync & Run Pipeline
Scrape all target companies, compute scores, and export to default sinks (db, rss, obsidian):
```bash
python3 radar.py sync
```

Sync with Telegram and Desktop alerts enabled:
```bash
python3 radar.py sync --notify
```

Sync only a single target company:
```bash
python3 radar.py sync --company cloudflare
```

### Explore Matched Roles
View roles sorted by **Profile Match %**:
```bash
python3 radar.py top --by-profile
python3 radar.py top --by-profile --min-match=75
```

View highest-paying positions:
```bash
python3 radar.py top --by-salary
python3 radar.py top --by-salary --min-salary=120000
```

Interactive review with tailored CV pitch bullets:
```bash
python3 radar.py review --limit=10
```

Inspect company intelligence dossier:
```bash
python3 radar.py company cloudflare
```

Update job tracking status (`new`, `reviewing`, `applied`, `interviewing`, `offer`, `rejected`, `archived`):
```bash
python3 radar.py status <job_id> applied
```

View database & scoring statistics:
```bash
python3 radar.py stats
```

---

## 📡 Sinks & Outputs

### 1. SQLite Database (`jobs.db`)
Central store for all tracked roles, historical states, and notification timestamps.

### 2. RSS 2.0 Feed (`feed.xml`)
Every `sync` generates a standard RSS feed at `feed.xml`. Subscribe using any feed reader (**newsboat**, Thunderbird, Feedly, NetNewsWire).

### 3. Obsidian Vault
When configured, exports structured notes into your Obsidian vault:
- **`jobs/offers/`**: One markdown file per role with YAML frontmatter, compensation breakdown, match percentage, and tailored pitch points. User edits in `## My Notes` or status changes are **strictly preserved** across runs.
- **`jobs/companies/`**: Dossiers with Glassdoor ratings, remote policy, EMEA compensation benchmarks, and interview pipeline stages.
- **`Job Radar Dashboard.md`**: Master dashboard with a Dataview pipeline table and static fallback tables.

### 4. Telegram Alerts
Dispatches HTML-formatted push alerts with clickable application links whenever a new role exceeds `JOB_RADAR_NOTIFY_MIN_SCORE` or `JOB_RADAR_NOTIFY_MIN_SALARY`.

---

## ⏰ Automated Scheduling (systemd User Timer)

To run Job Radar automatically in the background on Linux:

1. Copy the unit files to your systemd user directory:
   ```bash
   mkdir -p ~/.config/systemd/user/
   cp systemd/job-radar.timer ~/.config/systemd/user/
   cp systemd/job-radar.service.example ~/.config/systemd/user/job-radar.service
   ```

2. Adjust `WorkingDirectory` and `ExecStart` in `~/.config/systemd/user/job-radar.service` to match your checkout path.

3. Enable and start the timer:
   ```bash
   systemctl --user daemon-reload
   systemctl --user enable --now job-radar.timer
   ```

4. Check timer schedule and logs:
   ```bash
   systemctl --user list-timers job-radar.timer
   journalctl --user -u job-radar.service -n 50
   ```

---

## 🧩 Architecture

```
[data/targets.yaml]
        │
        ▼
┌─────────────────────────┐
│   Source Plugins (ATS)  │ ◄── greenhouse, ashby, lever, workday, workable, etc.
└───────────┬─────────────┘
            │  list[RawJob]
            ▼
┌─────────────────────────┐
│     Pipeline Stages     │
│  1. TitleFilterStage    │ ◄── drops non-engineering / irrelevant roles
│  2. LocationStage       │ ◄── candidate country, EMEA remote, non-EU filter
│  3. ContractStage       │ ◄── penalizes/drops B2B contractor roles
│  4. RoleSeniorityStage  │ ◄── systems/platform relevance & seniority boost
│  5. SalaryStage         │ ◄── EUR normalization & compensation tiers
│  6. ProfileMatchStage   │ ◄── semantic skill matrix match & tailored pitch
│  7. FreshnessStage      │ ◄── age scoring decay
└───────────┬─────────────┘
            │  Job (scored & tagged)
            ▼
┌─────────────────────────┐
│   Output Sink Plugins   │
│  - DatabaseSink         │ ──► sqlite jobs.db
│  - RssSink              │ ──► feed.xml (RSS 2.0)
│  - ObsidianSink         │ ──► Vault notes, Kanban, Dataview dashboard
│  - TelegramSink         │ ──► Bot notifications for new top matches
│  - DesktopSink          │ ──► notify-send alerts
└─────────────────────────┘
```

See [ARCHITECTURE.md](ARCHITECTURE.md) for details on writing custom ATS plugins and pipeline stages.

---

## 📄 License

MIT
