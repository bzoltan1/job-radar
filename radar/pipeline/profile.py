"""Candidate profile & domain matching stage."""

import re
from typing import Dict, List, Optional, Tuple

from radar.config import ConfigError, load_profile
from radar.models import Job, PipelineContext, ProfileMatch, RawJob
from radar.pipeline.base import PipelineStage, StageResult


# Matched skill weights summing to this reach a 100% profile match.
FULL_MATCH_WEIGHT = 80


def get_active_skill_matrix() -> List[Tuple[str, str, int, str]]:
    """Retrieve skill matrix from the candidate profile (empty if not configured)."""
    prof = load_profile()
    custom_matrix = prof.get("skill_matrix")
    if custom_matrix and isinstance(custom_matrix, list):
        parsed = []
        for item in custom_matrix:
            if isinstance(item, dict) and "pattern" in item and "name" in item:
                try:
                    re.compile(item["pattern"])
                except re.error as e:
                    raise ConfigError(f"invalid skill_matrix pattern for {item['name']!r}: {e}") from e
                parsed.append((
                    item["pattern"],
                    item["name"],
                    int(item.get("weight", 20)),
                    item.get("pitch", ""),
                ))
        return parsed
    return []


def evaluate_profile(title: str, content: str) -> ProfileMatch:
    """Evaluate candidate profile match percentage, matched skills, and tailored pitch bullets."""
    text = f"{title} {content}".lower()

    matched_skills = []
    matched_weights = 0
    pitch_bullets = []

    matrix = get_active_skill_matrix()
    for pattern, name, weight, pitch in matrix:
        if re.search(pattern, text, re.IGNORECASE):
            matched_skills.append(name)
            matched_weights += weight
            if pitch and len(pitch_bullets) < 3:
                pitch_bullets.append(pitch)

    match_pct = min(100, int((matched_weights / FULL_MATCH_WEIGHT) * 100))

    if not pitch_bullets:
        pitch_bullets = [str(p) for p in (load_profile().get("fallback_pitch") or [])]

    return ProfileMatch(
        match_pct=match_pct,
        matched_skills=matched_skills,
        pitch_bullets=pitch_bullets,
    )


class ProfileMatchStage(PipelineStage):
    """Computes candidate skill alignment based on profile research and adds pitch bullets."""

    @property
    def name(self) -> str:
        return "profile_match"

    def process(self, raw_job: RawJob, job: Job, context: PipelineContext) -> StageResult:
        eval_result = evaluate_profile(raw_job.title, raw_job.content)
        job.profile = eval_result

        score_delta = 0
        tags = []
        match_pct = eval_result.match_pct

        if match_pct >= 80:
            score_delta += 15
            tags.append(f"match:{match_pct}%")
        elif match_pct >= 50:
            score_delta += 5
            tags.append(f"match:{match_pct}%")

        return StageResult(should_continue=True, score_delta=score_delta, tags=tags)
