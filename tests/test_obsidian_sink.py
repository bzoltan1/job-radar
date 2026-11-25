"""Obsidian sink: note name collisions and frontmatter quoting."""

import os
import tempfile
import unittest

import yaml

from radar.models import Job, ProfileMatch, SalaryInfo
from radar.sinks.obsidian_sink import ObsidianSink


def make_job(job_id, title, location):
    return Job(
        id=job_id, company_id="acme", title=title, location=location, url="https://x.test/?a=1&b=2",
        score=80, salary=SalaryInfo(), profile=ProfileMatch(),
    )


def frontmatter(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f.read().split("---\n")[1])


class TestObsidianSink(unittest.TestCase):
    def test_same_title_different_jobs_get_separate_stable_notes(self):
        berlin = make_job("a1", 'Staff "Platform" Engineer', "Berlin")
        lisbon = make_job("b2", 'Staff "Platform" Engineer', "Lisbon")
        with tempfile.TemporaryDirectory() as vault:
            ObsidianSink().export([berlin, lisbon], {"vault_path": vault})
            offers = os.path.join(vault, "jobs", "offers")
            files = sorted(os.listdir(offers))
            self.assertEqual(len(files), 2)
            by_loc = {frontmatter(os.path.join(offers, f))["location"]: f for f in files}
            self.assertEqual(set(by_loc), {"Berlin", "Lisbon"})
            self.assertEqual(frontmatter(os.path.join(offers, by_loc["Berlin"]))["title"], 'Staff "Platform" Engineer')

            # Re-export in reverse order: each job keeps its own note.
            ObsidianSink().export([lisbon, berlin], {"vault_path": vault})
            self.assertEqual(sorted(os.listdir(offers)), files)
            for loc, f in by_loc.items():
                self.assertEqual(frontmatter(os.path.join(offers, f))["location"], loc)

    def test_user_notes_survive_reexport(self):
        job = make_job("a1", "SRE", "Berlin")
        with tempfile.TemporaryDirectory() as vault:
            ObsidianSink().export([job], {"vault_path": vault})
            path = os.path.join(vault, "jobs", "offers", os.listdir(os.path.join(vault, "jobs", "offers"))[0])
            with open(path, encoding="utf-8") as f:
                text = f.read()
            with open(path, "w", encoding="utf-8") as f:
                f.write(text.split("## My Notes")[0] + "## My Notes\nmy secret note\n")
            ObsidianSink().export([job], {"vault_path": vault})
            with open(path, encoding="utf-8") as f:
                self.assertIn("my secret note", f.read())


if __name__ == "__main__":
    unittest.main()
