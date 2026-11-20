"""Audit log repository.

Detail payloads are redacted before they are written, so a credential that leaks
into a detail dict is still not persisted. The ``redacted`` column records that
redaction was applied, so an auditor can tell the difference between "no secret
in this row" and "secret removed from this row".
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ningx.contracts.time import utcnow
from ningx.core.ports import AuditEvent
from ningx.observability.redaction import redact_mapping
from ningx.storage.db import Database


class SqliteAuditSink:
    def __init__(self, db: Database, clock: Callable[[], datetime] = utcnow) -> None:
        self._db = db
        self._clock = clock

    def append(self, event: AuditEvent) -> None:
        detail: dict[str, Any] = redact_mapping(dict(event.detail))
        self._db.connect().execute(
            """
            INSERT INTO audit_events (ts, actor, event_type, subject_id, detail_json, redacted)
            VALUES (?, ?, ?, ?, ?, 1)
            """,
            (
                self._clock().isoformat(),
                event.actor,
                event.event_type,
                event.subject_id,
                json.dumps(detail, sort_keys=True, ensure_ascii=True, default=str),
            ),
        )

    def recent(self, limit: int = 100) -> list[AuditEvent]:
        rows = self._db.connect().execute(
            """
            SELECT actor, event_type, subject_id, detail_json
            FROM audit_events ORDER BY id DESC LIMIT ?
            """,
            (max(1, min(limit, 1000)),),
        ).fetchall()
        return [
            AuditEvent(
                actor=str(row["actor"]),
                event_type=str(row["event_type"]),
                subject_id=None if row["subject_id"] is None else str(row["subject_id"]),
                detail=_decode(str(row["detail_json"])),
            )
            for row in rows
        ]

    def search(
        self,
        *,
        actor: str | None = None,
        event_type: str | None = None,
        limit: int = 100,
    ) -> list[AuditEvent]:
        clauses: list[str] = []
        params: list[Any] = []
        if actor:
            clauses.append("actor = ?")
            params.append(actor)
        if event_type:
            clauses.append("event_type = ?")
            params.append(event_type)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        params.append(max(1, min(limit, 1000)))
        rows = self._db.connect().execute(
            f"""
            SELECT actor, event_type, subject_id, detail_json
            FROM audit_events {where} ORDER BY id DESC LIMIT ?
            """,  # noqa: S608 - clause fragments are static, values are parameterized
            tuple(params),
        ).fetchall()
        return [
            AuditEvent(
                actor=str(row["actor"]),
                event_type=str(row["event_type"]),
                subject_id=None if row["subject_id"] is None else str(row["subject_id"]),
                detail=_decode(str(row["detail_json"])),
            )
            for row in rows
        ]


def _decode(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


__all__ = ["SqliteAuditSink"]
