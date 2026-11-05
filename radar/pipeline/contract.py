"""Contract type & company tier scoring stage."""

import re
from radar.config import get_location_config
from radar.models import Job, PipelineContext, RawJob
from radar.pipeline.base import PipelineStage, StageResult

B2B_RE = re.compile(
    r"\b(b2b|contractor only|independent contractor|freelance|vat number|partita iva)\b",
    re.IGNORECASE,
)


class ContractStage(PipelineStage):
    """Filters B2B roles and computes company tier + legal entity bonuses."""

    @property
    def name(self) -> str:
        return "contract_stage"

    def process(self, raw_job: RawJob, job: Job, context: PipelineContext) -> StageResult:
        content = raw_job.content or ""
        company = context.target

        # Hard contract check (no B2B)
        if B2B_RE.search(content):
            return StageResult(should_continue=False)

        score_delta = 0
        tags = []

        # Company tier
        tier = company.tier
        if tier == "big_tech":
            score_delta += 35
            tags.append("tier:big_tech")
        elif tier == "enterprise_infra":
            score_delta += 30
            tags.append("tier:enterprise_infra")
        elif tier == "scaleup":
            score_delta += 15
            tags.append("tier:scaleup")

        # Legal entity / EOR bonus (only awarded if role is direct home country or broad global remote)
        # Bypassed if single-country foreign restriction is present
        loc_cfg = get_location_config()
        home_country = loc_cfg["home_country"]
        is_foreign_restricted = any("loc:foreign_restriction" in t for t in job.tags)

        if not is_foreign_restricted:
            if company.has_home_entity():
                score_delta += 35
                tags.append(f"legal:{home_country[:2].lower()}_entity")
                tags.append("legal:home_entity")
            elif company.eor_supported:
                score_delta += 25
                tags.append("legal:eor")

        return StageResult(should_continue=True, score_delta=score_delta, tags=tags)
