"""The single door to the operating system.

Every side effect in NingX goes through :class:`WindowsOps`. That is what makes
the safety tests meaningful: CI runs against :class:`FakeWindowsOps`, so no test
can terminate a real process or delete a real file, and production code cannot
invent a second way to reach Windows.

In this build the mutating methods of :class:`RealWindowsOps` are intentionally
unimplemented. Executors are wired in M6, after the approval path exists.
"""

from __future__ import annotations

import subprocess
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from ningx.security.process_validator import ProcessFacts, ProcessProbe


@dataclass(frozen=True)
class ToolResult:
    argv: tuple[str, ...]
    returncode: int
    stdout: str = ""
    stderr: str = ""

    @property
    def ok(self) -> bool:
        return self.returncode == 0


@dataclass(frozen=True)
class RegistryValue:
    hive: str
    key_path: str
    name: str
    value: Any
    value_type: int | None = None


class MutationNotAvailable(RuntimeError):
    """Raised by any mutating method that is not implemented in this build."""


class WindowsOps(Protocol):
    def process_snapshot(self, pid: int) -> ProcessFacts | None: ...

    def terminate_process(self, pid: int, *, force: bool = False) -> None: ...

    def move_file(self, source: str, destination: str) -> None: ...

    def read_registry(self, hive: str, key_path: str, value_name: str) -> RegistryValue | None: ...

    def write_registry(
        self,
        hive: str,
        key_path: str,
        value_name: str,
        value: Any,
        value_type: int | None = None,
    ) -> None: ...

    def export_registry(self, hive: str, key_path: str, destination: str) -> ToolResult: ...

    def active_power_plan(self) -> str | None: ...

    def set_active_power_plan(self, guid: str) -> ToolResult: ...

    def run_tool(self, argv: Sequence[str], *, timeout: float = 30.0) -> ToolResult: ...


_HIVE_NAMES = {
    "HKCU": "HKEY_CURRENT_USER",
    "HKLM": "HKEY_LOCAL_MACHINE",
}


class RealWindowsOps:
    """Read operations are implemented; mutations arrive in M6.

    No method uses ``shell=True``; arguments are always passed as a sequence.
    """

    def __init__(self) -> None:
        self._probe: ProcessProbe | None = None

    def _process_probe(self) -> ProcessProbe:
        if self._probe is None:
            from ningx.security.process_validator import PsutilProcessProbe

            self._probe = PsutilProcessProbe()
        return self._probe

    # ------------------------------------------------------------------- reads

    def process_snapshot(self, pid: int) -> ProcessFacts | None:
        return self._process_probe().snapshot(pid)

    def read_registry(self, hive: str, key_path: str, value_name: str) -> RegistryValue | None:
        import winreg

        root = _root_key(winreg, hive)
        try:
            with winreg.OpenKey(root, key_path, 0, winreg.KEY_READ) as key:
                value, value_type = winreg.QueryValueEx(key, value_name)
        except OSError:
            return None
        return RegistryValue(hive, key_path, value_name, value, value_type)

    def active_power_plan(self) -> str | None:
        result = self.run_tool(["powercfg", "/getactivescheme"])
        if not result.ok:
            return None
        text = result.stdout
        marker = "GUID:"
        index = text.find(marker)
        if index < 0:
            return None
        return text[index + len(marker) :].strip().split(" ")[0] or None

    def run_tool(self, argv: Sequence[str], *, timeout: float = 30.0) -> ToolResult:
        if not argv or any(not isinstance(part, str) for part in argv):
            raise ValueError("argv must be a non-empty sequence of strings")
        completed = subprocess.run(  # noqa: S603 - argv sequence, shell disabled
            list(argv),
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
            shell=False,
        )
        return ToolResult(
            argv=tuple(argv),
            returncode=completed.returncode,
            stdout=completed.stdout or "",
            stderr=completed.stderr or "",
        )

    # --------------------------------------------------------------- mutations

    def terminate_process(self, pid: int, *, force: bool = False) -> None:
        raise MutationNotAvailable("process termination is not available in this build")

    def move_file(self, source: str, destination: str) -> None:
        raise MutationNotAvailable("file moves are not available in this build")

    def write_registry(
        self,
        hive: str,
        key_path: str,
        value_name: str,
        value: Any,
        value_type: int | None = None,
    ) -> None:
        raise MutationNotAvailable("registry writes are not available in this build")

    def export_registry(self, hive: str, key_path: str, destination: str) -> ToolResult:
        raise MutationNotAvailable("registry export is not available in this build")

    def set_active_power_plan(self, guid: str) -> ToolResult:
        raise MutationNotAvailable("power plan changes are not available in this build")


class FakeWindowsOps:
    """In-memory operating system for tests. Never touches the real machine."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.processes: dict[int, ProcessFacts] = {}
        self.files: set[str] = set()
        self.registry: dict[tuple[str, str, str], RegistryValue] = {}
        self.power_plan = "381b4222-f694-41f0-9685-ff5bb260df2e"
        self.failures: dict[str, Exception] = {}

    def _record(self, op: str, **details: Any) -> None:
        self.calls.append((op, details))
        failure = self.failures.get(op)
        if failure is not None:
            raise failure

    def process_snapshot(self, pid: int) -> ProcessFacts | None:
        self._record("process_snapshot", pid=pid)
        return self.processes.get(pid)

    def terminate_process(self, pid: int, *, force: bool = False) -> None:
        self._record("terminate_process", pid=pid, force=force)
        self.processes.pop(pid, None)

    def move_file(self, source: str, destination: str) -> None:
        self._record("move_file", source=source, destination=destination)
        self.files.discard(source)
        self.files.add(destination)

    def read_registry(self, hive: str, key_path: str, value_name: str) -> RegistryValue | None:
        self._record("read_registry", hive=hive, key_path=key_path, value_name=value_name)
        return self.registry.get((hive, key_path, value_name))

    def write_registry(
        self,
        hive: str,
        key_path: str,
        value_name: str,
        value: Any,
        value_type: int | None = None,
    ) -> None:
        self._record(
            "write_registry",
            hive=hive,
            key_path=key_path,
            value_name=value_name,
            value=value,
        )
        self.registry[(hive, key_path, value_name)] = RegistryValue(
            hive, key_path, value_name, value, value_type
        )

    def export_registry(self, hive: str, key_path: str, destination: str) -> ToolResult:
        self._record("export_registry", hive=hive, key_path=key_path, destination=destination)
        return ToolResult(("reg", "export"), 0, stdout="exported")

    def active_power_plan(self) -> str | None:
        self._record("active_power_plan")
        return self.power_plan

    def set_active_power_plan(self, guid: str) -> ToolResult:
        self._record("set_active_power_plan", guid=guid)
        self.power_plan = guid
        return ToolResult(("powercfg", "/setactive", guid), 0)

    def run_tool(self, argv: Sequence[str], *, timeout: float = 30.0) -> ToolResult:
        self._record("run_tool", argv=tuple(argv), timeout=timeout)
        return ToolResult(tuple(argv), 0)

    def mutations(self) -> list[tuple[str, dict[str, Any]]]:
        return [
            (op, details)
            for op, details in self.calls
            if op in {
                "terminate_process",
                "move_file",
                "write_registry",
                "export_registry",
                "set_active_power_plan",
            }
        ]


def _root_key(winreg: Any, hive: str) -> Any:
    normalized = hive.upper().strip()
    if normalized not in _HIVE_NAMES:
        raise ValueError(f"unsupported registry hive: {hive!r}")
    return winreg.HKEY_CURRENT_USER if normalized == "HKCU" else winreg.HKEY_LOCAL_MACHINE


def quarantine_destination(quarantine_root: Path, original: str) -> Path:
    """Deterministic quarantine path that preserves the original name."""
    return quarantine_root / f"{Path(original).name}.quarantined"


__all__ = [
    "FakeWindowsOps",
    "MutationNotAvailable",
    "RealWindowsOps",
    "RegistryValue",
    "ToolResult",
    "WindowsOps",
    "quarantine_destination",
]
