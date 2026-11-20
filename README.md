# NingX-Optimizer

AI-assisted Windows performance and maintenance, built around a deterministic
safety spine. An AI may observe and recommend; it may never execute.

**Status: pre-release vertical slice (M0–M3).** The application reads system
state, evaluates action proposals against a real policy engine, samples live
telemetry and turns measurements into evidence-backed findings. No mutation path
is enabled in this build: `RealWindowsOps` raises `MutationNotAvailable` for
every write.

## What exists today

- **Typed action contract** (`ningx.contracts`). Actions carry a target and
  parameters only. `extra="forbid"` means an AI payload that tries to supply
  `risk`, `reversible` or an executor reference fails validation.
- **Sealed action registry.** Eight action types; two (`service_stop`,
  `hardware_tune`) are explicitly denied in this release. Unknown types are
  denied before any other rule runs.
- **Policy engine with fixed precedence.** Hard safety → capability → mode →
  user lists → risk → approval → execution. `PolicyEngine.evaluate` is a pure
  function, so the permission table is exhaustively testable.
- **Three permission modes.** Read, Agent (approve each change) and Full-Access
  (bounded autonomy). Full-Access keeps a three-action allowlist and still
  requires approval for anything high-risk. Only a non-agent actor can change
  the mode, and Full-Access requires typing `FULL-ACCESS`.
- **Approval binding.** An approval commits to one action id, canonical payload,
  mode and expiry via SHA-256, and is single-use by design.
- **Protected targets.** System processes, security products, session-0
  processes, system directories, registry hives and the app's own data
  directory are refused structurally, not by convention.
- **Validation.** Paths reject device paths, traversal, alternate data streams
  and reparse points; processes are identified by `(pid, create_time, exe)` so a
  reused PID cannot be hit.
- **Windows Credential Manager** for provider secrets; a secret is stored by
  reference, never in settings, logs or the database.
- **Redaction on every log record and audit row** before it reaches a handler or
  the database.
- **SQLite storage** with WAL, hand-written Python migrations and an audit trail.
- **Live telemetry** from psutil plus PDH `GPU Engine` counters, sampled on one
  engine thread. A metric that is still warming up or that the hardware does not
  expose is reported as `warming_up` or `unsupported` — never as zero. GPU
  temperature, clocks and power are `unsupported` because no vendor API is
  bundled.
- **Dashboard and Live Monitor.** A weighted health score whose unavailable
  metrics are excluded and whose remaining weights are renormalised, per-core
  utilisation, stored load history, and a sortable process table that marks
  protected processes with the same object the policy engine enforces.
- **Deterministic analysts** (`ningx.analysis`). Eight pure functions over one
  measurement plus the startup registry and a bounded temp-folder walk. Each
  threshold is a named constant; each finding carries the measurements behind
  it. Nothing in that package can execute, and a test asserts it.
- **Findings with stable identity.** A fingerprint is derived from
  `(analyst, rule, subject)` and deliberately excludes measured values,
  timestamps and severity, so the same problem keeps its identity as it gets
  better or worse.
- **Optimization Center.** Runs a scan on a worker thread, groups results by
  category, shows evidence and the suggested action type, and refuses to scan a
  measurement older than two minutes rather than describing stale data as
  current.
- **Policy Lab UI** (PySide6): paste an untrusted action payload, choose a mode,
  and see every decision reason in precedence order. It audits the evaluation,
  cannot execute, and cannot change the saved mode.

Every other screen states which milestone will fill it. No screen shows
simulated telemetry or fake agent activity.

## Requirements

- Windows 10 or 11
- Python 3.12–3.14

## Development

```powershell
uv venv --system-site-packages .venv
uv pip install --python .venv\Scripts\python.exe -e .
uv pip install --python .venv\Scripts\python.exe pytest pytest-asyncio ruff mypy types-psutil
```

Run the checks:

```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m ruff check .
.\.venv\Scripts\python.exe -m mypy
.\.venv\Scripts\python.exe -m ningx --check
```

`--check` boots the real composition root and verifies the database schema, the
sealed registry, the permission truth table, Credential Manager round-trip,
audit redaction, the Windows read path, the deterministic analysts against one
real sample, the findings store, and that mutations stay disabled. It performs
no system change and writes no scan to the history.

Launch the UI:

```powershell
.\.venv\Scripts\python.exe -m ningx
```

## Data locations

- Application data: `%LOCALAPPDATA%\NingX` (database, logs, quarantine, backups)
- Provider secrets: Windows Credential Manager, targets prefixed
  `NingX-Optimizer/`

The repository itself contains no runtime data; a live WAL database inside a
synced folder is a corruption risk.

## Design constraints

- The UI never decides policy, validates actions or calls Windows directly.
- Risk is computed from `(action type, target, live facts)`. Uncertainty may
  raise risk, never lower it.
- Timeouts and silence never mean approval.
- A capability that is unavailable says so; it is not faked.
- A finding is a statement about a subject, not a snapshot of numbers, and every
  finding shows the measurements that produced it.
- Analysts are pure functions over data they are given. They cannot read the
  machine, open the database or call an executor, so no finding can be explained
  by "the model decided".
