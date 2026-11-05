"""Desktop notification sink plugin."""

import shutil
import subprocess
from typing import Any, Dict, List

from radar.models import Job
from radar.sinks.base import BaseSink


class DesktopSink(BaseSink):
    name = "desktop"

    def export(self, jobs: List[Job], context: Dict[str, Any]):
        eligible = [
            j for j in jobs
            if not any("loc:eu_no_italy" in t or "loc:foreign_restriction" in t for t in j.tags)
        ]
        notify_bin = shutil.which("notify-send")
        if not eligible or not notify_bin:
            return

        top = sorted(eligible, key=lambda x: x.score, reverse=True)[0]
        header = f"Job Radar: Top Match [{top.score}]"
        body = f"{top.company_id.capitalize()}: {top.title}"
        try:
            subprocess.run([notify_bin, header, body], check=False)
        except Exception:
            pass
