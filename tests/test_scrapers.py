"""Unit tests for the generic HTML scraper plugin framework and PagoPA scraper."""

import unittest
from unittest.mock import MagicMock, patch

from radar.models import CompanyTarget
from radar.scrapers import discover_scrapers, get_scraper, list_scrapers, register_scraper
from radar.scrapers.base import BaseHtmlScraper
from radar.scrapers.pagopa import PagoPAScraper
from radar.sources import get_source, list_sources
from radar.sources.scraper import HtmlScraperSource

SAMPLE_PAGOPA_HTML = """
<!DOCTYPE html>
<html>
<body>
  <h1>Careers</h1>
  <h2 class="h1">Posizioni aperte</h2>
  <div class="jobs-listing__list">
    <div class="p-4">
      <a href="/it/lavora-con-noi/jobposition-128/">
        <article class="job-entry">
          <h3 class="h4 primary job-entry__title">Security Operation Engineer<span>NEW</span></h3>
          <p class="job-entry__timeframe">Data di apertura: 2026-10-26</p>
        </article>
      </a>
    </div>
    <div class="p-4">
      <a href="/it/lavora-con-noi/jobposition-122/">
        <article class="job-entry">
          <h3 class="h4 primary job-entry__title">Product Security Engineer<span>NEW</span></h3>
          <p class="job-entry__timeframe">Data di apertura: 2026-09-25</p>
        </article>
      </a>
    </div>
  </div>
  <h2 class="mb-0 h3">Posizioni chiuse</h2>
  <div class="jobs-listing__past">
    <a href="/it/lavora-con-noi/jobposition-99/"><article class="job-entry"><h3 class="job-entry__title">Old Closed Job</h3></article></a>
  </div>
</body>
</html>
"""

SAMPLE_PAGOPA_SUBPAGE_HTML = """
<!DOCTYPE html>
<html>
<body>
  <main id="main-content">
    <h1>Security Operation Engineer</h1>
    <p>PagoPA S.p.A. cerca Security Operation Engineer con esperienza AWS, Azure, GCP e SIEM.</p>
  </main>
</body>
</html>
"""


class TestScraperFramework(unittest.TestCase):
    """Test generic scraper registry and base utilities."""

    def test_scraper_discovery_and_registry(self):
        discover_scrapers()
        scrapers = list_scrapers()
        self.assertIn("pagopa", scrapers)

        scraper = get_scraper("pagopa")
        self.assertIsInstance(scraper, PagoPAScraper)
        self.assertIsNone(get_scraper("non_existent_scraper"))

    def test_base_scraper_utilities(self):
        scraper = PagoPAScraper()

        dirty_html = "  <style>.x{}</style><div>Hello &amp; welcome! <script>alert(1)</script> </div>  "
        clean = scraper.clean_text(dirty_html)
        self.assertEqual(clean, "Hello & welcome!")

        content = "START---middle_text---END---after"
        extracted = scraper.extract_section(content, "START---", "---END")
        self.assertEqual(extracted, "middle_text")

    @patch.object(PagoPAScraper, "fetch_html")
    def test_pagopa_scraper_parsing(self, mock_fetch):
        def side_effect(url, **kwargs):
            if "jobposition-" in url:
                return SAMPLE_PAGOPA_SUBPAGE_HTML
            return SAMPLE_PAGOPA_HTML

        mock_fetch.side_effect = side_effect

        target = CompanyTarget(
            id="pagopa",
            name="PagoPA",
            tier="enterprise_infra",
            ats="scraper",
            board="pagopa",
            entity_in_home_country=True,
        )

        scraper = PagoPAScraper()
        jobs = scraper.scrape(target)

        self.assertEqual(len(jobs), 2)
        self.assertEqual(jobs[0].id, "pagopa_jobposition-128")
        self.assertEqual(jobs[0].title, "Security Operation Engineer")
        self.assertEqual(jobs[0].location, "Italy (Remote / Smart Working)")
        self.assertEqual(jobs[0].posted_date, "2026-10-26")
        self.assertIn("AWS, Azure, GCP", jobs[0].content)

        self.assertEqual(jobs[1].id, "pagopa_jobposition-122")
        self.assertEqual(jobs[1].title, "Product Security Engineer")

    def test_source_integration_and_aliases(self):
        available = list_sources()
        self.assertIn("scraper", available)
        self.assertIn("html_scraper", available)
        self.assertIn("pagopa", available)

        source = get_source("scraper")
        self.assertIsInstance(source, HtmlScraperSource)

        direct_pagopa_source = get_source("pagopa")
        self.assertIsNotNone(direct_pagopa_source)
        self.assertEqual(direct_pagopa_source.ats_name, "pagopa")


if __name__ == "__main__":
    unittest.main()
