"""Telemetry: read-only sampler, GPU counters, engine thread, persistence."""

from __future__ import annotations

import ast
import sys
import time
import types
from datetime import timedelta
from pathlib import Path

import pytest

from ningx.storage.db import Database
from ningx.storage.repositories.telemetry import (
    FakeTelemetrySink,
    SqliteTelemetryRepository,
)
from ningx.telemetry.engine import (
    EngineState,
    SampleProduced,
    StateChanged,
    Subscription,
    TelemetryEngine,
    TelemetryError,
)
from ningx.telemetry.gpu import NullGpuReader, PdhGpuReader
from ningx.telemetry.models import MetricState
from ningx.telemetry.sampler import FakeSampler, PsutilSampler
from tests.telemetry_fakes import BASE_TIME, GIB, make_sample, make_series

REPO_ROOT = Path(__file__).resolve().parents[1]


# --------------------------------------------------------------------- sampler


def test_sampler_module_imports_nothing_that_can_mutate() -> None:
    path = REPO_ROOT / "src" / "ningx" / "telemetry" / "sampler.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)

    forbidden = ("subprocess", "shutil", "sqlite3", "winreg", "win32api", "ningx.winapi")
    for name in forbidden:
        assert not any(
            module == name or module.startswith(name + ".") for module in imported
        ), f"sampler must not import {name}: {sorted(imported)}"


def test_real_sampler_reads_plausible_values_from_this_machine() -> None:
    sampler = PsutilSampler(max_processes=5)
    first = sampler.sample()
    time.sleep(0.05)
    second = sampler.sample()

    assert first.captured_at.tzinfo is not None
    assert first.memory.total_bytes > 0
    assert first.memory.used_bytes <= first.memory.total_bytes
    assert 0.0 <= first.memory.used_pct <= 100.0
    assert first.cpu.logical_count >= 1
    assert len(first.processes) <= 5
    assert first.process_count >= len(first.processes)

    # The second sample has a real interval behind it.
    assert second.cpu.total_pct is not None
    assert 0.0 <= second.cpu.total_pct <= 100.0
    assert len(second.cpu.per_core_pct) == second.cpu.logical_count
    assert second.processes
    assert any(process.cpu_pct is not None for process in second.processes)


def test_real_sampler_reports_rates_only_after_a_baseline() -> None:
    sampler = PsutilSampler(max_processes=3)
    first = sampler.sample()
    assert first.disk_read_bytes_per_s is None
    assert first.network.sent_bytes_per_s is None

    time.sleep(0.05)
    second = sampler.sample()
    assert second.disk_read_bytes_per_s is not None
    assert second.network.sent_bytes_per_s is not None


def test_real_sampler_marks_gpu_temperature_unsupported() -> None:
    sample = PsutilSampler(max_processes=1).sample()
    assert sample.gpu.temperature_c.state is MetricState.UNSUPPORTED
    assert sample.gpu.temperature_c.value is None
    assert sample.gpu.clocks_mhz.state is MetricState.UNSUPPORTED
    assert sample.gpu.power_w.state is MetricState.UNSUPPORTED


# ------------------------------------------------------------------------- gpu


class _FakePdh:
    PDH_FMT_DOUBLE = 0.0
    PERF_DETAIL_WIZARD = 400

    def __init__(self) -> None:
        self.values: list[float] = [11.0, 47.0, 2.0 * GIB]
        self.closed = 0
        self.collections = 0

    def EnumObjectItems(
        self, machine: object, source: object, object_name: str, detail: int
    ) -> tuple[list[str], list[str]]:
        if object_name == "GPU Engine":
            return (
                ["Utilization Percentage"],
                [
                    "pid_1_luid_0_phys_0_eng_0_engtype_3D",
                    "pid_2_luid_0_phys_0_eng_1_engtype_3D",
                    "pid_3_luid_0_phys_0_eng_2_engtype_Copy",
                ],
            )
        if object_name == "GPU Adapter Memory":
            return (["Dedicated Usage"], ["luid_0x0_phys_0"])
        raise OSError("unknown object")

    def OpenQuery(self) -> object:
        return object()

    def MakeCounterPath(self, parts: tuple[object, ...]) -> str:
        return "\\".join(str(part) for part in parts if part is not None)

    def AddCounter(self, query: object, path: str) -> str:
        return path

    def CollectQueryData(self, query: object) -> None:
        self.collections += 1

    def GetFormattedCounterValue(self, counter: str, fmt: float) -> tuple[float, float]:
        return (0.0, self.values.pop(0) if self.values else 0.0)

    def CloseQuery(self, query: object) -> None:
        self.closed += 1


@pytest.fixture
def fake_pdh(monkeypatch: pytest.MonkeyPatch) -> _FakePdh:
    module = types.ModuleType("win32pdh")
    fake = _FakePdh()
    for name in (
        "PDH_FMT_DOUBLE",
        "PERF_DETAIL_WIZARD",
        "EnumObjectItems",
        "OpenQuery",
        "MakeCounterPath",
        "AddCounter",
        "CollectQueryData",
        "GetFormattedCounterValue",
        "CloseQuery",
    ):
        setattr(module, name, getattr(fake, name))
    monkeypatch.setitem(sys.modules, "win32pdh", module)
    return fake


def test_gpu_reader_needs_a_baseline_before_reporting_utilisation(fake_pdh: _FakePdh) -> None:
    reader = PdhGpuReader()

    warming = reader.read()
    assert warming.utilization.state is MetricState.WARMING_UP
    assert fake_pdh.collections == 1

    reading = reader.read()
    assert reading.utilization.state is MetricState.AVAILABLE
    assert reading.utilization.value == 47.0
    assert reading.dedicated_memory.value == pytest.approx(2.0 * GIB)


def test_gpu_reader_reports_unsupported_when_the_counter_set_is_missing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    module = types.ModuleType("win32pdh")

    def enum(*_: object) -> tuple[list[str], list[str]]:
        raise OSError("no counters")

    module.EnumObjectItems = enum  # type: ignore[attr-defined]
    module.PERF_DETAIL_WIZARD = 400  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "win32pdh", module)

    reading = PdhGpuReader().read()
    assert reading.utilization.state is MetricState.UNSUPPORTED
    assert "no GPU Engine counters" in reading.utilization.detail


def test_gpu_reader_reports_unsupported_when_no_3d_engine_exists(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def enum(*_: object) -> tuple[list[str], list[str]]:
        return (["Utilization Percentage"], ["engtype_Copy"])

    def open_query() -> object:
        return object()

    def close_query(_query: object) -> None:
        return None

    module = types.ModuleType("win32pdh")
    module.EnumObjectItems = enum  # type: ignore[attr-defined]
    module.PERF_DETAIL_WIZARD = 400  # type: ignore[attr-defined]
    module.OpenQuery = open_query  # type: ignore[attr-defined]
    module.CloseQuery = close_query  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "win32pdh", module)

    reading = PdhGpuReader().read()
    assert reading.utilization.state is MetricState.UNSUPPORTED
    assert "no 3D GPU engine" in reading.utilization.detail


def test_null_gpu_reader_never_pretends_to_measure() -> None:
    reading = NullGpuReader().read()
    assert reading.utilization.state is MetricState.UNSUPPORTED
    assert reading.utilization.value is None


# ---------------------------------------------------------------------- engine


def _drain(
    subscription: Subscription,
    until: object,
    *,
    timeout: float = 5.0,
) -> list[object]:
    predicate = until
    events: list[object] = []
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        events.extend(subscription.poll())
        assert callable(predicate)
        if predicate(events):
            return events
        time.sleep(0.01)
    raise AssertionError(f"condition not reached; events={events}")


def _count(events: list[object]) -> int:
    return sum(isinstance(event, SampleProduced) for event in events)


def test_engine_samples_on_its_own_thread_and_stops_cleanly() -> None:
    sink = FakeTelemetrySink()
    engine = TelemetryEngine(
        FakeSampler(make_series(4)), sink=sink, interval_s=0.02, retention_every=2
    )
    subscription = engine.subscribe()
    engine.start()
    try:
        events = _drain(subscription, lambda items: _count(items) >= 3)
        assert any(isinstance(event, StateChanged) for event in events)
        samples = [event for event in events if isinstance(event, SampleProduced)]
        assert all(event.persisted for event in samples)
        assert all(event.sample.captured_at.tzinfo is not None for event in samples)
    finally:
        subscription.close()
        assert engine.stop(timeout=5.0)

    status = engine.status
    assert status.state is EngineState.STOPPED
    assert status.samples >= 3
    assert status.persisted == status.samples
    assert status.last_sample_at is not None
    assert status.last_error is None
    assert len(sink.samples) >= 3
    assert sink.closed
    assert sink.prune_calls >= 1


def test_pause_stops_sampling_and_resume_restarts_it() -> None:
    engine = TelemetryEngine(FakeSampler(make_series(20)), interval_s=0.02)
    subscription = engine.subscribe()
    engine.start()
    try:
        _drain(subscription, lambda items: _count(items) >= 2)
        engine.pause()
        assert engine.status.state is EngineState.PAUSED
        time.sleep(0.1)
        after_pause = engine.status.samples
        time.sleep(0.15)
        # At most one sample can have been in flight when pause was requested.
        assert engine.status.samples <= after_pause + 1

        engine.resume()
        assert engine.status.state is EngineState.RUNNING
        resumed = _drain(
            subscription,
            lambda _items: engine.status.samples > after_pause + 1,
        )
        assert resumed is not None
    finally:
        subscription.close()
        assert engine.stop(timeout=5.0)


def test_sampler_failure_is_reported_and_does_not_kill_the_engine() -> None:
    class BrokenSampler:
        def sample(self) -> object:
            raise RuntimeError("probe exploded")

    engine = TelemetryEngine(BrokenSampler(), interval_s=0.02, backoff_s=0.02)  # type: ignore[arg-type]
    subscription = engine.subscribe()
    engine.start()
    try:
        events = _drain(
            subscription,
            lambda items: any(isinstance(event, TelemetryError) for event in items),
        )
        errors = [event for event in events if isinstance(event, TelemetryError)]
        assert "probe exploded" in errors[0].message
        assert engine.status.state is EngineState.RUNNING
        assert engine.status.last_error is not None
    finally:
        subscription.close()
        assert engine.stop(timeout=5.0)


def test_persistence_failure_is_reported_without_stopping_the_stream() -> None:
    sink = FakeTelemetrySink()
    sink.failure = RuntimeError("disk full")
    engine = TelemetryEngine(FakeSampler(make_series(3)), sink=sink, interval_s=0.02)
    subscription = engine.subscribe()
    engine.start()
    try:
        events = _drain(subscription, lambda items: _count(items) >= 2)
        samples = [event for event in events if isinstance(event, SampleProduced)]
        assert all(not event.persisted for event in samples)
        assert any(isinstance(event, TelemetryError) for event in events)
        assert engine.status.last_persist_error is not None
        assert engine.status.samples >= 2
    finally:
        subscription.close()
        assert engine.stop(timeout=5.0)


def test_engine_reports_states_from_start_to_stop() -> None:
    engine = TelemetryEngine(FakeSampler(make_series(1)), interval_s=0.05)
    subscription = engine.subscribe()
    engine.start()
    try:
        _drain(subscription, lambda items: _count(items) >= 1)
    finally:
        subscription.close()
    engine.stop(timeout=5.0)

    states = [engine.status.state]
    assert states == [EngineState.STOPPED]


def test_subscription_drops_the_oldest_event_rather_than_blocking() -> None:
    engine = TelemetryEngine(FakeSampler(make_series(1)), interval_s=0.05)
    subscription = engine.subscribe(maxsize=1)
    try:
        engine._publish(StateChanged(EngineState.RUNNING, "first"))
        engine._publish(StateChanged(EngineState.PAUSED, "second"))
        events = subscription.poll()
        assert len(events) == 1
        assert isinstance(events[0], StateChanged)
        assert events[0].state is EngineState.PAUSED
    finally:
        subscription.close()


def test_stop_is_idempotent_and_safe_before_start() -> None:
    engine = TelemetryEngine(FakeSampler(make_series(1)))
    assert engine.stop(timeout=1.0)
    assert engine.stop(timeout=1.0)
    assert engine.status.state is EngineState.STOPPED


# ------------------------------------------------------------------- repository


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "telemetry.db")
    database.migrate()
    try:
        yield database
    finally:
        database.close()


def test_repository_stores_snapshot_and_process_rows(db: Database) -> None:
    repository = SqliteTelemetryRepository(db)
    sample = make_sample(processes=(make_sample().processes[0],))

    snapshot_id = repository.record(sample)
    assert snapshot_id > 0
    assert repository.count() == 1
    assert repository.process_count() == 1

    row = db.connect().execute("SELECT * FROM system_snapshots").fetchone()
    assert row["ts"] == BASE_TIME.isoformat()
    assert "total_pct" in row["cpu_json"]
    assert "used_pct" in row["mem_json"]


def test_history_returns_summaries_in_chronological_order(db: Database) -> None:
    repository = SqliteTelemetryRepository(db)
    for sample in make_series(3):
        repository.record(sample)

    history = repository.history(limit=10)
    assert [summary.captured_at for summary in history] == sorted(
        summary.captured_at for summary in history
    )
    assert history[-1].cpu_pct == 12.0
    assert history[-1].memory_pct == 52.0
    assert history[-1].gpu_pct == 12.5
    assert history[-1].net_sent_bytes_per_s == 512.0
    assert history[-1].disk_read_bytes_per_s == 1024.0


def test_history_honours_the_limit_and_survives_bad_json(db: Database) -> None:
    repository = SqliteTelemetryRepository(db)
    for sample in make_series(4):
        repository.record(sample)
    db.connect().execute("UPDATE system_snapshots SET cpu_json = 'not json' WHERE id = 2")

    history = repository.history(limit=2)
    assert len(history) == 2


def test_prune_removes_old_snapshots_and_cascades_to_processes(db: Database) -> None:
    clock = {"now": BASE_TIME}
    repository = SqliteTelemetryRepository(db, clock=lambda: clock["now"])
    repository.record(make_sample(at=BASE_TIME))
    repository.record(make_sample(at=BASE_TIME + timedelta(hours=2)))

    clock["now"] = BASE_TIME + timedelta(hours=3)
    removed = repository.prune(keep=timedelta(hours=2))

    assert removed == 1
    assert repository.count() == 1
    assert repository.process_count() == 1


def test_repository_closes_only_its_thread_connection(db: Database) -> None:
    repository = SqliteTelemetryRepository(db)
    repository.record(make_sample())
    repository.close_thread()

    # The database stays usable from this thread after the engine's connection
    # is released.
    assert repository.count() == 1


def test_unsupported_gpu_is_stored_without_a_value(db: Database) -> None:
    repository = SqliteTelemetryRepository(db)
    repository.record(make_sample(gpu_state="unsupported"))

    summary = repository.history(limit=1)[0]
    assert summary.gpu_pct is None
