"""Base contract for Output Sink plugins."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from radar.models import Job


class BaseSink(ABC):
    """Abstract base class for output sinks."""
    name: str
    # True: export() receives every stored active job (above min_score), not just this run's.
    # Use for artifacts that represent the whole pipeline (feed, vault) so partial syncs don't clobber them.
    snapshot: bool = False

    @abstractmethod
    def export(self, jobs: List[Job], context: Dict[str, Any]):
        """Export processed jobs or dispatch notifications."""
        pass
