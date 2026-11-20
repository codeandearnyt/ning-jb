"""Composition root.

Everything is constructed here, once. Nothing below this module reaches for a
global, a singleton or an environment variable at import time.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta

from ningx.analysis.junk import (
    JunkScanner,
    JunkScannerPort,
    NullJunkScanner,
    default_junk_roots,
)
from ningx.analysis.runner import ScanRunner
from ningx.app.context import AppContext
from ningx.app.paths import AppPaths
from ningx.contracts.time import Clock, utcnow
from ningx.core.action_registry import build_default_registry
from ningx.core.dry_run import DryRunExecutor
from ningx.core.permission_manager import PermissionManager
from ningx.core.policy_engine import PolicyEngine
from ningx.observability.logging import configure_logging
from ningx.security.path_validator import PathValidator
from ningx.security.process_validator import ProcessProbe, ProcessValidator
from ningx.security.protected_targets import default_protected_targets
from ningx.security.secret_store import SecretStore, WindowsCredentialStore
from ningx.security.startup_collector import (
    FakeStartupCollector,
    StartupCollector,
    WinregStartupCollector,
)
from ningx.security.target_assessor import TargetAssessor
from ningx.storage.db import Database
from ningx.storage.repositories.actions import SqliteActionRepository
from ningx.storage.repositories.audit import SqliteAuditSink
from ningx.storage.repositories.findings import SqliteFindingRepository
from ningx.storage.repositories.settings import SqliteSettingsStore
from ningx.storage.repositories.telemetry import SqliteTelemetryRepository
from ningx.telemetry.engine import TelemetryEngine
from ningx.telemetry.sampler import PsutilSampler, SystemSampler
from ningx.winapi.ops import RealWindowsOps, WindowsOps


@dataclass(frozen=True)
class BuildOptions:
    paths: AppPaths
    use_fake_ops: bool = False
    log_level: int = logging.INFO
    console_log: bool = True
    secret_store: SecretStore | None = None
    ops: WindowsOps | None = None
    probe: ProcessProbe | None = None
    sampler: SystemSampler | None = None
    telemetry_interval_s: float = 2.0
    telemetry_retention_hours: float = 24.0
    startup_collector: StartupCollector | None = None
    junk_scanner: JunkScannerPort | None = None
    keep_scans: int = 50
    clock: Clock = utcnow


def build_context(options: BuildOptions) -> AppContext:
    paths = options.paths
    paths.ensure()
    logger = configure_logging(paths.logs, level=options.log_level, console=options.console_log)
    logger.info("bootstrap.start", extra={"data_root": str(paths.root)})

    db = Database(paths.database)
    try:
        version = db.migrate()
    except Exception:
        db.close()
        raise
    logger.info("bootstrap.schema", extra={"version": version})

    settings = SqliteSettingsStore(db, clock=options.clock)
    audit = SqliteAuditSink(db, clock=options.clock)
    actions = SqliteActionRepository(db, clock=options.clock)

    secrets = options.secret_store if options.secret_store is not None else _default_secrets()

    protected = default_protected_targets(app_data_dir=paths.root)
    path_validator = PathValidator(protected)

    if options.probe is not None:
        probe = options.probe
    else:
        from ningx.security.process_validator import PsutilProcessProbe

        probe = PsutilProcessProbe()

    process_validator = ProcessValidator(probe, protected)
    assessor = TargetAssessor(
        protected=protected,
        path_validator=path_validator,
        process_validator=process_validator,
    )

    registry = build_default_registry()
    permissions = PermissionManager(settings, audit, clock=options.clock)
    policy = PolicyEngine(registry)

    ops: WindowsOps
    if options.ops is not None:
        ops = options.ops
    elif options.use_fake_ops:
        from ningx.winapi.ops import FakeWindowsOps

        ops = FakeWindowsOps()
    else:
        ops = RealWindowsOps()

    sampler = options.sampler or PsutilSampler(clock=options.clock)
    telemetry_repo = SqliteTelemetryRepository(db, clock=options.clock)
    telemetry = TelemetryEngine(
        sampler,
        sink=telemetry_repo,
        interval_s=options.telemetry_interval_s,
        retention=timedelta(hours=options.telemetry_retention_hours),
        logger=logger.getChild("telemetry"),
    )

    # Scanning is read-only, but a test build must never read the real
    # registry or walk the real temp folders, so the fake ops flag also
    # selects inert collectors.
    if options.startup_collector is not None:
        startup_collector: StartupCollector = options.startup_collector
    elif options.use_fake_ops:
        startup_collector = FakeStartupCollector([])
    else:
        startup_collector = WinregStartupCollector()

    if options.junk_scanner is not None:
        junk_scanner: JunkScannerPort = options.junk_scanner
    elif options.use_fake_ops:
        junk_scanner = NullJunkScanner()
    else:
        junk_scanner = JunkScanner(default_junk_roots())

    findings_repo = SqliteFindingRepository(db, clock=options.clock)
    scanner = ScanRunner(
        findings_repo,
        startup=startup_collector,
        junk=junk_scanner,
        clock=options.clock,
        keep_scans=options.keep_scans,
    )

    return AppContext(
        paths=paths,
        db=db,
        settings=settings,
        audit=audit,
        actions=actions,
        secrets=secrets,
        protected=protected,
        registry=registry,
        permissions=permissions,
        policy=policy,
        assessor=assessor,
        dry_run=DryRunExecutor(),
        ops=ops,
        probe=probe,
        path_validator=path_validator,
        process_validator=process_validator,
        sampler=sampler,
        telemetry_repo=telemetry_repo,
        telemetry=telemetry,
        findings_repo=findings_repo,
        startup_collector=startup_collector,
        junk_scanner=junk_scanner,
        scanner=scanner,
        clock=options.clock,
        logger=logger,
    )


def _default_secrets() -> SecretStore:
    try:
        return WindowsCredentialStore()
    except Exception:
        from ningx.security.secret_store import InMemorySecretStore

        return InMemorySecretStore()


__all__ = ["BuildOptions", "build_context"]
