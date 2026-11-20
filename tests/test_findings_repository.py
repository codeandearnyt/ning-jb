"""Scan and finding persistence.

These tests use the real SQLite schema so the columns, foreign keys and cascade
are exercised. The fake repository is checked against the same contract so a
runner test can never pass because the fake is more forgiving than the real one.
"""

from __future__ import annotations

import dataclasses
from datetime import UTC, datetime, timedelta

import pytest

from ningx.app.context import AppContext
from ningx.contracts.finding import Category, Evidence, Finding, Severity
from ningx.storage.repositories.findings import (
    FakeFindingRepository,
    ScanRecord,
    SqliteFindingRepository,
    StoredFinding,
)

START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def finding(
    *,
    rule: str = "memory.pressure",
    subject: str = "physical-memory",
    severity: Severity = Severity.MEDIUM,
    agent: str = "memory-analyst",
) -> Finding:
    return Finding(
        agent_id=agent,
        category=Category.MEMORY,
        rule=rule,
        subject=subject,
        severity=severity,
        title="Memory is 88% in use",
        detail="Measured pressure.",
        evidence=(Evidence("Used percent", "88.0%", 88.0),),
        impact="Slower app switching.",
        confidence=0.9,
        suggested_action=None,
    )


@pytest.fixture
def repo(ctx: AppContext) -> SqliteFindingRepository:
    return SqliteFindingRepository(ctx.db)


def test_start_scan_is_running_and_visible(repo: SqliteFindingRepository) -> None:
    scan_id = repo.start_scan(trigger="manual", started_at=START)
    record = repo.get_scan(scan_id)
    assert record is not None
    assert record.status == "running"
    assert record.trigger == "manual"
    assert record.finished_at is None
    assert record.findings_count == 0


def test_finish_scan_records_status_duration_and_count(repo: SqliteFindingRepository) -> None:
    scan_id = repo.start_scan(trigger="manual", started_at=START)
    finished = START + timedelta(milliseconds=840)
    repo.finish_scan(
        scan_id,
        status="completed",
        findings_count=3,
        duration_ms=840,
        finished_at=finished,
    )
    record = repo.get_scan(scan_id)
    assert record is not None
    assert record.status == "completed"
    assert record.duration_ms == 840
    assert record.findings_count == 3
    assert record.finished_at == finished


def test_round_trip_preserves_every_field(repo: SqliteFindingRepository) -> None:
    original = finding(severity=Severity.HIGH)
    scan_id = repo.start_scan(trigger="manual", started_at=START)
    assert repo.save_findings(scan_id, [original]) == 1

    stored = repo.findings_for(scan_id)
    assert len(stored) == 1
    item = stored[0]
    assert item.agent_id == original.agent_id
    assert item.category is Category.MEMORY
    assert item.severity is Severity.HIGH
    assert item.title == original.title
    assert item.fingerprint == original.fingerprint
    assert item.rule == original.rule
    assert item.subject == original.subject
    assert item.detail == original.detail
    assert item.impact == original.impact
    assert item.confidence == pytest.approx(0.9)
    assert item.evidence == original.evidence


def test_duplicate_fingerprints_within_one_scan_are_collapsed(
    repo: SqliteFindingRepository,
) -> None:
    scan_id = repo.start_scan(trigger="manual", started_at=START)
    same = finding()
    worse = finding(severity=Severity.HIGH)
    assert repo.save_findings(scan_id, [same, worse, same]) == 1
    assert len(repo.findings_for(scan_id)) == 1


def test_the_same_problem_reappears_in_a_later_scan(repo: SqliteFindingRepository) -> None:
    first = repo.start_scan(trigger="manual", started_at=START)
    repo.save_findings(first, [finding(severity=Severity.LOW)])
    repo.finish_scan(first, status="completed", findings_count=1, duration_ms=10)

    second = repo.start_scan(trigger="scheduled", started_at=START + timedelta(minutes=5))
    repo.save_findings(second, [finding(severity=Severity.HIGH)])
    repo.finish_scan(second, status="completed", findings_count=1, duration_ms=12)

    assert repo.finding_count() == 2
    assert (
        repo.findings_for(first)[0].fingerprint == repo.findings_for(second)[0].fingerprint
    )
    assert repo.findings_for(first)[0].severity is Severity.LOW
    assert repo.findings_for(second)[0].severity is Severity.HIGH


def test_latest_and_recent_scans_are_newest_first(repo: SqliteFindingRepository) -> None:
    ids = [
        repo.start_scan(trigger="manual", started_at=START + timedelta(minutes=index))
        for index in range(3)
    ]
    assert repo.latest_scan() is not None
    assert repo.latest_scan().id == ids[-1]  # type: ignore[union-attr]
    assert [record.id for record in repo.recent_scans(limit=2)] == [ids[2], ids[1]]


def test_prune_keeps_the_newest_scans_and_cascades_findings(
    repo: SqliteFindingRepository,
) -> None:
    ids = []
    for index in range(5):
        scan_id = repo.start_scan(trigger="manual", started_at=START + timedelta(minutes=index))
        repo.save_findings(scan_id, [finding(subject=f"subject-{index}")])
        repo.finish_scan(scan_id, status="completed", findings_count=1, duration_ms=1)
        ids.append(scan_id)

    assert repo.prune(keep=2) == 3
    assert repo.finding_count() == 2
    assert [record.id for record in repo.recent_scans()] == [ids[4], ids[3]]
    assert repo.findings_for(ids[0]) == []


def test_prune_with_a_nonsense_keep_value_changes_nothing(repo: SqliteFindingRepository) -> None:
    repo.start_scan(trigger="manual", started_at=START)
    assert repo.prune(keep=0) == 0
    assert repo.latest_scan() is not None


def test_empty_finding_list_writes_nothing(repo: SqliteFindingRepository) -> None:
    scan_id = repo.start_scan(trigger="manual", started_at=START)
    assert repo.save_findings(scan_id, []) == 0
    assert repo.findings_for(scan_id) == []


# ------------------------------------------------------------------------- fakes


def test_fake_repository_matches_the_real_contract() -> None:
    repo = FakeFindingRepository()
    scan_id = repo.start_scan(trigger="manual", started_at=START)
    assert repo.save_findings(scan_id, [finding(), finding(), finding(severity=Severity.HIGH)]) == 1
    repo.finish_scan(scan_id, status="completed", findings_count=1, duration_ms=5)

    record = repo.get_scan(scan_id)
    assert record is not None
    assert record.status == "completed"
    assert record.duration_ms == 5
    stored = repo.findings_for(scan_id)
    assert len(stored) == 1
    assert stored[0].fingerprint == finding().fingerprint
    assert repo.finding_count() == 1


def test_fake_repository_prunes_by_dropping_old_scans() -> None:
    repo = FakeFindingRepository()
    ids = [repo.start_scan(trigger="manual") for _ in range(3)]
    for scan_id in ids:
        repo.save_findings(scan_id, [finding(subject=f"subject-{scan_id}")])

    assert repo.prune(keep=2) == 1
    assert [record.id for record in repo.recent_scans()] == [ids[2], ids[1]]
    assert repo.finding_count() == 2
    assert repo.findings_for(ids[0]) == []
    assert repo.prune(keep=0) == 0


def test_scan_record_and_stored_finding_are_frozen() -> None:
    record = ScanRecord(
        id=1,
        started_at=START,
        finished_at=None,
        trigger="manual",
        status="running",
        duration_ms=None,
        findings_count=0,
        error=None,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        record.status = "completed"  # type: ignore[misc]

    stored = StoredFinding(
        id=1,
        scan_run_id=1,
        agent_id="a",
        category=Category.CPU,
        severity=Severity.INFO,
        title="t",
        fingerprint="f",
        rule="r",
        subject="s",
        detail="d",
        impact="i",
        confidence=1.0,
        suggested_action=None,
        evidence=(),
        created_at=START,
    )
    with pytest.raises(dataclasses.FrozenInstanceError):
        stored.title = "changed"  # type: ignore[misc]
