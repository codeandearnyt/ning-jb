"""The telemetry engine: one thread, one asyncio loop, one sampler.

Everything that reads the machine happens on the engine thread. The UI thread
subscribes to a bounded queue and never calls into the sampler, so a slow probe
can never freeze a window and a Qt object is never touched off the main thread.

The engine cannot mutate anything: it holds a sampler, an optional persistence
sink and a logger. There is no operations object in its constructor.
"""

from __future__ import annotations

import asyncio
import logging
import queue
import threading
import time
from collections.abc import Callable
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Protocol

from ningx.telemetry.models import SystemSample
from ningx.telemetry.sampler import SystemSampler


class EngineState(StrEnum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    PAUSED = "paused"
    STOPPING = "stopping"
    FAILED = "failed"


@dataclass(frozen=True)
class EngineStatus:
    state: EngineState
    samples: int
    persisted: int
    last_sample_at: datetime | None
    last_error: str | None
    last_persist_error: str | None


@dataclass(frozen=True)
class StateChanged:
    state: EngineState
    detail: str = ""


@dataclass(frozen=True)
class SampleProduced:
    sample: SystemSample
    persisted: bool


@dataclass(frozen=True)
class TelemetryError:
    message: str
    fatal: bool = False


type TelemetryEvent = StateChanged | SampleProduced | TelemetryError


class TelemetrySink(Protocol):
    def record(self, sample: SystemSample) -> int: ...

    def prune(self, *, keep: timedelta) -> int: ...

    def close_thread(self) -> None: ...


class Subscription:
    """A bounded queue of engine events, drained by the UI thread."""

    def __init__(self, engine: TelemetryEngine, maxsize: int = 16) -> None:
        self._engine = engine
        self._queue: queue.Queue[TelemetryEvent] = queue.Queue(maxsize=maxsize)
        self._closed = False

    def poll(self, limit: int = 64) -> list[TelemetryEvent]:
        events: list[TelemetryEvent] = []
        while len(events) < limit:
            try:
                events.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return events

    @property
    def queue(self) -> queue.Queue[TelemetryEvent]:
        """The engine's publish target. Only the engine writes to it."""
        return self._queue

    def close(self) -> None:
        if not self._closed:
            self._closed = True
            self._engine._remove(self)

    @property
    def closed(self) -> bool:
        return self._closed


class TelemetryEngine:
    def __init__(
        self,
        sampler: SystemSampler,
        *,
        sink: TelemetrySink | None = None,
        interval_s: float = 2.0,
        retention: timedelta = timedelta(hours=24),
        retention_every: int = 300,
        backoff_s: float = 5.0,
        clock: Callable[[], datetime] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._sampler = sampler
        self._sink = sink
        self._interval_s = max(0.05, interval_s)
        self._retention = retention
        self._retention_every = max(1, retention_every)
        self._backoff_s = max(0.1, backoff_s)
        self._clock = clock or _utcnow
        self._logger = logger or logging.getLogger("ningx.telemetry")

        self._lock = threading.Lock()
        self._subscribers: list[Subscription] = []
        self._thread: threading.Thread | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._stop_requested = threading.Event()
        self._stop_event: asyncio.Event | None = None
        self._paused = threading.Event()

        self._state = EngineState.STOPPED
        self._latest: SystemSample | None = None
        self._samples = 0
        self._persisted = 0
        self._last_error: str | None = None
        self._last_persist_error: str | None = None

    # ------------------------------------------------------------------ lifecycle

    def start(self) -> None:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return
            self._stop_requested.clear()
            thread = threading.Thread(
                target=self._thread_main,
                name="ningx-telemetry",
                daemon=True,
            )
            self._thread = thread
            self._state = EngineState.STARTING
        # Publish outside the lock: _publish takes the same lock.
        self._publish(StateChanged(state=EngineState.STARTING, detail="engine thread starting"))
        thread.start()

    def stop(self, timeout: float = 10.0) -> bool:
        """Request a stop and wait. Returns whether the thread actually exited."""
        self._stop_requested.set()
        thread = self._thread
        if thread is None or not thread.is_alive():
            self._set_state(EngineState.STOPPED, "engine is not running")
            return True

        self._set_state(EngineState.STOPPING, "stop requested")

        loop = self._loop
        event = self._stop_event
        if loop is not None and event is not None:
            with suppress(RuntimeError):
                loop.call_soon_threadsafe(event.set)

        thread.join(timeout)
        if thread.is_alive():
            self._publish(
                TelemetryError(
                    f"telemetry thread did not stop within {timeout:.0f}s",
                    fatal=True,
                )
            )
            return False
        return True

    def pause(self) -> None:
        if self._state in (EngineState.RUNNING, EngineState.STARTING):
            self._paused.set()
            self._set_state(EngineState.PAUSED, "sampling paused by the user")

    def resume(self) -> None:
        if self._state is EngineState.PAUSED:
            self._paused.clear()
            self._set_state(EngineState.RUNNING, "sampling resumed")

    # --------------------------------------------------------------------- access

    @property
    def latest(self) -> SystemSample | None:
        return self._latest

    @property
    def status(self) -> EngineStatus:
        return EngineStatus(
            state=self._state,
            samples=self._samples,
            persisted=self._persisted,
            last_sample_at=self._latest.captured_at if self._latest is not None else None,
            last_error=self._last_error,
            last_persist_error=self._last_persist_error,
        )

    def subscribe(self, maxsize: int = 16) -> Subscription:
        subscription = Subscription(self, maxsize=maxsize)
        with self._lock:
            self._subscribers.append(subscription)
        return subscription

    def _remove(self, subscription: Subscription) -> None:
        with self._lock:
            if subscription in self._subscribers:
                self._subscribers.remove(subscription)

    # ------------------------------------------------------------------- internals

    def _thread_main(self) -> None:
        loop = asyncio.new_event_loop()
        self._loop = loop
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._run())
        except BaseException as exc:
            self._last_error = f"{type(exc).__name__}: {exc}"
            self._logger.exception("telemetry.engine_crashed")
            self._set_state(EngineState.FAILED, self._last_error)
        finally:
            self._loop = None
            with suppress(Exception):
                loop.run_until_complete(loop.shutdown_asyncgens())
            asyncio.set_event_loop(None)
            loop.close()
            if self._sink is not None:
                with suppress(Exception):
                    self._sink.close_thread()
            with self._lock:
                self._thread = None
            self._set_state(EngineState.STOPPED, "engine thread exited")

    async def _run(self) -> None:
        event = asyncio.Event()
        self._stop_event = event
        if self._stop_requested.is_set():
            event.set()

        self._set_state(EngineState.RUNNING, f"sampling every {self._interval_s:g}s")
        since_prune = 0

        while not event.is_set():
            if self._paused.is_set():
                await self._wait(event, 0.2)
                continue

            started = time.monotonic()
            sample: SystemSample | None = None
            try:
                sample = await asyncio.to_thread(self._sampler.sample)
            except Exception as exc:
                self._last_error = f"{type(exc).__name__}: {exc}"
                self._logger.warning("telemetry.sample_failed", exc_info=True)
                self._publish(TelemetryError(f"sampling failed: {self._last_error}"))
                await self._wait(event, self._backoff_s)
                continue

            self._latest = sample
            self._samples += 1

            persisted = False
            if self._sink is not None:
                persisted = self._persist(sample)
                since_prune += 1
                if persisted and since_prune >= self._retention_every:
                    since_prune = 0
                    self._prune()

            self._publish(SampleProduced(sample=sample, persisted=persisted))

            elapsed = time.monotonic() - started
            await self._wait(event, max(0.0, self._interval_s - elapsed))

        self._stop_event = None

    def _persist(self, sample: SystemSample) -> bool:
        assert self._sink is not None
        try:
            self._sink.record(sample)
        except Exception as exc:
            self._last_persist_error = f"{type(exc).__name__}: {exc}"
            self._logger.warning("telemetry.persist_failed", exc_info=True)
            self._publish(TelemetryError(f"snapshot not stored: {self._last_persist_error}"))
            return False
        self._last_persist_error = None
        self._persisted += 1
        return True

    def _prune(self) -> None:
        assert self._sink is not None
        try:
            removed = self._sink.prune(keep=self._retention)
        except Exception as exc:
            self._logger.warning("telemetry.prune_failed", exc_info=True)
            self._publish(TelemetryError(f"retention sweep failed: {type(exc).__name__}"))
            return
        if removed:
            self._logger.info("telemetry.pruned", extra={"rows": removed})

    async def _wait(self, event: asyncio.Event, timeout: float) -> None:
        if timeout <= 0:
            await asyncio.sleep(0)
            return
        with suppress(TimeoutError):
            await asyncio.wait_for(event.wait(), timeout=timeout)

    # -------------------------------------------------------------------- events

    def _set_state(self, state: EngineState, detail: str = "") -> None:
        with self._lock:
            self._state = state
        self._publish(StateChanged(state=state, detail=detail))

    def _publish(self, event: TelemetryEvent) -> None:
        with self._lock:
            subscribers = list(self._subscribers)
        for subscription in subscribers:
            queue_in = subscription.queue
            try:
                queue_in.put_nowait(event)
            except queue.Full:
                # Drop the oldest event: a UI that falls behind should see the
                # newest state, never a backlog of stale ones.
                with suppress(queue.Empty):
                    queue_in.get_nowait()
                with suppress(queue.Full):
                    queue_in.put_nowait(event)


def _utcnow() -> datetime:
    return datetime.now(UTC)


__all__ = [
    "EngineState",
    "EngineStatus",
    "SampleProduced",
    "StateChanged",
    "Subscription",
    "TelemetryEngine",
    "TelemetryError",
    "TelemetryEvent",
    "TelemetrySink",
]
