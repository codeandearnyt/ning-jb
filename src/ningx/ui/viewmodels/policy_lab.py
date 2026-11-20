"""Policy Lab viewmodel.

Deliberately free of Qt: the screen renders this, tests exercise this. The lab is
an evaluation sandbox — it shows what the policy engine *would* decide and
audits the evaluation, but it cannot execute and cannot change the active mode.
"""

from __future__ import annotations

import json
from dataclasses import dataclass

from pydantic import ValidationError

from ningx.app.context import AppContext
from ningx.contracts.action import Action
from ningx.contracts.enums import PermissionMode
from ningx.core.policy_engine import PolicyContext
from ningx.core.ports import AuditEvent


class ActionParseError(ValueError):
    """Raised when untrusted JSON cannot become an Action."""


@dataclass(frozen=True)
class ReasonRow:
    code: str
    stage: str
    detail: str


@dataclass(frozen=True)
class Evaluation:
    ok: bool
    error: str | None
    summary: str
    outcome: str
    risk: str
    blocked_at: str
    approval_required: bool
    reversible: bool
    reasons: tuple[ReasonRow, ...]
    ops: tuple[str, ...]


def parse_action(raw: str) -> Action:
    try:
        data = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise ActionParseError(f"invalid JSON at line {exc.lineno}: {exc.msg}") from None
    if not isinstance(data, dict):
        raise ActionParseError("an action must be a JSON object")
    try:
        return Action.model_validate(data)
    except ValidationError as exc:
        location = ".".join(str(part) for part in exc.errors()[0]["loc"]) or "action"
        message = str(exc.errors()[0]["msg"])
        raise ActionParseError(f"{location}: {message}") from None


def evaluate(
    ctx: AppContext,
    raw: str,
    mode: PermissionMode,
    *,
    audit: bool = True,
) -> Evaluation:
    try:
        action = parse_action(raw)
    except ActionParseError as exc:
        return _error(str(exc))

    try:
        assessment = ctx.assessor.assess(action)
        context = PolicyContext(mode=mode, now=ctx.clock())
        decision = ctx.policy.evaluate(action, context, assessment)
        plan = ctx.dry_run.plan(action, decision)
    except Exception as exc:
        return _error(f"{type(exc).__name__}: {exc}")

    if audit:
        ctx.audit.append(
            AuditEvent(
                actor="ui:policy-lab",
                event_type="policy.evaluated",
                subject_id=str(action.action_id),
                detail={
                    "mode": str(mode),
                    "action_type": action.action_type,
                    "outcome": str(decision.outcome),
                    "risk": decision.risk.name,
                    "reasons": list(decision.reason_codes()),
                },
            )
        )

    return Evaluation(
        ok=True,
        error=None,
        summary=decision.summary(),
        outcome=str(decision.outcome),
        risk=decision.risk.label,
        blocked_at="" if decision.blocked_at is None else str(decision.blocked_at),
        approval_required=decision.approval_required,
        reversible=plan.reversible,
        reasons=tuple(
            ReasonRow(code=reason.code, stage=str(reason.stage), detail=reason.detail)
            for reason in decision.reasons
        ),
        ops=tuple(op.describe() for op in plan.ops),
    )


def _error(message: str) -> Evaluation:
    return Evaluation(
        ok=False,
        error=message,
        summary="Rejected before policy evaluation",
        outcome="invalid",
        risk="-",
        blocked_at="-",
        approval_required=False,
        reversible=False,
        reasons=(),
        ops=(),
    )


SAMPLE_PROCESS_ACTION = """{
  "action_type": "process_terminate",
  "target": {
    "kind": "process",
    "pid": 4242,
    "create_time": 1000.0,
    "executable": "C:\\\\Program Files\\\\Example\\\\example.exe"
  },
  "reason": "Sustained 38% CPU for 25 minutes with no foreground window.",
  "expected_effect": "Frees roughly 1.2 GB of private memory.",
  "requested_by": "agent:process-sniper"
}"""

SAMPLE_STARTUP_ACTION = json.dumps(
    {
        "action_type": "startup_disable",
        "target": {
            "kind": "startup",
            "hive": "HKCU",
            "registry_path": (
                "Software\\Microsoft\\Windows\\CurrentVersion\\Explorer"
                "\\StartupApproved\\Run"
            ),
            "value_name": "ExampleUpdater",
        },
        "reason": "Updater launches at logon and idles at 0.1% CPU for the rest of the session.",
        "expected_effect": "Removes one logon-time contributor; reversible from Startup Manager.",
        "requested_by": "agent:startup-engineer",
    },
    indent=2,
)

SAMPLE_TAMPERED_ACTION = """{
  "action_type": "process_terminate",
  "target": {
    "kind": "process",
    "pid": 4242,
    "create_time": 1000.0,
    "executable": "C:\\\\Program Files\\\\Example\\\\example.exe"
  },
  "risk": "low",
  "reversible": true,
  "requested_by": "provider:unknown"
}"""


__all__ = [
    "SAMPLE_PROCESS_ACTION",
    "SAMPLE_STARTUP_ACTION",
    "SAMPLE_TAMPERED_ACTION",
    "ActionParseError",
    "Evaluation",
    "ReasonRow",
    "evaluate",
    "parse_action",
]
