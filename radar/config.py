"""Configuration & YAML data loaders for Job Radar."""

import glob
import os
from typing import Any, Dict, List, Optional
import yaml

from radar.models import CompanyTarget

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
DATA_DIR = os.path.join(BASE_DIR, "data")
INTEL_DIR = os.path.join(DATA_DIR, "intel")


def load_dotenv_if_present(dotenv_path: Optional[str] = None):
    """Load key-value pairs from .env into os.environ without overwriting existing environment variables."""
    if dotenv_path is None:
        dotenv_path = os.path.join(BASE_DIR, ".env")
    if not os.path.exists(dotenv_path):
        return
    try:
        with open(dotenv_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and k not in os.environ:
                    os.environ[k] = v
    except Exception:
        pass


# Automatically load local .env if present
load_dotenv_if_present()

SETTINGS_FILE = (
    os.environ.get("JOB_RADAR_CONFIG")
    or (os.path.join(DATA_DIR, "settings.yaml") if os.path.exists(os.path.join(DATA_DIR, "settings.yaml")) else None)
    or (os.path.join(BASE_DIR, "config.yaml") if os.path.exists(os.path.join(BASE_DIR, "config.yaml")) else None)
)

PROFILE_FILE = (
    os.environ.get("JOB_RADAR_PROFILE")
    or (os.path.join(DATA_DIR, "profile.local.yaml") if os.path.exists(os.path.join(DATA_DIR, "profile.local.yaml")) else None)
    or (os.path.join(DATA_DIR, "profile.yaml") if os.path.exists(os.path.join(DATA_DIR, "profile.yaml")) else None)
    or (os.path.join(BASE_DIR, "profile.yaml") if os.path.exists(os.path.join(BASE_DIR, "profile.yaml")) else None)
    or os.path.join(DATA_DIR, "profile.example.yaml")
)

TARGETS_FILE = (
    os.environ.get("JOB_RADAR_TARGETS")
    or (os.path.join(DATA_DIR, "targets.yaml") if os.path.exists(os.path.join(DATA_DIR, "targets.yaml")) else None)
    or os.path.join(BASE_DIR, "targets.yaml")
)

LEGACY_INTEL_FILE = os.path.join(BASE_DIR, "company_intel.yaml")

DB_PATH = os.environ.get("JOB_RADAR_DB") or os.path.join(BASE_DIR, "jobs.db")
FEED_PATH = os.environ.get("JOB_RADAR_FEED") or os.path.join(BASE_DIR, "feed.xml")


def load_settings() -> dict:
    """Load optional global settings from config.yaml or data/settings.yaml."""
    if SETTINGS_FILE and os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                return yaml.safe_load(f) or {}
        except Exception:
            return {}
    return {}


def load_profile() -> dict:
    """Load candidate career profile, domain expertise, and scoring weights."""
    if not PROFILE_FILE or not os.path.exists(PROFILE_FILE):
        return {}
    with open(PROFILE_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def get_candidate_info() -> Dict[str, Any]:
    """Retrieve structured candidate identity and preferences."""
    prof = load_profile()
    cand = prof.get("candidate", {})
    return {
        "name": cand.get("name", "Candidate"),
        "headline": cand.get("headline", "Systems & Platform Engineer"),
        "current_role": cand.get("current_role", ""),
        "experience_years": cand.get("experience_years", 10),
        "location": os.environ.get("CANDIDATE_LOCATION") or cand.get("location", "Italy"),
        "allowed_locations": cand.get("allowed_locations", ["Italy", "Austria"]),
        "contract_preference": cand.get("contract_preference", "Employee contract"),
        "website": cand.get("website", ""),
    }


def get_salary_expectations() -> Dict[str, int]:
    """Retrieve salary threshold tiers (EUR equivalent) for scoring and alerts."""
    prof = load_profile()
    comp = prof.get("compensation", {}) or prof.get("salary_expectations", {})
    return {
        "high": int(comp.get("target_high", 150000)),
        "mid": int(comp.get("target_mid", 120000)),
        "low": int(comp.get("target_low", 85000)),
    }


def get_location_config() -> Dict[str, Any]:
    """Retrieve candidate target country and allowed secondary locations."""
    cand = get_candidate_info()
    primary = (
        os.environ.get("CANDIDATE_COUNTRY")
        or os.environ.get("CANDIDATE_LOCATION")
        or cand.get("location", "Italy")
    ).strip()

    allowed_env = os.environ.get("CANDIDATE_ALLOWED_COUNTRIES")
    if allowed_env:
        allowed = [c.strip() for c in allowed_env.split(",") if c.strip()]
    else:
        raw_allowed = cand.get("allowed_locations", ["Austria"])
        if isinstance(raw_allowed, list):
            allowed = [c.strip() for c in raw_allowed if c.strip()]
        elif isinstance(raw_allowed, str):
            allowed = [c.strip() for c in raw_allowed.split(",") if c.strip()]
        else:
            allowed = []

    return {
        "primary_country": primary,
        "allowed_countries": allowed,
    }


def get_obsidian_vault_path() -> str:
    """Resolve Obsidian vault directory from environment, config, or default."""
    settings = load_settings()
    vault = (
        os.environ.get("OBSIDIAN_VAULT_PATH")
        or os.environ.get("JOB_RADAR_OBSIDIAN_VAULT")
        or settings.get("obsidian", {}).get("vault_path")
        or os.path.expanduser("~/vault/career")
    )
    return os.path.expanduser(vault)


def get_telegram_config() -> Dict[str, Any]:
    """Resolve Telegram bot credentials and notification thresholds."""
    settings = load_settings()
    tg_settings = settings.get("telegram", {})

    token = os.environ.get("TELEGRAM_BOT_TOKEN") or tg_settings.get("bot_token")
    legacy_cfg_path = os.path.expanduser("~/.config/telegram_acp_bot/config.json")
    if not token and os.path.exists(legacy_cfg_path):
        try:
            import json
            with open(legacy_cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            token = cfg.get("telegram", {}).get("bot_token")
        except Exception:
            pass

    chat_id_val = os.environ.get("TELEGRAM_CHAT_ID") or tg_settings.get("chat_id")
    chat_id = int(chat_id_val) if chat_id_val else None

    min_score_val = os.environ.get("JOB_RADAR_NOTIFY_MIN_SCORE") or tg_settings.get("min_score", 85)
    min_score = int(min_score_val)

    min_sal_val = os.environ.get("JOB_RADAR_NOTIFY_MIN_SALARY") or tg_settings.get("min_salary", 150000)
    min_salary = int(min_sal_val)

    return {
        "bot_token": token,
        "chat_id": chat_id,
        "min_score": min_score,
        "min_salary": min_salary,
    }


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
