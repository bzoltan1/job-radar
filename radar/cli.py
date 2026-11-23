"""Unified modern CLI for Job Radar."""

import argparse
import os
import sys

from radar.config import (
    ConfigError,
    get_location_config,
    load_all_intel,
    load_company_intel,
    load_targets,
)
from radar.db import (
    deactivate_company_jobs,
    get_active_jobs,
    get_db,
    get_existing_first_seen,
    update_job_status,
)
from radar.discovery import add_peer, list_peers, query_cncf
from radar.models import PipelineContext
from radar.pipeline.engine import PipelineEngine
from radar.sinks import get_sink, list_sinks
from radar.sources import get_source, list_sources


def cmd_sync(args):
    get_location_config()  # fail fast on missing candidate country
    conn = get_db()
    targets = load_targets()
    if getattr(args, "company", None):
        targets = [c for c in targets if c.id.lower() == args.company.lower()]
        if not targets:
            print(f"[-] No target matching company ID: {args.company}", file=sys.stderr)
            return

    engine = PipelineEngine()
    total_scanned = 0
    all_processed_jobs = []

    print(f"[*] Syncing {len(targets)} target companies...")
    for target in targets:
        source = get_source(target.ats)
        if not source:
            print(f"[-] Unknown ATS '{target.ats}' for {target.name}. Skipping.", file=sys.stderr)
            continue

        raw_jobs = source.fetch(target)
        total_scanned += len(raw_jobs)
        existing_first_seen = get_existing_first_seen(conn, target.id)
        # shortcut: sources swallow fetch errors and return [], so an empty result keeps the
        # company's jobs active instead of wiping them; a company that really drops to zero
        # openings keeps stale rows until sources report failures explicitly.
        if not raw_jobs:
            if existing_first_seen:
                print(f"  ! {target.name:<24} | Found: 0 | keeping {len(existing_first_seen)} stored jobs (fetch may have failed)")
            continue
        deactivate_company_jobs(conn, target.id)

        target_matched = 0
        for raw_job in raw_jobs:
            prev_seen = existing_first_seen.get(raw_job.id)
            effective_date = raw_job.posted_date or prev_seen
            ctx = PipelineContext(target=target, first_seen=effective_date)

            job = engine.process(raw_job, ctx)
            if job and job.score >= args.min_score:
                all_processed_jobs.append(job)
                target_matched += 1

        print(f"  + {target.name:<24} | Found: {len(raw_jobs):<4} | Matched: {target_matched}")

    # Dispatch to Sinks
    sink_names = [s.strip().lower() for s in args.sinks.split(",") if s.strip()]
    if args.notify:
        if "telegram" not in sink_names:
            sink_names.append("telegram")
        if "desktop" not in sink_names:
            sink_names.append("desktop")

    sink_context = {
        "db_conn": conn,
        "min_score": args.min_score,
        "force_notify": getattr(args, "force_notify", False),
    }

    for s_name in sink_names:
        sink = get_sink(s_name)
        if sink:
            sink.export(all_processed_jobs, sink_context)
        else:
            print(f"[-] Warning: Sink '{s_name}' not found.", file=sys.stderr)

    print(f"\n[+] Sync complete. Total scanned: {total_scanned}, Matched: {len(all_processed_jobs)}")


def cmd_top(args):
    conn = get_db()
    jobs = get_active_jobs(
        conn,
        min_score=args.min_score,
        home_only=args.home_only,
        by_salary=args.by_salary,
        by_profile=args.by_profile,
        has_salary=args.has_salary,
        min_salary=args.min_salary,
        min_match=args.min_match,
        company_id=args.company,
        limit=args.limit,
    )

    if not jobs:
        print("No matching jobs found.")
        return

    print(f"\n{'SCORE':<5} | {'MATCH':<5} | {'COMPANY':<14} | {'TITLE':<38} | {'LOCATION':<24} | {'SALARY'}")
    print("-" * 115)
    for j in jobs:
        sal = j["salary_display"] or "-"
        comp = j["company_id"].capitalize()[:14]
        title = j["title"][:38]
        loc = j["location"][:24]
        print(f"{j['score']:<5} | {j['profile_match_pct']:<5}% | {comp:<14} | {title:<38} | {loc:<24} | {sal}")


def cmd_review(args):
    conn = get_db()
    jobs = get_active_jobs(
        conn,
        min_score=args.min_score,
        limit=args.limit,
    )

    if not jobs:
        print("No jobs found for review.")
        return

    for j in jobs:
        comp = j["company_id"].capitalize()
        sal = j["salary_display"] or "Not disclosed"
        print("=" * 80)
        print(f"[{j['score']} pts | {j['profile_match_pct']}% match] {comp}: {j['title']}")
        print(f"Location: {j['location']} | Status: {j['status'].upper()}")
        print(f"Salary:   {sal} (EUR: €{j['salary_norm_max']:,})")
        print(f"URL:      {j['url']}")
        print(f"Signals:  {j['tags']}")
        print("\nTailored Pitch Bullets:")
        if j["pitch_bullets"]:
            for b in j["pitch_bullets"].splitlines():
                print(f"  * {b}")
        print()


def cmd_status(args):
    conn = get_db()
    res = update_job_status(conn, args.job_id, args.status.lower())
    if res:
        print(f"[+] Updated: {res}")
    else:
        print(f"[-] No active job matched: {args.job_id}")


def cmd_apply(args):
    conn = get_db()
    res = update_job_status(conn, args.job_id, "applied")
    if res:
        print(f"[+] Role marked APPLIED: {res}")
    else:
        print(f"[-] No job matched: {args.job_id}")


def cmd_company(args):
    intel = load_company_intel(args.company_id)
    if not intel:
        print(f"[-] No dossier found for company: {args.company_id}")
        return

    print("=" * 80)
    print(f"🏛️  {intel.get('name', args.company_id.capitalize())} — Dossier")
    print(f"Tier:            {intel.get('tier')}")
    print(f"Glassdoor:       {intel.get('glassdoor_rating')}/5.0 (Recommend: {intel.get('recommend_to_friend')})")
    print(f"Home Entity:     {intel.get('home_legal_entity')}")
    print(f"Remote Policy:   {intel.get('remote_policy')}")
    print(f"Benchmark Comp:  {intel.get('emea_staff_comp_range')}")
    print("-" * 80)
    if "culture_and_wlb" in intel:
        print("Culture & WLB:")
        print(f"  {intel['culture_and_wlb'].get('summary')}")
    if "interview_process" in intel:
        print("\nInterview Pipeline:")
        for s in intel["interview_process"].get("stages", []):
            print(f"  - {s}")
        print("\nInsider Preparation Tip:")
        tip = (
            intel["interview_process"].get("insider_tips")
            or intel["interview_process"].get("candidate_tips")
            or intel["interview_process"].get("interview_tips")
        )
        print(f"  > {tip}")


def cmd_stats(args):
    conn = get_db()
    loc_cfg = get_location_config()
    country_name = loc_cfg["home_country"].capitalize()

    total_active = conn.execute("SELECT count(*) FROM jobs WHERE active = 1").fetchone()[0]
    total_home = conn.execute("SELECT count(*) FROM jobs WHERE active = 1 AND is_home_direct = 1").fetchone()[0]
    total_sal = conn.execute("SELECT count(*) FROM jobs WHERE active = 1 AND salary_norm_max > 0").fetchone()[0]
    high_match = conn.execute("SELECT count(*) FROM jobs WHERE active = 1 AND profile_match_pct >= 75").fetchone()[0]

    print(f"Active tracked jobs in DB: {total_active}")
    print(f"Jobs with direct {country_name} location: {total_home}")
    print(f"Jobs with salary disclosed: {total_sal}")
    print(f"Jobs with >=75% profile match: {high_match}")

    print("\nAvailable Source Plugins:")
    for s in list_sources():
        print(f"  - {s}")

    print("\nAvailable Output Sinks:")
    for s in list_sinks():
        print(f"  - {s}")


def main():
    try:
        _main()
    except ConfigError as e:
        sys.exit(f"[-] Config error: {e}")


def _main():
    parser = argparse.ArgumentParser(description="Job Radar: Modular Systems & Linux Career Engine")
    sub = parser.add_subparsers(dest="command", required=True)

    # sync
    p_sync = sub.add_parser("sync", help="Scrape ATS sources, run pipeline stages, and export to sinks")
    p_sync.add_argument("--min-score", type=int, default=50, help="Minimum score to store (default: 50)")
    p_sync.add_argument("--company", help="Only sync a specific company ID")
    p_sync.add_argument("--sinks", default="db,rss,obsidian", help="Comma-separated sink names (default: db,rss,obsidian)")
    p_sync.add_argument("--notify", action="store_true", help="Dispatch notifications (telegram, desktop)")
    p_sync.add_argument("--force-notify", action="store_true", help="Force notification of all eligible jobs")

    # top
    p_top = sub.add_parser("top", help="Show top scored jobs")
    p_top.add_argument("--min-score", type=int, default=50, help="Minimum score filter")
    p_top.add_argument("--home-only", dest="home_only", action="store_true", help="Only show direct home-country locations")
    p_top.add_argument("--by-salary", action="store_true", help="Sort highest paying jobs first")
    p_top.add_argument("--by-profile", action="store_true", help="Sort highest profile match first")
    p_top.add_argument("--has-salary", action="store_true", help="Only show jobs with salary disclosed")
    p_top.add_argument("--min-salary", type=int, default=0, help="Minimum salary in EUR")
    p_top.add_argument("--min-match", type=int, default=0, help="Minimum profile match percentage (0-100)")
    p_top.add_argument("--company", help="Filter by company ID")
    p_top.add_argument("--limit", type=int, default=25, help="Number of jobs to list")

    # review
    p_rev = sub.add_parser("review", help="Detailed review of top matches with tailored pitches")
    p_rev.add_argument("--min-score", type=int, default=100, help="Minimum score (default: 100)")
    p_rev.add_argument("--limit", type=int, default=10, help="Limit number of roles (default: 10)")

    # status
    p_stat = sub.add_parser("status", help="Update job application status")
    p_stat.add_argument("job_id", help="Job ID or title substring")
    p_stat.add_argument("status", choices=["new", "reviewing", "applied", "interviewing", "offer", "rejected", "archived"])

    # apply
    p_app = sub.add_parser("apply", help="Mark job as applied")
    p_app.add_argument("job_id", help="Job ID or title substring")

    # company
    p_comp = sub.add_parser("company", help="View company dossier")
    p_comp.add_argument("company_id", help="Company ID (e.g. sysdig, datadog, grafanalabs)")

    # stats
    sub.add_parser("stats", help="Database statistics and plugin registry")

    # discover
    p_disc = sub.add_parser("discover", help="Discover peer companies & search CNCF landscape")
    disc_sub = p_disc.add_subparsers(dest="discover_cmd", required=True)

    p_dlist = disc_sub.add_parser("list", help="List curated peer companies")
    p_dlist.add_argument("--category", help="Filter by category")
    p_dlist.add_argument("--tier", help="Filter by tier")
    p_dlist.add_argument("--home-only", action="store_true", help="Only show companies known to hire via EOR")

    p_dadd = disc_sub.add_parser("add", help="Add peer company to tracked targets")
    p_dadd.add_argument("company_id", help="Company ID to add")

    p_dcncf = disc_sub.add_parser("cncf", help="Search CNCF landscape")
    p_dcncf.add_argument("query", help="Keyword (e.g. ebpf, storage, runtime)")
    p_dcncf.add_argument("--limit", type=int, default=20, help="Max results")

    args = parser.parse_args()

    if args.command == "sync":
        cmd_sync(args)
    elif args.command == "top":
        cmd_top(args)
    elif args.command == "review":
        cmd_review(args)
    elif args.command == "status":
        cmd_status(args)
    elif args.command == "apply":
        cmd_apply(args)
    elif args.command == "company":
        cmd_company(args)
    elif args.command == "stats":
        cmd_stats(args)
    elif args.command == "discover":
        if args.discover_cmd == "list":
            list_peers(args.category, args.tier, args.home_only)
        elif args.discover_cmd == "add":
            add_peer(args.company_id)
        elif args.discover_cmd == "cncf":
            query_cncf(args.query, args.limit)


if __name__ == "__main__":
    main()
