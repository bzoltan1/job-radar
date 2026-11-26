"""HTTP helper + source error contract: failures raise FetchError, never a silent []."""

import io
import json
import unittest
import urllib.error
from unittest.mock import patch

from radar.http import FetchError, http_get_json, http_get_text
from radar.models import CompanyTarget
from radar.sources import get_source


class FakeResp(io.BytesIO):
    class _Headers:
        def get_content_charset(self):
            return None

    headers = _Headers()

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False


def resp(obj):
    return FakeResp(obj if isinstance(obj, bytes) else json.dumps(obj).encode())


def http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, None)


URLOPEN = "radar.http.urllib.request.urlopen"


class TestHttp(unittest.TestCase):
    def test_errors_become_fetch_error(self):
        for exc in (http_error(500), urllib.error.URLError("dns"), TimeoutError("slow"), ValueError("bad url")):
            with patch(URLOPEN, side_effect=exc), self.assertRaises(FetchError):
                http_get_text("http://x")

    def test_status_is_kept(self):
        with patch(URLOPEN, side_effect=http_error(404)), self.assertRaises(FetchError) as cm:
            http_get_text("http://x")
        self.assertEqual(cm.exception.status, 404)

    def test_invalid_json_is_fetch_error(self):
        with patch(URLOPEN, return_value=resp(b"<html>")), self.assertRaises(FetchError):
            http_get_json("http://x")

    def test_retry_429_once(self):
        with patch(URLOPEN, side_effect=[http_error(429), resp({"ok": 1})]) as m, patch("radar.http.time.sleep"):
            self.assertEqual(http_get_json("http://x", retry_429=True), {"ok": 1})
        self.assertEqual(m.call_count, 2)
        with patch(URLOPEN, side_effect=[http_error(429)]), self.assertRaises(FetchError):
            http_get_json("http://x")  # no retry unless asked

    def test_json_body_posts_with_content_type(self):
        with patch(URLOPEN, return_value=resp({})) as m:
            http_get_json("http://x", json_body={"a": 1})
        req = m.call_args[0][0]
        self.assertEqual(req.data, b'{"a": 1}')
        self.assertEqual(req.get_header("Content-type"), "application/json")


class TestSourceContract(unittest.TestCase):
    def target(self, **kw):
        return CompanyTarget(id="acme", name="Acme", **kw)

    def test_every_json_source_raises_on_http_error(self):
        for ats in ("greenhouse", "lever", "ashby", "recruitee", "smartrecruiters", "workable", "workday", "deel"):
            with patch(URLOPEN, side_effect=http_error(500)), self.assertRaises(FetchError, msg=ats):
                get_source(ats).fetch(self.target(ats=ats))

    def test_lever_falls_back_to_other_region_on_404_only(self):
        item = {"id": "1", "text": "SRE", "categories": {"location": "Berlin"}, "hostedUrl": "u", "createdAt": 1700000000000}
        with patch(URLOPEN, side_effect=[http_error(404), resp([item])]) as m:
            jobs = get_source("lever").fetch(self.target(ats="lever"))
        self.assertEqual([j.id for j in jobs], ["lever_acme_1"])
        self.assertEqual(jobs[0].posted_date, "2023-11-14 22:13:20")
        self.assertEqual(m.call_count, 2)
        with patch(URLOPEN, side_effect=[http_error(404), http_error(404)]), self.assertRaises(FetchError):
            get_source("lever").fetch(self.target(ats="lever"))

    def test_empty_board_is_a_real_empty_list(self):
        with patch(URLOPEN, return_value=resp({"jobs": []})):
            self.assertEqual(get_source("greenhouse").fetch(self.target(ats="greenhouse")), [])

    def test_workday_pages_past_100_with_total_on_first_page_only(self):
        def page(offset):
            n = max(0, min(20, 230 - offset))
            return {"total": 230 if offset == 0 else 0,
                    "jobPostings": [{"title": f"J{offset + i}", "externalPath": f"/job/X/J_{offset + i}"} for i in range(n)]}

        def fake(req, **kw):
            return resp(page(json.loads(req.data)["offset"]))

        with patch(URLOPEN, side_effect=fake):
            jobs = get_source("workday").fetch(self.target(ats="workday"))
        self.assertEqual(len(jobs), 230)

    def test_workday_failure_mid_board_raises(self):
        first = resp({"total": 100, "jobPostings": [{"title": "J", "externalPath": "/job/X/J_1"}]})
        with patch(URLOPEN, side_effect=[first, http_error(500)]), self.assertRaises(FetchError):
            get_source("workday").fetch(self.target(ats="workday"))

    def test_workday_splits_or_search_text_and_deduplicates(self):
        seen_queries = []

        def fake(req, **kw):
            body = json.loads(req.data)
            q = body.get("searchText", "")
            seen_queries.append(q)
            # Both queries return overlapping posting J_common, plus unique J_q
            return resp({
                "total": 2,
                "jobPostings": [
                    {"title": f"Common", "externalPath": "/job/X/J_common"},
                    {"title": f"Role {q}", "externalPath": f"/job/X/J_{q}"},
                ],
            })

        with patch(URLOPEN, side_effect=fake):
            jobs = get_source("workday").fetch(
                self.target(ats="workday", search_text="software OR platform OR sre")
            )

        self.assertEqual(seen_queries, ["software", "platform", "sre"])
        # J_common deduplicated across 3 queries, total unique jobs = 1 common + 3 unique = 4
        self.assertEqual(len(jobs), 4)
        ids = {j.id for j in jobs}
        self.assertEqual(ids, {"wd_acme_common", "wd_acme_software", "wd_acme_platform", "wd_acme_sre"})

    def test_workable_detail_failure_is_best_effort(self):
        listing = {"results": [{"shortcode": "A", "title": "SRE", "remote": True}, {"shortcode": "B", "title": "Dev"}]}

        def fake(req, **kw):
            url = req.full_url
            if url.endswith("/jobs") and "v3" in url:
                return resp(listing)
            if url.endswith("/A"):
                return resp({"description": "<p>Rust</p>", "requirements": "Linux"})
            raise http_error(500)

        with patch(URLOPEN, side_effect=fake):
            jobs = get_source("workable").fetch(self.target(ats="workable"))
        self.assertEqual([(j.id, j.content) for j in jobs], [("workable_acme_A", "Rust Linux"), ("workable_acme_B", "")])

    def test_html_sources_treat_zero_parsed_as_failure(self):
        with patch(URLOPEN, return_value=resp(b"<html>nothing</html>")):
            for ats in ("deel", "dynatrace", "sidero", "proxmox"):
                with self.assertRaises(FetchError, msg=ats):
                    get_source(ats).fetch(self.target(ats=ats))

    def test_sidero_parses_new_layout(self):
        html_page = (
            '<li><a class="careers-positions__row" href="/careers/senior-software-engineer">'
            '<span class="careers-positions__job">'
            '<span class="careers-positions__job-title">Senior / Staff Software Engineer</span>'
            '<span class="careers-positions__job-meta small">Full-Time<!-- --> · <!-- -->Remote — Europe preferred</span>'
            '</span></a></li>'
        )

        def fake(req, **kw):
            url = req.full_url if hasattr(req, "full_url") else str(req)
            if url.endswith("/careers/"):
                return resp(html_page.encode())
            return resp(b"<html>Job description text</html>")

        with patch(URLOPEN, side_effect=fake):
            jobs = get_source("sidero").fetch(self.target(ats="sidero"))
        self.assertEqual(len(jobs), 1)
        self.assertEqual(jobs[0].id, "sidero_senior-software-engineer")
        self.assertEqual(jobs[0].title, "Senior / Staff Software Engineer")
        self.assertEqual(jobs[0].location, "Full-Time · Remote — Europe preferred")

    def test_unknown_scraper_raises(self):
        with self.assertRaises(FetchError):
            get_source("scraper").fetch(self.target(ats="scraper", board="nope"))

    def test_scraper_page_failure_raises(self):
        with patch(URLOPEN, side_effect=http_error(503)), self.assertRaises(FetchError):
            get_source("pagopa").fetch(self.target(ats="pagopa"))


if __name__ == "__main__":
    unittest.main()
