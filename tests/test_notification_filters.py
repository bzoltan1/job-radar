"""Tests for sink notification suppression on foreign EU single-country remote roles."""

import unittest
from unittest.mock import MagicMock, patch

from radar.models import Job, ProfileMatch, SalaryInfo
from radar.sinks.desktop_sink import DesktopSink
from radar.sinks.telegram_sink import TelegramSink
from telegram_notify import notify_new_jobs


def make_dummy_job(job_id: str, score: int, tags: list, title: str = "Senior Systems Engineer", location: str = "Remote, United Kingdom") -> Job:
    job = Job(
        id=job_id,
        company_id="gitlab",
        title=title,
        location=location,
        url=f"https://example.com/jobs/{job_id}",
        score=score,
        tags=tags,
    )
    job.salary = SalaryInfo()
    job.profile = ProfileMatch(match_pct=90, matched_skills=["Linux", "eBPF"])
    return job


class TestNotificationSinks(unittest.TestCase):
    @patch("radar.sinks.telegram_sink.send_telegram_message")
    def test_telegram_sink_filters_foreign_restriction(self, mock_send):
        mock_send.return_value = True
        sink = TelegramSink()

        job_uk = make_dummy_job("j1", 80, ["loc:foreign_restriction(-40)", "role:systems"], title="UK Only Role")
        job_it = make_dummy_job("j2", 80, ["loc:home_country", "role:systems"], title="Italy Remote Role")

        ctx = {"min_score": 70, "force_notify": True}
        sink.export([job_uk, job_it], ctx)

        self.assertTrue(mock_send.called)
        call_arg = mock_send.call_args[0][0]
        self.assertIn("Italy Remote Role", call_arg)
        self.assertNotIn("UK Only Role", call_arg)
        self.assertIn("Job Radar: 1 New Top Matches", call_arg)

    @patch("radar.sinks.telegram_sink.send_telegram_message")
    def test_telegram_sink_skips_when_all_foreign_restriction(self, mock_send):
        mock_send.return_value = True
        sink = TelegramSink()

        job_uk = make_dummy_job("j1", 100, ["loc:foreign_restriction(-40)"])
        job_pl = make_dummy_job("j2", 100, ["loc:foreign_restriction(-40)"])

        ctx = {"min_score": 70, "force_notify": True}
        sink.export([job_uk, job_pl], ctx)

        self.assertFalse(mock_send.called)

    @patch("telegram_notify.send_telegram_message")
    def test_legacy_wrapper_filters_foreign_restriction(self, mock_send):
        job_uk = make_dummy_job("j1", 100, ["loc:foreign_restriction(-40)"])
        res = notify_new_jobs([job_uk])
        self.assertFalse(res)
        self.assertFalse(mock_send.called)

    @patch("subprocess.run")
    @patch("shutil.which", return_value="/usr/bin/notify-send")
    def test_desktop_sink_filters_foreign_restriction(self, mock_which, mock_run):
        sink = DesktopSink()
        job_uk = make_dummy_job("j1", 120, ["loc:foreign_restriction(-40)"])
        job_it = make_dummy_job("j2", 75, ["loc:home_country"])

        sink.export([job_uk, job_it], {})
        self.assertTrue(mock_run.called)
        args = mock_run.call_args[0][0]
        self.assertIn("[75]", args[1])
        self.assertNotIn("[120]", args[1])


if __name__ == "__main__":
    unittest.main()
