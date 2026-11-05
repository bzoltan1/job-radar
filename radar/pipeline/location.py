"""Location evaluation & geographic scoring stage."""

import re
from typing import Dict, List, Set, Tuple

from radar.config import get_location_config
from radar.models import Job, PipelineContext, RawJob
from radar.pipeline.base import PipelineStage, StageResult

COUNTRY_SYNONYMS = {
    "italy": ("italy", "italia", "milan", "milano", "rome", "roma", "turin", "torino", "bologna", "naples", "napoli"),
    "austria": ("austria", "vienna", "wien", "linz", "graz", "salzburg", "innsbruck"),
    "germany": ("germany", "munich", "münchen", "berlin", "frankfurt", "deutschland", "hamburg", "cologne", "köln", "stuttgart"),
    "france": ("france", "paris", "nantes", "grenoble", "montpellier", "lyon", "bordeaux", "toulouse"),
    "uk": ("united kingdom", "uk", "london", "england", "scotland", "wales", "edinburgh", "manchester"),
    "united kingdom": ("united kingdom", "uk", "london", "england", "scotland", "wales", "edinburgh", "manchester"),
    "netherlands": ("netherlands", "amsterdam", "holland", "rotterdam", "utrecht", "eindhoven"),
    "spain": ("spain", "madrid", "barcelona", "valencia", "seville", "españa"),
    "ireland": ("ireland", "dublin", "cork", "galway"),
    "poland": ("poland", "warsaw", "krakow", "wrocław", "polska", "gdansk"),
    "sweden": ("sweden", "stockholm", "gothenburg", "malmö"),
    "switzerland": ("switzerland", "zurich", "geneva", "basel", "bern", "schweiz", "suisse"),
    "portugal": ("portugal", "lisbon", "porto"),
    "belgium": ("belgium", "brussels", "antwerp", "ghent"),
    "czech": ("czech", "prague", "czechia", "brno"),
    "denmark": ("denmark", "copenhagen", "aarhus"),
    "norway": ("norway", "oslo", "bergen"),
    "finland": ("finland", "helsinki", "espoo"),
    "romania": ("romania", "bucharest", "cluj"),
    "greece": ("greece", "athens", "thessaloniki"),
    "canada": ("canada", "toronto", "vancouver", "montreal", "ottawa"),
    "australia": ("australia", "sydney", "melbourne", "brisbane"),
    "brazil": ("brazil", "brasil", "sao paulo", "rio de janeiro"),
    "india": ("india", "bengaluru", "bangalore", "delhi", "mumbai", "hyderabad", "pune"),
    "us": ("united states", "usa", "us", "new york", "california", "san francisco", "austin", "texas", "seattle"),
    "united states": ("united states", "usa", "us", "new york", "california", "san francisco", "austin", "texas", "seattle"),
}

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

_REGEX_CACHE: Dict[str, re.Pattern] = {}


def get_country_regex(country_name: str) -> re.Pattern:
    key = country_name.lower().strip()
    if key not in _REGEX_CACHE:
        syns = COUNTRY_SYNONYMS.get(key, (key,))
        pattern = r"\b(" + "|".join(re.escape(s) for s in syns) + r")\b"
        _REGEX_CACHE[key] = re.compile(pattern, re.IGNORECASE)
    return _REGEX_CACHE[key]


def get_eu_countries(text: str) -> Set[str]:
    found = set()
    for c in COUNTRY_SYNONYMS:
        rx = get_country_regex(c)
        if rx.search(text):
            found.add(c)
    return found


class LocationStage(PipelineStage):
    """Categorizes geographic eligibility and computes location score delta based on configured candidate countries."""

    @property
    def name(self) -> str:
        return "location_stage"

    def process(self, raw_job: RawJob, job: Job, context: PipelineContext) -> StageResult:
        title = raw_job.title
        location = raw_job.location
        company = context.target

        loc_cfg = get_location_config()
        home_country = loc_cfg["home_country"].lower()
        allowed_countries = [c.lower() for c in loc_cfg.get("allowed_countries", ["Austria"])]

        home_re = get_country_regex(home_country)
        is_direct_home = bool(home_re.search(location)) or bool(home_re.search(title))

        is_direct_allowed = False
        for ac in allowed_countries:
            ac_re = get_country_regex(ac)
            if ac_re.search(location) or ac_re.search(title):
                if ac == "austria" and not (company.allow_austria or "austria" in allowed_countries):
                    continue
                is_direct_allowed = True
                break

        if not is_direct_allowed and company.allow_austria:
            austria_re = get_country_regex("austria")
            if austria_re.search(location) or austria_re.search(title):
                is_direct_allowed = True

        # Hybrid / On-site check: must match home or allowed country directly
        is_hybrid = bool(re.search(r"\bhybrid\b", location, re.IGNORECASE))
        is_onsite = bool(re.search(r"\b(in-office|on-?site)\b", location, re.IGNORECASE))
        if (is_hybrid or is_onsite) and not (is_direct_home or is_direct_allowed):
            return StageResult(should_continue=False)

        # Disqualify non-EU positions (unless candidate is in that country or job is EMEA/global)
        is_non_eu = bool(NON_EU_DISQUALIFY_RE.search(location)) or bool(re.search(r"(?:\|\s*|\(\s*|\b-\s*|\b—\s*)(us\b|usa\b|united states|canada|india|australia|singapore|japan|apac|americas|amer\b|latam)(?:\s*\||\s*\)|\s*-|\s*—|\s*$)", title, re.IGNORECASE))
        title_non_eu = bool(re.search(r"\b(amer\b|americas|apac|latam|us\b|usa\b)\b", title, re.IGNORECASE))
        has_global_or_emea = (bool(LOCATION_EMEA_REMOTE_RE.search(location)) or bool(re.search(r"\b(emea|europe)\b", title, re.IGNORECASE))) and not title_non_eu
        if is_non_eu and not (is_direct_home or is_direct_allowed or has_global_or_emea):
            return StageResult(should_continue=False)

        # Check remote indicators
        is_title_geo = bool(re.search(r"\b(emea|europe)\b", title, re.IGNORECASE))
        is_loc_geo = bool(LOCATION_EMEA_REMOTE_RE.search(location)) or (location.strip().lower() in ("remote", "distributed"))
        is_remote_keyword = bool(re.search(r"\b(remote|distributed|telecommute|work from home)\b", f"{title} {location}", re.IGNORECASE))

        if not (is_direct_home or is_direct_allowed or is_title_geo or is_loc_geo or is_remote_keyword):
            return StageResult(should_continue=False)

        # Detect single-country foreign lock
        detected_countries = get_eu_countries(f"{title} {location}")
        accepted_countries = {home_country} | set(allowed_countries)
        foreign_restrictions = detected_countries - accepted_countries

        is_foreign_single_country = False
        is_emea_remote = False

        if is_direct_home or is_direct_allowed:
            pass
        elif len(foreign_restrictions) > 0 and (is_remote_keyword or is_loc_geo or is_title_geo):
            is_foreign_single_country = True
        elif is_title_geo or is_loc_geo:
            is_emea_remote = True
        else:
            return StageResult(should_continue=False)

        # Update Job flags
        job.is_home_direct = is_direct_home
        job.is_emea_remote = is_emea_remote or is_direct_allowed or is_foreign_single_country

        # Compute score delta & tags
        score_delta = 0
        tags = []

        if is_direct_home:
            score_delta += 25
            tags.append(f"loc:{home_country[:2]}_direct")
            tags.append("loc:home_country")
        elif is_direct_allowed:
            score_delta += 15
            tags.append("loc:allowed_country")
            tags.append("loc:austria")
        elif is_foreign_single_country:
            score_delta -= 40
            tags.append("loc:foreign_restriction(-40)")
        elif is_emea_remote:
            score_delta += 10
            tags.append("loc:emea_remote")

        return StageResult(should_continue=True, score_delta=score_delta, tags=tags)
