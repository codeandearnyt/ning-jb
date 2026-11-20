"""Application paths.

User data lives under ``%LOCALAPPDATA%\\NingX`` — deliberately *not* next to the
source tree. A live WAL database inside a OneDrive-synced folder is a corruption
risk, and a user's Documents folder is not application storage.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

APP_DIR_NAME = "NingX"


@dataclass(frozen=True)
class AppPaths:
    root: Path
    logs: Path
    database: Path
    quarantine: Path
    backups: Path
    cache: Path

    @classmethod
    def for_root(cls, root: Path) -> AppPaths:
        root = Path(root)
        return cls(
            root=root,
            logs=root / "logs",
            database=root / "ningx.db",
            quarantine=root / "quarantine",
            backups=root / "backups",
            cache=root / "cache",
        )

    @classmethod
    def default(cls) -> AppPaths:
        base = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if base:
            return cls.for_root(Path(base) / APP_DIR_NAME)
        return cls.for_root(Path.home() / f".{APP_DIR_NAME.lower()}")

    def ensure(self) -> None:
        for directory in (
            self.root,
            self.logs,
            self.quarantine,
            self.backups,
            self.cache,
        ):
            directory.mkdir(parents=True, exist_ok=True)


__all__ = ["APP_DIR_NAME", "AppPaths"]
