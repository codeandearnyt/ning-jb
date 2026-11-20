"""Analyst behaviour: thresholds, evidence and determinism.

Every analyst is a pure function of the data it receives, so these tests can
assert exact output. The point is not to re-test arithmetic; it is to prove the
properties the product promises:

* a metric the machine did not report never becomes a finding;
* severity follows the documented thresholds and nothing else;
* a fingerprint survives a change in the measured value.
"""

from __future__ import annotations

from datetime import UTC, datetime

from ningx.analysis.analysts import (
    CPU_HIGH_PCT,
    CPU_MEDIUM_PCT,
    JUNK_INFO_BYTES,
    MEMORY_HIGH_PCT,
    MEMORY_MEDIUM_PCT,
    PROCESS_INSTANCE_INFO,
    STARTUP_ENABLED_INFO,
    STORAGE_HIGH_FREE_PCT,
    AnalysisInput,
    analyse_cpu,
    analyse_gpu,
    analyse_junk,
    analyse_memory,
    analyse_network,
    analyse_processes,
    analyse_startup,
    analyse_storage,
    run_analysts,
)
from ningx.analysis.junk import JunkReport, JunkRoot
from ningx.contracts.finding import Category, Severity
from ningx.security.startup_collector import StartupEntry
from ningx.telemetry.models import NetworkSample
from tests.telemetry_fakes import make_process, make_sample

GIB = 1024**3


def test_memory_below_threshold_is_silent() -> None:
    data = AnalysisInput(sample=make_sample(memory_pct=MEMORY_MEDIUM_PCT - 1.0))
    assert analyse_memory(data) == []


def test_memory_medium_then_high_follows_the_constants() -> None:
    medium = analyse_memory(AnalysisInput(sample=make_sample(memory_pct=MEMORY_MEDIUM_PCT)))
    high = analyse_memory(AnalysisInput(sample=make_sample(memory_pct=MEMORY_HIGH_PCT)))
    assert [finding.severity for finding in medium] == [Severity.MEDIUM]
    assert [finding.severity for finding in high] == [Severity.HIGH]


def test_memory_evidence_names_the_measured_numbers() -> None:
    findings = analyse_memory(AnalysisInput(sample=make_sample(memory_pct=90.0)))
    labels = {item.label for item in findings[0].evidence}
    assert labels == {"Used", "Total", "Used percent"}
    percent = next(item for item in findings[0].evidence if item.label == "Used percent")
    assert percent.value == "90.0%"
    assert percent.numeric == 90.0


def test_memory_fingerprint_is_stable_when_the_value_changes() -> None:
    first = analyse_memory(AnalysisInput(sample=make_sample(memory_pct=85.0)))[0]
    second = analyse_memory(AnalysisInput(sample=make_sample(memory_pct=99.0)))[0]
    assert first.fingerprint == second.fingerprint
    assert first.severity != second.severity


def test_warming_cpu_is_not_a_finding() -> None:
    sample = make_sample(cpu_pct=None)
    assert analyse_cpu(AnalysisInput(sample=sample)) == []


def test_cpu_thresholds_and_core_count() -> None:
    medium = analyse_cpu(AnalysisInput(sample=make_sample(cpu_pct=CPU_MEDIUM_PCT)))
    high = analyse_cpu(AnalysisInput(sample=make_sample(cpu_pct=CPU_HIGH_PCT)))
    assert [finding.severity for finding in medium] == [Severity.MEDIUM]
    assert [finding.severity for finding in high] == [Severity.HIGH]

    labels = {item.label: item.value for item in high[0].evidence}
    assert labels["Logical cores"] == "16"
    assert "Cores at or above 90%" in labels


def test_unsupported_gpu_never_produces_a_finding() -> None:
    assert analyse_gpu(AnalysisInput(sample=make_sample(gpu_state="unsupported"))) == []


def test_saturated_gpu_is_medium_and_says_what_it_cannot_measure() -> None:
    findings = analyse_gpu(AnalysisInput(sample=make_sample(gpu_pct=99.0)))
    assert [finding.severity for finding in findings] == [Severity.MEDIUM]
    assert "Temperature and clock data are not available" in findings[0].detail


def test_process_high_cpu_requires_a_measured_rate() -> None:
    sample = make_sample(
        processes=(
            make_process(pid=10, name="busy.exe", cpu_pct=None),
            make_process(pid=11, name="idle.exe", cpu_pct=5.0),
        )
    )
    assert analyse_processes(AnalysisInput(sample=sample)) == []


def test_process_high_cpu_names_the_busiest_process() -> None:
    sample = make_sample(
        processes=(
            make_process(
                pid=10, name="warmer.exe", cpu_pct=55.0, exe_path=r"C:\Apps\warmer.exe"
            ),
            make_process(
                pid=11, name="busier.exe", cpu_pct=70.0, exe_path=r"C:\Apps\busier.exe"
            ),
        )
    )
    findings = analyse_processes(AnalysisInput(sample=sample))
    assert len(findings) == 1
    assert "busier.exe" in findings[0].title
    assert findings[0].subject == r"c:\apps\busier.exe"


def test_many_instances_is_informational_and_one_finding_per_executable() -> None:
    processes = tuple(
        make_process(
            pid=100 + index,
            name="chrome.exe",
            cpu_pct=0.5,
            exe_path=r"C:\Program Files\Chrome\chrome.exe",
        )
        for index in range(PROCESS_INSTANCE_INFO)
    )
    findings = analyse_processes(AnalysisInput(sample=make_sample(processes=processes)))
    assert len(findings) == 1
    assert findings[0].severity == Severity.INFO
    assert findings[0].title == f"{PROCESS_INSTANCE_INFO} instances of chrome.exe"


def test_one_instance_short_of_the_threshold_is_silent() -> None:
    processes = tuple(
        make_process(
            pid=100 + index,
            name="chrome.exe",
            cpu_pct=0.5,
            exe_path=r"C:\Program Files\Chrome\chrome.exe",
        )
        for index in range(PROCESS_INSTANCE_INFO - 1)
    )
    assert analyse_processes(AnalysisInput(sample=make_sample(processes=processes))) == []


def test_startup_missing_executable_is_medium_and_suggests_an_action() -> None:
    entry = StartupEntry(
        name="Ghost",
        command=r"C:\Missing\ghost.exe --minimised",
        location=r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        scope="current user",
        enabled=True,
        executable=r"C:\Missing\ghost.exe",
        exists=False,
    )
    findings = analyse_startup(AnalysisInput(sample=make_sample(), startup_entries=(entry,)))
    assert len(findings) == 1
    assert findings[0].severity == Severity.MEDIUM
    assert findings[0].suggested_action == "startup_disable"
    assert findings[0].subject == entry.fingerprint_subject


def test_disabled_startup_entry_with_missing_file_is_not_reported() -> None:
    entry = StartupEntry(
        name="Old",
        command=r"C:\Missing\old.exe",
        location=r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        scope="current user",
        enabled=False,
        executable=r"C:\Missing\old.exe",
        exists=False,
    )
    assert analyse_startup(AnalysisInput(sample=make_sample(), startup_entries=(entry,))) == []


def test_startup_count_threshold() -> None:
    def entries(count: int) -> tuple[StartupEntry, ...]:
        return tuple(
            StartupEntry(
                name=f"Entry{index}",
                command=rf"C:\Apps\app{index}.exe",
                location=r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
                scope="current user",
                enabled=True,
                executable=rf"C:\Apps\app{index}.exe",
                exists=True,
            )
            for index in range(count)
        )

    below = analyse_startup(
        AnalysisInput(sample=make_sample(), startup_entries=entries(STARTUP_ENABLED_INFO - 1))
    )
    at = analyse_startup(
        AnalysisInput(sample=make_sample(), startup_entries=entries(STARTUP_ENABLED_INFO))
    )
    assert below == []
    assert len(at) == 1
    assert at[0].severity == Severity.INFO


def test_junk_below_the_floor_is_silent() -> None:
    report = JunkReport(
        roots=(JunkRoot(path=r"C:\Temp", bytes=JUNK_INFO_BYTES - 1, files=10, truncated=False),)
    )
    assert analyse_junk(AnalysisInput(sample=make_sample(), junk=report)) == []


def test_junk_severity_bands_and_limit_disclosure() -> None:
    def report(size: int, *, limited: bool) -> JunkReport:
        return JunkReport(
            roots=(
                JunkRoot(path=r"C:\Temp", bytes=size, files=100, truncated=limited),
                JunkRoot(path=r"C:\Other", bytes=size // 2, files=10, truncated=False),
            ),
            scanned_at=datetime(2026, 1, 1, tzinfo=UTC),
            limit_hit=limited,
        )

    info = analyse_junk(
        AnalysisInput(sample=make_sample(), junk=report(JUNK_INFO_BYTES, limited=False))
    )
    low = analyse_junk(
        AnalysisInput(sample=make_sample(), junk=report(2 * 1024**3, limited=False))
    )
    medium = analyse_junk(
        AnalysisInput(sample=make_sample(), junk=report(6 * 1024**3, limited=True))
    )
    assert [finding.severity for finding in info] == [Severity.INFO]
    assert [finding.severity for finding in low] == [Severity.LOW]
    assert [finding.severity for finding in medium] == [Severity.MEDIUM]
    assert medium[0].confidence < info[0].confidence
    assert any(item.label == "Scan completeness" for item in medium[0].evidence)


def test_no_junk_report_means_no_junk_finding() -> None:
    assert analyse_junk(AnalysisInput(sample=make_sample(), junk=None)) == []


def test_storage_threshold_and_fingerprint_per_volume() -> None:
    tight = analyse_storage(
        AnalysisInput(sample=make_sample(disk_free_pct=STORAGE_HIGH_FREE_PCT - 1))
    )
    assert [finding.severity for finding in tight] == [Severity.HIGH]

    roomy = analyse_storage(AnalysisInput(sample=make_sample(disk_free_pct=50.0)))
    assert roomy == []

    sample = make_sample(disk_free_pct=5.0)
    two_volumes = type(sample)(
        captured_at=sample.captured_at,
        monotonic=sample.monotonic,
        cpu=sample.cpu,
        memory=sample.memory,
        gpu=sample.gpu,
        disks=(
            type(sample.disks[0])(mount="C:\\", total_bytes=1000 * GIB, free_bytes=10 * GIB),
            type(sample.disks[0])(mount="D:\\", total_bytes=2000 * GIB, free_bytes=20 * GIB),
        ),
        network=sample.network,
        processes=sample.processes,
        process_count=sample.process_count,
        truncated=False,
    )
    findings = analyse_storage(AnalysisInput(sample=two_volumes))
    assert len({finding.fingerprint for finding in findings}) == 2


def test_network_silence_when_counters_are_clean() -> None:
    sample = make_sample()
    assert analyse_network(AnalysisInput(sample=sample)) == []


def test_network_reports_interfaces_with_errors() -> None:
    sample = make_sample()
    network = NetworkSample(
        sent_bytes_per_s=1000.0,
        recv_bytes_per_s=2000.0,
        interfaces=(("Ethernet", 1000.0, 2000.0),),
        errors=(("Ethernet", 3, 0, 7, 0),),
    )
    noisy = type(sample)(
        captured_at=sample.captured_at,
        monotonic=sample.monotonic,
        cpu=sample.cpu,
        memory=sample.memory,
        gpu=sample.gpu,
        disks=sample.disks,
        network=network,
        processes=sample.processes,
        process_count=sample.process_count,
        truncated=False,
    )
    findings = analyse_network(AnalysisInput(sample=noisy))
    assert len(findings) == 1
    assert findings[0].severity == Severity.LOW
    labels = {item.label: item.value for item in findings[0].evidence}
    assert labels["Receive errors"] == "3"
    assert labels["Receive drops"] == "7"


def test_run_analysts_is_deterministic_and_ordered() -> None:
    sample = make_sample(cpu_pct=99.0, memory_pct=95.0, gpu_pct=99.0, disk_free_pct=5.0)
    first = run_analysts(AnalysisInput(sample=sample))
    second = run_analysts(AnalysisInput(sample=sample))
    assert [finding.fingerprint for finding in first] == [
        finding.fingerprint for finding in second
    ]
    assert {finding.category for finding in first} >= {
        Category.CPU,
        Category.MEMORY,
        Category.STORAGE,
        Category.GPU,
    }


def test_analysts_never_emit_a_target_or_executable_payload() -> None:
    sample = make_sample(cpu_pct=99.0, memory_pct=95.0, gpu_pct=99.0, disk_free_pct=5.0)
    for finding in run_analysts(AnalysisInput(sample=sample)):
        payload = finding.to_payload()
        assert set(payload) == {
            "rule",
            "subject",
            "detail",
            "impact",
            "confidence",
            "suggested_action",
            "evidence",
        }
        assert "pid" not in payload
