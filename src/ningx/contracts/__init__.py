"""Contracts package: the vocabulary shared by every layer.

Nothing in here performs I/O, reads the system, or imports the UI.
"""

from __future__ import annotations

from ningx.contracts.action import (
    Action,
    ActionTarget,
    HardwareTarget,
    JsonScalar,
    JsonValue,
    PathTarget,
    PowerPlanTarget,
    ProcessTarget,
    RegistryTarget,
    ServiceTarget,
    StartupTarget,
)
from ningx.contracts.approval import ApprovalDecision, ApprovalRequest
from ningx.contracts.enums import (
    ActionCategory,
    ActionState,
    ApprovalState,
    DecisionOutcome,
    ExecutionKind,
    PermissionMode,
    PrecedenceStage,
    RiskLevel,
)
from ningx.contracts.time import Clock, FakeClock, ensure_utc, plus_seconds, utcnow

__all__ = [
    "Action",
    "ActionCategory",
    "ActionState",
    "ActionTarget",
    "ApprovalDecision",
    "ApprovalRequest",
    "ApprovalState",
    "Clock",
    "DecisionOutcome",
    "ExecutionKind",
    "FakeClock",
    "HardwareTarget",
    "JsonScalar",
    "JsonValue",
    "PathTarget",
    "PermissionMode",
    "PowerPlanTarget",
    "PrecedenceStage",
    "ProcessTarget",
    "RegistryTarget",
    "RiskLevel",
    "ServiceTarget",
    "StartupTarget",
    "ensure_utc",
    "plus_seconds",
    "utcnow",
]
