"""Tests for target companies configuration and ATS source plugins."""

import unittest

from radar.config import load_targets
from radar.sources import get_source, list_sources


class TestTargetsAndSources(unittest.TestCase):
    def test_targets_load_and_contain_all_linkedin_companies(self):
        targets = load_targets()
        self.assertGreaterEqual(len(targets), 50)

        target_map = {t.id: t for t in targets}

        # 30 companies from the LinkedIn European remote engineering post
        expected_companies = [
            "canonical",
            "nebius",
            "gitlab",
            "elevenlabs",
            "clickhouse",
            "crowdstrike",
            "supabase",
            "nvidia",
            "mozilla",
            "kraken",
            "tether",
            "affirm",
            "datadog",
            "deel",
            "alan",
            "camunda",
            "castai",
            "elastic",
            "zscaler",
            "tide",
            "mistral",
            "fingerprint",
            "grafanalabs",
            "primer",
            "addepar",
            "chainguard",
            "docker",
            "prolific",
            "tem",
            "n8n",
        ]

        for cid in expected_companies:
            self.assertIn(cid, target_map, f"Target company '{cid}' missing in targets.yaml")
            t = target_map[cid]
            self.assertTrue(t.name, f"Target '{cid}' has empty name")
            self.assertTrue(t.ats, f"Target '{cid}' has empty ats")
            self.assertTrue(t.board, f"Target '{cid}' has empty board")

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


if __name__ == "__main__":
    unittest.main()
