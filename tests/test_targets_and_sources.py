"""Tests for target companies configuration and ATS source plugins."""

import unittest

from radar.config import load_targets
from radar.sources import get_source, list_sources
from radar.sources.base import parse_job_date


class TestTargetsAndSources(unittest.TestCase):
    def test_example_targets_load(self):
        targets = load_targets()
        self.assertGreaterEqual(len(targets), 5)
        for t in targets:
            self.assertTrue(t.name, f"Target '{t.id}' has empty name")
            self.assertTrue(t.ats, f"Target '{t.id}' has empty ats")
            self.assertTrue(t.board, f"Target '{t.id}' has empty board")

    def test_all_target_ats_plugins_are_registered(self):
        targets = load_targets()
        available_sources = list_sources()

        self.assertIn("recruitee", available_sources)
        self.assertIn("deel", available_sources)
        self.assertIn("greenhouse", available_sources)
        self.assertIn("ashby", available_sources)
        self.assertIn("workday", available_sources)

        for t in targets:
            source = get_source(t.ats)
            self.assertIsNotNone(
                source,
                f"Company '{t.id}' uses unknown or unregistered ATS source: '{t.ats}'",
            )

    def test_per_target_allowed_countries(self):
        targets = {t.id: t for t in load_targets()}
        self.assertEqual(targets["sentry"].allowed_countries, ["Austria"])
        self.assertEqual(targets["gitlab"].allowed_countries, [])
        cs = targets["crowdstrike"]
        self.assertEqual((cs.ats, cs.board, cs.site), ("workday", "crowdstrike", "crowdstrikecareers"))


class TestParseJobDate(unittest.TestCase):
    def test_formats(self):
        self.assertEqual(parse_job_date(1700000000000), "2023-11-14 22:13:20")  # epoch ms (Lever)
        self.assertEqual(parse_job_date(1700000000), "2023-11-14 22:13:20")  # epoch s
        self.assertEqual(parse_job_date("1700000000000"), "2023-11-14 22:13:20")
        self.assertEqual(parse_job_date("2026-03-09T16:05:19-04:00"), "2026-03-09 20:05:19")  # to UTC
        self.assertEqual(parse_job_date("2024-01-02T03:04:05Z"), "2024-01-02 03:04:05")
        self.assertEqual(parse_job_date("2024-01-02"), "2024-01-02 00:00:00")
        for bad in (None, "", "garbage"):
            self.assertIsNone(parse_job_date(bad), bad)


if __name__ == "__main__":
    unittest.main()

