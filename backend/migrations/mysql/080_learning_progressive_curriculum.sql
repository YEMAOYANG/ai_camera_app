-- Fine-grained curriculum evidence is separate from historical coarse mastery.
-- No historical mastery is copied and no generated course is implicitly bound.
CREATE TABLE IF NOT EXISTS learning_progressive_course_bindings (
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  curriculum_version VARCHAR(64) NOT NULL,
  lesson_id VARCHAR(128) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  assessment_set_id VARCHAR(128) NOT NULL,
  content_sha256 CHAR(64) NOT NULL,
  created_at BIGINT NOT NULL,
  retired_at BIGINT,
  PRIMARY KEY (course_id, course_version),
  INDEX idx_progressive_bound_lesson(curriculum_version, lesson_id, retired_at)
);

CREATE TABLE IF NOT EXISTS learning_progressive_evidence (
  id CHAR(64) PRIMARY KEY,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  curriculum_version VARCHAR(64) NOT NULL,
  lesson_id VARCHAR(128) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  source_kind VARCHAR(32) NOT NULL,
  source_session_id VARCHAR(255) NOT NULL,
  source_question_id VARCHAR(255) NOT NULL,
  question_fingerprint CHAR(64) NOT NULL,
  assessment_set_id VARCHAR(128) NOT NULL,
  attempt_number INTEGER NOT NULL,
  independent INTEGER NOT NULL,
  hint_count_before_answer INTEGER NOT NULL,
  correct INTEGER,
  actor_role VARCHAR(16),
  actor_id VARCHAR(128),
  occurred_at BIGINT NOT NULL,
  evidence_sha256 CHAR(64) NOT NULL,
  created_at BIGINT NOT NULL,
  INDEX idx_progressive_evidence_scope(
    family_id, child_id, curriculum_version, lesson_id, occurred_at
  ),
  INDEX idx_progressive_evidence_subject(
    family_id, child_id, curriculum_version, subject, occurred_at
  )
);

CREATE TABLE IF NOT EXISTS learning_progressive_lesson_progress (
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  curriculum_version VARCHAR(64) NOT NULL,
  lesson_id VARCHAR(128) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  mastery_status VARCHAR(32) NOT NULL,
  independent_count INTEGER NOT NULL DEFAULT 0,
  independent_correct_count INTEGER NOT NULL DEFAULT 0,
  distinct_assessment_sets INTEGER NOT NULL DEFAULT 0,
  total_evidence_count INTEGER NOT NULL DEFAULT 0,
  accuracy DOUBLE,
  mastered_at BIGINT,
  stable_at BIGINT,
  last_evidence_at BIGINT,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (family_id, child_id, curriculum_version, lesson_id),
  INDEX idx_progressive_progress_subject(
    family_id, child_id, curriculum_version, subject, mastery_status
  )
);

-- A published fine lesson can authorize a session before the whole grade is
-- finished. Keep its complete immutable publication identity without inventing
-- a grade pointer/history row or borrowing a child preparation plan.
-- Migration 070 added the nullable columns and this named CHECK. Replace the
-- CHECK atomically while preserving both existing authority branches.
ALTER TABLE learning_student_formal_session_bindings
  DROP CHECK chk_lsfsb_identity,
  ADD CONSTRAINT chk_lsfsb_identity CHECK (
    learning_session_id <> ''
    AND family_id <> '' AND child_id <> ''
    AND grade_code REGEXP '^primary_[1-6]$'
    AND authority_kind IN (
      'active_pointer', 'progressive_plan', 'progressive_course'
    )
    AND release_id <> ''
    AND target_fingerprint REGEXP '^[0-9a-f]{64}$'
    AND publication_contract_version =
      'mira.learning.formal-publication.v1'
    AND build_item_id <> ''
    AND course_id <> '' AND course_version <> ''
    AND package_id <> '' AND package_version > 0
    AND package_content_hash REGEXP '^[0-9a-f]{64}$'
    AND runtime_classroom_id <> '' AND upstream_classroom_id <> ''
    AND bound_at > 0
    AND created_at = bound_at
    AND (
      (
        authority_kind = 'active_pointer'
        AND pointer_history_id IS NOT NULL AND pointer_history_id <> ''
        AND pointer_revision IS NOT NULL AND pointer_revision >= 1
        AND preparation_plan_id IS NULL
        AND grade_selection_revision IS NULL
      )
      OR (
        authority_kind = 'progressive_plan'
        AND pointer_history_id IS NULL AND pointer_revision IS NULL
        AND preparation_plan_id IS NOT NULL AND preparation_plan_id <> ''
        AND grade_selection_revision IS NOT NULL
        AND grade_selection_revision >= 1
      )
      OR (
        authority_kind = 'progressive_course'
        AND pointer_history_id IS NULL AND pointer_revision IS NULL
        AND preparation_plan_id IS NULL
        AND grade_selection_revision IS NOT NULL
        AND grade_selection_revision >= 1
      )
    )
  );

-- Extend the actual final legacy CHECK expressions in place. The old branch is
-- read from MySQL instead of copied from an earlier migration, preserving 079
-- multigrade fixes and all legacy lease/receipt rules. New-version rows have a
-- separate strict branch. Missing JSON or proof fields fail closed.
-- CHECK_CLAUSE escapes quote delimiters. Decode only backslash + single quote
-- with character codes so SQL modes cannot change decoding, while preserving
-- every other backslash in legacy regular expressions.
-- MySQL types CASE/COALESCE as scalar expressions, so each CHECK explicitly
-- compares the final CASE to TRUE. Equality keeps legacy UNKNOWN unchanged.
-- the progressive branch still turns missing evidence into FALSE.

SET @mira_080_legacy_prep_counts = (
  SELECT REPLACE(CHECK_CLAUSE, CONCAT(CHAR(92), CHAR(39)), CHAR(39))
  FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
  WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'chk_learning_prep_content_counts'
);
SET @mira_080_prep_counts_sql = CONCAT(
  'ALTER TABLE learning_curriculum_preparation_plans DROP CHECK chk_learning_prep_content_counts, ADD CONSTRAINT chk_learning_prep_content_counts CHECK (CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.progressive.v1'' THEN COALESCE((
curriculum_version = ''mira.primary.progressive.v1''
AND preparation_contract_version = ''mira.learning.grade-preparation.progressive.v1''
AND grade_code REGEXP ''^primary_[1-6]$''
AND JSON_VALID(target_spec_json) = 1
AND JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.curriculumVersion'')) = curriculum_version
AND JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.preparationContractVersion'')) = preparation_contract_version
AND JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.gradeCode'')) = grade_code
AND JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.granularity'')) = ''lesson''
AND JSON_TYPE(JSON_EXTRACT(target_spec_json, ''$.assessmentBatchOrdinal'')) = ''INTEGER''
AND CAST(JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.assessmentBatchOrdinal'')) AS UNSIGNED) >= 1
AND JSON_TYPE(JSON_EXTRACT(target_spec_json, ''$.variantsPerBoundary'')) = ''INTEGER''
AND CAST(JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.variantsPerBoundary'')) AS UNSIGNED) = 2
AND JSON_TYPE(JSON_EXTRACT(target_spec_json, ''$.totalCourseCount'')) = ''INTEGER''
AND CAST(JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.totalCourseCount'')) AS UNSIGNED) = total_course_count
AND JSON_TYPE(JSON_EXTRACT(target_spec_json, ''$.boundaryCount'')) = ''INTEGER''
AND CAST(JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.boundaryCount'')) AS UNSIGNED) * 2 = total_course_count
AND JSON_TYPE(JSON_EXTRACT(target_spec_json, ''$.boundaries'')) = ''ARRAY''
AND JSON_LENGTH(JSON_EXTRACT(target_spec_json, ''$.boundaries'')) * 2 = total_course_count
AND JSON_TYPE(JSON_EXTRACT(target_spec_json, ''$.lessonIds'')) = ''ARRAY''
AND JSON_LENGTH(JSON_EXTRACT(target_spec_json, ''$.lessonIds'')) * 2 = total_course_count
AND JSON_TYPE(JSON_EXTRACT(target_spec_json, ''$.courseTargets'')) = ''ARRAY''
AND JSON_LENGTH(JSON_EXTRACT(target_spec_json, ''$.courseTargets'')) = total_course_count
AND JSON_TYPE(JSON_EXTRACT(target_spec_json, ''$.canaryManifest.targets'')) = ''ARRAY''
AND JSON_LENGTH(JSON_EXTRACT(target_spec_json, ''$.canaryManifest.targets'')) = content_canary_target_count
AND content_target_count = total_course_count
AND content_target_count > 0
AND content_candidate_count >= 0 AND content_failed_count >= 0
AND content_candidate_count + content_failed_count <= content_target_count
AND content_canary_target_count BETWEEN 1 AND 3
AND content_canary_target_count <= content_target_count
AND content_canary_candidate_count >= 0 AND content_canary_failed_count >= 0
AND content_canary_candidate_count + content_canary_failed_count <= content_canary_target_count
AND content_canary_candidate_count <= content_candidate_count
AND content_canary_failed_count <= content_failed_count
AND (content_canary_passed_at IS NULL OR (
  content_canary_candidate_count = content_canary_target_count
  AND content_canary_failed_count = 0
))
AND (content_generation_completed_at IS NULL OR (
  content_candidate_count = content_target_count AND content_failed_count = 0
  AND content_canary_passed_at IS NOT NULL
))
), FALSE) ELSE (',
  @mira_080_legacy_prep_counts,
  ') END = TRUE)'
);
PREPARE mira_080_prep_counts_stmt FROM @mira_080_prep_counts_sql;
EXECUTE mira_080_prep_counts_stmt;
DEALLOCATE PREPARE mira_080_prep_counts_stmt;

SET @mira_080_legacy_prep_state = (
  SELECT REPLACE(CHECK_CLAUSE, CONCAT(CHAR(92), CHAR(39)), CHAR(39))
  FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
  WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'chk_learning_prep_formal_state_evidence'
);
SET @mira_080_prep_state_sql = CONCAT(
  'ALTER TABLE learning_curriculum_preparation_plans DROP CHECK chk_learning_prep_formal_state_evidence, ADD CONSTRAINT chk_learning_prep_formal_state_evidence CHECK (CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.progressive.v1'' THEN COALESCE((
preparation_contract_version = ''mira.learning.grade-preparation.progressive.v1''
AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL
AND (
  (status = ''queued'' AND stage = ''queued'' AND next_run_at IS NOT NULL
    AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND work_unit_kind IS NULL
    AND resume_stage IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL)
  OR (status = ''running'' AND stage IN (''planning'', ''generating_content'')
    AND next_run_at IS NOT NULL AND resume_stage IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL
    AND (
      (lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND work_unit_kind IS NULL)
      OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL
        AND hard_deadline_at IS NOT NULL AND work_unit_kind = ''coordinator'')
    ))
  OR (status = ''running'' AND stage IN (''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'')
    AND catalog_build_id IS NOT NULL AND catalog_release_id IS NOT NULL
AND content_target_count = total_course_count AND content_candidate_count = total_course_count
AND content_failed_count = 0 AND content_canary_candidate_count = content_canary_target_count
AND content_canary_failed_count = 0 AND content_canary_passed_at IS NOT NULL
AND content_generation_completed_at IS NOT NULL AND resume_stage IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL
    AND (
      (stage = ''building_classrooms'' AND progress_percent = 35
        AND ready_course_count = 0 AND failed_course_count = 0
        AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND next_run_at IS NULL
        AND work_unit_kind IS NULL)
      OR (next_run_at IS NOT NULL
        AND ((stage = ''building_classrooms'' AND progress_percent BETWEEN 40 AND 64)
          OR (stage = ''generating_speech'' AND progress_percent BETWEEN 65 AND 84)
          OR (stage = ''validating'' AND progress_percent BETWEEN 85 AND 94)
          OR (stage = ''publishing'' AND progress_percent BETWEEN 95 AND 99))
        AND ((lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND work_unit_kind IS NULL)
          OR (lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL
            AND hard_deadline_at IS NOT NULL AND next_run_at <= hard_deadline_at
            AND work_unit_kind = ''coordinator'')))
    ))
  OR (status = ''queued'' AND stage = ''retry_wait'' AND next_run_at IS NOT NULL
    AND hard_deadline_at IS NOT NULL AND next_run_at <= hard_deadline_at
    AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND work_unit_kind = ''coordinator''
    AND resume_stage IN (''planning'', ''generating_content'', ''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'')
    AND retry_reason_code IS NOT NULL AND retry_message_safe IS NOT NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL
    AND (resume_stage IN (''planning'', ''generating_content'') OR (catalog_build_id IS NOT NULL AND catalog_release_id IS NOT NULL
AND content_target_count = total_course_count AND content_candidate_count = total_course_count
AND content_failed_count = 0 AND content_canary_candidate_count = content_canary_target_count
AND content_canary_failed_count = 0 AND content_canary_passed_at IS NOT NULL
AND content_generation_completed_at IS NOT NULL)))
  OR (stage = ''completed'' AND completed_at IS NOT NULL
    AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL
    AND work_unit_kind IS NULL AND resume_stage IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL
    AND (
      (status = ''ready'' AND superseded_at IS NULL
        AND progress_percent = 100 AND ready_course_count = total_course_count
        AND failed_course_count = 0 AND error_code IS NULL AND error_message_safe IS NULL
        AND catalog_build_id IS NOT NULL AND catalog_release_id IS NOT NULL
AND content_target_count = total_course_count AND content_candidate_count = total_course_count
AND content_failed_count = 0 AND content_canary_candidate_count = content_canary_target_count
AND content_canary_failed_count = 0 AND content_canary_passed_at IS NOT NULL
AND content_generation_completed_at IS NOT NULL)
      OR (status = ''failed'' AND superseded_at IS NULL
        AND error_code IS NOT NULL AND error_message_safe IS NOT NULL)
      OR (status = ''superseded'' AND superseded_at IS NOT NULL
        AND error_code IS NULL AND error_message_safe IS NULL)
    ))
)
), FALSE) ELSE (',
  @mira_080_legacy_prep_state,
  ') END = TRUE)'
);
PREPARE mira_080_prep_state_stmt FROM @mira_080_prep_state_sql;
EXECUTE mira_080_prep_state_stmt;
DEALLOCATE PREPARE mira_080_prep_state_stmt;

SET @mira_080_legacy_prep_publication = (
  SELECT REPLACE(CHECK_CLAUSE, CONCAT(CHAR(92), CHAR(39)), CHAR(39))
  FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
  WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'chk_learning_prep_formal_publication'
);
SET @mira_080_prep_publication_sql = CONCAT(
  'ALTER TABLE learning_curriculum_preparation_plans DROP CHECK chk_learning_prep_formal_publication, ADD CONSTRAINT chk_learning_prep_formal_publication CHECK (CASE WHEN JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.progressive.v1'' THEN COALESCE((
classroom_ready_count BETWEEN 0 AND total_course_count
AND speech_ready_count BETWEEN 0 AND classroom_ready_count
AND validation_ready_count BETWEEN 0 AND speech_ready_count
AND published_course_count BETWEEN 0 AND validation_ready_count
AND (
  (status = ''ready'' AND stage = ''completed''
    AND classroom_ready_count = total_course_count AND speech_ready_count = total_course_count
    AND validation_ready_count = total_course_count AND published_course_count = total_course_count
    AND catalog_release_id IS NOT NULL
    AND formal_contract_version = ''mira.learning.formal-publication.v1''
    AND formal_publication_history_id IS NOT NULL
    AND formal_publication_receipt_hash REGEXP ''^[0-9a-f]{64}$''
    AND formal_ready_at IS NOT NULL AND formal_ready_at > 0)
  OR (status <> ''ready'' AND formal_contract_version IS NULL
    AND formal_publication_history_id IS NULL
    AND formal_publication_receipt_hash IS NULL AND formal_ready_at IS NULL)
)
), FALSE) ELSE (',
  @mira_080_legacy_prep_publication,
  ') END = TRUE)'
);
PREPARE mira_080_prep_publication_stmt FROM @mira_080_prep_publication_sql;
EXECUTE mira_080_prep_publication_stmt;
DEALLOCATE PREPARE mira_080_prep_publication_stmt;

-- Fine content uses its own generation/host receipt graph. Legacy phase
-- counters remain zero. Immutable new host evidence proves course_ready.

SET @mira_080_legacy_item_state = (
  SELECT REPLACE(CHECK_CLAUSE, CONCAT(CHAR(92), CHAR(39)), CHAR(39))
  FROM INFORMATION_SCHEMA.CHECK_CONSTRAINTS
  WHERE CONSTRAINT_SCHEMA = DATABASE() AND CONSTRAINT_NAME = 'chk_learning_catalog_item_content_state'
);
SET @mira_080_item_state_sql = CONCAT(
  'ALTER TABLE learning_catalog_build_items DROP CHECK chk_learning_catalog_item_content_state, ADD CONSTRAINT chk_learning_catalog_item_content_state CHECK (CASE WHEN curriculum_version = ''mira.primary.progressive.v1'' THEN COALESCE((
execution_mode_snapshot = ''content_only''
AND content_manifest_version_snapshot = ''mira.learning.preparation-target.progressive.v1''
AND grade_code REGEXP ''^primary_[1-6]$''
AND subject IN (''chinese'', ''math'', ''english'')
AND skill_id <> '''' AND boundary_version <> ''''
AND subject_ordinal >= 1 AND boundary_ordinal >= 1
AND variant_ordinal BETWEEN 1 AND 2
AND package_attempt_count = 0 AND active_package_request_id IS NULL
AND package_id IS NULL AND package_version IS NULL
AND content_gate_attempt_count = 0 AND content_claim_attempt_ordinal IS NULL
AND content_attempt_started_at IS NULL
AND content_provider_attempt_hard_deadline_at IS NULL
AND content_work_unit_deadline_at IS NULL
AND (
  (status = ''pending'' AND content_phase = ''not_started''
    AND attempt_count = 0 AND active_generation_request_id IS NULL
    AND content_gate_status = ''not_started''
    AND course_id IS NULL AND course_version IS NULL
    AND content_gate_passed_at IS NULL AND content_validation_contract_version IS NULL
    AND content_receipt_hash IS NULL
    AND content_lease_token IS NULL AND content_lease_expires_at IS NULL AND content_heartbeat_at IS NULL)
  OR (status = ''processing'' AND content_phase = ''progressive_generation''
    AND attempt_count = 1 AND active_generation_request_id = generation_request_id
    AND content_gate_status = ''not_started''
    AND course_id IS NULL AND course_version IS NULL
    AND content_gate_passed_at IS NULL AND content_validation_contract_version IS NULL
    AND content_receipt_hash IS NULL
    AND content_lease_token IS NOT NULL AND content_lease_expires_at IS NOT NULL
    AND content_heartbeat_at IS NOT NULL)
  OR (status = ''course_ready'' AND content_phase = ''course_ready''
    AND attempt_count = 1 AND active_generation_request_id = generation_request_id
    AND content_gate_status = ''passed''
    AND course_id IS NOT NULL AND course_id <> ''''
    AND course_version IS NOT NULL AND course_version <> ''''
    AND content_gate_passed_at IS NOT NULL AND content_gate_passed_at > 0
    AND content_validation_contract_version = ''mira.learning.progressive-host-validation.v1''
    AND content_receipt_hash REGEXP ''^[0-9a-f]{64}$''
    AND content_lease_token IS NULL AND content_lease_expires_at IS NULL AND content_heartbeat_at IS NULL)
  OR (status = ''failed'' AND content_phase = ''failed''
    AND attempt_count = 1 AND active_generation_request_id = generation_request_id
    AND content_gate_status = ''failed''
    AND content_gate_passed_at IS NULL AND content_validation_contract_version IS NULL
    AND content_receipt_hash IS NULL
    AND error_code IS NOT NULL AND error_message_safe IS NOT NULL
    AND content_lease_token IS NULL AND content_lease_expires_at IS NULL AND content_heartbeat_at IS NULL)
)
), FALSE) ELSE (',
  @mira_080_legacy_item_state,
  ') END = TRUE)'
);
PREPARE mira_080_item_state_stmt FROM @mira_080_item_state_sql;
EXECUTE mira_080_item_state_stmt;
DEALLOCATE PREPARE mira_080_item_state_stmt;
