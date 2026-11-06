"""Candidate profile & domain matching stage."""

import re
from typing import Dict, List, Optional, Tuple

from radar.config import get_candidate_info, load_profile
from radar.models import Job, PipelineContext, ProfileMatch, RawJob
from radar.pipeline.base import PipelineStage, StageResult

DEFAULT_SKILL_MATRIX = [
    # 1. eBPF & Dynamic Instrumentation
    (
        r"\bebpf\b|\bbpf\b|\buprobe\b|\bftrace\b",
        "eBPF & Kernel Tracing",
        30,
        "Highlight background in non-intrusive eBPF runtime observability, uprobes, and kernel tracing.",
    ),
    (
        r"\bpintool\b|\bdynamic binary\b|\bdlopen\b|\belf\b|\bgot\b|\bplt\b",
        "Binary Instrumentation & Dynamic Linking",
        25,
        "Reference dynamic binary instrumentation, symbol resolution, and library hooking.",
    ),
    # 2. Kernel Security, Sandboxing & Capabilities
    (
        r"\bkernel\b",
        "Linux Kernel",
        25,
        "Emphasize systems programming, kernel debugging, and runtime test engineering.",
    ),
    (
        r"\blandlock\b|\bcapabilities\b|\bseccomp\b|\bsandbox\b",
        "Kernel Sandboxing & Capabilities",
        25,
        "Highlight experience with modern Linux kernel sandboxing: Landlock LSM, Linux Capabilities, and seccomp filtering.",
    ),
    # 3. OS Testing, Reliability & Fault Injection
    (
        r"\bltp\b|\blinux test project\b|\bkexec\b",
        "LTP & OS Reliability",
        25,
        "Highlight experience with operating system qualification, test development, and fast kernel reboot mechanisms.",
    ),
    (
        r"\bfault injection\b|\bchaos\b|\bnetns\b|\btrafic control\b|\btc\b|\bnetem\b",
        "Fault Injection & Simulation",
        20,
        "Reference edge failure simulation: network namespace packet loss/latency injection and disk resilience testing.",
    ),
    (
        r"\bopenqa\b|\bautomated testing\b|\bqe\b|\bos validation\b",
        "Automated OS Validation & QE",
        20,
        "Highlight automated qualification, test matrix orchestration via REST APIs, and regression monitoring.",
    ),
    # 4. Containers, systemd & Virtualization
    (
        r"\bsystemd\b|\bsocket activation\b",
        "systemd Plumbing",
        20,
        "Reference declarative systemd services, socket-activated daemons (SD_LISTEN_FDS), and zero-idle architecture.",
    ),
    (
        r"\bquadlet\b|\bpodman\b|\bcontainer\b|\bdocker\b|\brootless\b",
        "Containers & Isolation",
        20,
        "Leverage experience with declarative container units, rootless user namespaces, and container security.",
    ),
    (
        r"\bqemu\b|\bkvm\b|\bvirtualization\b",
        "QEMU/KVM & Virtualization",
        20,
        "Reference virtual machine orchestration, hypervisor management, and virtualization administration.",
    ),
    # 5. Core Systems Programming & Languages
    (
        r"\bgolang\b|\bgo\b",
        "Go (Golang)",
        20,
        "Highlight concurrent Go systems engineering, daemons, and CLI tooling.",
    ),
    (
        r"\bc\b(?!\+\+)|\bc\+\+",
        "C / C++ Systems",
        20,
        "Point to low-level C/C++ systems programming, memory safety, and POSIX primitives.",
    ),
    (
        r"\brust\b",
        "Rust",
        20,
        "Highlight memory-safe systems programming and high-performance services in Rust.",
    ),
    (
        r"\bpython\b|\bpytest\b|\bpython3\b",
        "Python Systems & Automation",
        20,
        "Highlight Python engineering for systems automation, test harnesses, and tooling.",
    ),
    (
        r"\bcloud\b|\baws\b|\bgcp\b|\bazure\b|\bcloud-native\b",
        "Cloud Platform & Infrastructure",
        20,
        "Leverage experience with cloud-native infrastructure, distributed systems, and cloud platforms.",
    ),
    (
        r"\bansible\b|\bconfiguration management\b",
        "Ansible & Fleet Automation",
        25,
        "Reference Red Hat Certified Specialist in Ansible Automation credentials and fleet management across thousands of Linux nodes.",
    ),
    (
        r"\bopenstack\b|\bhybrid cloud\b|\biaas\b|\bpaas\b",
        "OpenStack & Hybrid Cloud",
        20,
        "Leverage Certified OpenStack Administrator (COA) credentials and hands-on multi-datacenter private cloud orchestration.",
    ),
    (
        r"\brhel\b|\bsles\b|\bopensuse\b|\brhce\b|\bpam\b|\bpluggable authentication\b",
        "Enterprise Linux & PAM Architecture",
        20,
        "Highlight deep dual Red Hat RHCE and <employer> SCE certifications and published expertise in the Linux PAM subsystem.",
    ),
    (
        r"\bcrystal\b",
        "Crystal Systems Language",
        15,
        "Reference role as language community contributor and author of open-source koans.",
    ),
    (
        r"\brpm\b|\bpackaging\b|\bobs\b",
        "Linux Packaging & Build Services",
        15,
        "Highlight Linux package maintenance, distribution packaging, and automated build systems.",
    ),
    (
        r"\bobservability\b|\btelemetry\b|\bmonitoring\b|\bprometheus\b",
        "Observability & Telemetry",
        15,
        "Emphasize runtime telemetry instrumentation, metric pipelines, and custom observability agents.",
    ),
    # 6. SRE, DevOps & Cloud Platform Infrastructure
    (
        r"\bsre\b|\bsite reliability\b|\bproduction engineering\b",
        "Site Reliability Engineering (SRE)",
        20,
        "Highlight experience operating high-availability Linux environments, fault tolerance, and production reliability.",
    ),
    (
        r"\bdevops\b|\bplatform engineering\b|\bplatform engineer\b|\bci/cd\b|\bkubernetes\b|\bk8s\b",
        "Platform Engineering & DevOps",
        20,
        "Reference CI/CD deployment pipelines, automated validation, and Kubernetes container orchestration.",
    ),
    (
        r"\blinux\b",
        "Linux Foundation",
        15,
        "Leverage solid Linux engineering foundation and enterprise systems experience.",
    ),
]


def get_active_skill_matrix() -> List[Tuple[str, str, int, str]]:
    """Retrieve skill matrix from candidate profile or fallback to defaults."""
    prof = load_profile()
    custom_matrix = prof.get("skill_matrix")
    if custom_matrix and isinstance(custom_matrix, list):
        parsed = []
        for item in custom_matrix:
            if isinstance(item, dict) and "pattern" in item and "name" in item:
                parsed.append((
                    item["pattern"],
                    item["name"],
                    int(item.get("weight", 20)),
                    item.get("pitch", ""),
                ))
        if parsed:
            return parsed
    return DEFAULT_SKILL_MATRIX


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

    match_pct = min(100, int((matched_weights / 80) * 100))

    if not pitch_bullets:
        cand = get_candidate_info()
        headline = cand.get("headline", "Systems Engineering")
        years = cand.get("experience_years", 10)
        pitch_bullets.append(f"Highlight {years}+ years of systems engineering background and {headline} foundation.")
        pitch_bullets.append("Emphasize automated reliability testing, Linux platform internals, and production scalability.")

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
