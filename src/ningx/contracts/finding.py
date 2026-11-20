"""Findings: what an analyst concluded, and why.

A finding is a *statement about a subject*, not a snapshot of numbers. Its
fingerprint is derived from the analyst, the rule and the subject — never from
the measured value — so the same problem keeps the same identity across scans
while its severity can rise or fall. That is what makes "unchanged findings are
not resent" possible later.

Nothing in this module can act. A finding may name the action type that would
address it, but it carries no target payload and no permission to execute.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from hashlib import sha256
from typing import Any


class Severity(StrEnum):
    INFO = "info"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


SEVERITY_ORDER: dict[Severity, int] = {
    Severity.HIGH: 0,
    Severity.MEDIUM: 1,
    Severity.LOW: 2,
    Severity.INFO: 3,
}


class Category(StrEnum):
    MEMORY = "memory"
    CPU = "cpu"
    GPU = "gpu"
    PROCESS = "process"
    STARTUP = "startup"
    JUNK = "junk"
    STORAGE = "storage"
    NETWORK = "network"


@dataclass(frozen=True)
class Evidence:
    """One measured fact behind a finding, in the form the UI shows it."""

    label: str
    value: str
    numeric: float | None = None


@dataclass(frozen=True)
class Finding:
    agent_id: str
    category: Category
    rule: str
    subject: str
    severity: Severity
    title: str
    detail: str
    evidence: tuple[Evidence, ...] = ()
    impact: str = ""
    confidence: float = 1.0
    suggested_action: str | None = None
    created_at: datetime | None = None

    @property
    def fingerprint(self) -> str:
        return fingerprint_of(self.agent_id, self.rule, self.subject)

    def to_payload(self) -> dict[str, Any]:
        """The JSON document stored in ``findings.evidence_json``."""
        return {
            "rule": self.rule,
            "subject": self.subject,
            "detail": self.detail,
            "impact": self.impact,
            "confidence": round(self.confidence, 3),
            "suggested_action": self.suggested_action,
            "evidence": [
                {"label": item.label, "value": item.value, "numeric": item.numeric}
                for item in self.evidence
            ],
        }


@dataclass(frozen=True)
class ScanOutcome:
    scan_id: int
    started_at: datetime
    finished_at: datetime
    findings: tuple[Finding, ...]
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def duration_ms(self) -> int:
        return max(0, int((self.finished_at - self.started_at).total_seconds() * 1000))

    def sorted_findings(self) -> tuple[Finding, ...]:
        return tuple(
            sorted(
                self.findings,
                key=lambda item: (
                    SEVERITY_ORDER[item.severity],
                    -item.confidence,
                    item.category.value,
                    item.title,
                ),
            )
        )


def fingerprint_of(agent_id: str, rule: str, subject: str) -> str:
    """Stable identity for a finding.

    Deliberately excludes measured values, timestamps and severity. If the
    subject is the same and the rule is the same, it is the same problem — even
    if it got worse.
    """
    digest = sha256(f"{agent_id}|{rule}|{subject}".encode())
    return digest.hexdigest()[:32]


__all__ = [
    "SEVERITY_ORDER",
    "Category",
    "Evidence",
    "Finding",
    "ScanOutcome",
    "Severity",
    "fingerprint_of",
]
