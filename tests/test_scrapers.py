"""Unit tests for the generic HTML scraper plugin framework and PagoPA scraper."""

import unittest
from unittest.mock import MagicMock, patch

from radar.models import CompanyTarget
from radar.scrapers import discover_scrapers, get_scraper, list_scrapers, register_scraper
from radar.scrapers.base import BaseHtmlScraper
from radar.scrapers.pagopa import PagoPAScraper
from radar.pipeline.salary import extract_salary
from radar.models import RawJob
from radar.scrapers.flyio import FlyIOScraper
from radar.sources import get_source, list_sources
from radar.sources.scraper import HtmlScraperSource

SAMPLE_FLYIO_HTML = """
<!DOCTYPE html>
<html>
<body>
  <article>
    <dl>
      <dd class="font-heading text-[1.4rem]">Networking Engineer: Proxy and Corrosion</dd>
      <dd><div>Remote</div></dd>
    </dl>
    <p class="text-base line-clamp-3">Agent workloads churn machines fast.</p>
    <a href="/jobs/networking-engineer/"><span class="sr-only">Read more</span></a>
  </article>
</body>
</html>
"""

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

    @patch.object(FlyIOScraper, "fetch_html")
    def test_flyio_scraper_parsing(self, mock_fetch):
        mock_fetch.return_value = SAMPLE_FLYIO_HTML
        target = CompanyTarget(
            id="flyio",
            name="Fly.io",
            tier="scaleup",
            ats="scraper",
            board="flyio",
        )
        scraper = FlyIOScraper()
        jobs = scraper.scrape(target)
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "flyio_networking-engineer")
        self.assertEqual(jobs[0].title, "Networking Engineer: Proxy and Corrosion")
        self.assertEqual(jobs[0].location, "Remote")
        self.assertIn("Agent workloads", jobs[0].content)

    def test_ashby_salary_extraction(self):
        cases = [
            ("Compensation: $180,880 – $342,000 • Offers Equity", "USD 180k-342k", 314640),
            ("Compensation: €134K – €177.1K • Offers Equity", "EUR 134k-177k", 177100),
            ("Compensation: $118K • Offers Equity", "USD 118k", 108560),
            ("Compensation: $190.5K • Offers Equity", "USD 190k", 175260),
        ]
        for text, expected_disp, expected_norm in cases:
            raw = RawJob(id="test", company_id="test", title="Dev", location="Remote", url="", content=text)
            sal = extract_salary(raw)
            self.assertEqual(sal.display, expected_disp)
            self.assertEqual(sal.norm_max_eur, expected_norm)


    def test_salary_currency_edge_cases(self):
        def ext(content="", metadata=None):
            return extract_salary(RawJob(id="t", company_id="t", title="T", location="R", url="", content=content,
                                         metadata={"raw": metadata} if metadata else {}))

        low = ext("Pay: eur 80,000 - 100,000")  # lowercase symbol was mislabelled USD
        self.assertEqual((low.currency, low.norm_max_eur), ("EUR", 100000))
        self.assertEqual(ext("80,000 - 100,000 gbp").currency, "GBP")
        self.assertEqual(ext("EUR 90k and USD 200k").currency, "EUR")  # EUR preferred
        self.assertEqual(ext("rate $60/hour, range $5,000 - $9,000").display, "")  # implausible
        inr = ext(metadata=[{"value_type": "currency_range", "value": {"unit": "INR", "min_value": 2000000, "max_value": 3000000}}])
        self.assertEqual((inr.currency, inr.max_val, inr.norm_max_eur), ("INR", 3000000, 0))  # no rate: never guess
        gbp = ext(metadata=[{"value_type": "currency_range", "value": {"unit": "gbp", "min_value": 0, "max_value": 100000}}])
        self.assertEqual((gbp.display, gbp.norm_max_eur), ("GBP 100k", 118000))


if __name__ == "__main__":
    unittest.main()
