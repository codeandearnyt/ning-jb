"""Optimization Center presentation rules.

Pure functions only: ordering, grouping, counts and the honest empty state. The
screen is a renderer; anything that could be wrong about a finding is decided
here where it can be tested.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ningx.contracts.finding import Category, Evidence, Finding, ScanOutcome, Severity
from ningx.ui.viewmodels.optimization import (
    build_view,
    build_views,
    format_scan_age,
    group_by_category,
    stale_sample_message,
    summarise,
)

START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def finding(
    *,
    severity: Severity = Severity.MEDIUM,
    category: Category = Category.MEMORY,
    title: str = "Memory is 90% in use",
    rule: str = "memory.pressure",
    subject: str = "physical-memory",
    confidence: float = 0.9,
    agent: str = "memory-analyst",
    action: str | None = None,
) -> Finding:
    return Finding(
        agent_id=agent,
        category=category,
        rule=rule,
        subject=subject,
        severity=severity,
        title=title,
        detail="Measured pressure.",
        evidence=(Evidence("Used percent", "90.0%", 90.0),),
        impact="Slower app switching.",
        confidence=confidence,
        suggested_action=action,
    )


def test_a_finding_carries_its_evidence_and_confidence() -> None:
    view = build_view(finding(confidence=0.95))
    assert view.severity_label == "Medium"
    assert view.category_label == "Memory"
    assert view.confidence_label == "high confidence"
    assert view.evidence[0].label == "Used percent"
    assert view.evidence[0].value == "90.0%"


def test_confidence_labels_use_documented_bands() -> None:
    assert build_view(finding(confidence=0.9)).confidence_label == "high confidence"
    assert build_view(finding(confidence=0.75)).confidence_label == "moderate confidence"
    assert build_view(finding(confidence=0.5)).confidence_label == "low confidence"


def test_ordering_is_severity_then_confidence_then_category_then_title() -> None:
    findings = [
        finding(severity=Severity.INFO, title="b", category=Category.CPU, agent="cpu"),
        finding(severity=Severity.HIGH, title="c", category=Category.STORAGE, agent="disk"),
        finding(severity=Severity.HIGH, title="a", category=Category.MEMORY, agent="mem"),
        finding(severity=Severity.MEDIUM, title="d", category=Category.NETWORK, agent="net"),
    ]
    ordered = [view.title for view in build_views(findings)]
    assert ordered == ["a", "c", "d", "b"]


def test_higher_confidence_wins_within_the_same_severity() -> None:
    findings = [
        finding(severity=Severity.MEDIUM, title="sure", confidence=0.95),
        finding(
            severity=Severity.MEDIUM,
            title="unsure",
            confidence=0.5,
            rule="other",
            subject="other",
        ),
    ]
    assert [view.title for view in build_views(findings)] == ["sure", "unsure"]


def test_grouping_puts_one_header_per_category() -> None:
    findings = [
        finding(category=Category.MEMORY, subject="a"),
        finding(category=Category.MEMORY, subject="b", rule="other"),
        finding(category=Category.CPU, agent="cpu", rule="cpu.high", subject="c"),
    ]
    groups = group_by_category(build_views(findings))
    assert [group.label for group in groups] == ["CPU", "Memory"]
    assert [len(group.findings) for group in groups] == [1, 2]


def test_a_finding_without_an_action_says_so() -> None:
    assert build_view(finding()).action_label == "No action proposed"
    assert build_view(finding(action="startup_disable")).action_label == "startup disable"


def test_summary_counts_every_severity_including_zeroes() -> None:
    outcome = ScanOutcome(
        scan_id=7,
        started_at=START,
        finished_at=START + timedelta(milliseconds=900),
        findings=(
            finding(severity=Severity.HIGH),
            finding(severity=Severity.MEDIUM, rule="r2", subject="s2"),
            finding(severity=Severity.MEDIUM, rule="r3", subject="s3"),
        ),
    )
    summary = summarise(outcome)
    assert summary.scan_id == 7
    assert summary.total == 3
    assert summary.duration_ms == 900
    assert summary.count_of(Severity.HIGH) == 1
    assert summary.count_of(Severity.MEDIUM) == 2
    assert summary.count_of(Severity.LOW) == 0
    assert summary.count_of(Severity.INFO) == 0
    assert summary.headline == "Scan #7 reported 3 findings"


def test_a_clean_scan_says_it_found_nothing_rather_than_showing_a_zero() -> None:
    summary = summarise(
        ScanOutcome(scan_id=4, started_at=START, finished_at=START, findings=())
    )
    assert summary.headline == "Scan #4 found nothing to report"
    assert summary.total == 0


def test_collector_errors_change_the_headline_honestly() -> None:
    summary = summarise(
        ScanOutcome(
            scan_id=9,
            started_at=START,
            finished_at=START,
            findings=(),
            errors=("junk scanner failed: OSError",),
        )
    )
    assert summary.status == "completed with warnings"
    assert summary.errors == ("junk scanner failed: OSError",)


def test_no_scan_yet_is_its_own_state_not_a_zero_score() -> None:
    summary = summarise(None)
    assert summary.scan_id is None
    assert summary.headline == "No scan has run yet"
    assert summary.total == 0
    assert summary.finished_at is None


def test_scan_age_reads_naturally() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert format_scan_age(None) == "never"
    assert format_scan_age(now, now=now) == "just now"
    assert format_scan_age(now - timedelta(seconds=42), now=now) == "42s ago"
    assert format_scan_age(now - timedelta(minutes=9), now=now) == "9m ago"
    assert format_scan_age(now - timedelta(hours=3), now=now) == "3.0h ago"
    assert format_scan_age(now - timedelta(days=2), now=now) == "2.0d ago"


def test_a_naive_stored_timestamp_is_treated_as_utc() -> None:
    naive = datetime(2026, 1, 1, 11, 59, 0)
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert format_scan_age(naive, now=now) == "1m ago"


def test_a_fresh_sample_may_be_scanned() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert stale_sample_message(now - timedelta(seconds=3), now=now) is None
    assert stale_sample_message(now, now=now) is None
    assert stale_sample_message(None, now=now) is None


def test_a_stale_sample_is_refused_with_an_actionable_reason() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    message = stale_sample_message(now - timedelta(minutes=30), now=now)
    assert message is not None
    assert "1800 seconds old" in message
    assert "Resume sampling" in message


def test_staleness_uses_the_documented_boundary() -> None:
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert stale_sample_message(now - timedelta(seconds=120), now=now) is None
    assert stale_sample_message(now - timedelta(seconds=121), now=now) is not None


def test_a_naive_sample_timestamp_is_compared_as_utc() -> None:
    naive = datetime(2026, 1, 1, 11, 55, 0)
    now = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    message = stale_sample_message(naive, now=now)
    assert message is not None and "300 seconds old" in message
