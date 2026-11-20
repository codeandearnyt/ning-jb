"""Windows adaptation layer."""

from __future__ import annotations

from ningx.winapi.ops import (
    FakeWindowsOps,
    MutationNotAvailable,
    RealWindowsOps,
    RegistryValue,
    ToolResult,
    WindowsOps,
    quarantine_destination,
)

__all__ = [
    "FakeWindowsOps",
    "MutationNotAvailable",
    "RealWindowsOps",
    "RegistryValue",
    "ToolResult",
    "WindowsOps",
    "quarantine_destination",
]
