-- Additive only. Apply through the reviewed migration workflow before enabling
-- LEARNING_REVIEW_ENABLED. No existing marks or classroom records are rewritten.
CREATE TABLE IF NOT EXISTS learning_answer_events (
  id CHAR(64) PRIMARY KEY,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  source_kind VARCHAR(32) NOT NULL,
  source_id VARCHAR(255) NOT NULL,
  event_key VARCHAR(255) NOT NULL,
  knowledge_id VARCHAR(255) NOT NULL,
  knowledge_label VARCHAR(255) NOT NULL,
  subject VARCHAR(32) NOT NULL,
  grade_code VARCHAR(32) NOT NULL,
  question_fingerprint CHAR(64) NOT NULL,
  question_json JSON NOT NULL,
  answer_json JSON NOT NULL,
  correct TINYINT,
  independent TINYINT,
  hint_used TINYINT,
  adult_help TINYINT,
  attempt INT NOT NULL,
  confirmed TINYINT NOT NULL,
  confidence DOUBLE,
  diagnosis_json JSON,
  payload_sha256 CHAR(64) NOT NULL,
  occurred_at BIGINT NOT NULL,
  revoked_at BIGINT,
  revoke_reason VARCHAR(255),
  INDEX idx_answer_child (family_id,child_id,occurred_at),
  INDEX idx_answer_source (family_id,child_id,source_kind,source_id),
  INDEX idx_answer_knowledge (child_id,knowledge_id,revoked_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS learning_review_preferences (
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  preferences_json JSON NOT NULL,
  revision INT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (family_id,child_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS learning_review_runs (
  id VARCHAR(80) PRIMARY KEY,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  week_start VARCHAR(10) NOT NULL,
  task_type VARCHAR(32) NOT NULL DEFAULT 'weekend_review',
  task_id VARCHAR(255) NOT NULL UNIQUE,
  grade_code VARCHAR(32) NOT NULL,
  grade_revision INT NOT NULL,
  status VARCHAR(32) NOT NULL,
  revision INT NOT NULL DEFAULT 0,
  appointment_revision INT NOT NULL DEFAULT 0,
  scheduled_at BIGINT,
  reminder_expires_at BIGINT,
  reminder_status VARCHAR(40) NOT NULL,
  current_index INT NOT NULL DEFAULT 0,
  total_questions INT NOT NULL,
  correct_count INT NOT NULL DEFAULT 0,
  independent_correct_count INT NOT NULL DEFAULT 0,
  estimated_seconds INT NOT NULL,
  coverage_json JSON NOT NULL,
  policy_json JSON NOT NULL,
  created_at BIGINT NOT NULL,
  started_at BIGINT,
  completed_at BIGINT,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_review_week (family_id,child_id,week_start,task_type),
  INDEX idx_review_active (family_id,child_id,status),
  INDEX idx_review_due (status,scheduled_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS learning_review_items (
  run_id VARCHAR(80) NOT NULL,
  ordinal INT NOT NULL,
  question_id CHAR(64) NOT NULL,
  snapshot_json JSON NOT NULL,
  snapshot_sha256 CHAR(64) NOT NULL,
  knowledge_id VARCHAR(255) NOT NULL,
  evidence_mode VARCHAR(32) NOT NULL,
  exposure_at BIGINT,
  hint_level INT NOT NULL DEFAULT 0,
  explanation_seen TINYINT NOT NULL DEFAULT 0,
  answer_json JSON,
  answer_sha256 CHAR(64),
  feedback_json JSON,
  answered_at BIGINT,
  PRIMARY KEY (run_id,ordinal),
  UNIQUE KEY uq_review_question (run_id,question_id),
  CONSTRAINT fk_review_item_run FOREIGN KEY (run_id) REFERENCES learning_review_runs(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS learning_review_requests (
  run_id VARCHAR(80) NOT NULL,
  request_id VARCHAR(128) NOT NULL,
  payload_sha256 CHAR(64) NOT NULL,
  created_at BIGINT NOT NULL,
  PRIMARY KEY (run_id,request_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS learning_review_reminders (
  run_id VARCHAR(80) NOT NULL,
  appointment_revision INT NOT NULL,
  local_day VARCHAR(10) NOT NULL,
  status VARCHAR(40) NOT NULL,
  receipt_json JSON,
  attempted_at BIGINT NOT NULL,
  PRIMARY KEY (run_id,appointment_revision),
  INDEX idx_review_reminder_day (local_day,run_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
