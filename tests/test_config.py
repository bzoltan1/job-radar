"""Tests for decoupled configuration loaders, environment variable resolution, and bugfixes."""

import os
import unittest
from unittest.mock import patch

from radar.config import (
    get_candidate_info,
    get_location_config,
    get_obsidian_vault_path,
    get_salary_expectations,
    get_telegram_config,
    load_dotenv_if_present,
    load_profile,
)
from radar.db import get_db
from radar.models import CompanyTarget, Job, PipelineContext, RawJob
from radar.pipeline.freshness import FreshnessStage
from radar.pipeline.location import LocationStage
from radar.pipeline.profile import evaluate_profile


class TestConfigAndEnvironment(unittest.TestCase):
    def test_telegram_creds_no_hardcoded_chat_id(self):
        with patch.dict(os.environ, {}, clear=True):
            with patch("radar.config.load_settings", return_value={}):
                cfg = get_telegram_config()
                self.assertIsNone(cfg.get("chat_id"))

    def test_telegram_creds_from_env(self):
        env_vars = {
            "TELEGRAM_BOT_TOKEN": "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11",
            "TELEGRAM_CHAT_ID": "987654321",
            "JOB_RADAR_NOTIFY_MIN_SCORE": "90",
            "JOB_RADAR_NOTIFY_MIN_SALARY": "140000",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            cfg = get_telegram_config()
            self.assertEqual(cfg["bot_token"], "123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11")
            self.assertEqual(cfg["chat_id"], 987654321)
            self.assertEqual(cfg["min_score"], 90)
            self.assertEqual(cfg["min_salary"], 140000)

    def test_obsidian_vault_path_env_override(self):
        custom_path = "/tmp/my_custom_vault"
        with patch.dict(os.environ, {"OBSIDIAN_VAULT_PATH": custom_path}, clear=True):
            resolved = get_obsidian_vault_path()
            self.assertEqual(resolved, custom_path)

    def test_candidate_info_defaults(self):
        cand = get_candidate_info()
        self.assertIn("name", cand)
        self.assertIn("headline", cand)
        self.assertIn("location", cand)
        self.assertTrue(cand["name"])

    def test_salary_expectations_tiers(self):
        tiers = get_salary_expectations()
        self.assertIn("high", tiers)
        self.assertIn("mid", tiers)
        self.assertIn("low", tiers)
        self.assertGreater(tiers["high"], tiers["low"])

    def test_evaluate_profile_pitch_bullets_generic(self):
        res = evaluate_profile("eBPF Kernel Engineer", "Working on Linux kernel tracing and uprobes.")
        self.assertGreater(res.match_pct, 0)
        self.assertTrue(len(res.pitch_bullets) > 0)
        for b in res.pitch_bullets:
            self.assertIsInstance(b, str)

    def test_location_config_from_env(self):
        env_vars = {
            "CANDIDATE_COUNTRY": "Germany",
            "CANDIDATE_ALLOWED_COUNTRIES": "Austria, Switzerland",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            loc_cfg = get_location_config()
            self.assertEqual(loc_cfg["home_country"], "Germany")
            self.assertEqual(loc_cfg["allowed_countries"], ["Austria", "Switzerland"])

    def test_location_stage_with_custom_country(self):
        env_vars = {
            "CANDIDATE_COUNTRY": "Germany",
            "CANDIDATE_ALLOWED_COUNTRIES": "Austria",
        }
        with patch.dict(os.environ, env_vars, clear=True):
            stage = LocationStage()
            target = CompanyTarget(id="testcomp", name="Test Comp")
            ctx = PipelineContext(target=target)

            raw_de = RawJob(id="1", company_id="testcomp", title="Systems Engineer", location="Berlin, Germany", url="")
            job_de = Job(id="1", company_id="testcomp", title="Systems Engineer", location="Berlin, Germany", url="")
            res_de = stage.process(raw_de, job_de, ctx)
            self.assertTrue(res_de.should_continue)
            self.assertEqual(res_de.score_delta, 25)
            self.assertIn("loc:home_country", res_de.tags)
            self.assertTrue(job_de.is_home_direct)

            raw_uk = RawJob(id="2", company_id="testcomp", title="Systems Engineer (UK only)", location="London, UK", url="")
            job_uk = Job(id="2", company_id="testcomp", title="Systems Engineer (UK only)", location="London, UK", url="")
            res_uk = stage.process(raw_uk, job_uk, ctx)
            self.assertTrue(res_uk.should_continue)
            self.assertEqual(res_uk.score_delta, -40)
            self.assertIn("loc:foreign_restriction(-40)", res_uk.tags)

    def test_location_no_false_positive_on_common_words(self):
        stage = LocationStage()
        target = CompanyTarget(id="testcomp", name="Test Comp")
        ctx = PipelineContext(target=target)

        # "status", "focus", "bonus" contain "us" as substring, but must NOT trigger US foreign lock
        raw = RawJob(
            id="status1",
            company_id="testcomp",
            title="Status Monitoring Platform Engineer (EMEA Remote)",
            location="Remote, Europe",
            url="",
        )
        job = Job(id="status1", company_id="testcomp", title=raw.title, location=raw.location, url="")
        res = stage.process(raw, job, ctx)
        self.assertTrue(res.should_continue)
        self.assertNotIn("loc:foreign_restriction(-40)", res.tags)
        self.assertNotIn("loc:foreign_restriction(-40)", res.tags)
        self.assertEqual(res.score_delta, 10)  # emea_remote bonus

    def test_freshness_unparseable_date_is_neutral(self):
        stage = FreshnessStage()
        raw = RawJob(id="f1", company_id="testcomp", title="Systems Engineer", location="Remote", url="", posted_date="invalid-date")
        job = Job(id="f1", company_id="testcomp", title=raw.title, location=raw.location, url="")
        ctx = PipelineContext(target=CompanyTarget(id="testcomp", name="Test Comp"), first_seen=None)
        res = stage.process(raw, job, ctx)
        self.assertTrue(res.should_continue)
        self.assertEqual(res.score_delta, 0)
        self.assertNotIn("age:fresh(<7d)", res.tags)

    def test_db_schema_indexes_exist(self):
        conn = get_db(":memory:")
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='index'").fetchall()
        index_names = {r["name"] for r in rows}
        self.assertIn("idx_jobs_active_score", index_names)
        self.assertIn("idx_jobs_company", index_names)
        self.assertIn("idx_jobs_salary", index_names)


if __name__ == "__main__":
    unittest.main()
