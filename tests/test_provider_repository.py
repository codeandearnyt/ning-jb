"""Provider configuration and usage storage against the real schema.

The point of using the real database here is that the column mapping, the
upsert, the cascade and the NULL semantics of a missing token count are all
exercised rather than assumed.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from ningx.app.context import AppContext
from ningx.contracts.ai import (
    ConnectionResult,
    ErrorClass,
    ProviderConfig,
    TokenUsage,
    UsageSource,
)
from ningx.storage.repositories.providers import (
    MIN_SAMPLES_FOR_P95,
    FakeProviderRepository,
    SqliteProviderRepository,
)

SECRET_VALUE = "test-secret-value-that-must-never-be-stored"  # noqa: S105

START = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)


def config(**overrides: object) -> ProviderConfig:
    base: dict[str, object] = {
        "provider_id": "gemini",
        "name": "Gemini",
        "kind": "gemini",
        "model_id": "gemini-2.5-flash",
        "secret_ref": "provider/gemini",
        "timeout_s": 45.0,
        "max_retries": 3,
        "priority": 10,
        "fallback_ok": True,
        "extra": {"note": "primary"},
    }
    base.update(overrides)
    return ProviderConfig.model_validate(base)


@pytest.fixture
def repo(ctx: AppContext) -> SqliteProviderRepository:
    return SqliteProviderRepository(ctx.db)


def test_a_configuration_round_trips_through_storage(repo: SqliteProviderRepository) -> None:
    original = config()
    repo.save(original)

    loaded = repo.get("gemini")
    assert loaded is not None
    assert loaded.name == "Gemini"
    assert loaded.kind == "gemini"
    assert loaded.model_id == "gemini-2.5-flash"
    assert loaded.secret_ref == "provider/gemini"  # noqa: S105
    assert loaded.timeout_s == 45.0
    assert loaded.max_retries == 3
    assert loaded.priority == 10
    assert loaded.fallback_ok is True
    assert loaded.extra == {"note": "primary"}


def test_saving_twice_updates_rather_than_duplicating(
    repo: SqliteProviderRepository, ctx: AppContext
) -> None:
    repo.save(config())
    repo.save(config(name="Gemini (edited)", priority=5))

    rows = ctx.db.connect().execute("SELECT COUNT(*) AS n FROM provider_configs").fetchone()
    assert int(rows["n"]) == 1
    loaded = repo.get("gemini")
    assert loaded is not None and loaded.name == "Gemini (edited)"
    assert loaded.priority == 5


def test_listing_orders_by_priority_then_name(repo: SqliteProviderRepository) -> None:
    repo.save(config(provider_id="b", name="Bravo", priority=20))
    repo.save(config(provider_id="a", name="Alpha", priority=10))
    repo.save(config(provider_id="c", name="Charlie", priority=10))

    assert [item.provider_id for item in repo.list_all()] == ["a", "c", "b"]


def test_an_unknown_provider_reads_as_none(repo: SqliteProviderRepository) -> None:
    assert repo.get("nope") is None


def test_enabling_and_disabling_is_reported_truthfully(repo: SqliteProviderRepository) -> None:
    repo.save(config())
    assert repo.set_enabled("gemini", False) is True
    loaded = repo.get("gemini")
    assert loaded is not None and loaded.enabled is False
    assert repo.set_enabled("missing", True) is False


def test_deleting_a_provider_removes_its_usage_rows(
    repo: SqliteProviderRepository, ctx: AppContext
) -> None:
    repo.save(config())
    repo.record_usage(
        "gemini",
        request_kind="generate",
        model="gemini-2.5-flash",
        usage=TokenUsage(input_tokens=10, output_tokens=5, source=UsageSource.PROVIDER),
        latency_ms=120.0,
        status="ok",
    )

    assert repo.delete("gemini") is True
    rows = ctx.db.connect().execute("SELECT COUNT(*) AS n FROM provider_usage").fetchone()
    assert int(rows["n"]) == 0
    assert repo.delete("gemini") is False


def test_a_connection_test_records_when_and_how_it_went(repo: SqliteProviderRepository) -> None:
    repo.save(config())
    repo.record_test("gemini", ConnectionResult(ok=True, detail="2 models", models_seen=2))

    loaded = repo.get("gemini")
    assert loaded is not None
    assert loaded.last_test_at is not None
    assert loaded.last_test_status == "ok"


def test_a_failed_connection_test_records_the_error_class(repo: SqliteProviderRepository) -> None:
    repo.save(config())
    repo.record_test(
        "gemini",
        ConnectionResult(ok=False, detail="bad key", error_class=ErrorClass.AUTH),
    )
    loaded = repo.get("gemini")
    assert loaded is not None and loaded.last_test_status == "auth"


def test_reported_usage_is_stored_as_reported(repo: SqliteProviderRepository) -> None:
    repo.save(config())
    repo.record_usage(
        "gemini",
        request_kind="generate",
        model="gemini-2.5-flash",
        usage=TokenUsage(input_tokens=120, output_tokens=47, source=UsageSource.PROVIDER),
        latency_ms=310.0,
        status="ok",
    )

    rows = repo.recent_usage("gemini")
    assert len(rows) == 1
    assert rows[0].usage.source is UsageSource.PROVIDER
    assert rows[0].usage.total == 167
    assert rows[0].latency_ms == 310.0


def test_a_missing_token_count_is_stored_as_null_not_zero(
    repo: SqliteProviderRepository, ctx: AppContext
) -> None:
    repo.save(config())
    repo.record_usage(
        "gemini",
        request_kind="generate",
        model="gemini-2.5-flash",
        usage=TokenUsage(),
        latency_ms=None,
        status="ok",
    )

    row = ctx.db.connect().execute(
        "SELECT input_tokens, output_tokens, usage_source FROM provider_usage"
    ).fetchone()
    assert row["input_tokens"] is None
    assert row["output_tokens"] is None
    assert row["usage_source"] == "unavailable"


def test_the_summary_separates_measured_from_missing_usage(
    repo: SqliteProviderRepository,
) -> None:
    repo.save(config())
    for index in range(3):
        repo.record_usage(
            "gemini",
            request_kind="generate",
            model="gemini-2.5-flash",
            usage=TokenUsage(
                input_tokens=10, output_tokens=2, source=UsageSource.PROVIDER
            ),
            latency_ms=100.0 + index,
            status="ok",
        )
    repo.record_usage(
        "gemini",
        request_kind="generate",
        model="gemini-2.5-flash",
        usage=TokenUsage(),
        latency_ms=90.0,
        status="error",
        error_class="rate_limit",
    )

    summary = repo.usage_summary("gemini")
    assert summary.requests == 4
    assert summary.successes == 3
    assert summary.errors == 1
    assert summary.with_usage == 3
    assert summary.without_usage == 1
    assert summary.input_tokens == 30
    assert summary.output_tokens == 6
    assert summary.last_error_class == "rate_limit"
    assert summary.success_rate == 0.75


def test_an_empty_summary_reports_no_rate_rather_than_perfect_health(
    repo: SqliteProviderRepository,
) -> None:
    summary = repo.usage_summary("gemini")
    assert summary.requests == 0
    assert summary.success_rate is None
    assert summary.median_latency_ms is None
    assert summary.p95_latency_ms is None


def test_p95_is_withheld_until_there_are_enough_samples(
    repo: SqliteProviderRepository,
) -> None:
    repo.save(config())
    for index in range(MIN_SAMPLES_FOR_P95 - 1):
        repo.record_usage(
            "gemini",
            request_kind="generate",
            model="m",
            usage=TokenUsage(),
            latency_ms=float(index + 1),
            status="ok",
        )

    assert repo.usage_summary("gemini").p95_latency_ms is None

    repo.record_usage(
        "gemini",
        request_kind="generate",
        model="m",
        usage=TokenUsage(),
        latency_ms=100.0,
        status="ok",
    )
    summary = repo.usage_summary("gemini")
    assert summary.p95_latency_ms is not None
    assert summary.p95_is_available
    assert summary.latency_samples == MIN_SAMPLES_FOR_P95


def test_the_median_is_reported_as_soon_as_there_is_one_sample(
    repo: SqliteProviderRepository,
) -> None:
    repo.save(config())
    for latency in (100.0, 300.0, 200.0):
        repo.record_usage(
            "gemini",
            request_kind="generate",
            model="m",
            usage=TokenUsage(),
            latency_ms=latency,
            status="ok",
        )
    assert repo.usage_summary("gemini").median_latency_ms == 200.0


def test_the_secret_value_is_never_written_to_the_database(
    repo: SqliteProviderRepository, ctx: AppContext
) -> None:
    ctx.secrets.set("provider/gemini", SECRET_VALUE)
    repo.save(config())
    repo.record_usage(
        "gemini",
        request_kind="generate",
        model="gemini-2.5-flash",
        usage=TokenUsage(input_tokens=1, source=UsageSource.PROVIDER),
        latency_ms=10.0,
        status="ok",
    )

    dump = "\n".join(
        str(value)
        for row in ctx.db.connect().execute("SELECT * FROM provider_configs").fetchall()
        for value in tuple(row)
    )
    usage_dump = "\n".join(
        str(value)
        for row in ctx.db.connect().execute("SELECT * FROM provider_usage").fetchall()
        for value in tuple(row)
    )
    assert SECRET_VALUE not in dump
    assert SECRET_VALUE not in usage_dump
    assert "provider/gemini" in dump


def test_the_fake_repository_agrees_with_the_real_one_on_summaries(
    repo: SqliteProviderRepository,
) -> None:
    fake = FakeProviderRepository()
    fake.save(config())
    repo.save(config())

    for latency, status in ((100.0, "ok"), (200.0, "ok"), (300.0, "error")):
        usage = TokenUsage(input_tokens=10, output_tokens=5, source=UsageSource.PROVIDER)
        repo.record_usage(
            "gemini",
            request_kind="generate",
            model="m",
            usage=usage,
            latency_ms=latency,
            status=status,
            error_class=None if status == "ok" else "server",
        )
        fake.record_usage(
            "gemini",
            request_kind="generate",
            model="m",
            usage=usage,
            latency_ms=latency,
            status=status,
            error_class=None if status == "ok" else "server",
        )

    real = repo.usage_summary("gemini")
    mirrored = fake.usage_summary("gemini")
    assert (real.requests, real.successes, real.errors) == (
        mirrored.requests,
        mirrored.successes,
        mirrored.errors,
    )
    assert (real.input_tokens, real.output_tokens) == (
        mirrored.input_tokens,
        mirrored.output_tokens,
    )
    assert real.median_latency_ms == mirrored.median_latency_ms


def test_the_fake_records_a_connection_test_like_the_real_one() -> None:
    fake = FakeProviderRepository()
    fake.save(config())
    fake.record_test(
        "gemini",
        ConnectionResult(ok=False, detail="bad", error_class=ErrorClass.AUTH),
        at=START,
    )

    loaded = fake.get("gemini")
    assert loaded is not None
    assert loaded.last_test_status == "auth"


