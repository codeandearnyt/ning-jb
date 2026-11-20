"""Deterministic telemetry samples. No test here reads the real machine."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

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

BASE_TIME = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
GIB = 1024**3


def make_process(
    pid: int = 4242,
    *,
    name: str = "example.exe",
    rss_bytes: int = 512 * 1024 * 1024,
    cpu_pct: float | None = 4.5,
    exe_path: str | None = r"C:\Program Files\Example\example.exe",
) -> ProcessSample:
    return ProcessSample(
        pid=pid,
        create_time=1000.0,
        name=name,
        exe_path=exe_path,
        username="dev\\user",
        cpu_pct=cpu_pct,
        rss_bytes=rss_bytes,
        private_bytes=rss_bytes,
        parent_pid=500,
        status="running",
    )


def make_sample(
    at: datetime = BASE_TIME,
    *,
    cpu_pct: float | None = 25.0,
    memory_pct: float = 62.0,
    gpu_pct: float | None = 12.5,
    gpu_state: str = "available",
    processes: tuple[ProcessSample, ...] | None = None,
    disk_read: float | None = 1024.0,
    disk_write: float | None = 2048.0,
    net_sent: float | None = 512.0,
    net_recv: float | None = 4096.0,
    disk_free_pct: float = 25.0,
    disks: tuple[DiskSample, ...] | None = None,
) -> SystemSample:
    total = 16 * GIB
    used = int(total * memory_pct / 100)
    if gpu_state == "available" and gpu_pct is not None:
        utilization = Metric.available(gpu_pct)
    elif gpu_state == "unsupported":
        utilization = Metric.unsupported("no vendor GPU API")
    elif gpu_state == "warming":
        utilization = Metric.warming_up()
    else:
        utilization = Metric.error("GPU counters failed")

    return SystemSample(
        captured_at=at,
        monotonic=at.timestamp(),
        cpu=CpuSample(
            total_pct=cpu_pct,
            # A warming CPU has no rate yet, so it has no per-core rates either.
            per_core_pct=(cpu_pct, cpu_pct / 2) if cpu_pct is not None else (),
            frequency_mhz=Metric.available(3600.0),
            temperature_c=Metric.unsupported("no kernel driver"),
            logical_count=16,
            physical_count=8,
        ),
        memory=MemorySample(
            total_bytes=total,
            available_bytes=total - used,
            used_bytes=used,
            used_pct=memory_pct,
            commit_total_bytes=20 * GIB,
            commit_used_bytes=12 * GIB,
            pagefile_total_bytes=4 * GIB,
            pagefile_used_bytes=GIB,
        ),
        gpu=GpuSample(
            utilization=utilization,
            dedicated_memory=Metric.available(2 * GIB),
        ),
        disks=(
            disks
            if disks is not None
            else (
                DiskSample(
                    mount="C:\\",
                    total_bytes=1000 * GIB,
                    free_bytes=int(1000 * GIB * disk_free_pct / 100),
                ),
            )
        ),
        network=NetworkSample(
            sent_bytes_per_s=net_sent,
            recv_bytes_per_s=net_recv,
            interfaces=(("Ethernet", net_sent or 0.0, net_recv or 0.0),),
        ),
        processes=processes if processes is not None else (make_process(),),
        process_count=len(processes) if processes is not None else 1,
        truncated=False,
        disk_read_bytes_per_s=disk_read,
        disk_write_bytes_per_s=disk_write,
    )


def make_series(count: int = 5, *, step_seconds: int = 2) -> list[SystemSample]:
    return [
        make_sample(
            at=BASE_TIME + timedelta(seconds=index * step_seconds),
            cpu_pct=10.0 + index,
            memory_pct=50.0 + index,
        )
        for index in range(count)
    ]


__all__ = ["BASE_TIME", "GIB", "make_process", "make_sample", "make_series"]
