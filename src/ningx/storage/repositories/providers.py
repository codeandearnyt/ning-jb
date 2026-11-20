"""Provider configuration and usage storage.

Two rules shape this module:

* **The credential never passes through here.** ``secret_ref`` names an entry in
  the OS secret store; writing the value is the secret store's job and the UI's
  call. This repository would have no column to put it in.
* **Unknown usage is recorded as unknown.** ``usage_source`` defaults to
  ``unavailable``, and the summary counts those rows instead of quietly treating
  a missing token count as zero.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from statistics import median

from ningx.contracts.ai import (
    ConnectionResult,
    ErrorClass,
    ProviderConfig,
    TokenUsage,
    UsageSource,
)
from ningx.contracts.time import utcnow
from ningx.storage.db import Database

# A p95 from a handful of samples is noise wearing a statistic's clothes, so it
# is only reported once there is enough data to mean something.
MIN_SAMPLES_FOR_P95 = 20


@dataclass(frozen=True)
class UsageRecord:
    provider_id: str
    ts: datetime
    request_kind: str
    model: str | None
    usage: TokenUsage
    latency_ms: float | None
    status: str
    error_class: str | None


@dataclass(frozen=True)
class UsageSummary:
    provider_id: str
    requests: int = 0
    successes: int = 0
    errors: int = 0
    with_usage: int = 0
    without_usage: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    latency_samples: int = 0
    median_latency_ms: float | None = None
    p95_latency_ms: float | None = None
    last_error_class: str | None = None

    @property
    def success_rate(self) -> float | None:
        """``None`` when nothing has been recorded, never a made-up 100%."""
        if self.requests == 0:
            return None
        return self.successes / self.requests

    @property
    def p95_is_available(self) -> bool:
        return self.p95_latency_ms is not None


@dataclass
class FakeProviderRepository:
    """In-memory stand-in. Never touches a database or the network."""

    configs: dict[str, ProviderConfig] = field(default_factory=dict)
    records: list[UsageRecord] = field(default_factory=list)
    tests: dict[str, ConnectionResult] = field(default_factory=dict)

    def list_all(self) -> list[ProviderConfig]:
        return sorted(self.configs.values(), key=lambda item: (item.priority, item.name))

    def get(self, provider_id: str) -> ProviderConfig | None:
        return self.configs.get(provider_id)

    def save(self, config: ProviderConfig) -> None:
        self.configs[config.provider_id] = config

    def set_enabled(self, provider_id: str, enabled: bool) -> bool:
        current = self.configs.get(provider_id)
        if current is None:
            return False
        self.configs[provider_id] = current.model_copy(update={"enabled": enabled})
        return True

    def delete(self, provider_id: str) -> bool:
        self.records = [r for r in self.records if r.provider_id != provider_id]
        return self.configs.pop(provider_id, None) is not None

    def record_test(self, provider_id: str, result: ConnectionResult, *, at: datetime) -> None:
        self.tests[provider_id] = result
        current = self.configs.get(provider_id)
        if current is not None:
            status = "ok" if result.ok else (result.error_class or ErrorClass.UNKNOWN).value
            self.configs[provider_id] = current.model_copy(
                update={"last_test_at": at, "last_test_status": status}
            )

    def record_usage(
        self,
        provider_id: str,
        *,
        request_kind: str,
        model: str | None,
        usage: TokenUsage,
        latency_ms: float | None,
        status: str,
        error_class: str | None = None,
        at: datetime | None = None,
    ) -> None:
        self.records.append(
            UsageRecord(
                provider_id=provider_id,
                ts=at or utcnow(),
                request_kind=request_kind,
                model=model,
                usage=usage,
                latency_ms=latency_ms,
                status=status,
                error_class=error_class,
            )
        )

    def usage_summary(self, provider_id: str) -> UsageSummary:
        rows = [record for record in self.records if record.provider_id == provider_id]
        return _summarise(provider_id, rows)


class SqliteProviderRepository:
    def __init__(self, db: Database, clock: Callable[[], datetime] = utcnow) -> None:
        self._db = db
        self._clock = clock

    # ------------------------------------------------------------------- config

    def list_all(self) -> list[ProviderConfig]:
        rows = self._db.connect().execute(
            """
            SELECT * FROM provider_configs
            ORDER BY priority ASC, name ASC
            """
        ).fetchall()
        return [_row_to_config(row) for row in rows]

    def get(self, provider_id: str) -> ProviderConfig | None:
        row = self._db.connect().execute(
            "SELECT * FROM provider_configs WHERE id = ?", (provider_id,)
        ).fetchone()
        return None if row is None else _row_to_config(row)

    def save(self, config: ProviderConfig) -> None:
        now = self._clock().isoformat()
        self._db.connect().execute(
            """
            INSERT INTO provider_configs (
                id, name, kind, base_url, model_id, auth_scheme, extra_json, enabled,
                is_local, priority, fallback_ok, timeout_s, max_retries,
                max_output_tokens, secret_ref, last_test_at, last_test_status,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name = excluded.name,
                kind = excluded.kind,
                base_url = excluded.base_url,
                model_id = excluded.model_id,
                auth_scheme = excluded.auth_scheme,
                extra_json = excluded.extra_json,
                enabled = excluded.enabled,
                is_local = excluded.is_local,
                priority = excluded.priority,
                fallback_ok = excluded.fallback_ok,
                timeout_s = excluded.timeout_s,
                max_retries = excluded.max_retries,
                max_output_tokens = excluded.max_output_tokens,
                secret_ref = excluded.secret_ref,
                last_test_at = excluded.last_test_at,
                last_test_status = excluded.last_test_status,
                updated_at = excluded.updated_at
            """,
            (
                config.provider_id,
                config.name,
                config.kind,
                config.base_url,
                config.model_id,
                config.auth_scheme,
                json.dumps(config.extra, sort_keys=True, default=str),
                int(config.enabled),
                int(config.is_local),
                config.priority,
                int(config.fallback_ok),
                config.timeout_s,
                config.max_retries,
                config.max_output_tokens,
                config.secret_ref,
                None if config.last_test_at is None else config.last_test_at.isoformat(),
                config.last_test_status,
                now,
                now,
            ),
        )

    def set_enabled(self, provider_id: str, enabled: bool) -> bool:
        cursor = self._db.connect().execute(
            "UPDATE provider_configs SET enabled = ?, updated_at = ? WHERE id = ?",
            (int(enabled), self._clock().isoformat(), provider_id),
        )
        return cursor.rowcount > 0

    def delete(self, provider_id: str) -> bool:
        cursor = self._db.connect().execute(
            "DELETE FROM provider_configs WHERE id = ?", (provider_id,)
        )
        return cursor.rowcount > 0

    # ------------------------------------------------------------------- results

    def record_test(
        self, provider_id: str, result: ConnectionResult, *, at: datetime | None = None
    ) -> None:
        moment = at or self._clock()
        status = "ok" if result.ok else (result.error_class or ErrorClass.UNKNOWN).value
        self._db.connect().execute(
            """
            UPDATE provider_configs
            SET last_test_at = ?, last_test_status = ?, updated_at = ?
            WHERE id = ?
            """,
            (moment.isoformat(), status, self._clock().isoformat(), provider_id),
        )

    def record_usage(
        self,
        provider_id: str,
        *,
        request_kind: str,
        model: str | None,
        usage: TokenUsage,
        latency_ms: float | None,
        status: str,
        error_class: str | None = None,
        cost_micros: int | None = None,
        at: datetime | None = None,
    ) -> int:
        cursor = self._db.connect().execute(
            """
            INSERT INTO provider_usage (
                provider_id, ts, request_kind, model, input_tokens, output_tokens,
                usage_source, latency_ms, status, error_class, cost_micros
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                provider_id,
                (at or self._clock()).isoformat(),
                request_kind,
                model,
                usage.input_tokens,
                usage.output_tokens,
                usage.source.value,
                latency_ms,
                status,
                error_class,
                cost_micros,
            ),
        )
        return int(cursor.lastrowid or 0)

    # ------------------------------------------------------------------ reading

    def recent_usage(self, provider_id: str, limit: int = 50) -> list[UsageRecord]:
        rows = self._db.connect().execute(
            """
            SELECT provider_id, ts, request_kind, model, input_tokens, output_tokens,
                   usage_source, latency_ms, status, error_class
            FROM provider_usage
            WHERE provider_id = ?
            ORDER BY id DESC LIMIT ?
            """,
            (provider_id, max(1, min(limit, 500))),
        ).fetchall()
        return [_row_to_usage(row) for row in rows]

    def usage_summary(self, provider_id: str, *, limit: int = 500) -> UsageSummary:
        return _summarise(provider_id, self.recent_usage(provider_id, limit=limit))


def _summarise(provider_id: str, rows: Sequence[UsageRecord]) -> UsageSummary:
    if not rows:
        return UsageSummary(provider_id=provider_id)

    latencies = [row.latency_ms for row in rows if row.latency_ms is not None]
    with_usage = [row for row in rows if row.usage.source is UsageSource.PROVIDER]
    errors = [row for row in rows if row.status != "ok"]
    return UsageSummary(
        provider_id=provider_id,
        requests=len(rows),
        successes=len(rows) - len(errors),
        errors=len(errors),
        with_usage=len(with_usage),
        without_usage=len(rows) - len(with_usage),
        input_tokens=sum(row.usage.input_tokens or 0 for row in with_usage),
        output_tokens=sum(row.usage.output_tokens or 0 for row in with_usage),
        latency_samples=len(latencies),
        median_latency_ms=median(latencies) if latencies else None,
        p95_latency_ms=_percentile(latencies, 95),
        last_error_class=errors[0].error_class if errors else None,
    )


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if len(values) < MIN_SAMPLES_FOR_P95:
        return None
    ordered = sorted(values)
    index = min(len(ordered) - 1, round((percentile / 100.0) * (len(ordered) - 1)))
    return ordered[index]


def _row_to_config(row: object) -> ProviderConfig:
    extra = _decode_json(str(_get(row, "extra_json") or "{}"))
    return ProviderConfig(
        provider_id=str(_get(row, "id")),
        name=str(_get(row, "name")),
        kind=str(_get(row, "kind")),
        enabled=bool(_get(row, "enabled")),
        is_local=bool(_get(row, "is_local")),
        base_url=_optional_str(_get(row, "base_url")),
        model_id=_optional_str(_get(row, "model_id")),
        auth_scheme=_optional_str(_get(row, "auth_scheme")),
        timeout_s=_number(_get(row, "timeout_s"), 60.0),
        max_retries=int(_number(_get(row, "max_retries"), 0.0)),
        max_output_tokens=_optional_int(_get(row, "max_output_tokens")),
        priority=int(_number(_get(row, "priority"), 100.0)),
        fallback_ok=bool(_get(row, "fallback_ok")),
        secret_ref=_optional_str(_get(row, "secret_ref")),
        extra=extra,
        last_test_at=_parse_time(_optional_str(_get(row, "last_test_at"))),
        last_test_status=_optional_str(_get(row, "last_test_status")),
    )


def _row_to_usage(row: object) -> UsageRecord:
    source = str(_get(row, "usage_source") or "unavailable")
    return UsageRecord(
        provider_id=str(_get(row, "provider_id")),
        ts=_parse_time(str(_get(row, "ts"))) or utcnow(),
        request_kind=str(_get(row, "request_kind")),
        model=_optional_str(_get(row, "model")),
        usage=TokenUsage(
            input_tokens=_optional_int(_get(row, "input_tokens")),
            output_tokens=_optional_int(_get(row, "output_tokens")),
            source=UsageSource(source),
        ),
        latency_ms=_optional_float(_get(row, "latency_ms")),
        status=str(_get(row, "status")),
        error_class=_optional_str(_get(row, "error_class")),
    )


def _get(row: object, key: str) -> object:
    try:
        return row[key]  # type: ignore[index]
    except (KeyError, IndexError):  # pragma: no cover - schema guarantees the column
        return None


def _decode_json(raw: str) -> dict[str, object]:
    try:
        value = json.loads(raw)
    except json.JSONDecodeError:
        return {}
    return value if isinstance(value, dict) else {}


def _parse_time(raw: str | None) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError:
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


def _optional_str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _number(value: object, default: float) -> float:
    return float(value) if isinstance(value, int | float) else default


def _optional_int(value: object) -> int | None:
    return int(value) if isinstance(value, int | float) else None


def _optional_float(value: object) -> float | None:
    return float(value) if isinstance(value, int | float) else None


__all__ = [
    "MIN_SAMPLES_FOR_P95",
    "FakeProviderRepository",
    "SqliteProviderRepository",
    "UsageRecord",
    "UsageSummary",
]
