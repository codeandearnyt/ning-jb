"""Action and policy-decision repository.

Every evaluated action is persisted with its decision, so a recommendation the
user saw is always reconstructable later — including what the policy engine said
about it and why.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from ningx.contracts.action import Action
from ningx.contracts.enums import ActionState, DecisionOutcome
from ningx.contracts.time import utcnow
from ningx.core.policy_engine import PolicyDecision
from ningx.storage.db import Database


@dataclass(frozen=True)
class ActionRecord:
    action_id: str
    action_type: str
    target_kind: str
    risk: str
    outcome: str
    state: str
    created_at: str


_STATE_BY_OUTCOME = {
    DecisionOutcome.ALLOW: ActionState.PROPOSED,
    DecisionOutcome.REQUIRE_APPROVAL: ActionState.AWAITING_APPROVAL,
    DecisionOutcome.DENY: ActionState.POLICY_BLOCKED,
}


class SqliteActionRepository:
    def __init__(self, db: Database, clock: Callable[[], datetime] = utcnow) -> None:
        self._db = db
        self._clock = clock

    def record(self, action: Action, decision: PolicyDecision) -> ActionRecord:
        state = _STATE_BY_OUTCOME[decision.outcome]
        decision_json = {
            "outcome": str(decision.outcome),
            "risk": decision.risk.name,
            "blocked_at": None if decision.blocked_at is None else str(decision.blocked_at),
            "reasons": [
                {"code": reason.code, "stage": str(reason.stage), "detail": reason.detail}
                for reason in decision.reasons
            ],
        }
        self._db.connect().execute(
            """
            INSERT INTO actions (
                id, action_type, target_kind, target_json, params_json, risk,
                reversible, rollback_plan_json, payload_hash, state, decision_json,
                created_at, expires_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(action.action_id),
                action.action_type,
                action.target.kind,
                action.target.model_dump_json(),
                json.dumps(action.parameters, sort_keys=True, default=str),
                decision.risk.name,
                int(decision.full_access_eligible and decision.risk.name in {"LOW", "MEDIUM"}),
                None,
                None,
                str(state),
                json.dumps(decision_json, sort_keys=True),
                self._clock().isoformat(),
                None,
            ),
        )
        return ActionRecord(
            action_id=str(action.action_id),
            action_type=action.action_type,
            target_kind=action.target.kind,
            risk=decision.risk.name,
            outcome=str(decision.outcome),
            state=str(state),
            created_at=self._clock().isoformat(),
        )

    def recent(self, limit: int = 50) -> list[ActionRecord]:
        rows = self._db.connect().execute(
            """
            SELECT id, action_type, target_kind, risk, state, decision_json, created_at
            FROM actions ORDER BY created_at DESC LIMIT ?
            """,
            (max(1, min(limit, 500)),),
        ).fetchall()
        records: list[ActionRecord] = []
        for row in rows:
            decision = _json_object(str(row["decision_json"] or "{}"))
            records.append(
                ActionRecord(
                    action_id=str(row["id"]),
                    action_type=str(row["action_type"]),
                    target_kind=str(row["target_kind"]),
                    risk=str(row["risk"]),
                    outcome=str(decision.get("outcome", "unknown")),
                    state=str(row["state"]),
                    created_at=str(row["created_at"]),
                )
            )
        return records

    def count_by_outcome(self) -> dict[str, int]:
        rows = self._db.connect().execute(
            "SELECT state, COUNT(*) AS n FROM actions GROUP BY state"
        ).fetchall()
        return {str(row["state"]): int(row["n"]) for row in rows}

    def decision_for(self, action_id: str) -> dict[str, Any] | None:
        row = self._db.connect().execute(
            "SELECT decision_json FROM actions WHERE id = ?", (action_id,)
        ).fetchone()
        if row is None:
            return None
        return _json_object(str(row["decision_json"] or "{}"))


def _json_object(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


__all__ = ["ActionRecord", "SqliteActionRepository"]
