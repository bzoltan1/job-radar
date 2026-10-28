"""Company discovery & CNCF landscape exploration."""

import json
import os
import sys
import urllib.request
import yaml

from radar.config import TARGETS_FILE

PEER_CATALOG = [
    {
        "id": "canonical",
        "name": "Canonical",
        "category": "Linux & OS",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "canonical",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Ubuntu creators. Home based EMEA/Worldwide. EOR in Italy.",
    },
    {
        "id": "redhat",
        "name": "Red Hat",
        "category": "Linux & OS",
        "tier": "big_tech",
        "ats": "workday",
        "board": "redhat",
        "site": "jobs",
        "sub_domain": "wd5",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Red Hat Italy S.r.l. Primary <employer> peer. Enterprise Linux, OpenShift, Kernel.",
    },
    {
        "id": "intel",
        "name": "Intel",
        "category": "Silicon & Systems",
        "tier": "big_tech",
        "ats": "workday",
        "board": "intel",
        "site": "External",
        "sub_domain": "wd1",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Intel Corporation Italia S.p.A. Linux kernel, toolchains, low-level systems.",
    },
    {
        "id": "arm",
        "name": "Arm",
        "category": "Silicon & Systems",
        "tier": "big_tech",
        "ats": "smartrecruiters",
        "board": "Arm",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Arm architecture, Linux kernel enablement, toolchain, firmware.",
    },
    {
        "id": "datadog",
        "name": "Datadog",
        "category": "Observability",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "datadog",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Datadog Italy S.r.l. Major eBPF, Go, C, Linux kernel observability stack.",
    },
    {
        "id": "grafanalabs",
        "name": "Grafana Labs",
        "category": "Observability",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "grafanalabs",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Fully distributed. Explicit 'Italy (Remote)' listings. Go, eBPF, Prometheus.",
    },
    {
        "id": "sysdig",
        "name": "Sysdig",
        "category": "Container & eBPF Security",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "sysdig",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Sysdig Italy S.r.l. with Milan hub. eBPF, Falco creators, runtime security agent.",
    },
    {
        "id": "cloudflare",
        "name": "Cloudflare",
        "category": "Edge & Networking",
        "tier": "big_tech",
        "ats": "greenhouse",
        "board": "cloudflare",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Cloudflare Italy S.r.l. Linux network stack, eBPF/XDP, kernel tuning, Go/Rust.",
    },
    {
        "id": "elastic",
        "name": "Elastic",
        "category": "Search & Observability",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "elastic",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Distributed by design. Hires remote employees in Italy.",
    },
    {
        "id": "gitlab",
        "name": "GitLab",
        "category": "DevOps & Cloud",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "gitlab",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "All-remote company. EOR-based hiring across EMEA.",
    },
    {
        "id": "docker",
        "name": "Docker",
        "category": "Containers & Runtime",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "docker",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Docker Desktop, Linux containers, buildx. Explicit Italy remote listings.",
    },
    {
        "id": "siderolabs",
        "name": "Sidero Labs",
        "category": "Immutable OS & Kubernetes",
        "tier": "scaleup",
        "ats": "sidero",
        "board": "siderolabs",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Creators of Talos Linux. 100% Go & Linux kernel immutable platform.",
    },
    {
        "id": "proxmox",
        "name": "Proxmox Server Solutions",
        "category": "Virtualization & Storage",
        "tier": "scaleup",
        "ats": "proxmox",
        "board": "proxmox",
        "entity_in_italy": False,
        "eor_supported": False,
        "allow_austria": True,
        "notes": "Vienna Austria headquarters. Proxmox VE, Debian, Linux kernel, QEMU/KVM, ZFS.",
    },
    {
        "id": "ciq",
        "name": "CIQ (Ctrl IQ)",
        "category": "Enterprise Linux & HPC",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "ciq",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Rocky Linux commercial sponsor. Linux kernel live patching. 100% remote.",
    },
]


def load_tracked_ids():
    if not os.path.exists(TARGETS_FILE):
        return set()
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}
    return {c["id"] for c in data.get("companies", [])}


def list_peers(category=None, tier=None, italy_only=False):
    tracked = load_tracked_ids()
    print(f"\n{'ID':<15} | {'NAME':<20} | {'TIER':<16} | {'IT ENTITY':<9} | {'EOR':<5} | {'STATUS'}")
    print("-" * 80)
    for p in PEER_CATALOG:
        if category and category.lower() not in p["category"].lower():
            continue
        if tier and tier.lower() != p["tier"].lower():
            continue
        if italy_only and not (p["entity_in_italy"] or p["eor_supported"]):
            continue

        status = "[TRACKED]" if p["id"] in tracked else "[AVAILABLE]"
        it_ent = "YES" if p["entity_in_italy"] else "NO"
        eor = "YES" if p["eor_supported"] else "NO"
        print(f"{p['id']:<15} | {p['name']:<20} | {p['tier']:<16} | {it_ent:<9} | {eor:<5} | {status}")


def add_peer(company_id: str):
    target_id = company_id.lower()
    match = next((p for p in PEER_CATALOG if p["id"].lower() == target_id), None)
    if not match:
        sys.exit(f"Company ID '{target_id}' not found in discovery catalog.")

    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f) or {}

    existing_ids = {c["id"] for c in data.get("companies", [])}
    if target_id in existing_ids:
        print(f"[!] Company '{target_id}' already tracked in targets.yaml.")
        return

    data.setdefault("companies", []).append(match)
    with open(TARGETS_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

    print(f"[+] Added {match['name']} ({match['id']}) to targets.yaml successfully.")


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
