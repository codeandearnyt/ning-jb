"""Deterministic analysts.

Each analyst is a pure function of the data it is given: one system sample plus
whatever the read-only collectors gathered. No analyst reads the machine, opens
a database, calls a model or proposes an executable payload. That is why their
output can be tested exactly and why "the AI decided" can never be used to
explain a finding.

Every threshold below is a documented constant. If a number is worth showing to
a user it is worth being able to point at the line that produced it.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from pathlib import PureWindowsPath

from ningx.analysis.junk import JunkReport
from ningx.contracts.finding import Category, Evidence, Finding, Severity
from ningx.security.startup_collector import StartupEntry
from ningx.telemetry.models import MetricState, ProcessSample, SystemSample, human_bytes

# ---------------------------------------------------------------- thresholds

CPU_HIGH_PCT = 95.0
CPU_MEDIUM_PCT = 85.0
GPU_MEDIUM_PCT = 95.0

MEMORY_HIGH_PCT = 92.0
MEMORY_MEDIUM_PCT = 84.0
PROCESS_SHARE_MEDIUM = 0.25
PROCESS_SHARE_HIGH = 0.45
PROCESS_MIN_BYTES = 1024**3

PROCESS_CPU_MEDIUM_PCT = 40.0
PROCESS_INSTANCE_INFO = 12

STARTUP_ENABLED_INFO = 15
JUNK_INFO_BYTES = 250 * 1024**2
JUNK_LOW_BYTES = 1024**3
JUNK_MEDIUM_BYTES = 5 * 1024**3

STORAGE_MEDIUM_FREE_PCT = 20.0
STORAGE_HIGH_FREE_PCT = 10.0

NETWORK_ERROR_LOW = 1


@dataclass(frozen=True)
class AnalysisInput:
    sample: SystemSample
    startup_entries: tuple[StartupEntry, ...] = ()
    junk: JunkReport | None = None


def run_analysts(data: AnalysisInput) -> list[Finding]:
    """Run every analyst in a fixed order."""
    findings: list[Finding] = []
    findings.extend(analyse_memory(data))
    findings.extend(analyse_cpu(data))
    findings.extend(analyse_gpu(data))
    findings.extend(analyse_processes(data))
    findings.extend(analyse_startup(data))
    findings.extend(analyse_junk(data))
    findings.extend(analyse_storage(data))
    findings.extend(analyse_network(data))
    return findings


# --------------------------------------------------------------------- memory


def analyse_memory(data: AnalysisInput) -> list[Finding]:
    memory = data.sample.memory
    findings: list[Finding] = []

    if memory.used_pct >= MEMORY_HIGH_PCT:
        severity = Severity.HIGH
    elif memory.used_pct >= MEMORY_MEDIUM_PCT:
        severity = Severity.MEDIUM
    else:
        severity = None

    if severity is not None:
        findings.append(
            Finding(
                agent_id="memory-analyst",
                category=Category.MEMORY,
                rule="memory.pressure",
                subject="physical-memory",
                severity=severity,
                title=f"Memory is {memory.used_pct:.0f}% in use",
                detail=(
                    f"{human_bytes(memory.used_bytes)} of "
                    f"{human_bytes(memory.total_bytes)} is committed to physical "
                    "memory. Windows is already evicting cache at this level, so "
                    "switching between heavy applications will feel slower."
                ),
                evidence=(
                    Evidence("Used", human_bytes(memory.used_bytes), float(memory.used_bytes)),
                    Evidence(
                        "Total", human_bytes(memory.total_bytes), float(memory.total_bytes)
                    ),
                    Evidence("Used percent", f"{memory.used_pct:.1f}%", memory.used_pct),
                ),
                impact="Lower latency when switching apps and less paging.",
                confidence=0.9,
            )
        )

    commit = memory.commit_total_bytes
    if commit and memory.commit_used_bytes and memory.commit_used_bytes > commit:
        findings.append(
            Finding(
                agent_id="memory-analyst",
                category=Category.MEMORY,
                rule="memory.commit_over_commit_limit",
                subject="commit-charge",
                severity=Severity.INFO,
                title="Commit charge exceeds the commit limit",
                detail=(
                    "Committed memory is larger than the configured commit limit, "
                    "so Windows is extending it through the page file."
                ),
                evidence=(
                    Evidence(
                        "Commit used", human_bytes(memory.commit_used_bytes), commit
                    ),
                    Evidence("Commit limit", human_bytes(commit), float(commit)),
                ),
                impact="Disk activity increases when committed pages are paged out.",
                confidence=0.85,
            )
        )

    findings.extend(_largest_process_by_memory(data.sample))
    return findings


def _largest_process_by_memory(sample: SystemSample) -> list[Finding]:
    total = sample.memory.total_bytes
    if total <= 0 or not sample.processes:
        return []
    heaviest = max(sample.processes, key=lambda process: process.private_bytes or process.rss_bytes)
    used = heaviest.private_bytes or heaviest.rss_bytes
    share = used / total
    if used < PROCESS_MIN_BYTES or share < PROCESS_SHARE_MEDIUM:
        return []

    severity = Severity.HIGH if share >= PROCESS_SHARE_HIGH else Severity.MEDIUM
    return [
        Finding(
            agent_id="process-analyst",
            category=Category.PROCESS,
            rule="process.memory_share",
            subject=_process_subject(heaviest),
            severity=severity,
            title=f"{heaviest.name} holds {share * 100:.0f}% of physical memory",
            detail=(
                f"{heaviest.name} (PID {heaviest.pid}) has "
                f"{human_bytes(used)} of private memory committed, which is "
                f"{share * 100:.1f}% of the machine's {human_bytes(total)}."
            ),
            evidence=(
                Evidence("Process", heaviest.name),
                Evidence("PID", str(heaviest.pid), float(heaviest.pid)),
                Evidence("Private bytes", human_bytes(used), float(used)),
                Evidence("Share of RAM", f"{share * 100:.1f}%", round(share * 100, 1)),
            ),
            impact="Closing or restarting it frees the largest single block of RAM.",
            confidence=0.85,
        )
    ]


# ------------------------------------------------------------------------ cpu


def analyse_cpu(data: AnalysisInput) -> list[Finding]:
    cpu = data.sample.cpu
    if cpu.total_pct is None:
        return []

    if cpu.total_pct >= CPU_HIGH_PCT:
        severity = Severity.HIGH
    elif cpu.total_pct >= CPU_MEDIUM_PCT:
        severity = Severity.MEDIUM
    else:
        return []

    hot_cores = sum(1 for value in cpu.per_core_pct if value >= 90.0)
    evidence = [
        Evidence("Total utilisation", f"{cpu.total_pct:.1f}%", cpu.total_pct),
        Evidence("Logical cores", str(cpu.logical_count), float(cpu.logical_count)),
    ]
    if cpu.per_core_pct:
        evidence.append(
            Evidence(
                "Cores at or above 90%",
                f"{hot_cores} of {len(cpu.per_core_pct)}",
                float(hot_cores),
            )
        )

    return [
        Finding(
            agent_id="cpu-analyst",
            category=Category.CPU,
            rule="cpu.high_utilisation",
            subject="total-cpu",
            severity=severity,
            title=f"CPU is {cpu.total_pct:.0f}% busy",
            detail=(
                "Utilisation was measured at the moment of this scan, not averaged "
                "over time. If this repeats across scans, something is running "
                "continuously rather than in short bursts."
            ),
            evidence=tuple(evidence),
            impact="Fewer free cycles for foreground work; fans and power draw rise.",
            confidence=0.8,
        )
    ]


# ------------------------------------------------------------------------ gpu


def analyse_gpu(data: AnalysisInput) -> list[Finding]:
    gpu = data.sample.gpu.utilization
    if gpu.state is not MetricState.AVAILABLE or gpu.value is None:
        return []
    if gpu.value < GPU_MEDIUM_PCT:
        return []

    adapter = data.sample.gpu.adapter or "the active adapter"
    return [
        Finding(
            agent_id="gpu-analyst",
            category=Category.GPU,
            rule="gpu.saturated",
            subject="3d-engine",
            severity=Severity.MEDIUM,
            title=f"GPU 3D engine is {gpu.value:.0f}% busy",
            detail=(
                f"Windows reports the busiest 3D engine of {adapter} at "
                f"{gpu.value:.1f}%. Temperature and clock data are not available "
                "without a vendor API, so thermal throttling cannot be ruled out "
                "from this build."
            ),
            evidence=(
                Evidence("3D utilisation", f"{gpu.value:.1f}%", gpu.value),
                Evidence("Adapter", adapter),
            ),
            impact="Rendering and compositing slow down when the engine is saturated.",
            confidence=0.7,
        )
    ]


# ------------------------------------------------------------------- processes


def analyse_processes(data: AnalysisInput) -> list[Finding]:
    sample = data.sample
    findings: list[Finding] = []
    busy = [
        process
        for process in sample.processes
        if process.cpu_pct is not None and process.cpu_pct >= PROCESS_CPU_MEDIUM_PCT
    ]
    busiest = max(busy, key=lambda process: process.cpu_pct or 0.0, default=None)
    if busiest is not None and busiest.cpu_pct is not None:
        findings.append(
            Finding(
                agent_id="process-analyst",
                category=Category.PROCESS,
                rule="process.high_cpu",
                subject=_process_subject(busiest),
                severity=Severity.MEDIUM,
                title=f"{busiest.name} uses {busiest.cpu_pct:.0f}% of the CPU",
                detail=(
                    f"One process accounts for {busiest.cpu_pct:.1f}% of the whole "
                    f"machine across {sample.cpu.logical_count} logical cores."
                ),
                evidence=(
                    Evidence("Process", busiest.name),
                    Evidence("PID", str(busiest.pid), float(busiest.pid)),
                    Evidence("CPU", f"{busiest.cpu_pct:.1f}%", busiest.cpu_pct),
                    Evidence("Paths", busiest.exe_path or "not readable"),
                ),
                impact="Ending or pausing it returns those cycles to other work.",
                confidence=0.8,
            )
        )

    counts = Counter(_process_subject(process) for process in sample.processes)
    for subject, count in sorted(counts.items()):
        if count < PROCESS_INSTANCE_INFO:
            continue
        name = _display_name(subject)
        findings.append(
            Finding(
                agent_id="process-analyst",
                category=Category.PROCESS,
                rule="process.many_instances",
                subject=subject,
                severity=Severity.INFO,
                title=f"{count} instances of {name}",
                detail=(
                    f"{count} processes share the executable {name}. Many "
                    "instances multiply the per-process memory overhead."
                ),
                evidence=(
                    Evidence("Executable", name),
                    Evidence("Instances", str(count), float(count)),
                    Evidence(
                        "Visible rows",
                        str(len(sample.processes)),
                        float(len(sample.processes)),
                    ),
                ),
                impact="Each instance holds its own working set.",
                confidence=0.9,
            )
        )

    return findings


def _display_name(subject: str) -> str:
    return PureWindowsPath(subject).name or subject


# --------------------------------------------------------------------- startup


def analyse_startup(data: AnalysisInput) -> list[Finding]:
    entries = data.startup_entries
    findings: list[Finding] = []

    broken = [entry for entry in entries if entry.enabled and entry.exists is False]
    for entry in sorted(broken, key=lambda item: item.fingerprint_subject):
        findings.append(
            Finding(
                agent_id="startup-analyst",
                category=Category.STARTUP,
                rule="startup.missing_executable",
                subject=entry.fingerprint_subject,
                severity=Severity.MEDIUM,
                title=f"Startup entry {entry.name} points at a missing file",
                detail=(
                    "Windows still tries to launch this entry at sign-in, but the "
                    "executable it names no longer exists. The launch fails and the "
                    "entry stays behind."
                ),
                evidence=(
                    Evidence("Entry", entry.name),
                    Evidence("Location", entry.location),
                    Evidence("Command", entry.command),
                    Evidence("Executable", entry.executable or "not parsed"),
                ),
                impact="Removes a failing launch from every sign-in.",
                confidence=0.95,
                suggested_action="startup_disable",
            )
        )

    enabled = [entry for entry in entries if entry.enabled]
    if len(enabled) >= STARTUP_ENABLED_INFO:
        findings.append(
            Finding(
                agent_id="startup-analyst",
                category=Category.STARTUP,
                rule="startup.many_enabled",
                subject="startup-enabled-count",
                severity=Severity.INFO,
                title=f"{len(enabled)} startup entries are enabled",
                detail=(
                    "Each enabled entry costs sign-in time and some hold memory "
                    "for the whole session. This is a count, not a claim that any "
                    "particular entry is unnecessary."
                ),
                evidence=(
                    Evidence("Enabled entries", str(len(enabled)), float(len(enabled))),
                    Evidence("Total entries", str(len(entries)), float(len(entries))),
                ),
                impact="Shorter, more predictable sign-in.",
                confidence=0.9,
            )
        )

    return findings


# ------------------------------------------------------------------------ junk


def analyse_junk(data: AnalysisInput) -> list[Finding]:
    report = data.junk
    if report is None or not report.roots:
        return []

    total = report.total_bytes
    if total < JUNK_INFO_BYTES:
        return []

    if total >= JUNK_MEDIUM_BYTES:
        severity = Severity.MEDIUM
    elif total >= JUNK_LOW_BYTES:
        severity = Severity.LOW
    else:
        severity = Severity.INFO

    biggest = max(report.roots, key=lambda root: root.bytes)
    evidence = [
        Evidence("Total in temporary folders", human_bytes(total), float(total)),
        Evidence("Files counted", str(report.total_files), float(report.total_files)),
        Evidence(
            "Largest folder",
            f"{biggest.path} \u00b7 {human_bytes(biggest.bytes)}",
            float(biggest.bytes),
        ),
    ]
    if report.limit_hit:
        evidence.append(Evidence("Scan completeness", "stopped at its own limit"))

    return [
        Finding(
            agent_id="junk-analyst",
            category=Category.JUNK,
            rule="junk.temp_bytes",
            subject="temporary-folders",
            severity=severity,
            title=f"{human_bytes(total)} in temporary folders",
            detail=(
                "This is the measured size of the temp directories Windows exposes. "
                "Some of it is in active use; nothing here has been deleted or "
                "quarantined."
            ),
            evidence=tuple(evidence),
            impact="Reclaiming it is possible without touching documents.",
            confidence=0.75 if report.limit_hit else 0.95,
        )
    ]


# --------------------------------------------------------------------- storage


def analyse_storage(data: AnalysisInput) -> list[Finding]:
    findings: list[Finding] = []
    for disk in data.sample.disks:
        total = disk.total_bytes
        if total <= 0:
            continue
        free_pct = disk.free_bytes / total * 100.0
        if free_pct >= STORAGE_MEDIUM_FREE_PCT:
            continue
        severity = Severity.HIGH if free_pct < STORAGE_HIGH_FREE_PCT else Severity.MEDIUM
        findings.append(
            Finding(
                agent_id="storage-analyst",
                category=Category.STORAGE,
                rule="storage.low_free_space",
                subject=disk.mount.lower(),
                severity=severity,
                title=f"{disk.mount} has {free_pct:.0f}% free",
                detail=(
                    f"{human_bytes(disk.free_bytes)} remains of "
                    f"{human_bytes(total)}. Windows needs headroom for the page "
                    "file, updates and temporary files."
                ),
                evidence=(
                    Evidence("Volume", disk.mount),
                    Evidence("Free", human_bytes(disk.free_bytes), float(disk.free_bytes)),
                    Evidence("Total", human_bytes(total), float(total)),
                    Evidence("Free percent", f"{free_pct:.1f}%", round(free_pct, 1)),
                ),
                impact="Updates and large saves can fail when a volume is full.",
                confidence=0.95,
            )
        )
    return findings


# --------------------------------------------------------------------- network


def analyse_network(data: AnalysisInput) -> list[Finding]:
    network = data.sample.network
    findings: list[Finding] = []

    for interface in network.interfaces:
        name, _sent, _recv = interface
        errors = network.interface_errors(name)
        if errors is None:
            continue
        error_total = sum(errors)
        if error_total < NETWORK_ERROR_LOW:
            continue
        findings.append(
            Finding(
                agent_id="network-analyst",
                category=Category.NETWORK,
                rule="network.interface_errors",
                subject=name.lower(),
                severity=Severity.LOW,
                title=f"{name} reports {error_total} receive or transmit errors",
                detail=(
                    "Counters are cumulative since the adapter was last reset, not "
                    "since this scan. A single non-zero count can be old; a rising "
                    "count across scans indicates a real link problem."
                ),
                evidence=(
                    Evidence("Interface", name),
                    Evidence("Receive errors", str(errors[0]), float(errors[0])),
                    Evidence("Send errors", str(errors[1]), float(errors[1])),
                    Evidence("Receive drops", str(errors[2]), float(errors[2])),
                    Evidence("Send drops", str(errors[3]), float(errors[3])),
                ),
                impact="Retransmissions reduce effective bandwidth and raise latency.",
                confidence=0.7,
            )
        )

    return findings


def _process_subject(process: ProcessSample) -> str:
    if process.exe_path:
        return process.exe_path.lower()
    return process.name.lower()


__all__ = [
    "AnalysisInput",
    "analyse_cpu",
    "analyse_gpu",
    "analyse_junk",
    "analyse_memory",
    "analyse_network",
    "analyse_processes",
    "analyse_startup",
    "analyse_storage",
    "run_analysts",
]
