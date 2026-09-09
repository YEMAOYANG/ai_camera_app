-- Migration 054 allowed retry_wait without a persisted deadline. Such a row
-- cannot be assigned a deadline while the 054 check is still installed, so
-- fail it closed with one fixed public upgrade reason before any DDL. This is
-- deterministic on both a normal upgrade and a restart after partial DDL.
UPDATE learning_curriculum_preparation_plans
SET status = 'failed', stage = 'completed',
  error_code = 'preparation_upgrade_retry_state_invalid',
  error_message_safe = '课程准备重试状态已安全终止，请重新准备',
  completed_at = COALESCE(last_progress_at, next_run_at, updated_at, created_at),
  lease_token = NULL, lease_expires_at = NULL, heartbeat_at = NULL,
  next_run_at = NULL, hard_deadline_at = NULL, resume_stage = NULL,
  updated_at = COALESCE(last_progress_at, next_run_at, updated_at, created_at)
WHERE status = 'queued' AND stage = 'retry_wait'
  AND hard_deadline_at IS NULL;

SET @drop_learning_prep_state_evidence = (
  SELECT IF(
    COUNT(*) > 0,
    'ALTER TABLE learning_curriculum_preparation_plans DROP CHECK chk_learning_prep_state_evidence',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'chk_learning_prep_state_evidence'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE drop_learning_prep_state_evidence_stmt
  FROM @drop_learning_prep_state_evidence;
EXECUTE drop_learning_prep_state_evidence_stmt;
DEALLOCATE PREPARE drop_learning_prep_state_evidence_stmt;

SET @add_learning_prep_state_evidence = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD CONSTRAINT chk_learning_prep_state_evidence CHECK (((status = ''queued'' AND stage = ''queued'' AND next_run_at IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage = ''queued'' AND next_run_at IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND resume_stage IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage IN (''planning'', ''generating_content'', ''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND next_run_at IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND resume_stage IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''queued'' AND stage = ''retry_wait'' AND next_run_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND next_run_at <= hard_deadline_at AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND resume_stage IN (''planning'', ''generating_content'', ''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''ready'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NULL AND progress_percent = 100 AND ready_course_count = total_course_count AND failed_course_count = 0 AND error_code IS NULL AND error_message_safe IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL) OR (status = ''failed'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NULL AND error_code IS NOT NULL AND error_message_safe IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL) OR (status = ''superseded'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NOT NULL AND error_code IS NULL AND error_message_safe IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL)))',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'chk_learning_prep_state_evidence'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_learning_prep_state_evidence_stmt
  FROM @add_learning_prep_state_evidence;
EXECUTE add_learning_prep_state_evidence_stmt;
DEALLOCATE PREPARE add_learning_prep_state_evidence_stmt;
