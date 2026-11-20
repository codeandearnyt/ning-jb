"""Shared enums for the permission, risk and action model.

These are the vocabulary of the safety spine. They are deliberately small and
closed: a new permission mode or risk level is a policy change, not a plugin.
"""

from __future__ import annotations

from enum import IntEnum, StrEnum


class PermissionMode(StrEnum):
    """Top-level autonomy policy. No agent may override this."""

    READ = "read"
    AGENT = "agent"
    FULL_ACCESS = "full_access"

    @property
    def label(self) -> str:
        return _MODE_LABELS[self]


_MODE_LABELS = {
    PermissionMode.READ: "Read only",
    PermissionMode.AGENT: "Agent (approve each change)",
    PermissionMode.FULL_ACCESS: "Full-Access (bounded autonomy)",
}


class RiskLevel(IntEnum):
    """Deterministic risk. Ordered so comparisons are meaningful."""

    INFORMATIONAL = 0
    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4

    @property
    def label(self) -> str:
        return self.name.capitalize()


class ActionCategory(StrEnum):
    PROCESS = "process"
    STARTUP = "startup"
    FILE = "file"
    REGISTRY = "registry"
    POWER = "power"
    NETWORK = "network"
    SERVICE = "service"
    HARDWARE = "hardware"


class ActionState(StrEnum):
    PROPOSED = "proposed"
    POLICY_BLOCKED = "policy_blocked"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    EXECUTING = "executing"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class DecisionOutcome(StrEnum):
    ALLOW = "allow"
    REQUIRE_APPROVAL = "require_approval"
    DENY = "deny"


class PrecedenceStage(StrEnum):
    """Where in PRD §5.4 ordering a decision was settled."""

    SAFETY_HARD = "safety_hard"
    CAPABILITY = "capability"
    MODE = "mode"
    USER_LISTS = "user_lists"
    RISK = "risk"
    APPROVAL = "approval"
    EXECUTION = "execution"


class ApprovalState(StrEnum):
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    EXPIRED = "expired"
    CONSUMED = "consumed"


class ExecutionKind(StrEnum):
    """How an agent produced its output. The UI is required to show this."""

    DETERMINISTIC = "deterministic"
    LLM = "llm"
    CACHED = "cached"
    SKIPPED = "skipped"


__all__ = [
    "ActionCategory",
    "ActionState",
    "ApprovalState",
    "DecisionOutcome",
    "ExecutionKind",
    "PermissionMode",
    "PrecedenceStage",
    "RiskLevel",
]
