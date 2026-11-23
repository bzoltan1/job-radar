"""Salary extraction, currency normalization & compensation scoring stage."""

import html
import re
from typing import Dict, Optional, Tuple

from radar.config import get_salary_expectations
from radar.models import Job, PipelineContext, RawJob, SalaryInfo
from radar.pipeline.base import PipelineStage, StageResult

CURRENCY_RATES = {
    "EUR": 1.0,
    "USD": 0.92,
    "GBP": 1.18,
    "CHF": 1.05,
}


def normalize_to_eur(val: int, currency: str) -> int:
    """Normalize foreign salary amount to EUR equivalent."""
    rate = CURRENCY_RATES.get(currency.upper(), 0.92)
    return int(val * rate)


def extract_salary(raw_job: RawJob) -> SalaryInfo:
    """Extract salary from metadata or raw job description text."""
    # 1. Structured metadata (e.g. Greenhouse custom fields)
    metadata = raw_job.metadata.get("raw", []) if isinstance(raw_job.metadata, dict) else []
    if not isinstance(metadata, list):
        metadata = []
    for m in metadata:
        if isinstance(m, dict) and m.get("value_type") == "currency_range" and m.get("value"):
            v = m["value"]
            unit = v.get("unit", "USD").upper()
            try:
                vmin = int(float(v.get("min_value", 0)))
                vmax = int(float(v.get("max_value", 0)))
                if vmax > 0:
                    norm = normalize_to_eur(vmax, unit)
                    disp = f"{unit} {vmin//1000}k-{vmax//1000}k" if vmin > 0 else f"{unit} {vmax//1000}k"
                    return SalaryInfo(min_val=vmin, max_val=vmax, currency=unit, display=disp, norm_max_eur=norm)
            except (ValueError, TypeError):
                pass

    content = html.unescape(raw_job.content or "")
    if not content:
        return SalaryInfo()

    text = re.sub(r"<[^>]+>", " ", content)

    p1 = re.compile(
        r"([€$£]|EUR|USD|GBP|CHF)\s*([0-9]{2,3}(?:[,\.][0-9]{3})+)\s*(?:-|to|–|and)\s*([€$£]|EUR|USD|GBP|CHF)?\s*([0-9]{2,3}(?:[,\.][0-9]{3})+)",
        re.IGNORECASE,
    )
    p2 = re.compile(
        r"([0-9]{2,3}(?:[,\.][0-9]{3})+)\s*(?:-|to|–|and)\s*([0-9]{2,3}(?:[,\.][0-9]{3})+)\s*([€$£]|EUR|USD|GBP|CHF)",
        re.IGNORECASE,
    )
    p3 = re.compile(
        r"([€$£]|EUR|USD|GBP|CHF)?\s*([0-9]{2,3})\s*k\s*(?:-|to|–|and)\s*([€$£]|EUR|USD|GBP|CHF)?\s*([0-9]{2,3})\s*k",
        re.IGNORECASE,
    )

    matches = []
    for m in p1.finditer(text):
        c1, s1, c2, s2 = m.groups()
        curr = c1 if c1 in ["$", "€", "£", "EUR", "USD", "GBP", "CHF"] else (c2 or "USD")
        curr = {"$": "USD", "€": "EUR", "£": "GBP"}.get(curr, curr.upper())
        v1 = int(re.sub(r"[,.]", "", s1))
        v2 = int(re.sub(r"[,.]", "", s2))
        vmin, vmax = min(v1, v2), max(v1, v2)
        if 25000 <= vmax <= 700000:
            matches.append((vmin, vmax, curr))

    for m in p2.finditer(text):
        s1, s2, curr = m.groups()
        curr = {"$": "USD", "€": "EUR", "£": "GBP"}.get(curr, curr.upper())
        v1 = int(re.sub(r"[,.]", "", s1))
        v2 = int(re.sub(r"[,.]", "", s2))
        vmin, vmax = min(v1, v2), max(v1, v2)
        if 25000 <= vmax <= 700000:
            matches.append((vmin, vmax, curr))

    for m in p3.finditer(text):
        c1, s1, c2, s2 = m.groups()
        curr = c1 or c2 or "USD"
        curr = {"$": "USD", "€": "EUR", "£": "GBP"}.get(curr, curr.upper())
        v1 = int(s1) * 1000
        v2 = int(s2) * 1000
        vmin, vmax = min(v1, v2), max(v1, v2)
        if 25000 <= vmax <= 700000:
            matches.append((vmin, vmax, curr))

    if matches:
        eur_matches = [m for m in matches if m[2] == "EUR"]
        chosen = max(eur_matches, key=lambda x: x[1]) if eur_matches else max(matches, key=lambda x: x[1])
        vmin, vmax, curr = chosen
        norm = normalize_to_eur(vmax, curr)
        disp = f"{curr} {vmin//1000}k-{vmax//1000}k" if vmin != vmax else f"{curr} {vmax//1000}k"
        return SalaryInfo(min_val=vmin, max_val=vmax, currency=curr, display=disp, norm_max_eur=norm)

    return SalaryInfo()


class SalaryStage(PipelineStage):
    """Extracts salary ranges and computes baseline compensation scores."""

    @property
    def name(self) -> str:
        return "salary_stage"

    def process(self, raw_job: RawJob, job: Job, context: PipelineContext) -> StageResult:
        salary_info = extract_salary(raw_job)
        job.salary = salary_info

        score_delta = 0
        tags = []
        norm = salary_info.norm_max_eur

        tiers = get_salary_expectations()  # unset tier (None) is skipped
        high, mid, low = tiers["high"], tiers["mid"], tiers["low"]

        if high is not None and norm >= high:
            score_delta += 35
            tags.append(f"pay:{salary_info.display}(>{high // 1000}k)")
        elif mid is not None and norm >= mid:
            score_delta += 25
            tags.append(f"pay:{salary_info.display}(>{mid // 1000}k)")
        elif low is not None and norm >= low:
            score_delta += 15
            tags.append(f"pay:{salary_info.display}(>={low // 1000}k)")
        elif low is not None and 0 < norm < low:
            score_delta -= 10
            tags.append(f"pay:{salary_info.display}(<{low // 1000}k)")

        return StageResult(should_continue=True, score_delta=score_delta, tags=tags)
