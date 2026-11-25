"""Location evaluation & geographic scoring stage."""

import re
from dataclasses import dataclass
from typing import Dict, FrozenSet, List, Optional, Set

from radar.config import get_location_config, load_countries
from radar.models import Job, PipelineContext, RawJob
from radar.pipeline.base import PipelineStage, StageResult

LOCATION_EMEA_REMOTE_RE = re.compile(
    r"\b(emea|europe|eu|european union|worldwide|anywhere|global)\b",
    re.IGNORECASE,
)

# Location is only a remote marker, with no country: treated as global remote.
BARE_REMOTE_RE = re.compile(r"^(fully |100% |globally )?(remote|distributed)$", re.IGNORECASE)

NON_EU_DISQUALIFY_RE = re.compile(
    r"\b(us only|united states only|americas only|apac only|canada only|india only|latam only|"
    r"australia only|singapore only|japan only|brazil only)\b|"
    r"\b(united states|usa\b|us\b|new york|california|san francisco|austin|texas|canada|toronto|vancouver|brazil|brasil|india|bengaluru|bangalore|australia|sydney|singapore|japan|tokyo|new zealand|mexico|argentina|colombia|chile|americas|amer\b|apac|latam|nasa)\b",
    re.IGNORECASE,
)

TITLE_GEO_RE = re.compile(r"\b(emea|europe)\b", re.IGNORECASE)
REMOTE_KEYWORD_RE = re.compile(r"\b(remote|distributed|telecommute|work from home|flexible)\b", re.IGNORECASE)
HYBRID_RE = re.compile(r"\bhybrid\b", re.IGNORECASE)
ONSITE_RE = re.compile(r"\b(in-office|on-?site)\b", re.IGNORECASE)
TITLE_NON_EU_RE = re.compile(
    r"(?:\|\s*|\(\s*|\b-\s*|\b—\s*)(us\b|usa\b|united states|canada|india|australia|singapore|japan|apac|americas|amer\b|latam)"
    r"(?:\s*\||\s*\)|\s*-|\s*—|\s*$)",
    re.IGNORECASE,
)
TITLE_REGION_LOCK_RE = re.compile(r"\b(amer\b|americas|apac|latam|us\b|usa\b)\b", re.IGNORECASE)

_REGEX_CACHE: Dict[str, re.Pattern] = {}


def _country_terms(country: str) -> List[str]:
    entry = load_countries().get(country, {})
    return list(entry.get("aliases") or [country]) + list(entry.get("cities") or [])


def get_country_regex(country_name: str) -> re.Pattern:
    key = country_name.lower().strip()
    if key not in _REGEX_CACHE:
        pattern = r"\b(" + "|".join(re.escape(s) for s in _country_terms(key)) + r")\b"
        _REGEX_CACHE[key] = re.compile(pattern, re.IGNORECASE)
    return _REGEX_CACHE[key]


def get_eu_countries(text: str) -> Set[str]:
    return {c for c in load_countries() if get_country_regex(c).search(text)}


@dataclass(frozen=True)
class LocationFacts:
    """What the job's title/location say about geography, before any decision is made."""
    direct_home: bool
    direct_allowed: bool
    remote: bool
    geo_remote: bool  # EMEA/Europe/worldwide wording (title or location)
    hybrid_or_onsite: bool
    matches_home_city: bool
    has_different_city: bool
    non_eu: bool
    global_or_emea: bool
    foreign_countries: FrozenSet[str]


def classify_location(raw_job: RawJob, context: PipelineContext, loc_cfg: dict) -> LocationFacts:
    title, location, content = raw_job.title, raw_job.location, raw_job.content or ""
    home_country = loc_cfg["home_country"].lower()
    # Candidate-wide allowed countries plus per-company extras from targets (allowed_countries).
    allowed = list(dict.fromkeys(c.lower() for c in loc_cfg["allowed_countries"] + context.target.allowed_countries))
    candidate_city = loc_cfg.get("city", "").lower().strip()
    title_loc = f"{title} {location}"

    def mentions(country: str) -> bool:
        rx = get_country_regex(country)
        return bool(rx.search(location) or rx.search(title))

    direct_home = mentions(home_country)
    direct_allowed = any(mentions(c) for c in allowed)

    title_geo = bool(TITLE_GEO_RE.search(title))
    loc_geo = bool(LOCATION_EMEA_REMOTE_RE.search(location)) or bool(BARE_REMOTE_RE.match(location.strip()))
    content_remote = bool(re.search(
        rf"\b(100% remote|fully remote|work from anywhere|remote within {re.escape(home_country)})\b", content, re.IGNORECASE
    ))

    home_cities = load_countries().get(home_country, {}).get("cities") or []
    loc_lower = location.lower()
    title_non_eu = bool(TITLE_REGION_LOCK_RE.search(title))

    return LocationFacts(
        direct_home=direct_home,
        direct_allowed=direct_allowed,
        remote=title_geo or loc_geo or bool(REMOTE_KEYWORD_RE.search(title_loc)) or content_remote,
        geo_remote=title_geo or loc_geo,
        hybrid_or_onsite=bool(HYBRID_RE.search(title_loc) or ONSITE_RE.search(title_loc)),
        matches_home_city=bool(candidate_city and re.search(rf"\b{re.escape(candidate_city)}\b", location, re.IGNORECASE)),
        has_different_city=any(bool(re.search(rf"\b{re.escape(c)}\b", loc_lower)) for c in home_cities if c != candidate_city),
        non_eu=bool(NON_EU_DISQUALIFY_RE.search(location)) or bool(TITLE_NON_EU_RE.search(title)),
        global_or_emea=(bool(LOCATION_EMEA_REMOTE_RE.search(location)) or title_geo) and not title_non_eu,
        foreign_countries=frozenset(get_eu_countries(title_loc) - ({home_country} | set(allowed))),
    )


def decide_location(f: LocationFacts, remote_only: bool) -> Optional[str]:
    """Eligibility verdict: None (drop) or "home" | "allowed" | "foreign" | "emea"."""
    direct = f.direct_home or f.direct_allowed
    if remote_only:
        if f.hybrid_or_onsite and not f.matches_home_city:
            return None
        if not f.remote and (f.has_different_city or not f.matches_home_city):
            return None
    elif f.hybrid_or_onsite and not direct:
        return None

    # Non-EU positions are out unless the candidate is in that country or the job is EMEA/global.
    if f.non_eu and not (direct or f.global_or_emea):
        return None
    if not (direct or f.remote):
        return None

    if f.direct_home:
        return "home"
    if f.direct_allowed:
        return "allowed"
    if f.foreign_countries and f.remote:
        return "foreign"  # remote, but locked to another single country
    if f.geo_remote:
        return "emea"
    return None


class LocationStage(PipelineStage):
    """Categorizes geographic eligibility and computes location score delta based on configured candidate countries."""

    @property
    def name(self) -> str:
        return "location_stage"

    def process(self, raw_job: RawJob, job: Job, context: PipelineContext) -> StageResult:
        loc_cfg = get_location_config()
        facts = classify_location(raw_job, context, loc_cfg)
        verdict = decide_location(facts, loc_cfg.get("remote_only", False))
        if verdict is None:
            return StageResult(should_continue=False)

        job.is_home_direct = facts.direct_home
        job.is_emea_remote = verdict in ("emea", "foreign") or facts.direct_allowed

        if verdict == "home":
            home = loc_cfg["home_country"].lower()
            return StageResult(True, 25, [f"loc:{home[:2]}_direct", "loc:home_country"])
        if verdict == "allowed":
            return StageResult(True, 15, ["loc:allowed_country"])
        if verdict == "foreign":
            return StageResult(True, -40, ["loc:foreign_restriction(-40)"])
        return StageResult(True, 10, ["loc:emea_remote"])
