"""Dashboard derivation: health from measured values only.

The health score is a documented arithmetic combination of the metrics this
machine actually reported. A metric that is unavailable is excluded and the
weights are renormalised, so a missing GPU sensor cannot flatter the score.
There is no machine-learning guess and no baseline comparison with invented
data.
"""

from __future__ import annotations

from dataclasses import dataclass

from ningx.telemetry.models import MetricState, SystemSample, human_bytes

# CPU and memory describe current pressure; disk describes headroom, which is
# slower to become urgent; GPU is weighted last because it is often unavailable.
_WEIGHTS: dict[str, float] = {"cpu": 0.30, "memory": 0.30, "disk": 0.25, "gpu": 0.15}


@dataclass(frozen=True)
class HealthComponent:
    key: str
    label: str
    score: float
    detail: str


@dataclass(frozen=True)
class HealthExclusion:
    key: str
    label: str
    reason: str


@dataclass(frozen=True)
class HealthReport:
    score: int | None
    grade: str
    components: tuple[HealthComponent, ...]
    excluded: tuple[HealthExclusion, ...]


def compute_health(sample: SystemSample) -> HealthReport:
    components: list[HealthComponent] = []
    excluded: list[HealthExclusion] = []

    if sample.cpu.total_pct is None:
        excluded.append(HealthExclusion("cpu", "CPU", "waiting for the first delta"))
    else:
        components.append(
            HealthComponent(
                key="cpu",
                label="CPU",
                score=_goodness(sample.cpu.total_pct),
                detail=(
                    f"{sample.cpu.total_pct:.1f}% busy across "
                    f"{sample.cpu.logical_count} logical cores"
                ),
            )
        )

    components.append(
        HealthComponent(
            key="memory",
            label="Memory",
            score=_goodness(sample.memory.used_pct),
            detail=(
                f"{human_bytes(sample.memory.used_bytes)} of "
                f"{human_bytes(sample.memory.total_bytes)} in use "
                f"({sample.memory.used_pct:.0f}%)"
            ),
        )
    )

    if not sample.disks:
        excluded.append(HealthExclusion("disk", "Storage", "no fixed volume was reported"))
    else:
        worst = min(sample.disks, key=_free_pct)
        components.append(
            HealthComponent(
                key="disk",
                label="Storage",
                score=_free_pct(worst),
                detail=(
                    f"{worst.mount} has {human_bytes(worst.free_bytes)} free of "
                    f"{human_bytes(worst.total_bytes)}"
                ),
            )
        )

    gpu = sample.gpu.utilization
    if gpu.state is MetricState.AVAILABLE and gpu.value is not None:
        components.append(
            HealthComponent(
                key="gpu",
                label="GPU",
                score=_goodness(gpu.value),
                detail=f"{gpu.value:.1f}% 3D engine utilisation",
            )
        )
    else:
        reason = gpu.detail or str(gpu.state).replace("_", " ")
        excluded.append(HealthExclusion("gpu", "GPU", reason))

    if not components:
        return HealthReport(
            score=None,
            grade="Unknown",
            components=(),
            excluded=tuple(excluded),
        )

    total_weight = sum(_WEIGHTS[component.key] for component in components)
    weighted = sum(
        _WEIGHTS[component.key] * component.score for component in components
    )
    score = round(weighted / total_weight) if total_weight else 0

    return HealthReport(
        score=score,
        grade=_grade(score),
        components=tuple(components),
        excluded=tuple(excluded),
    )


def format_age(seconds: float | None) -> str:
    if seconds is None:
        return "no sample yet"
    if seconds < 2:
        return "just now"
    if seconds < 60:
        return f"{seconds:.0f}s ago"
    minutes = seconds / 60
    if minutes < 60:
        return f"{minutes:.0f}m ago"
    return f"{minutes / 60:.1f}h ago"


def _goodness(pressure_pct: float) -> float:
    """Convert a 0-100 pressure reading into a 0-100 health reading."""
    return round(max(0.0, min(100.0, 100.0 - pressure_pct)), 1)


def _free_pct(disk: object) -> float:
    total = getattr(disk, "total_bytes", 0)
    free = getattr(disk, "free_bytes", 0)
    if not total:
        return 0.0
    return round(max(0.0, min(100.0, free / total * 100.0)), 1)


def _grade(score: int) -> str:
    if score >= 85:
        return "Excellent"
    if score >= 70:
        return "Good"
    if score >= 50:
        return "Fair"
    return "Poor"


__all__ = [
    "HealthComponent",
    "HealthExclusion",
    "HealthReport",
    "compute_health",
    "format_age",
]
