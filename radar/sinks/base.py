"""Base contract for Output Sink plugins."""

from abc import ABC, abstractmethod
from typing import Any, Dict, List

from radar.models import Job


class BaseSink(ABC):
    """Abstract base class for output sinks."""
    name: str

    @abstractmethod
    def export(self, jobs: List[Job], context: Dict[str, Any]):
        """Export processed jobs or dispatch notifications."""
        pass
