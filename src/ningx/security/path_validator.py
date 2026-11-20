"""Path validation.

Every path that reaches an executor — or a file scan — passes through here.
The rules are conservative on purpose:

* absolute paths only,
* no device paths, no drive-relative paths, no alternate data streams,
* no ``..`` segments even if they would normalize away,
* canonicalized with ``realpath`` so a junction into a protected directory is
  caught *after* resolution, not before,
* reparse points are refused as mutation targets.
"""

from __future__ import annotations

import ntpath
import os
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import Literal

from ningx.security.protected_targets import ProtectedTargets, is_within

_DEVICE_PREFIXES = ("\\\\.\\", "\\??\\", "\\\\?\\")
_FILE_ATTRIBUTE_REPARSE_POINT = 0x400


class PathVerdict(StrEnum):
    OK = "ok"
    DENIED = "denied"


@dataclass(frozen=True)
class PathCheck:
    verdict: PathVerdict
    canonical: str | None
    reasons: tuple[str, ...]

    @property
    def allowed(self) -> bool:
        return self.verdict is PathVerdict.OK

    @classmethod
    def deny(cls, *reasons: str) -> PathCheck:
        return cls(PathVerdict.DENIED, None, tuple(reasons))


class PathValidator:
    """Validates paths against the shipped protection policy."""

    def __init__(self, protected: ProtectedTargets, *, allow_unc: bool = False) -> None:
        self._protected = protected
        self._allow_unc = allow_unc

    def validate(
        self,
        raw_path: str,
        *,
        purpose: Literal["read", "mutation"] = "read",
        allowed_roots: tuple[Path, ...] | None = None,
        must_exist: bool | None = None,
    ) -> PathCheck:
        if must_exist is None:
            must_exist = purpose == "read"

        reasons: list[str] = []

        if not raw_path or not raw_path.strip():
            return PathCheck.deny("path.empty")

        text = raw_path.strip()
        if "\x00" in text:
            return PathCheck.deny("path.nul_byte")
        if any(ord(ch) < 0x20 for ch in text):
            return PathCheck.deny("path.control_character")
        if text.startswith(_DEVICE_PREFIXES):
            return PathCheck.deny("path.device_path")

        if text.startswith("\\\\"):
            if not self._allow_unc:
                return PathCheck.deny("path.unc_not_allowed")
            reasons.append("path.unc")

        drive, tail = ntpath.splitdrive(text)
        if not drive:
            return PathCheck.deny("path.not_absolute")
        if not tail.startswith(("\\", "/")):
            return PathCheck.deny("path.drive_relative")
        if ":" in tail:
            return PathCheck.deny("path.alternate_data_stream")

        if any(part == ".." for part in text.replace("/", "\\").split("\\")):
            return PathCheck.deny("path.traversal")

        try:
            canonical = os.path.realpath(text)
        except OSError:
            return PathCheck.deny("path.unresolvable")

        if len(canonical) < 3 or not ntpath.isabs(canonical):
            return PathCheck.deny("path.unresolvable")

        exists = Path(canonical).exists()
        if must_exist and not exists:
            return PathCheck.deny("path.not_found")

        if exists and purpose == "mutation" and _is_reparse_point(canonical):
            return PathCheck.deny("path.reparse_point")

        if allowed_roots is not None and not any(
            is_within(canonical, str(root)) for root in allowed_roots
        ):
            return PathCheck.deny("path.outside_allowed_roots")

        denial = self._protected.path_denial(canonical)
        if denial is not None:
            reasons.append(denial)
            return PathCheck(PathVerdict.DENIED, canonical, tuple(reasons))

        return PathCheck(PathVerdict.OK, canonical, tuple(reasons))


def _is_reparse_point(path: str) -> bool:
    try:
        stat_result = os.lstat(path)
    except OSError:
        return False
    attributes = getattr(stat_result, "st_file_attributes", 0)
    return bool(attributes & _FILE_ATTRIBUTE_REPARSE_POINT)


def is_within_any(path: str, roots: tuple[Path, ...]) -> bool:
    return any(is_within(path, str(root)) for root in roots)


__all__ = ["PathCheck", "PathValidator", "PathVerdict", "is_within_any"]
