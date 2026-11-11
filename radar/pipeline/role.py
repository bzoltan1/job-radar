"""Role seniority, systems relevance & tech stack scoring stage."""

import re
from radar.config import find_tech_matches
from radar.models import Job, PipelineContext, RawJob
from radar.pipeline.base import PipelineStage, StageResult
from radar.pipeline.title import DEVOPS_PLATFORM_SRE_RE, SYSTEMS_TITLE_RE

HIGH_PROFILE_SENIORITY_RE = re.compile(
    r"\b(staff|principal|lead|senior\s+staff|distinguished|head\s+of|director|architect)\b",
    re.IGNORECASE,
)

SENIOR_RE = re.compile(r"\b(senior|sr\.?)\b", re.IGNORECASE)


class RoleSeniorityStage(PipelineStage):
    """Evaluates role alignment (systems/SRE vs general SWE), seniority tier, and tech stack."""

    @property
    def name(self) -> str:
        return "role_seniority"

    def process(self, raw_job: RawJob, job: Job, context: PipelineContext) -> StageResult:
        title = raw_job.title
        content = raw_job.content or ""
        score_delta = 0
        tags = []

        is_systems = bool(SYSTEMS_TITLE_RE.search(title))
        is_high_profile = bool(HIGH_PROFILE_SENIORITY_RE.search(title))
        is_senior = bool(SENIOR_RE.search(title))
        is_devops_platform_sre = bool(DEVOPS_PLATFORM_SRE_RE.search(title))

        if is_systems:
            score_delta += 30
            tags.append("role:systems_platform")
            if is_devops_platform_sre:
                tags.append("domain:devops_platform_sre")
            if is_high_profile:
                score_delta += 20
                tags.append("seniority:staff_principal_lead")
            elif is_senior:
                score_delta += 10
                tags.append("seniority:senior")
        elif re.search(r"\b(software engineer|senior engineer|staff engineer|principal engineer)\b", title, re.IGNORECASE):
            score_delta += 10
            tags.append("role:swe")
            if is_high_profile:
                score_delta += 15
                tags.append("seniority:staff_principal_lead")
            elif is_senior:
                score_delta += 5
                tags.append("seniority:senior")

        # Tech stack matches
        unique_matches = find_tech_matches(f"{title} {content}")
        if unique_matches:
            score_delta += min(len(unique_matches) * 5, 25)
            tags.append(f"tech:{','.join(unique_matches[:4])}")

        return StageResult(should_continue=True, score_delta=score_delta, tags=tags)
