"""Configuration & YAML data loaders for Job Radar."""

import glob
import os
from typing import Dict, List, Optional
import yaml

from radar.models import CompanyTarget

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
INTEL_DIR = os.path.join(DATA_DIR, "intel")

PROFILE_FILE = os.path.join(DATA_DIR, "profile.yaml") if os.path.exists(os.path.join(DATA_DIR, "profile.yaml")) else os.path.join(BASE_DIR, "profile.yaml")
TARGETS_FILE = os.path.join(DATA_DIR, "targets.yaml") if os.path.exists(os.path.join(DATA_DIR, "targets.yaml")) else os.path.join(BASE_DIR, "targets.yaml")
LEGACY_INTEL_FILE = os.path.join(BASE_DIR, "company_intel.yaml")

DB_PATH = os.path.join(BASE_DIR, "jobs.db")
FEED_PATH = os.path.join(BASE_DIR, "feed.xml")


def load_profile() -> dict:
    """Load candidate career profile and scoring weights."""
    if not os.path.exists(PROFILE_FILE):
        return {}
    with open(PROFILE_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_targets() -> List[CompanyTarget]:
    """Load target companies list."""
    if not os.path.exists(TARGETS_FILE):
        return []
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    raw_list = data.get("companies", [])
    targets = []
    for c in raw_list:
        targets.append(
            CompanyTarget(
                id=c["id"],
                name=c.get("name", c["id"].capitalize()),
                tier=c.get("tier", "scaleup"),
                category=c.get("category", ""),
                ats=c.get("ats", "greenhouse"),
                board=c.get("board", c["id"]),
                entity_in_italy=c.get("entity_in_italy", False),
                eor_supported=c.get("eor_supported", True),
                allow_austria=c.get("allow_austria", False),
                notes=c.get("notes", ""),
                site=c.get("site", "jobs"),
                sub_domain=c.get("sub_domain", "wd5"),
                extra=c,
            )
        )
    return targets


def load_all_intel() -> Dict[str, dict]:
    """Load all company intel dossiers from data/intel/*.yaml."""
    intel_map = {}
    if os.path.isdir(INTEL_DIR):
        for path in glob.glob(os.path.join(INTEL_DIR, "*.yaml")):
            cid = os.path.splitext(os.path.basename(path))[0]
            try:
                with open(path, "r", encoding="utf-8") as f:
                    intel_map[cid] = yaml.safe_load(f) or {}
            except Exception:
                pass

    if not intel_map and os.path.exists(LEGACY_INTEL_FILE):
        with open(LEGACY_INTEL_FILE, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
            intel_map = data.get("companies", {})

    return intel_map


def load_company_intel(company_id: str) -> Optional[dict]:
    """Load dossier for a specific company."""
    specific_path = os.path.join(INTEL_DIR, f"{company_id.lower()}.yaml")
    if os.path.exists(specific_path):
        with open(specific_path, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    all_intel = load_all_intel()
    return all_intel.get(company_id.lower())
