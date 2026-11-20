"""Presentation model for the Optimization Center.

Qt-free on purpose. The screen renders what these functions return; the rules
that decide what a user sees live here so they can be tested without a window.

The one thing this module refuses to do is rank findings by anything other than
the deterministic severity the analyst assigned. There is no "AI score".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from ningx.contracts.finding import Category, Finding, ScanOutcome, Severity

# Display order: the most actionable first.
_SEVERITY_ORDER = (Severity.HIGH, Severity.MEDIUM, Severity.LOW, Severity.INFO)

SEVERITY_LABEL: dict[Severity, str] = {
    Severity.HIGH: "High",
    Severity.MEDIUM: "Medium",
    Severity.LOW: "Low",
    Severity.INFO: "Info",
}

CATEGORY_LABEL: dict[Category, str] = {
    Category.MEMORY: "Memory",
    Category.CPU: "CPU",
    Category.GPU: "GPU",
    Category.PROCESS: "Processes",
    Category.STARTUP: "Startup",
    Category.JUNK: "Temporary files",
    Category.STORAGE: "Storage",
    Category.NETWORK: "Network",
}


@dataclass(frozen=True)
class EvidenceRow:
    label: str
    value: str


@dataclass(frozen=True)
class FindingView:
    fingerprint: str
    title: str
    detail: str
    impact: str
    category: Category
    category_label: str
    severity: Severity
    severity_label: str
    confidence: float
    confidence_label: str
    evidence: tuple[EvidenceRow, ...]
    suggested_action: str | None
    agent_id: str

    @property
    def action_label(self) -> str:
        if not self.suggested_action:
            return "No action proposed"
        return self.suggested_action.replace("_", " ")


@dataclass(frozen=True)
class CategoryGroup:
    category: Category
    label: str
    findings: tuple[FindingView, ...]


@dataclass(frozen=True)
class ScanSummary:
    scan_id: int | None
    status: str
    finished_at: datetime | None
    duration_ms: int | None
    counts: tuple[tuple[Severity, int], ...]
    total: int
    errors: tuple[str, ...]

    @property
    def headline(self) -> str:
        if self.scan_id is None:
            return "No scan has run yet"
        if self.status != "completed":
            return f"Scan #{self.scan_id} {self.status}"
        if self.total == 0:
            return f"Scan #{self.scan_id} found nothing to report"
        return f"Scan #{self.scan_id} reported {self.total} findings"

    def count_of(self, severity: Severity) -> int:
        return dict(self.counts).get(severity, 0)


def build_view(finding: Finding) -> FindingView:
    return FindingView(
        fingerprint=finding.fingerprint,
        title=finding.title,
        detail=finding.detail,
        impact=finding.impact,
        category=finding.category,
        category_label=CATEGORY_LABEL[finding.category],
        severity=finding.severity,
        severity_label=SEVERITY_LABEL[finding.severity],
        confidence=finding.confidence,
        confidence_label=_confidence_label(finding.confidence),
        evidence=tuple(
            EvidenceRow(label=item.label, value=item.value) for item in finding.evidence
        ),
        suggested_action=finding.suggested_action,
        agent_id=finding.agent_id,
    )


def build_views(findings: tuple[Finding, ...] | list[Finding]) -> tuple[FindingView, ...]:
    """Sort by severity, then confidence, then category, then title.

    This is the same order the outcome uses, so the screen and any export agree.
    """
    ordered = sorted(
        findings,
        key=lambda item: (
            _SEVERITY_ORDER.index(item.severity),
            -item.confidence,
            item.category.value,
            item.title,
        ),
    )
    return tuple(build_view(finding) for finding in ordered)


def group_by_category(views: tuple[FindingView, ...]) -> tuple[CategoryGroup, ...]:
    """Group in severity order, keeping the strongest finding's group first."""
    groups: dict[Category, list[FindingView]] = {}
    for view in views:
        groups.setdefault(view.category, []).append(view)
    order = list(groups)
    order.sort(key=lambda category: CATEGORY_LABEL[category])
    return tuple(
        CategoryGroup(
            category=category,
            label=CATEGORY_LABEL[category],
            findings=tuple(groups[category]),
        )
        for category in order
    )


def summarise(outcome: ScanOutcome | None) -> ScanSummary:
    if outcome is None:
        return ScanSummary(
            scan_id=None,
            status="none",
            finished_at=None,
            duration_ms=None,
            counts=tuple((severity, 0) for severity in _SEVERITY_ORDER),
            total=0,
            errors=(),
        )
    counts = tuple(
        (severity, sum(1 for finding in outcome.findings if finding.severity is severity))
        for severity in _SEVERITY_ORDER
    )
    return ScanSummary(
        scan_id=outcome.scan_id,
        status="completed" if not outcome.errors else "completed with warnings",
        finished_at=outcome.finished_at,
        duration_ms=outcome.duration_ms,
        counts=counts,
        total=len(outcome.findings),
        errors=outcome.errors,
    )


def stale_sample_message(
    captured_at: datetime | None,
    *,
    now: datetime | None = None,
    max_age_s: float = 120.0,
) -> str | None:
    """Refuse to describe a stale sample as the current measurement.

    Returns ``None`` when the sample is fresh enough to scan, otherwise a
    sentence a user can act on. A missing timestamp is treated as unknown
    rather than stale: the caller already refuses to scan without a sample.
    """
    if captured_at is None:
        return None
    current = now or datetime.now(UTC)
    moment = (
        captured_at if captured_at.tzinfo is not None else captured_at.replace(tzinfo=UTC)
    )
    age = max(0.0, (current - moment).total_seconds())
    if age <= max_age_s:
        return None
    return (
        f"The newest measurement is {age:.0f} seconds old, so it no longer "
        "describes the machine. Resume sampling in Live Monitor, then scan."
    )


def format_scan_age(finished_at: datetime | None, *, now: datetime | None = None) -> str:
    if finished_at is None:
        return "never"
    current = now or datetime.now(UTC)
    moment = finished_at if finished_at.tzinfo is not None else finished_at.replace(tzinfo=UTC)
    seconds = max(0.0, (current - moment).total_seconds())
    if seconds < 5:
        return "just now"
    if seconds < 60:
        return f"{int(seconds)}s ago"
    if seconds < 3600:
        return f"{int(seconds // 60)}m ago"
    if seconds < 86_400:
        return f"{seconds / 3600:.1f}h ago"
    return f"{seconds / 86_400:.1f}d ago"


def _confidence_label(confidence: float) -> str:
    if confidence >= 0.9:
        return "high confidence"
    if confidence >= 0.7:
        return "moderate confidence"
    return "low confidence"


__all__ = [
    "CATEGORY_LABEL",
    "SEVERITY_LABEL",
    "CategoryGroup",
    "EvidenceRow",
    "FindingView",
    "ScanSummary",
    "build_view",
    "build_views",
    "format_scan_age",
    "group_by_category",
    "stale_sample_message",
    "summarise",
]
