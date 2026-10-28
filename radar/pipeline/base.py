"""Base contract for Job Radar Pipeline Stages."""

from abc import ABC, abstractmethod
from typing import List, Optional

from radar.models import Job, PipelineContext, RawJob


class StageResult:
    """Result returned by each pipeline stage."""

    def __init__(
        self,
        should_continue: bool = True,
        score_delta: int = 0,
        tags: Optional[List[str]] = None,
    ):
        self.should_continue = should_continue
        self.score_delta = score_delta
        self.tags = tags or []


class PipelineStage(ABC):
    """Abstract base class for a discrete filter or scoring stage."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Descriptive name of the pipeline stage."""
        pass

    @abstractmethod
    def process(self, raw_job: RawJob, job: Job, context: PipelineContext) -> StageResult:
        """
        Evaluate and mutate the Job instance.
        Return StageResult(should_continue=False) to discard the job completely.
        """
        pass
