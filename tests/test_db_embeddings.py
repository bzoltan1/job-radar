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

    def test_upsert_keeps_semantic_bonus(self):
        job = Job(
            id="job_3", company_id="c", title="T", location="Remote",
            url="u", score=80, content="x", salary=SalaryInfo(),
            profile=ProfileMatch(), tags=["role:systems"],
        )
        upsert_job(self.conn, job)
        save_job_embedding(self.conn, "job_3", "m", [0.1], 20, "semantic:foo")
        upsert_job(self.conn, job)
        upsert_job(self.conn, job)  # idempotent: bonus must not accumulate
        row = self.conn.execute(
            "SELECT score, semantic_score, embedding_status, tags FROM jobs WHERE id='job_3'"
        ).fetchone()
        self.assertEqual((row["score"], row["semantic_score"], row["embedding_status"]), (100, 20, "done"))
        self.assertEqual(row["tags"], "role:systems;semantic:foo")

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


class TestProfilePillarSync(unittest.TestCase):
    def setUp(self):
        from radar.semantic import LocalHashedEmbeddingProvider

        self.conn = get_db(":memory:")
        self.provider = LocalHashedEmbeddingProvider()
        job = Job(id="j", company_id="c", title="T", location="L", url="u", score=50)
        upsert_job(self.conn, job)
        save_job_embedding(self.conn, "j", self.provider.model_name, [0.1], 10, "semantic:x")

    def status(self):
        return self.conn.execute("SELECT embedding_status FROM jobs WHERE id='j'").fetchone()[0]

    def test_removed_changed_and_unchanged_pillars(self):
        from radar.semantic import ensure_profile_embeddings

        a = {"category": "Kernel", "description": "drivers", "keywords": ["linux"]}
        b = {"category": "Cloud", "description": "k8s", "keywords": ["docker"]}
        emb = ensure_profile_embeddings(self.conn, {"deep_domain_expertise": [a, b]}, self.provider)
        self.assertEqual(set(emb), {"Kernel", "Cloud"})
        self.assertEqual(self.status(), "pending")  # first build re-queues

        save_job_embedding(self.conn, "j", self.provider.model_name, [0.1], 10, "semantic:x")
        ensure_profile_embeddings(self.conn, {"deep_domain_expertise": [a, b]}, self.provider)
        self.assertEqual(self.status(), "done")  # unchanged profile: no churn

        a2 = dict(a, description="completely different text")
        emb = ensure_profile_embeddings(self.conn, {"deep_domain_expertise": [a2, b]}, self.provider)
        self.assertEqual(self.status(), "pending")  # edited pillar re-embedded
        self.assertNotEqual(emb["Kernel"], ensure_profile_embeddings(
            self.conn, {"deep_domain_expertise": [a, b]}, self.provider)["Kernel"])

        save_job_embedding(self.conn, "j", self.provider.model_name, [0.1], 10, "semantic:x")
        emb = ensure_profile_embeddings(self.conn, {"deep_domain_expertise": [b]}, self.provider)
        self.assertEqual(set(emb), {"Cloud"})  # removed pillar gone from result...
        self.assertEqual(set(get_profile_embeddings(self.conn, self.provider.model_name)), {"Cloud"})  # ...and cache
        self.assertEqual(self.status(), "pending")

    def test_no_category_is_cached_under_default(self):
        from radar.semantic import ensure_profile_embeddings

        profile = {"deep_domain_expertise": [{"description": "x"}]}
        self.assertEqual(set(ensure_profile_embeddings(self.conn, profile, self.provider)), {"General Systems"})
        save_job_embedding(self.conn, "j", self.provider.model_name, [0.1], 10, "semantic:x")
        ensure_profile_embeddings(self.conn, profile, self.provider)
        self.assertEqual(self.status(), "done")  # not re-embedded every run


class TestUpsertAndStatus(unittest.TestCase):
    def setUp(self):
        self.conn = get_db(":memory:")

    def job(self, jid, title, score=50, first_seen=None, active=True):
        j = Job(id=jid, company_id="acme", title=title, location="L", url="u", score=score, first_seen=first_seen)
        upsert_job(self.conn, j)
        if not active:
            self.conn.execute("UPDATE jobs SET active=0 WHERE id=?", (jid,))
        return j

    def test_first_seen_is_kept_and_only_moves_earlier(self):
        self.job("a", "T", first_seen="2024-01-01 00:00:00")
        self.job("a", "T")  # no date: keep stored
        self.job("a", "T", first_seen="2024-06-01 00:00:00")  # later: keep stored
        fs = lambda: self.conn.execute("SELECT first_seen FROM jobs WHERE id='a'").fetchone()[0]
        self.assertEqual(fs(), "2024-01-01 00:00:00")
        self.job("a", "T", first_seen="2023-05-05 00:00:00")  # earlier posting date wins
        self.assertEqual(fs(), "2023-05-05 00:00:00")

    def test_new_job_without_date_gets_now(self):
        self.job("b", "T")
        self.assertIsNotNone(self.conn.execute("SELECT first_seen FROM jobs WHERE id='b'").fetchone()[0])

    def test_status_prefers_exact_id_then_active_best_score_and_escapes_wildcards(self):
        from radar.db import update_job_status

        self.job("low", "Senior SRE", score=10)
        self.job("high", "Senior SRE II", score=90)
        self.job("dead", "Senior SRE III", score=99, active=False)
        self.job("pct", "100% Remote")
        self.job("other", "Platform")
        update_job_status(self.conn, "SRE", "applied")
        st = lambda i: self.conn.execute("SELECT status FROM jobs WHERE id=?", (i,)).fetchone()[0]
        self.assertEqual((st("high"), st("low"), st("dead")), ("applied", "new", "new"))
        update_job_status(self.conn, "low", "rejected")  # exact id beats title matches
        self.assertEqual(st("low"), "rejected")
        update_job_status(self.conn, "%", "offer")  # literal %, not a wildcard
        self.assertEqual((st("pct"), st("other")), ("offer", "new"))
