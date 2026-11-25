"""Company discovery & CNCF landscape exploration."""

import functools
import json
import os
import sys
import urllib.request
import yaml

from radar.config import DATA_DIR, TARGETS_FILE, TARGETS_WRITE_FILE

PEER_CATALOG_FILE = os.path.join(DATA_DIR, "peer_catalog.yaml")


@functools.lru_cache(maxsize=1)
def load_peer_catalog() -> list:
    """Curated peer companies from data/peer_catalog.yaml."""
    with open(PEER_CATALOG_FILE, "r", encoding="utf-8") as f:
        return (yaml.safe_load(f) or {}).get("peers", [])


def load_tracked_ids():
    if not os.path.exists(TARGETS_FILE):
        return set()
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {c["id"] for c in data.get("companies", [])}


def list_peers(category=None, tier=None, home_only=False):
    tracked = load_tracked_ids()
    print(f"\n{'ID':<15} | {'NAME':<20} | {'TIER':<16} | {'EOR':<5} | {'STATUS'}")
    print("-" * 80)
    for p in load_peer_catalog():
        if category and category.lower() not in p["category"].lower():
            continue
        if tier and tier.lower() != p["tier"].lower():
            continue
        if home_only and not p["eor_supported"]:
            continue

        status = "[TRACKED]" if p["id"] in tracked else "[AVAILABLE]"
        eor = "YES" if p["eor_supported"] else "NO"
        print(f"{p['id']:<15} | {p['name']:<20} | {p['tier']:<16} | {eor:<5} | {status}")


def add_peer(company_id: str):
    target_id = company_id.lower()
    match = next((p for p in load_peer_catalog() if p["id"].lower() == target_id), None)
    if not match:
        sys.exit(f"Company ID '{target_id}' not found in discovery catalog.")

    # Seed the personal list from the active one (e.g. the example) on first add.
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    existing_ids = {c["id"] for c in data.get("companies", [])}
    if target_id in existing_ids:
        print(f"[!] Company '{target_id}' already tracked in targets.yaml.")
        return

    data.setdefault("companies", []).append(match)
    with open(TARGETS_WRITE_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

    print(f"[+] Added {match['name']} ({match['id']}) to {os.path.relpath(TARGETS_WRITE_FILE)}.")


def query_cncf(query: str, limit: int = 20):
    print(f"[*] Fetching CNCF Landscape index for '{query}'...")
    url = "https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml"
    req = urllib.request.Request(url, headers={"User-Agent": "JobRadar/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = yaml.safe_load(resp)
    except Exception as e:
        sys.exit(f"Error downloading CNCF landscape: {e}")

    q = query.lower()
    matches = []
    for cat in data.get("landscape", []):
        cat_name = cat.get("name", "")
        for sub in cat.get("subcategories", []):
            sub_name = sub.get("name", "")
            for item in sub.get("items", []):
                name = item.get("name", "").replace(" (member)", "")
                hp = item.get("homepage_url", "")
                if q in name.lower() or q in cat_name.lower() or q in sub_name.lower():
                    matches.append({
                        "name": name,
                        "category": f"{cat_name} / {sub_name}",
                        "url": hp,
                    })

    print(f"\nFound {len(matches)} CNCF entities matching '{query}':")
    for m in matches[:limit]:
        print(f"  - {m['name']:<25} | {m['category']:<40} | {m['url']}")
