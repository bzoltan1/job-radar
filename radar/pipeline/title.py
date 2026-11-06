"""Title and Technical Domain filtering stage."""

import re
from radar.models import Job, PipelineContext, RawJob
from radar.pipeline.base import PipelineStage, StageResult

TITLE_EXCLUDE_RE = re.compile(
    r"\b("
    r"sales|pre-?sales|solutions?\s+engineer(?:ing)?|solutions?\s+architect(?:ure)?|"
    r"customer\s+success|customer\s+engineer(?:ing)?|"
    r"technical\s+account\s+manage(?:r|ment|rs)?|\btam\b|"
    r"account\s+executive|\bae\b|account\s+manage(?:r|ment|rs)?|\bam\b|business\s+development|\bbdr\b|\bsdr\b|"
    r"gtm\b|go-to-market|revops\b|revenue\s+operations|renewals?|"
    r"deal\s+pricing|monetization|pricing|"
    r"commercial|partner\s+engineer|partner\s+solutions|partner\s+architect|partner\s+manager|alliances?|"
    r"marketing|recruiter|recruiting|talent|legal|counsel|attorney|"
    r"accountant|accounting|payroll|people\s+partner|hr\b|copywriter|content\s+writer|office\s+manager|"
    r"frontend|front-end|react|angular|ui/ux|product\s+designer|graphic\s+designer|finance\s+director|"
    r"deal\s+desk|sales\s+ops|technical\s+enablement|curriculum\s+developer|"
    r"(?:deal|pricing|monetization|strategy|business|commercial|financial|revenue)\s+analyst|"
    r"junior|entry[\s-]level|"
    r"interns?|internships?|students?|co-ops?|working\s+students?|apprentices?|loss\s+prevention|"
    r"construction|vendor\s+manager|retail|facility\s+manager|warehouse"
    r")\b",
    re.IGNORECASE,
)

ENGINEERING_TITLE_RE = re.compile(
    r"\b(software|developer|engineer|architect|sre|devops|platform|infrastructure|infra|technician)\b",
    re.IGNORECASE,
)

SYSTEMS_TITLE_RE = re.compile(
    r"\b(systems|platform|platform\s+eng(?:ineer(?:ing)?)?|devops|linux|kernel|ebpf|bpf|"
    r"infrastructure|infra|sre|site\s+reliability|production\s+eng(?:ineer(?:ing)?)?|"
    r"distributed|runtime|virtualization|container|core\s+os|low-level|storage|networking|"
    r"cloud\s+platform|kubernetes|cloud\s+infrastructure)\b",
    re.IGNORECASE,
)

DEVOPS_PLATFORM_SRE_RE = re.compile(
    r"\b(devops|platform|site\s+reliability|sre|production\s+eng(?:ineer(?:ing)?)?|infrastructure|cloud\s+platform)\b",
    re.IGNORECASE,
)

TECH_STACK_RE = re.compile(
    r"\b(golang|go\b|c\b|c\+\+|rust|python|cloud|aws|linux|ebpf|systemd|kernel|kubernetes|docker|perf|syscall|posix)\b",
    re.IGNORECASE,
)


class TitleFilterStage(PipelineStage):
    """Filters out non-engineering or hard-excluded business/sales roles."""

    @property
    def name(self) -> str:
        return "title_filter"

    def process(self, raw_job: RawJob, job: Job, context: PipelineContext) -> StageResult:
        title = raw_job.title
        content = raw_job.content or ""

        # Hard exclusion
        if TITLE_EXCLUDE_RE.search(title):
            return StageResult(should_continue=False)

        # Must be technical or match tech stack
        is_eng = bool(ENGINEERING_TITLE_RE.search(title))
        is_sys = bool(SYSTEMS_TITLE_RE.search(title))
        has_tech = bool(TECH_STACK_RE.search(f"{title} {content}"))

        if not (is_eng or is_sys or has_tech):
            return StageResult(should_continue=False)

        return StageResult(should_continue=True)
