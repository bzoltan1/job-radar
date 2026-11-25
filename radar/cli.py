"""Unified modern CLI for Job Radar."""

import argparse
import os
import sys

from radar.config import (
    ConfigError,
    get_location_config,
    load_all_intel,
    load_company_intel,
    load_profile,
    load_targets,
)
from radar.db import (
    VALID_STATUSES,
    apply_stored_scores,
    deactivate_company_jobs,
    get_active_jobs,
    get_db,
    get_existing_first_seen,
    get_pending_embedding_jobs,
    job_from_row,
    save_job_embedding,
    update_job_status,
)
from radar.discovery import add_peer, list_peers, query_cncf
from radar.models import PipelineContext
from radar.pipeline.engine import PipelineEngine
from radar.semantic import (
    ensure_profile_embeddings,
    evaluate_semantic_match,
    get_embedding_provider,
)
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
    new_job_ids = set()

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
                if raw_job.id not in existing_first_seen:
                    new_job_ids.add(job.id)

        print(f"  + {target.name:<24} | Found: {len(raw_jobs):<4} | Matched: {target_matched}")

    # Dispatch to Sinks
    # db always runs first: jobs were deactivated above and only upsert_job re-activates them,
    # and later sinks (telegram dedup via notified_at) read the stored rows.
    sink_names = ["db"] + [n for n in (s.strip().lower() for s in args.sinks.split(",")) if n and n != "db"]
    if args.notify:
        if "telegram" not in sink_names:
            sink_names.append("telegram")
        if "desktop" not in sink_names:
            sink_names.append("desktop")

    sink_context = {
        "db_conn": conn,
        "min_score": args.min_score,
        "force_notify": getattr(args, "force_notify", False),
        "new_job_ids": new_job_ids,
    }

    snapshot_jobs = all_processed_jobs
    for s_name in sink_names:
        sink = get_sink(s_name)
        if not sink:
            print(f"[-] Warning: Sink '{s_name}' not found.", file=sys.stderr)
            continue
        sink.export(snapshot_jobs if sink.snapshot else all_processed_jobs, sink_context)
        if s_name == "db":
            # Later sinks see stored scores (incl. semantic bonus); snapshot sinks see every active
            # job, so a partial sync (--company) or a failed fetch doesn't shrink the feed/vault.
            apply_stored_scores(conn, all_processed_jobs)
            snapshot_jobs = [job_from_row(r) for r in get_active_jobs(conn, min_score=args.min_score)]

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


def cmd_embed(args):
    """Process pending job embeddings locally and score semantic similarity."""
    conn = get_db()
    profile = load_profile()
    provider = get_embedding_provider()

    profile_embeddings = ensure_profile_embeddings(conn, profile, provider, force=args.reindex_profile)
    is_dense = False  # Local subword feature hashing model

    pending = get_pending_embedding_jobs(conn, limit=args.batch_size)
    if not pending:
        print("[*] No jobs pending semantic embedding.")
        return

    print(f"[*] Processing {len(pending)} jobs locally using {provider.model_name}...")
    texts = [f"{j['title']}\n{j.get('content', '')[:1500]}" for j in pending]
    vectors = provider.embed_texts(texts)

    updated = 0
    scored = 0
    for job, vec in zip(pending, vectors):
        pillar, sim, bonus, tag = evaluate_semantic_match(vec, profile_embeddings, is_dense_model=is_dense)
        save_job_embedding(conn, job["id"], provider.model_name, vec, bonus, tag)
        updated += 1
        if bonus > 0:
            scored += 1
            print(f"  + {job['company_id'].capitalize()}: {job['title'][:40]} -> {pillar} (sim: {sim:.2f}, +{bonus} pts)")

    print(f"[+] Local semantic processing complete. Embedded: {updated}, Matched bonus: {scored}.")


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
    p_sync.set_defaults(func=cmd_sync)
    p_sync.add_argument("--min-score", type=int, default=50, help="Minimum score to store (default: 50)")
    p_sync.add_argument("--company", help="Only sync a specific company ID")
    p_sync.add_argument("--sinks", default="db,rss,obsidian", help="Comma-separated sink names; db always runs (default: db,rss,obsidian)")
    p_sync.add_argument("--notify", action="store_true", help="Dispatch notifications (telegram, desktop)")
    p_sync.add_argument("--force-notify", action="store_true", help="Force notification of all eligible jobs")

    # top
    p_top = sub.add_parser("top", help="Show top scored jobs")
    p_top.set_defaults(func=cmd_top)
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
    p_rev.set_defaults(func=cmd_review)
    p_rev.add_argument("--min-score", type=int, default=100, help="Minimum score (default: 100)")
    p_rev.add_argument("--limit", type=int, default=10, help="Limit number of roles (default: 10)")

    # status
    p_stat = sub.add_parser("status", help="Update job application status")
    p_stat.set_defaults(func=cmd_status)
    p_stat.add_argument("job_id", help="Job ID or title substring")
    p_stat.add_argument("status", choices=VALID_STATUSES)

    # apply
    p_app = sub.add_parser("apply", help="Mark job as applied (alias for: status <job> applied)")
    p_app.add_argument("job_id", help="Job ID or title substring")
    p_app.set_defaults(func=cmd_status, status="applied")

    # company
    p_comp = sub.add_parser("company", help="View company dossier")
    p_comp.set_defaults(func=cmd_company)
    p_comp.add_argument("company_id", help="Company ID (e.g. sysdig, datadog, grafanalabs)")

    # stats
    sub.add_parser("stats", help="Database statistics and plugin registry").set_defaults(func=cmd_stats)

    # embed
    p_emb = sub.add_parser("embed", help="Run offline local semantic embedding and similarity scoring")
    p_emb.set_defaults(func=cmd_embed)
    p_emb.add_argument("--batch-size", type=int, default=100, help="Number of pending jobs to process (default: 100)")
    p_emb.add_argument("--reindex-profile", action="store_true", help="Force recomputing profile pillar embeddings")

    # discover
    p_disc = sub.add_parser("discover", help="Discover peer companies & search CNCF landscape")
    disc_sub = p_disc.add_subparsers(dest="discover_cmd", required=True)

    p_dlist = disc_sub.add_parser("list", help="List curated peer companies")
    p_dlist.add_argument("--category", help="Filter by category")
    p_dlist.add_argument("--tier", help="Filter by tier")
    p_dlist.add_argument("--home-only", action="store_true", help="Only show companies known to hire via EOR")
    p_dlist.set_defaults(func=lambda a: list_peers(a.category, a.tier, a.home_only))

    p_dadd = disc_sub.add_parser("add", help="Add peer company to tracked targets")
    p_dadd.add_argument("company_id", help="Company ID to add")
    p_dadd.set_defaults(func=lambda a: add_peer(a.company_id))

    p_dcncf = disc_sub.add_parser("cncf", help="Search CNCF landscape")
    p_dcncf.add_argument("query", help="Keyword (e.g. ebpf, storage, runtime)")
    p_dcncf.add_argument("--limit", type=int, default=20, help="Max results")
    p_dcncf.set_defaults(func=lambda a: query_cncf(a.query, a.limit))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
