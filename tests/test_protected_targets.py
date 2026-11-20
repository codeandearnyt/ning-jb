"""Protected targets: exception-before-root precedence and never-shrink rules."""

from __future__ import annotations

from pathlib import Path

from ningx.security.protected_targets import (
    ProtectedTargets,
    default_protected_targets,
    is_within,
)
from tests.conftest import PathValidationFixture


def test_known_system_process_is_protected(
    sandbox: tuple[ProtectedTargets, PathValidationFixture],
) -> None:
    protected, _ = sandbox
    assert protected.process_denial(name="lsass.exe") == "target.protected_process"
    assert protected.process_denial(name="LSASS.EXE") == "target.protected_process"
    assert protected.process_denial(name="explorer.exe") == "target.protected_process"


def test_security_product_is_protected_by_publisher(
    sandbox: tuple[ProtectedTargets, PathValidationFixture],
) -> None:
    protected, _ = sandbox
    assert protected.process_denial(name="shield.exe", publisher="Acme Antivirus") == (
        "target.security_product"
    )
    assert protected.process_denial(name="msmpeng.exe") == "target.protected_process"


def test_session_zero_and_system_directory_processes_are_protected(
    sandbox: tuple[ProtectedTargets, PathValidationFixture],
) -> None:
    protected, fixture = sandbox
    assert protected.process_denial(name="neutral.exe", session_id=0) == "target.session_zero"
    inside = str(fixture.protected_root / "System32" / "neutral.exe")
    assert protected.process_denial(name="neutral.exe", exe=inside) == (
        "target.protected_directory"
    )


def test_ordinary_user_application_is_not_protected(
    sandbox: tuple[ProtectedTargets, PathValidationFixture],
) -> None:
    protected, _ = sandbox
    assert (
        protected.process_denial(
            name="game.exe",
            exe=r"C:\Program Files\Steam\game.exe",
            publisher="Valve",
            session_id=1,
        )
        is None
    )


def test_exception_beats_protected_root(
    sandbox: tuple[ProtectedTargets, PathValidationFixture],
) -> None:
    protected, fixture = sandbox
    inside_exception = str(fixture.exception_root / "leftover.tmp")
    inside_protected = str(fixture.protected_root / "System32" / "kernel32.dll")
    assert protected.path_denial(inside_exception) is None
    assert protected.path_denial(inside_protected) == "target.protected_directory"


def test_path_denial_is_boundary_aware(
    sandbox: tuple[ProtectedTargets, PathValidationFixture],
) -> None:
    protected, fixture = sandbox
    sibling = fixture.protected_root.parent / "Windows-old" / "x.dll"
    assert protected.path_denial(str(sibling)) is None
    assert protected.path_denial(str(fixture.protected_root)) == "target.protected_directory"


def test_registry_boundary_is_not_a_loose_prefix(
    sandbox: tuple[ProtectedTargets, PathValidationFixture],
) -> None:
    protected, _ = sandbox
    assert protected.registry_denial("HKLM", r"SYSTEM\CurrentControlSet\Services") == (
        "target.protected_registry"
    )
    assert protected.registry_denial("HKLM", r"SYSTEMATIC\Unrelated") is None
    assert protected.registry_denial("HKCU", r"Software\NingX\Setting") is None


def test_extend_only_adds_processes(
    sandbox: tuple[ProtectedTargets, PathValidationFixture],
) -> None:
    protected, _ = sandbox
    extended = protected.extended_with({"my-custom-agent.exe"})
    assert "my-custom-agent.exe" in extended.process_names
    assert "lsass.exe" in extended.process_names
    assert len(extended.process_names) >= len(protected.process_names)
    assert "my-custom-agent.exe" not in protected.process_names


def test_default_targets_resolve_real_windows_roots() -> None:
    protected = default_protected_targets()
    # %SystemRoot% may be reported as C:\Windows or C:\WINDOWS depending on the
    # process environment block, so compare case-insensitively.
    assert any("windows" in str(root).lower() for root in protected.directory_roots)
    assert protected.quarantine_roots, "quarantine roots must resolve on Windows"


def test_default_targets_protect_the_app_data_dir(tmp_path: Path) -> None:
    app_dir = tmp_path / "NingX"
    app_dir.mkdir()
    protected = default_protected_targets(app_data_dir=app_dir)
    assert protected.path_denial(str(app_dir / "ningx.db")) == "target.protected_directory"


def test_is_within_is_case_insensitive_and_separator_safe() -> None:
    assert is_within(r"C:\Windows\Temp\a.tmp", r"c:\windows")
    assert not is_within(r"C:\Windows-old\a.tmp", r"C:\Windows")
