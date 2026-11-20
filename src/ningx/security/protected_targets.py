"""Protected targets: what the application will refuse to touch, always.

Precedence inside this module is: specific exception first, then protected root.
That is what makes ``%WINDIR%\\Temp`` cleanable while ``%WINDIR%`` stays off
limits — and why the ordering is implemented once, here, instead of in each
optimizer.
"""

from __future__ import annotations

import ntpath
import os
from dataclasses import dataclass, field, replace
from pathlib import Path

from ningx.security.protected_data import (
    PROTECTED_DIRECTORY_TEMPLATES,
    PROTECTED_PROCESS_NAMES,
    PROTECTED_REGISTRY_ROOTS,
    QUARANTINE_EXCEPTION_TEMPLATES,
    QUARANTINE_ROOT_TEMPLATES,
    SECURITY_VENDOR_MARKERS,
)


def normalize_for_compare(path: str) -> str:
    """Canonical form used for every protected-path comparison."""
    return ntpath.normcase(ntpath.normpath(path))


def is_within(child: str, root: str) -> bool:
    """True when ``child`` equals ``root`` or lives beneath it."""
    child_n = normalize_for_compare(child)
    root_n = normalize_for_compare(root)
    if child_n == root_n:
        return True
    prefix = root_n if root_n.endswith("\\") else root_n + "\\"
    return child_n.startswith(prefix)


_ENV_ALIASES: dict[str, tuple[str, ...]] = {
    "SYSTEMROOT": ("SystemRoot", "WINDIR"),
    "PROGRAMFILES": ("ProgramFiles", "ProgramW6432"),
    "PROGRAMFILES_X86": ("ProgramFiles(x86)",),
    "PROGRAMDATA": ("ProgramData", "ALLUSERSPROFILE"),
    "SYSTEMDRIVE": ("SystemDrive",),
    "LOCALAPPDATA": ("LOCALAPPDATA",),
    "TEMP": ("TEMP", "TMP"),
}


def _resolve(base: str, relative: str) -> Path | None:
    for alias in _ENV_ALIASES.get(base, ()):
        value = os.environ.get(alias)
        if value:
            root = Path(value)
            return root / relative if relative else root
    return None


def _resolve_all(templates: tuple[tuple[str, str], ...]) -> tuple[Path, ...]:
    resolved: list[Path] = []
    seen: set[str] = set()
    for base, relative in templates:
        path = _resolve(base, relative)
        if path is None:
            continue
        key = normalize_for_compare(str(path))
        if key not in seen:
            seen.add(key)
            resolved.append(path)
    return tuple(resolved)


@dataclass(frozen=True)
class ProtectedTargets:
    """Immutable protected-target policy."""

    process_names: frozenset[str] = field(default_factory=lambda: PROTECTED_PROCESS_NAMES)
    vendor_markers: tuple[str, ...] = field(default_factory=lambda: SECURITY_VENDOR_MARKERS)
    directory_roots: tuple[Path, ...] = ()
    directory_exceptions: tuple[Path, ...] = ()
    # Checked before exceptions. The application's own data directory lives here:
    # no exception may ever reopen it for deletion or quarantine.
    always_denied_roots: tuple[Path, ...] = ()
    process_roots: tuple[Path, ...] = ()
    registry_roots: tuple[tuple[str, str], ...] = field(
        default_factory=lambda: PROTECTED_REGISTRY_ROOTS
    )
    quarantine_roots: tuple[Path, ...] = ()

    # ------------------------------------------------------------------ processes

    def process_denial(
        self,
        *,
        name: str | None,
        exe: str | None = None,
        publisher: str | None = None,
        session_id: int | None = None,
    ) -> str | None:
        lowered = (name or "").lower()
        if lowered and lowered in self.process_names:
            return "target.protected_process"

        haystack = " ".join(part for part in (lowered, (publisher or "").lower()) if part)
        if haystack and any(marker in haystack for marker in self.vendor_markers):
            return "target.security_product"

        if session_id == 0:
            return "target.session_zero"

        if exe:
            for root in self.process_roots:
                if is_within(exe, str(root)):
                    return "target.protected_directory"
        return None

    # ---------------------------------------------------------------------- paths

    def path_denial(self, canonical: str) -> str | None:
        for root in self.always_denied_roots:
            if is_within(canonical, str(root)):
                return "target.protected_directory"
        for exception in self.directory_exceptions:
            if is_within(canonical, str(exception)):
                return None
        for root in self.directory_roots:
            if is_within(canonical, str(root)):
                return "target.protected_directory"
        return None

    def is_quarantine_root(self, canonical: str) -> bool:
        return any(is_within(canonical, str(root)) for root in self.quarantine_roots)

    # ------------------------------------------------------------------- registry

    def registry_denial(self, hive: str, key_path: str) -> str | None:
        hive_u = hive.upper()
        key_n = key_path.strip("\\").lower()
        for root_hive, root_key in self.registry_roots:
            if root_hive.upper() != hive_u:
                continue
            root_n = root_key.strip("\\").lower()
            if key_n == root_n or key_n.startswith(root_n + "\\"):
                return "target.protected_registry"
        return None

    # ------------------------------------------------------------------ extension

    def extended_with(self, extra_processes: set[str]) -> ProtectedTargets:
        """Return a copy with additional protected process names (never fewer)."""
        merged = self.process_names | frozenset(p.lower() for p in extra_processes)
        return replace(self, process_names=merged)


def default_protected_targets(*, app_data_dir: Path | None = None) -> ProtectedTargets:
    """Build the shipped defaults, optionally protecting the app's own data dir."""
    directories = list(_resolve_all(PROTECTED_DIRECTORY_TEMPLATES))

    system_root = _resolve("SYSTEMROOT", "")
    process_roots: tuple[Path, ...] = (system_root,) if system_root is not None else ()

    return ProtectedTargets(
        directory_roots=tuple(_dedupe_paths(directories)),
        directory_exceptions=_resolve_all(QUARANTINE_EXCEPTION_TEMPLATES),
        always_denied_roots=(app_data_dir,) if app_data_dir is not None else (),
        process_roots=process_roots,
        quarantine_roots=_resolve_all(QUARANTINE_ROOT_TEMPLATES),
    )


def _dedupe_paths(paths: list[Path]) -> list[Path]:
    seen: set[str] = set()
    ordered: list[Path] = []
    for path in paths:
        key = normalize_for_compare(str(path))
        if key not in seen:
            seen.add(key)
            ordered.append(path)
    return ordered


__all__ = [
    "ProtectedTargets",
    "default_protected_targets",
    "is_within",
    "normalize_for_compare",
]
