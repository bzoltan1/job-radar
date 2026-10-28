"""Candidate profile & blog domain matching stage."""

import re
from typing import Dict, List

from radar.models import Job, PipelineContext, ProfileMatch, RawJob
from radar.pipeline.base import PipelineStage, StageResult

SKILL_MATRIX = [
    # 1. eBPF & Dynamic Instrumentation
    (
        r"\bebpf\b|\bbpf\b|\buprobe\b|\bftrace\b",
        "eBPF & Kernel Tracing",
        30,
        "Highlight your 5-part research on binary-coverage research: measuring precompiled binary test coverage via eBPF uprobes and kernel ftrace with zero recompile overhead.",
    ),
    (
        r"\bpintool\b|\bdynamic binary\b|\bdlopen\b|\belf\b|\bgot\b|\bplt\b",
        "Binary Instrumentation & Dynamic Linking",
        25,
        "Reference your Intel PinTool DBI analysis and dynamic library hooking (dlopen/PLT/GOT dynamic symbol resolution).",
    ),
    # 2. Kernel Security, Sandboxing & Capabilities
    (
        r"\bkernel\b",
        "Linux Kernel",
        25,
        "Emphasize Linux Test Project (LTP) test development and kernel ftrace/debugging experience at <employer>.",
    ),
    (
        r"\blandlock\b|\bcapabilities\b|\bseccomp\b|\bsandbox\b",
        "Kernel Sandboxing & Capabilities",
        25,
        "Point to your technical publications on Linux Landlock unprivileged LSM sandboxing, Linux Capabilities, and seccomp syscall filtering.",
    ),
    # 3. OS Testing, Reliability & Fault Injection
    (
        r"\bltp\b|\blinux test project\b|\bkexec\b",
        "LTP & OS Reliability",
        25,
        "Highlight your experience running and extending the Linux Test Project (LTP) and instant kernel reboots with kexec.",
    ),
    (
        r"\bfault injection\b|\bchaos\b|\bnetns\b|\btrafic control\b|\btc\b|\bnetem\b",
        "Fault Injection & Simulation",
        20,
        "Note your work simulating edge failures: network namespace packet loss/latency injection with NetEm and disk failures with dm-flakey.",
    ),
    (
        r"\bopenqa\b|\bautomated testing\b|\bqe\b|\bos validation\b",
        "openQA & OS Validation",
        20,
        "Highlight your current <employer> QE automation role: automating openQA test job matrix cloning via REST APIs and custom tooling.",
    ),
    # 4. Containers, systemd & Virtualization
    (
        r"\bsystemd\b|\bsocket activation\b",
        "systemd Plumbing",
        20,
        "Reference your blog guides on declarative systemd socket-activated services (SD_LISTEN_FDS) and zero-idle architecture.",
    ),
    (
        r"\bquadlet\b|\bpodman\b|\bcontainer\b|\bdocker\b|\brootless\b",
        "Podman Quadlets & Containers",
        20,
        "Leverage your experience with Podman Quadlets (.container units), rootless user namespaces, and container security.",
    ),
    (
        r"\bqemu\b|\bkvm\b|\bvirtualization\b",
        "QEMU/KVM & Virtualization",
        20,
        "Reference your open-source a QEMU VM runner multi-arch QEMU runner and RHCVA virtualization administrator certification.",
    ),
    # 5. Core Systems Programming & Packaging
    (
        r"\bgolang\b|\bgo\b",
        "Go (Golang)",
        20,
        "Highlight concurrent Go daemon engineering, GoLab conference talks, and systems tooling.",
    ),
    (
        r"\bc\b(?!\+\+)|\bc\+\+",
        "C / C++20 Systems",
        20,
        "Point to your C low-level systems programming, dlopen dynamic linking, and Zero-JS C++20 desktop monitors.",
    ),
    (
        r"\brpm\b|\bpackaging\b|\bobs\b",
        "RPM & Open Build Service",
        15,
        "Highlight active openSUSE RPM package maintainer status on Open Build Service.",
    ),
    (
        r"\bobservability\b|\btelemetry\b|\bmonitoring\b|\bprometheus\b",
        "Observability & Telemetry",
        15,
        "Emphasize runtime telemetry instrumentation and custom observability agents.",
    ),
    # 6. SRE, DevOps & Cloud Platform Infrastructure
    (
        r"\bsre\b|\bsite reliability\b|\bproduction engineering\b",
        "Site Reliability Engineering (SRE)",
        20,
        "Highlight your experience operating enterprise Linux production environments, automated fault injection, and zero-idle daemon architecture.",
    ),
    (
        r"\bdevops\b|\bplatform engineering\b|\bplatform engineer\b|\bci/cd\b|\bkubernetes\b|\bk8s\b",
        "Platform Engineering & DevOps",
        20,
        "Reference your extensive CI/CD validation pipelines, openQA matrix automation, Kubernetes container orchestration, and multi-node fleet management.",
    ),
    (
        r"\blinux\b",
        "Linux Foundation",
        15,
        "Leverage many years continuous Linux engineering experience  and RHCE / SLES certifications.",
    ),
]


def evaluate_profile(title: str, content: str) -> ProfileMatch:
    """Evaluate candidate profile match percentage, matched skills, and tailored pitch bullets."""
    text = f"{title} {content}".lower()

    matched_skills = []
    matched_weights = 0
    pitch_bullets = []

    for pattern, name, weight, pitch in SKILL_MATRIX:
        if re.search(pattern, text, re.IGNORECASE):
            matched_skills.append(name)
            matched_weights += weight
            if pitch and len(pitch_bullets) < 3:
                pitch_bullets.append(pitch)

    match_pct = min(100, int((matched_weights / 80) * 100))

    if not pitch_bullets:
        pitch_bullets.append("Leverage many years Linux engineering experience  and current <employer> platform foundation.")
        pitch_bullets.append("Emphasize automation of thousands of Linux servers and RHCE/SLES certifications.")

    return ProfileMatch(
        match_pct=match_pct,
        matched_skills=matched_skills,
        pitch_bullets=pitch_bullets,
    )


class ProfileMatchStage(PipelineStage):
    """Computes candidate skill alignment based on blog research and adds pitch bullets."""

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
