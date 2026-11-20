# NingX-Optimizer

AI-assisted Windows performance and maintenance, built around a deterministic
safety spine. An AI may observe and recommend; it may never execute.

**Status: pre-release vertical slice (M0–M4).** The application reads system
state, evaluates action proposals against a real policy engine, samples live
telemetry and turns measurements into evidence-backed findings. An AI provider
can describe a plan, but the model's output only becomes a typed proposal after
it passes the registry and parameter boundary. No mutation path is enabled in
this build: `RealWindowsOps` raises `MutationNotAvailable` for every write.

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
- **Provider layer with one real adapter** (`ningx.providers`). The catalogue is a
  closed set; `gemini` is the only kind implemented in this release and every
  other kind reports "adapter not built yet". The Gemini adapter uses
  `google-genai`, counts thinking tokens as output because they are billed as
  output, and disables SDK retries so a timeout stays a timeout.
- **Routing that can refuse.** Before a request is sent, the router evaluates
  local-only, fallback permission and a pinned provider, and reports the plan it
  would follow. Rate limiting is not retried automatically because a retry spends
  quota.
- **Honest usage accounting.** `TokenUsage` cannot carry counts while marked
  unavailable, an estimate is a separate type from a measurement, and `p95`
  latency is withheld below 20 samples.
- **Proposal boundary.** Model JSON becomes a typed `Action` only if it names a
  registered, non-denied action and only parameters on that action's allowlist;
  `requested_by` is overwritten with `agent:<id>`, and `risk` or `reversible`
  supplied by a model is rejected.
- **Prompt built from the registry** (`ningx.ai.prompt`): the system prompt is
  generated from the sealed registry, denied actions are withheld, and finding
  text is flattened so a measurement cannot smuggle instructions into a prompt.
- **AI Providers screen.** Configure a provider, store its key in Credential
  Manager, test the connection (lists models and spends no generation tokens),
  fetch models, set the routing policy, and read the stored usage ledger. The
  routing card shows a live preview and says "Preview only: nothing is sent."
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
real sample, the findings store, the AI provider catalogue and proposal
boundary, and that mutations stay disabled. It performs no system change, makes
no network request and writes no scan to the history.

Launch the UI:

```powershell
.\.venv\Scripts\python.exe -m ningx
```

## Build the Windows executable

The packaged app is a single windowed `.exe`. Double-clicking it opens the UI;
there is no installer. PyInstaller's onefile bootloader unpacks the bundle into
a temporary `%TEMP%\_MEIxxxx` folder while the app runs and removes it on exit;
application data still lives only in the app data directory.

```powershell
.\.venv\Scripts\python.exe -m pip install pyinstaller
powershell -ExecutionPolicy Bypass -File packaging\build_exe.ps1
```

The script renders `packaging\ningx.ico` from the same design the window icon
uses, writes the version resource from `ningx.__version__`, then runs
PyInstaller (`--onefile --windowed`). The artifact is
`dist\NingX-Optimizer.exe` — about 87 MB, most of it Qt and the Gemini SDK. A
build takes roughly five minutes.

Verify the artifact from a console:

```powershell
.\dist\NingX-Optimizer.exe --version
.\dist\NingX-Optimizer.exe --check --quiet
```

Both print to the console that launched them; started from Explorer, the
windowed build opens the UI. `--check` runs the same 19 probes as the source
tree, including that Credential Manager round-trips and that `google-genai`
imports inside the bundle.

The build is **unsigned**. Windows SmartScreen will warn on first run
("Windows protected your PC" → *More info* → *Run anyway*) until a signed
release exists. The exe is self-contained: the machine does not need Python,
PySide6 or pywin32 installed.

`dist\`, `build\` and `*.spec` are gitignored; only `packaging\` is tracked.

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
