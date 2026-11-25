"""Base contract for ATS source plugins."""

from abc import ABC, abstractmethod
import datetime
from typing import List, Optional, Union
from radar.models import CompanyTarget, RawJob


def parse_job_date(value: Union[str, int, float, None]) -> Optional[str]:
    """Parse an ATS date (ISO string or epoch seconds/milliseconds) into UTC 'YYYY-MM-DD HH:MM:SS'."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)) or (str(value).isdigit() and len(str(value)) >= 10):
            ts = float(value)
            dt = datetime.datetime.fromtimestamp(ts / 1000 if ts > 1e11 else ts, datetime.timezone.utc)
        else:
            dt = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            if dt.tzinfo:
                dt = dt.astimezone(datetime.timezone.utc)
        return dt.strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OverflowError, OSError):
        return None


class BaseSource(ABC):
    """Abstract base class for ATS scraping source plugins."""
    ats_name: str

    @abstractmethod
    def fetch(self, target: CompanyTarget) -> List[RawJob]:
        """Fetch all raw job postings for a target company."""
        pass
