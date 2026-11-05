#!/usr/bin/env python3
"""Analysis of Markdown blog posts to extract domain pillars and keywords for profile.yaml."""

import glob
import os
import re
import sys
from collections import Counter

POSTS_DIR = os.environ.get("BLOG_POSTS_DIR") or (sys.argv[1] if len(sys.argv) > 1 else "")
if not POSTS_DIR or not os.path.isdir(POSTS_DIR):
    print("Usage: python3 analyze_blog.py <path_to_markdown_posts_dir>")
    print("Or set BLOG_POSTS_DIR environment variable.")
    sys.exit(0 if not POSTS_DIR else 1)
files = glob.glob(os.path.join(POSTS_DIR, "*.md"))
posts = []

for f in files:
    with open(f, "r", encoding="utf-8", errors="ignore") as fp:
        raw = fp.read()

    # Frontmatter regex
    date_m = re.search(r'date\s*[:=]\s*["\']?([0-9]{4}-[0-9]{2}-[0-9]{2})', raw)
    title_m = re.search(r'title\s*[:=]\s*["\']([^"\']+)["\']', raw)
    tags_m = re.search(r'tags\s*[:=]\s*\[(.*?)\]', raw, re.DOTALL)

    date = date_m.group(1) if date_m else "1970-01-01"
    title = title_m.group(1) if title_m else os.path.basename(f)
    tags = [t.strip().strip('"').strip("'") for t in tags_m.group(1).split(",")] if tags_m else []

    body = raw
    for delim in ["+++", "---"]:
        if delim in raw:
            parts = raw.split(delim)
            if len(parts) >= 3:
                body = parts[2]
                break

    posts.append({
        "file": os.path.basename(f),
        "path": f,
        "date": date,
        "title": title,
        "tags": [t for t in tags if t],
        "content": body.strip(),
    })

posts.sort(key=lambda x: x["date"], reverse=True)
latest_48 = posts[:48]

print(f"Total posts analyzed: {len(latest_48)}")
print("=" * 80)

# Categorization clusters
clusters = {
    "eBPF, Tracing & Binary Coverage": [],
    "Linux Internals, Kernel & Sandboxing": [],
    "Containers, Podman & systemd": [],
    "QA Automation, openQA & Test Frameworks": [],
    "Languages & Systems Programming (Go, Rust, C, Zig)": [],
    "Networking, D-Bus & Fault Injection": [],
    "Hardware, Power, Storage & Embedded": [],
}

for idx, p in enumerate(latest_48, 1):
    title = p["title"]
    text = (title + " " + p["content"]).lower()
    
    assigned = []
    if any(k in text for k in ["ebpf", "pintool", "ftrace", "binary_coverage", "coverage", "dlopen"]):
        clusters["eBPF, Tracing & Binary Coverage"].append(title)
        assigned.append("Tracing/eBPF")
    if any(k in text for k in ["landlock", "capabilities", "kernel", "linux test project", "ltp", "segfault", "kexec", "instant reboot"]):
        clusters["Linux Internals, Kernel & Sandboxing"].append(title)
        assigned.append("Kernel/Internals")
    if any(k in text for k in ["quadlet", "podman", "systemd", "socket-activated", "container"]):
        clusters["Containers, Podman & systemd"].append(title)
        assigned.append("Containers/systemd")
    if any(k in text for k in ["openqa", "test project", "testing", "unit_testing", "job-filter"]):
        clusters["QA Automation, openQA & Test Frameworks"].append(title)
        assigned.append("QA/openQA")
    if any(k in text for k in ["rust", "golang", "go", "bubbletea", "zig", "dlang", "nim", "c++"]):
        clusters["Languages & Systems Programming (Go, Rust, C, Zig)"].append(title)
        assigned.append("Languages")
    if any(k in text for k in ["faulty_network", "faulty_disk", "dbus", "d-bus", "wifi", "network"]):
        clusters["Networking, D-Bus & Fault Injection"].append(title)
        assigned.append("Networking/Faults")
    if any(k in text for k in ["microsd", "thinkpad", "power consumption", "qboot", "qemu", "arm"]):
        clusters["Hardware, Power, Storage & Embedded"].append(title)
        assigned.append("Hardware/Virt")

    print(f"{idx:2d}. [{p['date']}] {title}")
    print(f"    Categories: {', '.join(assigned) if assigned else 'General'}")
    print(f"    File: {p['file']}")

print("\n" + "=" * 80)
print("DOMAIN EXPERTISE CLUSTERS BREAKDOWN:")
for cat, items in clusters.items():
    print(f"\n### {cat} ({len(items)} posts):")
    for it in items[:6]:
        print(f"  * {it}")
