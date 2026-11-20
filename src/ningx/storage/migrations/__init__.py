"""Schema migrations.

Migration SQL lives in Python modules, not in loose ``.sql`` files: packaging
cannot lose it and a missing resource cannot silently skip a migration.
Migrations are append-only. Never edit an applied migration; add a new one.
"""

from __future__ import annotations

from dataclasses import dataclass

from ningx.storage.migrations.v0001_initial import INITIAL_SCHEMA


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    statements: tuple[str, ...]


MIGRATIONS: tuple[Migration, ...] = (
    Migration(version=1, name="initial", statements=INITIAL_SCHEMA),
)

LATEST_VERSION = MIGRATIONS[-1].version

__all__ = ["LATEST_VERSION", "MIGRATIONS", "Migration"]
