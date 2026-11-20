"""Process identity validation: PID reuse, protection, identity drift."""

from __future__ import annotations

from ningx.security.process_validator import ProcessValidator
from tests.fakes import make_facts


def test_matching_identity_passes(process_validator: ProcessValidator) -> None:
    check = process_validator.validate(pid=4242, create_time=1000.0)
    assert check.ok, check.reasons
    assert check.facts is not None
    assert check.facts.name == "example.exe"


def test_missing_process_is_blocked(process_validator: ProcessValidator) -> None:
    check = process_validator.validate(pid=9999, create_time=1.0)
    assert not check.ok
    assert check.reasons == ("process.not_found",)


def test_reused_pid_is_blocked(process_validator: ProcessValidator) -> None:
    check = process_validator.validate(pid=4242, create_time=2000.0)
    assert not check.ok
    assert "process.pid_reused" in check.reasons


def test_changed_executable_is_blocked(process_validator: ProcessValidator) -> None:
    check = process_validator.validate(
        pid=4242, create_time=1000.0, executable=r"C:\Other\impostor.exe"
    )
    assert not check.ok
    assert "process.executable_changed" in check.reasons


def test_protected_system_process_is_blocked(process_validator: ProcessValidator) -> None:
    check = process_validator.validate(pid=2000, create_time=1000.0)
    assert not check.ok
    assert "target.protected_process" in check.reasons


def test_security_product_is_blocked(process_validator: ProcessValidator) -> None:
    check = process_validator.validate(pid=2001, create_time=1000.0)
    assert not check.ok
    assert "target.security_product" in check.reasons


def test_session_zero_process_is_blocked(process_validator: ProcessValidator) -> None:
    check = process_validator.validate(pid=2002, create_time=1000.0)
    assert not check.ok
    assert "target.session_zero" in check.reasons


def test_self_and_ancestors_are_blocked(process_validator: ProcessValidator) -> None:
    self_check = process_validator.validate(pid=1000, create_time=1000.0)
    assert self_check.reasons == ("process.self",)

    ancestor_check = process_validator.validate(pid=900, create_time=1000.0)
    assert ancestor_check.reasons == ("process.ancestor",)


def test_unsigned_process_is_flagged_but_not_blocked(
    process_validator: ProcessValidator,
) -> None:
    check = process_validator.validate(pid=4243, create_time=1000.0)
    assert check.ok
    assert "process.unsigned" in check.flags


def test_other_user_process_is_flagged(process_validator: ProcessValidator) -> None:
    check = process_validator.validate(pid=2003, create_time=1000.0)
    assert check.ok
    assert "process.other_user" in check.flags


def test_unknown_signature_state_is_not_treated_as_signed(
    process_validator: ProcessValidator,
) -> None:
    probe = process_validator._probe
    probe.add(make_facts(7777, "unknown.exe", is_signed=None))  # type: ignore[attr-defined]
    check = process_validator.validate(pid=7777, create_time=1000.0)
    assert check.ok
    assert check.facts is not None
    assert check.facts.is_signed is None
