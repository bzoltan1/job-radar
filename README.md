# Job Radar

Automated job discovery, scraper, and scoring engine targeting Linux, Kernel, Systems, Observability, and Cloud Platform engineering roles for Italy residents.

Prioritizes:
- **Direct Italian Entity** (`S.r.l.` / `S.p.A.`) or **Employee of Record** (Deel, Remote.com, CXC) for full employee contract (`contratto a tempo indeterminato`).
- Rejects / penalizes B2B contractor & freelance roles.
- Big Tech & Enterprise Infrastructure leaders over early startups.

---

## 1. Fast CLI Usage

Sync jobs, extract salaries, and compute profile match:
```bash
/usr/bin/python3 radar.py sync
```

View roles sorted by **Profile Match %** to the candidate:
```bash
/usr/bin/python3 radar.py top --by-profile
/usr/bin/python3 radar.py top --by-profile --min-match=80
```

View highest-paying jobs first:
```bash
/usr/bin/python3 radar.py top --by-salary
/usr/bin/python3 radar.py top --by-salary --min-salary=120000
```

View detailed company intelligence dossier (reviews, interview stages, legal entity):
```bash
/usr/bin/python3 radar.py company cloudflare
/usr/bin/python3 radar.py company sysdig
/usr/bin/python3 radar.py company redhat
```

Interactive review with tailored CV pitch bullets:
```bash
/usr/bin/python3 radar.py review --limit=10
```

View database metrics & profile stats:
```bash
/usr/bin/python3 radar.py stats
```

---

## 2. Profile Intelligence & Semantic Matcher (`profile.yaml`)

Built from your CV and technical publications (`ws/ilmanzo.github.com` + `career_systems_plan.md`):
- **Core Pillars**: many years Linux engineering, eBPF & runtime tracing, Go & C systems programming, <employer> QE automation / LTP / openQA, fleet management (thousands of servers), RPM packaging on OBS, RHCE/SLES certifications.
- **Match Engine**: Evaluates every job description against your exact skills matrix, calculating a match percentage (0–100%).
- **Custom Pitch Generator**: Produces 3 tailored application pitch points for each job (referencing your projects like `binary-coverage research`, openQA, and certs).

---

## 3. Local RSS Feed (`feed.xml`)

Each `sync` automatically updates `~/ws/job-radar/feed.xml`:
- Open in any local RSS reader (**newsboat**, Thunderbird, Feedly, NetNewsWire).
- Items include match score, salary, profile match %, and direct application link.

---

## 2. Discovering Similar Companies (peer companies)

List curated peer companies in enterprise systems, Linux, and cloud infrastructure:
```bash
/usr/bin/python3 discover.py list --italy-only
```

Search CNCF Landscape for companies by domain:
```bash
/usr/bin/python3 discover.py cncf "runtime"
/usr/bin/python3 discover.py cncf "storage"
/usr/bin/python3 discover.py cncf "ebpf"
```

Add a discovered company to active tracking:
```bash
/usr/bin/python3 discover.py add sysdig
/usr/bin/python3 discover.py add arm
```

---

## 3. Supported ATS APIs (Zero HTML Scraping)

Target companies use public REST/GraphQL ATS APIs:
- **Greenhouse**: `boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true` (Canonical, Cloudflare, Datadog, Grafana Labs, Elastic, GitLab, Fastly)
- **Lever**: `api.lever.co/v0/postings/{board}?mode=json` (Sysdig, Palantir)
- **Ashby**: `jobs.ashbyhq.com/api/non-user-graphql` (Docker, Temporal)
- **Workday**: `{tenant}.{subdomain}.myworkdayjobs.com/wday/cxs/...` (Red Hat, Intel)

---

## 5. Obsidian Vault Integration & Pipeline Tracking

Sync high-scoring jobs into Obsidian (`~/sync/ObsidianNotes/`):
```bash
/usr/bin/python3 obsidian_sync.py --min-score=95
```

- **Dashboard**: Generates `Job Radar Dashboard.md` in vault with Dataview & static markdown tables.
- **Job Notes**: Creates individual notes under `jobs/` with YAML properties (`company`, `salary`, `score`, `status: new`, `url`).
- **Notes Preservation**: Editing `## My Notes` or changing `status` to `applied`/`interviewing` inside Obsidian is **strictly preserved** on subsequent syncs.

---

## 6. Automated Scheduling (systemd user timer)

Managed via systemd user units:
- Unit files: `systemd/job-radar.service` and `systemd/job-radar.timer` (installed to `~/.config/systemd/user/`)
- Schedule: Twice daily at **01:04 AM** and **01:04 PM** (`Persistent=true`).

Check timer status:
```bash
systemctl --user list-timers job-radar.timer
```

View execution logs:
```bash
journalctl --user -u job-radar.service -n 50
```

Trigger immediate manual run:
```bash
systemctl --user start job-radar.service
```
