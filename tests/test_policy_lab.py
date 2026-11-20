"""Policy Lab viewmodel: untrusted JSON in, explained decision out."""

from __future__ import annotations

import json

import pytest

from ningx.app.context import AppContext
from ningx.contracts.enums import PermissionMode
from ningx.ui.viewmodels.policy_lab import (
    SAMPLE_PROCESS_ACTION,
    SAMPLE_STARTUP_ACTION,
    SAMPLE_TAMPERED_ACTION,
    ActionParseError,
    evaluate,
    parse_action,
)


def test_valid_payload_parses_into_a_contract() -> None:
    action = parse_action(SAMPLE_PROCESS_ACTION)
    assert action.action_type == "process_terminate"
    assert action.target.kind == "process"
    assert action.target.pid == 4242  # type: ignore[union-attr]


def test_ai_supplied_risk_field_is_a_parse_error() -> None:
    with pytest.raises(ActionParseError) as excinfo:
        parse_action(SAMPLE_TAMPERED_ACTION)
    message = str(excinfo.value)
    assert "risk" in message or "extra" in message.lower()
    assert "reversible" in message or "extra" in message.lower()


def test_invalid_json_reports_the_line() -> None:
    with pytest.raises(ActionParseError) as excinfo:
        parse_action('{"action_type": ')
    assert "invalid JSON" in str(excinfo.value)


def test_non_object_payload_is_rejected() -> None:
    with pytest.raises(ActionParseError) as excinfo:
        parse_action("[1, 2, 3]")
    assert "JSON object" in str(excinfo.value)


def test_read_mode_denies_with_mode_reason(ctx: AppContext) -> None:
    result = evaluate(ctx, SAMPLE_PROCESS_ACTION, PermissionMode.READ)
    assert result.ok
    assert result.outcome == "deny"
    assert result.blocked_at == "mode"
    assert [reason.code for reason in result.reasons] == ["mode.read_only"]
    assert not result.reversible


def test_agent_mode_requires_approval_and_plans_the_op(ctx: AppContext) -> None:
    result = evaluate(ctx, SAMPLE_PROCESS_ACTION, PermissionMode.AGENT)
    assert result.outcome == "require_approval"
    assert result.approval_required
    assert result.ops == (
        "process.terminate (exe=C:\\Program Files\\Example\\example.exe, pid=4242)",
    )


def test_full_access_autonomy_for_a_startup_entry(ctx: AppContext) -> None:
    result = evaluate(ctx, SAMPLE_STARTUP_ACTION, PermissionMode.FULL_ACCESS)
    assert result.outcome == "allow"
    assert not result.approval_required
    assert result.reversible
    assert any("registry.write_startup_approved" in op for op in result.ops)


def test_unknown_action_type_is_denied_not_crashed(ctx: AppContext) -> None:
    payload = json.loads(SAMPLE_PROCESS_ACTION)
    payload["action_type"] = "defragment_everything"
    result = evaluate(ctx, json.dumps(payload), PermissionMode.AGENT)
    assert result.ok
    assert result.outcome == "deny"
    assert "action.unknown_type" in [reason.code for reason in result.reasons]


def test_tampered_payload_is_rejected_before_policy(ctx: AppContext) -> None:
    result = evaluate(ctx, SAMPLE_TAMPERED_ACTION, PermissionMode.AGENT)
    assert not result.ok
    assert result.outcome == "invalid"
    assert result.error is not None
    assert result.reasons == ()


def test_evaluation_is_audited(ctx: AppContext) -> None:
    evaluate(ctx, SAMPLE_PROCESS_ACTION, PermissionMode.AGENT)
    latest = ctx.audit.recent(1)[0]
    assert latest.event_type == "policy.evaluated"
    assert latest.actor == "ui:policy-lab"
    assert latest.detail["mode"] == "agent"
    assert latest.detail["outcome"] == "require_approval"


def test_audit_can_be_suppressed_for_previews(ctx: AppContext) -> None:
    before = len(ctx.audit.recent(50))
    evaluate(ctx, SAMPLE_PROCESS_ACTION, PermissionMode.AGENT, audit=False)
    assert len(ctx.audit.recent(50)) == before


def test_lab_never_changes_the_saved_mode(ctx: AppContext) -> None:
    before = ctx.permissions.current_mode()
    evaluate(ctx, SAMPLE_STARTUP_ACTION, PermissionMode.FULL_ACCESS)
    assert ctx.permissions.current_mode() is before
