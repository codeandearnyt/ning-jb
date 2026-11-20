"""Persistence for scans and their findings.

A scan is a row, its findings are rows, and a finding is identified by the
fingerprint stored alongside it. Within one scan a fingerprint appears once;
across scans it repeats deliberately, which is what lets a later change-detection
step say "this problem is unchanged" instead of guessing from titles.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from ningx.contracts.finding import Category, Evidence, Finding, Severity
from ningx.storage.db import Database


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class ScanRecord:
    id: int
    started_at: datetime
    finished_at: datetime | None
    trigger: str
    status: str
    duration_ms: int | None
    findings_count: int
    error: str | None


@dataclass(frozen=True)
class StoredFinding:
    id: int
    scan_run_id: int
    agent_id: str
    category: Category
    severity: Severity
    title: str
    fingerprint: str
    rule: str
    subject: str
    detail: str
    impact: str
    confidence: float
    suggested_action: str | None
    evidence: tuple[Evidence, ...]
    created_at: datetime


class SqliteFindingRepository:
    def __init__(self, db: Database, *, clock: Callable[[], datetime] = _utcnow) -> None:
        self._db = db
        self._clock = clock

    # -------------------------------------------------------------------- writes

    def start_scan(self, *, trigger: str, started_at: datetime | None = None) -> int:
        started = started_at or self._clock()
        with self._db.transaction() as tx:
            cursor = tx.execute(
                """
                INSERT INTO scan_runs (started_at, finished_at, trigger, status, findings_count)
                VALUES (?, NULL, ?, 'running', 0)
                """,
                (started.isoformat(), trigger),
            )
            if cursor.lastrowid is None:
                raise RuntimeError("scan insert did not return an id")
            return int(cursor.lastrowid)

    def save_findings(self, scan_id: int, findings: Iterable[Finding]) -> int:
        rows = []
        seen: set[str] = set()
        created = self._clock().isoformat()
        for finding in findings:
            fingerprint = finding.fingerprint
            if fingerprint in seen:
                continue
            seen.add(fingerprint)
            rows.append(
                (
                    scan_id,
                    finding.agent_id,
                    finding.category.value,
                    finding.severity.value,
                    finding.title,
                    json.dumps(finding.to_payload(), separators=(",", ":"), sort_keys=True),
                    fingerprint,
                    created,
                )
            )
        if not rows:
            return 0
        with self._db.transaction() as tx:
            tx.executemany(
                """
                INSERT INTO findings
                    (scan_run_id, agent_id, category, severity, title,
                     evidence_json, fingerprint, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def finish_scan(
        self,
        scan_id: int,
        *,
        status: str,
        findings_count: int,
        duration_ms: int,
        finished_at: datetime | None = None,
        error: str | None = None,
    ) -> None:
        finished = finished_at or self._clock()
        with self._db.transaction() as tx:
            tx.execute(
                """
                UPDATE scan_runs
                SET finished_at = ?, status = ?, findings_count = ?, duration_ms = ?, error = ?
                WHERE id = ?
                """,
                (finished.isoformat(), status, findings_count, duration_ms, error, scan_id),
            )

    def prune(self, *, keep: int = 50) -> int:
        """Keep the newest ``keep`` scans; older ones cascade to their findings."""
        if keep < 1:
            return 0
        row = self._db.connect().execute(
            "SELECT id FROM scan_runs ORDER BY id DESC LIMIT 1 OFFSET ?", (keep,)
        ).fetchone()
        if row is None:
            return 0
        with self._db.transaction() as tx:
            cursor = tx.execute("DELETE FROM scan_runs WHERE id <= ?", (int(row["id"]),))
        return int(cursor.rowcount or 0)

    # --------------------------------------------------------------------- reads

    def latest_scan(self) -> ScanRecord | None:
        row = self._db.connect().execute(
            "SELECT * FROM scan_runs ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return _scan(row) if row is not None else None

    def get_scan(self, scan_id: int) -> ScanRecord | None:
        row = self._db.connect().execute(
            "SELECT * FROM scan_runs WHERE id = ?", (scan_id,)
        ).fetchone()
        return _scan(row) if row is not None else None

    def recent_scans(self, limit: int = 20) -> list[ScanRecord]:
        rows = self._db.connect().execute(
            "SELECT * FROM scan_runs ORDER BY id DESC LIMIT ?", (max(1, limit),)
        ).fetchall()
        return [record for record in (_scan(row) for row in rows) if record is not None]

    def findings_for(self, scan_id: int) -> list[StoredFinding]:
        rows = self._db.connect().execute(
            "SELECT * FROM findings WHERE scan_run_id = ? ORDER BY id", (scan_id,)
        ).fetchall()
        return [finding for finding in (_stored(row) for row in rows) if finding is not None]

    def finding_count(self) -> int:
        row = self._db.connect().execute("SELECT COUNT(*) AS n FROM findings").fetchone()
        return int(row["n"]) if row else 0


class FakeFindingRepository:
    """In-memory repository for runner tests."""

    def __init__(self) -> None:
        self.scans: list[ScanRecord] = []
        self.findings: dict[int, list[StoredFinding]] = {}
        self._next = 1

    def start_scan(self, *, trigger: str, started_at: datetime | None = None) -> int:
        scan_id = self._next
        self._next += 1
        self.scans.append(
            ScanRecord(
                id=scan_id,
                started_at=started_at or _utcnow(),
                finished_at=None,
                trigger=trigger,
                status="running",
                duration_ms=None,
                findings_count=0,
                error=None,
            )
        )
        self.findings[scan_id] = []
        return scan_id

    def save_findings(self, scan_id: int, findings: Iterable[Finding]) -> int:
        seen = {finding.fingerprint for finding in self.findings[scan_id]}
        saved = 0
        for finding in findings:
            if finding.fingerprint in seen:
                continue
            seen.add(finding.fingerprint)
            self.findings[scan_id].append(_stored_from_finding(scan_id, finding))
            saved += 1
        return saved

    def finish_scan(
        self,
        scan_id: int,
        *,
        status: str,
        findings_count: int,
        duration_ms: int,
        finished_at: datetime | None = None,
        error: str | None = None,
    ) -> None:
        for index, record in enumerate(self.scans):
            if record.id != scan_id:
                continue
            self.scans[index] = ScanRecord(
                id=record.id,
                started_at=record.started_at,
                finished_at=finished_at or _utcnow(),
                trigger=record.trigger,
                status=status,
                duration_ms=duration_ms,
                findings_count=findings_count,
                error=error,
            )

    def latest_scan(self) -> ScanRecord | None:
        return self.scans[-1] if self.scans else None

    def get_scan(self, scan_id: int) -> ScanRecord | None:
        return next((record for record in self.scans if record.id == scan_id), None)

    def recent_scans(self, limit: int = 20) -> list[ScanRecord]:
        return list(reversed(self.scans))[:limit]

    def findings_for(self, scan_id: int) -> list[StoredFinding]:
        return list(self.findings.get(scan_id, []))

    def finding_count(self) -> int:
        return sum(len(items) for items in self.findings.values())

    def prune(self, *, keep: int = 50) -> int:
        if keep < 1 or len(self.scans) <= keep:
            return 0
        drop = self.scans[:-keep]
        for record in drop:
            self.findings.pop(record.id, None)
        self.scans = self.scans[-keep:]
        return len(drop)


# --------------------------------------------------------------------- mapping


def _scan(row: Any) -> ScanRecord | None:
    try:
        started = datetime.fromisoformat(str(row["started_at"]))
    except (TypeError, ValueError):
        return None
    finished_raw = row["finished_at"]
    finished = None
    if finished_raw:
        try:
            finished = datetime.fromisoformat(str(finished_raw))
        except ValueError:
            finished = None
    return ScanRecord(
        id=int(row["id"]),
        started_at=_as_utc(started),
        finished_at=_as_utc(finished) if finished is not None else None,
        trigger=str(row["trigger"]),
        status=str(row["status"]),
        duration_ms=int(row["duration_ms"]) if row["duration_ms"] is not None else None,
        findings_count=int(row["findings_count"] or 0),
        error=str(row["error"]) if row["error"] else None,
    )


def _stored(row: Any) -> StoredFinding | None:
    try:
        created = datetime.fromisoformat(str(row["created_at"]))
    except (TypeError, ValueError):
        return None
    try:
        category = Category(str(row["category"]))
    except ValueError:
        category = Category.PROCESS
    try:
        severity = Severity(str(row["severity"]))
    except ValueError:
        severity = Severity.INFO
    payload = _load(str(row["evidence_json"] or "{}"))
    return StoredFinding(
        id=int(row["id"]),
        scan_run_id=int(row["scan_run_id"]) if row["scan_run_id"] is not None else 0,
        agent_id=str(row["agent_id"]),
        category=category,
        severity=severity,
        title=str(row["title"]),
        fingerprint=str(row["fingerprint"]),
        rule=str(payload.get("rule") or ""),
        subject=str(payload.get("subject") or ""),
        detail=str(payload.get("detail") or ""),
        impact=str(payload.get("impact") or ""),
        confidence=float(payload.get("confidence") or 0.0),
        suggested_action=_optional_str(payload.get("suggested_action")),
        evidence=_evidence(payload.get("evidence")),
        created_at=_as_utc(created),
    )


def _stored_from_finding(scan_id: int, finding: Finding) -> StoredFinding:
    return StoredFinding(
        id=0,
        scan_run_id=scan_id,
        agent_id=finding.agent_id,
        category=finding.category,
        severity=finding.severity,
        title=finding.title,
        fingerprint=finding.fingerprint,
        rule=finding.rule,
        subject=finding.subject,
        detail=finding.detail,
        impact=finding.impact,
        confidence=finding.confidence,
        suggested_action=finding.suggested_action,
        evidence=finding.evidence,
        created_at=finding.created_at or _utcnow(),
    )


def _evidence(raw: object) -> tuple[Evidence, ...]:
    if not isinstance(raw, list):
        return ()
    items: list[Evidence] = []
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        numeric = entry.get("numeric")
        items.append(
            Evidence(
                label=str(entry.get("label") or ""),
                value=str(entry.get("value") or ""),
                numeric=float(numeric) if isinstance(numeric, (int, float)) else None,
            )
        )
    return tuple(items)


def _load(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _optional_str(value: object) -> str | None:
    return str(value) if value else None


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


__all__ = [
    "FakeFindingRepository",
    "ScanRecord",
    "SqliteFindingRepository",
    "StoredFinding",
]
