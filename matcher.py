#!/usr/bin/env python3
"""Job Radar Profile Matcher, Stale Role Detector & Feed Generator."""

import datetime
import html
import os
import re
import xml.etree.ElementTree as ET
import yaml

PROFILE_FILE = os.path.join(os.path.dirname(__file__), "profile.yaml")


def load_profile():
    if not os.path.exists(PROFILE_FILE):
        return None
    with open(PROFILE_FILE, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


PROFILE = load_profile()


def evaluate_profile_match(job_title: str, job_content: str, company_id: str):
    """Compute personalized match percentage, matched skills, gaps, and custom pitch."""
    text = f"{job_title} {job_content}".lower()

    # Domain matrix synthesized from the latest 48 blog posts & career plan
    SKILL_MATRIX = [
        # 1. eBPF & Dynamic Instrumentation
        (
            r"\bebpf\b|\bbpf\b|\buprobe\b|\bftrace\b",
            "eBPF & Kernel Tracing",
            30,
            "Highlight your 5-part research on binary-coverage research: measuring precompiled binary test coverage via eBPF uprobes and kernel ftrace with zero recompile overhead."
        ),
        (
            r"\bpintool\b|\bdynamic binary\b|\bdlopen\b|\belf\b|\bgot\b|\bplt\b",
            "Binary Instrumentation & Dynamic Linking",
            25,
            "Reference your Intel PinTool DBI analysis and dynamic library hooking (dlopen/PLT/GOT dynamic symbol resolution)."
        ),
        # 2. Kernel Security, Sandboxing & Capabilities
        (
            r"\bkernel\b",
            "Linux Kernel",
            25,
            "Emphasize Linux Test Project (LTP) test development and kernel ftrace/debugging experience at <employer>."
        ),
        (
            r"\blandlock\b|\bcapabilities\b|\bseccomp\b|\bsandbox\b",
            "Kernel Sandboxing & Capabilities",
            25,
            "Point to your technical publications on Linux Landlock unprivileged LSM sandboxing, Linux Capabilities, and seccomp syscall filtering."
        ),
        # 3. OS Testing, Reliability & Fault Injection
        (
            r"\bltp\b|\blinux test project\b|\bkexec\b",
            "LTP & OS Reliability",
            25,
            "Highlight your experience running and extending the Linux Test Project (LTP) and instant kernel reboots with kexec."
        ),
        (
            r"\bfault injection\b|\bchaos\b|\bnetns\b|\btrafic control\b|\btc\b|\bnetem\b",
            "Fault Injection & Simulation",
            20,
            "Note your work simulating edge failures: network namespace packet loss/latency injection with NetEm and disk failures with dm-flakey."
        ),
        (
            r"\bopenqa\b|\bautomated testing\b|\bqe\b|\bos validation\b",
            "openQA & OS Validation",
            20,
            "Highlight your current <employer> QE automation role: automating openQA test job matrix cloning via REST APIs and custom tooling."
        ),
        # 4. Containers, systemd & Virtualization
        (
            r"\bsystemd\b|\bsocket activation\b",
            "systemd Plumbing",
            20,
            "Reference your blog guides on declarative systemd socket-activated services (SD_LISTEN_FDS) and zero-idle architecture."
        ),
        (
            r"\bquadlet\b|\bpodman\b|\bcontainer\b|\bdocker\b|\brootless\b",
            "Podman Quadlets & Containers",
            20,
            "Leverage your experience with Podman Quadlets (.container units), rootless user namespaces, and container security."
        ),
        (
            r"\bqemu\b|\bkvm\b|\bvirtualization\b",
            "QEMU/KVM & Virtualization",
            20,
            "Reference your open-source a QEMU VM runner multi-arch QEMU runner and RHCVA virtualization administrator certification."
        ),
        # 5. Core Systems Programming & Packaging
        (
            r"\bgolang\b|\bgo\b",
            "Go (Golang)",
            20,
            "Highlight concurrent Go daemon engineering, GoLab conference talks, and systems tooling."
        ),
        (
            r"\bc\b(?!\+\+)|\bc\+\+",
            "C / C++20 Systems",
            20,
            "Point to your C low-level systems programming, dlopen dynamic linking, and Zero-JS C++20 desktop monitors."
        ),
        (
            r"\brpm\b|\bpackaging\b|\bobs\b",
            "RPM & Open Build Service",
            15,
            "Highlight active openSUSE RPM package maintainer status on Open Build Service."
        ),
        (
            r"\bobservability\b|\btelemetry\b|\bmonitoring\b|\bprometheus\b",
            "Observability & Telemetry",
            15,
            "Emphasize runtime telemetry instrumentation and custom observability agents."
        ),
        # 6. SRE, DevOps & Cloud Platform Infrastructure
        (
            r"\bsre\b|\bsite reliability\b|\bproduction engineering\b",
            "Site Reliability Engineering (SRE)",
            20,
            "Highlight your experience operating enterprise Linux production environments, automated fault injection, and zero-idle daemon architecture."
        ),
        (
            r"\bdevops\b|\bplatform engineering\b|\bplatform engineer\b|\bci/cd\b|\bkubernetes\b|\bk8s\b",
            "Platform Engineering & DevOps",
            20,
            "Reference your extensive CI/CD validation pipelines, openQA matrix automation, Kubernetes container orchestration, and multi-node fleet management."
        ),
        (
            r"\blinux\b",
            "Linux Foundation",
            15,
            "Leverage many years continuous Linux engineering experience  and RHCE / SLES certifications."
        ),
    ]

    matched_skills = []
    matched_weights = 0
    pitch_bullets = []

    for pattern, name, weight, pitch in SKILL_MATRIX:
        if re.search(pattern, text, re.IGNORECASE):
            matched_skills.append(name)
            matched_weights += weight
            if pitch and len(pitch_bullets) < 3:
                pitch_bullets.append(pitch)

    # Normalized match percentage (capped at 100%)
    match_pct = min(100, int((matched_weights / 80) * 100))

    # Gaps check
    POTENTIAL_GAPS = [
        (r"\bjava\b", "Java"),
        (r"\bterraform\b", "Terraform"),
        (r"\baws cdk\b", "AWS CDK"),
        (r"\btypescript\b", "TypeScript"),
    ]
    gaps = [name for pat, name in POTENTIAL_GAPS if re.search(pat, text, re.IGNORECASE)]

    if not pitch_bullets:
        pitch_bullets.append("Leverage many years Linux engineering experience  and current <employer> platform foundation.")
        pitch_bullets.append("Emphasize automation of thousands of Linux servers and RHCE/SLES certifications.")

    return {
        "match_pct": match_pct,
        "matched_skills": matched_skills,
        "gaps": gaps[:3],
        "pitch_bullets": pitch_bullets,
    }


def compute_freshness(first_seen_str: str):
    """Determine role freshness / ghost status based on days active."""
    if not first_seen_str:
        return {"days_active": 0, "status": "FRESH (<7d)"}
    try:
        first_dt = datetime.datetime.strptime(first_seen_str.split(".")[0], "%Y-%m-%d %H:%M:%S")
        now_utc = datetime.datetime.now(datetime.timezone.utc).replace(tzinfo=None)
        days = max(0, (now_utc - first_dt).days)
        if days > 75:
            status = f"STALE ({days}d)"
        elif days > 45:
            status = f"AGING ({days}d)"
        elif days > 21:
            status = f"ACTIVE ({days}d)"
        elif days > 7:
            status = f"RECENT ({days}d)"
        else:
            status = f"FRESH (<7d)"
        return {"days_active": days, "status": status}
    except Exception:
        return {"days_active": 0, "status": "UNKNOWN"}


def generate_rss_feed(jobs, output_path="feed.xml"):
    """Generate RSS 2.0 XML feed for local readers (newsboat, Thunderbird, Feedly)."""
    rss = ET.Element("rss", version="2.0")
    channel = ET.SubElement(rss, "channel")

    title = ET.SubElement(channel, "title")
    title.text = "Job Radar - Systems & Platform Feed (Candidate)"

    link = ET.SubElement(channel, "link")
    link.text = "https://example.com"

    desc = ET.SubElement(channel, "description")
    desc.text = "Top curated Linux, Platform, and Systems engineering opportunities matching the candidate's profile."

    last_build = ET.SubElement(channel, "lastBuildDate")
    last_build.text = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    for j in jobs[:50]:
        item = ET.SubElement(channel, "item")
        it_title = ET.SubElement(item, "title")
        score = j.get("score", 0)
        sal = j.get("salary_display") or "Unspecified"
        comp = j.get("company_id", "").capitalize()
        it_title.text = f"[{score} pts | {sal}] {comp}: {j.get('title')}"

        it_link = ET.SubElement(item, "link")
        it_link.text = j.get("url", "")

        guid = ET.SubElement(item, "guid")
        guid.text = j.get("id", j.get("url", ""))

        it_desc = ET.SubElement(item, "description")
        loc = j.get("location", "")
        tags = j.get("tags", "")
        eval_info = evaluate_profile_match(j.get("title", ""), "", j.get("company_id", ""))
        skills_str = ", ".join(eval_info["matched_skills"])

        it_desc.text = (
            f"<strong>Company:</strong> {comp}<br/>"
            f"<strong>Location:</strong> {loc}<br/>"
            f"<strong>Salary:</strong> {sal}<br/>"
            f"<strong>Profile Match:</strong> {eval_info['match_pct']}%<br/>"
            f"<strong>Matched Skills:</strong> {skills_str}<br/>"
            f"<strong>Tags:</strong> {tags}<br/><br/>"
            f"<a href='{j.get('url')}'>Apply on {comp} career site</a>"
        )

        pub_date = ET.SubElement(item, "pubDate")
        pub_date.text = datetime.datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

    tree = ET.ElementTree(rss)
    ET.indent(tree, space="  ", level=0)
    tree.write(output_path, encoding="utf-8", xml_declaration=True)
    return output_path
