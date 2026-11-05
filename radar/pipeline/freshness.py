"""Posting age & staleness decay scoring stage."""

import datetime
from typing import Optional

from radar.models import Job, PipelineContext, RawJob
from radar.pipeline.base import PipelineStage, StageResult


class FreshnessStage(PipelineStage):
    """Computes posting freshness bonus or staleness penalties."""

    @property
    def name(self) -> str:
        return "freshness"

    def process(self, raw_job: RawJob, job: Job, context: PipelineContext) -> StageResult:
        eff_date = raw_job.posted_date or context.first_seen
        age_days: Optional[int] = None

        if eff_date:
            try:
                clean_date = str(eff_date).split(".")[0].strip()
                if " " in clean_date:
                    dt = datetime.datetime.strptime(clean_date, "%Y-%m-%d %H:%M:%S")
                else:
                    dt = datetime.datetime.strptime(clean_date, "%Y-%m-%d")
                now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
                age_days = max(0, (now_utc - dt).days)
            except Exception:
                age_days = None

        if age_days is None:
            # Neutral baseline when posting date cannot be verified
            return StageResult(should_continue=True, score_delta=0, tags=[])

        score_delta = 0
        tags = []

        if age_days <= 7:
            score_delta += 20
            tags.append("age:fresh(<7d)")
        elif age_days <= 21:
            score_delta += 10
            tags.append("age:recent(<=21d)")
        elif age_days <= 45:
            pass  # Active baseline
        elif age_days <= 75:
            score_delta -= 15
            tags.append("age:aging(>45d)")
        else:
            score_delta -= 30
            tags.append("age:stale(>75d)")

        return StageResult(should_continue=True, score_delta=score_delta, tags=tags)
