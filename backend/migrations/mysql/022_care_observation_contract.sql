CREATE TABLE IF NOT EXISTS care_capability_configs (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(64) NOT NULL,
  child_id VARCHAR(64) NOT NULL,
  device_id VARCHAR(64) NOT NULL DEFAULT '',
  scenario VARCHAR(64) NOT NULL,
  enabled TINYINT NOT NULL DEFAULT 1,
  day_types TEXT NOT NULL,
  time_windows TEXT NOT NULL,
  min_observation_seconds INTEGER NOT NULL DEFAULT 20,
  confidence_threshold DECIMAL(5,4) NOT NULL DEFAULT 0.7200,
  cooldown_seconds INTEGER NOT NULL DEFAULT 900,
  daily_limit INTEGER NOT NULL DEFAULT 4,
  parent_notify_threshold INTEGER NOT NULL DEFAULT 3,
  allow_speaker TINYINT NOT NULL DEFAULT 1,
  record_only TINYINT NOT NULL DEFAULT 0,
  prompt_id VARCHAR(128) NOT NULL,
  prompt_version VARCHAR(32) NOT NULL DEFAULT 'v1',
  fallback_templates TEXT NOT NULL,
  last_reminded_at BIGINT,
  daily_reminder_count INTEGER NOT NULL DEFAULT 0,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

CREATE UNIQUE INDEX uniq_care_capability_target
  ON care_capability_configs(family_id, child_id, device_id, scenario);

CREATE INDEX idx_care_capability_family_child
  ON care_capability_configs(family_id, child_id, enabled);

CREATE TABLE IF NOT EXISTS care_routine_windows (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(64) NOT NULL,
  child_id VARCHAR(64) NOT NULL,
  day_type VARCHAR(64) NOT NULL,
  window_type VARCHAR(128) NOT NULL,
  start_time VARCHAR(16) NOT NULL,
  end_time VARCHAR(16) NOT NULL,
  enabled TINYINT NOT NULL DEFAULT 1,
  timezone VARCHAR(64) NOT NULL DEFAULT 'Asia/Shanghai',
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

CREATE UNIQUE INDEX uniq_care_routine_window_child_type
  ON care_routine_windows(family_id, child_id, day_type, window_type);

CREATE INDEX idx_care_routine_windows_family_child
  ON care_routine_windows(family_id, child_id, day_type, enabled);

CREATE TABLE IF NOT EXISTS camera_observation_events (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(64) NOT NULL,
  child_id VARCHAR(64) NOT NULL,
  device_id VARCHAR(64) NOT NULL DEFAULT '',
  scenario VARCHAR(64) NOT NULL,
  observed_at BIGINT NOT NULL,
  confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
  evidence_type VARCHAR(128) NOT NULL DEFAULT 'none',
  parent_summary TEXT,
  raw_detail_json TEXT,
  source VARCHAR(128) NOT NULL DEFAULT 'camera_adapter',
  source_event_id VARCHAR(128),
  source_type VARCHAR(64),
  source_id VARCHAR(128),
  task_id VARCHAR(64),
  created_at BIGINT NOT NULL
);

CREATE UNIQUE INDEX uniq_camera_observation_source_event
  ON camera_observation_events(family_id, source, source_event_id);

CREATE INDEX idx_camera_observations_family_child
  ON camera_observation_events(family_id, child_id, scenario, created_at);

CREATE INDEX idx_camera_observations_device_created
  ON camera_observation_events(device_id, created_at);

CREATE INDEX idx_camera_observations_source
  ON camera_observation_events(source_type, source_id);

CREATE TABLE IF NOT EXISTS behavior_signals (
  id VARCHAR(255) PRIMARY KEY,
  observation_event_id VARCHAR(64) NOT NULL,
  family_id VARCHAR(64) NOT NULL,
  child_id VARCHAR(64) NOT NULL,
  device_id VARCHAR(64) NOT NULL DEFAULT '',
  scenario VARCHAR(64) NOT NULL,
  signal_type VARCHAR(128) NOT NULL,
  signal_value VARCHAR(128) NOT NULL,
  confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
  duration_seconds INTEGER NOT NULL DEFAULT 0,
  metadata_json TEXT,
  created_at BIGINT NOT NULL
);

CREATE INDEX idx_behavior_signals_observation
  ON behavior_signals(observation_event_id);

CREATE INDEX idx_behavior_signals_family_child
  ON behavior_signals(family_id, child_id, scenario, created_at);

CREATE TABLE IF NOT EXISTS current_behavior_states (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(64) NOT NULL,
  child_id VARCHAR(64) NOT NULL,
  device_id VARCHAR(64) NOT NULL DEFAULT '',
  scenario VARCHAR(64) NOT NULL,
  state VARCHAR(128) NOT NULL,
  status VARCHAR(64) NOT NULL DEFAULT 'active',
  started_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  last_observed_at BIGINT NOT NULL,
  confidence DECIMAL(5,4) NOT NULL DEFAULT 0.0000,
  consecutive_seconds INTEGER NOT NULL DEFAULT 0,
  parent_summary TEXT,
  raw_detail_json TEXT
);

CREATE UNIQUE INDEX uniq_current_behavior_state_active
  ON current_behavior_states(family_id, child_id, device_id, scenario, state);

CREATE INDEX idx_current_behavior_states_family_child
  ON current_behavior_states(family_id, child_id, scenario, status, updated_at);

CREATE TABLE IF NOT EXISTS reminder_decisions (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(64) NOT NULL,
  child_id VARCHAR(64) NOT NULL,
  device_id VARCHAR(64) NOT NULL DEFAULT '',
  scenario VARCHAR(64) NOT NULL,
  observation_event_id VARCHAR(64),
  behavior_state_id VARCHAR(64),
  source_type VARCHAR(64),
  source_id VARCHAR(128),
  task_id VARCHAR(64),
  decision VARCHAR(128) NOT NULL,
  reason VARCHAR(255) NOT NULL,
  reminder_level VARCHAR(64) NOT NULL DEFAULT 'gentle',
  cooldown_until BIGINT,
  should_speak TINYINT NOT NULL DEFAULT 0,
  should_notify_parent TINYINT NOT NULL DEFAULT 0,
  policy_snapshot_json TEXT,
  created_at BIGINT NOT NULL
);

CREATE INDEX idx_reminder_decisions_family_child
  ON reminder_decisions(family_id, child_id, scenario, created_at);

CREATE INDEX idx_reminder_decisions_observation
  ON reminder_decisions(observation_event_id);

CREATE INDEX idx_reminder_decisions_source
  ON reminder_decisions(source_type, source_id);

CREATE TABLE IF NOT EXISTS reminder_events (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(64) NOT NULL,
  child_id VARCHAR(64) NOT NULL,
  device_id VARCHAR(64) NOT NULL DEFAULT '',
  scenario VARCHAR(64) NOT NULL,
  reminder_decision_id VARCHAR(64),
  event_source VARCHAR(64) NOT NULL DEFAULT 'care_policy',
  is_test TINYINT NOT NULL DEFAULT 0,
  source_type VARCHAR(64),
  source_id VARCHAR(128),
  task_id VARCHAR(64),
  prompt_id VARCHAR(128),
  prompt_version VARCHAR(32),
  text TEXT NOT NULL,
  tone VARCHAR(64) NOT NULL DEFAULT 'warm',
  text_source VARCHAR(64) NOT NULL DEFAULT 'fallback',
  delivery_status VARCHAR(128) NOT NULL DEFAULT 'generated',
  command_id VARCHAR(64),
  fallback_used TINYINT NOT NULL DEFAULT 0,
  generated_at BIGINT NOT NULL,
  delivered_at BIGINT,
  failure_reason TEXT,
  created_at BIGINT NOT NULL
);

CREATE INDEX idx_reminder_events_family_child
  ON reminder_events(family_id, child_id, scenario, is_test, created_at);

CREATE INDEX idx_reminder_events_delivery
  ON reminder_events(scenario, delivery_status, generated_at);

CREATE INDEX idx_reminder_events_source
  ON reminder_events(source_type, source_id);

CREATE TABLE IF NOT EXISTS review_items (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(64) NOT NULL,
  child_id VARCHAR(64),
  device_id VARCHAR(64) NOT NULL DEFAULT '',
  domain VARCHAR(64) NOT NULL,
  scenario VARCHAR(64),
  item_type VARCHAR(128) NOT NULL,
  source_type VARCHAR(64),
  source_id VARCHAR(128),
  priority VARCHAR(32) NOT NULL DEFAULT 'normal',
  status VARCHAR(64) NOT NULL DEFAULT 'pending',
  summary TEXT NOT NULL,
  related_observation_id VARCHAR(64),
  related_reminder_id VARCHAR(64),
  task_id VARCHAR(64),
  due_at BIGINT,
  created_at BIGINT NOT NULL,
  resolved_at BIGINT,
  resolved_by VARCHAR(255)
);

CREATE INDEX idx_review_items_family_child
  ON review_items(family_id, child_id, status, created_at);

CREATE INDEX idx_review_items_source
  ON review_items(domain, source_type, source_id);

CREATE TABLE IF NOT EXISTS audit_events (
  id VARCHAR(255) PRIMARY KEY,
  audit_domain VARCHAR(64) NOT NULL,
  actor_type VARCHAR(64) NOT NULL DEFAULT 'internal_service',
  actor_id VARCHAR(128),
  route VARCHAR(128) NOT NULL,
  source_ip VARCHAR(128),
  source_name VARCHAR(128),
  accepted TINYINT NOT NULL DEFAULT 0,
  reason VARCHAR(255) NOT NULL,
  payload_ref VARCHAR(255),
  created_at BIGINT NOT NULL
);

CREATE INDEX idx_audit_events_route_created
  ON audit_events(audit_domain, route, created_at);

CREATE INDEX idx_audit_events_source_created
  ON audit_events(source_ip, created_at);
