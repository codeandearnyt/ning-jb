"""Initial schema.

High-volume tables (``process_observations``, ``system_snapshots``) are indexed
by time and by parent run so retention sweeps stay cheap. Secrets are never
stored here: ``provider_configs.secret_ref`` is a name, not a value.
"""

from __future__ import annotations

INITIAL_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE provider_configs (
        id TEXT PRIMARY KEY,
        name TEXT NOT NULL UNIQUE,
        kind TEXT NOT NULL,
        base_url TEXT,
        model_id TEXT,
        auth_scheme TEXT,
        extra_json TEXT NOT NULL DEFAULT '{}',
        enabled INTEGER NOT NULL DEFAULT 1,
        is_local INTEGER NOT NULL DEFAULT 0,
        priority INTEGER NOT NULL DEFAULT 100,
        fallback_ok INTEGER NOT NULL DEFAULT 0,
        timeout_s REAL NOT NULL DEFAULT 60,
        max_retries INTEGER NOT NULL DEFAULT 2,
        max_output_tokens INTEGER,
        secret_ref TEXT,
        last_test_at TEXT,
        last_test_status TEXT,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE provider_usage (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        provider_id TEXT NOT NULL REFERENCES provider_configs(id) ON DELETE CASCADE,
        ts TEXT NOT NULL,
        request_kind TEXT NOT NULL,
        model TEXT,
        input_tokens INTEGER,
        output_tokens INTEGER,
        usage_source TEXT NOT NULL DEFAULT 'unavailable',
        latency_ms REAL,
        status TEXT NOT NULL,
        error_class TEXT,
        cost_micros INTEGER
    )
    """,
    "CREATE INDEX idx_provider_usage_ts ON provider_usage (ts)",
    "CREATE INDEX idx_provider_usage_provider ON provider_usage (provider_id, ts)",
    """
    CREATE TABLE scan_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        trigger TEXT NOT NULL,
        status TEXT NOT NULL,
        duration_ms INTEGER,
        findings_count INTEGER NOT NULL DEFAULT 0,
        error TEXT
    )
    """,
    "CREATE INDEX idx_scan_runs_started ON scan_runs (started_at)",
    """
    CREATE TABLE system_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_run_id INTEGER REFERENCES scan_runs(id) ON DELETE CASCADE,
        ts TEXT NOT NULL,
        cpu_json TEXT,
        mem_json TEXT,
        gpu_json TEXT,
        disk_json TEXT,
        net_json TEXT,
        health_json TEXT
    )
    """,
    "CREATE INDEX idx_snapshots_ts ON system_snapshots (ts)",
    "CREATE INDEX idx_snapshots_run ON system_snapshots (scan_run_id)",
    """
    CREATE TABLE process_observations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_id INTEGER NOT NULL REFERENCES system_snapshots(id) ON DELETE CASCADE,
        pid INTEGER NOT NULL,
        create_time REAL NOT NULL,
        name TEXT NOT NULL,
        exe_path TEXT,
        username TEXT,
        cpu_pct REAL,
        rss_bytes INTEGER,
        private_bytes INTEGER,
        parent_pid INTEGER,
        signature_status TEXT
    )
    """,
    "CREATE INDEX idx_process_obs_snapshot ON process_observations (snapshot_id)",
    "CREATE INDEX idx_process_obs_name ON process_observations (name)",
    """
    CREATE TABLE agent_runs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        agent_id TEXT NOT NULL,
        scan_run_id INTEGER REFERENCES scan_runs(id) ON DELETE SET NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        execution_kind TEXT NOT NULL,
        status TEXT NOT NULL,
        input_hash TEXT,
        provider_id TEXT,
        model TEXT,
        tokens_in INTEGER,
        tokens_out INTEGER,
        output_summary TEXT,
        error TEXT
    )
    """,
    "CREATE INDEX idx_agent_runs_started ON agent_runs (started_at)",
    "CREATE INDEX idx_agent_runs_agent ON agent_runs (agent_id, started_at)",
    "CREATE INDEX idx_agent_runs_input_hash ON agent_runs (input_hash)",
    """
    CREATE TABLE findings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        scan_run_id INTEGER REFERENCES scan_runs(id) ON DELETE CASCADE,
        agent_id TEXT NOT NULL,
        category TEXT NOT NULL,
        severity TEXT NOT NULL,
        title TEXT NOT NULL,
        evidence_json TEXT NOT NULL DEFAULT '{}',
        fingerprint TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX idx_findings_fingerprint ON findings (fingerprint)",
    "CREATE INDEX idx_findings_scan ON findings (scan_run_id)",
    """
    CREATE TABLE recommendations (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        finding_id INTEGER REFERENCES findings(id) ON DELETE CASCADE,
        action_spec_json TEXT NOT NULL DEFAULT '{}',
        impact_estimate TEXT,
        confidence REAL,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE actions (
        id TEXT PRIMARY KEY,
        action_type TEXT NOT NULL,
        target_kind TEXT NOT NULL,
        target_json TEXT NOT NULL,
        params_json TEXT NOT NULL DEFAULT '{}',
        risk TEXT NOT NULL,
        reversible INTEGER NOT NULL DEFAULT 0,
        rollback_plan_json TEXT,
        payload_hash TEXT,
        state TEXT NOT NULL,
        decision_json TEXT,
        created_at TEXT NOT NULL,
        expires_at TEXT
    )
    """,
    "CREATE INDEX idx_actions_created ON actions (created_at)",
    "CREATE INDEX idx_actions_state ON actions (state)",
    "CREATE INDEX idx_actions_attention ON actions (created_at DESC)",
    """
    CREATE TABLE approval_requests (
        id TEXT PRIMARY KEY,
        action_id TEXT NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
        requested_by TEXT NOT NULL,
        mode TEXT NOT NULL,
        payload_hash TEXT NOT NULL,
        nonce TEXT NOT NULL,
        expires_at TEXT NOT NULL,
        state TEXT NOT NULL,
        created_at TEXT NOT NULL
    )
    """,
    "CREATE INDEX idx_approval_requests_action ON approval_requests (action_id)",
    "CREATE INDEX idx_approval_requests_state ON approval_requests (state, expires_at)",
    """
    CREATE TABLE approval_decisions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        request_id TEXT NOT NULL REFERENCES approval_requests(id) ON DELETE CASCADE,
        decision TEXT NOT NULL,
        decided_at TEXT NOT NULL,
        note TEXT
    )
    """,
    """
    CREATE TABLE action_results (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_id TEXT NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        status TEXT NOT NULL,
        preflight_json TEXT,
        postflight_json TEXT,
        error TEXT
    )
    """,
    "CREATE INDEX idx_action_results_action ON action_results (action_id)",
    """
    CREATE TABLE rollback_records (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        action_id TEXT NOT NULL REFERENCES actions(id) ON DELETE CASCADE,
        strategy TEXT NOT NULL,
        manifest_path TEXT,
        state TEXT NOT NULL,
        verified_at TEXT
    )
    """,
    """
    CREATE TABLE audit_events (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        ts TEXT NOT NULL,
        actor TEXT NOT NULL,
        event_type TEXT NOT NULL,
        subject_id TEXT,
        detail_json TEXT NOT NULL DEFAULT '{}',
        redacted INTEGER NOT NULL DEFAULT 1
    )
    """,
    "CREATE INDEX idx_audit_ts ON audit_events (ts DESC)",
    "CREATE INDEX idx_audit_event_type ON audit_events (event_type, ts DESC)",
    """
    CREATE TABLE gaming_profiles (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL UNIQUE,
        rules_json TEXT NOT NULL DEFAULT '{}',
        enabled INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    )
    """,
    """
    CREATE TABLE file_scan_sessions (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        root TEXT NOT NULL,
        kind TEXT NOT NULL,
        started_at TEXT NOT NULL,
        finished_at TEXT,
        files_seen INTEGER NOT NULL DEFAULT 0,
        bytes_seen INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL,
        cursor TEXT
    )
    """,
    """
    CREATE TABLE metric_aggregates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bucket TEXT NOT NULL,
        entity TEXT NOT NULL,
        key TEXT NOT NULL,
        min_value REAL,
        max_value REAL,
        avg_value REAL,
        samples INTEGER NOT NULL DEFAULT 0
    )
    """,
    "CREATE UNIQUE INDEX idx_metric_aggregates_unique ON metric_aggregates (bucket, entity, key)",
)
