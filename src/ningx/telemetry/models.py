"""Telemetry contracts.

These models are the only shape in which system measurements travel: the
sampler produces them, the engine broadcasts them, the repository stores them
and the UI renders them. Nothing here can mutate the machine.

Every value carries a state. A metric this hardware cannot report is
``UNSUPPORTED`` — never zero, never a plausible-looking guess.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum


class MetricState(StrEnum):
    AVAILABLE = "available"
    WARMING_UP = "warming_up"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


@dataclass(frozen=True)
class Metric:
    """A single measurement plus the reason it may be missing."""

    value: float | None
    state: MetricState
    detail: str = ""

    @classmethod
    def available(cls, value: float) -> Metric:
        return cls(float(value), MetricState.AVAILABLE)

    @classmethod
    def unsupported(cls, detail: str) -> Metric:
        return cls(None, MetricState.UNSUPPORTED, detail)

    @classmethod
    def warming_up(cls, detail: str = "first delta not yet measured") -> Metric:
        return cls(None, MetricState.WARMING_UP, detail)

    @classmethod
    def error(cls, detail: str) -> Metric:
        return cls(None, MetricState.ERROR, detail)

    @property
    def known(self) -> bool:
        return self.state is MetricState.AVAILABLE

    def text(self, suffix: str = "", digits: int = 1) -> str:
        if self.value is None:
            return {
                MetricState.WARMING_UP: "measuring\u2026",
                MetricState.UNSUPPORTED: "unsupported",
                MetricState.ERROR: "error",
                MetricState.AVAILABLE: "\u2014",
            }[self.state]
        return f"{self.value:.{digits}f}{suffix}"


@dataclass(frozen=True)
class CpuSample:
    total_pct: float | None
    per_core_pct: tuple[float, ...]
    frequency_mhz: Metric
    temperature_c: Metric
    logical_count: int
    physical_count: int | None


@dataclass(frozen=True)
class MemorySample:
    total_bytes: int
    available_bytes: int
    used_bytes: int
    used_pct: float
    commit_total_bytes: int | None = None
    commit_used_bytes: int | None = None
    pagefile_total_bytes: int | None = None
    pagefile_used_bytes: int | None = None


@dataclass(frozen=True)
class GpuSample:
    """GPU telemetry.

    Windows exposes per-engine utilisation counters through PDH. Temperature,
    clocks and board power need a vendor API (NVML, ADL, IGCL) that is not
    bundled, so they stay explicitly unsupported rather than guessed.
    """

    utilization: Metric
    dedicated_memory: Metric
    temperature_c: Metric = field(
        default_factory=lambda: Metric.unsupported("no vendor GPU API is bundled")
    )
    clocks_mhz: Metric = field(
        default_factory=lambda: Metric.unsupported("no vendor GPU API is bundled")
    )
    power_w: Metric = field(
        default_factory=lambda: Metric.unsupported("no vendor GPU API is bundled")
    )
    adapter: str | None = None


@dataclass(frozen=True)
class DiskSample:
    mount: str
    total_bytes: int
    free_bytes: int

    @property
    def used_bytes(self) -> int:
        return max(0, self.total_bytes - self.free_bytes)

    @property
    def used_pct(self) -> float:
        if self.total_bytes <= 0:
            return 0.0
        return round(self.used_bytes / self.total_bytes * 100.0, 1)


@dataclass(frozen=True)
class NetworkSample:
    sent_bytes_per_s: float | None
    recv_bytes_per_s: float | None
    interfaces: tuple[tuple[str, float, float], ...] = ()
    # Cumulative since the adapter was last reset, straight from the OS:
    # (name, receive errors, send errors, receive drops, send drops).
    errors: tuple[tuple[str, int, int, int, int], ...] = ()

    def interface_rate(self, name: str) -> tuple[float, float] | None:
        for interface, sent, recv in self.interfaces:
            if interface == name:
                return sent, recv
        return None

    def interface_errors(self, name: str) -> tuple[int, int, int, int] | None:
        for interface, err_in, err_out, drop_in, drop_out in self.errors:
            if interface == name:
                return (err_in, err_out, drop_in, drop_out)
        return None


@dataclass(frozen=True)
class ProcessSample:
    pid: int
    create_time: float
    name: str
    exe_path: str | None
    username: str | None
    cpu_pct: float | None
    rss_bytes: int
    private_bytes: int | None
    parent_pid: int | None
    status: str | None


@dataclass(frozen=True)
class SystemSample:
    captured_at: datetime
    monotonic: float
    cpu: CpuSample
    memory: MemorySample
    gpu: GpuSample
    disks: tuple[DiskSample, ...]
    network: NetworkSample
    processes: tuple[ProcessSample, ...]
    process_count: int
    truncated: bool
    disk_read_bytes_per_s: float | None = None
    disk_write_bytes_per_s: float | None = None


@dataclass(frozen=True)
class SampleSummary:
    """The narrow shape charts and retention checks need."""

    captured_at: datetime
    cpu_pct: float | None
    memory_pct: float | None
    gpu_pct: float | None
    disk_read_bytes_per_s: float | None
    disk_write_bytes_per_s: float | None
    net_sent_bytes_per_s: float | None
    net_recv_bytes_per_s: float | None


def human_bytes(value: int | float | None) -> str:
    """Render bytes without inventing precision."""
    if value is None:
        return "\u2014"
    size = float(value)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(size) < 1024.0 or unit == "TB":
            return f"{size:.0f} {unit}" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"


def human_rate(value: float | None) -> str:
    if value is None:
        return "\u2014"
    return f"{human_bytes(value)}/s"


__all__ = [
    "CpuSample",
    "DiskSample",
    "GpuSample",
    "MemorySample",
    "Metric",
    "MetricState",
    "NetworkSample",
    "ProcessSample",
    "SampleSummary",
    "SystemSample",
    "human_bytes",
    "human_rate",
]
