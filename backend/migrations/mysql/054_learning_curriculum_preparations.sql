SET @add_children_grade_selection_revision = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE children ADD COLUMN grade_selection_revision INTEGER NOT NULL DEFAULT 0 AFTER grade_confirmed_at',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'grade_selection_revision'
);
PREPARE add_children_grade_selection_revision_stmt
  FROM @add_children_grade_selection_revision;
EXECUTE add_children_grade_selection_revision_stmt;
DEALLOCATE PREPARE add_children_grade_selection_revision_stmt;

CREATE TABLE IF NOT EXISTS learning_curriculum_preparation_plans (
  id VARCHAR(128) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  school_year_start_year INTEGER NOT NULL,
  grade_selection_revision INTEGER NOT NULL,
  curriculum_version VARCHAR(128) NOT NULL,
  preparation_contract_version VARCHAR(128) NOT NULL,
  target_spec_json LONGTEXT NOT NULL,
  target_fingerprint CHAR(64) NOT NULL,
  request_id VARCHAR(128) NOT NULL,
  shared_build_request_id VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  stage VARCHAR(64) NOT NULL,
  catalog_build_id VARCHAR(128),
  catalog_release_id VARCHAR(128),
  total_course_count INTEGER NOT NULL,
  ready_course_count INTEGER NOT NULL DEFAULT 0,
  failed_course_count INTEGER NOT NULL DEFAULT 0,
  progress_percent INTEGER NOT NULL DEFAULT 0,
  subject_progress_json LONGTEXT NOT NULL,
  retry_of_plan_id VARCHAR(128),
  retry_ordinal INTEGER NOT NULL DEFAULT 0,
  resume_stage VARCHAR(64),
  lease_token VARCHAR(128),
  lease_expires_at BIGINT,
  heartbeat_at BIGINT,
  next_run_at BIGINT,
  hard_deadline_at BIGINT,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  last_progress_at BIGINT,
  started_at BIGINT,
  completed_at BIGINT,
  superseded_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_prep_identity(
    child_id, grade_selection_revision, target_fingerprint, retry_ordinal
  ),
  UNIQUE KEY uq_learning_prep_request(request_id),
  UNIQUE KEY uq_learning_prep_retry_source(retry_of_plan_id),
  INDEX idx_learning_prep_claim(status, stage, next_run_at, lease_expires_at),
  CONSTRAINT fk_learning_prep_family FOREIGN KEY (family_id)
    REFERENCES families(id) ON DELETE CASCADE,
  CONSTRAINT fk_learning_prep_child FOREIGN KEY (child_id)
    REFERENCES children(id) ON DELETE CASCADE,
  CONSTRAINT fk_learning_prep_retry FOREIGN KEY (retry_of_plan_id)
    REFERENCES learning_curriculum_preparation_plans(id) ON DELETE CASCADE,
  CONSTRAINT chk_learning_prep_status CHECK (
    status IN ('queued', 'running', 'ready', 'failed', 'superseded')
  ),
  CONSTRAINT chk_learning_prep_stage CHECK (
    stage IN (
      'queued', 'planning', 'generating_content', 'building_classrooms',
      'generating_speech', 'validating', 'publishing', 'retry_wait', 'completed'
    )
  ),
  CONSTRAINT chk_learning_prep_counts CHECK (
    total_course_count > 0
    AND ready_course_count >= 0
    AND failed_course_count >= 0
    AND ready_course_count + failed_course_count <= total_course_count
    AND progress_percent BETWEEN 0 AND 100
  ),
  CONSTRAINT chk_learning_prep_json CHECK (
    JSON_VALID(target_spec_json) = 1
    AND JSON_VALID(subject_progress_json) = 1
  ),
  CONSTRAINT chk_learning_prep_retry_ordinal CHECK (
    retry_ordinal BETWEEN 0 AND 1
  ),
  CONSTRAINT chk_learning_prep_retry CHECK (
    (
      retry_ordinal = 0
      AND retry_of_plan_id IS NULL
    ) OR (
      retry_ordinal = 1
      AND retry_of_plan_id IS NOT NULL
    )
  ),
  CONSTRAINT chk_learning_prep_lease_group CHECK (
    (
      lease_token IS NULL
      AND lease_expires_at IS NULL
      AND heartbeat_at IS NULL
    ) OR (
      lease_token IS NOT NULL
      AND lease_expires_at IS NOT NULL
      AND heartbeat_at IS NOT NULL
    )
  ),
  CONSTRAINT chk_learning_prep_state_evidence CHECK (
    (
      status = 'queued'
      AND stage = 'queued'
      AND next_run_at IS NOT NULL
      AND lease_token IS NULL
      AND lease_expires_at IS NULL
      AND heartbeat_at IS NULL
      AND hard_deadline_at IS NULL
      AND resume_stage IS NULL
      AND completed_at IS NULL
      AND superseded_at IS NULL
      AND error_code IS NULL
      AND error_message_safe IS NULL
    ) OR (
      status = 'running'
      AND stage = 'queued'
      AND next_run_at IS NOT NULL
      AND lease_token IS NOT NULL
      AND lease_expires_at IS NOT NULL
      AND heartbeat_at IS NOT NULL
      AND hard_deadline_at IS NOT NULL
      AND resume_stage IS NULL
      AND completed_at IS NULL
      AND superseded_at IS NULL
      AND error_code IS NULL
      AND error_message_safe IS NULL
    ) OR (
      status = 'running'
      AND stage IN (
        'planning', 'generating_content', 'building_classrooms',
        'generating_speech', 'validating', 'publishing'
      )
      AND next_run_at IS NOT NULL
      AND lease_token IS NOT NULL
      AND lease_expires_at IS NOT NULL
      AND heartbeat_at IS NOT NULL
      AND hard_deadline_at IS NOT NULL
      AND resume_stage IS NULL
      AND completed_at IS NULL
      AND superseded_at IS NULL
      AND error_code IS NULL
      AND error_message_safe IS NULL
    ) OR (
      status = 'queued'
      AND stage = 'retry_wait'
      AND next_run_at IS NOT NULL
      AND lease_token IS NULL
      AND lease_expires_at IS NULL
      AND heartbeat_at IS NULL
      AND hard_deadline_at IS NULL
      AND resume_stage IS NOT NULL
      AND resume_stage IN (
        'planning', 'generating_content', 'building_classrooms',
        'generating_speech', 'validating', 'publishing'
      )
      AND completed_at IS NULL
      AND superseded_at IS NULL
      AND error_code IS NULL
      AND error_message_safe IS NULL
    ) OR (
      status = 'ready'
      AND stage = 'completed'
      AND completed_at IS NOT NULL
      AND superseded_at IS NULL
      AND progress_percent = 100
      AND ready_course_count = total_course_count
      AND failed_course_count = 0
      AND error_code IS NULL
      AND error_message_safe IS NULL
      AND lease_token IS NULL
      AND lease_expires_at IS NULL
      AND heartbeat_at IS NULL
      AND next_run_at IS NULL
      AND hard_deadline_at IS NULL
      AND resume_stage IS NULL
    ) OR (
      status = 'failed'
      AND stage = 'completed'
      AND completed_at IS NOT NULL
      AND superseded_at IS NULL
      AND error_code IS NOT NULL
      AND error_message_safe IS NOT NULL
      AND lease_token IS NULL
      AND lease_expires_at IS NULL
      AND heartbeat_at IS NULL
      AND next_run_at IS NULL
      AND hard_deadline_at IS NULL
      AND resume_stage IS NULL
    ) OR (
      status = 'superseded'
      AND stage = 'completed'
      AND completed_at IS NOT NULL
      AND superseded_at IS NOT NULL
      AND error_code IS NULL
      AND error_message_safe IS NULL
      AND lease_token IS NULL
      AND lease_expires_at IS NULL
      AND heartbeat_at IS NULL
      AND next_run_at IS NULL
      AND hard_deadline_at IS NULL
      AND resume_stage IS NULL
    )
  )
);

CREATE TABLE IF NOT EXISTS learning_curriculum_preparation_events (
  id VARCHAR(128) PRIMARY KEY,
  plan_id VARCHAR(128) NOT NULL,
  event_type VARCHAR(64) NOT NULL,
  stage VARCHAR(64) NOT NULL,
  payload_json LONGTEXT NOT NULL,
  created_at BIGINT NOT NULL,
  INDEX idx_learning_prep_events(plan_id, created_at),
  CONSTRAINT fk_learning_prep_event_plan FOREIGN KEY (plan_id)
    REFERENCES learning_curriculum_preparation_plans(id) ON DELETE CASCADE,
  CONSTRAINT chk_learning_prep_event_json CHECK (JSON_VALID(payload_json) = 1)
);
