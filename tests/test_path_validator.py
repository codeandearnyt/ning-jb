"""Path validation: traversal, device paths, junctions, protected roots."""

from __future__ import annotations

import ntpath
import os
import types
from pathlib import Path

import pytest

from ningx.security.path_validator import PathCheck, PathValidator
from tests.conftest import PathValidationFixture


def _touch(path: Path, content: str = "x") -> str:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return str(path)


def test_empty_path_is_denied(validator: PathValidator) -> None:
    assert validator.validate("").reasons == ("path.empty",)
    assert validator.validate("   ").reasons == ("path.empty",)


def test_nul_byte_is_denied(validator: PathValidator) -> None:
    check = validator.validate("C:\\temp\\a\x00b.txt")
    assert check.reasons == ("path.nul_byte",)


def test_device_path_is_denied(validator: PathValidator) -> None:
    assert validator.validate("\\\\.\\PhysicalDrive0").reasons == ("path.device_path",)
    assert validator.validate("\\\\?\\C:\\Windows").reasons == ("path.device_path",)
    assert validator.validate("\\??\\C:\\Windows").reasons == ("path.device_path",)


def test_unc_path_is_denied_by_default(validator: PathValidator) -> None:
    check = validator.validate(r"\\server\share\file.txt")
    assert "path.unc_not_allowed" in check.reasons


def test_unc_can_be_enabled_explicitly(
    sandbox: tuple[object, PathValidationFixture],
) -> None:
    _, fixture = sandbox
    validator = fixture.validator(allow_unc=True)
    check = validator.validate(r"\\server\share\file.txt", must_exist=False)
    assert check.reasons == ("path.unc",)
    assert check.allowed


def test_relative_and_drive_relative_paths_are_denied(validator: PathValidator) -> None:
    assert validator.validate(r"Windows\System32").reasons == ("path.not_absolute",)
    assert validator.validate("C:Windows\\System32").reasons == ("path.drive_relative",)


def test_alternate_data_stream_is_denied(
    validator: PathValidator, sandbox: tuple[object, PathValidationFixture]
) -> None:
    _, fixture = sandbox
    target = _touch(fixture.temp_root / "plain.txt")
    check = validator.validate(target + ":hidden")
    assert check.reasons == ("path.alternate_data_stream",)


def test_traversal_is_denied_even_when_it_would_normalize(
    validator: PathValidator, sandbox: tuple[object, PathValidationFixture]
) -> None:
    _, fixture = sandbox
    sneaky = str(fixture.temp_root / ".." / "Windows" / "System32" / "kernel32.dll")
    check = validator.validate(sneaky)
    assert check.reasons == ("path.traversal",)


def test_missing_file_is_denied_for_reads(
    validator: PathValidator, sandbox: tuple[object, PathValidationFixture]
) -> None:
    _, fixture = sandbox
    check = validator.validate(str(fixture.temp_root / "missing.txt"))
    assert check.reasons == ("path.not_found",)


def test_missing_destination_is_allowed_for_mutations(
    validator: PathValidator, sandbox: tuple[object, PathValidationFixture]
) -> None:
    _, fixture = sandbox
    check = validator.validate(
        str(fixture.temp_root / "not-yet-there.txt"), purpose="mutation", must_exist=False
    )
    assert check.allowed, check.reasons


def test_protected_directory_is_denied(
    validator: PathValidator, sandbox: tuple[object, PathValidationFixture]
) -> None:
    _, fixture = sandbox
    target = _touch(fixture.protected_root / "System32" / "driver.sys")
    check = validator.validate(target)
    assert check.reasons == ("target.protected_directory",)
    assert check.canonical is not None


def test_exception_inside_protected_root_is_allowed(
    validator: PathValidator, sandbox: tuple[object, PathValidationFixture]
) -> None:
    _, fixture = sandbox
    target = _touch(fixture.exception_root / "leftover.tmp")
    check = validator.validate(target)
    assert check.allowed, check.reasons


def test_app_data_directory_is_protected(
    validator: PathValidator, sandbox: tuple[object, PathValidationFixture]
) -> None:
    _, fixture = sandbox
    target = _touch(fixture.app_root / "ningx.db")
    check = validator.validate(target)
    assert check.reasons == ("target.protected_directory",)


def test_allowed_roots_are_enforced(
    validator: PathValidator, sandbox: tuple[object, PathValidationFixture]
) -> None:
    _, fixture = sandbox
    inside = _touch(fixture.temp_root / "inside.txt")
    other = _touch(fixture.app_root.parent / "elsewhere" / "outside.txt")

    assert validator.validate(inside, allowed_roots=(fixture.temp_root,)).allowed
    denied = validator.validate(other, allowed_roots=(fixture.temp_root,))
    assert "path.outside_allowed_roots" in denied.reasons


def test_reparse_point_is_refused_as_a_mutation_target(
    monkeypatch: pytest.MonkeyPatch,
    validator: PathValidator,
    sandbox: tuple[object, PathValidationFixture],
) -> None:
    _, fixture = sandbox
    target = _touch(fixture.temp_root / "junction-target.txt")
    real_lstat = os.lstat

    def fake_lstat(path: object) -> object:
        result = real_lstat(path)  # type: ignore[arg-type]
        if ntpath.normcase(str(path)) == ntpath.normcase(target):
            return types.SimpleNamespace(
                st_file_attributes=getattr(result, "st_file_attributes", 0) | 0x400
            )
        return result

    monkeypatch.setattr(os, "lstat", fake_lstat)

    read_check = validator.validate(target, purpose="read")
    assert read_check.allowed

    mutation_check = validator.validate(target, purpose="mutation")
    assert mutation_check.reasons == ("path.reparse_point",)


def test_successful_validation_returns_canonical_path(
    validator: PathValidator, sandbox: tuple[object, PathValidationFixture]
) -> None:
    _, fixture = sandbox
    target = _touch(fixture.temp_root / "canonical.txt")
    check = validator.validate(target)
    assert isinstance(check, PathCheck)
    assert check.allowed
    assert check.canonical is not None
    assert ntpath.normcase(check.canonical) == ntpath.normcase(os.path.realpath(target))
