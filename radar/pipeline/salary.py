"""Salary extraction, currency normalization & compensation scoring stage."""

import html
import re
from typing import List, Optional, Tuple

from radar.config import get_salary_expectations
from radar.models import Job, PipelineContext, RawJob, SalaryInfo
from radar.pipeline.base import PipelineStage, StageResult

CURRENCY_RATES = {
    "EUR": 1.0,
    "USD": 0.92,
    "GBP": 1.18,
    "CHF": 1.05,
}

_SYMBOLS = {"$": "USD", "€": "EUR", "£": "GBP"}
_CUR = r"[€$£]|EUR|USD|GBP|CHF"
_AMOUNT = r"[0-9]{2,3}(?:[,\.][0-9]{3})+"  # 120,000 / 120.000
_K = r"[0-9]{2,3}(?:\.[0-9]+)?"  # 120 / 120.5 (followed by k)
_SEP = r"\s*(?:-|to|–|and)\s*"
MIN_PLAUSIBLE, MAX_PLAUSIBLE = 25000, 700000  # yearly, any currency; filters hourly rates, equity, phone numbers

_RANGE_CUR_FIRST = re.compile(rf"({_CUR})\s*({_AMOUNT}){_SEP}({_CUR})?\s*({_AMOUNT})", re.IGNORECASE)
_RANGE_CUR_LAST = re.compile(rf"({_AMOUNT}){_SEP}({_AMOUNT})\s*({_CUR})", re.IGNORECASE)
_RANGE_K = re.compile(rf"({_CUR})?\s*({_K})\s*k{_SEP}({_CUR})?\s*({_K})\s*k", re.IGNORECASE)
_SINGLE_K = re.compile(rf"({_CUR})\s*({_K})\s*k\b", re.IGNORECASE)


def _currency(token: Optional[str]) -> str:
    """Currency symbol or code (any case) -> ISO code; USD when absent."""
    return _SYMBOLS.get(token, (token or "USD").upper())


def _digits(s: str) -> int:
    return int(re.sub(r"[,.]", "", s))


def normalize_to_eur(val: int, currency: str) -> int:
    """Normalize a salary amount to EUR; 0 for a currency without a known rate (never guess)."""
    rate = CURRENCY_RATES.get(currency.upper())
    return int(val * rate) if rate else 0


def _find_amounts(text: str) -> List[Tuple[int, int, str]]:
    """All plausible (min, max, currency) salary mentions in free text."""
    found = []
    for m in _RANGE_CUR_FIRST.finditer(text):
        c1, s1, _c2, s2 = m.groups()
        found.append((_digits(s1), _digits(s2), _currency(c1)))
    for m in _RANGE_CUR_LAST.finditer(text):
        s1, s2, c = m.groups()
        found.append((_digits(s1), _digits(s2), _currency(c)))
    for m in _RANGE_K.finditer(text):
        c1, s1, c2, s2 = m.groups()
        found.append((int(float(s1) * 1000), int(float(s2) * 1000), _currency(c1 or c2)))
    for m in _SINGLE_K.finditer(text):
        c, s = m.groups()
        v = int(float(s) * 1000)
        found.append((v, v, _currency(c)))
    return [
        (min(lo, hi), max(lo, hi), cur)
        for lo, hi, cur in found
        if MIN_PLAUSIBLE <= max(lo, hi) <= MAX_PLAUSIBLE
    ]


def _salary_info(vmin: int, vmax: int, currency: str) -> SalaryInfo:
    disp = f"{currency} {vmin // 1000}k-{vmax // 1000}k" if vmin not in (0, vmax) else f"{currency} {vmax // 1000}k"
    return SalaryInfo(min_val=vmin, max_val=vmax, currency=currency, display=disp, norm_max_eur=normalize_to_eur(vmax, currency))


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
            except (ValueError, TypeError):
                continue
            if vmax > 0:
                return _salary_info(vmin, vmax, unit)

    content = html.unescape(raw_job.content or "")
    if not content:
        return SalaryInfo()

    matches = _find_amounts(re.sub(r"<[^>]+>", " ", content))
    if not matches:
        return SalaryInfo()
    eur = [m for m in matches if m[2] == "EUR"]
    return _salary_info(*max(eur or matches, key=lambda x: x[1]))


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
