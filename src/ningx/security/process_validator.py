"""Process identity validation.

A PID is not an identity. Windows reuses PIDs aggressively, so an action that
says "terminate PID 1234" can hit a completely different program a second later.
Every process action therefore carries ``(pid, create_time, executable)`` and is
revalidated against live state immediately before execution.
"""

from __future__ import annotations

import ntpath
from dataclasses import dataclass
from typing import Any, Protocol

from ningx.security.protected_targets import ProtectedTargets

_CREATE_TIME_TOLERANCE = 0.05


@dataclass(frozen=True)
class ProcessFacts:
    pid: int
    create_time: float
    name: str
    exe: str | None = None
    username: str | None = None
    session_id: int | None = None
    parent_pid: int | None = None
    publisher: str | None = None
    is_signed: bool | None = None


@dataclass(frozen=True)
class ProcessCheck:
    ok: bool
    reasons: tuple[str, ...]
    flags: tuple[str, ...]
    facts: ProcessFacts | None


class ProcessProbe(Protocol):
    def snapshot(self, pid: int) -> ProcessFacts | None: ...

    def current_pid(self) -> int: ...

    def current_username(self) -> str | None: ...

    def ancestors(self) -> tuple[int, ...]: ...


class ProcessValidator:
    def __init__(self, probe: ProcessProbe, protected: ProtectedTargets) -> None:
        self._probe = probe
        self._protected = protected

    def validate(
        self,
        *,
        pid: int,
        create_time: float,
        executable: str | None = None,
    ) -> ProcessCheck:
        reasons: list[str] = []
        flags: list[str] = []

        if pid == self._probe.current_pid():
            return ProcessCheck(False, ("process.self",), (), None)

        if pid in self._probe.ancestors():
            return ProcessCheck(False, ("process.ancestor",), (), None)

        facts = self._probe.snapshot(pid)
        if facts is None:
            return ProcessCheck(False, ("process.not_found",), (), None)

        if abs(facts.create_time - create_time) > _CREATE_TIME_TOLERANCE:
            reasons.append("process.pid_reused")

        if executable and facts.exe and not _same_path(executable, facts.exe):
            reasons.append("process.executable_changed")

        denial = self._protected.process_denial(
            name=facts.name,
            exe=facts.exe,
            publisher=facts.publisher,
            session_id=facts.session_id,
        )
        if denial is not None:
            reasons.append(denial)

        if facts.is_signed is False:
            flags.append("process.unsigned")

        current_user = self._probe.current_username()
        if current_user and facts.username and not _same_user(facts.username, current_user):
            flags.append("process.other_user")

        return ProcessCheck(not reasons, tuple(reasons), tuple(flags), facts)


def _same_path(left: str, right: str) -> bool:
    return ntpath.normcase(ntpath.normpath(left)) == ntpath.normcase(ntpath.normpath(right))


def _same_user(left: str, right: str) -> bool:
    return left.strip().lower() == right.strip().lower()


class FakeProcessProbe:
    """Deterministic probe for tests. No real process is ever inspected."""

    def __init__(
        self,
        processes: dict[int, ProcessFacts] | None = None,
        *,
        current_pid: int = 999_000,
        current_username: str = "dev\\user",
        ancestor_pids: tuple[int, ...] = (),
    ) -> None:
        self._processes = dict(processes or {})
        self._current_pid = current_pid
        self._current_username = current_username
        self._ancestors = ancestor_pids

    def snapshot(self, pid: int) -> ProcessFacts | None:
        return self._processes.get(pid)

    def current_pid(self) -> int:
        return self._current_pid

    def current_username(self) -> str | None:
        return self._current_username

    def ancestors(self) -> tuple[int, ...]:
        return self._ancestors

    def add(self, facts: ProcessFacts) -> None:
        self._processes[facts.pid] = facts

    def remove(self, pid: int) -> None:
        self._processes.pop(pid, None)


class PsutilProcessProbe:
    """Live probe. Read-only: it never terminates or suspends anything."""

    def __init__(self) -> None:
        import psutil  # imported lazily so core tests need no live process table

        self._psutil = psutil
        self._me = psutil.Process()
        self._current_username = _read_username(self._me)
        self._ancestors = self._read_ancestors()

    def snapshot(self, pid: int) -> ProcessFacts | None:
        try:
            process = self._psutil.Process(pid)
            with process.oneshot():
                exe = _safe_str(process.exe)
                name = _safe_str(process.name) or f"pid-{pid}"
                create_time = float(process.create_time())
                return ProcessFacts(
                    pid=pid,
                    create_time=create_time,
                    name=name,
                    exe=exe,
                    username=_read_username(process),
                    session_id=_session_id(pid),
                    parent_pid=_safe_int(process.ppid),
                    is_signed=_signature_state(exe),
                )
        except Exception:
            return None

    def current_pid(self) -> int:
        return int(self._me.pid)

    def current_username(self) -> str | None:
        return self._current_username

    def ancestors(self) -> tuple[int, ...]:
        return self._ancestors

    def _read_ancestors(self) -> tuple[int, ...]:
        found: list[int] = []
        try:
            for parent in self._me.parents():
                found.append(int(parent.pid))
        except Exception:
            return ()
        return tuple(found)


def _signature_state(exe: str | None) -> bool | None:
    if not exe:
        return None
    from ningx.security.signature import verify_authenticode

    return verify_authenticode(exe)


def _read_username(process: Any) -> str | None:
    try:
        value = process.username()
    except Exception:
        return None
    return value if isinstance(value, str) else None


def _safe_str(func: Any) -> str | None:
    try:
        value = func()
    except Exception:
        return None
    return value if isinstance(value, str) else None


def _safe_int(func: Any) -> int | None:
    try:
        value = func()
    except Exception:
        return None
    return int(value) if isinstance(value, int) else None


def _session_id(pid: int) -> int | None:
    """Windows session id via win32ts; ``None`` when unavailable. Never guessed."""
    try:
        import win32ts  # type: ignore[import-untyped]

        return int(win32ts.ProcessIdToSessionId(pid))
    except Exception:
        return None


__all__ = [
    "FakeProcessProbe",
    "ProcessCheck",
    "ProcessFacts",
    "ProcessProbe",
    "ProcessValidator",
    "PsutilProcessProbe",
]
