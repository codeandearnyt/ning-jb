"""Dashboard health arithmetic.

These are pure functions: no Qt, no machine access. The score must be
reproducible by hand from the documented weights, and a metric the hardware did
not report must never be counted as healthy.
"""

from __future__ import annotations

import pytest

from ningx.ui.viewmodels.dashboard import (
    HealthExclusion,
    compute_health,
    format_age,
)
from tests.telemetry_fakes import make_sample


def test_score_is_the_documented_weighted_pressure() -> None:
    # cpu 20 -> 80, memory 50 -> 50, disk 50 % free -> 50, gpu 10 -> 90
    # 0.30*80 + 0.30*50 + 0.25*50 + 0.15*90 = 65
    report = compute_health(
        make_sample(cpu_pct=20.0, memory_pct=50.0, gpu_pct=10.0, disk_free_pct=50.0)
    )
    assert report.score == 65
    assert report.grade == "Fair"
    assert [component.key for component in report.components] == [
        "cpu",
        "memory",
        "disk",
        "gpu",
    ]
    assert report.excluded == ()


def test_missing_gpu_renormalises_the_remaining_weights() -> None:
    report = compute_health(
        make_sample(cpu_pct=20.0, memory_pct=50.0, gpu_state="unsupported", disk_free_pct=50.0)
    )
    # Same components minus gpu: (0.30*80 + 0.30*50 + 0.25*50) / 0.85 = 60.6
    assert report.score == 61
    assert [component.key for component in report.components] == ["cpu", "memory", "disk"]
    assert len(report.excluded) == 1
    assert report.excluded[0].key == "gpu"
    assert "vendor" in report.excluded[0].reason


def test_warming_cpu_is_excluded_rather_than_scored_as_zero() -> None:
    sample = make_sample(memory_pct=50.0, gpu_pct=10.0, disk_free_pct=50.0)
    warming = type(sample)(
        captured_at=sample.captured_at,
        monotonic=sample.monotonic,
        cpu=type(sample.cpu)(
            total_pct=None,
            per_core_pct=(),
            frequency_mhz=sample.cpu.frequency_mhz,
            temperature_c=sample.cpu.temperature_c,
            logical_count=sample.cpu.logical_count,
            physical_count=sample.cpu.physical_count,
        ),
        memory=sample.memory,
        gpu=sample.gpu,
        disks=sample.disks,
        network=sample.network,
        processes=sample.processes,
        process_count=sample.process_count,
        truncated=False,
    )

    report = compute_health(warming)
    assert "cpu" not in {component.key for component in report.components}
    assert any(
        entry.key == "cpu" and "first delta" in entry.reason for entry in report.excluded
    )
    # 0.30*50 + 0.25*50 + 0.15*90 = 41 over 0.70 = 58.6
    assert report.score == 59


def test_no_fixed_volume_excludes_storage() -> None:
    report = compute_health(make_sample(disks=()))
    assert any(
        isinstance(entry, HealthExclusion) and entry.key == "disk"
        for entry in report.excluded
    )
    assert "disk" not in {component.key for component in report.components}


def test_memory_alone_is_enough_for_a_score() -> None:
    sample = make_sample(gpu_state="unsupported", disks=())
    warming = type(sample)(
        captured_at=sample.captured_at,
        monotonic=sample.monotonic,
        cpu=type(sample.cpu)(
            total_pct=None,
            per_core_pct=(),
            frequency_mhz=sample.cpu.frequency_mhz,
            temperature_c=sample.cpu.temperature_c,
            logical_count=sample.cpu.logical_count,
            physical_count=sample.cpu.physical_count,
        ),
        memory=sample.memory,
        gpu=sample.gpu,
        disks=(),
        network=sample.network,
        processes=sample.processes,
        process_count=sample.process_count,
        truncated=False,
    )
    report = compute_health(warming)
    assert report.score is not None
    assert [component.key for component in report.components] == ["memory"]


def test_grades_follow_the_documented_bands() -> None:
    assert compute_health(make_sample(cpu_pct=0.0, memory_pct=0.0, gpu_pct=0.0,
                                      disk_free_pct=100.0)).grade == "Excellent"
    assert compute_health(make_sample(cpu_pct=100.0, memory_pct=100.0, gpu_pct=100.0,
                                      disk_free_pct=0.0)).grade == "Poor"


@pytest.mark.parametrize(
    ("seconds", "expected"),
    [
        (None, "no sample yet"),
        (0.4, "just now"),
        (12.0, "12s ago"),
        (90.0, "2m ago"),
        (7200.0, "2.0h ago"),
    ],
)
def test_format_age(seconds: float | None, expected: str) -> None:
    assert format_age(seconds) == expected
