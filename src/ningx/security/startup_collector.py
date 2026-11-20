"""Read-only startup inventory.

The startup analyst needs to know what runs at logon. That is a *read*: this
module enumerates two registry locations and the approvals key that records
whether Windows disabled an entry. It writes nothing, and a failure to read one
location is reported as a missing entry rather than an exception — an analyst
must never turn a permissions problem into a fake finding.

Commands are parsed only far enough to find the executable path, so the analyst
can say "this entry points at a file that no longer exists" with evidence.
"""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
APPROVED_KEY = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
)
_WOW64_RUN_KEY = r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Run"

# StartupApproved values are binary: the first byte is 2 or 6 for disabled
# entries, 0 or 1 for enabled ones. Anything else is treated as enabled, which
# is the safer reading for an informational report.
_DISABLED_FLAGS = frozenset({0x02, 0x03, 0x06})


@dataclass(frozen=True)
class StartupEntry:
    name: str
    command: str
    location: str
    scope: str
    enabled: bool
    executable: str | None = None
    exists: bool | None = None

    @property
    def fingerprint_subject(self) -> str:
        return f"{self.location}\\{self.name}".lower()


class StartupCollector(Protocol):
    def collect(self) -> list[StartupEntry]: ...


class WinregStartupCollector:
    """Enumerate ``Run`` keys for the current user and all users."""

    def __init__(self, *, check_paths: bool = True) -> None:
        self._check_paths = check_paths

    def collect(self) -> list[StartupEntry]:
        entries: list[StartupEntry] = []
        for hive_name, key_path, scope in (
            ("HKCU", RUN_KEY, "current user"),
            ("HKLM", RUN_KEY, "all users"),
            ("HKLM", _WOW64_RUN_KEY, "all users (32-bit)"),
        ):
            entries.extend(self._read_run_key(hive_name, key_path, scope))
        return entries

    # ------------------------------------------------------------------ internals

    def _read_run_key(self, hive_name: str, key_path: str, scope: str) -> list[StartupEntry]:
        try:
            import winreg
        except ImportError:  # pragma: no cover - only on non-Windows
            return []

        hive = winreg.HKEY_CURRENT_USER if hive_name == "HKCU" else winreg.HKEY_LOCAL_MACHINE
        try:
            with winreg.OpenKey(hive, key_path) as key:
                approved = self._approved_values(winreg, hive)
                entries: list[StartupEntry] = []
                index = 0
                while True:
                    try:
                        name, command, _kind = winreg.EnumValue(key, index)
                    except OSError:
                        break
                    index += 1
                    if not isinstance(command, str) or not command.strip():
                        continue
                    executable = parse_executable(command)
                    exists = _exists(executable) if self._check_paths else None
                    entries.append(
                        StartupEntry(
                            name=str(name),
                            command=command,
                            location=f"{hive_name}\\{key_path}",
                            scope=scope,
                            enabled=not _is_disabled(approved.get(str(name).lower())),
                            executable=executable,
                            exists=exists,
                        )
                    )
                return entries
        except OSError:
            return []

    def _approved_values(self, winreg: object, hive: object) -> dict[str, bytes]:
        try:
            with winreg.OpenKey(hive, APPROVED_KEY) as key:  # type: ignore[attr-defined]
                values: dict[str, bytes] = {}
                index = 0
                while True:
                    try:
                        name, data, _kind = winreg.EnumValue(key, index)  # type: ignore[attr-defined]
                    except OSError:
                        break
                    index += 1
                    if isinstance(data, (bytes, bytearray)):
                        values[str(name).lower()] = bytes(data)
                return values
        except OSError:
            return {}


class FakeStartupCollector:
    """Scripted entries for tests and the UI smoke harness."""

    def __init__(self, entries: list[StartupEntry] | None = None) -> None:
        self._entries = list(entries or [])

    def collect(self) -> list[StartupEntry]:
        return list(self._entries)


def parse_executable(command: str) -> str | None:
    """Return the executable path from a ``Run`` command line, if it has one."""
    text = command.strip()
    if not text:
        return None
    expanded = os.path.expandvars(text)
    if expanded.startswith('"'):
        end = expanded.find('"', 1)
        candidate = expanded[1:end] if end > 0 else expanded[1:]
    else:
        try:
            parts = shlex.split(expanded, posix=False)
        except ValueError:
            parts = expanded.split()
        candidate = parts[0] if parts else ""
    candidate = candidate.strip().strip('"')
    if not candidate:
        return None
    # ``rundll32.exe foo.dll,Entry`` and similar host processes are still real
    # executables; the path check is about the first token only.
    return os.path.expandvars(candidate)


def _exists(path: str | None) -> bool | None:
    if not path:
        return None
    try:
        return Path(path).is_file()
    except OSError:
        return None


def _is_disabled(flag_value: bytes | None) -> bool:
    if not flag_value:
        return False
    return flag_value[0] in _DISABLED_FLAGS


__all__ = [
    "FakeStartupCollector",
    "StartupCollector",
    "StartupEntry",
    "WinregStartupCollector",
    "parse_executable",
]
