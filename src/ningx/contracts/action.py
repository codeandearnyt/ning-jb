"""The action contract.

An :class:`Action` is a *proposal*: what to do, to which exact target, with which
parameters. It deliberately carries no risk level, no reversibility flag and no
executor reference — those are derived deterministically by the policy engine
and action registry. Because ``extra="forbid"`` is set, an AI payload that tries
to smuggle in ``risk: "low"`` or ``reversible: true`` fails validation instead of
being silently ignored.
"""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, field_validator

from ningx.contracts.time import ensure_utc, utcnow

# PEP 695 aliases: pydantic needs a named recursive type to build a schema for
# JSON parameters without recursing into the type itself.
type JsonScalar = str | int | float | bool | None
type JsonValue = JsonScalar | list[JsonValue] | dict[str, JsonValue]

_ACTION_TYPE_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")

_FROZEN = ConfigDict(extra="forbid", frozen=True)


def _reject_control(value: str) -> str:
    if any(ord(ch) < 0x20 for ch in value):
        raise ValueError("control characters are not allowed")
    return value


class ProcessTarget(BaseModel):
    """A process identity, never a bare PID.

    ``create_time`` is part of the identity because Windows reuses PIDs. An
    action proposed against PID 1234 is only valid while PID 1234 still refers
    to the same process instance.
    """

    model_config = _FROZEN

    kind: Literal["process"] = "process"
    pid: int = Field(ge=1)
    create_time: float = Field(ge=0)
    executable: str | None = Field(default=None, max_length=32_767)
    username: str | None = Field(default=None, max_length=256)


class PathTarget(BaseModel):
    model_config = _FROZEN

    kind: Literal["path"] = "path"
    path: str = Field(min_length=1, max_length=32_767)

    @field_validator("path")
    @classmethod
    def _validate(cls, value: str) -> str:
        if "\x00" in value:
            raise ValueError("NUL byte in path")
        return _reject_control(value)


class StartupTarget(BaseModel):
    """A startup entry identified by its registry location and value name."""

    model_config = _FROZEN

    kind: Literal["startup"] = "startup"
    hive: Literal["HKCU", "HKLM"] = "HKCU"
    registry_path: str = Field(min_length=1, max_length=1024)
    value_name: str = Field(min_length=1, max_length=256)


class RegistryTarget(BaseModel):
    model_config = _FROZEN

    kind: Literal["registry"] = "registry"
    hive: Literal["HKCU", "HKLM"]
    key_path: str = Field(min_length=1, max_length=1024)
    value_name: str = Field(min_length=1, max_length=256)


class PowerPlanTarget(BaseModel):
    model_config = _FROZEN

    kind: Literal["power_plan"] = "power_plan"
    guid: str = Field(
        pattern=(
            r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}"
            r"-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$"
        )
    )


class ServiceTarget(BaseModel):
    model_config = _FROZEN

    kind: Literal["service"] = "service"
    name: str = Field(min_length=1, max_length=256)


class HardwareTarget(BaseModel):
    """Hardware tuning target. Denied in this release by policy, not by omission."""

    model_config = _FROZEN

    kind: Literal["hardware"] = "hardware"
    device: str = Field(min_length=1, max_length=256)
    setting: str = Field(min_length=1, max_length=128)


type ActionTarget = Annotated[
    ProcessTarget
    | PathTarget
    | StartupTarget
    | RegistryTarget
    | PowerPlanTarget
    | ServiceTarget
    | HardwareTarget,
    Field(discriminator="kind"),
]


class Action(BaseModel):
    """An immutable proposal to change system state."""

    model_config = _FROZEN

    schema_version: Literal[1] = 1
    action_id: UUID = Field(default_factory=uuid4)
    action_type: str
    target: ActionTarget
    parameters: dict[str, JsonValue] = Field(default_factory=dict)
    reason: str = Field(default="", max_length=2000)
    expected_effect: str = Field(default="", max_length=1000)
    requested_by: str = Field(default="unknown", max_length=64)
    created_at: datetime = Field(default_factory=utcnow)

    @field_validator("action_type")
    @classmethod
    def _validate_action_type(cls, value: str) -> str:
        if not _ACTION_TYPE_RE.match(value):
            raise ValueError("action_type must be snake_case, 3-64 chars")
        return value

    @field_validator("created_at")
    @classmethod
    def _validate_created_at(cls, value: datetime) -> datetime:
        return ensure_utc(value)

    def target_kind(self) -> str:
        return self.target.kind


__all__ = [
    "Action",
    "ActionTarget",
    "HardwareTarget",
    "JsonScalar",
    "JsonValue",
    "PathTarget",
    "PowerPlanTarget",
    "ProcessTarget",
    "RegistryTarget",
    "ServiceTarget",
    "StartupTarget",
]
