"""Tests for removal of built-in personal defaults."""

import argparse
import os
import unittest
from unittest.mock import MagicMock, patch

from radar.config import ConfigError, get_location_config, get_salary_expectations
from radar.db import get_db, upsert_job
from radar.models import CompanyTarget, Job, PipelineContext, RawJob
from radar.pipeline.location import LocationStage
from radar.pipeline.salary import SalaryStage


class TestNoBuiltinDefaults(unittest.TestCase):
    def test_missing_country_fails_fast(self):
        with patch.dict(os.environ, {}, clear=True), patch("radar.config.load_profile", return_value={}):
            with self.assertRaises(ConfigError):
                get_location_config()

    def test_unset_salary_tiers_are_not_scored(self):
        with patch("radar.config.load_profile", return_value={}):
            self.assertEqual(get_salary_expectations(), {"high": None, "mid": None, "low": None})
            raw = RawJob(id="s", company_id="t", title="Dev", location="Remote", url="", content="€200,000 - €250,000")
            job = Job(id="s", company_id="t", title="Dev", location="Remote", url="")
            res = SalaryStage().process(raw, job, PipelineContext(target=CompanyTarget(id="t", name="T")))
            self.assertEqual(res.score_delta, 0)

    def test_per_target_allowed_country(self):
        env = {"CANDIDATE_COUNTRY": "Germany", "CANDIDATE_ALLOWED_COUNTRIES": "", "CANDIDATE_REMOTE_ONLY": "false"}
        raw = RawJob(id="v", company_id="t", title="Systems Engineer", location="Vienna, Austria", url="")
        with patch.dict(os.environ, env, clear=True):
            plain = LocationStage().process(raw, Job(id="v", company_id="t", title=raw.title, location=raw.location, url=""),
                                            PipelineContext(target=CompanyTarget(id="t", name="T")))
            extra = LocationStage().process(raw, Job(id="v", company_id="t", title=raw.title, location=raw.location, url=""),
                                            PipelineContext(target=CompanyTarget(id="t", name="T", allowed_countries=["Austria"])))
        self.assertFalse(plain.should_continue)
        self.assertTrue(extra.should_continue)
        self.assertIn("loc:allowed_country", extra.tags)


class TestSyncEmptyFetch(unittest.TestCase):
    def sync_with(self, source):
        from radar import cli

        conn = get_db(":memory:")
        upsert_job(conn, Job(id="j1", company_id="acme", title="SRE", location="Remote", url="u", score=90))
        args = argparse.Namespace(company=None, min_score=0, sinks="", notify=False, force_notify=False)
        with patch.object(cli, "get_db", return_value=conn), \
             patch.object(cli, "load_targets", return_value=[CompanyTarget(id="acme", name="Acme")]), \
             patch.object(cli, "get_source", return_value=source):
            cli.cmd_sync(args)
        return conn.execute("SELECT active FROM jobs WHERE id='j1'").fetchone()[0]

    def test_failed_fetch_keeps_stored_jobs_active(self):
        from radar.http import FetchError

        source = MagicMock()
        source.fetch.side_effect = FetchError("boom")
        self.assertEqual(self.sync_with(source), 1)

    def test_unexpected_source_error_keeps_stored_jobs_active(self):
        source = MagicMock()
        source.fetch.side_effect = KeyError("id")
        self.assertEqual(self.sync_with(source), 1)

    def test_genuinely_empty_board_deactivates_stored_jobs(self):
        source = MagicMock()
        source.fetch.return_value = []
        self.assertEqual(self.sync_with(source), 0)

    def test_sinks_without_db_still_store_jobs_before_other_sinks(self):
        from radar import cli
        from radar.sinks import get_sink as real_get_sink

        conn = get_db(":memory:")
        job = Job(id="j1", company_id="acme", title="SRE", location="Remote", url="u", score=90)
        source = MagicMock()
        source.fetch.return_value = [RawJob(id="j1", company_id="acme", title="SRE", location="Remote", url="u")]
        engine = MagicMock()
        engine.process.return_value = job
        seen = []
        other = MagicMock()
        other.export.side_effect = lambda jobs, ctx: seen.append(
            conn.execute("SELECT active FROM jobs WHERE id='j1'").fetchone()
        )
        args = argparse.Namespace(company=None, min_score=0, sinks="rss", notify=False, force_notify=False)
        with patch.object(cli, "get_db", return_value=conn), \
             patch.object(cli, "load_targets", return_value=[CompanyTarget(id="acme", name="Acme")]), \
             patch.object(cli, "get_source", return_value=source), \
             patch.object(cli, "PipelineEngine", return_value=engine), \
             patch.object(cli, "get_sink", side_effect=lambda n: real_get_sink("db") if n == "db" else other):
            cli.cmd_sync(args)
        self.assertEqual(len(seen), 1)
        self.assertEqual(seen[0][0], 1)  # row already stored and active when rss runs


    def test_snapshot_sinks_get_all_active_jobs_and_others_get_stored_scores(self):
        from radar import cli
        from radar.db import save_job_embedding
        from radar.sinks import get_sink as real_get_sink

        conn = get_db(":memory:")
        upsert_job(conn, Job(id="other1", company_id="other", title="SRE", location="Remote", url="u", score=90))
        fresh = Job(id="j1", company_id="acme", title="SRE", location="Remote", url="u", score=60)
        upsert_job(conn, fresh)
        save_job_embedding(conn, "j1", "m", [0.1], 20, "semantic:foo")  # stored score 80

        source = MagicMock()
        source.fetch.return_value = [RawJob(id="j1", company_id="acme", title="SRE", location="Remote", url="u")]
        engine = MagicMock()
        engine.process.return_value = fresh
        feed, alert = MagicMock(snapshot=True), MagicMock(snapshot=False)
        sinks = {"rss": feed, "telegram": alert}
        args = argparse.Namespace(company="acme", min_score=0, sinks="rss,telegram", notify=False, force_notify=False)
        with patch.object(cli, "get_db", return_value=conn), \
             patch.object(cli, "load_targets", return_value=[CompanyTarget(id="acme", name="Acme")]), \
             patch.object(cli, "get_source", return_value=source), \
             patch.object(cli, "PipelineEngine", return_value=engine), \
             patch.object(cli, "get_sink", side_effect=lambda n: real_get_sink("db") if n == "db" else sinks[n]):
            cli.cmd_sync(args)
        self.assertEqual({j.id for j in feed.export.call_args[0][0]}, {"other1", "j1"})
        alerted = alert.export.call_args[0][0]
        self.assertEqual([(j.id, j.score) for j in alerted], [("j1", 80)])
        self.assertEqual(alert.export.call_args[0][1]["new_job_ids"], set())  # j1 already stored


class TestJobFromRow(unittest.TestCase):
    def test_roundtrip(self):
        from radar.db import job_from_row
        from radar.models import ProfileMatch, SalaryInfo

        conn = get_db(":memory:")
        job = Job(
            id="r1", company_id="c", title="T", location="L", url="u", score=70, tags=["a:b", "c:d"],
            is_home_direct=True, content="body",
            salary=SalaryInfo(min_val=1, max_val=2, currency="EUR", display="1-2", norm_max_eur=2),
            profile=ProfileMatch(match_pct=50, matched_skills=["x", "y"], pitch_bullets=["p1", "p2"]),
        )
        upsert_job(conn, job)
        got = job_from_row(dict(conn.execute("SELECT * FROM jobs WHERE id='r1'").fetchone()))
        for f in ("id", "company_id", "title", "location", "url", "score", "tags", "is_home_direct", "salary", "profile", "content"):
            self.assertEqual(getattr(got, f), getattr(job, f), f)


if __name__ == "__main__":
    unittest.main()


class TestCliDispatch(unittest.TestCase):
    def run_cli(self, *argv):
        import sys
        from radar import cli

        conn = get_db(":memory:")
        with patch.object(sys, "argv", ["radar", *argv]), patch.object(cli, "get_db", return_value=conn), \
             patch.object(cli, "update_job_status", return_value="Acme: SRE") as upd:
            cli.main()
        return upd

    def test_apply_is_status_applied(self):
        self.assertEqual(self.run_cli("apply", "sre").call_args[0][1:], ("sre", "applied"))

    def test_status_passes_through(self):
        self.assertEqual(self.run_cli("status", "sre", "offer").call_args[0][1:], ("sre", "offer"))


class TestScoreThresholds(unittest.TestCase):
    def run_sync(self, **kw):
        from radar import cli

        conn = get_db(":memory:")
        job = Job(id="j1", company_id="acme", title="SRE", location="Remote", url="u", score=60)
        source = MagicMock()
        source.fetch.return_value = [RawJob(id="j1", company_id="acme", title="SRE", location="Remote", url="u")]
        engine = MagicMock()
        engine.process.return_value = job
        alert = MagicMock(snapshot=False)
        args = argparse.Namespace(company=None, min_score=50, sinks="", notify=False, force_notify=False, **kw)
        real = cli.get_sink
        with patch.object(cli, "get_db", return_value=conn), \
             patch.object(cli, "load_targets", return_value=[CompanyTarget(id="acme", name="Acme")]), \
             patch.object(cli, "get_source", return_value=source), patch.object(cli, "PipelineEngine", return_value=engine), \
             patch.object(cli, "get_sink", side_effect=lambda n: real("db") if n == "db" else alert):
            args.sinks = "telegram"
            cli.cmd_sync(args)
        stored = conn.execute("SELECT count(*) FROM jobs").fetchone()[0]
        return stored, alert.export.call_args[0][1]["min_score"]

    def test_store_and_notify_thresholds_are_independent(self):
        self.assertEqual(self.run_sync(notify_min_score=70), (1, 70))  # stored at 60 though notify bar is 70
        self.assertEqual(self.run_sync(notify_min_score=None), (1, None))  # sink falls back to its config
