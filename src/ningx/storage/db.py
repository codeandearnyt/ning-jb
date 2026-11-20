"""SQLite access layer.

One connection per thread, WAL journaling, explicit transactions. All action
state transitions later run inside ``BEGIN IMMEDIATE`` so two windows cannot race
the same approval into execution twice.
"""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from contextlib import contextmanager, suppress
from datetime import UTC, datetime
from pathlib import Path

from ningx.storage.migrations import MIGRATIONS, Migration


class MigrationError(RuntimeError):
    pass


class Database:
    def __init__(self, path: Path | str) -> None:
        self._path = str(path)
        self._local = threading.local()
        self._closed = False
        if self._path != ":memory:":
            Path(self._path).parent.mkdir(parents=True, exist_ok=True)

    @property
    def path(self) -> str:
        return self._path

    def connect(self) -> sqlite3.Connection:
        if self._closed:
            raise RuntimeError("database is closed")
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is None:
            connection = sqlite3.connect(
                self._path,
                timeout=5.0,
                isolation_level=None,
                check_same_thread=True,
            )
            connection.row_factory = sqlite3.Row
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA busy_timeout = 5000")
            if self._path != ":memory:":
                connection.execute("PRAGMA journal_mode = WAL")
                connection.execute("PRAGMA synchronous = NORMAL")
            self._local.connection = connection
        return connection

    @contextmanager
    def transaction(self, *, immediate: bool = False) -> Iterator[sqlite3.Connection]:
        connection = self.connect()
        connection.execute("BEGIN IMMEDIATE" if immediate else "BEGIN")
        try:
            yield connection
        except BaseException:
            connection.execute("ROLLBACK")
            raise
        connection.execute("COMMIT")

    def migrate(self) -> int:
        connection = self.connect()
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS schema_migrations (
                version INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                applied_at TEXT NOT NULL
            )
            """
        )
        applied = self.schema_version()
        for migration in MIGRATIONS:
            if migration.version <= applied:
                continue
            self._apply(migration)
        return self.schema_version()

    def _apply(self, migration: Migration) -> None:
        try:
            with self.transaction(immediate=True) as tx:
                for statement in migration.statements:
                    tx.execute(statement)
                tx.execute(
                    "INSERT INTO schema_migrations (version, name, applied_at) VALUES (?, ?, ?)",
                    (migration.version, migration.name, datetime.now(UTC).isoformat()),
                )
        except sqlite3.Error as exc:
            raise MigrationError(
                f"migration {migration.version} ({migration.name}) failed: {exc}"
            ) from exc

    def schema_version(self) -> int:
        connection = self.connect()
        row = connection.execute("SELECT MAX(version) AS version FROM schema_migrations").fetchone()
        if row is None or row["version"] is None:
            return 0
        return int(row["version"])

    def close(self) -> None:
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is not None:
            connection.close()
            self._local.connection = None
        self._closed = True

    def close_thread_connection(self) -> None:
        """Close the connection owned by the calling thread only.

        The engine thread opens its own connection; it must release that
        connection before the thread exits without closing the database for the
        UI thread.
        """
        connection: sqlite3.Connection | None = getattr(self._local, "connection", None)
        if connection is None:
            return
        with suppress(sqlite3.Error):
            connection.close()
        self._local.connection = None


__all__ = ["Database", "MigrationError"]
