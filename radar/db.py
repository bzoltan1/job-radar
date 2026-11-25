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
        if "embedding_status" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN embedding_status TEXT DEFAULT 'pending'")
        if "semantic_score" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN semantic_score INTEGER DEFAULT 0")
        if "content" not in cols:
            conn.execute("ALTER TABLE jobs ADD COLUMN content TEXT DEFAULT ''")

        conn.execute("""
            CREATE TABLE IF NOT EXISTS job_embeddings (
                job_id TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector BLOB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY(job_id) REFERENCES jobs(id)
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS profile_embeddings (
                pillar_name TEXT PRIMARY KEY,
                model TEXT NOT NULL,
                dim INTEGER NOT NULL,
                vector BLOB NOT NULL,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        """)

        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_active_score ON jobs(active, score DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_company ON jobs(company_id)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_salary ON jobs(salary_norm_max DESC)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_embedding ON jobs(embedding_status)")
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
    # Carry over the semantic bonus/tag from `radar embed`: the pipeline score excludes it.
    prev = conn.execute("SELECT semantic_score, tags FROM jobs WHERE id = ?", (job.id,)).fetchone()
    sem_score = (prev["semantic_score"] or 0) if prev else 0
    sem_tags = [t for t in (prev["tags"] or "").split(";") if t.startswith("semantic:")] if prev else []
    score = job.score + sem_score
    tags_str = ";".join([*job.tags, *sem_tags])
    matched_skills_str = ", ".join(job.profile.matched_skills)
    pitch_str = "\n".join(job.profile.pitch_bullets)
    content_str = (job.content or "")[:4000]

    with conn:
        if job.first_seen:
            conn.execute(
                """
                INSERT INTO jobs (
                    id, company_id, title, location, is_home_direct, is_emea_remote,
                    score, url, tags, salary_min, salary_max, salary_currency,
                    salary_display, salary_norm_max, profile_match_pct, matched_skills,
                    pitch_bullets, content, first_seen, last_seen, active
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 1)
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
                    content=excluded.content,
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
                    score,
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
                    content_str,
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
                    pitch_bullets, content, last_seen, active
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
                    content=excluded.content,
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
                    score,
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
                    content_str,
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


def serialize_vector(vec: List[float]) -> bytes:
    """Pack float array into binary float32 buffer."""
    import struct
    return struct.pack(f"{len(vec)}f", *vec)


def deserialize_vector(data: bytes) -> List[float]:
    """Unpack binary float32 buffer into float list."""
    import struct
    count = len(data) // 4
    return list(struct.unpack(f"{count}f", data))


def get_pending_embedding_jobs(conn: sqlite3.Connection, limit: int = 50) -> List[Dict[str, Any]]:
    """Retrieve active jobs pending semantic embedding."""
    rows = conn.execute(
        """
        SELECT id, company_id, title, location, score, tags, content
        FROM jobs
        WHERE active = 1 AND (embedding_status = 'pending' OR embedding_status IS NULL)
        ORDER BY score DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def save_job_embedding(
    conn: sqlite3.Connection,
    job_id: str,
    model: str,
    vector: List[float],
    semantic_score: int,
    semantic_tag: Optional[str] = None,
):
    """Save raw vector embedding and update job semantic score and tags."""
    blob = serialize_vector(vector)
    dim = len(vector)
    with conn:
        conn.execute(
            """
            INSERT INTO job_embeddings (job_id, model, dim, vector, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(job_id) DO UPDATE SET
                model = excluded.model,
                dim = excluded.dim,
                vector = excluded.vector,
                updated_at = CURRENT_TIMESTAMP
            """,
            (job_id, model, dim, blob),
        )

        row = conn.execute(
            "SELECT score, tags, semantic_score FROM jobs WHERE id = ?",
            (job_id,),
        ).fetchone()
        if row:
            old_sem = row["semantic_score"] or 0
            base_score = (row["score"] or 0) - old_sem
            new_score = base_score + semantic_score
            tags = [t.strip() for t in (row["tags"] or "").split(";") if t.strip()]
            tags = [t for t in tags if not t.startswith("semantic:")]
            if semantic_tag:
                tags.append(semantic_tag)
            tags_str = ";".join(tags)

            conn.execute(
                """
                UPDATE jobs
                SET score = ?,
                    semantic_score = ?,
                    tags = ?,
                    embedding_status = 'done'
                WHERE id = ?
                """,
                (new_score, semantic_score, tags_str, job_id),
            )


def save_profile_embedding(
    conn: sqlite3.Connection,
    pillar_name: str,
    model: str,
    vector: List[float],
):
    """Save reference embedding for a profile domain pillar."""
    blob = serialize_vector(vector)
    dim = len(vector)
    with conn:
        conn.execute(
            """
            INSERT INTO profile_embeddings (pillar_name, model, dim, vector, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(pillar_name) DO UPDATE SET
                model = excluded.model,
                dim = excluded.dim,
                vector = excluded.vector,
                updated_at = CURRENT_TIMESTAMP
            """,
            (pillar_name, model, dim, blob),
        )


def get_profile_embeddings(conn: sqlite3.Connection, model: str) -> Dict[str, List[float]]:
    """Retrieve all cached profile pillar embeddings for a specific model."""
    rows = conn.execute(
        "SELECT pillar_name, vector FROM profile_embeddings WHERE model = ?",
        (model,),
    ).fetchall()
    return {r["pillar_name"]: deserialize_vector(r["vector"]) for r in rows}

