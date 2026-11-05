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

        # Legal entity / EOR bonus (only awarded if role is direct local country or broad global remote)
        # Bypassed if single-country foreign restriction is present
        loc_cfg = get_location_config()
        primary_country = loc_cfg.get("primary_country", "Italy")
        is_foreign_restricted = any("loc:eu_no_italy" in t or "loc:foreign_restriction" in t for t in job.tags)

        if not is_foreign_restricted:
            has_entity = (
                company.has_local_entity(primary_country)
                if hasattr(company, "has_local_entity")
                else company.entity_in_italy
            )
            if has_entity:
                score_delta += 35
                tags.append(f"legal:{primary_country[:2].lower()}_entity")
                tags.append("legal:local_entity")
                if primary_country.lower() == "italy":
                    tags.append("legal:it_entity")
            elif company.eor_supported:
                score_delta += 25
                tags.append("legal:eor")

        return StageResult(should_continue=True, score_delta=score_delta, tags=tags)
