"""Tests for target companies configuration and ATS source plugins."""

import unittest

from radar.config import load_targets
from radar.sources import get_source, list_sources


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


if __name__ == "__main__":
    unittest.main()

