#!/usr/bin/env python3
"""Job Radar Company Discovery: Discover & qualify companies similar to <employer>."""

import argparse
import json
import os
import sys
import urllib.request
import yaml

TARGETS_FILE = os.path.join(os.path.dirname(__file__), "targets.yaml")
CATALOG_FILE = os.path.join(os.path.dirname(__file__), "catalog.yaml")

# Curated catalog of enterprise systems, Linux, observability, and cloud infrastructure companies
PEER_CATALOG = [
    # Linux & Core OS
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
    # Observability & eBPF
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
        "notes": "Prometheus, Grafana, Beyla (eBPF). Remote in Italy via EOR.",
    },
    {
        "id": "elastic",
        "name": "Elastic",
        "category": "Observability & Search",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "elastic",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Distributed by design. Elasticsearch B.V. Italian contracts.",
    },
    {
        "id": "dynatrace",
        "name": "Dynatrace",
        "category": "Observability",
        "tier": "enterprise_infra",
        "ats": "dynatrace",
        "board": "dynatrace",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Dynatrace Italy S.r.l. Deep Linux agents, eBPF, tracing.",
    },
    {
        "id": "sysdig",
        "name": "Sysdig",
        "category": "Security & eBPF",
        "tier": "enterprise_infra",
        "ats": "lever",
        "board": "sysdig",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Sysdig Italy S.r.l. (Italian founders, offices in Milan). Falco / eBPF security.",
    },
    # Edge, Networking & Cloud Infra
    {
        "id": "aws",
        "name": "Amazon Web Services (AWS)",
        "category": "Cloud Infrastructure & OS",
        "tier": "big_tech",
        "ats": "amazon",
        "board": "amazon",
        "entity_in_italy": True,
        "eor_supported": True,
        "notes": "Amazon Italia Services S.r.l. (Milan & Asti NICE DCV). Bottlerocket, Amazon Linux, Firecracker, Linux Kernel.",
    },
    {
        "id": "siderolabs",
        "name": "Sidero Labs",
        "category": "Container OS & Kubernetes",
        "tier": "scaleup",
        "ats": "sidero",
        "board": "siderolabs",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Talos Linux, Omni. 100% remote. Go, Linux kernel, immutable OS.",
    },
    {
        "id": "proxmox",
        "name": "Proxmox Server Solutions",
        "category": "Virtualization & Linux Platform",
        "tier": "enterprise_infra",
        "ats": "proxmox",
        "board": "proxmox",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Proxmox VE, PBS, Kernel, QEMU/KVM, Debian, Rust. Vienna / Remote.",
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
        "notes": "Cloudflare Italy S.r.l. Heavy Linux kernel tuning, XDP, eBPF, Go/Rust.",
    },
    {
        "id": "fastly",
        "name": "Fastly",
        "category": "Edge & Networking",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "fastly",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Edge compute, Linux systems, networking.",
    },
    # Containers & Cloud Native
    {
        "id": "docker",
        "name": "Docker",
        "category": "Containers",
        "tier": "enterprise_infra",
        "ats": "ashby",
        "board": "docker",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Container tooling, Go, Linux cgroups/namespaces.",
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
        "notes": "100% remote. CXC / EOR employee contracts in Italy.",
    },
    {
        "id": "cockroachlabs",
        "name": "Cockroach Labs",
        "category": "Distributed Systems",
        "tier": "scaleup",
        "ats": "greenhouse",
        "board": "cockroachlabs",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Distributed SQL, Go, storage engine.",
    },
    {
        "id": "temporal",
        "name": "Temporal Technologies",
        "category": "Orchestration",
        "tier": "scaleup",
        "ats": "ashby",
        "board": "temporal",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Durable execution, Go, distributed coordination.",
    },
    {
        "id": "chainguard",
        "name": "Chainguard",
        "category": "Container OS & Supply Chain",
        "tier": "scaleup",
        "ats": "greenhouse",
        "board": "chainguard",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Wolfi Linux, minimal container OS, apk packaging, security. 100% remote.",
    },
    {
        "id": "clickhouse",
        "name": "ClickHouse",
        "category": "Distributed Systems",
        "tier": "enterprise_infra",
        "ats": "ashby",
        "board": "clickhouse",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Columnar OLAP engine, C++20, high-performance systems. EMEA remote pool.",
    },
    {
        "id": "supabase",
        "name": "Supabase",
        "category": "Cloud Platform & Data",
        "tier": "scaleup",
        "ats": "ashby",
        "board": "supabase",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Open source cloud platform, Postgres, Go, containers, microVMs. 100% remote.",
    },
    {
        "id": "tailscale",
        "name": "Tailscale",
        "category": "Networking & Security",
        "tier": "scaleup",
        "ats": "greenhouse",
        "board": "tailscale",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "WireGuard mesh networking, Go, Linux network stack. 100% remote.",
    },
    {
        "id": "sentry",
        "name": "Sentry",
        "category": "Observability",
        "tier": "enterprise_infra",
        "ats": "ashby",
        "board": "sentry",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "Crash symbolication, native DWARF/ELF inspection, Rust, tracing. Remote in Europe & US.",
    },
    {
        "id": "backblaze",
        "name": "Backblaze",
        "category": "Cloud Storage & Infra",
        "tier": "enterprise_infra",
        "ats": "greenhouse",
        "board": "backblaze",
        "entity_in_italy": False,
        "eor_supported": True,
        "notes": "B2 Cloud Storage, Storage Pods, ZFS/ext4, distributed storage. US/LATAM/Europe DC.",
    },
]


def load_tracked_ids():
    if not os.path.exists(TARGETS_FILE):
        return set()
    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return {c["id"] for c in data.get("companies", [])}


def cmd_list(args):
    tracked = load_tracked_ids()
    print(f"\n{'ID':<15} | {'NAME':<20} | {'TIER':<16} | {'IT ENTITY':<9} | {'EOR':<5} | {'STATUS'}")
    print("-" * 80)
    for p in PEER_CATALOG:
        if args.category and args.category.lower() not in p["category"].lower():
            continue
        if args.tier and args.tier.lower() != p["tier"].lower():
            continue
        if args.italy_only and not (p["entity_in_italy"] or p["eor_supported"]):
            continue

        status = "[TRACKED]" if p["id"] in tracked else "[AVAILABLE]"
        it_ent = "YES" if p["entity_in_italy"] else "NO"
        eor = "YES" if p["eor_supported"] else "NO"
        print(f"{p['id']:<15} | {p['name']:<20} | {p['tier']:<16} | {it_ent:<9} | {eor:<5} | {status}")


def cmd_add(args):
    target_id = args.company_id.lower()
    match = next((p for p in PEER_CATALOG if p["id"].lower() == target_id), None)
    if not match:
        sys.exit(f"Company ID '{target_id}' not found in discovery catalog.")

    with open(TARGETS_FILE, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    existing_ids = {c["id"] for c in data.get("companies", [])}
    if target_id in existing_ids:
        print(f"[!] Company '{target_id}' already tracked in targets.yaml.")
        return

    data.setdefault("companies", []).append(match)
    with open(TARGETS_FILE, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, sort_keys=False, allow_unicode=True)

    print(f"[+] Added {match['name']} ({match['id']}) to targets.yaml successfully.")


def cmd_query_cncf(args):
    print("[*] Fetching CNCF Landscape index...")
    url = "https://raw.githubusercontent.com/cncf/landscape/master/landscape.yml"
    req = urllib.request.Request(url, headers={"User-Agent": "JobRadar/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = yaml.safe_load(resp)
    except Exception as e:
        sys.exit(f"Error downloading CNCF landscape: {e}")

    query = args.query.lower()
    matches = []
    for cat in data.get("landscape", []):
        cat_name = cat.get("name", "")
        for sub in cat.get("subcategories", []):
            sub_name = sub.get("name", "")
            for item in sub.get("items", []):
                name = item.get("name", "").replace(" (member)", "")
                hp = item.get("homepage_url", "")
                if query in name.lower() or query in cat_name.lower() or query in sub_name.lower():
                    matches.append({
                        "name": name,
                        "category": f"{cat_name} / {sub_name}",
                        "url": hp,
                    })

    print(f"\nFound {len(matches)} CNCF entities matching '{query}':")
    for m in matches[:args.limit]:
        print(f"  - {m['name']:<25} | {m['category']:<40} | {m['url']}")


def main():
    parser = argparse.ArgumentParser(description="Job Radar Company Discovery")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List curated peer companies")
    p_list.add_argument("--category", help="Filter by category (e.g. Linux, Observability, Edge)")
    p_list.add_argument("--tier", help="Filter by tier (big_tech, enterprise_infra, scaleup)")
    p_list.add_argument("--italy-only", action="store_true", help="Only show with Italy entity or EOR")

    p_add = sub.add_parser("add", help="Add company from catalog to active targets")
    p_add.add_argument("company_id", help="Company ID to track")

    p_cncf = sub.add_parser("cncf", help="Search CNCF landscape for cloud-native companies")
    p_cncf.add_argument("query", help="Keyword (e.g., storage, runtime, ebpf, kubernetes)")
    p_cncf.add_argument("--limit", type=int, default=20, help="Max results")

    args = parser.parse_args()
    if args.command == "list":
        cmd_list(args)
    elif args.command == "add":
        cmd_add(args)
    elif args.command == "cncf":
        cmd_query_cncf(args)


if __name__ == "__main__":
    main()
