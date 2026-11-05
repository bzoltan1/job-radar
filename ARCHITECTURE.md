# Job Radar: Modular Architecture & Plugin System

Job Radar is an automated career intelligence and scoring engine specifically tuned for Linux, kernel, and systems platform roles eligible for engineers based in the configured country.

---

## 1. Architectural Pipeline

Data flows through three distinct plugin layers:

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
│  1. TitleFilterStage    │ ◄── drops non-eng, non-systems
│  2. LocationStage       │ ◄── Primary country (+25), foreign single-country lock (-40), allowed countries (+15), non-EU drop
│  3. ContractStage       │ ◄── drops B2B, awards legal entity / EOR bonuses
│  4. RoleSeniorityStage  │ ◄── systems/SRE relevance (+30), staff/principal (+20), tech stack
│  5. SalaryStage         │ ◄── EUR normalization, >150k (+35), >120k (+25), >85k (+15)
│  6. ProfileMatchStage   │ ◄── blog research skill matrix & tailored pitch bullets
│  7. FreshnessStage      │ ◄── age scoring (<7d +20, >75d -30)
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

---

## 2. Directory Layout

```
job-radar/
├── data/                         # Decoupled YAML datasets
│   ├── profile.yaml              # Candidate skills & scoring weights
│   ├── targets.yaml              # Tracked companies & ATS endpoints
│   └── intel/                    # Split dossiers (1 file per company)
│       ├── cloudflare.yaml
│       ├── datadog.yaml
│       ├── grafanalabs.yaml
│       ├── sysdig.yaml
│       └── ...
├── radar/                        # Core Python package
│   ├── __init__.py
│   ├── config.py                 # Central path & YAML data loaders
│   ├── models.py                 # RawJob, Job, SalaryInfo, ProfileMatch, CompanyTarget
│   ├── db.py                     # SQLite schema & query operations
│   ├── discovery.py              # CNCF & peer company explorer
│   ├── cli.py                    # Unified CLI command router
│   ├── sources/                  # Source plugins (dynamic auto-discovery via pkgutil)
│   │   ├── base.py               # BaseSource interface
│   │   ├── greenhouse.py
│   │   ├── ashby.py
│   │   ├── lever.py
│   │   ├── workday.py
│   │   ├── workable.py
│   │   ├── smartrecruiters.py
│   │   └── custom.py             # Amazon, Dynatrace, Proxmox, Sidero
│   ├── pipeline/                 # Modular filtering & scoring stages
│   │   ├── base.py               # PipelineStage interface
│   │   ├── engine.py             # PipelineEngine orchestrator
│   │   ├── title.py              # Title & hard tech exclusions
│   │   ├── location.py           # Primary country, foreign lock, Non-EU filter
│   │   ├── contract.py           # B2B drop, legal entity bonuses
│   │   ├── role.py               # Systems/SRE role & seniority scoring
│   │   ├── salary.py             # Regex parser & EUR normalization
│   │   ├── profile.py            # Blog skill matrix match & pitch generation
│   │   └── freshness.py          # Post age & staleness decay
│   └── sinks/                    # Sink plugins (dynamic auto-discovery)
│       ├── base.py               # BaseSink interface
│       ├── db_sink.py            # SQLite updater
│       ├── rss_sink.py           # feed.xml generator
│       ├── obsidian_sink.py      # Vault sync & dashboard generator
│       ├── telegram_sink.py      # Telegram bot alerts
│       └── desktop_sink.py       # Desktop notification
├── radar.py                      # Main entrypoint
├── run_sync.sh                   # Runner script invoked by systemd
├── run_radar_cron.sh             # Backward-compatibility wrapper for systemd unit
└── jobs.db                       # Local SQLite database
```

---

## 3. Extending the System

### Adding a new ATS Source Plugin
Create `radar/sources/<name>.py`:
```python
from radar.models import CompanyTarget, RawJob
from radar.sources.base import BaseSource

class MyAtsSource(BaseSource):
    ats_name = "myats"

    def fetch(self, target: CompanyTarget) -> list[RawJob]:
        # fetch logic
        return [...]
```
The dynamic loader automatically registers it upon startup.

### Adding a new Pipeline Stage
Create `radar/pipeline/<stage>.py` implementing `PipelineStage` and append it to `PipelineEngine.stages` in `radar/pipeline/engine.py`.

### Adding a new Output Sink
Create `radar/sinks/<sink>.py`:
```python
from radar.models import Job
from radar.sinks.base import BaseSink

class WebhookSink(BaseSink):
    name = "webhook"

    def export(self, jobs: list[Job], context: dict):
        # post to webhook
        pass
```
Pass `--sinks db,rss,obsidian,webhook` to invoke it.
