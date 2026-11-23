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
    def test_empty_fetch_keeps_stored_jobs_active(self):
        from radar import cli

        conn = get_db(":memory:")
        upsert_job(conn, Job(id="j1", company_id="acme", title="SRE", location="Remote", url="u", score=90))
        source = MagicMock()
        source.fetch.return_value = []
        args = argparse.Namespace(company=None, min_score=0, sinks="", notify=False, force_notify=False)
        with patch.object(cli, "get_db", return_value=conn), \
             patch.object(cli, "load_targets", return_value=[CompanyTarget(id="acme", name="Acme")]), \
             patch.object(cli, "get_source", return_value=source):
            cli.cmd_sync(args)
        self.assertEqual(conn.execute("SELECT active FROM jobs WHERE id='j1'").fetchone()[0], 1)


if __name__ == "__main__":
    unittest.main()
