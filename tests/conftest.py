"""Test fixtures.

Every fixture points at a temporary database, a fake process table and a fake
operating system. No test may inspect or modify the real machine.
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

from ningx.app.bootstrap import BuildOptions, build_context
from ningx.app.context import AppContext
from ningx.app.paths import AppPaths
from ningx.contracts.enums import PermissionMode
from ningx.contracts.time import FakeClock
from ningx.core.action_registry import ActionRegistry, build_default_registry
from ningx.core.policy_engine import PolicyContext, PolicyEngine
from ningx.security.path_validator import PathValidator
from ningx.security.process_validator import FakeProcessProbe, ProcessValidator
from ningx.security.protected_targets import ProtectedTargets
from ningx.security.secret_store import InMemorySecretStore
from ningx.telemetry.sampler import FakeSampler
from ningx.winapi.ops import FakeWindowsOps
from tests.fakes import CLOCK_START, sample_processes
from tests.telemetry_fakes import make_sample

CLOCK = FakeClock(CLOCK_START)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(CLOCK_START)


@pytest.fixture
def app_paths(tmp_path: Path) -> AppPaths:
    paths = AppPaths.for_root(tmp_path / "appdata")
    paths.ensure()
    return paths


@pytest.fixture
def probe() -> FakeProcessProbe:
    return FakeProcessProbe(
        sample_processes(),
        current_pid=1000,
        current_username="dev\\user",
        ancestor_pids=(1, 2, 900),
    )


@pytest.fixture
def fake_ops() -> FakeWindowsOps:
    ops = FakeWindowsOps()
    for pid, facts in sample_processes().items():
        ops.processes[pid] = facts
    return ops


@pytest.fixture
def ctx(
    app_paths: AppPaths,
    probe: FakeProcessProbe,
    fake_ops: FakeWindowsOps,
    clock: FakeClock,
) -> Iterator[AppContext]:
    context = build_context(
        BuildOptions(
            paths=app_paths,
            use_fake_ops=True,
            console_log=False,
            probe=probe,
            ops=fake_ops,
            secret_store=InMemorySecretStore(),
            sampler=FakeSampler([make_sample()]),
            clock=clock,
        )
    )
    try:
        yield context
    finally:
        context.db.close()


@pytest.fixture
def registry() -> ActionRegistry:
    return build_default_registry()


@pytest.fixture
def policy(registry: ActionRegistry) -> PolicyEngine:
    return PolicyEngine(registry)


@pytest.fixture
def sandbox(tmp_path: Path) -> tuple[ProtectedTargets, PathValidationFixture]:
    """A protected-target policy rooted in temporary directories."""
    protected_root = tmp_path / "Windows"
    exception_root = protected_root / "Temp"
    temp_root = tmp_path / "UserTemp"
    app_root = tmp_path / "AppData"
    for directory in (protected_root, exception_root, temp_root, app_root):
        directory.mkdir(parents=True, exist_ok=True)

    protected = ProtectedTargets(
        directory_roots=(protected_root, app_root),
        directory_exceptions=(exception_root,),
        process_roots=(protected_root,),
        quarantine_roots=(temp_root, exception_root),
    )
    fixture = PathValidationFixture(
        protected=protected,
        protected_root=protected_root,
        exception_root=exception_root,
        temp_root=temp_root,
        app_root=app_root,
    )
    return protected, fixture


class PathValidationFixture:
    def __init__(
        self,
        *,
        protected: ProtectedTargets,
        protected_root: Path,
        exception_root: Path,
        temp_root: Path,
        app_root: Path,
    ) -> None:
        self.protected = protected
        self.protected_root = protected_root
        self.exception_root = exception_root
        self.temp_root = temp_root
        self.app_root = app_root

    def validator(self, *, allow_unc: bool = False) -> PathValidator:
        return PathValidator(self.protected, allow_unc=allow_unc)


@pytest.fixture
def validator(sandbox: tuple[ProtectedTargets, PathValidationFixture]) -> PathValidator:
    _, fixture = sandbox
    return fixture.validator()


@pytest.fixture
def process_validator(
    probe: FakeProcessProbe, sandbox: tuple[ProtectedTargets, PathValidationFixture]
) -> ProcessValidator:
    protected, _ = sandbox
    return ProcessValidator(probe, protected)


@pytest.fixture
def read_ctx(clock: FakeClock) -> PolicyContext:
    return PolicyContext(mode=PermissionMode.READ, now=clock())


@pytest.fixture
def agent_ctx(clock: FakeClock) -> PolicyContext:
    return PolicyContext(mode=PermissionMode.AGENT, now=clock())


@pytest.fixture
def full_ctx(clock: FakeClock) -> PolicyContext:
    return PolicyContext(mode=PermissionMode.FULL_ACCESS, now=clock())


__all__ = ["CLOCK", "PathValidationFixture"]
