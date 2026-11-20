"""Settings repository.

Only non-secret configuration lives here. API keys belong in
:mod:`ningx.security.secret_store`.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from datetime import datetime
from typing import Any

from ningx.contracts.time import utcnow
from ningx.storage.db import Database


class SqliteSettingsStore:
    def __init__(self, db: Database, clock: Callable[[], datetime] = utcnow) -> None:
        self._db = db
        self._clock = clock

    def get(self, key: str) -> str | None:
        row = self._db.connect().execute(
            "SELECT value FROM settings WHERE key = ?", (key,)
        ).fetchone()
        return None if row is None else str(row["value"])

    def set(self, key: str, value: str) -> None:
        if not key:
            raise ValueError("settings key must not be empty")
        self._db.connect().execute(
            """
            INSERT INTO settings (key, value, updated_at) VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                           updated_at = excluded.updated_at
            """,
            (key, value, self._clock().isoformat()),
        )

    def delete(self, key: str) -> bool:
        cursor = self._db.connect().execute("DELETE FROM settings WHERE key = ?", (key,))
        return cursor.rowcount > 0

    def all(self) -> dict[str, str]:
        rows = self._db.connect().execute("SELECT key, value FROM settings").fetchall()
        return {str(row["key"]): str(row["value"]) for row in rows}

    # ------------------------------------------------------------- typed helpers

    def get_int(self, key: str, default: int) -> int:
        raw = self.get(key)
        if raw is None:
            return default
        try:
            return int(raw)
        except ValueError:
            return default

    def get_float(self, key: str, default: float) -> float:
        raw = self.get(key)
        if raw is None:
            return default
        try:
            return float(raw)
        except ValueError:
            return default

    def get_bool(self, key: str, default: bool) -> bool:
        raw = self.get(key)
        if raw is None:
            return default
        return raw.strip().lower() in {"1", "true", "yes", "on"}

    def set_bool(self, key: str, value: bool) -> None:
        self.set(key, "true" if value else "false")

    def get_json(self, key: str, default: Any) -> Any:
        raw = self.get(key)
        if raw is None:
            return default
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return default

    def set_json(self, key: str, value: Any) -> None:
        self.set(key, json.dumps(value, sort_keys=True))


__all__ = ["SqliteSettingsStore"]
