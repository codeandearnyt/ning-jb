# NingX-Optimizer — Product Requirements Document (PRD)

**Document version:** 1.0  
**Status:** Proposed baseline specification  
**Product:** NingX-Optimizer  
**Platform:** Windows 10/11 desktop  
**Primary language:** Python  
**AI layer:** Multi-provider, with Google Gemini already integrated  
**Document purpose:** Product, architecture, safety, and implementation specification for development with OpenCode, Qoder, or a similar coding agent.

---

## 1. Product overview

NingX-Optimizer is an AI-assisted Windows performance and maintenance application. It acts as a continuously available PC performance engineer: it observes system health, identifies potential bottlenecks, explains findings, proposes optimizations, and executes permitted actions through a controlled local execution layer.

The product combines:

- Local Python-based monitoring and deterministic analysis.
- A multi-provider AI integration layer.
- A 20-role logical multi-agent organization.
- Three user permission modes: Read, Agent, and Full-Access.
- Explicit approval workflows for system-changing actions.
- Pre-action safety checks, post-action verification, audit logs, and rollback support.
- Token- and API-cost-aware cloud synchronization.

**Core principle:** AI may reason and recommend, but it must never be the unrestricted executor of Windows commands. All system modifications must pass through deterministic policy checks and a restricted execution engine.

## 2. Product vision

Deliver a reliable Windows utility that helps users:

1. Understand what is consuming CPU, RAM, GPU, network bandwidth, and storage.
2. Identify unnecessary background activity and startup overhead.
3. Find memory pressure, possible leaks, junk files, duplicate files, and disorganized files.
4. Improve gaming and everyday responsiveness through reversible, evidence-based optimizations.
5. Keep control over every meaningful system change.
6. Use the user's chosen AI provider and API credentials, while minimizing unnecessary API calls and token consumption.

## 3. Goals and non-goals

### 3.1 Goals

- Provide useful local monitoring even when no AI provider is configured or the internet is unavailable.
- Support multiple AI providers through a consistent adapter interface.
- Keep local scans and cloud reasoning on separate schedules.
- Support the three permission modes consistently across every agent and action.
- Require explicit, per-action approval in Agent Mode.
- Make destructive or risky actions explainable, auditable, and recoverable where technically possible.
- Avoid targeting protected Windows processes and critical system resources.
- Make performance claims measurable using before/after telemetry.
- Keep the application modular so new agents, providers, and optimizers can be added independently.

### 3.2 Non-goals for the initial release

- Guaranteeing a specific FPS increase or performance improvement on every PC.
- Automatically overclocking every GPU or CPU.
- Replacing Windows Security, Task Manager, Device Manager, Disk Cleanup, or backup software.
- Running arbitrary AI-generated PowerShell, CMD, registry scripts, or Python code.
- Deleting user files based on semantic guesses.
- Bypassing administrator permissions, Windows security controls, or application protections.
- Supporting Linux or macOS in the first Windows release.

## 4. Target users and use cases

### Target users

- PC gamers who want better visibility into background resource usage.
- Everyday Windows users who want safer cleanup and startup management.
- Power users who want detailed telemetry and configurable optimization profiles.
- Users who prefer local AI through Ollama or wish to use their own API keys.

### Primary user journeys

1. Install and launch the app; complete a system capability scan.
2. Choose Read Mode, Agent Mode, or Full-Access Mode.
3. Configure one or more AI providers and test connectivity.
4. View a live dashboard and a prioritized system health report.
5. Review recommendations with impact, risk, reason, and rollback details.
6. Approve or reject proposed actions where required.
7. Inspect execution results and post-action stability checks.
8. Review historical metrics, actions, approvals, and provider usage.

## 5. Permission and autonomy model

The selected mode is a top-level policy input. No agent or provider may override it.

### 5.1 Read Mode

**Purpose:** Observe and report only.

Allowed:
- Read system metrics and process metadata.
- Inspect startup entries, storage metadata, and permitted registry values.
- Analyze logs and historical metrics.
- Produce recommendations and reports.

Not allowed:
- Terminate or suspend processes.
- Delete, move, rename, or write files.
- Change registry values, services, startup settings, power plans, network settings, or hardware settings.
- Apply overclocking or undervolting.

The execution engine must reject all write actions in this mode, even if an agent requests them.

### 5.2 Agent Mode

**Purpose:** AI-assisted operation with explicit user approval.

Allowed:
- All Read Mode operations.
- Prepare a proposed action and explain its purpose.
- Run safe, non-mutating pre-flight checks.
- Request approval for a specific action.

Rules:
- Every system-changing action requires a separate, explicit approval.
- Approval is bound to one immutable action payload, target, parameters, and expiry.
- Approval for one action must never authorize a batch of unrelated actions.
- If the action payload changes, approval becomes invalid.
- Reject, timeout, or dismissal means do not execute.
- The UI must show the exact target, expected effect, risk, and recovery plan before approval.
- Actions with multiple targets require separate approvals per target unless the user explicitly approves a clearly itemized batch.

### 5.3 Full-Access Mode

**Purpose:** Reduce approval interruptions for supported, pre-authorized routine optimizations.

Allowed:
- Execute actions that are explicitly classified as eligible for autonomous execution by the policy engine.
- Run configured cleanup, process, startup, and profile actions within user-defined boundaries.

Full-Access is **not** unrestricted operating-system control. The following remain protected:
- Windows system files and protected directories.
- Critical Windows processes and security software.
- Unverified or ambiguous file deletion.
- Registry changes without a known setting, validated value, and recovery record.
- Driver, firmware, BIOS, voltage, and hardware changes that cannot be safely verified.
- High-risk overclocking or undervolting.
- Disabling security, update, recovery, or core operating-system services.
- Any action prohibited by the security policy.

For high-impact or irreversible actions, require a separate confirmation or keep the action unavailable. The UI must clearly explain that Full-Access has these boundaries.

### 5.4 Policy precedence

Apply policy in this order:

1. Hard safety deny rules.
2. Windows capability and privilege checks.
3. User-selected permission mode.
4. User-defined allow/deny lists and optimization preferences.
5. Risk classification and action-specific requirements.
6. Approval state, if required.
7. Execution.

A lower-level rule must never override a higher-level restriction.

## 6. Multi-provider AI engine

### 6.1 Supported providers

The provider manager must support:

1. Google Gemini — existing integration; preserve and refactor behind the common interface.
2. NVIDIA — supported NVIDIA inference/API endpoints and models.
3. Groq.
4. Cloudflare AI Gateway — gateway/routing configuration; not treated as a model family itself.
5. Ollama — local model server.
6. Anthropic Claude.
7. OpenAI ChatGPT API.
8. OpenRouter.
9. OpenCode Zen — integrate through its currently supported API/authentication contract.
10. Custom OpenAI-compatible endpoint.

Provider availability and model IDs must be configurable. Do not hard-code assumptions about model availability, free quotas, pricing, or endpoint compatibility.

### 6.2 Provider configuration

Each provider configuration should support, as applicable:

- Display name and provider type.
- Enabled/disabled state.
- API key or credential reference.
- Base URL / endpoint.
- Model ID.
- Authentication scheme and header configuration.
- Request timeout.
- Retry policy.
- Maximum output tokens.
- Optional provider-specific parameters.
- Local/remote designation.
- Priority and fallback eligibility.
- Connection-test status and last successful test.
- Per-provider usage and error statistics.

Secrets must be stored using Windows Credential Manager or an equivalent OS-protected secret store. Do not store API keys in plaintext configuration files, logs, crash reports, or source code. Provide a clear option to remove credentials.

### 6.3 Custom OpenAI-compatible integrations

Required user inputs:
- Provider display name.
- Base URL.
- Bearer token.
- Model ID.
- Optional custom headers only when explicitly supported.
- Timeout and retry configuration.

The adapter must:
- Validate URL scheme and reject unsafe local/network destinations according to policy.
- Avoid sending credentials to a different host after redirects.
- Support the documented compatible chat/completion request format.
- Provide a connection test and a small, user-visible test request.
- Surface unsupported parameters clearly rather than silently pretending they worked.

### 6.4 Cloudflare AI Gateway

Treat Cloudflare AI Gateway as a configurable gateway/proxy path. Support the required account/gateway endpoint and authentication settings. The gateway may route to a model provider; model selection and gateway configuration must remain separate concepts.

### 6.5 Unified provider interface

All providers should implement a common interface similar to:

```python
class AIProvider:
    def validate_config(self) -> ValidationResult: ...
    def test_connection(self) -> ConnectionResult: ...
    def list_models(self) -> list[ModelInfo]: ...
    def generate(self, request: AIRequest) -> AIResponse: ...
    def estimate_usage(self, request: AIRequest) -> UsageEstimate: ...
```

Use typed request/response objects. Normalize:
- Text content.
- Tool/action proposal data, if supported.
- Input/output token counts when provided.
- Latency.
- Provider/model identity.
- Finish reason.
- Errors and retryability.

Never assume every provider supports the same tool calling, JSON mode, streaming, context size, or usage metadata. Use capability flags and provider-specific translation.

### 6.6 Routing strategy

The model router should choose a provider/model based on:
- User preference and explicit pinning.
- Task capability requirements.
- Local versus cloud preference.
- Availability and health.
- Latency.
- Configured cost/token budget.
- Context window and output requirements.
- Privacy settings.

Do not silently route sensitive system data to a new provider. Show the user which provider receives data and allow cloud synchronization to be disabled.

### 6.7 Fallback behavior

- Retry only transient errors with bounded exponential backoff.
- Do not repeatedly retry authentication, invalid request, or quota errors.
- Use a fallback provider only if the user has enabled it and the data-sharing policy permits it.
- Never fall back to a cloud provider when the user has configured local-only processing.
- Record provider switches in the audit log.
- If all providers fail, continue local monitoring and queue a summarized report.

## 7. The 20-agent organization

Agents are logical roles coordinated by a Python orchestrator. They do not need to be 20 separate LLM processes or 20 API calls. Most roles should use deterministic Python code and only request AI reasoning when it adds value.

### 7.1 Executive and coordination agents

**01. CEO — Chief Execution Optimizer**
- Master orchestrator and final internal decision authority.
- Reads the active user mode and global policy.
- Collects recommendations and risk assessments.
- Resolves conflicts and rejects unsafe proposals.
- Issues an internal execution decision.
- Cannot override hard safety rules or Agent Mode user approval.

**02. Chairperson — API & Token Strategist**
- Manages provider selection, API budgets, and cloud synchronization.
- Compresses local findings into structured summaries.
- Enforces the configured 40-minute routine AI cycle.
- Tracks token usage, cost estimates, latency, and failures.
- Avoids duplicate requests using hashes and change detection.

**03. Director of Operations — System Monitor**
- Initializes monitoring services.
- Triggers the default 20-minute local scan cycle.
- Dispatches relevant engineering agents.
- Coordinates event-driven scans for important anomalies.
- Ensures local safety monitoring continues if AI is offline.

**04. Project Manager — Approval Coordinator**
- Converts approved internal proposals into user-facing approval requests.
- In Agent Mode, requests explicit Y/N approval for every mutation.
- Binds approval to the exact action payload and expiry.
- Records approval, rejection, timeout, and cancellation.
- Never executes actions itself.

**05. Customer Success Lead — Live UI Broadcaster**
- Publishes live agent activity and progress to the UI.
- Shows which logical agent is active and what it is analyzing.
- Communicates findings, waiting states, approvals, and failures.
- Avoids exposing secrets, sensitive paths, or excessive technical noise.
- Must distinguish actual activity from planned or simulated activity.

### 7.2 Engineering agents

**06. Sr. RAM Engineer**
- Tracks memory use, commit charge, working sets, and pressure.
- Identifies sustained growth patterns that may indicate leaks.
- Produces evidence-based memory recommendations.
- May prepare a standby-list review or memory-maintenance proposal.
- Must not blindly clear standby memory; Windows memory management should be respected.

**07. Sr. CPU/GPU Specialist**
- Tracks utilization, clocks, temperatures, power, and bottlenecks where supported.
- Detects thermal throttling and sustained high load.
- Suggests safe performance profiles.
- Overclocking/undervolting is advisory or limited to validated integrations.
- No automatic voltage, firmware, or BIOS changes in the initial release.

**08. RegEdit Architect**
- Looks up known registry settings and documents their purpose.
- Reads relevant registry values with least privilege.
- Prepares changes only from a reviewed settings catalog.
- Requires strict validation, backup/export, and policy authorization for writes.
- Never invents registry paths or values from an AI response.

**09. Process Sniper — Senior Developer**
- Analyzes processes, resource use, signatures, paths, services, and parent-child relationships.
- Identifies likely unnecessary background activity.
- Uses allowlists and protected-process rules.
- Proposes process termination only when safe and explainable.
- Never targets protected or critical processes.

**10. Startup Sequence Engineer**
- Inspects startup applications, scheduled tasks, and startup impact where available.
- Reports boot-time contributors.
- Proposes disable, delay, or removal only where supported.
- Preserve the ability to restore the previous startup configuration.

**11. Network Bandwidth Manager**
- Measures throughput and identifies bandwidth-heavy applications where possible.
- Detects background downloads and sync activity.
- Suggests user-controlled traffic prioritization.
- Does not silently modify firewall rules, network adapters, or application settings.
- Do not promise game packet prioritization unless the OS/network mechanism actually supports it.

**12. Junk Demolition Partner**
- Identifies temporary files and known safe cleanup locations.
- Calculates reclaimable space before cleanup.
- Excludes system-critical, active, unknown, and user data by default.
- Uses a review/quarantine workflow where feasible.
- Windows Update and component-store cleanup must use supported Windows servicing mechanisms, not arbitrary deletion.

**13. Duplicate Detective**
- Finds exact duplicate files using size plus cryptographic hash.
- Groups duplicates and identifies empty folders.
- Excludes system and application directories by default.
- Never treats similar filenames as proof of duplication.
- Presents paths, sizes, and proposed retained copy before any removal.

**14. Auto-Organization Specialist**
- Categorizes files using deterministic rules and optional AI suggestions.
- Previews source and destination paths.
- Avoids moving application data, system files, hidden files, and unknown formats by default.
- Uses collision-safe moves and maintains a reversible operation manifest.
- Does not reorganize files without the required permission/approval.

### 7.3 Quality, safety, and intelligence agents

**15. Pre-Flight Tester — QA 1**
- Validates target existence, permissions, preconditions, and expected effects.
- Checks action against known risk rules and local history.
- Detects conflicting or duplicate pending actions.
- Simulates or dry-runs where the operation supports it.
- Blocks actions with failed preconditions.

**16. Post-Action Tester — QA 2**
- Verifies the action's actual result.
- Monitors resource and stability metrics after execution.
- Detects unexpected errors, crashes, stutters, or regressions.
- Initiates rollback or recovery recommendations when supported.
- Updates future risk history.

**17. Security & Stability Auditor**
- Applies hard-deny rules and protected target lists.
- Checks process identity, file paths, signatures, and action scope.
- Enforces least privilege and safe command construction.
- Rejects untrusted AI-generated commands or registry values.
- Can veto any action in every permission mode.

**18. The Problem Solver — Crash Analyst**
- Detects application hangs, system instability, and thermal throttling indicators.
- Correlates recent actions with newly observed problems.
- Suggests conservative recovery steps.
- Must not kill arbitrary processes or override the security auditor.
- Emergency response is limited to pre-approved safe actions.

**19. The Idea Maker — Proactive Profiler**
- Analyzes historical, privacy-conscious performance patterns.
- Suggests gaming profiles, power plans, and optimization opportunities.
- Explains the evidence behind suggestions.
- Does not autonomously create risky hardware settings.

**20. The Archiver — Log Master**
- Stores scans, recommendations, approvals, decisions, actions, and results.
- Maintains compact summaries for the next AI synchronization.
- Applies log rotation and retention limits.
- Redacts credentials and sensitive information.
- Provides searchable history and export.

## 8. Scheduling and event processing

Default schedules:

| Task | Default interval |
|---|---:|
| Local system scan | 20 minutes |
| Routine cloud AI synchronization | 40 minutes |
| UI updates | Event-driven |
| Critical local safety checks | Continuous or short interval as appropriate |
| Post-action verification | Immediately after an action, then bounded follow-up checks |
| Historical profiling | Configurable, low-priority |

Requirements:
- All intervals must be configurable.
- Use a single scheduler rather than one timer per agent.
- Prevent overlapping scans.
- Use cancellation and shutdown handling.
- Coalesce repeated events.
- A critical event may trigger immediate local analysis and, if enabled, an AI request outside the 40-minute cycle.
- The routine 40-minute sync must not block urgent local safety actions.
- Store the last successful sync and pending summary state across restarts.

## 9. Token and API cost optimization

The Chairperson should implement:

1. **Local-first analysis:** use Python rules and metrics before asking an LLM.
2. **Change detection:** compare current findings with the previous scan.
3. **Deduplication:** do not resend unchanged findings.
4. **Context compression:** send concise structured summaries, not raw process dumps.
5. **Request batching:** group related agent findings into one request when practical.
6. **Task routing:** use the smallest capable model/provider for routine tasks.
7. **Caching:** cache safe, reusable analysis results with clear invalidation rules.
8. **Budget controls:** per-provider request/token limits and optional monthly budgets.
9. **Usage reporting:** track known token counts, estimated counts, cost where available, and missing provider usage metadata.
10. **Local fallback:** use Ollama when configured and capable.

Never claim token savings as a fixed percentage without measurement. Show actual measured or estimated usage and clearly label estimates.

## 10. System monitoring requirements

Collect only metrics needed for the selected features and explain any elevated permissions.

### CPU
- Total and per-core utilization where available.
- Process CPU use.
- Frequency and temperature where supported.
- Load trends and sustained saturation.

### RAM
- Physical memory total, available, used.
- Commit charge and pagefile data where available.
- Per-process working set/private bytes.
- Sustained growth observations for leak suspicion.

### GPU
- Utilization, dedicated/shared memory, temperature, clocks, and power where supported by hardware/vendor APIs.
- Graceful unsupported state when a metric is unavailable.

### Storage
- Total/free space.
- Read/write activity where available.
- Candidate cleanup size.
- Duplicate file scan progress.

### Network
- Per-interface throughput.
- Per-process attribution only when supported and permissioned.
- Connection metadata should be minimized and not uploaded by default.

### Processes
- PID, name, executable path where permitted, parent PID, CPU/RAM use, publisher/signature status, and service association where available.
- PIDs must be revalidated immediately before any action to avoid PID reuse errors.

## 11. Optimization modules and action contracts

Every proposed mutation must use a typed action object. Never execute raw AI-generated shell text.

Example conceptual schema:

```json
{
  "action_id": "uuid",
  "action_type": "process_terminate",
  "target": {
    "pid": 1234,
    "executable": "example.exe"
  },
  "parameters": {},
  "reason": "Evidence-based explanation",
  "expected_effect": "Expected outcome",
  "risk": "low",
  "reversible": false,
  "preconditions": [],
  "rollback_plan": null,
  "created_at": "ISO-8601 timestamp",
  "expires_at": "ISO-8601 timestamp"
}
```

The actual implementation should use validated Python models (for example, Pydantic or dataclasses plus explicit validation).

### Action categories

- Read-only inspection.
- Process control.
- Startup configuration.
- File cleanup.
- File move/organization.
- Registry modification.
- Power-plan changes.
- Network configuration.
- Hardware tuning.

Each category must have separate capability checks, risk rules, and executor modules.

### Risk levels

- **Informational:** read-only observation.
- **Low:** narrow, reversible user-level change.
- **Medium:** change with meaningful user impact and a recovery path.
- **High:** potentially disruptive or difficult-to-reverse operation.
- **Critical:** prohibited or requires a dedicated manual workflow outside normal automation.

Risk must be assigned by deterministic policy, not accepted from the AI proposal alone.

## 12. Approval UX

An approval card should display:

- Agent proposing the action.
- Exact action type.
- Exact target and path/process identity.
- Why the action is recommended.
- Evidence and measured impact.
- Expected effect and possible side effects.
- Risk level.
- Whether it is reversible.
- Backup/rollback plan.
- Approval expiry.
- Approve and Reject controls.

Agent Mode:
- Require a fresh approval for each action.
- Do not use pre-checked approval controls.
- Do not interpret silence as approval.
- Cancel the action if the target changes before execution.
- Record the user's decision and timestamp.

Read Mode should not display executable approval controls for prohibited writes. Full-Access should show an activity feed and allow the user to pause automation or revoke the mode.

## 13. Security and privacy

- Store API credentials in Windows Credential Manager or equivalent secure storage.
- Never log credentials, authorization headers, or full secret-bearing URLs.
- Use TLS for remote API requests.
- Validate provider endpoints and redirects.
- Apply least privilege; request elevation only for a specific operation that needs it.
- Do not run the entire UI or application as administrator by default.
- Use argument arrays and safe subprocess APIs; avoid shell string interpolation.
- Validate and canonicalize file paths.
- Prevent path traversal and symlink/reparse-point deletion escapes.
- Revalidate process identity immediately before termination.
- Protect critical process, service, directory, and registry allow/deny lists.
- Keep AI output untrusted; parse into a strict schema and validate every field.
- Do not allow an agent to modify policy, permissions, provider credentials, or its own safety restrictions.
- Provide local-only mode and controls for what data can be sent to each provider.
- Provide log retention and clear-history controls.

## 14. Rollback and recovery

For supported changes:
- Capture the previous state before mutation.
- Store a transaction/operation manifest.
- Verify the backup can be read before proceeding.
- Use atomic file operations where possible.
- Move files to a quarantine/recycle workflow rather than permanent deletion when feasible.
- Export registry keys/values before modification.
- Record previous startup and power-plan settings.
- Offer a clear rollback action.
- Verify rollback results.

Not every operation is reversible. The UI and action proposal must say so honestly. Do not claim a restore point or backup exists unless it was successfully created and verified.

## 15. User interface requirements

Suggested primary navigation:

1. Dashboard
2. Live Monitor
3. AI Agents
4. Optimization Center
5. Gaming Profiles
6. Storage Analyzer
7. Startup Manager
8. Approval Center
9. Activity & Logs
10. AI Providers
11. Settings

### Dashboard
- CPU, RAM, GPU, disk, and network overview.
- Current system health and scan timestamp.
- Active permission mode.
- Current agent activity.
- Pending approvals.
- Recent actions and key recommendations.

### Live Monitor
- Process list with sortable resource metrics.
- Hardware telemetry.
- Historical graphs.
- Filter/search and protected-process indicators.

### AI Agents
- All 20 logical agents and their status.
- Current task, last activity, findings, and errors.
- Provider/model used when an LLM request occurs.
- Clearly distinguish local deterministic work from cloud AI reasoning.

### Optimization Center
- Recommendations grouped by category and risk.
- Evidence, estimated impact, and action preview.
- Approval workflow based on active mode.

### AI Providers
- Add/edit/disable providers.
- Secure credential entry.
- Model selection and connection test.
- Routing preferences and fallback configuration.
- Usage, latency, and error statistics.

### Settings
- Permission mode and clear mode explanation.
- Scan and sync intervals.
- Provider privacy settings.
- API budgets.
- Protected processes and paths.
- Log retention.
- Startup behavior and pause controls.

## 16. Local data model

Use SQLite for the initial release. Keep schema migrations versioned.

Suggested tables:

- `settings`
- `provider_configs` (store secret references, not plaintext secrets)
- `provider_usage`
- `scan_runs`
- `system_snapshots`
- `process_observations`
- `agent_runs`
- `findings`
- `recommendations`
- `actions`
- `approval_requests`
- `approval_decisions`
- `action_results`
- `rollback_records`
- `audit_events`
- `gaming_profiles`
- `file_scan_sessions`

Requirements:
- Use UTC timestamps internally and localize in the UI.
- Index time-series and lookup fields appropriately.
- Apply retention/compaction to high-volume metrics.
- Use database transactions for action state changes.
- Avoid storing unnecessary personal file contents or network payloads.

## 17. Suggested technical architecture

```text
NingX-Optimizer/
├── app/
│   ├── main.py
│   ├── bootstrap.py
│   └── lifecycle.py
├── core/
│   ├── orchestrator.py
│   ├── scheduler.py
│   ├── event_bus.py
│   ├── permission_manager.py
│   ├── policy_engine.py
│   └── config.py
├── ai_engine/
│   ├── provider_manager.py
│   ├── model_router.py
│   ├── token_optimizer.py
│   ├── context_compressor.py
│   ├── cache_manager.py
│   └── providers/
│       ├── base.py
│       ├── gemini.py
│       ├── nvidia.py
│       ├── groq.py
│       ├── cloudflare_gateway.py
│       ├── ollama.py
│       ├── anthropic.py
│       ├── openai.py
│       ├── openrouter.py
│       ├── opencode_zen.py
│       └── custom_openai.py
├── agents/
│   ├── base_agent.py
│   ├── ceo.py
│   ├── chairperson.py
│   ├── director_operations.py
│   ├── project_manager.py
│   ├── customer_success.py
│   ├── ram_engineer.py
│   ├── cpu_gpu_specialist.py
│   ├── regedit_architect.py
│   ├── process_sniper.py
│   ├── startup_engineer.py
│   ├── network_manager.py
│   ├── junk_cleaner.py
│   ├── duplicate_detective.py
│   ├── auto_organizer.py
│   ├── preflight_tester.py
│   ├── postaction_tester.py
│   ├── security_auditor.py
│   ├── problem_solver.py
│   ├── idea_maker.py
│   └── archiver.py
├── monitoring/
│   ├── cpu.py
│   ├── memory.py
│   ├── gpu.py
│   ├── disk.py
│   ├── network.py
│   └── processes.py
├── optimization/
│   ├── process_control.py
│   ├── startup.py
│   ├── cleanup.py
│   ├── duplicates.py
│   ├── file_organization.py
│   ├── registry.py
│   ├── power_profiles.py
│   └── gaming_profiles.py
├── execution/
│   ├── action_executor.py
│   ├── subprocess_runner.py
│   ├── file_executor.py
│   └── windows_adapters/
├── approval/
│   ├── approval_service.py
│   └── approval_models.py
├── security/
│   ├── protected_targets.py
│   ├── path_validator.py
│   ├── process_validator.py
│   └── secret_store.py
├── rollback/
│   ├── manager.py
│   └── strategies/
├── storage/
│   ├── database.py
│   ├── migrations/
│   └── repositories/
├── ui/
│   ├── screens/
│   ├── components/
│   └── viewmodels/
├── tests/
│   ├── unit/
│   ├── integration/
│   ├── security/
│   └── fixtures/
├── docs/
├── pyproject.toml
└── README.md
```

The UI framework is a technical decision to confirm during implementation. Keep UI code separate from business logic and Windows executors.

## 18. Recommended implementation phases

### Phase 0 — Repository and safety foundation
- Inspect the existing Gemini implementation and current codebase.
- Preserve working functionality.
- Define typed models, configuration, logging, and SQLite migrations.
- Implement permission manager, policy engine, protected targets, and dry-run executor.
- Add tests before enabling mutations.

**Exit criteria:** Read Mode is reliable; write actions are blocked unless explicitly authorized by policy.

### Phase 1 — Monitoring MVP
- CPU, RAM, process, disk, and basic network monitoring.
- GPU metrics where supported.
- 20-minute scheduler and live UI updates.
- Local findings and system health report.

**Exit criteria:** Monitoring works without an AI provider and does not cause noticeable resource overhead.

### Phase 2 — Provider abstraction
- Refactor Gemini behind the common provider interface.
- Add Ollama and one additional cloud provider as reference adapters.
- Add custom OpenAI-compatible integration.
- Add secure credential storage, connection tests, usage reporting, and routing.
- Add remaining provider adapters incrementally.

**Exit criteria:** Provider tests pass; failed providers do not break local monitoring.

### Phase 3 — Agent orchestration
- Implement the 20 logical agent roles.
- Use deterministic agents first.
- Add event bus, task registry, and agent status reporting.
- Implement Chairperson compression and 40-minute synchronization.
- Add bounded event-triggered AI analysis.

**Exit criteria:** Agent activity is observable and no agent can bypass the policy engine.

### Phase 4 — Approval and controlled execution
- Implement action schema and approval center.
- Add process, startup, and safe cleanup actions.
- Implement per-action Agent Mode approvals.
- Add pre-flight and post-action tests.
- Add audit logs and rollback for supported actions.

**Exit criteria:** All mutations are policy-checked, approval-bound, logged, and tested.

### Phase 5 — Advanced optimization
- Duplicate detection and reversible file organization.
- Registry catalog with reviewed settings only.
- Gaming profiles and power-plan suggestions.
- Network optimization suggestions.
- Advanced hardware telemetry.
- Limited hardware tuning integrations only after device-specific safety validation.

**Exit criteria:** Each module has documented supported hardware/OS scope, risk policy, and recovery behavior.

### Phase 6 — Release hardening
- Performance, compatibility, security, and recovery testing.
- Installer and update strategy.
- Documentation and troubleshooting.
- Signed release artifacts where possible.
- User-facing privacy and safety documentation.

## 19. Testing requirements

### Unit tests
- Permission mode enforcement.
- Risk classification.
- Approval payload binding and expiry.
- Path validation and protected directories.
- Process identity validation and PID reuse.
- Provider request/response normalization.
- Token accounting and context deduplication.
- Scheduler overlap and cancellation.

### Integration tests
- Provider connection failures and timeouts.
- Offline local monitoring.
- SQLite migrations and recovery.
- Approval-to-execution workflow.
- File quarantine and restore.
- Registry export and restore for supported test keys.
- Post-action verification.

### Security tests
- Prompt injection in process names, filenames, metadata, and logs.
- Malformed AI JSON and unexpected action types.
- Path traversal and symlink/reparse-point attacks.
- Credential leakage in logs and exceptions.
- Redirects to untrusted hosts.
- Attempts by agents to change permission mode or protected lists.
- Attempts to terminate protected processes.
- Attempts to delete protected files.

### Performance tests
- Idle CPU and RAM overhead.
- Scan duration on large process lists and disks.
- Database growth and retention.
- UI responsiveness during scans.
- Behavior during high CPU/RAM pressure.

## 20. Acceptance criteria

The first production-ready release must satisfy all of the following:

1. Read Mode cannot perform any system mutation.
2. Agent Mode requires explicit approval for every individual mutation.
3. Full-Access is constrained by hard safety rules and configured action eligibility.
4. No agent can directly execute arbitrary AI-generated commands.
5. Local monitoring functions when all AI providers are unavailable.
6. Gemini continues to work through the unified provider interface.
7. Provider credentials are not stored in plaintext.
8. The 20-minute local scan and 40-minute routine AI sync are configurable and do not overlap incorrectly.
9. Unchanged data is not needlessly resent to AI providers.
10. Every action has a risk assessment, pre-flight result, execution record, and post-action result.
11. Protected processes and paths cannot be targeted by normal optimization actions.
12. File deletion is replaced by quarantine/recycle where practical.
13. Duplicate detection uses content hashes, not filenames alone.
14. Registry modifications use a reviewed catalog and verified backup.
15. Unsupported hardware metrics and features fail gracefully.
16. The UI accurately reports agent activity, provider usage, and action status.

## 21. Product analytics and success metrics

Track locally by default:

- Scan completion rate and duration.
- Monitoring CPU/RAM overhead.
- Findings per scan and actionable finding rate.
- Recommendation acceptance/rejection rate.
- Action success and rollback rate.
- False-positive rate for process/file recommendations.
- Provider latency, errors, and usage.
- Estimated versus provider-reported tokens.
- User-reported stability regressions.
- Time to detect and explain a performance issue.

Do not collect or upload telemetry without clear user consent.

## 22. Important engineering constraints

- Prefer Windows-supported APIs and documented mechanisms.
- Use least privilege and request elevation only when needed.
- Avoid permanent deletion by default.
- Do not promise guaranteed performance gains.
- Do not clear standby memory as a routine optimization.
- Do not automatically kill processes based only on high CPU/RAM use.
- Do not apply generic registry “tweaks” without a documented, tested rationale.
- Do not automate voltage or firmware changes in the initial release.
- Do not disable Windows Update, Defender, firewall, recovery, or core services for performance.
- Treat process names, filenames, registry data, and AI output as untrusted input.
- Make local monitoring useful without cloud AI.

## 23. Open technical decisions

Confirm these during repository discovery and Phase 0 rather than guessing:

- Existing UI framework and whether it should be retained.
- Current Gemini SDK, request format, and working features.
- Minimum supported Windows version and architecture.
- GPU telemetry libraries/APIs supported by target hardware.
- Whether the app needs an optional background service for elevated tasks.
- Installer, auto-update, and code-signing approach.
- Exact OpenCode Zen API/authentication contract available at implementation time.
- Cloudflare AI Gateway endpoint and provider routing configuration.
- Which actions qualify for Full-Access autonomous execution.
- Log retention defaults and user privacy controls.

---

## 24. Instructions for the coding agent

When implementing this PRD:

1. **Inspect before changing.** Read the existing repository, identify the current Gemini integration, UI, dependencies, and working features.
2. Produce a concise repository assessment and implementation plan before major refactoring.
3. Preserve existing working behavior unless a migration is explicitly planned.
4. Build in phases. Do not attempt all 20 agents and all providers in one untested change.
5. Implement the policy engine and action executor before enabling any write operation.
6. Start with Read Mode and dry-run execution.
7. Use typed schemas and strict validation for every AI proposal.
8. Never execute raw shell commands returned by an LLM.
9. Add unit and integration tests for every permission and safety boundary.
10. Use mocks/fakes for destructive operations during development and CI.
11. Keep API keys out of source code, `.env` commits, logs, screenshots, and crash reports.
12. Document unsupported features honestly; do not create fake telemetry or simulated success states.
13. Keep each provider adapter isolated and testable.
14. Keep agent roles modular, but use deterministic Python logic wherever an LLM adds no meaningful value.
15. Before enabling a new mutation type, document its preconditions, risk, approval rule, protected targets, and rollback strategy.
16. Update this PRD or an implementation-status document when a requirement changes.

**Definition of done:** A feature is not complete merely because its UI exists. It must have working implementation, policy enforcement, error handling, tests, and accurate user-facing status.
