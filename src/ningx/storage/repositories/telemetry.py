"""Persistence for telemetry snapshots.

The engine thread owns this object while it runs and writes on that thread, so
SQLite's same-thread rule holds. ``close_thread`` releases the engine thread's
connection when the engine stops.

Only the five structured JSON columns plus the process rows are written; no
personal file content, window titles or network payloads are collected.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any

from ningx.storage.db import Database
from ningx.telemetry.models import (
    CpuSample,
    GpuSample,
    MemorySample,
    Metric,
    MetricState,
    NetworkSample,
    SampleSummary,
    SystemSample,
)


def _utcnow() -> datetime:
    return datetime.now(UTC)


class SqliteTelemetryRepository:
    def __init__(self, db: Database, *, clock: Callable[[], datetime] = _utcnow) -> None:
        self._db = db
        self._clock = clock
    # -------------------------------------------------------------------- writes

    def record(self, sample: SystemSample) -> int:
        captured = _as_utc(sample.captured_at)
        with self._db.transaction() as tx:
            cursor = tx.execute(
                """
                INSERT INTO system_snapshots
                    (scan_run_id, ts, cpu_json, mem_json, gpu_json,
                     disk_json, net_json, health_json)
                VALUES (NULL, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    captured.isoformat(),
                    _encode(_cpu(sample.cpu)),
                    _encode(_memory(sample.memory)),
                    _encode(_gpu(sample.gpu)),
                    _encode(_disks(sample)),
                    _encode(_network(sample.network)),
                    _encode(
                        {
                            "process_count": sample.process_count,
                            "truncated": sample.truncated,
                        }
                    ),
                ),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("snapshot insert did not return an id")
            snapshot_id = int(cursor.lastrowid)
            if sample.processes:
                tx.executemany(
                    """
                    INSERT INTO process_observations
                        (snapshot_id, pid, create_time, name, exe_path, username,
                         cpu_pct, rss_bytes, private_bytes, parent_pid, signature_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, NULL)
                    """,
                    [
                        (
                            snapshot_id,
                            process.pid,
                            process.create_time,
                            process.name,
                            process.exe_path,
                            process.username,
                            process.cpu_pct,
                            process.rss_bytes,
                            process.private_bytes,
                            process.parent_pid,
                        )
                        for process in sample.processes
                    ],
                )
        return snapshot_id

    def prune(self, *, keep: timedelta = timedelta(hours=24)) -> int:
        cutoff = (_as_utc(self._clock()) - keep).isoformat()
        with self._db.transaction() as tx:
            cursor = tx.execute("DELETE FROM system_snapshots WHERE ts < ?", (cutoff,))
        return int(cursor.rowcount or 0)

    # --------------------------------------------------------------------- reads

    def history(self, limit: int = 120) -> list[SampleSummary]:
        if limit <= 0:
            return []
        rows = (
            self._db.connect()
            .execute(
                """
                SELECT ts, cpu_json, mem_json, gpu_json, disk_json, net_json
                FROM system_snapshots
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            .fetchall()
        )
        summaries = [_summarise(row) for row in reversed(rows)]
        return [summary for summary in summaries if summary is not None]

    def count(self) -> int:
        row = self._db.connect().execute("SELECT COUNT(*) AS n FROM system_snapshots").fetchone()
        return int(row["n"]) if row else 0

    def process_count(self) -> int:
        row = self._db.connect().execute(
            "SELECT COUNT(*) AS n FROM process_observations"
        ).fetchone()
        return int(row["n"]) if row else 0

    def close_thread(self) -> None:
        self._db.close_thread_connection()


class FakeTelemetrySink:
    """In-memory sink for engine tests."""

    def __init__(self) -> None:
        self.samples: list[SystemSample] = []
        self.prune_calls = 0
        self.pruned = 0
        self.closed = False
        self.failure: Exception | None = None

    def record(self, sample: SystemSample) -> int:
        if self.failure is not None:
            raise self.failure
        self.samples.append(sample)
        return len(self.samples)

    def prune(self, *, keep: timedelta = timedelta(hours=24)) -> int:
        del keep
        self.prune_calls += 1
        return self.pruned

    def close_thread(self) -> None:
        self.closed = True


# --------------------------------------------------------------------- encoding


def _metric(metric: Metric) -> dict[str, Any]:
    return {"value": metric.value, "state": str(metric.state), "detail": metric.detail}


def _decode_metric(payload: object) -> Metric:
    if not isinstance(payload, dict):
        return Metric.unsupported("no stored value")
    value = payload.get("value")
    state_value = payload.get("state")
    try:
        state = MetricState(str(state_value))
    except ValueError:
        state = MetricState.UNSUPPORTED
    return Metric(
        float(value) if isinstance(value, (int, float)) else None,
        state,
        str(payload.get("detail") or ""),
    )


def _cpu(cpu: CpuSample) -> dict[str, Any]:
    return {
        "total_pct": cpu.total_pct,
        "per_core_pct": list(cpu.per_core_pct),
        "frequency_mhz": _metric(cpu.frequency_mhz),
        "temperature_c": _metric(cpu.temperature_c),
        "logical_count": cpu.logical_count,
        "physical_count": cpu.physical_count,
    }


def _memory(memory: MemorySample) -> dict[str, Any]:
    return {
        "total_bytes": memory.total_bytes,
        "available_bytes": memory.available_bytes,
        "used_bytes": memory.used_bytes,
        "used_pct": memory.used_pct,
        "commit_total_bytes": memory.commit_total_bytes,
        "commit_used_bytes": memory.commit_used_bytes,
        "pagefile_total_bytes": memory.pagefile_total_bytes,
        "pagefile_used_bytes": memory.pagefile_used_bytes,
    }


def _gpu(gpu: GpuSample) -> dict[str, Any]:
    return {
        "utilization": _metric(gpu.utilization),
        "dedicated_memory": _metric(gpu.dedicated_memory),
        "temperature_c": _metric(gpu.temperature_c),
        "clocks_mhz": _metric(gpu.clocks_mhz),
        "power_w": _metric(gpu.power_w),
        "adapter": gpu.adapter,
    }


def _disks(sample: SystemSample) -> dict[str, Any]:
    return {
        "volumes": [
            {
                "mount": disk.mount,
                "total_bytes": disk.total_bytes,
                "free_bytes": disk.free_bytes,
            }
            for disk in sample.disks
        ],
        "read_bytes_per_s": sample.disk_read_bytes_per_s,
        "write_bytes_per_s": sample.disk_write_bytes_per_s,
    }


def _network(network: NetworkSample) -> dict[str, Any]:
    return {
        "sent_bytes_per_s": network.sent_bytes_per_s,
        "recv_bytes_per_s": network.recv_bytes_per_s,
        "interfaces": [
            {"name": name, "sent": sent, "recv": recv}
            for name, sent, recv in network.interfaces
        ],
        "errors": [
            {"name": name, "errin": err_in, "errout": err_out,
             "dropin": drop_in, "dropout": drop_out}
            for name, err_in, err_out, drop_in, drop_out in network.errors
        ],
    }


def _encode(payload: dict[str, Any]) -> str:
    return json.dumps(payload, separators=(",", ":"), sort_keys=True)


def _summarise(row: Any) -> SampleSummary | None:
    try:
        captured = datetime.fromisoformat(str(row["ts"]))
    except (TypeError, ValueError):
        return None
    cpu = _load(row["cpu_json"])
    memory = _load(row["mem_json"])
    gpu = _load(row["gpu_json"])
    disk = _load(row["disk_json"])
    network = _load(row["net_json"])
    return SampleSummary(
        captured_at=_as_utc(captured),
        cpu_pct=_number(cpu.get("total_pct")),
        memory_pct=_number(memory.get("used_pct")),
        gpu_pct=_decode_metric(gpu.get("utilization")).value,
        disk_read_bytes_per_s=_number(disk.get("read_bytes_per_s")),
        disk_write_bytes_per_s=_number(disk.get("write_bytes_per_s")),
        net_sent_bytes_per_s=_number(network.get("sent_bytes_per_s")),
        net_recv_bytes_per_s=_number(network.get("recv_bytes_per_s")),
    )


def _load(raw: object) -> dict[str, Any]:
    if not isinstance(raw, str) or not raw:
        return {}
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _number(value: object) -> float | None:
    return float(value) if isinstance(value, (int, float)) else None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = ["FakeTelemetrySink", "SqliteTelemetryRepository"]
