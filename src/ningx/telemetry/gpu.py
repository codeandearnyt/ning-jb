"""GPU telemetry through Windows performance counters.

WDDM 2.x registers ``GPU Engine`` and ``GPU Adapter Memory`` counter sets. PDH
gives them to us without a vendor SDK, which matters because this build bundles
none. A counter that is absent on the running machine is reported as
``UNSUPPORTED`` with the reason; it is never replaced with a zero.

Only the engine thread may use this object: a PDH query is stateful and not
thread-safe.
"""

from __future__ import annotations

import os
from contextlib import suppress
from dataclasses import dataclass
from importlib.util import find_spec
from typing import Any

from ningx.telemetry.models import GpuSample, Metric

_ENGINE_OBJECT = "GPU Engine"
_MEMORY_OBJECT = "GPU Adapter Memory"
_UTILIZATION_COUNTER = "Utilization Percentage"
_DEDICATED_COUNTER = "Dedicated Usage"
_ENGINE_PREFIX = "engtype_3D"


@dataclass(frozen=True)
class GpuReading:
    utilization: Metric
    dedicated_memory: Metric
    adapter: str | None = None

    def as_sample(self) -> GpuSample:
        return GpuSample(
            utilization=self.utilization,
            dedicated_memory=self.dedicated_memory,
            adapter=self.adapter,
        )


class NullGpuReader:
    """Used on non-Windows hosts and when no GPU API is available."""

    def __init__(self, detail: str = "GPU counters are only read on Windows") -> None:
        self._detail = detail

    def read(self) -> GpuReading:
        return GpuReading(
            utilization=Metric.unsupported(self._detail),
            dedicated_memory=Metric.unsupported(self._detail),
        )


class PdhGpuReader:
    """Aggregate 3D-engine utilisation from the ``GPU Engine`` counter set.

    ``Utilization Percentage`` is a rate counter: it needs two collections to
    produce a value. The first :meth:`read` opens the query and collects the
    baseline, so the first sample is ``WARMING_UP`` and later samples are real.
    """

    def __init__(self, *, refresh_instances_after: int = 300) -> None:
        self._pdh: Any | None = None
        self._query: Any | None = None
        self._counters: dict[str, Any] = {}
        self._memory_counters: dict[str, Any] = {}
        self._collections = 0
        self._refresh_instances_after = max(1, refresh_instances_after)

    # ------------------------------------------------------------------- public

    def read(self) -> GpuReading:
        try:
            return self._read()
        except Exception as exc:
            self._close()
            detail = f"GPU counters failed: {type(exc).__name__}"
            return GpuReading(
                utilization=Metric.error(detail),
                dedicated_memory=Metric.error(detail),
            )

    # ------------------------------------------------------------------ internals

    def _read(self) -> GpuReading:
        pdh = self._load()
        if self._query is None:
            detail = self._open(pdh)
            if detail is not None:
                return GpuReading(
                    utilization=Metric.unsupported(detail),
                    dedicated_memory=Metric.unsupported(detail),
                )

        assert self._query is not None
        pdh.CollectQueryData(self._query)
        self._collections += 1

        if self._collections == 1:
            baseline = Metric.warming_up("GPU counter baseline collected")
            return GpuReading(utilization=baseline, dedicated_memory=baseline)

        utilization = self._read_utilization(pdh)
        memory = self._read_memory(pdh)

        if self._collections % self._refresh_instances_after == 0:
            # Engine instances come and go with processes; rebuild on a slow
            # cadence so a long session keeps seeing new engines.
            self._close()

        return GpuReading(utilization=utilization, dedicated_memory=memory)

    def _load(self) -> Any:
        if self._pdh is None:
            import win32pdh

            self._pdh = win32pdh
        return self._pdh

    def _open(self, pdh: Any) -> str | None:
        """Open the query. Returns an unsupported reason, or ``None`` on success."""
        with suppress(Exception):
            instances = self._instances(pdh, _ENGINE_OBJECT)
            if not instances:
                return "no 3D GPU engine counters are registered"

            query = pdh.OpenQuery()
            counters: dict[str, Any] = {}
            for instance in instances:
                if _ENGINE_PREFIX not in instance:
                    continue
                with suppress(Exception):
                    path = pdh.MakeCounterPath(
                        (None, _ENGINE_OBJECT, instance, None, 0, _UTILIZATION_COUNTER)
                    )
                    counters[instance] = pdh.AddCounter(query, path)

            if not counters:
                pdh.CloseQuery(query)
                return "no 3D GPU engine counters are registered"

            self._query = query
            self._counters = counters
            self._memory_counters = self._add_memory_counters(pdh, query)
            return None

        return "this machine exposes no GPU Engine counters"

    def _add_memory_counters(self, pdh: Any, query: Any) -> dict[str, Any]:
        counters: dict[str, Any] = {}
        with suppress(Exception):
            for instance in self._instances(pdh, _MEMORY_OBJECT):
                with suppress(Exception):
                    path = pdh.MakeCounterPath(
                        (None, _MEMORY_OBJECT, instance, None, 0, _DEDICATED_COUNTER)
                    )
                    counters[instance] = pdh.AddCounter(query, path)
        return counters

    def _read_utilization(self, pdh: Any) -> Metric:
        values: list[float] = []
        for counter in self._counters.values():
            with suppress(Exception):
                _value, formatted = pdh.GetFormattedCounterValue(
                    counter, pdh.PDH_FMT_DOUBLE
                )
                if isinstance(formatted, (int, float)):
                    values.append(float(formatted))
        if not values:
            return Metric.warming_up("GPU engine counters produced no value yet")
        # A GPU has several 3D engines; the busiest one is what a user reads as
        # "GPU usage", matching Task Manager.
        return Metric.available(min(100.0, max(values)))

    def _read_memory(self, pdh: Any) -> Metric:
        values: list[float] = []
        for counter in self._memory_counters.values():
            with suppress(Exception):
                _value, formatted = pdh.GetFormattedCounterValue(
                    counter, pdh.PDH_FMT_DOUBLE
                )
                if isinstance(formatted, (int, float)) and formatted > 0:
                    values.append(float(formatted))
        if not values:
            return Metric.unsupported("GPU memory counters are unavailable")
        return Metric.available(sum(values))

    def _instances(self, pdh: Any, object_name: str) -> list[str]:
        _counters, instances = pdh.EnumObjectItems(
            None, None, object_name, pdh.PERF_DETAIL_WIZARD
        )
        return [str(name) for name in instances]

    def _close(self) -> None:
        if self._query is not None and self._pdh is not None:
            with suppress(Exception):
                self._pdh.CloseQuery(self._query)
        self._query = None
        self._counters = {}
        self._memory_counters = {}
        self._collections = 0


def default_gpu_reader() -> PdhGpuReader | NullGpuReader:
    if os.name != "nt":
        return NullGpuReader()
    if find_spec("win32pdh") is None:
        return NullGpuReader("pywin32 is not installed, so GPU counters cannot be read")
    return PdhGpuReader()


__all__ = ["GpuReading", "NullGpuReader", "PdhGpuReader", "default_gpu_reader"]
