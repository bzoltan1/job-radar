"""SQLite Database interface and storage operations for Job Radar."""

import sqlite3
from typing import Any, Dict, List, Optional

from radar.config import DB_PATH
from radar.models import Job, ProfileMatch, SalaryInfo

VALID_STATUSES = ["new", "reviewing", "applied", "interviewing", "offer", "rejected", "archived"]


def get_db(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Connect to SQLite database and ensure schema is migrated."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    with conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                company_id TEXT,
                title TEXT,
                location TEXT,
                is_home_direct INTEGER,
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
                active INTEGER DEFAULT 1,
                notified_at TIMESTAMP DEFAULT NULL,
                status TEXT DEFAULT 'new'
            )
        """)
        cols = {r["name"] for r in conn.execute("PRAGMA table_info(jobs)")}
        for legacy in ("is_italy_direct", "is_local_direct"):  # legacy column names
            if legacy in cols:
                conn.execute(f"ALTER TABLE jobs RENAME COLUMN {legacy} TO is_home_direct")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_active_score ON jobs(active, score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_salary ON jobs(salary_norm_max DESC)")
    return conn


def get_existing_first_seen(conn: sqlite3.Connection, company_id: str) -> Dict[str, str]:
    """Retrieve existing first_seen dates for deduplication and freshness tracking."""
    rows = conn.execute(
        "SELECT id, first_seen FROM jobs WHERE company_id = ?", (company_id,)
    ).fetchall()
    return {r["id"]: r["first_seen"] for r in rows}


def deactivate_company_jobs(conn: sqlite3.Connection, company_id: str):
    """Mark all jobs for a company as inactive before sync."""
    with conn:
        conn.execute("UPDATE jobs SET active = 0 WHERE company_id = ?", (company_id,))


def upsert_job(conn: sqlite3.Connection, job: Job):
    """Insert or update a single processed job."""
    tags_str = ";".join(job.tags)
    matched_skills_str = ", ".join(job.profile.matched_skills)
    pitch_str = "\n".join(job.profile.pitch_bullets)

    with conn:
        if job.first_seen:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, company_id, title, location, is_home_direct, is_emea_remote,
                    score, url, tags, salary_min, salary_max, salary_currency,
                    salary_display, salary_norm_max, profile_match_pct, matched_skills,
                    pitch_bullets, first_seen, last_seen, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    location=excluded.location,
                    is_home_direct=excluded.is_home_direct,
                    is_emea_remote=excluded.is_emea_remote,
                    score=excluded.score,
                    tags=excluded.tags,
                    salary_min=excluded.salary_min,
                    salary_max=excluded.salary_max,
                    salary_currency=excluded.salary_currency,
                    salary_display=excluded.salary_display,
                    salary_norm_max=excluded.salary_norm_max,
                    profile_match_pct=excluded.profile_match_pct,
                    matched_skills=excluded.matched_skills,
                    pitch_bullets=excluded.pitch_bullets,
                    first_seen=MIN(jobs.first_seen, excluded.first_seen),
                    last_seen=CURRENT_TIMESTAMP,
                    active=1
                """,
                (
                    job.id,
                    job.company_id,
                    job.title,
                    job.location,
                    int(job.is_home_direct),
                    int(job.is_emea_remote),
                    job.score,
                    job.url,
                    tags_str,
                    job.salary.min_val,
                    job.salary.max_val,
                    job.salary.currency,
                    job.salary.display,
                    job.salary.norm_max_eur,
                    job.profile.match_pct,
                    matched_skills_str,
                    pitch_str,
                    job.first_seen,
                ),
            )
        else:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, company_id, title, location, is_home_direct, is_emea_remote,
                    score, url, tags, salary_min, salary_max, salary_currency,
                    salary_display, salary_norm_max, profile_match_pct, matched_skills,
                    pitch_bullets, last_seen, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
                ON CONFLICT(id) DO UPDATE SET
                    title=excluded.title,
                    location=excluded.location,
                    is_home_direct=excluded.is_home_direct,
                    is_emea_remote=excluded.is_emea_remote,
                    score=excluded.score,
                    tags=excluded.tags,
                    salary_min=excluded.salary_min,
                    salary_max=excluded.salary_max,
                    salary_currency=excluded.salary_currency,
                    salary_display=excluded.salary_display,
                    salary_norm_max=excluded.salary_norm_max,
                    profile_match_pct=excluded.profile_match_pct,
                    matched_skills=excluded.matched_skills,
                    pitch_bullets=excluded.pitch_bullets,
                    last_seen=CURRENT_TIMESTAMP,
                    active=1
                """,
                (
                    job.id,
                    job.company_id,
                    job.title,
                    job.location,
                    int(job.is_home_direct),
                    int(job.is_emea_remote),
                    job.score,
                    job.url,
                    tags_str,
                    job.salary.min_val,
                    job.salary.max_val,
                    job.salary.currency,
                    job.salary.display,
                    job.salary.norm_max_eur,
                    job.profile.match_pct,
                    matched_skills_str,
                    pitch_str,
                ),
            )


def get_active_jobs(
    conn: sqlite3.Connection,
    min_score: int = 0,
    home_only: bool = False,
    by_salary: bool = False,
    by_profile: bool = False,
    has_salary: bool = False,
    min_salary: int = 0,
    min_match: int = 0,
    company_id: Optional[str] = None,
    limit: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Query active jobs from the database with flexible filtering."""
    query = "SELECT * FROM jobs WHERE active = 1"
    params = []

    if min_score > 0:
        query += " AND score >= ?"
        params.append(min_score)

    if home_only:
        query += " AND is_home_direct = 1"

    if has_salary:
        query += " AND salary_norm_max > 0"

    if min_salary > 0:
        query += " AND salary_norm_max >= ?"
        params.append(min_salary)

    if min_match > 0:
        query += " AND profile_match_pct >= ?"
        params.append(min_match)

    if company_id:
        query += " AND company_id = ?"
        params.append(company_id)

    if by_salary:
        query += " ORDER BY salary_norm_max DESC, score DESC"
    elif by_profile:
        query += " ORDER BY profile_match_pct DESC, score DESC"
    else:
        query += " ORDER BY score DESC, salary_norm_max DESC"

    if limit:
        query += " LIMIT ?"
        params.append(limit)

    rows = conn.execute(query, params).fetchall()
    return [dict(r) for r in rows]


def update_job_status(conn: sqlite3.Connection, job_id_query: str, new_status: str) -> Optional[str]:
    """Find a job by ID or title substring and update status."""
    row = conn.execute(
        "SELECT id, title, company_id, status FROM jobs WHERE id = ? OR title LIKE ? LIMIT 1",
        (job_id_query, f"%{job_id_query}%"),
    ).fetchone()

    if not row:
        return None

    jid = row["id"]
    with conn:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (new_status, jid))
    return f"{row['company_id'].capitalize()}: {row['title']} -> {new_status}"


def mark_notified(conn: sqlite3.Connection, job_ids: List[str]):
    """Mark jobs as notified with current timestamp."""
    with conn:
        conn.executemany(
            "UPDATE jobs SET notified_at = CURRENT_TIMESTAMP WHERE id = ?",
            [(jid,) for jid in job_ids],
        )
