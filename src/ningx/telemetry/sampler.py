"""System sampler.

The sampler is read-only by construction: it imports ``psutil``, arithmetic and
the models, and nothing that can write. That property is asserted by a test that
parses this module's imports.

Rates are real deltas measured over the elapsed time between two samples. When
there is no previous sample the rate is ``None`` with state ``WARMING_UP`` -
not zero, because zero would claim the disk was idle.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Iterable
from contextlib import suppress
from datetime import UTC, datetime
from typing import Protocol

from ningx.telemetry.gpu import GpuReading, default_gpu_reader
from ningx.telemetry.models import (
    CpuSample,
    DiskSample,
    GpuSample,
    MemorySample,
    Metric,
    NetworkSample,
    ProcessSample,
    SystemSample,
)


class GpuReader(Protocol):
    def read(self) -> GpuReading: ...


class SystemSampler(Protocol):
    def sample(self) -> SystemSample: ...


def _utcnow() -> datetime:
    return datetime.now(UTC)


class PsutilSampler:
    """Real Windows telemetry through psutil plus PDH GPU counters.

    Process CPU is normalised to the whole machine (0-100 %), the same scale as
    total CPU utilisation, so the numbers in the process table add up against
    the system total instead of being silently multiplied by the core count.
    """

    def __init__(
        self,
        *,
        clock: Callable[[], datetime] = _utcnow,
        gpu_reader: GpuReader | None = None,
        max_processes: int = 300,
    ) -> None:
        self._clock = clock
        self._gpu_reader = gpu_reader
        self._max_processes = max(1, max_processes)
        self._last_monotonic: float | None = None
        self._last_disk: dict[str, tuple[float, float]] | None = None
        self._last_net: dict[str, tuple[float, float]] | None = None
        self._process_cpu: dict[tuple[int, float], float] = {}
        self._primed = False

    # ------------------------------------------------------------------- public

    def sample(self) -> SystemSample:
        psutil = _psutil()
        monotonic = time.monotonic()
        elapsed = None if self._last_monotonic is None else monotonic - self._last_monotonic

        if not self._primed:
            self._prime(psutil)
            self._primed = True

        cpu = self._sample_cpu(psutil, elapsed)
        memory = self._sample_memory(psutil)
        gpu = self._sample_gpu()
        disks, disk_read, disk_write = self._sample_disks(psutil, elapsed)
        network = self._sample_network(psutil, elapsed)
        processes, process_count, truncated = self._sample_processes(psutil)

        # Rate baselines are captured after each sample, so the next sample sees
        # a full interval rather than a fraction of one.
        self._last_monotonic = monotonic
        self._last_disk = _disk_totals(psutil)
        self._last_net = _net_totals(psutil)

        return SystemSample(
            captured_at=self._clock(),
            monotonic=monotonic,
            cpu=cpu,
            memory=memory,
            gpu=gpu,
            disks=disks,
            network=NetworkSample(
                sent_bytes_per_s=network[0],
                recv_bytes_per_s=network[1],
                interfaces=network[2],
                errors=_net_errors(psutil),
            ),
            processes=processes,
            process_count=process_count,
            truncated=truncated,
            disk_read_bytes_per_s=disk_read,
            disk_write_bytes_per_s=disk_write,
        )

    # ------------------------------------------------------------------ priming

    def _prime(self, psutil: object) -> None:
        """Discard the first, meaningless ``cpu_percent`` reading."""
        psutil.cpu_percent(None)  # type: ignore[attr-defined]
        psutil.cpu_percent(None, percpu=True)  # type: ignore[attr-defined]
        with suppress(Exception):
            for process in psutil.process_iter(["create_time"]):  # type: ignore[attr-defined]
                self._process_cpu[_process_key(process)] = _cpu_seconds(process)
        self._last_disk = _disk_totals(psutil)
        self._last_net = _net_totals(psutil)

    # ----------------------------------------------------------------------- cpu

    def _sample_cpu(self, psutil: object, elapsed: float | None) -> CpuSample:
        logical = int(psutil.cpu_count() or 1)  # type: ignore[attr-defined]
        try:
            physical = psutil.cpu_count(logical=False)  # type: ignore[attr-defined]
            physical_count = int(physical) if physical else None
        except Exception:
            physical_count = None

        total: float | None
        per_core: tuple[float, ...]
        if elapsed is None:
            total = None
            per_core = ()
        else:
            try:
                total = float(psutil.cpu_percent(None))  # type: ignore[attr-defined]
                per_core = tuple(
                    float(value)
                    for value in psutil.cpu_percent(None, percpu=True)  # type: ignore[attr-defined]
                )
            except Exception as exc:
                total = None
                per_core = ()
                del exc

        try:
            freq = psutil.cpu_freq()  # type: ignore[attr-defined]
            frequency = (
                Metric.available(freq.current) if freq is not None else Metric.unsupported(
                    "this machine does not report CPU frequency"
                )
            )
        except Exception:
            frequency = Metric.unsupported("CPU frequency is not exposed on this machine")

        return CpuSample(
            total_pct=total,
            per_core_pct=per_core,
            frequency_mhz=frequency,
            temperature_c=Metric.unsupported(
                "Windows exposes no CPU temperature without a kernel driver"
            ),
            logical_count=logical,
            physical_count=physical_count,
        )

    # -------------------------------------------------------------------- memory

    def _sample_memory(self, psutil: object) -> MemorySample:
        virtual = psutil.virtual_memory()  # type: ignore[attr-defined]
        swap = None
        try:
            swap = psutil.swap_memory()  # type: ignore[attr-defined]
        except Exception:
            swap = None

        total = int(virtual.total)
        available = int(getattr(virtual, "available", 0))
        used = int(getattr(virtual, "used", max(0, total - available)))
        percent = float(getattr(virtual, "percent", 0.0))

        return MemorySample(
            total_bytes=total,
            available_bytes=available,
            used_bytes=used,
            used_pct=round(percent, 1),
            commit_total_bytes=int(swap.total) if swap is not None else None,
            commit_used_bytes=int(swap.used) if swap is not None else None,
            pagefile_total_bytes=int(swap.total) if swap is not None else None,
            pagefile_used_bytes=int(swap.used) if swap is not None else None,
        )

    # ----------------------------------------------------------------------- gpu

    def _sample_gpu(self) -> GpuSample:
        if self._gpu_reader is None:
            self._gpu_reader = _default_reader()
        try:
            return self._gpu_reader.read().as_sample()
        except Exception as exc:
            detail = f"GPU reader failed: {type(exc).__name__}"
            return GpuSample(
                utilization=Metric.error(detail),
                dedicated_memory=Metric.error(detail),
            )

    # --------------------------------------------------------------------- disks

    def _sample_disks(
        self, psutil: object, elapsed: float | None
    ) -> tuple[tuple[DiskSample, ...], float | None, float | None]:
        disks: list[DiskSample] = []
        try:
            partitions = psutil.disk_partitions(all=False)  # type: ignore[attr-defined]
        except Exception:
            partitions = ()

        for partition in partitions:
            if "cdrom" in str(getattr(partition, "opts", "")):
                continue
            try:
                usage = psutil.disk_usage(partition.mountpoint)  # type: ignore[attr-defined]
            except (OSError, PermissionError):
                continue
            disks.append(
                DiskSample(
                    mount=str(partition.mountpoint),
                    total_bytes=int(usage.total),
                    free_bytes=int(usage.free),
                )
            )

        read_rate: float | None = None
        write_rate: float | None = None
        if elapsed is not None and elapsed > 0 and self._last_disk is not None:
            current = _disk_totals(psutil)
            read_rate = _delta_rate(
                sum(value[0] for value in current.values()),
                sum(value[0] for value in self._last_disk.values()),
                elapsed,
            )
            write_rate = _delta_rate(
                sum(value[1] for value in current.values()),
                sum(value[1] for value in self._last_disk.values()),
                elapsed,
            )
        return tuple(disks), read_rate, write_rate

    # ------------------------------------------------------------------- network

    def _sample_network(
        self, psutil: object, elapsed: float | None
    ) -> tuple[float | None, float | None, tuple[tuple[str, float, float], ...]]:
        current = _net_totals(psutil)
        if elapsed is None or elapsed <= 0 or self._last_net is None:
            return None, None, ()

        sent = _delta_rate(
            sum(value[0] for value in current.values()),
            sum(value[0] for value in self._last_net.values()),
            elapsed,
        )
        recv = _delta_rate(
            sum(value[1] for value in current.values()),
            sum(value[1] for value in self._last_net.values()),
            elapsed,
        )

        interfaces: list[tuple[str, float, float]] = []
        for name, values in current.items():
            previous = self._last_net.get(name)
            if previous is None:
                continue
            interfaces.append(
                (
                    name,
                    _delta_rate(values[0], previous[0], elapsed),
                    _delta_rate(values[1], previous[1], elapsed),
                )
            )
        interfaces.sort(key=lambda item: item[1] + item[2], reverse=True)
        return sent, recv, tuple(interfaces[:8])

    # ------------------------------------------------------------------ processes

    def _sample_processes(
        self, psutil: object
    ) -> tuple[tuple[ProcessSample, ...], int, bool]:
        monotonic = time.monotonic()
        elapsed = None if self._last_monotonic is None else monotonic - self._last_monotonic
        logical = int(psutil.cpu_count() or 1)  # type: ignore[attr-defined]

        samples: list[ProcessSample] = []
        seen: dict[tuple[int, float], float] = {}
        try:
            iterator: Iterable[object] = psutil.process_iter(  # type: ignore[attr-defined]
                ["pid", "name", "exe", "username", "memory_info", "create_time", "ppid", "status"]
            )
        except Exception:
            return (), 0, False

        for process in iterator:
            sample = _read_process(process, elapsed, logical, self._process_cpu, seen)
            if sample is not None:
                samples.append(sample)

        self._process_cpu = seen
        samples.sort(key=lambda item: item.rss_bytes, reverse=True)
        total = len(samples)
        truncated = total > self._max_processes
        return tuple(samples[: self._max_processes]), total, truncated


class FakeSampler:
    """Deterministic sampler for tests and UI smoke runs.

    Callers supply complete samples; nothing is generated from thin air.
    """

    def __init__(self, samples: Iterable[SystemSample] = ()) -> None:
        self._samples = list(samples)
        self._index = 0
        self.failures = 0

    def sample(self) -> SystemSample:
        if not self._samples:
            raise RuntimeError("FakeSampler has no samples queued")
        if self._index >= len(self._samples):
            # Hold the last sample: a test that runs longer than its script
            # should not crash the engine thread.
            return self._samples[-1]
        sample = self._samples[self._index]
        self._index += 1
        return sample


def _psutil() -> object:
    import psutil

    return psutil


def _default_reader() -> GpuReader:
    return default_gpu_reader()


def _process_key(process: object) -> tuple[int, float]:
    try:
        pid = int(process.pid)  # type: ignore[attr-defined]
        create_time = float(process.create_time())  # type: ignore[attr-defined]
    except Exception:
        return (0, 0.0)
    return (pid, create_time)


def _read_process(
    process: object,
    elapsed: float | None,
    logical: int,
    previous_cpu: dict[tuple[int, float], float],
    seen: dict[tuple[int, float], float],
) -> ProcessSample | None:
    """Turn one psutil process into a sample, or ``None`` if it vanished.

    A process that exits mid-read, or refuses access, is skipped: the table
    shows what was readable, never an invented row.
    """
    try:
        info = process.info  # type: ignore[attr-defined]
        pid = int(info["pid"])
        create_time = float(info.get("create_time") or 0.0)
        key = (pid, create_time)
        cpu_total = _cpu_seconds(process)
        seen[key] = cpu_total

        cpu_pct: float | None = None
        previous = previous_cpu.get(key)
        if elapsed is not None and elapsed > 0 and previous is not None:
            cpu_pct = _process_cpu_pct(cpu_total - previous, elapsed, logical)

        memory = info.get("memory_info")
        rss = int(getattr(memory, "rss", 0) or 0)
        private = getattr(memory, "private", None)

        return ProcessSample(
            pid=pid,
            create_time=create_time,
            name=str(info.get("name") or f"pid {pid}"),
            exe_path=_optional_str(info.get("exe")),
            username=_optional_str(info.get("username")),
            cpu_pct=cpu_pct,
            rss_bytes=rss,
            private_bytes=int(private) if private is not None else None,
            parent_pid=int(info["ppid"]) if info.get("ppid") is not None else None,
            status=_optional_str(info.get("status")),
        )
    except Exception:
        return None


def _cpu_seconds(process: object) -> float:
    try:
        times = process.cpu_times()  # type: ignore[attr-defined]
        return float(times.user) + float(times.system)
    except Exception:
        return 0.0


def _process_cpu_pct(delta_seconds: float, elapsed: float, logical: int) -> float:
    if elapsed <= 0 or logical <= 0:
        return 0.0
    value = delta_seconds / elapsed / logical * 100.0
    return round(max(0.0, min(100.0, value)), 1)


def _disk_totals(psutil: object) -> dict[str, tuple[float, float]]:
    try:
        counters = psutil.disk_io_counters(perdisk=True)  # type: ignore[attr-defined]
    except Exception:
        return {}
    return {
        str(name): (float(value.read_bytes), float(value.write_bytes))
        for name, value in (counters or {}).items()
    }


def _net_totals(psutil: object) -> dict[str, tuple[float, float]]:
    try:
        counters = psutil.net_io_counters(pernic=True)  # type: ignore[attr-defined]
    except Exception:
        return {}
    return {
        str(name): (float(value.bytes_sent), float(value.bytes_recv))
        for name, value in (counters or {}).items()
    }


def _net_errors(psutil: object) -> tuple[tuple[str, int, int, int, int], ...]:
    """Cumulative error and drop counters, straight from the OS."""
    try:
        counters = psutil.net_io_counters(pernic=True)  # type: ignore[attr-defined]
    except Exception:
        return ()
    rows: list[tuple[str, int, int, int, int]] = []
    for name, value in (counters or {}).items():
        rows.append(
            (
                str(name),
                int(getattr(value, "errin", 0) or 0),
                int(getattr(value, "errout", 0) or 0),
                int(getattr(value, "dropin", 0) or 0),
                int(getattr(value, "dropout", 0) or 0),
            )
        )
    return tuple(rows)


def _delta_rate(current: float, previous: float, elapsed: float) -> float:
    return max(0.0, (current - previous) / elapsed)


def _optional_str(value: object) -> str | None:
    return str(value) if value else None


__all__ = ["FakeSampler", "GpuReader", "PsutilSampler", "SystemSampler"]
