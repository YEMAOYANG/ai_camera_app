-- Add every persisted content-stage field independently so a MySQL DDL
-- autocommit interruption can resume without replaying an already-added field.
SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN content_target_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'content_target_count'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN content_candidate_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'content_candidate_count'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN content_failed_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'content_failed_count'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN content_canary_target_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'content_canary_target_count'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN content_canary_candidate_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'content_canary_candidate_count'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN content_canary_failed_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'content_canary_failed_count'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN content_canary_passed_at BIGINT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'content_canary_passed_at'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN content_generation_completed_at BIGINT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'content_generation_completed_at'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN retry_reason_code VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'retry_reason_code'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN retry_message_safe VARCHAR(512)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'retry_message_safe'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN work_unit_kind VARCHAR(32)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'work_unit_kind'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN bound_catalog_item_id VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'bound_catalog_item_id'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN bound_content_attempt_ordinal INTEGER',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'bound_content_attempt_ordinal'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN bound_content_phase VARCHAR(64)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'bound_content_phase'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN stage_progress_json LONGTEXT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'stage_progress_json'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_jobs ADD COLUMN execution_mode VARCHAR(32)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_jobs'
    AND COLUMN_NAME = 'execution_mode'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_jobs ADD COLUMN content_manifest_version VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_jobs'
    AND COLUMN_NAME = 'content_manifest_version'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_jobs ADD COLUMN canary_manifest_json LONGTEXT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_jobs'
    AND COLUMN_NAME = 'canary_manifest_json'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_jobs ADD COLUMN stage_ceiling VARCHAR(64)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_jobs'
    AND COLUMN_NAME = 'stage_ceiling'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN execution_mode_snapshot VARCHAR(32)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'execution_mode_snapshot'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_manifest_version_snapshot VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_manifest_version_snapshot'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN subject_ordinal INTEGER',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'subject_ordinal'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN boundary_ordinal INTEGER',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'boundary_ordinal'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_phase VARCHAR(64)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_phase'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_gate_status VARCHAR(32)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_gate_status'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_gate_attempt_count INTEGER',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_gate_attempt_count'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_gate_passed_at BIGINT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_gate_passed_at'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_validation_contract_version VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_validation_contract_version'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_receipt_hash CHAR(64)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_receipt_hash'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_lease_token VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_lease_token'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_lease_expires_at BIGINT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_lease_expires_at'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_heartbeat_at BIGINT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_heartbeat_at'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_attempt_started_at BIGINT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_attempt_started_at'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_provider_attempt_hard_deadline_at BIGINT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_provider_attempt_hard_deadline_at'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_work_unit_deadline_at BIGINT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_work_unit_deadline_at'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

SET @column_ddl = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD COLUMN content_claim_attempt_ordinal INTEGER',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND COLUMN_NAME = 'content_claim_attempt_ordinal'
);
PREPARE column_ddl_stmt FROM @column_ddl;
EXECUTE column_ddl_stmt;
DEALLOCATE PREPARE column_ddl_stmt;

-- Create a complete table on a normal upgrade, then independently repair every
-- column below when a previous run stopped after creating only part of it.
CREATE TABLE IF NOT EXISTS learning_course_provider_dispatches (
  id VARCHAR(128) PRIMARY KEY,
  build_item_id VARCHAR(128) NOT NULL,
  logical_attempt INTEGER NOT NULL,
  phase VARCHAR(64) NOT NULL,
  phase_ordinal INTEGER NOT NULL,
  generation_request_id VARCHAR(128) NOT NULL,
  item_lease_token VARCHAR(128) NOT NULL,
  provider VARCHAR(128) NOT NULL,
  model VARCHAR(128) NOT NULL,
  profile VARCHAR(128) NOT NULL,
  input_sha256 CHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  checkpoint_json LONGTEXT,
  output_sha256 CHAR(64),
  attempt_started_at BIGINT NOT NULL,
  attempt_hard_deadline_at BIGINT NOT NULL,
  provider_request_id_hash CHAR(64),
  input_tokens INTEGER,
  output_tokens INTEGER,
  billing_evidence VARCHAR(32),
  safe_error_code VARCHAR(128),
  dispatched_at BIGINT NOT NULL,
  completed_at BIGINT
);

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN build_item_id VARCHAR(128) NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'build_item_id'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN logical_attempt INTEGER NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'logical_attempt'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN phase VARCHAR(64) NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'phase'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN phase_ordinal INTEGER NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'phase_ordinal'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN generation_request_id VARCHAR(128) NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'generation_request_id'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN item_lease_token VARCHAR(128) NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'item_lease_token'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN provider VARCHAR(128) NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'provider'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN model VARCHAR(128) NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'model'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN profile VARCHAR(128) NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'profile'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN input_sha256 CHAR(64) NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'input_sha256'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN status VARCHAR(32) NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'status'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN checkpoint_json LONGTEXT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'checkpoint_json'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN output_sha256 CHAR(64)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'output_sha256'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN attempt_started_at BIGINT NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'attempt_started_at'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN attempt_hard_deadline_at BIGINT NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'attempt_hard_deadline_at'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN provider_request_id_hash CHAR(64)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'provider_request_id_hash'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN input_tokens INTEGER', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'input_tokens'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN output_tokens INTEGER', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'output_tokens'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN billing_evidence VARCHAR(32)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'billing_evidence'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN safe_error_code VARCHAR(128)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'safe_error_code'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN dispatched_at BIGINT NOT NULL', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'dispatched_at'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

SET @dispatch_column_ddl = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE learning_course_provider_dispatches ADD COLUMN completed_at BIGINT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches' AND COLUMN_NAME = 'completed_at'
);
PREPARE dispatch_column_ddl_stmt FROM @dispatch_column_ddl;
EXECUTE dispatch_column_ddl_stmt;
DEALLOCATE PREPARE dispatch_column_ddl_stmt;

-- Safe field backfills happen before replacing the 055 state constraint.
UPDATE learning_curriculum_preparation_plans
SET content_target_count = CASE
      WHEN JSON_VALID(target_spec_json) = 1
        AND JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, '$.schemaVersion')) = 'mira.learning.preparation-target.v2'
        THEN 30 ELSE 0 END,
    content_canary_target_count = CASE
      WHEN JSON_VALID(target_spec_json) = 1
        AND JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, '$.schemaVersion')) = 'mira.learning.preparation-target.v2'
        THEN 3 ELSE 0 END;

UPDATE learning_curriculum_preparation_plans
SET retry_reason_code = CASE
      WHEN resume_stage = 'planning' THEN 'legacy_create_only_planning'
      ELSE 'legacy_unclassified_retry' END,
    retry_message_safe = '课程准备状态正在安全升级'
WHERE status = 'queued' AND stage = 'retry_wait'
  AND retry_reason_code IS NULL AND retry_message_safe IS NULL;

UPDATE learning_catalog_build_jobs
SET execution_mode = COALESCE(execution_mode, 'full_pipeline'),
  stage_ceiling = COALESCE(stage_ceiling, 'active_release');

UPDATE learning_catalog_build_items
SET execution_mode_snapshot = COALESCE(execution_mode_snapshot, 'full_pipeline'),
  content_phase = COALESCE(content_phase, 'legacy_full_pipeline'),
  content_gate_status = COALESCE(content_gate_status, 'not_applicable'),
  content_gate_attempt_count = COALESCE(content_gate_attempt_count, 0);

SET @drop_old_state_check = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_curriculum_preparation_plans DROP CHECK chk_learning_prep_state_evidence',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'chk_learning_prep_state_evidence'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE drop_old_state_check_stmt FROM @drop_old_state_check;
EXECUTE drop_old_state_check_stmt;
DEALLOCATE PREPARE drop_old_state_check_stmt;

-- Normalize only rows classified by this migration. A legitimate dependency
-- retry written after 056 retains its non-legacy reason on a marker replay.
UPDATE learning_curriculum_preparation_plans
SET stage = 'planning'
WHERE status = 'running' AND stage = 'queued';

UPDATE learning_curriculum_preparation_plans
SET status = 'running', stage = 'planning', resume_stage = NULL,
  lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
  hard_deadline_at = NULL, work_unit_kind = NULL,
  bound_catalog_item_id = NULL, bound_content_attempt_ordinal = NULL,
  bound_content_phase = NULL, retry_reason_code = NULL,
  retry_message_safe = NULL, error_code = NULL, error_message_safe = NULL,
  completed_at = NULL, superseded_at = NULL
WHERE status = 'queued' AND stage = 'retry_wait'
  AND retry_reason_code = 'legacy_create_only_planning';

UPDATE learning_curriculum_preparation_plans
SET status = 'failed', stage = 'completed',
  error_code = 'preparation_upgrade_retry_state_invalid',
  error_message_safe = '课程准备重试状态已安全终止，请重新准备',
  completed_at = COALESCE(last_progress_at, next_run_at, updated_at, created_at),
  lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
  next_run_at = NULL, hard_deadline_at = NULL, resume_stage = NULL,
  work_unit_kind = NULL, bound_catalog_item_id = NULL,
  bound_content_attempt_ordinal = NULL, bound_content_phase = NULL,
  retry_reason_code = NULL, retry_message_safe = NULL,
  updated_at = COALESCE(last_progress_at, next_run_at, updated_at, created_at)
WHERE status = 'queued' AND stage = 'retry_wait'
  AND retry_reason_code = 'legacy_unclassified_retry';

UPDATE learning_curriculum_preparation_plans
SET stage_progress_json = JSON_OBJECT(
  'candidateCount', content_candidate_count,
  'canaryCandidateCount', content_canary_candidate_count,
  'canaryFailedCount', content_canary_failed_count,
  'canaryTargetCount', content_canary_target_count,
  'failedCount', content_failed_count,
  'targetCount', content_target_count
);

-- The sole replacement state constraint explicitly branches on the immutable
-- target schema inside target_spec_json. Every nullable evidence group is
-- closed with IS NULL or IS NOT NULL so MySQL UNKNOWN cannot pass the check.
SET @add_content_state_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD CONSTRAINT chk_learning_prep_content_state_evidence CHECK (preparation_contract_version = ''mira.learning.grade-preparation.v1'' AND target_spec_json IS NOT NULL AND JSON_VALID(target_spec_json) = 1 AND JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) IS NOT NULL AND ((JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.v1'' AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND (((status = ''queued'' AND stage = ''queued'' AND next_run_at IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage IN (''planning'', ''generating_content'', ''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND next_run_at IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage IN (''planning'', ''generating_content'', ''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND next_run_at IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND resume_stage IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''queued'' AND stage = ''retry_wait'' AND next_run_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND next_run_at <= hard_deadline_at AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND resume_stage IS NOT NULL AND resume_stage IN (''planning'', ''generating_content'', ''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL AND ((retry_reason_code IS NULL AND retry_message_safe IS NULL) OR (retry_reason_code IS NOT NULL AND retry_message_safe IS NOT NULL))) OR (status = ''ready'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NULL AND progress_percent = 100 AND ready_course_count = total_course_count AND failed_course_count = 0 AND error_code IS NULL AND error_message_safe IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL) OR (status = ''failed'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NULL AND error_code IS NOT NULL AND error_message_safe IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL) OR (status = ''superseded'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NOT NULL AND error_code IS NULL AND error_message_safe IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL)))) OR (JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.v2'' AND (((status = ''queued'' AND stage = ''queued'' AND next_run_at IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage IN (''planning'', ''generating_content'') AND next_run_at IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage IN (''planning'', ''generating_content'') AND next_run_at IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND resume_stage IS NULL AND work_unit_kind IS NOT NULL AND work_unit_kind = ''coordinator'' AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage = ''generating_content'' AND next_run_at IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND resume_stage IS NULL AND work_unit_kind IS NOT NULL AND work_unit_kind IN (''provider_phase'', ''host_gate'') AND bound_catalog_item_id IS NOT NULL AND bound_content_attempt_ordinal IS NOT NULL AND bound_content_attempt_ordinal BETWEEN 1 AND 2 AND bound_content_phase IS NOT NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''queued'' AND stage = ''retry_wait'' AND next_run_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND next_run_at <= hard_deadline_at AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND resume_stage IS NOT NULL AND resume_stage IN (''planning'', ''generating_content'') AND retry_reason_code IS NOT NULL AND retry_message_safe IS NOT NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL AND ((work_unit_kind IS NOT NULL AND work_unit_kind = ''coordinator'' AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL) OR (work_unit_kind IS NOT NULL AND work_unit_kind IN (''provider_phase'', ''host_gate'') AND bound_catalog_item_id IS NOT NULL AND bound_content_attempt_ordinal IS NOT NULL AND bound_content_attempt_ordinal BETWEEN 1 AND 2 AND bound_content_phase IS NOT NULL))) OR (status = ''running'' AND stage = ''building_classrooms'' AND catalog_build_id IS NOT NULL AND catalog_release_id IS NOT NULL AND content_target_count = 30 AND content_candidate_count = 30 AND content_failed_count = 0 AND content_canary_target_count = 3 AND content_canary_candidate_count = 3 AND content_canary_failed_count = 0 AND content_canary_passed_at IS NOT NULL AND content_generation_completed_at IS NOT NULL AND ready_course_count = 0 AND failed_course_count = 0 AND progress_percent = 35 AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''failed'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NULL AND error_code IS NOT NULL AND error_message_safe IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL) OR (status = ''superseded'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NOT NULL AND error_code IS NULL AND error_message_safe IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL))))))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'chk_learning_prep_content_state_evidence'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_content_state_check_stmt FROM @add_content_state_check;
EXECUTE add_content_state_check_stmt;
DEALLOCATE PREPARE add_content_state_check_stmt;

SET @add_content_counts_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD CONSTRAINT chk_learning_prep_content_counts CHECK (content_target_count >= 0 AND content_candidate_count >= 0 AND content_failed_count >= 0 AND content_candidate_count + content_failed_count <= content_target_count AND content_canary_target_count >= 0 AND content_canary_candidate_count >= 0 AND content_canary_failed_count >= 0 AND content_canary_target_count <= content_target_count AND content_canary_candidate_count + content_canary_failed_count <= content_canary_target_count AND content_canary_candidate_count <= content_candidate_count AND content_canary_failed_count <= content_failed_count AND ((content_canary_passed_at IS NULL) OR (content_canary_passed_at IS NOT NULL AND content_canary_target_count = 3 AND content_canary_candidate_count = 3 AND content_canary_failed_count = 0)) AND ((content_generation_completed_at IS NULL) OR (content_generation_completed_at IS NOT NULL AND content_target_count = 30 AND content_candidate_count = 30 AND content_failed_count = 0 AND content_canary_passed_at IS NOT NULL)) AND JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) IS NOT NULL AND ((JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.v1'' AND content_target_count = 0 AND content_candidate_count = 0 AND content_failed_count = 0 AND content_canary_target_count = 0 AND content_canary_candidate_count = 0 AND content_canary_failed_count = 0 AND content_canary_passed_at IS NULL AND content_generation_completed_at IS NULL) OR (JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.v2'' AND content_target_count = 30 AND content_canary_target_count = 3)))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'chk_learning_prep_content_counts' AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_content_counts_check_stmt FROM @add_content_counts_check;
EXECUTE add_content_counts_check_stmt;
DEALLOCATE PREPARE add_content_counts_check_stmt;

SET @add_stage_progress_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD CONSTRAINT chk_learning_prep_stage_progress_json CHECK (stage_progress_json IS NOT NULL AND JSON_VALID(stage_progress_json) = 1 AND JSON_TYPE(stage_progress_json) = ''OBJECT'' AND JSON_LENGTH(stage_progress_json) = 6 AND JSON_EXTRACT(stage_progress_json, ''$.candidateCount'') IS NOT NULL AND JSON_EXTRACT(stage_progress_json, ''$.canaryCandidateCount'') IS NOT NULL AND JSON_EXTRACT(stage_progress_json, ''$.canaryFailedCount'') IS NOT NULL AND JSON_EXTRACT(stage_progress_json, ''$.canaryTargetCount'') IS NOT NULL AND JSON_EXTRACT(stage_progress_json, ''$.failedCount'') IS NOT NULL AND JSON_EXTRACT(stage_progress_json, ''$.targetCount'') IS NOT NULL AND JSON_TYPE(JSON_EXTRACT(stage_progress_json, ''$.candidateCount'')) = ''INTEGER'' AND JSON_TYPE(JSON_EXTRACT(stage_progress_json, ''$.canaryCandidateCount'')) = ''INTEGER'' AND JSON_TYPE(JSON_EXTRACT(stage_progress_json, ''$.canaryFailedCount'')) = ''INTEGER'' AND JSON_TYPE(JSON_EXTRACT(stage_progress_json, ''$.canaryTargetCount'')) = ''INTEGER'' AND JSON_TYPE(JSON_EXTRACT(stage_progress_json, ''$.failedCount'')) = ''INTEGER'' AND JSON_TYPE(JSON_EXTRACT(stage_progress_json, ''$.targetCount'')) = ''INTEGER'' AND CAST(JSON_UNQUOTE(JSON_EXTRACT(stage_progress_json, ''$.candidateCount'')) AS UNSIGNED) = content_candidate_count AND CAST(JSON_UNQUOTE(JSON_EXTRACT(stage_progress_json, ''$.canaryCandidateCount'')) AS UNSIGNED) = content_canary_candidate_count AND CAST(JSON_UNQUOTE(JSON_EXTRACT(stage_progress_json, ''$.canaryFailedCount'')) AS UNSIGNED) = content_canary_failed_count AND CAST(JSON_UNQUOTE(JSON_EXTRACT(stage_progress_json, ''$.canaryTargetCount'')) AS UNSIGNED) = content_canary_target_count AND CAST(JSON_UNQUOTE(JSON_EXTRACT(stage_progress_json, ''$.failedCount'')) AS UNSIGNED) = content_failed_count AND CAST(JSON_UNQUOTE(JSON_EXTRACT(stage_progress_json, ''$.targetCount'')) AS UNSIGNED) = content_target_count)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'chk_learning_prep_stage_progress_json' AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_stage_progress_check_stmt FROM @add_stage_progress_check;
EXECUTE add_stage_progress_check_stmt;
DEALLOCATE PREPARE add_stage_progress_check_stmt;

ALTER TABLE learning_curriculum_preparation_plans
  MODIFY COLUMN stage_progress_json LONGTEXT NOT NULL;
ALTER TABLE learning_catalog_build_jobs
  MODIFY COLUMN execution_mode VARCHAR(32) NOT NULL DEFAULT 'full_pipeline',
  MODIFY COLUMN stage_ceiling VARCHAR(64) NOT NULL DEFAULT 'active_release';
ALTER TABLE learning_catalog_build_items
  MODIFY COLUMN execution_mode_snapshot VARCHAR(32) NOT NULL DEFAULT 'full_pipeline',
  MODIFY COLUMN content_phase VARCHAR(64) NOT NULL DEFAULT 'legacy_full_pipeline',
  MODIFY COLUMN content_gate_status VARCHAR(32) NOT NULL DEFAULT 'not_applicable',
  MODIFY COLUMN content_gate_attempt_count INTEGER NOT NULL DEFAULT 0;

SET @add_build_mode_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_jobs ADD CONSTRAINT chk_learning_catalog_build_content_mode CHECK ((execution_mode = ''full_pipeline'' AND stage_ceiling = ''active_release'' AND ((content_manifest_version IS NULL) OR (content_manifest_version IS NOT NULL AND content_manifest_version <> '''')) AND ((canary_manifest_json IS NULL) OR (canary_manifest_json IS NOT NULL AND JSON_VALID(canary_manifest_json) = 1))) OR (execution_mode = ''content_only'' AND content_manifest_version IS NOT NULL AND content_manifest_version <> '''' AND canary_manifest_json IS NOT NULL AND JSON_VALID(canary_manifest_json) = 1 AND JSON_TYPE(canary_manifest_json) = ''OBJECT'' AND stage_ceiling = ''content_ready''))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_jobs'
    AND CONSTRAINT_NAME = 'chk_learning_catalog_build_content_mode' AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_build_mode_check_stmt FROM @add_build_mode_check;
EXECUTE add_build_mode_check_stmt;
DEALLOCATE PREPARE add_build_mode_check_stmt;

SET @add_item_state_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD CONSTRAINT chk_learning_catalog_item_content_state CHECK ((execution_mode_snapshot = ''full_pipeline'' AND content_phase = ''legacy_full_pipeline'' AND content_gate_status = ''not_applicable'' AND content_gate_attempt_count = 0 AND ((content_manifest_version_snapshot IS NULL) OR (content_manifest_version_snapshot IS NOT NULL AND content_manifest_version_snapshot <> '''')) AND ((subject_ordinal IS NULL) OR (subject_ordinal IS NOT NULL AND subject_ordinal >= 1)) AND ((boundary_ordinal IS NULL) OR (boundary_ordinal IS NOT NULL AND boundary_ordinal >= 1)) AND content_gate_passed_at IS NULL AND content_validation_contract_version IS NULL AND content_receipt_hash IS NULL AND content_lease_token IS NULL AND content_lease_expires_at IS NULL AND content_heartbeat_at IS NULL AND content_attempt_started_at IS NULL AND content_provider_attempt_hard_deadline_at IS NULL AND content_work_unit_deadline_at IS NULL AND content_claim_attempt_ordinal IS NULL) OR (execution_mode_snapshot = ''content_only'' AND content_manifest_version_snapshot IS NOT NULL AND content_manifest_version_snapshot <> '''' AND subject_ordinal IS NOT NULL AND subject_ordinal >= 1 AND boundary_ordinal IS NOT NULL AND boundary_ordinal >= 1 AND content_phase IS NOT NULL AND content_phase IN (''not_started'', ''outline'', ''raw_candidate'', ''candidate_repair'', ''candidate_repair_retry'', ''lesson_text'', ''reconciliation'', ''reconciliation_retry'', ''practice_leak_repair_1'', ''practice_leak_repair_2'', ''choice_prompt_repair'', ''independent_verification'', ''consistency_repair'', ''consistency_repair_retry'', ''verification_after_repair'', ''host_gate_pending'', ''host_gate_running'', ''course_ready'', ''failed'') AND content_gate_status IS NOT NULL AND content_gate_status IN (''not_started'', ''pending'', ''retry_wait'', ''passed'', ''failed_deterministic'') AND content_gate_attempt_count BETWEEN 0 AND 3 AND package_attempt_count = 0 AND active_package_request_id IS NULL AND package_id IS NULL AND package_version IS NULL AND ((content_lease_token IS NULL AND content_lease_expires_at IS NULL AND content_heartbeat_at IS NULL) OR (content_lease_token IS NOT NULL AND content_lease_expires_at IS NOT NULL AND content_heartbeat_at IS NOT NULL)) AND ((content_claim_attempt_ordinal IS NULL) OR (content_claim_attempt_ordinal IS NOT NULL AND content_claim_attempt_ordinal BETWEEN 1 AND 2)) AND ((content_receipt_hash IS NULL) OR (content_receipt_hash IS NOT NULL AND content_receipt_hash REGEXP ''^[0-9a-f]{64}$'')) AND ((content_phase = ''not_started'' AND status = ''pending'' AND attempt_count = 0 AND active_generation_request_id IS NULL AND content_claim_attempt_ordinal IS NULL AND content_gate_status = ''not_started'' AND content_gate_attempt_count = 0 AND course_id IS NULL AND course_version IS NULL AND content_gate_passed_at IS NULL AND content_validation_contract_version IS NULL AND content_receipt_hash IS NULL AND content_lease_token IS NULL AND content_lease_expires_at IS NULL AND content_heartbeat_at IS NULL AND content_attempt_started_at IS NULL AND content_provider_attempt_hard_deadline_at IS NULL AND content_work_unit_deadline_at IS NULL) OR (content_phase IN (''outline'', ''raw_candidate'', ''candidate_repair'', ''candidate_repair_retry'', ''lesson_text'', ''reconciliation'', ''reconciliation_retry'', ''practice_leak_repair_1'', ''practice_leak_repair_2'', ''choice_prompt_repair'', ''independent_verification'', ''consistency_repair'', ''consistency_repair_retry'', ''verification_after_repair'') AND status = ''processing'' AND attempt_count BETWEEN 1 AND 2 AND content_claim_attempt_ordinal IS NOT NULL AND content_claim_attempt_ordinal = attempt_count AND active_generation_request_id IS NOT NULL AND content_gate_status = ''not_started'' AND content_gate_attempt_count = 0 AND content_attempt_started_at IS NOT NULL AND content_provider_attempt_hard_deadline_at IS NOT NULL AND content_work_unit_deadline_at IS NOT NULL AND content_attempt_started_at <= content_work_unit_deadline_at AND content_work_unit_deadline_at <= content_provider_attempt_hard_deadline_at AND content_gate_passed_at IS NULL AND content_validation_contract_version IS NULL AND content_receipt_hash IS NULL) OR (content_phase = ''host_gate_pending'' AND status = ''processing'' AND attempt_count BETWEEN 1 AND 2 AND content_claim_attempt_ordinal IS NOT NULL AND content_claim_attempt_ordinal = attempt_count AND active_generation_request_id IS NOT NULL AND course_id IS NOT NULL AND course_version IS NOT NULL AND content_gate_status IN (''pending'', ''retry_wait'') AND content_gate_attempt_count BETWEEN 0 AND 3 AND content_gate_passed_at IS NULL AND content_validation_contract_version IS NULL AND content_receipt_hash IS NULL AND content_lease_token IS NULL AND content_lease_expires_at IS NULL AND content_heartbeat_at IS NULL AND content_provider_attempt_hard_deadline_at IS NULL AND content_work_unit_deadline_at IS NULL) OR (content_phase = ''host_gate_running'' AND status = ''processing'' AND attempt_count BETWEEN 1 AND 2 AND content_claim_attempt_ordinal IS NOT NULL AND content_claim_attempt_ordinal = attempt_count AND active_generation_request_id IS NOT NULL AND course_id IS NOT NULL AND course_version IS NOT NULL AND content_gate_status IN (''pending'', ''retry_wait'') AND content_gate_attempt_count BETWEEN 1 AND 3 AND content_gate_passed_at IS NULL AND content_validation_contract_version IS NULL AND content_receipt_hash IS NULL AND content_lease_token IS NOT NULL AND content_lease_expires_at IS NOT NULL AND content_heartbeat_at IS NOT NULL AND content_provider_attempt_hard_deadline_at IS NULL AND content_work_unit_deadline_at IS NOT NULL) OR (content_phase = ''course_ready'' AND status = ''course_ready'' AND attempt_count BETWEEN 1 AND 2 AND content_claim_attempt_ordinal IS NOT NULL AND content_claim_attempt_ordinal = attempt_count AND active_generation_request_id IS NOT NULL AND course_id IS NOT NULL AND course_version IS NOT NULL AND content_gate_status = ''passed'' AND content_gate_attempt_count BETWEEN 1 AND 3 AND content_gate_passed_at IS NOT NULL AND content_validation_contract_version IS NOT NULL AND content_validation_contract_version <> '''' AND content_receipt_hash IS NOT NULL AND content_receipt_hash REGEXP ''^[0-9a-f]{64}$'' AND content_lease_token IS NULL AND content_lease_expires_at IS NULL AND content_heartbeat_at IS NULL AND content_provider_attempt_hard_deadline_at IS NULL AND content_work_unit_deadline_at IS NULL) OR (content_phase = ''failed'' AND status = ''failed'' AND attempt_count BETWEEN 1 AND 2 AND content_claim_attempt_ordinal IS NOT NULL AND content_claim_attempt_ordinal = attempt_count AND active_generation_request_id IS NOT NULL AND ((content_gate_status = ''not_started'' AND content_gate_attempt_count = 0) OR (content_gate_status = ''failed_deterministic'' AND content_gate_attempt_count BETWEEN 1 AND 3)) AND content_gate_passed_at IS NULL AND content_validation_contract_version IS NULL AND content_receipt_hash IS NULL AND error_code IS NOT NULL AND error_message_safe IS NOT NULL AND content_lease_token IS NULL AND content_lease_expires_at IS NULL AND content_heartbeat_at IS NULL AND content_provider_attempt_hard_deadline_at IS NULL AND content_work_unit_deadline_at IS NULL))))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND CONSTRAINT_NAME = 'chk_learning_catalog_item_content_state' AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_item_state_check_stmt FROM @add_item_state_check;
EXECUTE add_item_state_check_stmt;
DEALLOCATE PREPARE add_item_state_check_stmt;

SET @add_dispatch_attempt_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_course_provider_dispatches ADD CONSTRAINT chk_learning_provider_dispatch_attempt CHECK (logical_attempt BETWEEN 1 AND 2)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches'
    AND CONSTRAINT_NAME = 'chk_learning_provider_dispatch_attempt' AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_dispatch_attempt_check_stmt FROM @add_dispatch_attempt_check;
EXECUTE add_dispatch_attempt_check_stmt;
DEALLOCATE PREPARE add_dispatch_attempt_check_stmt;

SET @add_dispatch_phase_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_course_provider_dispatches ADD CONSTRAINT chk_learning_provider_dispatch_phase CHECK ((phase = ''outline'' AND phase_ordinal = 1) OR (phase = ''raw_candidate'' AND phase_ordinal = 2) OR (phase = ''candidate_repair'' AND phase_ordinal = 3) OR (phase = ''candidate_repair_retry'' AND phase_ordinal = 4) OR (phase = ''lesson_text'' AND phase_ordinal = 5) OR (phase = ''reconciliation'' AND phase_ordinal = 6) OR (phase = ''reconciliation_retry'' AND phase_ordinal = 7) OR (phase = ''practice_leak_repair_1'' AND phase_ordinal = 8) OR (phase = ''practice_leak_repair_2'' AND phase_ordinal = 9) OR (phase = ''choice_prompt_repair'' AND phase_ordinal = 10) OR (phase = ''independent_verification'' AND phase_ordinal = 11) OR (phase = ''consistency_repair'' AND phase_ordinal = 12) OR (phase = ''consistency_repair_retry'' AND phase_ordinal = 13) OR (phase = ''verification_after_repair'' AND phase_ordinal = 14))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches'
    AND CONSTRAINT_NAME = 'chk_learning_provider_dispatch_phase' AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_dispatch_phase_check_stmt FROM @add_dispatch_phase_check;
EXECUTE add_dispatch_phase_check_stmt;
DEALLOCATE PREPARE add_dispatch_phase_check_stmt;

SET @add_dispatch_evidence_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_course_provider_dispatches ADD CONSTRAINT chk_learning_provider_dispatch_evidence CHECK (input_sha256 REGEXP ''^[0-9a-f]{64}$'' AND attempt_started_at <= dispatched_at AND dispatched_at <= attempt_hard_deadline_at AND ((provider_request_id_hash IS NULL) OR (provider_request_id_hash IS NOT NULL AND provider_request_id_hash REGEXP ''^[0-9a-f]{64}$'')) AND ((input_tokens IS NULL) OR (input_tokens IS NOT NULL AND input_tokens >= 0)) AND ((output_tokens IS NULL) OR (output_tokens IS NOT NULL AND output_tokens >= 0)) AND ((completed_at IS NULL) OR (completed_at IS NOT NULL AND completed_at <= attempt_hard_deadline_at)) AND ((status = ''dispatched'' AND checkpoint_json IS NULL AND output_sha256 IS NULL AND provider_request_id_hash IS NULL AND input_tokens IS NULL AND output_tokens IS NULL AND billing_evidence IS NULL AND safe_error_code IS NULL AND completed_at IS NULL) OR (status = ''succeeded'' AND checkpoint_json IS NOT NULL AND JSON_VALID(checkpoint_json) = 1 AND JSON_TYPE(checkpoint_json) = ''OBJECT'' AND output_sha256 IS NOT NULL AND output_sha256 REGEXP ''^[0-9a-f]{64}$'' AND billing_evidence IS NOT NULL AND billing_evidence IN (''reported'', ''unknown'') AND safe_error_code IS NULL AND completed_at IS NOT NULL AND completed_at >= dispatched_at) OR (status IN (''failed_safe'', ''ambiguous'') AND checkpoint_json IS NULL AND output_sha256 IS NULL AND billing_evidence IS NOT NULL AND billing_evidence IN (''reported'', ''unknown'') AND safe_error_code IS NOT NULL AND safe_error_code REGEXP ''^[a-z0-9_]{1,128}$'' AND completed_at IS NOT NULL AND completed_at >= dispatched_at)))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches'
    AND CONSTRAINT_NAME = 'chk_learning_provider_dispatch_evidence' AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_dispatch_evidence_check_stmt FROM @add_dispatch_evidence_check;
EXECUTE add_dispatch_evidence_check_stmt;
DEALLOCATE PREPARE add_dispatch_evidence_check_stmt;

SET @add_dispatch_fk = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_course_provider_dispatches ADD CONSTRAINT fk_learning_provider_dispatch_item FOREIGN KEY (build_item_id) REFERENCES learning_catalog_build_items(id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_course_provider_dispatches'
    AND CONSTRAINT_NAME = 'fk_learning_provider_dispatch_item'
);
PREPARE add_dispatch_fk_stmt FROM @add_dispatch_fk;
EXECUTE add_dispatch_fk_stmt;
DEALLOCATE PREPARE add_dispatch_fk_stmt;

SET @add_dispatch_phase_unique = (
  SELECT IF(COUNT(*) = 0,
    'CREATE UNIQUE INDEX uq_learning_provider_dispatch_phase ON learning_course_provider_dispatches(build_item_id, logical_attempt, phase)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches'
    AND INDEX_NAME = 'uq_learning_provider_dispatch_phase'
);
PREPARE add_dispatch_phase_unique_stmt FROM @add_dispatch_phase_unique;
EXECUTE add_dispatch_phase_unique_stmt;
DEALLOCATE PREPARE add_dispatch_phase_unique_stmt;

SET @add_dispatch_ordinal_unique = (
  SELECT IF(COUNT(*) = 0,
    'CREATE UNIQUE INDEX uq_learning_provider_dispatch_ordinal ON learning_course_provider_dispatches(build_item_id, logical_attempt, phase_ordinal)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches'
    AND INDEX_NAME = 'uq_learning_provider_dispatch_ordinal'
);
PREPARE add_dispatch_ordinal_unique_stmt FROM @add_dispatch_ordinal_unique;
EXECUTE add_dispatch_ordinal_unique_stmt;
DEALLOCATE PREPARE add_dispatch_ordinal_unique_stmt;

SET @add_dispatch_status_index = (
  SELECT IF(COUNT(*) = 0,
    'CREATE INDEX idx_learning_provider_dispatch_item_status ON learning_course_provider_dispatches(build_item_id, status, phase_ordinal)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches'
    AND INDEX_NAME = 'idx_learning_provider_dispatch_item_status'
);
PREPARE add_dispatch_status_index_stmt FROM @add_dispatch_status_index;
EXECUTE add_dispatch_status_index_stmt;
DEALLOCATE PREPARE add_dispatch_status_index_stmt;

SET @add_plan_content_index = (
  SELECT IF(COUNT(*) = 0,
    'CREATE INDEX idx_learning_prep_content_claim ON learning_curriculum_preparation_plans(status, stage, next_run_at, work_unit_kind)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND INDEX_NAME = 'idx_learning_prep_content_claim'
);
PREPARE add_plan_content_index_stmt FROM @add_plan_content_index;
EXECUTE add_plan_content_index_stmt;
DEALLOCATE PREPARE add_plan_content_index_stmt;

SET @add_build_content_index = (
  SELECT IF(COUNT(*) = 0,
    'CREATE INDEX idx_learning_catalog_build_content_mode ON learning_catalog_build_jobs(execution_mode, status, updated_at)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_jobs'
    AND INDEX_NAME = 'idx_learning_catalog_build_content_mode'
);
PREPARE add_build_content_index_stmt FROM @add_build_content_index;
EXECUTE add_build_content_index_stmt;
DEALLOCATE PREPARE add_build_content_index_stmt;

SET @add_item_content_index = (
  SELECT IF(COUNT(*) = 0,
    'CREATE INDEX idx_learning_catalog_item_content_claim ON learning_catalog_build_items(build_job_id, execution_mode_snapshot, status, subject_ordinal, boundary_ordinal, variant_ordinal)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
    AND INDEX_NAME = 'idx_learning_catalog_item_content_claim'
);
PREPARE add_item_content_index_stmt FROM @add_item_content_index;
EXECUTE add_item_content_index_stmt;
DEALLOCATE PREPARE add_item_content_index_stmt;

-- A failing verification statement prevents scripts.migrate from registering
-- 056. The marker is inserted only after this script returns successfully.
SET @verify_056 = (
  SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
        AND CONSTRAINT_NAME = 'chk_learning_prep_state_evidence') = 0
    AND (SELECT COUNT(*)
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
      JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
        ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
        AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
      WHERE tc.TABLE_SCHEMA = DATABASE()
        AND tc.TABLE_NAME = 'learning_curriculum_preparation_plans'
        AND tc.CONSTRAINT_TYPE = 'CHECK'
        AND tc.CONSTRAINT_NAME = 'chk_learning_prep_content_state_evidence'
        AND SHA2(cc.CHECK_CLAUSE, 256) =
          'f9e79f956fdabad79fad19ff9acaab9deb75f83e1c014b83f1182fb24878f94d') = 1
    AND (SELECT COUNT(*)
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
      JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
        ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
        AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
      WHERE tc.TABLE_SCHEMA = DATABASE()
        AND tc.TABLE_NAME = 'learning_curriculum_preparation_plans'
        AND tc.CONSTRAINT_TYPE = 'CHECK'
        AND tc.CONSTRAINT_NAME = 'chk_learning_prep_content_counts'
        AND SHA2(cc.CHECK_CLAUSE, 256) =
          '17f1b5ed1cb2594565b9a88b5fd6f89692f153d8cc776a46b87b699d1d4d5d2a') = 1
    AND (SELECT COUNT(*)
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
      JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
        ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
        AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
      WHERE tc.TABLE_SCHEMA = DATABASE()
        AND tc.TABLE_NAME = 'learning_curriculum_preparation_plans'
        AND tc.CONSTRAINT_TYPE = 'CHECK'
        AND tc.CONSTRAINT_NAME = 'chk_learning_prep_stage_progress_json'
        AND SHA2(cc.CHECK_CLAUSE, 256) =
          '1c8ae8ea05228502047f1988a4dc7643dd5ec93ddae443db65486a917dd504ec') = 1
    AND (SELECT COUNT(*)
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
      JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
        ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
        AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
      WHERE tc.TABLE_SCHEMA = DATABASE()
        AND tc.TABLE_NAME = 'learning_catalog_build_jobs'
        AND tc.CONSTRAINT_TYPE = 'CHECK'
        AND tc.CONSTRAINT_NAME = 'chk_learning_catalog_build_content_mode'
        AND SHA2(cc.CHECK_CLAUSE, 256) =
          'cf9be3bbe31f658a6ea06c4e806d604fe0b5c9b10db13bf402c9fc699c7fa6b4') = 1
    AND (SELECT COUNT(*)
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
      JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
        ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
        AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
      WHERE tc.TABLE_SCHEMA = DATABASE()
        AND tc.TABLE_NAME = 'learning_catalog_build_items'
        AND tc.CONSTRAINT_TYPE = 'CHECK'
        AND tc.CONSTRAINT_NAME = 'chk_learning_catalog_item_content_state'
        AND SHA2(cc.CHECK_CLAUSE, 256) =
          '85f0302da2b0fac46bbf8188178ba7bb915b0580f3cf9f22b803673ccfbb635c') = 1
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_curriculum_preparation_plans'
        AND COLUMN_NAME IN ('content_target_count', 'content_candidate_count', 'content_failed_count', 'content_canary_target_count', 'content_canary_candidate_count', 'content_canary_failed_count', 'content_canary_passed_at', 'content_generation_completed_at', 'retry_reason_code', 'retry_message_safe', 'work_unit_kind', 'bound_catalog_item_id', 'bound_content_attempt_ordinal', 'bound_content_phase', 'stage_progress_json')) = 15
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_curriculum_preparation_plans'
        AND EXTRA = ''
        AND (
          (COLUMN_NAME IN ('content_target_count', 'content_candidate_count', 'content_failed_count', 'content_canary_target_count', 'content_canary_candidate_count', 'content_canary_failed_count') AND COLUMN_TYPE = 'int' AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT = '0')
          OR (COLUMN_NAME IN ('content_canary_passed_at', 'content_generation_completed_at') AND COLUMN_TYPE = 'bigint' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'retry_reason_code' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'retry_message_safe' AND COLUMN_TYPE = 'varchar(512)' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'work_unit_kind' AND COLUMN_TYPE = 'varchar(32)' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'bound_catalog_item_id' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'bound_content_attempt_ordinal' AND COLUMN_TYPE = 'int' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'bound_content_phase' AND COLUMN_TYPE = 'varchar(64)' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'stage_progress_json' AND COLUMN_TYPE = 'longtext' AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT IS NULL)
        )) = 15
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_jobs'
        AND COLUMN_NAME IN ('execution_mode', 'content_manifest_version', 'canary_manifest_json', 'stage_ceiling')) = 4
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_catalog_build_jobs'
        AND EXTRA = ''
        AND (
          (COLUMN_NAME = 'execution_mode' AND COLUMN_TYPE = 'varchar(32)' AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT = 'full_pipeline')
          OR (COLUMN_NAME = 'content_manifest_version' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'canary_manifest_json' AND COLUMN_TYPE = 'longtext' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'stage_ceiling' AND COLUMN_TYPE = 'varchar(64)' AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT = 'active_release')
        )) = 4
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_catalog_build_items'
        AND COLUMN_NAME IN ('execution_mode_snapshot', 'content_manifest_version_snapshot', 'subject_ordinal', 'boundary_ordinal', 'content_phase', 'content_gate_status', 'content_gate_attempt_count', 'content_gate_passed_at', 'content_validation_contract_version', 'content_receipt_hash', 'content_lease_token', 'content_lease_expires_at', 'content_heartbeat_at', 'content_attempt_started_at', 'content_provider_attempt_hard_deadline_at', 'content_work_unit_deadline_at', 'content_claim_attempt_ordinal')) = 17
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_catalog_build_items'
        AND EXTRA = ''
        AND (
          (COLUMN_NAME = 'execution_mode_snapshot' AND COLUMN_TYPE = 'varchar(32)' AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT = 'full_pipeline')
          OR (COLUMN_NAME = 'content_manifest_version_snapshot' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME IN ('subject_ordinal', 'boundary_ordinal', 'content_claim_attempt_ordinal') AND COLUMN_TYPE = 'int' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'content_phase' AND COLUMN_TYPE = 'varchar(64)' AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT = 'legacy_full_pipeline')
          OR (COLUMN_NAME = 'content_gate_status' AND COLUMN_TYPE = 'varchar(32)' AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT = 'not_applicable')
          OR (COLUMN_NAME = 'content_gate_attempt_count' AND COLUMN_TYPE = 'int' AND IS_NULLABLE = 'NO' AND COLUMN_DEFAULT = '0')
          OR (COLUMN_NAME IN ('content_gate_passed_at', 'content_lease_expires_at', 'content_heartbeat_at', 'content_attempt_started_at', 'content_provider_attempt_hard_deadline_at', 'content_work_unit_deadline_at') AND COLUMN_TYPE = 'bigint' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME IN ('content_validation_contract_version', 'content_lease_token') AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
          OR (COLUMN_NAME = 'content_receipt_hash' AND COLUMN_TYPE = 'char(64)' AND IS_NULLABLE = 'YES' AND COLUMN_DEFAULT IS NULL)
        )) = 17
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'learning_course_provider_dispatches') = 23
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_course_provider_dispatches'
        AND COLUMN_DEFAULT IS NULL
        AND EXTRA = ''
        AND (
          (COLUMN_NAME = 'id' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'build_item_id' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'logical_attempt' AND COLUMN_TYPE = 'int' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'phase' AND COLUMN_TYPE = 'varchar(64)' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'phase_ordinal' AND COLUMN_TYPE = 'int' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'generation_request_id' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'item_lease_token' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'provider' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'model' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'profile' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'input_sha256' AND COLUMN_TYPE = 'char(64)' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'status' AND COLUMN_TYPE = 'varchar(32)' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'checkpoint_json' AND COLUMN_TYPE = 'longtext' AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'output_sha256' AND COLUMN_TYPE = 'char(64)' AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'attempt_started_at' AND COLUMN_TYPE = 'bigint' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'attempt_hard_deadline_at' AND COLUMN_TYPE = 'bigint' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'provider_request_id_hash' AND COLUMN_TYPE = 'char(64)' AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'input_tokens' AND COLUMN_TYPE = 'int' AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'output_tokens' AND COLUMN_TYPE = 'int' AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'billing_evidence' AND COLUMN_TYPE = 'varchar(32)' AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'safe_error_code' AND COLUMN_TYPE = 'varchar(128)' AND IS_NULLABLE = 'YES')
          OR (COLUMN_NAME = 'dispatched_at' AND COLUMN_TYPE = 'bigint' AND IS_NULLABLE = 'NO')
          OR (COLUMN_NAME = 'completed_at' AND COLUMN_TYPE = 'bigint' AND IS_NULLABLE = 'YES')
        )) = 23
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_course_provider_dispatches'
        AND INDEX_NAME = 'PRIMARY') = 1
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_course_provider_dispatches'
        AND INDEX_NAME = 'PRIMARY' AND NON_UNIQUE = 0
        AND SEQ_IN_INDEX = 1 AND COLUMN_NAME = 'id'
        AND SUB_PART IS NULL AND INDEX_TYPE = 'BTREE') = 1
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_course_provider_dispatches'
        AND INDEX_NAME = 'uq_learning_provider_dispatch_phase'
        AND NON_UNIQUE = 0 AND SUB_PART IS NULL AND INDEX_TYPE = 'BTREE') = 3
    AND (SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',')
      FROM INFORMATION_SCHEMA.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_course_provider_dispatches'
        AND INDEX_NAME = 'uq_learning_provider_dispatch_phase') =
      'build_item_id,logical_attempt,phase'
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_course_provider_dispatches'
        AND INDEX_NAME = 'uq_learning_provider_dispatch_ordinal'
        AND NON_UNIQUE = 0 AND SUB_PART IS NULL AND INDEX_TYPE = 'BTREE') = 3
    AND (SELECT GROUP_CONCAT(COLUMN_NAME ORDER BY SEQ_IN_INDEX SEPARATOR ',')
      FROM INFORMATION_SCHEMA.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_course_provider_dispatches'
        AND INDEX_NAME = 'uq_learning_provider_dispatch_ordinal') =
      'build_item_id,logical_attempt,phase_ordinal'
    AND (SELECT COUNT(*)
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
      JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
        ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
        AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
      WHERE tc.TABLE_SCHEMA = DATABASE()
        AND tc.TABLE_NAME = 'learning_course_provider_dispatches'
        AND tc.CONSTRAINT_TYPE = 'CHECK'
        AND tc.CONSTRAINT_NAME = 'chk_learning_provider_dispatch_attempt'
        AND SHA2(cc.CHECK_CLAUSE, 256) =
          'ba7142e8360ce05518a0cbce1ecc693f85d4f26263e804d6e9ab0b0eb05747e4') = 1
    AND (SELECT COUNT(*)
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
      JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
        ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
        AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
      WHERE tc.TABLE_SCHEMA = DATABASE()
        AND tc.TABLE_NAME = 'learning_course_provider_dispatches'
        AND tc.CONSTRAINT_TYPE = 'CHECK'
        AND tc.CONSTRAINT_NAME = 'chk_learning_provider_dispatch_phase'
        AND SHA2(cc.CHECK_CLAUSE, 256) =
          '569304f457a08ead6d0a726de19bd944072e5c1e5c414f7f58326ccefc052930') = 1
    AND (SELECT COUNT(*)
      FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS AS tc
      JOIN INFORMATION_SCHEMA.CHECK_CONSTRAINTS AS cc
        ON cc.CONSTRAINT_SCHEMA = tc.CONSTRAINT_SCHEMA
        AND cc.CONSTRAINT_NAME = tc.CONSTRAINT_NAME
      WHERE tc.TABLE_SCHEMA = DATABASE()
        AND tc.TABLE_NAME = 'learning_course_provider_dispatches'
        AND tc.CONSTRAINT_TYPE = 'CHECK'
        AND tc.CONSTRAINT_NAME = 'chk_learning_provider_dispatch_evidence'
        AND SHA2(cc.CHECK_CLAUSE, 256) =
          '4846d6f940666c01044c3a0c4f53c7b3065dc40fcf583765121092fb455b3d05') = 1
    AND (SELECT COUNT(*)
      FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE AS kcu
      JOIN INFORMATION_SCHEMA.REFERENTIAL_CONSTRAINTS AS rc
        ON rc.CONSTRAINT_SCHEMA = kcu.CONSTRAINT_SCHEMA
        AND rc.CONSTRAINT_NAME = kcu.CONSTRAINT_NAME
        AND rc.TABLE_NAME = kcu.TABLE_NAME
      WHERE kcu.TABLE_SCHEMA = DATABASE()
        AND kcu.TABLE_NAME = 'learning_course_provider_dispatches'
        AND kcu.CONSTRAINT_NAME = 'fk_learning_provider_dispatch_item'
        AND kcu.COLUMN_NAME = 'build_item_id'
        AND kcu.ORDINAL_POSITION = 1
        AND kcu.POSITION_IN_UNIQUE_CONSTRAINT = 1
        AND kcu.REFERENCED_TABLE_NAME = 'learning_catalog_build_items'
        AND kcu.REFERENCED_COLUMN_NAME = 'id'
        AND rc.UNIQUE_CONSTRAINT_NAME = 'PRIMARY'
        AND rc.UPDATE_RULE = 'NO ACTION'
        AND rc.DELETE_RULE = 'NO ACTION') = 1
    AND (SELECT COUNT(*) FROM learning_catalog_build_jobs
      WHERE execution_mode IS NULL OR stage_ceiling IS NULL) = 0
    AND (SELECT COUNT(*) FROM learning_catalog_build_items
      WHERE execution_mode_snapshot IS NULL OR content_phase IS NULL
        OR content_gate_status IS NULL OR content_gate_attempt_count IS NULL) = 0,
    'SELECT 1',
    'SIGNAL SQLSTATE ''45000'' SET MESSAGE_TEXT = ''056 schema verification failed'''
  )
);
PREPARE verify_056_stmt FROM @verify_056;
EXECUTE verify_056_stmt;
DEALLOCATE PREPARE verify_056_stmt;
