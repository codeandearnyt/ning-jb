"""One scan: collect, analyse, persist, report.

The runner is the only place that knows a scan happened. It owns ordering and
error containment, and nothing else:

* a collector that fails adds an error string to the outcome and the scan
  continues with the data that *was* gathered;
* analysts see only what was collected, so a failed collector can never turn
  into a finding;
* persistence is attempted once at the end, and a failure there is reported as
  a failed scan rather than silently dropping the findings.

The runner does not own the sample. Callers pass the latest measured
``SystemSample`` so that a scan always describes a real observation instead of
triggering its own machine reads.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol

from ningx.analysis.analysts import AnalysisInput, run_analysts
from ningx.analysis.junk import JunkReport, JunkScannerPort
from ningx.contracts.finding import Finding, ScanOutcome
from ningx.security.startup_collector import StartupCollector, StartupEntry
from ningx.telemetry.models import SystemSample


class ScanRepository(Protocol):
    def start_scan(self, *, trigger: str, started_at: datetime | None = None) -> int: ...
    def save_findings(self, scan_id: int, findings: Iterable[Finding]) -> int: ...
    def finish_scan(
        self,
        scan_id: int,
        *,
        status: str,
        findings_count: int,
        duration_ms: int,
        finished_at: datetime | None = None,
        error: str | None = None,
    ) -> None: ...
    def prune(self, *, keep: int = 50) -> int: ...


@dataclass(frozen=True)
class ScanRequest:
    trigger: str = "manual"
    include_startup: bool = True
    include_junk: bool = True


class ScanRunner:
    def __init__(
        self,
        repository: ScanRepository,
        *,
        startup: StartupCollector | None = None,
        junk: JunkScannerPort | None = None,
        clock: Callable[[], datetime] | None = None,
        keep_scans: int = 50,
    ) -> None:
        self._repository = repository
        self._startup = startup
        self._junk = junk
        self._clock = clock or (lambda: datetime.now(UTC))
        self._keep_scans = keep_scans

    def run(self, sample: SystemSample, request: ScanRequest | None = None) -> ScanOutcome:
        options = request or ScanRequest()
        started = self._clock()
        scan_id = self._repository.start_scan(trigger=options.trigger, started_at=started)

        errors: list[str] = []
        startup_entries: tuple[StartupEntry, ...] = ()
        junk: JunkReport | None = None

        if options.include_startup and self._startup is not None:
            try:
                startup_entries = tuple(self._startup.collect())
            except Exception as exc:
                errors.append(f"startup collector failed: {type(exc).__name__}")

        if options.include_junk and self._junk is not None:
            try:
                junk = self._junk.scan()
            except Exception as exc:
                errors.append(f"junk scanner failed: {type(exc).__name__}")

        try:
            findings: tuple[Finding, ...] = tuple(
                run_analysts(
                    AnalysisInput(
                        sample=sample,
                        startup_entries=startup_entries,
                        junk=junk,
                    )
                )
            )
        except Exception as exc:
            finished = self._clock()
            self._repository.finish_scan(
                scan_id,
                status="failed",
                findings_count=0,
                duration_ms=_duration_ms(started, finished),
                finished_at=finished,
                error=f"analysis failed: {type(exc).__name__}",
            )
            return ScanOutcome(
                scan_id=scan_id,
                started_at=started,
                finished_at=finished,
                findings=(),
                errors=(*errors, f"analysis failed: {type(exc).__name__}"),
            )

        try:
            saved = self._repository.save_findings(scan_id, findings)
        except Exception as exc:
            finished = self._clock()
            self._repository.finish_scan(
                scan_id,
                status="failed",
                findings_count=0,
                duration_ms=_duration_ms(started, finished),
                finished_at=finished,
                error=f"persistence failed: {type(exc).__name__}",
            )
            return ScanOutcome(
                scan_id=scan_id,
                started_at=started,
                finished_at=finished,
                findings=findings,
                errors=(*errors, f"persistence failed: {type(exc).__name__}"),
            )

        finished = self._clock()
        self._repository.finish_scan(
            scan_id,
            status="completed",
            findings_count=saved,
            duration_ms=_duration_ms(started, finished),
            finished_at=finished,
        )
        try:
            self._repository.prune(keep=self._keep_scans)
        except Exception as exc:
            errors.append(f"retention failed: {type(exc).__name__}")

        return ScanOutcome(
            scan_id=scan_id,
            started_at=started,
            finished_at=finished,
            findings=findings,
            errors=tuple(errors),
        )


def _duration_ms(started: datetime, finished: datetime) -> int:
    return max(0, int((finished - started).total_seconds() * 1000))


__all__ = ["ScanRepository", "ScanRequest", "ScanRunner"]
