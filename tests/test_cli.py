"""Self-check and CLI behaviour against the real composition root (fake ops)."""

from __future__ import annotations

from ningx.__main__ import main
from ningx.app.context import AppContext
from ningx.app.paths import AppPaths
from ningx.cli import CheckResult, default_data_dir, format_report, run_self_check


def test_self_check_passes_with_a_clean_environment(ctx: AppContext) -> None:
    results = run_self_check(ctx)

    failures = [result for result in results if not result.ok]
    assert not failures, failures
    assert len(results) >= 10

    names = {result.name for result in results}
    for required in (
        "paths.writable",
        "database.schema",
        "action.registry",
        "policy.read_mode_blocks_write",
        "policy.agent_requires_approval",
        "policy.full_access_respects_hard_deny",
        "policy.full_access_autonomy",
        "secrets.round_trip",
        "audit.append",
        "telemetry.read_path",
        "windows.read_path",
        "windows.mutations_disabled",
    ):
        assert required in names


def test_self_check_proves_the_mutation_path_stays_closed(ctx: AppContext) -> None:
    results = {r.name: r for r in run_self_check(ctx)}
    mutation = results["windows.mutations_disabled"]
    assert mutation.ok
    assert "test double" in mutation.detail or "MutationNotAvailable" in mutation.detail


def test_self_check_writes_a_redacted_audit_event(ctx: AppContext) -> None:
    run_self_check(ctx)
    latest = ctx.audit.recent(5)[0]
    assert latest.event_type == "selfcheck.run"
    assert latest.detail["api_key"] != "x"
    assert "redacted" in str(latest.detail["api_key"]).lower()


def test_self_check_does_not_change_the_permission_mode(ctx: AppContext) -> None:
    before = ctx.permissions.current_mode()
    run_self_check(ctx)
    assert ctx.permissions.current_mode() is before


def test_report_format_lists_every_check() -> None:
    results = [
        CheckResult("first.check", True, "detail"),
        CheckResult("second.check", False, "broken"),
    ]
    report = format_report(results)
    assert "PASS  first.check" in report
    assert "FAIL  second.check" in report
    assert "1/2 checks passed" in report


def test_report_handles_an_empty_result_set() -> None:
    assert "0/0 checks passed" in format_report([])


def test_module_entry_point_prints_version() -> None:
    assert main(["--version"]) == 0


def test_module_entry_point_check_mode_returns_zero(ctx: AppContext) -> None:
    assert all(result.ok for result in run_self_check(ctx))


def test_default_data_dir_is_under_local_appdata() -> None:
    path = default_data_dir()
    assert path.name == "NingX"
    assert "NingX" in str(path)


def test_data_dir_override_is_honoured(tmp_path) -> None:
    paths = AppPaths.for_root(tmp_path / "custom")
    assert paths.database == tmp_path / "custom" / "ningx.db"
    assert paths.quarantine.parent == tmp_path / "custom"
