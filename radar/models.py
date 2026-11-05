"""Data models for Job Radar."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class RawJob:
    """Raw unparsed job posting fetched from ATS source."""
    id: str
    company_id: str
    title: str
    location: str
    url: str
    content: str = ""
    posted_date: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class SalaryInfo:
    """Extracted and normalized salary information."""
    min_val: int = 0
    max_val: int = 0
    currency: str = ""
    display: str = ""
    norm_max_eur: int = 0


@dataclass
class ProfileMatch:
    """Profile matching evaluation results."""
    match_pct: int = 0
    matched_skills: List[str] = field(default_factory=list)
    pitch_bullets: List[str] = field(default_factory=list)


@dataclass
class Job:
    """Fully processed, scored, and enriched job record."""
    id: str
    company_id: str
    title: str
    location: str
    url: str
    score: int = 0
    tags: List[str] = field(default_factory=list)
    is_home_direct: bool = False
    is_emea_remote: bool = False
    salary: SalaryInfo = field(default_factory=SalaryInfo)
    profile: ProfileMatch = field(default_factory=ProfileMatch)
    content: str = ""
    posted_date: Optional[str] = None
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    active: bool = True
    notified_at: Optional[str] = None
    status: str = "new"


@dataclass
class CompanyTarget:
    """Target company tracking definition."""
    id: str
    name: str
    tier: str = "scaleup"
    category: str = ""
    ats: str = "greenhouse"
    board: str = ""
    entity_in_home_country: bool = False
    eor_supported: bool = True
    allow_austria: bool = False
    notes: str = ""
    site: str = "jobs"
    sub_domain: str = "wd5"
    extra: Dict[str, Any] = field(default_factory=dict)

    def has_home_entity(self) -> bool:
        return bool(self.entity_in_home_country)


@dataclass
class PipelineContext:
    """Context passed across pipeline stages."""
    target: CompanyTarget
    first_seen: Optional[str] = None
    existing_job: Optional[Job] = None
