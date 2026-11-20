"""The application context: every service wired exactly once.

Handlers and UI screens receive this object instead of reaching for globals. Tests
build a context pointing at a temporary database and a fake operating system, so
no test can touch the real machine.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from ningx.analysis.junk import JunkScannerPort
from ningx.analysis.runner import ScanRunner
from ningx.app.paths import AppPaths
from ningx.contracts.time import Clock
from ningx.core.action_registry import ActionRegistry
from ningx.core.dry_run import DryRunExecutor
from ningx.core.permission_manager import PermissionManager
from ningx.core.policy_engine import PolicyEngine
from ningx.providers.router import ProviderRegistry, ProviderRouter
from ningx.security.path_validator import PathValidator
from ningx.security.process_validator import ProcessProbe, ProcessValidator
from ningx.security.protected_targets import ProtectedTargets
from ningx.security.secret_store import SecretStore
from ningx.security.startup_collector import StartupCollector
from ningx.security.target_assessor import TargetAssessor
from ningx.storage.db import Database
from ningx.storage.repositories.actions import SqliteActionRepository
from ningx.storage.repositories.audit import SqliteAuditSink
from ningx.storage.repositories.findings import SqliteFindingRepository
from ningx.storage.repositories.providers import SqliteProviderRepository
from ningx.storage.repositories.settings import SqliteSettingsStore
from ningx.storage.repositories.telemetry import SqliteTelemetryRepository
from ningx.telemetry.engine import TelemetryEngine
from ningx.telemetry.sampler import SystemSampler
from ningx.winapi.ops import WindowsOps


@dataclass(frozen=True)
class AppContext:
    paths: AppPaths
    db: Database
    settings: SqliteSettingsStore
    audit: SqliteAuditSink
    actions: SqliteActionRepository
    secrets: SecretStore
    protected: ProtectedTargets
    registry: ActionRegistry
    permissions: PermissionManager
    policy: PolicyEngine
    assessor: TargetAssessor
    dry_run: DryRunExecutor
    ops: WindowsOps
    probe: ProcessProbe
    path_validator: PathValidator
    process_validator: ProcessValidator
    sampler: SystemSampler
    telemetry_repo: SqliteTelemetryRepository
    telemetry: TelemetryEngine
    findings_repo: SqliteFindingRepository
    startup_collector: StartupCollector
    junk_scanner: JunkScannerPort
    scanner: ScanRunner
    providers_repo: SqliteProviderRepository
    provider_registry: ProviderRegistry
    clock: Clock
    logger: logging.Logger

    def make_router(self) -> ProviderRouter:
        """A router over the *current* stored configurations.

        Built per use rather than stored, so enabling a provider in the UI takes
        effect on the next request without restarting the application.
        """
        return ProviderRouter(
            self.providers_repo.list_all(),
            self.provider_registry,
            audit=self.audit,
            clock=self.clock,
        )


__all__ = ["AppContext"]
