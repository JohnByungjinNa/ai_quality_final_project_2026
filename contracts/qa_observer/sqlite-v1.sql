-- FUTURE EXPANSION CONTRACT ONLY.
-- The MVP uses JSONL event logs and daily aggregate CSV files.
-- Apply this DDL only after a separately approved SQLite migration task.
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS schema_migrations (
    version INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    applied_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL CHECK (event_type IN (
        'api.request.completed',
        'llm.call.completed',
        'rag.search.completed',
        'quality.evaluation.completed',
        'test.run.completed',
        'safety.violation.detected',
        'defect.changed',
        'collector.sync.completed'
    )),
    schema_version INTEGER NOT NULL DEFAULT 1 CHECK (schema_version = 1),
    occurred_at_utc TEXT NOT NULL,
    received_at_utc TEXT NOT NULL,
    environment TEXT NOT NULL,
    service TEXT NOT NULL,
    source_component TEXT NOT NULL,
    source_instance TEXT,
    trace_id TEXT,
    run_id TEXT,
    case_id TEXT,
    dedup_key TEXT NOT NULL UNIQUE,
    payload_json TEXT NOT NULL CHECK (json_valid(payload_json)),
    created_at_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_events_type_occurred
    ON events (event_type, occurred_at_utc);
CREATE INDEX IF NOT EXISTS idx_events_filter
    ON events (environment, service, occurred_at_utc);
CREATE INDEX IF NOT EXISTS idx_events_run_case
    ON events (run_id, case_id);
CREATE INDEX IF NOT EXISTS idx_events_trace
    ON events (trace_id);

CREATE TABLE IF NOT EXISTS api_request_events (
    event_id TEXT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
    method TEXT NOT NULL,
    route_template TEXT NOT NULL,
    status_code INTEGER NOT NULL CHECK (status_code BETWEEN 100 AND 599),
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    timeout INTEGER NOT NULL DEFAULT 0 CHECK (timeout IN (0, 1)),
    error_type TEXT
);

CREATE INDEX IF NOT EXISTS idx_api_request_status
    ON api_request_events (status_code, timeout);

CREATE TABLE IF NOT EXISTS llm_price_snapshots (
    price_snapshot_id TEXT PRIMARY KEY,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    currency TEXT NOT NULL,
    input_per_million TEXT NOT NULL,
    output_per_million TEXT NOT NULL,
    cached_input_per_million TEXT,
    exchange_rate_to_krw TEXT NOT NULL,
    effective_from_utc TEXT NOT NULL,
    effective_to_utc TEXT,
    source_url TEXT,
    fetched_at_utc TEXT NOT NULL,
    UNIQUE (provider, model, effective_from_utc)
);

CREATE TABLE IF NOT EXISTS llm_usage_events (
    event_id TEXT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
    provider TEXT NOT NULL,
    model TEXT NOT NULL,
    operation TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('success', 'error')),
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    cached_input_tokens INTEGER NOT NULL DEFAULT 0 CHECK (cached_input_tokens >= 0),
    reasoning_tokens INTEGER NOT NULL DEFAULT 0 CHECK (reasoning_tokens >= 0),
    total_tokens INTEGER NOT NULL CHECK (total_tokens >= 0),
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    prompt_fingerprint TEXT,
    prompt_chars INTEGER CHECK (prompt_chars >= 0),
    response_fingerprint TEXT,
    response_chars INTEGER CHECK (response_chars >= 0),
    price_snapshot_id TEXT REFERENCES llm_price_snapshots(price_snapshot_id),
    input_cost_micros_krw INTEGER CHECK (input_cost_micros_krw >= 0),
    output_cost_micros_krw INTEGER CHECK (output_cost_micros_krw >= 0),
    total_cost_micros_krw INTEGER CHECK (total_cost_micros_krw >= 0),
    error_type TEXT
);

CREATE INDEX IF NOT EXISTS idx_llm_usage_filter
    ON llm_usage_events (provider, model, operation, status);

CREATE TABLE IF NOT EXISTS rag_search_events (
    event_id TEXT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
    query_fingerprint TEXT,
    query_chars INTEGER NOT NULL CHECK (query_chars >= 0),
    top_k INTEGER NOT NULL CHECK (top_k > 0),
    result_count INTEGER NOT NULL CHECK (result_count >= 0),
    no_result INTEGER NOT NULL CHECK (no_result IN (0, 1)),
    duration_ms INTEGER NOT NULL CHECK (duration_ms >= 0),
    expected_document_fingerprint TEXT,
    top_k_hit INTEGER CHECK (top_k_hit IN (0, 1))
);

CREATE TABLE IF NOT EXISTS rag_search_results (
    event_id TEXT NOT NULL REFERENCES rag_search_events(event_id) ON DELETE CASCADE,
    rank INTEGER NOT NULL CHECK (rank > 0),
    document_fingerprint TEXT,
    chunk_fingerprint TEXT,
    score REAL NOT NULL,
    PRIMARY KEY (event_id, rank)
);

CREATE INDEX IF NOT EXISTS idx_rag_search_quality
    ON rag_search_events (no_result, top_k_hit, duration_ms);

CREATE TABLE IF NOT EXISTS test_runs (
    run_id TEXT PRIMARY KEY,
    started_at_utc TEXT NOT NULL,
    ended_at_utc TEXT,
    duration_ms INTEGER CHECK (duration_ms >= 0),
    environment TEXT NOT NULL,
    service TEXT NOT NULL,
    criteria_stage TEXT NOT NULL,
    pass_count INTEGER NOT NULL DEFAULT 0 CHECK (pass_count >= 0),
    fail_count INTEGER NOT NULL DEFAULT 0 CHECK (fail_count >= 0),
    error_count INTEGER NOT NULL DEFAULT 0 CHECK (error_count >= 0),
    total_count INTEGER NOT NULL DEFAULT 0 CHECK (total_count >= 0),
    source_manifest_path TEXT,
    synced_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS test_case_results (
    run_id TEXT NOT NULL REFERENCES test_runs(run_id) ON DELETE CASCADE,
    case_id TEXT NOT NULL,
    category TEXT,
    test_type TEXT,
    rule_decision TEXT CHECK (rule_decision IN ('PASS', 'REVIEW', 'FAIL', 'ERROR')),
    api_decision TEXT CHECK (api_decision IN ('PASS', 'REVIEW', 'FAIL', 'ERROR')),
    question_fingerprint TEXT,
    response_fingerprint TEXT,
    error_type TEXT,
    PRIMARY KEY (run_id, case_id)
);

CREATE INDEX IF NOT EXISTS idx_test_case_decisions
    ON test_case_results (api_decision, rule_decision);

CREATE TABLE IF NOT EXISTS quality_evaluations (
    evaluation_id TEXT PRIMARY KEY,
    event_id TEXT NOT NULL UNIQUE REFERENCES events(event_id) ON DELETE CASCADE,
    run_id TEXT,
    case_id TEXT,
    evaluator_type TEXT NOT NULL CHECK (evaluator_type IN ('rule', 'llm_judge', 'human')),
    overall_decision TEXT NOT NULL CHECK (overall_decision IN ('PASS', 'REVIEW', 'FAIL', 'ERROR')),
    summary_code TEXT,
    safety_violation_severity TEXT CHECK (
        safety_violation_severity IS NULL OR
        safety_violation_severity IN ('low', 'medium', 'high', 'critical')
    )
);

CREATE TABLE IF NOT EXISTS quality_metric_scores (
    evaluation_id TEXT NOT NULL REFERENCES quality_evaluations(evaluation_id) ON DELETE CASCADE,
    metric_name TEXT NOT NULL,
    score REAL,
    scale_min REAL NOT NULL DEFAULT 1,
    scale_max REAL NOT NULL DEFAULT 5,
    evaluated INTEGER NOT NULL DEFAULT 1 CHECK (evaluated IN (0, 1)),
    PRIMARY KEY (evaluation_id, metric_name),
    CHECK (score IS NULL OR score BETWEEN scale_min AND scale_max)
);

CREATE INDEX IF NOT EXISTS idx_quality_metric
    ON quality_metric_scores (metric_name, evaluated, score);

CREATE TABLE IF NOT EXISTS safety_violations (
    event_id TEXT PRIMARY KEY REFERENCES events(event_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    action TEXT NOT NULL,
    blocked INTEGER NOT NULL DEFAULT 0 CHECK (blocked IN (0, 1)),
    content_fingerprint TEXT,
    policy_version TEXT
);

CREATE INDEX IF NOT EXISTS idx_safety_severity
    ON safety_violations (severity, blocked);

CREATE TABLE IF NOT EXISTS defects (
    defect_id TEXT PRIMARY KEY,
    event_id TEXT REFERENCES events(event_id) ON DELETE SET NULL,
    run_id TEXT,
    case_id TEXT,
    defect_type TEXT NOT NULL,
    severity TEXT NOT NULL CHECK (severity IN ('low', 'medium', 'high', 'critical')),
    status TEXT NOT NULL CHECK (status IN ('open', 'investigating', 'resolved', 'closed')),
    summary_code TEXT NOT NULL,
    external_system TEXT,
    external_issue_key TEXT,
    opened_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL,
    resolved_at_utc TEXT
);

CREATE INDEX IF NOT EXISTS idx_defects_status
    ON defects (status, severity, updated_at_utc);

CREATE TABLE IF NOT EXISTS collector_checkpoints (
    source_name TEXT PRIMARY KEY,
    cursor_value TEXT,
    last_started_at_utc TEXT,
    last_success_at_utc TEXT,
    last_error_at_utc TEXT,
    last_error_type TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0 CHECK (consecutive_failures >= 0),
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS retention_policies (
    data_class TEXT PRIMARY KEY,
    retention_days INTEGER NOT NULL CHECK (retention_days > 0),
    description TEXT NOT NULL
);

INSERT OR IGNORE INTO retention_policies (data_class, retention_days, description) VALUES
    ('api_llm_rag_detail', 90, 'API, LLM, RAG 상세 이벤트와 fingerprint'),
    ('collector_events', 30, '수집기 실행 및 오류 이벤트'),
    ('test_quality_results', 365, '테스트 실행, 케이스 결과, 품질 평가'),
    ('safety_events', 365, '안전성 위반 메타데이터'),
    ('defects', 730, '결함 상태 및 외부 이슈 연결'),
    ('price_snapshots', 1095, '비용 재현을 위한 모델 단가 및 환율 snapshot'),
    ('aggregates', 730, '일별 KPI 집계');

INSERT OR IGNORE INTO schema_migrations (version, name, applied_at_utc)
VALUES (1, 'initial qa-observer schema', strftime('%Y-%m-%dT%H:%M:%fZ', 'now'));
