"""The scan runner: ordering, error containment and persistence.

The runner is the seam between "we measured something" and "we stored a
finding". These tests pin the two properties that matter most:

* a collector failure degrades the scan instead of aborting it;
* a scan always records how it ended, even when it failed.
"""

from __future__ import annotations

import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ningx.analysis.junk import JunkReport, JunkRoot
from ningx.analysis.runner import ScanRequest, ScanRunner
from ningx.security.startup_collector import FakeStartupCollector, StartupEntry
from ningx.storage.repositories.findings import FakeFindingRepository
from tests.telemetry_fakes import make_sample

GIB = 1024**3
START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


class SteppingClock:
    def __init__(self) -> None:
        self._now = START

    def __call__(self) -> datetime:
        self._now += timedelta(milliseconds=250)
        return self._now


class FailingCollector:
    def collect(self) -> list[StartupEntry]:
        raise PermissionError("registry is not readable")


class FailingJunkScanner:
    def scan(self) -> JunkReport:
        raise OSError("temp folder is not readable")


class FixedJunkScanner:
    def __init__(self, report: JunkReport) -> None:
        self._report = report

    def scan(self) -> JunkReport:
        return self._report


def junk(size: int) -> JunkReport:
    return JunkReport(
        roots=(JunkRoot(path=r"C:\Temp", bytes=size, files=100, truncated=False),),
        scanned_at=START,
    )


def test_scan_records_a_completed_run() -> None:
    repo = FakeFindingRepository()
    runner = ScanRunner(repo, clock=SteppingClock())
    outcome = runner.run(make_sample(memory_pct=95.0))

    assert outcome.findings
    assert outcome.errors == ()
    record = repo.get_scan(outcome.scan_id)
    assert record is not None
    assert record.status == "completed"
    assert record.trigger == "manual"
    assert record.findings_count == len(outcome.findings)
    assert record.duration_ms is not None and record.duration_ms > 0
    assert record.finished_at is not None


def test_findings_are_persisted_with_their_fingerprints() -> None:
    repo = FakeFindingRepository()
    outcome = ScanRunner(repo, clock=SteppingClock()).run(make_sample(memory_pct=95.0))
    stored = repo.findings_for(outcome.scan_id)
    assert {item.fingerprint for item in stored} == {
        finding.fingerprint for finding in outcome.findings
    }
    assert repo.finding_count() == len(outcome.findings)


def test_collectors_are_used_when_supplied() -> None:
    entry = StartupEntry(
        name="Ghost",
        command=r"C:\Missing\ghost.exe",
        location=r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run",
        scope="current user",
        enabled=True,
        executable=r"C:\Missing\ghost.exe",
        exists=False,
    )
    repo = FakeFindingRepository()
    runner = ScanRunner(
        repo,
        startup=FakeStartupCollector([entry]),
        junk=FixedJunkScanner(junk(6 * GIB)),
        clock=SteppingClock(),
    )
    outcome = runner.run(make_sample())
    categories = {finding.category.value for finding in outcome.findings}
    assert "startup" in categories
    assert "junk" in categories


def test_collectors_can_be_skipped_per_request() -> None:
    repo = FakeFindingRepository()
    runner = ScanRunner(
        repo,
        startup=FakeStartupCollector([]),
        junk=FixedJunkScanner(junk(6 * GIB)),
        clock=SteppingClock(),
    )
    outcome = runner.run(
        make_sample(), ScanRequest(trigger="scheduled", include_junk=False)
    )
    assert "junk" not in {finding.category.value for finding in outcome.findings}
    record = repo.get_scan(outcome.scan_id)
    assert record is not None
    assert record.trigger == "scheduled"


def test_a_failing_collector_degrades_the_scan_without_aborting_it() -> None:
    repo = FakeFindingRepository()
    runner = ScanRunner(
        repo,
        startup=FailingCollector(),
        junk=FailingJunkScanner(),
        clock=SteppingClock(),
    )
    outcome = runner.run(make_sample(memory_pct=95.0))

    assert outcome.findings, "memory analysis must still run"
    assert len(outcome.errors) == 2
    assert any("startup collector failed" in error for error in outcome.errors)
    assert any("junk scanner failed" in error for error in outcome.errors)

    record = repo.get_scan(outcome.scan_id)
    assert record is not None
    assert record.status == "completed"
    assert record.findings_count == len(outcome.findings)


def test_a_failure_to_persist_marks_the_scan_failed() -> None:
    class BrokenRepository(FakeFindingRepository):
        def save_findings(self, scan_id: int, findings: object) -> int:
            raise RuntimeError("disk is full")

    repo = BrokenRepository()
    outcome = ScanRunner(repo, clock=SteppingClock()).run(make_sample(memory_pct=95.0))

    assert outcome.findings, "the analysis result is still returned to the caller"
    assert any("persistence failed" in error for error in outcome.errors)
    record = repo.get_scan(outcome.scan_id)
    assert record is not None
    assert record.status == "failed"
    assert record.error is not None and "disk is full" not in record.error
    assert record.findings_count == 0


def test_a_retention_failure_is_reported_but_does_not_fail_the_scan() -> None:
    class NoPruneRepository(FakeFindingRepository):
        def prune(self, *, keep: int = 50) -> int:
            raise RuntimeError("locked")

    repo = NoPruneRepository()
    outcome = ScanRunner(repo, clock=SteppingClock()).run(make_sample())
    assert any("retention failed" in error for error in outcome.errors)
    record = repo.get_scan(outcome.scan_id)
    assert record is not None
    assert record.status == "completed"


def test_old_scans_are_pruned_to_the_configured_retention() -> None:
    repo = FakeFindingRepository()
    runner = ScanRunner(repo, clock=SteppingClock(), keep_scans=2)
    for _ in range(4):
        runner.run(make_sample())
    assert len(repo.scans) == 2


def test_outcome_sorts_by_severity_then_confidence() -> None:
    repo = FakeFindingRepository()
    outcome = ScanRunner(repo, clock=SteppingClock()).run(
        make_sample(cpu_pct=99.0, memory_pct=95.0, gpu_pct=99.0, disk_free_pct=5.0)
    )
    ordered = outcome.sorted_findings()
    ranks = [
        {"high": 0, "medium": 1, "low": 2, "info": 3}[finding.severity.value]
        for finding in ordered
    ]
    assert ranks == sorted(ranks)


def test_an_empty_sample_still_produces_a_valid_scan() -> None:
    repo = FakeFindingRepository()
    outcome = ScanRunner(repo, clock=SteppingClock()).run(
        make_sample(cpu_pct=10.0, memory_pct=20.0, gpu_state="unsupported", disk_free_pct=80.0)
    )
    assert outcome.findings == ()
    record = repo.get_scan(outcome.scan_id)
    assert record is not None
    assert record.status == "completed"
    assert record.findings_count == 0


def test_analysis_sources_import_nothing_that_can_act() -> None:
    """A structural guarantee: no analyst can reach an executor or a shell.

    Checked two ways, because each catches a different mistake:

    * a source scan of every module under ``ningx/analysis`` for imports of the
      mutation layer, a shell, or process spawning;
    * a runtime check in a fresh interpreter that importing the package does not
      load the Windows operations layer or the dry-run executor.

    ``psutil`` does get loaded transitively through the telemetry models. That
    is acceptable: psutil reads, it cannot act, and it is the same library the
    sampler already trusts.
    """
    package = Path(__file__).resolve().parents[1] / "src" / "ningx" / "analysis"
    forbidden_imports = (
        "subprocess",
        "shutil",
        "os.system",
        "os.startfile",
        "ningx.winapi",
        "ningx.core.dry_run",
        "ningx.core.executor",
    )
    offenders: list[str] = []
    for source in sorted(package.glob("*.py")):
        text = source.read_text(encoding="utf-8")
        for name in forbidden_imports:
            if f"import {name}" in text or f"from {name}" in text:
                offenders.append(f"{source.name}: {name}")
    assert offenders == [], f"analysis may not import: {offenders}"

    code = (
        "import sys, ningx.analysis, ningx.analysis.runner\n"
        "forbidden = ['ningx.winapi.ops', 'ningx.core.dry_run']\n"
        "print(','.join(name for name in forbidden if name in sys.modules))\n"
    )
    result = subprocess.run(  # noqa: S603 - fixed argv, our own interpreter
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        check=True,
        cwd=str(Path(__file__).resolve().parents[1]),
    )
    assert result.stdout.strip() == "", f"analysis imported: {result.stdout.strip()}"
