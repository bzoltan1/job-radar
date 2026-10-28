"""Desktop notification sink plugin."""

import os
from typing import Any, Dict, List

from radar.models import Job
from radar.sinks.base import BaseSink


class DesktopSink(BaseSink):
    name = "desktop"

    def export(self, jobs: List[Job], context: Dict[str, Any]):
        if not jobs or not os.path.exists("/usr/bin/notify-send"):
            return

        top = sorted(jobs, key=lambda x: x.score, reverse=True)[0]
        try:
            cmd = f'/usr/bin/notify-send "Job Radar: Top Match [{top.score}]" "{top.company_id.capitalize()}: {top.title}"'
            os.system(cmd)
        except Exception:
            pass
