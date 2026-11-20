"""The policy engine.

Precedence is fixed by PRD §5.4 and implemented here in that order:

1. hard safety deny rules
2. Windows capability / privilege checks
3. user-selected permission mode
4. user allow / deny lists
5. risk classification and action-specific requirements
6. approval state
7. execution

A lower level can never relax a higher one. ``evaluate`` is a pure function of
``(action, context, target assessment)`` plus the sealed action registry, so the
whole permission truth table can be enumerated in tests.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from uuid import UUID

from ningx.contracts.action import Action
from ningx.contracts.approval import ApprovalRequest
from ningx.contracts.enums import (
    DecisionOutcome,
    PermissionMode,
    PrecedenceStage,
    RiskLevel,
)
from ningx.contracts.time import ensure_utc
from ningx.core.action_registry import ActionRegistry, ActionSpec
from ningx.core.binding import verify_binding
from ningx.core.risk import compute_risk
from ningx.security.target_assessor import TargetAssessment


@dataclass(frozen=True)
class PolicyReason:
    code: str
    stage: PrecedenceStage
    detail: str = ""


@dataclass(frozen=True)
class PolicyContext:
    mode: PermissionMode
    now: datetime
    is_elevated: bool = False
    denied_action_types: frozenset[str] = frozenset()
    allowed_action_types: frozenset[str] = frozenset()
    approval: ApprovalRequest | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "now", ensure_utc(self.now))

    def with_mode(self, mode: PermissionMode) -> PolicyContext:
        return replace(self, mode=mode)

    def with_approval(self, approval: ApprovalRequest | None) -> PolicyContext:
        return replace(self, approval=approval)


@dataclass(frozen=True)
class PolicyDecision:
    action_id: UUID
    action_type: str
    outcome: DecisionOutcome
    risk: RiskLevel
    reasons: tuple[PolicyReason, ...]
    blocked_at: PrecedenceStage | None
    approval_required: bool
    full_access_eligible: bool
    spec: ActionSpec | None

    @property
    def allowed(self) -> bool:
        return self.outcome is DecisionOutcome.ALLOW

    @property
    def denied(self) -> bool:
        return self.outcome is DecisionOutcome.DENY

    def reason_codes(self) -> tuple[str, ...]:
        return tuple(reason.code for reason in self.reasons)

    def summary(self) -> str:
        if self.outcome is DecisionOutcome.ALLOW:
            return f"Allowed ({self.risk.label} risk)"
        if self.outcome is DecisionOutcome.REQUIRE_APPROVAL:
            return f"Needs approval ({self.risk.label} risk)"
        return f"Denied at {self.blocked_at}: {', '.join(self.reason_codes())}"


class PolicyEngine:
    def __init__(self, registry: ActionRegistry) -> None:
        self._registry = registry

    def evaluate(
        self,
        action: Action,
        ctx: PolicyContext,
        assessment: TargetAssessment,
    ) -> PolicyDecision:
        spec = self._registry.require(action.action_type)
        risk = (
            compute_risk(action, spec, assessment)
            if spec is not None
            else RiskLevel.CRITICAL
        )

        # ---------------------------------------------------------- 1. hard safety
        reasons: list[PolicyReason] = []

        if spec is None:
            reasons.append(
                _r("action.unknown_type", PrecedenceStage.SAFETY_HARD, action.action_type)
            )
        else:
            if spec.expected_target_kind != action.target.kind:
                reasons.append(
                    _r(
                        "action.target_kind_mismatch",
                        PrecedenceStage.SAFETY_HARD,
                        f"expected {spec.expected_target_kind}, got {action.target.kind}",
                    )
                )
            if spec.denied_in_release:
                reasons.append(
                    _r("action.unavailable_in_release", PrecedenceStage.SAFETY_HARD)
                )

        for code in assessment.reasons:
            reasons.append(_r(code, PrecedenceStage.SAFETY_HARD))

        if risk is RiskLevel.CRITICAL and spec is not None and not spec.denied_in_release:
            reasons.append(_r("risk.critical", PrecedenceStage.SAFETY_HARD))

        if reasons:
            return _decide(action, DecisionOutcome.DENY, risk, reasons, spec)

        assert spec is not None  # narrowed: spec is None always produced a deny above

        # ---------------------------------------------------------- 2. capability
        if spec.requires_elevation and not ctx.is_elevated:
            reasons.append(
                _r(
                    "capability.elevation_required",
                    PrecedenceStage.CAPABILITY,
                    "this build has no elevated helper; the action is unavailable",
                )
            )
            return _decide(action, DecisionOutcome.DENY, risk, reasons, spec)

        # ------------------------------------------------------------------ 3. mode
        if ctx.mode is PermissionMode.READ:
            reasons.append(_r("mode.read_only", PrecedenceStage.MODE))
            return _decide(action, DecisionOutcome.DENY, risk, reasons, spec)

        approval_required = ctx.mode is PermissionMode.AGENT
        if approval_required:
            reasons.append(_r("mode.agent_requires_approval", PrecedenceStage.MODE))

        # ------------------------------------------------------------ 4. user lists
        if action.action_type in ctx.denied_action_types:
            reasons.append(_r("user_lists.denied", PrecedenceStage.USER_LISTS))
            return _decide(action, DecisionOutcome.DENY, risk, reasons, spec)

        allowlisted = (
            not ctx.allowed_action_types
            or action.action_type in ctx.allowed_action_types
        )
        if not allowlisted:
            reasons.append(_r("user_lists.not_allowlisted", PrecedenceStage.USER_LISTS))

        # ------------------------------------------------------------------ 5. risk
        if ctx.mode is PermissionMode.FULL_ACCESS:
            autonomous = (
                spec.full_access_eligible
                and risk <= RiskLevel.MEDIUM
                and allowlisted
            )
            if autonomous:
                approval_required = False
            else:
                approval_required = True
                reasons.append(
                    _r(
                        "risk.autonomy_not_eligible",
                        PrecedenceStage.RISK,
                        "action is outside the Full-Access allowlist",
                    )
                )

        if risk >= RiskLevel.HIGH:
            approval_required = True
            reasons.append(_r("risk.high_requires_approval", PrecedenceStage.RISK))

        # -------------------------------------------------------------- 6. approval
        if approval_required:
            if ctx.approval is None:
                reasons.append(_r("approval.missing", PrecedenceStage.APPROVAL))
                return _decide(
                    action, DecisionOutcome.REQUIRE_APPROVAL, risk, reasons, spec
                )
            check = verify_binding(
                ctx.approval, action, current_mode=ctx.mode, now=ctx.now
            )
            if not check.ok:
                reasons.extend(
                    _r(code, PrecedenceStage.APPROVAL) for code in check.reasons
                )
                return _decide(
                    action, DecisionOutcome.REQUIRE_APPROVAL, risk, reasons, spec
                )

        # --------------------------------------------------------- 7. execution
        return _decide(action, DecisionOutcome.ALLOW, risk, reasons, spec)


def _r(code: str, stage: PrecedenceStage, detail: str = "") -> PolicyReason:
    return PolicyReason(code=code, stage=stage, detail=detail)


def _decide(
    action: Action,
    outcome: DecisionOutcome,
    risk: RiskLevel,
    reasons: list[PolicyReason],
    spec: ActionSpec | None,
) -> PolicyDecision:
    blocked_at = None
    if outcome is DecisionOutcome.DENY:
        blocked_at = reasons[-1].stage if reasons else PrecedenceStage.SAFETY_HARD
    elif outcome is DecisionOutcome.REQUIRE_APPROVAL:
        blocked_at = PrecedenceStage.APPROVAL

    return PolicyDecision(
        action_id=action.action_id,
        action_type=action.action_type,
        outcome=outcome,
        risk=risk,
        reasons=tuple(reasons),
        blocked_at=blocked_at,
        approval_required=outcome is DecisionOutcome.REQUIRE_APPROVAL,
        full_access_eligible=bool(spec.full_access_eligible) if spec else False,
        spec=spec,
    )


__all__ = ["PolicyContext", "PolicyDecision", "PolicyEngine", "PolicyReason"]
