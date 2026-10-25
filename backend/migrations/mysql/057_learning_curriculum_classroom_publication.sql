-- Grade-scoped formal classroom publication contract.  Content-only build
-- items from 056 stay immutable: candidate Runtime/package ownership lives in
-- the Runtime binding columns and the per-item receipt ledger below.

SET @add_runtime_candidate_build_item_id = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD COLUMN candidate_build_item_id VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND COLUMN_NAME = 'candidate_build_item_id'
);
PREPARE add_runtime_candidate_build_item_id_stmt FROM @add_runtime_candidate_build_item_id;
EXECUTE add_runtime_candidate_build_item_id_stmt;
DEALLOCATE PREPARE add_runtime_candidate_build_item_id_stmt;

SET @add_runtime_candidate_release_id = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD COLUMN candidate_release_id VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND COLUMN_NAME = 'candidate_release_id'
);
PREPARE add_runtime_candidate_release_id_stmt FROM @add_runtime_candidate_release_id;
EXECUTE add_runtime_candidate_release_id_stmt;
DEALLOCATE PREPARE add_runtime_candidate_release_id_stmt;

SET @add_runtime_candidate_grade_code = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD COLUMN candidate_grade_code VARCHAR(64)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND COLUMN_NAME = 'candidate_grade_code'
);
PREPARE add_runtime_candidate_grade_code_stmt FROM @add_runtime_candidate_grade_code;
EXECUTE add_runtime_candidate_grade_code_stmt;
DEALLOCATE PREPARE add_runtime_candidate_grade_code_stmt;

SET @add_runtime_candidate_target_fingerprint = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD COLUMN candidate_target_fingerprint CHAR(64)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND COLUMN_NAME = 'candidate_target_fingerprint'
);
PREPARE add_runtime_candidate_target_fingerprint_stmt FROM @add_runtime_candidate_target_fingerprint;
EXECUTE add_runtime_candidate_target_fingerprint_stmt;
DEALLOCATE PREPARE add_runtime_candidate_target_fingerprint_stmt;

SET @add_runtime_candidate_binding_contract_version = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD COLUMN candidate_binding_contract_version VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND COLUMN_NAME = 'candidate_binding_contract_version'
);
PREPARE add_runtime_candidate_binding_contract_version_stmt FROM @add_runtime_candidate_binding_contract_version;
EXECUTE add_runtime_candidate_binding_contract_version_stmt;
DEALLOCATE PREPARE add_runtime_candidate_binding_contract_version_stmt;

SET @add_runtime_candidate_bound_at = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD COLUMN candidate_bound_at BIGINT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND COLUMN_NAME = 'candidate_bound_at'
);
PREPARE add_runtime_candidate_bound_at_stmt FROM @add_runtime_candidate_bound_at;
EXECUTE add_runtime_candidate_bound_at_stmt;
DEALLOCATE PREPARE add_runtime_candidate_bound_at_stmt;

SET @add_plan_classroom_ready_count = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN classroom_ready_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'classroom_ready_count'
);
PREPARE add_plan_classroom_ready_count_stmt FROM @add_plan_classroom_ready_count;
EXECUTE add_plan_classroom_ready_count_stmt;
DEALLOCATE PREPARE add_plan_classroom_ready_count_stmt;

SET @add_plan_speech_ready_count = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN speech_ready_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'speech_ready_count'
);
PREPARE add_plan_speech_ready_count_stmt FROM @add_plan_speech_ready_count;
EXECUTE add_plan_speech_ready_count_stmt;
DEALLOCATE PREPARE add_plan_speech_ready_count_stmt;

SET @add_plan_validation_ready_count = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN validation_ready_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'validation_ready_count'
);
PREPARE add_plan_validation_ready_count_stmt FROM @add_plan_validation_ready_count;
EXECUTE add_plan_validation_ready_count_stmt;
DEALLOCATE PREPARE add_plan_validation_ready_count_stmt;

SET @add_plan_published_course_count = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN published_course_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'published_course_count'
);
PREPARE add_plan_published_course_count_stmt FROM @add_plan_published_course_count;
EXECUTE add_plan_published_course_count_stmt;
DEALLOCATE PREPARE add_plan_published_course_count_stmt;

SET @add_plan_formal_contract_version = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN formal_contract_version VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'formal_contract_version'
);
PREPARE add_plan_formal_contract_version_stmt FROM @add_plan_formal_contract_version;
EXECUTE add_plan_formal_contract_version_stmt;
DEALLOCATE PREPARE add_plan_formal_contract_version_stmt;

SET @add_plan_formal_publication_history_id = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN formal_publication_history_id VARCHAR(128)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'formal_publication_history_id'
);
PREPARE add_plan_formal_publication_history_id_stmt FROM @add_plan_formal_publication_history_id;
EXECUTE add_plan_formal_publication_history_id_stmt;
DEALLOCATE PREPARE add_plan_formal_publication_history_id_stmt;

SET @add_plan_formal_publication_receipt_hash = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN formal_publication_receipt_hash CHAR(64)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'formal_publication_receipt_hash'
);
PREPARE add_plan_formal_publication_receipt_hash_stmt FROM @add_plan_formal_publication_receipt_hash;
EXECUTE add_plan_formal_publication_receipt_hash_stmt;
DEALLOCATE PREPARE add_plan_formal_publication_receipt_hash_stmt;

SET @add_plan_formal_ready_at = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD COLUMN formal_ready_at BIGINT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND COLUMN_NAME = 'formal_ready_at'
);
PREPARE add_plan_formal_ready_at_stmt FROM @add_plan_formal_ready_at;
EXECUTE add_plan_formal_ready_at_stmt;
DEALLOCATE PREPARE add_plan_formal_ready_at_stmt;

CREATE TABLE IF NOT EXISTS learning_curriculum_grade_release_history (
  id VARCHAR(128) PRIMARY KEY,
  grade_code VARCHAR(64) NOT NULL,
  pointer_revision INTEGER NOT NULL,
  target_fingerprint CHAR(64) NOT NULL,
  contract_version VARCHAR(128) NOT NULL,
  release_id VARCHAR(128) NOT NULL,
  previous_history_id VARCHAR(128),
  previous_release_id VARCHAR(128),
  activation_source VARCHAR(32) NOT NULL,
  publication_request_id VARCHAR(128),
  publication_receipt_hash CHAR(64),
  activated_at BIGINT NOT NULL,
  superseded_at BIGINT,
  created_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_grade_release_history_release(grade_code, release_id),
  UNIQUE KEY uq_learning_grade_release_history_revision(
    grade_code, pointer_revision
  ),
  UNIQUE KEY uq_learning_grade_release_history_request(publication_request_id),
  UNIQUE KEY uq_learning_grade_release_history_exact(
    id, grade_code, pointer_revision, target_fingerprint,
    contract_version, release_id, activated_at
  ),
  UNIQUE KEY uq_learning_grade_release_history_previous_exact(
    id, grade_code, release_id
  ),
  UNIQUE KEY uq_learning_grade_release_history_plan_exact(
    id, grade_code, target_fingerprint, contract_version, release_id,
    publication_receipt_hash
  ),
  INDEX idx_learning_grade_release_history_timeline(
    grade_code, activated_at, superseded_at
  ),
  CONSTRAINT fk_learning_grade_release_history_release
    FOREIGN KEY (release_id) REFERENCES learning_catalog_releases(id),
  CONSTRAINT fk_learning_grade_release_history_previous_exact
    FOREIGN KEY (previous_history_id, grade_code, previous_release_id)
      REFERENCES learning_curriculum_grade_release_history(
        id, grade_code, release_id
      ),
  CONSTRAINT chk_learning_grade_release_history_identity CHECK (
    grade_code <> ''
    AND pointer_revision >= 1
    AND target_fingerprint REGEXP '^[0-9a-f]{64}$'
    AND contract_version <> ''
    AND activated_at > 0
    AND (superseded_at IS NULL OR superseded_at >= activated_at)
    AND (
      (pointer_revision = 1 AND previous_history_id IS NULL
        AND previous_release_id IS NULL)
      OR (pointer_revision > 1 AND previous_history_id IS NOT NULL
        AND previous_release_id IS NOT NULL
        AND previous_release_id <> release_id)
    )
  ),
  CONSTRAINT chk_learning_grade_release_history_evidence CHECK (
    (
      activation_source = 'legacy_backfill'
      AND publication_request_id IS NULL
      AND publication_receipt_hash IS NULL
    ) OR (
      activation_source = 'formal_publication'
      AND publication_request_id IS NOT NULL
      AND publication_request_id <> ''
      AND publication_receipt_hash IS NOT NULL
      AND publication_receipt_hash REGEXP '^[0-9a-f]{64}$'
    )
  )
);

CREATE TABLE IF NOT EXISTS learning_curriculum_grade_release_pointers (
  grade_code VARCHAR(64) PRIMARY KEY,
  pointer_revision INTEGER NOT NULL DEFAULT 0,
  target_fingerprint CHAR(64),
  contract_version VARCHAR(128),
  release_id VARCHAR(128),
  history_id VARCHAR(128),
  activated_at BIGINT,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_grade_release_pointer_history(history_id),
  CONSTRAINT fk_learning_grade_release_pointer_release
    FOREIGN KEY (release_id) REFERENCES learning_catalog_releases(id),
  CONSTRAINT fk_learning_grade_release_pointer_history_exact
    FOREIGN KEY (
      history_id, grade_code, pointer_revision, target_fingerprint,
      contract_version, release_id, activated_at
    ) REFERENCES learning_curriculum_grade_release_history(
      id, grade_code, pointer_revision, target_fingerprint,
      contract_version, release_id, activated_at
    ),
  CONSTRAINT chk_learning_grade_release_pointer_identity CHECK (
    grade_code <> ''
    AND updated_at > 0
    AND (
      (pointer_revision = 0 AND target_fingerprint IS NULL
        AND contract_version IS NULL AND release_id IS NULL
        AND history_id IS NULL AND activated_at IS NULL)
      OR (pointer_revision >= 1 AND target_fingerprint IS NOT NULL
        AND target_fingerprint REGEXP '^[0-9a-f]{64}$'
        AND contract_version IS NOT NULL AND contract_version <> ''
        AND release_id IS NOT NULL AND history_id IS NOT NULL
        AND activated_at IS NOT NULL AND activated_at > 0
        AND updated_at >= activated_at)
    )
  )
);

CREATE TABLE IF NOT EXISTS learning_curriculum_classroom_item_receipts (
  build_item_id VARCHAR(128) PRIMARY KEY,
  release_id VARCHAR(128) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  target_fingerprint CHAR(64) NOT NULL,
  binding_contract_version VARCHAR(128) NOT NULL,
  runtime_classroom_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  package_id VARCHAR(128) NOT NULL,
  package_version INTEGER NOT NULL,
  classroom_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  classroom_receipt_hash CHAR(64),
  classroom_completed_at BIGINT,
  tts_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  tts_receipt_hash CHAR(64),
  tts_completed_at BIGINT,
  asr_roundtrip_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  asr_roundtrip_receipt_hash CHAR(64),
  asr_roundtrip_completed_at BIGINT,
  conversation_provider_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  conversation_provider_receipt_hash CHAR(64),
  conversation_provider_completed_at BIGINT,
  auto_validated TINYINT NOT NULL DEFAULT 0,
  auto_validation_contract_version VARCHAR(128),
  auto_validation_receipt_hash CHAR(64),
  auto_validated_at BIGINT,
  approved TINYINT NOT NULL DEFAULT 0,
  approved_by VARCHAR(128),
  approval_receipt_hash CHAR(64),
  approved_at BIGINT,
  publication_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  publication_receipt_hash CHAR(64),
  published_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_classroom_receipt_runtime(runtime_classroom_id),
  INDEX idx_learning_classroom_receipt_release(
    release_id, grade_code, publication_status, auto_validated
  ),
  CONSTRAINT fk_learning_classroom_receipt_item
    FOREIGN KEY (build_item_id) REFERENCES learning_catalog_build_items(id),
  CONSTRAINT fk_learning_classroom_receipt_release
    FOREIGN KEY (release_id) REFERENCES learning_catalog_releases(id),
  CONSTRAINT fk_learning_classroom_receipt_runtime
    FOREIGN KEY (runtime_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(id),
  CONSTRAINT fk_learning_classroom_receipt_course
    FOREIGN KEY (course_id, course_version)
      REFERENCES learning_courses(id, version),
  CONSTRAINT fk_learning_classroom_receipt_package
    FOREIGN KEY (package_id, package_version)
      REFERENCES learning_lesson_packages(id, version),
  CONSTRAINT chk_learning_classroom_receipt_identity CHECK (
    grade_code <> ''
    AND target_fingerprint REGEXP '^[0-9a-f]{64}$'
    AND binding_contract_version <> ''
    AND package_version > 0
  ),
  CONSTRAINT chk_learning_classroom_receipt_evidence CHECK (
    (
      (classroom_status = 'pending' AND classroom_receipt_hash IS NULL
        AND classroom_completed_at IS NULL)
      OR (classroom_status IN ('passed', 'failed')
        AND classroom_receipt_hash IS NOT NULL
        AND classroom_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND classroom_completed_at IS NOT NULL AND classroom_completed_at > 0)
    )
    AND (
      (tts_status = 'pending' AND tts_receipt_hash IS NULL
        AND tts_completed_at IS NULL)
      OR (tts_status IN ('passed', 'failed')
        AND tts_receipt_hash IS NOT NULL
        AND tts_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND tts_completed_at IS NOT NULL AND tts_completed_at > 0)
    )
    AND (
      (asr_roundtrip_status = 'pending'
        AND asr_roundtrip_receipt_hash IS NULL
        AND asr_roundtrip_completed_at IS NULL)
      OR (asr_roundtrip_status IN ('passed', 'failed')
        AND asr_roundtrip_receipt_hash IS NOT NULL
        AND asr_roundtrip_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND asr_roundtrip_completed_at IS NOT NULL
        AND asr_roundtrip_completed_at > 0)
    )
    AND (
      (conversation_provider_status = 'pending'
        AND conversation_provider_receipt_hash IS NULL
        AND conversation_provider_completed_at IS NULL)
      OR (conversation_provider_status IN ('passed', 'failed')
        AND conversation_provider_receipt_hash IS NOT NULL
        AND conversation_provider_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND conversation_provider_completed_at IS NOT NULL
        AND conversation_provider_completed_at > 0)
    )
    AND (
      (auto_validated = 0 AND auto_validation_contract_version IS NULL
        AND auto_validation_receipt_hash IS NULL AND auto_validated_at IS NULL)
      OR (auto_validated = 1
        AND auto_validation_contract_version IS NOT NULL
        AND auto_validation_contract_version <> ''
        AND auto_validation_receipt_hash IS NOT NULL
        AND auto_validation_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND auto_validated_at IS NOT NULL AND auto_validated_at > 0)
    )
    AND (
      (approved = 0 AND approved_by IS NULL
        AND approval_receipt_hash IS NULL AND approved_at IS NULL)
      OR (approved = 1 AND approved_by IS NOT NULL AND approved_by <> ''
        AND approval_receipt_hash IS NOT NULL
        AND approval_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND approved_at IS NOT NULL AND approved_at > 0)
    )
    AND (
      (publication_status = 'pending' AND publication_receipt_hash IS NULL
        AND published_at IS NULL)
      OR (publication_status = 'failed'
        AND publication_receipt_hash IS NOT NULL
        AND publication_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND published_at IS NOT NULL AND published_at > 0)
      OR (publication_status = 'published'
        AND publication_receipt_hash IS NOT NULL
        AND publication_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND published_at IS NOT NULL AND published_at > 0
        AND classroom_status = 'passed' AND tts_status = 'passed'
        AND asr_roundtrip_status = 'passed'
        AND conversation_provider_status = 'passed'
        AND auto_validated = 1)
    )
  ),
  CONSTRAINT chk_learning_classroom_receipt_timeline CHECK (
    created_at > 0 AND updated_at >= created_at
    AND (classroom_completed_at IS NULL OR (
      classroom_completed_at >= created_at
      AND classroom_completed_at <= updated_at))
    AND (tts_completed_at IS NULL OR (
      tts_completed_at >= created_at AND tts_completed_at <= updated_at))
    AND (asr_roundtrip_completed_at IS NULL OR (
      asr_roundtrip_completed_at >= created_at
      AND asr_roundtrip_completed_at <= updated_at))
    AND (conversation_provider_completed_at IS NULL OR (
      conversation_provider_completed_at >= created_at
      AND conversation_provider_completed_at <= updated_at))
    AND (auto_validated_at IS NULL OR (
      auto_validated_at >= created_at AND auto_validated_at <= updated_at))
    AND (approved_at IS NULL OR (
      approved_at >= created_at AND approved_at <= updated_at))
    AND (published_at IS NULL OR (
      published_at >= created_at AND published_at <= updated_at))
    AND (auto_validated = 0 OR (
      classroom_status = 'passed' AND tts_status = 'passed'
      AND asr_roundtrip_status = 'passed'
      AND conversation_provider_status = 'passed'
      AND auto_validated_at >= classroom_completed_at
      AND auto_validated_at >= tts_completed_at
      AND auto_validated_at >= asr_roundtrip_completed_at
      AND auto_validated_at >= conversation_provider_completed_at))
    AND (publication_status <> 'published' OR (
      auto_validated = 1 AND published_at >= auto_validated_at))
  )
);

-- Repair partial 057 DDL before backfill or publication reads.  These exact
-- keys also make the self-history and plan-history authorities grade scoped.
SET @add_history_previous_exact_index = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_grade_release_history ADD UNIQUE INDEX uq_learning_grade_release_history_previous_exact(id, grade_code, release_id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_grade_release_history'
    AND INDEX_NAME = 'uq_learning_grade_release_history_previous_exact'
);
PREPARE add_history_previous_exact_index_stmt FROM @add_history_previous_exact_index;
EXECUTE add_history_previous_exact_index_stmt;
DEALLOCATE PREPARE add_history_previous_exact_index_stmt;

SET @add_history_plan_exact_index = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_grade_release_history ADD UNIQUE INDEX uq_learning_grade_release_history_plan_exact(id, grade_code, target_fingerprint, contract_version, release_id, publication_receipt_hash)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_grade_release_history'
    AND INDEX_NAME = 'uq_learning_grade_release_history_plan_exact'
);
PREPARE add_history_plan_exact_index_stmt FROM @add_history_plan_exact_index;
EXECUTE add_history_plan_exact_index_stmt;
DEALLOCATE PREPARE add_history_plan_exact_index_stmt;

SET @drop_history_previous_legacy_fk = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_curriculum_grade_release_history DROP FOREIGN KEY fk_learning_grade_release_history_previous',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_grade_release_history'
    AND CONSTRAINT_NAME = 'fk_learning_grade_release_history_previous'
);
PREPARE drop_history_previous_legacy_fk_stmt FROM @drop_history_previous_legacy_fk;
EXECUTE drop_history_previous_legacy_fk_stmt;
DEALLOCATE PREPARE drop_history_previous_legacy_fk_stmt;

SET @drop_history_previous_release_legacy_fk = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_curriculum_grade_release_history DROP FOREIGN KEY fk_learning_grade_release_history_previous_release',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_grade_release_history'
    AND CONSTRAINT_NAME = 'fk_learning_grade_release_history_previous_release'
);
PREPARE drop_history_previous_release_legacy_fk_stmt FROM @drop_history_previous_release_legacy_fk;
EXECUTE drop_history_previous_release_legacy_fk_stmt;
DEALLOCATE PREPARE drop_history_previous_release_legacy_fk_stmt;

SET @add_history_previous_exact_fk = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_grade_release_history ADD CONSTRAINT fk_learning_grade_release_history_previous_exact FOREIGN KEY (previous_history_id, grade_code, previous_release_id) REFERENCES learning_curriculum_grade_release_history(id, grade_code, release_id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_grade_release_history'
    AND CONSTRAINT_NAME = 'fk_learning_grade_release_history_previous_exact'
);
PREPARE add_history_previous_exact_fk_stmt FROM @add_history_previous_exact_fk;
EXECUTE add_history_previous_exact_fk_stmt;
DEALLOCATE PREPARE add_history_previous_exact_fk_stmt;

SET @add_receipt_timeline_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_classroom_item_receipts ADD CONSTRAINT chk_learning_classroom_receipt_timeline CHECK (created_at > 0 AND updated_at >= created_at AND (classroom_completed_at IS NULL OR (classroom_completed_at >= created_at AND classroom_completed_at <= updated_at)) AND (tts_completed_at IS NULL OR (tts_completed_at >= created_at AND tts_completed_at <= updated_at)) AND (asr_roundtrip_completed_at IS NULL OR (asr_roundtrip_completed_at >= created_at AND asr_roundtrip_completed_at <= updated_at)) AND (conversation_provider_completed_at IS NULL OR (conversation_provider_completed_at >= created_at AND conversation_provider_completed_at <= updated_at)) AND (auto_validated_at IS NULL OR (auto_validated_at >= created_at AND auto_validated_at <= updated_at)) AND (approved_at IS NULL OR (approved_at >= created_at AND approved_at <= updated_at)) AND (published_at IS NULL OR (published_at >= created_at AND published_at <= updated_at)) AND (auto_validated = 0 OR (classroom_status = ''passed'' AND tts_status = ''passed'' AND asr_roundtrip_status = ''passed'' AND conversation_provider_status = ''passed'' AND auto_validated_at >= classroom_completed_at AND auto_validated_at >= tts_completed_at AND auto_validated_at >= asr_roundtrip_completed_at AND auto_validated_at >= conversation_provider_completed_at)) AND (publication_status <> ''published'' OR (auto_validated = 1 AND published_at >= auto_validated_at)))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_classroom_item_receipts'
    AND CONSTRAINT_NAME = 'chk_learning_classroom_receipt_timeline'
);
PREPARE add_receipt_timeline_check_stmt FROM @add_receipt_timeline_check;
EXECUTE add_receipt_timeline_check_stmt;
DEALLOCATE PREPARE add_receipt_timeline_check_stmt;

-- Every active legacy release is split by the distinct grades in its published
-- release items.  History retains every same-grade legacy active row in a
-- deterministic timeline and the pointer selects only the newest revision.
INSERT IGNORE INTO learning_curriculum_grade_release_history(
  id, grade_code, pointer_revision, target_fingerprint, contract_version,
  release_id, previous_history_id, previous_release_id, activation_source,
  publication_request_id, publication_receipt_hash, activated_at,
  superseded_at, created_at
)
SELECT
  ranked.history_id,
  ranked.grade_code,
  ranked.pointer_revision,
  ranked.target_fingerprint,
  'mira.learning.grade-release-pointer.legacy.v1',
  ranked.release_id,
  ranked.previous_history_id,
  ranked.previous_release_id,
  'legacy_backfill',
  NULL,
  NULL,
  ranked.activated_at,
  ranked.superseded_at,
  ranked.activated_at
FROM (
  SELECT base.*,
    ROW_NUMBER() OVER (
      PARTITION BY base.grade_code
      ORDER BY base.activated_at, base.release_id
    ) AS pointer_revision,
    LAG(base.history_id) OVER (
      PARTITION BY base.grade_code
      ORDER BY base.activated_at, base.release_id
    ) AS previous_history_id,
    LAG(base.release_id) OVER (
      PARTITION BY base.grade_code
      ORDER BY base.activated_at, base.release_id
    ) AS previous_release_id,
    LEAD(base.activated_at) OVER (
      PARTITION BY base.grade_code
      ORDER BY base.activated_at, base.release_id
    ) AS superseded_at
  FROM (
    SELECT release_row.id AS release_id,
      grade_scope.grade_code,
      CONCAT('grade_release_history_', LEFT(SHA2(CONCAT(
        'legacy:', grade_scope.grade_code, ':', release_row.id
      ), 256), 40)) AS history_id,
      COALESCE(
        build_scope.target_fingerprint,
        plan_scope.target_fingerprint,
        SHA2(CONCAT(
          'legacy-grade-release-v1:', grade_scope.grade_code,
          ':', release_row.id
        ), 256)
      ) AS target_fingerprint,
      GREATEST(COALESCE(
        release_row.activated_at, release_row.updated_at,
        release_row.created_at, 1
      ), 1) AS activated_at
    FROM learning_catalog_releases AS release_row
    JOIN (
      SELECT DISTINCT release_id, grade_code
      FROM learning_catalog_release_items
      WHERE status = 'published' AND retired_at IS NULL
    ) AS grade_scope ON grade_scope.release_id = release_row.id
    LEFT JOIN (
      SELECT release_id,
        MAX(CASE
          WHEN request_id REGEXP '^grade-build:[0-9a-f]{64}$'
            THEN SUBSTRING(request_id, 13)
          ELSE NULL
        END) AS target_fingerprint
      FROM learning_catalog_build_jobs
      GROUP BY release_id
    ) AS build_scope ON build_scope.release_id = release_row.id
    LEFT JOIN (
      SELECT catalog_release_id,
        CASE
          WHEN COUNT(DISTINCT target_fingerprint) = 1
            AND MAX(target_fingerprint) REGEXP '^[0-9a-f]{64}$'
            THEN MAX(target_fingerprint)
          ELSE NULL
        END AS target_fingerprint
      FROM learning_curriculum_preparation_plans
      WHERE catalog_release_id IS NOT NULL
      GROUP BY catalog_release_id
    ) AS plan_scope ON plan_scope.catalog_release_id = release_row.id
    WHERE release_row.status = 'active'
      AND release_row.quality_status = 'ready'
      AND release_row.retired_at IS NULL
  ) AS base
) AS ranked
ORDER BY ranked.grade_code, ranked.pointer_revision;

INSERT INTO learning_curriculum_grade_release_pointers(
  grade_code, pointer_revision, target_fingerprint, contract_version,
  release_id, history_id, activated_at, updated_at
)
SELECT history.grade_code, history.pointer_revision, history.target_fingerprint,
  history.contract_version, history.release_id, history.id,
  history.activated_at, history.activated_at
FROM learning_curriculum_grade_release_history AS history
LEFT JOIN learning_curriculum_grade_release_history AS newer
  ON newer.grade_code = history.grade_code
 AND newer.pointer_revision > history.pointer_revision
WHERE history.superseded_at IS NULL AND newer.id IS NULL
ON DUPLICATE KEY UPDATE
  pointer_revision = VALUES(pointer_revision),
  target_fingerprint = VALUES(target_fingerprint),
  contract_version = VALUES(contract_version),
  release_id = VALUES(release_id),
  history_id = VALUES(history_id),
  activated_at = VALUES(activated_at),
  updated_at = GREATEST(updated_at, VALUES(updated_at));

SET @add_runtime_candidate_index = (
  SELECT IF(COUNT(*) = 0,
    'CREATE UNIQUE INDEX uq_learning_openmaic_candidate_item_attempt ON learning_openmaic_runtime_classrooms(candidate_build_item_id, attempt_ordinal)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND INDEX_NAME = 'uq_learning_openmaic_candidate_item_attempt'
);
PREPARE add_runtime_candidate_index_stmt FROM @add_runtime_candidate_index;
EXECUTE add_runtime_candidate_index_stmt;
DEALLOCATE PREPARE add_runtime_candidate_index_stmt;

SET @add_runtime_candidate_item_fk = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD CONSTRAINT fk_learning_openmaic_candidate_item FOREIGN KEY (candidate_build_item_id) REFERENCES learning_catalog_build_items(id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND CONSTRAINT_NAME = 'fk_learning_openmaic_candidate_item'
);
PREPARE add_runtime_candidate_item_fk_stmt FROM @add_runtime_candidate_item_fk;
EXECUTE add_runtime_candidate_item_fk_stmt;
DEALLOCATE PREPARE add_runtime_candidate_item_fk_stmt;

SET @add_runtime_candidate_release_fk = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD CONSTRAINT fk_learning_openmaic_candidate_release FOREIGN KEY (candidate_release_id) REFERENCES learning_catalog_releases(id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND CONSTRAINT_NAME = 'fk_learning_openmaic_candidate_release'
);
PREPARE add_runtime_candidate_release_fk_stmt FROM @add_runtime_candidate_release_fk;
EXECUTE add_runtime_candidate_release_fk_stmt;
DEALLOCATE PREPARE add_runtime_candidate_release_fk_stmt;

SET @add_runtime_candidate_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD CONSTRAINT chk_learning_openmaic_candidate_binding CHECK ((candidate_build_item_id IS NULL AND candidate_release_id IS NULL AND candidate_grade_code IS NULL AND candidate_target_fingerprint IS NULL AND candidate_binding_contract_version IS NULL AND candidate_bound_at IS NULL) OR (candidate_build_item_id IS NOT NULL AND candidate_release_id IS NOT NULL AND candidate_grade_code IS NOT NULL AND candidate_grade_code <> '''' AND candidate_target_fingerprint IS NOT NULL AND candidate_target_fingerprint REGEXP ''^[0-9a-f]{64}$'' AND candidate_binding_contract_version IS NOT NULL AND candidate_binding_contract_version <> '''' AND candidate_bound_at IS NOT NULL AND candidate_bound_at > 0))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND CONSTRAINT_NAME = 'chk_learning_openmaic_candidate_binding'
);
PREPARE add_runtime_candidate_check_stmt FROM @add_runtime_candidate_check;
EXECUTE add_runtime_candidate_check_stmt;
DEALLOCATE PREPARE add_runtime_candidate_check_stmt;

SET @drop_legacy_runtime_attempt_check = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms DROP CHECK chk_learning_openmaic_runtime_attempt',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND CONSTRAINT_NAME = 'chk_learning_openmaic_runtime_attempt'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE drop_legacy_runtime_attempt_check_stmt FROM @drop_legacy_runtime_attempt_check;
EXECUTE drop_legacy_runtime_attempt_check_stmt;
DEALLOCATE PREPARE drop_legacy_runtime_attempt_check_stmt;

SET @add_candidate_runtime_attempt_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD CONSTRAINT chk_learning_openmaic_runtime_candidate_attempt CHECK (((candidate_build_item_id IS NULL AND attempt_ordinal = 1 AND retry_of_runtime_id IS NULL AND retry_reason IS NULL AND expected_previous_job_id IS NULL) OR (candidate_build_item_id IS NULL AND attempt_ordinal = 2 AND retry_of_runtime_id IS NOT NULL AND retry_reason IS NOT NULL AND retry_reason = ''approved_stage2_retry'' AND expected_previous_job_id IS NOT NULL) OR (candidate_build_item_id IS NULL AND attempt_ordinal = 3 AND retry_of_runtime_id IS NOT NULL AND retry_reason IS NOT NULL AND retry_reason = ''approved_stage2_retry_3'' AND expected_previous_job_id IS NOT NULL) OR (candidate_build_item_id IS NOT NULL AND attempt_ordinal = 1 AND retry_of_runtime_id IS NULL AND retry_reason IS NULL AND expected_previous_job_id IS NULL) OR (candidate_build_item_id IS NOT NULL AND attempt_ordinal = 2 AND retry_of_runtime_id IS NOT NULL AND retry_reason IS NOT NULL AND retry_reason = ''formal_candidate_retry_2'' AND expected_previous_job_id IS NOT NULL) OR (candidate_build_item_id IS NOT NULL AND attempt_ordinal = 3 AND retry_of_runtime_id IS NOT NULL AND retry_reason IS NOT NULL AND retry_reason = ''formal_candidate_retry_3'' AND expected_previous_job_id IS NOT NULL)))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND CONSTRAINT_NAME = 'chk_learning_openmaic_runtime_candidate_attempt'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_candidate_runtime_attempt_check_stmt FROM @add_candidate_runtime_attempt_check;
EXECUTE add_candidate_runtime_attempt_check_stmt;
DEALLOCATE PREPARE add_candidate_runtime_attempt_check_stmt;

-- 056 deliberately stops V2 at a lease-free building_classrooms handoff.
-- Phase II replaces that one state check so only an explicit formal resume can
-- claim the four remaining stages.  V1 behavior remains unchanged.
SET @drop_content_handoff_state_check = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_curriculum_preparation_plans DROP CHECK chk_learning_prep_content_state_evidence',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'chk_learning_prep_content_state_evidence'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE drop_content_handoff_state_check_stmt FROM @drop_content_handoff_state_check;
EXECUTE drop_content_handoff_state_check_stmt;
DEALLOCATE PREPARE drop_content_handoff_state_check_stmt;

SET @add_formal_state_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD CONSTRAINT chk_learning_prep_formal_state_evidence CHECK (preparation_contract_version = ''mira.learning.grade-preparation.v1'' AND target_spec_json IS NOT NULL AND JSON_VALID(target_spec_json) = 1 AND JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) IS NOT NULL AND ((JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.v1'' AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND (((status = ''queued'' AND stage = ''queued'' AND next_run_at IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage IN (''planning'', ''generating_content'', ''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND next_run_at IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage IN (''planning'', ''generating_content'', ''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND next_run_at IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND resume_stage IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''queued'' AND stage = ''retry_wait'' AND next_run_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND next_run_at <= hard_deadline_at AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND resume_stage IS NOT NULL AND resume_stage IN (''planning'', ''generating_content'', ''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL AND ((retry_reason_code IS NULL AND retry_message_safe IS NULL) OR (retry_reason_code IS NOT NULL AND retry_message_safe IS NOT NULL))) OR (status = ''ready'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NULL AND progress_percent = 100 AND ready_course_count = total_course_count AND failed_course_count = 0 AND error_code IS NULL AND error_message_safe IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL) OR (status = ''failed'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NULL AND error_code IS NOT NULL AND error_message_safe IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL) OR (status = ''superseded'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NOT NULL AND error_code IS NULL AND error_message_safe IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL)))) OR (JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.v2'' AND (((status = ''queued'' AND stage = ''queued'' AND next_run_at IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage IN (''planning'', ''generating_content'') AND next_run_at IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage IN (''planning'', ''generating_content'') AND next_run_at IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND resume_stage IS NULL AND work_unit_kind IS NOT NULL AND work_unit_kind = ''coordinator'' AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage = ''generating_content'' AND next_run_at IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND resume_stage IS NULL AND work_unit_kind IS NOT NULL AND work_unit_kind IN (''provider_phase'', ''host_gate'') AND bound_catalog_item_id IS NOT NULL AND bound_content_attempt_ordinal IS NOT NULL AND bound_content_attempt_ordinal BETWEEN 1 AND 2 AND bound_content_phase IS NOT NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''queued'' AND stage = ''retry_wait'' AND next_run_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND next_run_at <= hard_deadline_at AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND resume_stage IS NOT NULL AND resume_stage IN (''planning'', ''generating_content'') AND retry_reason_code IS NOT NULL AND retry_message_safe IS NOT NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL AND ((work_unit_kind IS NOT NULL AND work_unit_kind = ''coordinator'' AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL) OR (work_unit_kind IS NOT NULL AND work_unit_kind IN (''provider_phase'', ''host_gate'') AND bound_catalog_item_id IS NOT NULL AND bound_content_attempt_ordinal IS NOT NULL AND bound_content_attempt_ordinal BETWEEN 1 AND 2 AND bound_content_phase IS NOT NULL))) OR (status = ''failed'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NULL AND error_code IS NOT NULL AND error_message_safe IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL) OR (status = ''superseded'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NOT NULL AND error_code IS NULL AND error_message_safe IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL))) OR (JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.v2'' AND catalog_build_id IS NOT NULL AND catalog_release_id IS NOT NULL AND content_target_count = 30 AND content_candidate_count = 30 AND content_failed_count = 0 AND content_canary_target_count = 3 AND content_canary_candidate_count = 3 AND content_canary_failed_count = 0 AND content_canary_passed_at IS NOT NULL AND content_generation_completed_at IS NOT NULL AND (((status = ''running'' AND stage = ''building_classrooms'' AND ready_course_count = 0 AND failed_course_count = 0 AND progress_percent = 35 AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''running'' AND stage IN (''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND next_run_at IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL AND ((stage = ''building_classrooms'' AND progress_percent BETWEEN 40 AND 64) OR (stage = ''generating_speech'' AND progress_percent BETWEEN 65 AND 84) OR (stage = ''validating'' AND progress_percent BETWEEN 85 AND 94) OR (stage = ''publishing'' AND progress_percent BETWEEN 95 AND 99))) OR (status = ''running'' AND stage IN (''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND next_run_at IS NOT NULL AND lease_token IS NOT NULL AND lease_expires_at IS NOT NULL AND heartbeat_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND next_run_at <= hard_deadline_at AND resume_stage IS NULL AND work_unit_kind IS NOT NULL AND work_unit_kind = ''coordinator'' AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL AND ((stage = ''building_classrooms'' AND progress_percent BETWEEN 40 AND 64) OR (stage = ''generating_speech'' AND progress_percent BETWEEN 65 AND 84) OR (stage = ''validating'' AND progress_percent BETWEEN 85 AND 94) OR (stage = ''publishing'' AND progress_percent BETWEEN 95 AND 99))) OR (status = ''queued'' AND stage = ''retry_wait'' AND next_run_at IS NOT NULL AND hard_deadline_at IS NOT NULL AND next_run_at <= hard_deadline_at AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND resume_stage IS NOT NULL AND resume_stage IN (''building_classrooms'', ''generating_speech'', ''validating'', ''publishing'') AND work_unit_kind IS NOT NULL AND work_unit_kind = ''coordinator'' AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NOT NULL AND retry_message_safe IS NOT NULL AND completed_at IS NULL AND superseded_at IS NULL AND error_code IS NULL AND error_message_safe IS NULL) OR (status = ''ready'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NULL AND progress_percent = 100 AND ready_course_count = total_course_count AND failed_course_count = 0 AND error_code IS NULL AND error_message_safe IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL) OR (status = ''failed'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NULL AND error_code IS NOT NULL AND error_message_safe IS NOT NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL) OR (status = ''superseded'' AND stage = ''completed'' AND completed_at IS NOT NULL AND superseded_at IS NOT NULL AND error_code IS NULL AND error_message_safe IS NULL AND lease_token IS NULL AND lease_expires_at IS NULL AND heartbeat_at IS NULL AND next_run_at IS NULL AND hard_deadline_at IS NULL AND resume_stage IS NULL AND work_unit_kind IS NULL AND bound_catalog_item_id IS NULL AND bound_content_attempt_ordinal IS NULL AND bound_content_phase IS NULL AND retry_reason_code IS NULL AND retry_message_safe IS NULL))))))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'chk_learning_prep_formal_state_evidence'
    AND CONSTRAINT_TYPE = 'CHECK'
);
SET @add_formal_state_check = IF(
  @add_formal_state_check = 'SELECT 1',
  @add_formal_state_check,
  CONCAT(@add_formal_state_check, ')')
);
PREPARE add_formal_state_check_stmt FROM @add_formal_state_check;
EXECUTE add_formal_state_check_stmt;
DEALLOCATE PREPARE add_formal_state_check_stmt;

SET @add_plan_formal_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD CONSTRAINT chk_learning_prep_formal_publication CHECK (classroom_ready_count BETWEEN 0 AND total_course_count AND speech_ready_count BETWEEN 0 AND classroom_ready_count AND validation_ready_count BETWEEN 0 AND speech_ready_count AND published_course_count BETWEEN 0 AND validation_ready_count AND ((JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.v2'' AND status = ''ready'' AND stage = ''completed'' AND classroom_ready_count = total_course_count AND speech_ready_count = total_course_count AND validation_ready_count = total_course_count AND published_course_count = total_course_count AND catalog_release_id IS NOT NULL AND formal_contract_version IS NOT NULL AND formal_contract_version <> '''' AND formal_publication_history_id IS NOT NULL AND formal_publication_receipt_hash IS NOT NULL AND formal_publication_receipt_hash REGEXP ''^[0-9a-f]{64}$'' AND formal_ready_at IS NOT NULL AND formal_ready_at > 0) OR (NOT (JSON_UNQUOTE(JSON_EXTRACT(target_spec_json, ''$.schemaVersion'')) = ''mira.learning.preparation-target.v2'' AND status = ''ready'') AND formal_contract_version IS NULL AND formal_publication_history_id IS NULL AND formal_publication_receipt_hash IS NULL AND formal_ready_at IS NULL)))',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'chk_learning_prep_formal_publication'
);
PREPARE add_plan_formal_check_stmt FROM @add_plan_formal_check;
EXECUTE add_plan_formal_check_stmt;
DEALLOCATE PREPARE add_plan_formal_check_stmt;

SET @drop_plan_formal_history_fk = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_curriculum_preparation_plans DROP FOREIGN KEY fk_learning_prep_formal_history',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'fk_learning_prep_formal_history'
);
PREPARE drop_plan_formal_history_fk_stmt FROM @drop_plan_formal_history_fk;
EXECUTE drop_plan_formal_history_fk_stmt;
DEALLOCATE PREPARE drop_plan_formal_history_fk_stmt;

SET @add_plan_formal_history_fk = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_preparation_plans ADD CONSTRAINT fk_learning_prep_formal_history_exact FOREIGN KEY (formal_publication_history_id, grade_code, target_fingerprint, formal_contract_version, catalog_release_id, formal_publication_receipt_hash) REFERENCES learning_curriculum_grade_release_history(id, grade_code, target_fingerprint, contract_version, release_id, publication_receipt_hash)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_preparation_plans'
    AND CONSTRAINT_NAME = 'fk_learning_prep_formal_history_exact'
);
PREPARE add_plan_formal_history_fk_stmt FROM @add_plan_formal_history_fk;
EXECUTE add_plan_formal_history_fk_stmt;
DEALLOCATE PREPARE add_plan_formal_history_fk_stmt;

SET @verify_057 = (
  SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME IN (
          'learning_curriculum_grade_release_history',
          'learning_curriculum_grade_release_pointers',
          'learning_curriculum_classroom_item_receipts'
        )) = 3
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
        AND COLUMN_NAME IN (
          'candidate_build_item_id', 'candidate_release_id',
          'candidate_grade_code', 'candidate_target_fingerprint',
          'candidate_binding_contract_version', 'candidate_bound_at'
        )) = 6
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_curriculum_preparation_plans'
        AND COLUMN_NAME IN (
          'classroom_ready_count', 'speech_ready_count',
          'validation_ready_count', 'published_course_count',
          'formal_contract_version', 'formal_publication_history_id',
          'formal_publication_receipt_hash', 'formal_ready_at'
        )) = 8,
    'SELECT 1',
    'SIGNAL SQLSTATE ''45000'' SET MESSAGE_TEXT = ''057 schema verification failed'''
  )
);
PREPARE verify_057_stmt FROM @verify_057;
EXECUTE verify_057_stmt;
DEALLOCATE PREPARE verify_057_stmt;
