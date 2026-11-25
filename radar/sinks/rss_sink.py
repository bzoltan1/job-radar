"""RSS 2.0 feed generator sink plugin."""

import datetime
from typing import Any, Dict, List
import xml.etree.ElementTree as ET

from radar.config import FEED_PATH, get_candidate_info
from radar.models import Job
from radar.sinks.base import BaseSink


class RssSink(BaseSink):
    name = "rss"
    snapshot = True

    def export(self, jobs: List[Job], context: Dict[str, Any]):
        output_path = context.get("feed_path", FEED_PATH)
        rss = ET.Element("rss", version="2.0")
        channel = ET.SubElement(rss, "channel")

        cand_info = get_candidate_info()
        cand_name = cand_info.get("name", "Candidate")
        cand_headline = cand_info.get("headline", "Systems & Platform Engineering")
        cand_site = cand_info.get("website", "")

        title = ET.SubElement(channel, "title")
        title.text = f"{cand_name} — {cand_headline} Radar"

        link = ET.SubElement(channel, "link")
        link.text = cand_site if cand_site else "https://github.com/job-radar"

        desc = ET.SubElement(channel, "description")
        desc.text = f"Top curated opportunities matching {cand_name}'s profile."

        last_build = ET.SubElement(channel, "lastBuildDate")
        now_str = datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
        last_build.text = now_str

        # Sort jobs by score descending
        sorted_jobs = sorted(jobs, key=lambda x: x.score, reverse=True)

        for j in sorted_jobs[:50]:
            item = ET.SubElement(channel, "item")
            it_title = ET.SubElement(item, "title")
            score = j.score
            sal = j.salary.display or "Unspecified"
            comp = j.company_id.capitalize()
            it_title.text = f"[{score} pts | {sal}] {comp}: {j.title}"

            it_link = ET.SubElement(item, "link")
            it_link.text = j.url

            guid = ET.SubElement(item, "guid")
            guid.text = j.id or j.url

            it_desc = ET.SubElement(item, "description")
            loc = j.location
            tags = ";".join(j.tags)
            skills_str = ", ".join(j.profile.matched_skills)

            it_desc.text = (
                f"<strong>Company:</strong> {comp}<br/>"
                f"<strong>Location:</strong> {loc}<br/>"
                f"<strong>Salary:</strong> {sal}<br/>"
                f"<strong>Profile Match:</strong> {j.profile.match_pct}%<br/>"
                f"<strong>Matched Skills:</strong> {skills_str}<br/>"
                f"<strong>Tags:</strong> {tags}<br/><br/>"
                f"<a href='{j.url}'>Apply on {comp} career site</a>"
            )

            pub_date = ET.SubElement(item, "pubDate")
            pub_date.text = now_str

        tree = ET.ElementTree(rss)
        ET.indent(tree, space="  ", level=0)
        tree.write(output_path, encoding="utf-8", xml_declaration=True)
