"""Storage: migrations, settings, audit redaction, action records, transactions."""

from __future__ import annotations

from pathlib import Path

import pytest

from ningx.contracts.enums import PermissionMode
from ningx.contracts.time import FakeClock
from ningx.core.policy_engine import PolicyContext
from ningx.core.ports import AuditEvent
from ningx.observability.redaction import REDACTED
from ningx.security.target_assessor import TargetAssessment
from ningx.storage import db as db_module
from ningx.storage.db import Database
from ningx.storage.migrations import LATEST_VERSION
from ningx.storage.repositories.actions import SqliteActionRepository
from ningx.storage.repositories.audit import SqliteAuditSink
from ningx.storage.repositories.settings import SqliteSettingsStore
from tests.fakes import CLOCK_START, process_action


@pytest.fixture
def db(tmp_path: Path) -> Database:
    database = Database(tmp_path / "ningx-test.db")
    database.migrate()
    try:
        yield database
    finally:
        database.close()


def test_migrate_reaches_the_latest_version(db: Database) -> None:
    assert db.schema_version() == LATEST_VERSION
    assert LATEST_VERSION >= 1


def test_migrate_is_idempotent(tmp_path: Path) -> None:
    path = tmp_path / "twice.db"
    first = Database(path)
    assert first.migrate() == LATEST_VERSION
    first.close()

    second = Database(path)
    assert second.migrate() == LATEST_VERSION
    rows = second.connect().execute("SELECT COUNT(*) AS n FROM schema_migrations").fetchone()
    assert int(rows["n"]) == LATEST_VERSION
    second.close()


def test_all_declared_tables_exist(db: Database) -> None:
    expected = {
        "settings",
        "provider_configs",
        "provider_usage",
        "scan_runs",
        "system_snapshots",
        "process_observations",
        "agent_runs",
        "findings",
        "recommendations",
        "actions",
        "approval_requests",
        "approval_decisions",
        "action_results",
        "rollback_records",
        "audit_events",
        "gaming_profiles",
        "file_scan_sessions",
        "metric_aggregates",
    }
    rows = db.connect().execute("SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()
    names = {str(row["name"]) for row in rows}
    assert expected <= names


def test_settings_round_trip_and_typed_helpers(db: Database) -> None:
    clock = FakeClock(CLOCK_START)
    store = SqliteSettingsStore(db, clock=clock)

    assert store.get("missing") is None
    store.set("scanner.interval", "300")
    assert store.get("scanner.interval") == "300"
    assert store.get_int("scanner.interval", 60) == 300
    assert store.get_int("missing", 60) == 60

    store.set("not-a-number", "abc")
    assert store.get_int("not-a-number", 7) == 7

    store.set("flag", "yes")
    assert store.get_bool("flag", False) is True
    store.set("flag", "off")
    assert store.get_bool("flag", True) is False

    store.set_json("layout", {"b": 2, "a": 1})
    assert store.get_json("layout", {}) == {"a": 1, "b": 2}

    assert store.all()["scanner.interval"] == "300"
    assert store.delete("scanner.interval") is True
    assert store.delete("scanner.interval") is False


def test_settings_write_is_an_upsert(db: Database) -> None:
    store = SqliteSettingsStore(db)
    store.set("k", "1")
    store.set("k", "2")
    rows = db.connect().execute("SELECT COUNT(*) AS n FROM settings WHERE key = 'k'").fetchone()
    assert int(rows["n"]) == 1
    assert store.get("k") == "2"


def test_audit_details_are_redacted_before_storage(db: Database) -> None:
    sink = SqliteAuditSink(db, clock=FakeClock(CLOCK_START))
    sink.append(
        AuditEvent(
            actor="user",
            event_type="provider.configured",
            subject_id="gemini",
            detail={
                "api_key": "plain-text-value",
                "note": "Authorization: Bearer abcdef1234567890xyz",
                "model": "gemini-2.0-flash",
            },
        )
    )

    stored = sink.recent(1)[0]
    assert stored.detail["api_key"] == REDACTED
    assert "abcdef1234567890" not in stored.detail["note"]
    assert stored.detail["model"] == "gemini-2.0-flash"

    raw = db.connect().execute("SELECT detail_json FROM audit_events").fetchone()
    assert "plain-text-value" not in str(raw["detail_json"])
    assert "abcdef1234567890" not in str(raw["detail_json"])


def test_audit_search_filters_by_actor_and_type(db: Database) -> None:
    sink = SqliteAuditSink(db)
    sink.append(AuditEvent(actor="user", event_type="mode.changed"))
    sink.append(AuditEvent(actor="agent:ram", event_type="finding.created"))
    sink.append(AuditEvent(actor="user", event_type="finding.created"))

    assert len(sink.search(actor="user")) == 2
    assert len(sink.search(event_type="finding.created")) == 2
    assert len(sink.search(actor="user", event_type="finding.created")) == 1
    assert len(sink.recent(1)) == 1


def test_action_records_capture_the_policy_decision(db: Database, policy, clock) -> None:
    repository = SqliteActionRepository(db, clock=FakeClock(CLOCK_START))
    action = process_action()
    decision = policy.evaluate(
        action,
        PolicyContext(mode=PermissionMode.READ, now=clock()),
        TargetAssessment.allow(),
    )

    record = repository.record(action, decision)
    assert record.state == "policy_blocked"
    assert record.risk == "LOW"

    recent = repository.recent(5)
    assert len(recent) == 1
    assert recent[0].action_id == str(action.action_id)
    assert recent[0].outcome == "deny"

    stored = repository.decision_for(str(action.action_id))
    assert stored is not None
    assert stored["outcome"] == "deny"
    assert "mode.read_only" in [reason["code"] for reason in stored["reasons"]]
    assert repository.count_by_outcome() == {"policy_blocked": 1}


def test_transaction_rolls_back_on_error(db: Database) -> None:
    store = SqliteSettingsStore(db)
    store.set("committed", "yes")

    with pytest.raises(RuntimeError), db.transaction() as tx:
        tx.execute(
            "INSERT INTO settings (key, value, updated_at) VALUES ('rolled-back', 'x', 'now')"
        )
        raise RuntimeError("boom")

    assert store.get("committed") == "yes"
    assert store.get("rolled-back") is None


def test_migration_failure_is_wrapped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(_self: Database, migration: db_module.Migration) -> None:
        raise db_module.MigrationError(f"migration {migration.version} failed")

    database = Database(tmp_path / "broken.db")
    monkeypatch.setattr(Database, "_apply", broken)
    with pytest.raises(db_module.MigrationError):
        database.migrate()
    database.close()


def test_closed_database_refuses_new_connections(tmp_path: Path) -> None:
    database = Database(tmp_path / "closed.db")
    database.migrate()
    database.close()
    with pytest.raises(RuntimeError, match="closed"):
        database.connect()
