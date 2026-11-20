"""Test doubles and sample data.

Nothing here touches the operating system. These builders are shared by the
policy, validator and matrix tests so a change to an Action shape breaks in one
place, not twenty.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

from ningx.contracts.action import (
    Action,
    HardwareTarget,
    PathTarget,
    PowerPlanTarget,
    ProcessTarget,
    RegistryTarget,
    ServiceTarget,
    StartupTarget,
)
from ningx.core.ports import AuditEvent
from ningx.security.process_validator import ProcessFacts

CLOCK_START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

APPROVED_STARTUP_PATH = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
)

EXAMPLE_EXE = r"C:\Program Files\Example\example.exe"


def make_facts(
    pid: int,
    name: str,
    *,
    create_time: float = 1000.0,
    exe: str | None = None,
    username: str | None = "dev\\user",
    session_id: int | None = 1,
    parent_pid: int | None = 500,
    publisher: str | None = None,
    is_signed: bool | None = True,
) -> ProcessFacts:
    return ProcessFacts(
        pid=pid,
        create_time=create_time,
        name=name,
        exe=exe if exe is not None else EXAMPLE_EXE,
        username=username,
        session_id=session_id,
        parent_pid=parent_pid,
        publisher=publisher,
        is_signed=is_signed,
    )


def sample_processes() -> dict[int, ProcessFacts]:
    return {
        4242: make_facts(4242, "example.exe"),
        4243: make_facts(4243, "tools.exe", is_signed=False),
        2000: make_facts(2000, "lsass.exe", exe=r"C:\Windows\System32\lsass.exe"),
        2001: make_facts(2001, "shield.exe", publisher="Acme Antivirus"),
        2002: make_facts(2002, "svc.exe", session_id=0),
        2003: make_facts(2003, "other.exe", username="other\\user"),
        2004: make_facts(2004, "unsigned.exe", is_signed=False),
    }


# ------------------------------------------------------------------------ actions


def process_action(pid: int = 4242, create_time: float = 1000.0) -> Action:
    return Action(
        action_type="process_terminate",
        target=ProcessTarget(pid=pid, create_time=create_time, executable=EXAMPLE_EXE),
        reason="sustained background CPU",
        requested_by="test",
    )


def startup_action(hive: str = "HKCU") -> Action:
    return Action(
        action_type="startup_disable",
        target=StartupTarget(
            hive=hive,  # type: ignore[arg-type]
            registry_path=APPROVED_STARTUP_PATH,
            value_name="ExampleUpdater",
        ),
        reason="logon contributor",
        requested_by="test",
    )


def quarantine_action(path: str) -> Action:
    return Action(
        action_type="file_quarantine",
        target=PathTarget(path=path),
        reason="stale temporary data",
        requested_by="test",
    )


def file_move_action(path: str, destination: str) -> Action:
    return Action(
        action_type="file_move",
        target=PathTarget(path=path),
        parameters={"destination": destination},
        reason="organization",
        requested_by="test",
    )


def registry_action(hive: str = "HKCU") -> Action:
    return Action(
        action_type="registry_set",
        target=RegistryTarget(
            hive=hive,  # type: ignore[arg-type]
            key_path=r"Software\NingX\Test",
            value_name="Example",
        ),
        parameters={"value": 1},
        reason="catalogued setting",
        requested_by="test",
    )


def power_action(guid: str = "381b4222-f694-41f0-9685-ff5bb260df2e") -> Action:
    return Action(
        action_type="power_plan_set",
        target=PowerPlanTarget(guid=guid),
        reason="balanced plan",
        requested_by="test",
    )


def service_action() -> Action:
    return Action(
        action_type="service_stop",
        target=ServiceTarget(name="Spooler"),
        reason="not allowed in this release",
        requested_by="test",
    )


def hardware_action() -> Action:
    return Action(
        action_type="hardware_tune",
        target=HardwareTarget(device="gpu0", setting="core_offset"),
        parameters={"value": 50},
        reason="not allowed in this release",
        requested_by="test",
    )


def all_sample_actions(path: str) -> dict[str, Action]:
    """One representative action per registered type."""
    return {
        "process_terminate": process_action(),
        "startup_disable": startup_action(),
        "file_quarantine": quarantine_action(path),
        "file_move": file_move_action(path, str(path) + ".moved"),
        "registry_set": registry_action(),
        "power_plan_set": power_action(),
        "service_stop": service_action(),
        "hardware_tune": hardware_action(),
    }


# ------------------------------------------------------------------------- sinks


class InMemoryAudit:
    def __init__(self) -> None:
        self.events: list[AuditEvent] = []

    def append(self, event: AuditEvent) -> None:
        self.events.append(event)

    def recent(self, limit: int = 100) -> list[AuditEvent]:
        return list(reversed(self.events))[:limit]


class InMemorySettings:
    def __init__(self, values: Mapping[str, str] | None = None) -> None:
        self._values: dict[str, str] = dict(values or {})

    def get(self, key: str) -> str | None:
        return self._values.get(key)

    def set(self, key: str, value: str) -> None:
        self._values[key] = value

    def as_dict(self) -> dict[str, Any]:
        return dict(self._values)


__all__ = [
    "APPROVED_STARTUP_PATH",
    "CLOCK_START",
    "EXAMPLE_EXE",
    "InMemoryAudit",
    "InMemorySettings",
    "all_sample_actions",
    "file_move_action",
    "hardware_action",
    "make_facts",
    "power_action",
    "process_action",
    "quarantine_action",
    "registry_action",
    "sample_processes",
    "service_action",
    "startup_action",
]
