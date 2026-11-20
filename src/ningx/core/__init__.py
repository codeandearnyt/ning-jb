"""Core services: policy, permissions, planning, ports."""

from __future__ import annotations

from ningx.core.action_registry import (
    ActionRegistry,
    ActionSpec,
    DuplicateActionType,
    build_default_registry,
)
from ningx.core.binding import (
    BindingCheck,
    canonical_json,
    canonical_payload,
    compute_payload_hash,
    verify_binding,
)
from ningx.core.dry_run import DryRunExecutor, DryRunPlan, IntendedOp
from ningx.core.permission_manager import ModeChangeRejected, PermissionManager
from ningx.core.policy_engine import (
    PolicyContext,
    PolicyDecision,
    PolicyEngine,
    PolicyReason,
)
from ningx.core.ports import AuditEvent, AuditSink, SettingsStore
from ningx.core.risk import compute_risk

__all__ = [
    "ActionRegistry",
    "ActionSpec",
    "AuditEvent",
    "AuditSink",
    "BindingCheck",
    "DryRunExecutor",
    "DryRunPlan",
    "DuplicateActionType",
    "IntendedOp",
    "ModeChangeRejected",
    "PermissionManager",
    "PolicyContext",
    "PolicyDecision",
    "PolicyEngine",
    "PolicyReason",
    "SettingsStore",
    "build_default_registry",
    "canonical_json",
    "canonical_payload",
    "compute_payload_hash",
    "compute_risk",
    "verify_binding",
]
