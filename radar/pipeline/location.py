"""Location evaluation & geographic scoring stage."""

import re
from radar.models import Job, PipelineContext, RawJob
from radar.pipeline.base import PipelineStage, StageResult

LOCATION_ITALY_RE = re.compile(
    r"\b(italy|italia|milan|milano|rome|roma)\b",
    re.IGNORECASE,
)

LOCATION_AUSTRIA_RE = re.compile(
    r"\b(austria|vienna|wien|linz|graz)\b",
    re.IGNORECASE,
)

LOCATION_EMEA_REMOTE_RE = re.compile(
    r"\b(emea|europe|worldwide|anywhere|global)\b",
    re.IGNORECASE,
)

NON_EU_DISQUALIFY_RE = re.compile(
    r"\b(us only|united states only|americas only|apac only|canada only|india only|latam only|"
    r"australia only|singapore only|japan only|brazil only)\b|"
    r"\b(united states|usa\b|us\b|new york|california|san francisco|austin|texas|canada|toronto|vancouver|brazil|brasil|india|bengaluru|bangalore|australia|sydney|singapore|japan|tokyo|new zealand|mexico|argentina|colombia|chile|americas|amer\b|apac|latam|nasa)\b",
    re.IGNORECASE,
)

EU_COUNTRY_MAP = {
    "uk": ("united kingdom", "uk", "london", "england", "scotland"),
    "germany": ("germany", "munich", "berlin", "frankfurt", "deutschland"),
    "france": ("france", "paris", "nantes", "grenoble", "montpellier"),
    "netherlands": ("netherlands", "amsterdam", "holland"),
    "spain": ("spain", "madrid", "barcelona"),
    "italy": ("italy", "italia", "milan", "milano", "rome", "roma"),
    "ireland": ("ireland", "dublin"),
    "poland": ("poland", "warsaw"),
    "austria": ("austria", "vienna", "wien", "linz", "graz"),
    "sweden": ("sweden", "stockholm"),
    "switzerland": ("switzerland", "zurich", "geneva"),
    "portugal": ("portugal", "lisbon"),
    "belgium": ("belgium", "brussels"),
    "czech": ("czech", "prague", "czechia"),
    "denmark": ("denmark", "copenhagen"),
    "norway": ("norway", "oslo"),
    "finland": ("finland", "helsinki"),
    "romania": ("romania", "bucharest"),
    "greece": ("greece", "athens"),
}


def get_eu_countries(text: str) -> set:
    text_lower = text.lower()
    return {c for c, syns in EU_COUNTRY_MAP.items() if any(s in text_lower for s in syns)}


class LocationStage(PipelineStage):
    """Categorizes geographic eligibility and computes location score delta."""

    @property
    def name(self) -> str:
        return "location_stage"

    def process(self, raw_job: RawJob, job: Job, context: PipelineContext) -> StageResult:
        title = raw_job.title
        location = raw_job.location
        company = context.target

        is_direct_italy = bool(LOCATION_ITALY_RE.search(location)) or bool(LOCATION_ITALY_RE.search(title))
        is_austria = (bool(LOCATION_AUSTRIA_RE.search(location)) or bool(LOCATION_AUSTRIA_RE.search(title))) if company.allow_austria else False

        # Hybrid / On-site check
        is_hybrid = bool(re.search(r"\bhybrid\b", location, re.IGNORECASE))
        is_onsite = bool(re.search(r"\b(in-office|on-?site)\b", location, re.IGNORECASE))
        if (is_hybrid or is_onsite) and not (is_direct_italy or is_austria):
            return StageResult(should_continue=False)

        # Disqualify non-EU positions
        is_non_eu = bool(NON_EU_DISQUALIFY_RE.search(location)) or bool(re.search(r"(?:\|\s*|\(\s*|\b-\s*|\b—\s*)(us\b|usa\b|united states|canada|india|australia|singapore|japan|apac|americas|amer\b|latam)(?:\s*\||\s*\)|\s*-|\s*—|\s*$)", title, re.IGNORECASE))
        title_non_eu = bool(re.search(r"\b(amer\b|americas|apac|latam|us\b|usa\b)\b", title, re.IGNORECASE))
        has_global_or_emea = (bool(LOCATION_EMEA_REMOTE_RE.search(location)) or bool(re.search(r"\b(emea|europe)\b", title, re.IGNORECASE))) and not title_non_eu
        if is_non_eu and not (is_direct_italy or is_austria or has_global_or_emea):
            return StageResult(should_continue=False)

        # Check remote indicators
        is_title_geo = bool(re.search(r"\b(emea|europe)\b", title, re.IGNORECASE))
        is_loc_geo = bool(LOCATION_EMEA_REMOTE_RE.search(location)) or (location.strip().lower() in ("remote", "distributed"))
        is_remote_keyword = bool(re.search(r"\b(remote|distributed|telecommute|work from home)\b", f"{title} {location}", re.IGNORECASE))

        if not (is_direct_italy or is_austria or is_title_geo or is_loc_geo or is_remote_keyword):
            return StageResult(should_continue=False)

        eu_found = get_eu_countries(f"{title} {location}")
        foreign_eu = eu_found - {"italy", "austria"} if company.allow_austria else eu_found - {"italy"}

        is_eu_no_italy = False
        is_emea_remote = False

        if is_direct_italy or is_austria:
            pass
        elif len(foreign_eu) > 0 and (is_remote_keyword or is_loc_geo or is_title_geo):
            is_eu_no_italy = True
        elif is_title_geo or is_loc_geo:
            is_emea_remote = True
        else:
            return StageResult(should_continue=False)

        # Set job flags
        job.is_italy_direct = is_direct_italy
        job.is_emea_remote = is_emea_remote or is_austria or is_eu_no_italy

        # Score delta & tags
        score_delta = 0
        tags = []

        if is_direct_italy:
            score_delta += 25
            tags.append("loc:italy_direct")
        elif is_austria:
            score_delta += 15
            tags.append("loc:austria")
        elif is_eu_no_italy:
            score_delta -= 40
            tags.append("loc:eu_no_italy(-40)")
        elif is_emea_remote:
            score_delta += 10
            tags.append("loc:emea_remote")

        return StageResult(should_continue=True, score_delta=score_delta, tags=tags)
