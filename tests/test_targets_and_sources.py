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

    def test_isovalent_and_chainguard_targets(self):
        targets = {t.id: t for t in load_targets()}

        self.assertIn("chainguard", targets)
        cg = targets["chainguard"]
        self.assertEqual(cg.ats, "greenhouse")
        self.assertEqual(cg.board, "chainguard")

        self.assertIn("isovalent", targets)
        iso = targets["isovalent"]
        self.assertEqual(iso.ats, "workday")
        self.assertEqual(iso.board, "cisco")
        self.assertEqual(iso.site, "Cisco_Careers")
        self.assertEqual(iso.search_text, "isovalent")
        self.assertTrue(iso.entity_in_home_country)

        self.assertIn("sibill", targets)
        sib = targets["sibill"]
        self.assertEqual(sib.ats, "ashby")
        self.assertEqual(sib.board, "sibill")
        self.assertTrue(sib.entity_in_home_country)

        self.assertIn("pagopa", targets)
        pago = targets["pagopa"]
        self.assertEqual(pago.ats, "scraper")
        self.assertEqual(pago.board, "pagopa")
        self.assertTrue(pago.entity_in_home_country)


if __name__ == "__main__":
    unittest.main()

