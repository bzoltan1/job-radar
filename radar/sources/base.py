"""Base contract for ATS source plugins."""

from abc import ABC, abstractmethod
import datetime
from typing import List, Optional
from radar.models import CompanyTarget, RawJob


def parse_job_date(date_str: Optional[str]) -> Optional[str]:
    """Parse ATS date strings into standard YYYY-MM-DD HH:MM:SS format."""
    if not date_str:
        return None
    try:
        clean = str(date_str).replace("Z", "+00:00")
        dt = datetime.datetime.fromisoformat(clean)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except Exception:
        return None


class BaseSource(ABC):
    """Abstract base class for ATS scraping source plugins."""
    ats_name: str

    @abstractmethod
    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        """Fetch all raw job postings for a target company."""
        pass
