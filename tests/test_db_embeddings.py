"""Unit tests for SQLite database embedding schema and helper functions."""

import sqlite3
import unittest

from radar.db import (
    deserialize_vector,
    get_db,
    get_pending_embedding_jobs,
    get_profile_embeddings,
    save_job_embedding,
    save_profile_embedding,
    serialize_vector,
    upsert_job,
)
from radar.models import Job, ProfileMatch, SalaryInfo


class TestDbEmbeddings(unittest.TestCase):
    def setUp(self):
        self.conn = get_db(":memory:")

    def tearDown(self):
        self.conn.close()

    def test_vector_serialization_roundtrip(self):
        orig = [0.123456, -0.987654, 0.0, 1.234567, -42.0]
        blob = serialize_vector(orig)
        self.assertIsInstance(blob, bytes)
        self.assertEqual(len(blob), len(orig) * 4)
        restored = deserialize_vector(blob)
        self.assertEqual(len(restored), len(orig))
        for o, r in zip(orig, restored):
            self.assertAlmostEqual(o, r, places=5)

    def test_schema_migration_and_tables(self):
        cols = {r["name"] for r in self.conn.execute("PRAGMA table_info(jobs)")}
        self.assertIn("embedding_status", cols)
        self.assertIn("semantic_score", cols)
        self.assertIn("content", cols)

        tables = {r[0] for r in self.conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
        self.assertIn("job_embeddings", tables)
        self.assertIn("profile_embeddings", tables)

    def test_upsert_job_and_pending_query(self):
        job = Job(
            id="job_1",
            company_id="teleport",
            title="Senior Systems Engineer",
            location="Remote",
            url="https://jobs.example.com/1",
            score=100,
            content="Linux PAM and eBPF security daemon.",
            salary=SalaryInfo(),
            profile=ProfileMatch(match_pct=80, matched_skills=["Linux"], pitch_bullets=["Pitch"]),
            tags=["role:systems"],
        )
        upsert_job(self.conn, job)

        pending = get_pending_embedding_jobs(self.conn, limit=10)
        self.assertEqual(len(pending), 1)
        self.assertEqual(pending[0]["id"], "job_1")
        self.assertEqual(pending[0]["content"], "Linux PAM and eBPF security daemon.")

    def test_save_job_embedding_updates_score_and_tags(self):
        job = Job(
            id="job_2",
            company_id="flyio",
            title="Networking Engineer",
            location="Remote",
            url="https://jobs.example.com/2",
            score=110,
            content="Proxy routing and BGP Anycast.",
            salary=SalaryInfo(),
            profile=ProfileMatch(),
            tags=["role:systems"],
        )
        upsert_job(self.conn, job)

        vec = [0.1, 0.2, 0.3, 0.4]
        save_job_embedding(
            self.conn,
            job_id="job_2",
            model="test-embedding",
            vector=vec,
            semantic_score=25,
            semantic_tag="semantic:networking",
        )

        row = self.conn.execute(
            "SELECT score, semantic_score, tags, embedding_status FROM jobs WHERE id = 'job_2'"
        ).fetchone()
        self.assertEqual(row["score"], 135)
        self.assertEqual(row["semantic_score"], 25)
        self.assertEqual(row["embedding_status"], "done")
        self.assertIn("semantic:networking", row["tags"])

        # Check embedding record
        emb_row = self.conn.execute(
            "SELECT model, dim, vector FROM job_embeddings WHERE job_id = 'job_2'"
        ).fetchone()
        self.assertEqual(emb_row["model"], "test-embedding")
        self.assertEqual(emb_row["dim"], 4)
        for expected_val, actual_val in zip(vec, deserialize_vector(emb_row["vector"])):
            self.assertAlmostEqual(expected_val, actual_val, places=5)

    def test_profile_embeddings_storage_and_retrieval(self):
        save_profile_embedding(
            self.conn,
            pillar_name="eBPF & Dynamic Tracing",
            model="test-model",
            vector=[1.0, 0.0, 0.5],
        )
        save_profile_embedding(
            self.conn,
            pillar_name="OS Reliability",
            model="test-model",
            vector=[0.0, 1.0, 0.5],
        )

        pillars = get_profile_embeddings(self.conn, model="test-model")
        self.assertEqual(len(pillars), 2)
        self.assertIn("eBPF & Dynamic Tracing", pillars)
        self.assertEqual(pillars["eBPF & Dynamic Tracing"], [1.0, 0.0, 0.5])


if __name__ == "__main__":
    unittest.main()
