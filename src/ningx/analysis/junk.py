"""Bounded, read-only measurement of temporary folders.

A "junk" number that is not measured is worse than no number: users delete
things based on it. This scanner therefore reports exactly what it walked, how
many files it saw, and whether it stopped early because of its own limits.

It never deletes, moves or opens a file's contents. It follows no links, so a
junction pointing at ``C:\\`` cannot turn a temp scan into a full disk walk.
"""

from __future__ import annotations

import os
import time
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Protocol


@dataclass(frozen=True)
class JunkRoot:
    path: str
    bytes: int
    files: int
    truncated: bool
    error: str | None = None


@dataclass(frozen=True)
class JunkReport:
    roots: tuple[JunkRoot, ...] = ()
    scanned_at: datetime | None = None
    limit_hit: bool = False
    errors: tuple[str, ...] = field(default_factory=tuple)

    @property
    def total_bytes(self) -> int:
        return sum(root.bytes for root in self.roots)

    @property
    def total_files(self) -> int:
        return sum(root.files for root in self.roots)


class JunkScannerPort(Protocol):
    def scan(self) -> JunkReport: ...


class JunkScanner:
    """Walk the configured roots with a file-count and a wall-clock budget."""

    def __init__(
        self,
        roots: Iterable[Path],
        *,
        max_files: int = 40_000,
        max_seconds: float = 6.0,
    ) -> None:
        self._roots = tuple(roots)
        self._max_files = max(1, max_files)
        self._max_seconds = max(0.1, max_seconds)

    def scan(self) -> JunkReport:
        started = time.monotonic()
        deadline = started + self._max_seconds
        remaining = self._max_files
        results: list[JunkRoot] = []
        errors: list[str] = []
        limit_hit = False

        for root in self._roots:
            if remaining <= 0 or time.monotonic() >= deadline:
                limit_hit = True
                break
            measured, remaining, root_limit, error = _walk(root, remaining, deadline)
            results.append(measured)
            limit_hit = limit_hit or root_limit
            if error is not None:
                errors.append(error)

        return JunkReport(
            roots=tuple(results),
            scanned_at=datetime.now(UTC),
            limit_hit=limit_hit,
            errors=tuple(errors),
        )


class NullJunkScanner:
    """Used where scanning temp folders is not appropriate (tests, other OSes)."""

    def scan(self) -> JunkReport:
        return JunkReport(scanned_at=datetime.now(UTC))


def default_junk_roots() -> tuple[Path, ...]:
    """The temporary locations Windows itself offers to clean."""
    roots: list[Path] = []
    for variable in ("TEMP", "TMP"):
        value = os.environ.get(variable)
        if value:
            roots.append(Path(value))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        roots.append(Path(local) / "Temp")
    system_root = os.environ.get("SYSTEMROOT") or os.environ.get("WINDIR")
    if system_root:
        roots.append(Path(system_root) / "Temp")

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        key = str(root).lower()
        if key not in seen and root.is_dir():
            seen.add(key)
            unique.append(root)
    return tuple(unique)


def _walk(
    root: Path, budget: int, deadline: float
) -> tuple[JunkRoot, int, bool, str | None]:
    total = 0
    files = 0
    truncated = False
    error: str | None = None

    try:
        for current, _dirs, filenames in root.walk(follow_symlinks=False):
            if time.monotonic() >= deadline:
                truncated = True
                break
            for name in filenames:
                if files >= budget:
                    truncated = True
                    break
                try:
                    stat = (current / name).stat()
                except OSError:
                    continue
                if getattr(stat, "st_file_attributes", 0) & 0x400:
                    # FILE_ATTRIBUTE_REPARSE_POINT: never follow or count links.
                    continue
                total += int(stat.st_size)
                files += 1
            if truncated:
                break
    except OSError as exc:
        error = f"{root}: {type(exc).__name__}"

    return (
        JunkRoot(path=str(root), bytes=total, files=files, truncated=truncated, error=error),
        max(0, budget - files),
        truncated,
        error,
    )


__all__ = [
    "JunkReport",
    "JunkRoot",
    "JunkScanner",
    "JunkScannerPort",
    "NullJunkScanner",
    "default_junk_roots",
]
