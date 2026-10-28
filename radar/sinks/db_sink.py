"""SQLite database sink plugin."""

from typing import Any, Dict, List

from radar.db import get_db, upsert_job
from radar.models import Job
from radar.sinks.base import BaseSink


class DatabaseSink(BaseSink):
    name = "db"

    def export(self, jobs: List[Job], context: Dict[str, Any]):
        conn = context.get("db_conn") or get_db()
        for j in jobs:
            upsert_job(conn, j)
