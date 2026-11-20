"""Command line entry points.

``ningx --check`` is the verification command for this build: it boots the real
composition root, exercises the safety spine against the real policy engine, and
proves the database, secret store and Windows read path all work. It performs no
mutation.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from pathlib import Path

from ningx.app.context import AppContext
from ningx.contracts.action import Action, ProcessTarget, StartupTarget
from ningx.contracts.enums import DecisionOutcome, PermissionMode
from ningx.core.policy_engine import PolicyContext
from ningx.security.target_assessor import TargetAssessment
from ningx.storage.migrations import LATEST_VERSION
from ningx.telemetry.models import human_bytes

_APPROVED_STARTUP_PATH = (
    r"Software\Microsoft\Windows\CurrentVersion\Explorer\StartupApproved\Run"
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    ok: bool
    detail: str = ""


def run_self_check(ctx: AppContext) -> list[CheckResult]:
    results: list[CheckResult] = []
    now = ctx.clock()

    # --- filesystem -----------------------------------------------------------
    try:
        probe_file = ctx.paths.cache / f".write-test-{uuid.uuid4().hex}"
        probe_file.write_text("ok", encoding="utf-8")
        probe_file.unlink()
        results.append(CheckResult("paths.writable", True, str(ctx.paths.root)))
    except OSError as exc:
        results.append(CheckResult("paths.writable", False, str(exc)))

    # --- schema ---------------------------------------------------------------
    version = ctx.db.schema_version()
    results.append(
        CheckResult("database.schema", version == LATEST_VERSION, f"version={version}")
    )

    # --- registry -------------------------------------------------------------
    results.append(
        CheckResult(
            "action.registry",
            ctx.registry.is_sealed and len(ctx.registry) > 0,
            f"{len(ctx.registry)} action types: {', '.join(ctx.registry.types())}",
        )
    )

    # --- policy: read mode cannot mutate -------------------------------------
    process_action = _process_action()
    read_ctx = PolicyContext(mode=PermissionMode.READ, now=now)
    decision = ctx.policy.evaluate(
        process_action, read_ctx, TargetAssessment.allow(risk_floor=None)
    )
    results.append(
        CheckResult(
            "policy.read_mode_blocks_write",
            decision.outcome is DecisionOutcome.DENY
            and "mode.read_only" in decision.reason_codes(),
            decision.summary(),
        )
    )

    # --- policy: agent mode requires approval --------------------------------
    agent_ctx = PolicyContext(mode=PermissionMode.AGENT, now=now)
    decision = ctx.policy.evaluate(
        process_action, agent_ctx, TargetAssessment.allow()
    )
    results.append(
        CheckResult(
            "policy.agent_requires_approval",
            decision.outcome is DecisionOutcome.REQUIRE_APPROVAL,
            decision.summary(),
        )
    )

    # --- policy: hard safety beats full access -------------------------------
    full_ctx = PolicyContext(mode=PermissionMode.FULL_ACCESS, now=now)
    decision = ctx.policy.evaluate(
        process_action, full_ctx, TargetAssessment.deny("target.protected_process")
    )
    results.append(
        CheckResult(
            "policy.full_access_respects_hard_deny",
            decision.outcome is DecisionOutcome.DENY
            and "target.protected_process" in decision.reason_codes(),
            decision.summary(),
        )
    )

    # --- policy: full access autonomy for an allowlisted action --------------
    startup_action = _startup_action()
    decision = ctx.policy.evaluate(
        startup_action, full_ctx, TargetAssessment.allow()
    )
    results.append(
        CheckResult(
            "policy.full_access_autonomy",
            decision.outcome is DecisionOutcome.ALLOW,
            decision.summary(),
        )
    )

    # --- secrets --------------------------------------------------------------
    reference = f"selfcheck/{uuid.uuid4().hex}"
    try:
        ctx.secrets.set(reference, "selfcheck-value-123")
        round_trip = ctx.secrets.get(reference) == "selfcheck-value-123"
        deleted = ctx.secrets.delete(reference)
        results.append(
            CheckResult(
                "secrets.round_trip",
                round_trip and deleted,
                type(ctx.secrets).__name__,
            )
        )
    except Exception as exc:
        results.append(CheckResult("secrets.round_trip", False, type(exc).__name__))

    # --- audit ----------------------------------------------------------------
    try:
        from ningx.core.ports import AuditEvent

        before = len(ctx.audit.recent(5))
        ctx.audit.append(
            AuditEvent(actor="selfcheck", event_type="selfcheck.run", detail={"api_key": "x"})
        )
        after = ctx.audit.recent(5)
        results.append(
            CheckResult(
                "audit.append",
                len(after) >= before and after[0].event_type == "selfcheck.run",
                f"{len(after)} recent events",
            )
        )
    except Exception as exc:
        results.append(CheckResult("audit.append", False, type(exc).__name__))

    # --- windows read path ----------------------------------------------------
    try:
        plan = ctx.ops.active_power_plan()
        snapshot = ctx.ops.process_snapshot(_current_pid())
        results.append(
            CheckResult(
                "windows.read_path",
                plan is not None or snapshot is not None,
                f"power_plan={plan or 'unknown'} process={'found' if snapshot else 'missing'}",
            )
        )
    except Exception as exc:
        results.append(CheckResult("windows.read_path", False, type(exc).__name__))

    # --- telemetry read path ---------------------------------------------------
    results.append(_check_telemetry(ctx))

    # --- deterministic analysis ------------------------------------------------
    results.extend(_check_analysis(ctx))

    # --- AI layer: honest inventory and a closed proposal boundary ------------
    results.extend(_check_ai(ctx))

    # --- mutation path is closed ---------------------------------------------
    from ningx.winapi.ops import RealWindowsOps

    if isinstance(ctx.ops, RealWindowsOps):
        blocked = False
        detail = ""
        try:
            ctx.ops.terminate_process(999_999)
        except Exception as exc:
            blocked = True
            detail = type(exc).__name__
        results.append(
            CheckResult(
                "windows.mutations_disabled",
                blocked,
                detail or "UNEXPECTED: a mutation method returned normally",
            )
        )
    else:
        results.append(
            CheckResult(
                "windows.mutations_disabled",
                True,
                f"skipped: {type(ctx.ops).__name__} (test double)",
            )
        )

    return results


def _check_telemetry(ctx: AppContext) -> CheckResult:
    """Take one real sample and verify it is self-consistent.

    This proves the sampling path works without starting the engine thread or
    writing a snapshot.
    """
    try:
        sample = ctx.sampler.sample()
    except Exception as exc:
        return CheckResult("telemetry.read_path", False, f"{type(exc).__name__}: {exc}")

    consistent = (
        sample.memory.total_bytes > 0
        and sample.memory.used_bytes <= sample.memory.total_bytes
        and sample.cpu.logical_count >= 1
        and 0.0 <= sample.memory.used_pct <= 100.0
    )
    cpu_text = (
        f"{sample.cpu.total_pct:.0f}%"
        if sample.cpu.total_pct is not None
        else "warming up"
    )
    detail = (
        f"cpu={cpu_text}/{sample.cpu.logical_count} cores"
        f" memory={human_bytes(sample.memory.used_bytes)}/{human_bytes(sample.memory.total_bytes)}"
        f" gpu={sample.gpu.utilization.state}"
        f" processes={len(sample.processes)}"
    )
    return CheckResult("telemetry.read_path", consistent, detail)


def _check_analysis(ctx: AppContext) -> list[CheckResult]:
    """Prove the deterministic layer runs on real data and is wired to storage.

    The analysts are exercised against one real sample. Nothing is written: a
    self-check must not invent a scan in the user's history.
    """
    from ningx.analysis.analysts import AnalysisInput, run_analysts

    results: list[CheckResult] = []
    try:
        sample = ctx.sampler.sample()
        findings = run_analysts(AnalysisInput(sample=sample))
        fingerprints = {finding.fingerprint for finding in findings}
        consistent = len(fingerprints) == len(findings)
        categories = sorted({finding.category.value for finding in findings})
        results.append(
            CheckResult(
                "analysis.analysts",
                consistent,
                f"{len(findings)} findings"
                + (f" in {', '.join(categories)}" if categories else " (nothing wrong)"),
            )
        )
    except Exception as exc:
        results.append(CheckResult("analysis.analysts", False, type(exc).__name__))

    try:
        latest = ctx.findings_repo.latest_scan()
        count = ctx.findings_repo.finding_count()
        detail = (
            f"latest scan #{latest.id} {latest.status}" if latest is not None else "no scans yet"
        )
        results.append(
            CheckResult("analysis.storage", True, f"{detail}, {count} findings stored")
        )
    except Exception as exc:
        results.append(CheckResult("analysis.storage", False, type(exc).__name__))

    return results


def _check_ai(ctx: AppContext) -> list[CheckResult]:
    """Prove the AI layer is honest about what exists and closed to what does not.

    Nothing here calls a provider or spends a token. It checks the catalogue the
    UI reads, the storage path it writes through, and the proposal validator that
    every model response must survive.
    """
    import json

    from ningx.ai.prompt import build_system_prompt, proposable_specs
    from ningx.ai.proposal import ProposalRejected, parse_proposals
    from ningx.providers.catalogue import PROFILES, implemented_kinds

    results: list[CheckResult] = []

    implemented = implemented_kinds()
    honest = all(PROFILES[kind].implemented for kind in implemented) and all(
        profile.implemented or profile.note for profile in PROFILES.values()
    )
    results.append(
        CheckResult(
            "ai.provider_catalogue",
            honest and len(PROFILES) > 0,
            f"{len(implemented)} implemented of {len(PROFILES)}: {', '.join(implemented)}",
        )
    )

    try:
        stored = ctx.providers_repo.list_all()
        results.append(
            CheckResult(
                "providers.storage",
                True,
                f"{len(stored)} configured"
                + (f", {sum(1 for item in stored if item.enabled)} enabled" if stored else ""),
            )
        )
    except Exception as exc:
        results.append(CheckResult("providers.storage", False, type(exc).__name__))

    valid = {
        "action_type": "startup_disable",
        "target": {
            "kind": "startup",
            "hive": "HKCU",
            "registry_path": (
                r"Software\Microsoft\Windows\CurrentVersion\Explorer"
                r"\StartupApproved\Run"
            ),
            "value_name": "SelfCheckEntry",
        },
        "reason": "self-check sample",
    }

    def rejects(payload: dict[str, object], expected: str) -> bool:
        try:
            parse_proposals(
                json.dumps(payload),
                registry=ctx.registry,
                agent_id="selfcheck",
                provider_id="none",
                model="none",
            )
        except ProposalRejected as exc:
            return exc.reason == expected
        return False

    try:
        parsed = parse_proposals(
            json.dumps({"proposals": [valid]}),
            registry=ctx.registry,
            agent_id="selfcheck",
            provider_id="none",
            model="none",
        )
        relabelled = parsed[0].action.requested_by == "agent:selfcheck"
        refused = (
            rejects({**valid, "risk": "low"}, "proposal.invalid_action")
            and rejects(
                {**valid, "parameters": {"command": "cmd /c whoami"}},
                "proposal.unknown_parameter",
            )
            and rejects({**valid, "action_type": "shell_execute"}, "proposal.unknown_action_type")
            and rejects({**valid, "reason": "  "}, "proposal.missing_reason")
        )
        results.append(
            CheckResult(
                "ai.proposal_boundary",
                relabelled and refused,
                "1 accepted and relabelled, 4 hostile payloads refused",
            )
        )
    except Exception as exc:
        results.append(CheckResult("ai.proposal_boundary", False, type(exc).__name__))

    try:
        system = build_system_prompt(ctx.registry)
        specs = proposable_specs(ctx.registry)
        offered = all(spec.action_type in system for spec in specs)
        denied = [spec.action_type for spec in ctx.registry if spec.denied_in_release]
        withheld = all(f"- {name} (" not in system for name in denied)
        results.append(
            CheckResult(
                "ai.prompt",
                offered and withheld and bool(specs),
                f"{len(specs)} actions described, {len(denied)} denied actions withheld",
            )
        )
    except Exception as exc:
        results.append(CheckResult("ai.prompt", False, type(exc).__name__))

    return results


def format_report(results: list[CheckResult]) -> str:
    width = max(len(result.name) for result in results) if results else 0
    lines = ["NingX-Optimizer self-check", "-" * 60]
    for result in results:
        status = "PASS" if result.ok else "FAIL"
        lines.append(f"{status}  {result.name.ljust(width)}  {result.detail}")
    passed = sum(1 for result in results if result.ok)
    lines.append("-" * 60)
    lines.append(f"{passed}/{len(results)} checks passed")
    return "\n".join(lines)


def _process_action() -> Action:
    return Action(
        action_type="process_terminate",
        target=ProcessTarget(
            pid=4242,
            create_time=1000.0,
            executable=r"C:\Program Files\Example\example.exe",
        ),
        reason="self-check sample",
        requested_by="selfcheck",
    )


def _startup_action() -> Action:
    return Action(
        action_type="startup_disable",
        target=StartupTarget(
            hive="HKCU",
            registry_path=_APPROVED_STARTUP_PATH,
            value_name="ExampleStartup",
        ),
        reason="self-check sample",
        requested_by="selfcheck",
    )


def _current_pid() -> int:
    import os

    return os.getpid()


def default_data_dir() -> Path:
    from ningx.app.paths import AppPaths

    return AppPaths.default().root


__all__ = ["CheckResult", "default_data_dir", "format_report", "run_self_check"]
