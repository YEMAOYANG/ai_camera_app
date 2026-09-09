-- Permit an immutable student Runtime binding to be authorized either by the
-- shared final grade pointer or by the exact current child preparation plan.
-- Progressive bindings never invent grade history or mutate the grade pointer.

SET @drop_070_binding_identity_check = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_student_formal_session_bindings DROP CHECK chk_lsfsb_identity',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND CONSTRAINT_NAME = 'chk_lsfsb_identity'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE drop_070_binding_identity_check_stmt
  FROM @drop_070_binding_identity_check;
EXECUTE drop_070_binding_identity_check_stmt;
DEALLOCATE PREPARE drop_070_binding_identity_check_stmt;

SET @make_070_pointer_history_nullable = (
  SELECT IF(COUNT(*) = 1 AND MAX(IS_NULLABLE) = 'NO',
    'ALTER TABLE learning_student_formal_session_bindings MODIFY COLUMN pointer_history_id VARCHAR(128) NULL',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND COLUMN_NAME = 'pointer_history_id'
);
PREPARE make_070_pointer_history_nullable_stmt
  FROM @make_070_pointer_history_nullable;
EXECUTE make_070_pointer_history_nullable_stmt;
DEALLOCATE PREPARE make_070_pointer_history_nullable_stmt;

SET @make_070_pointer_revision_nullable = (
  SELECT IF(COUNT(*) = 1 AND MAX(IS_NULLABLE) = 'NO',
    'ALTER TABLE learning_student_formal_session_bindings MODIFY COLUMN pointer_revision INTEGER NULL',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND COLUMN_NAME = 'pointer_revision'
);
PREPARE make_070_pointer_revision_nullable_stmt
  FROM @make_070_pointer_revision_nullable;
EXECUTE make_070_pointer_revision_nullable_stmt;
DEALLOCATE PREPARE make_070_pointer_revision_nullable_stmt;

SET @add_070_authority_kind = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_student_formal_session_bindings ADD COLUMN authority_kind VARCHAR(32) NOT NULL DEFAULT ''active_pointer'' AFTER grade_code',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND COLUMN_NAME = 'authority_kind'
);
PREPARE add_070_authority_kind_stmt FROM @add_070_authority_kind;
EXECUTE add_070_authority_kind_stmt;
DEALLOCATE PREPARE add_070_authority_kind_stmt;

SET @add_070_preparation_plan_id = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_student_formal_session_bindings ADD COLUMN preparation_plan_id VARCHAR(128) NULL AFTER pointer_revision',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND COLUMN_NAME = 'preparation_plan_id'
);
PREPARE add_070_preparation_plan_id_stmt FROM @add_070_preparation_plan_id;
EXECUTE add_070_preparation_plan_id_stmt;
DEALLOCATE PREPARE add_070_preparation_plan_id_stmt;

SET @add_070_grade_selection_revision = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_student_formal_session_bindings ADD COLUMN grade_selection_revision INTEGER NULL AFTER preparation_plan_id',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND COLUMN_NAME = 'grade_selection_revision'
);
PREPARE add_070_grade_selection_revision_stmt
  FROM @add_070_grade_selection_revision;
EXECUTE add_070_grade_selection_revision_stmt;
DEALLOCATE PREPARE add_070_grade_selection_revision_stmt;

SET @add_070_plan_index = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_student_formal_session_bindings ADD INDEX idx_lsfsb_progressive_plan(preparation_plan_id, grade_selection_revision, bound_at)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND INDEX_NAME = 'idx_lsfsb_progressive_plan'
);
PREPARE add_070_plan_index_stmt FROM @add_070_plan_index;
EXECUTE add_070_plan_index_stmt;
DEALLOCATE PREPARE add_070_plan_index_stmt;

SET @add_070_plan_fk = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_student_formal_session_bindings ADD CONSTRAINT fk_lsfsb_progressive_plan FOREIGN KEY (preparation_plan_id) REFERENCES learning_curriculum_preparation_plans(id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND CONSTRAINT_NAME = 'fk_lsfsb_progressive_plan'
    AND REFERENCED_TABLE_NAME = 'learning_curriculum_preparation_plans'
);
PREPARE add_070_plan_fk_stmt FROM @add_070_plan_fk;
EXECUTE add_070_plan_fk_stmt;
DEALLOCATE PREPARE add_070_plan_fk_stmt;

ALTER TABLE learning_student_formal_session_bindings
  ADD CONSTRAINT chk_lsfsb_identity CHECK (
    learning_session_id <> ''
    AND family_id <> '' AND child_id <> ''
    AND grade_code REGEXP '^primary_[1-6]$'
    AND authority_kind IN ('active_pointer', 'progressive_plan')
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
    )
  );

SET @drop_070_authority_kind_default = (
  SELECT IF(COUNT(*) = 1 AND MAX(COLUMN_DEFAULT) IS NOT NULL,
    'ALTER TABLE learning_student_formal_session_bindings ALTER COLUMN authority_kind DROP DEFAULT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND COLUMN_NAME = 'authority_kind'
);
PREPARE drop_070_authority_kind_default_stmt
  FROM @drop_070_authority_kind_default;
EXECUTE drop_070_authority_kind_default_stmt;
DEALLOCATE PREPARE drop_070_authority_kind_default_stmt;

SET @verify_070 = (
  SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND COLUMN_NAME IN (
          'authority_kind', 'preparation_plan_id',
          'grade_selection_revision'
        )) = 3
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND COLUMN_NAME IN ('pointer_history_id', 'pointer_revision')
        AND IS_NULLABLE = 'YES') = 2
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND CONSTRAINT_NAME = 'chk_lsfsb_identity'
        AND CONSTRAINT_TYPE = 'CHECK') = 1
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND CONSTRAINT_NAME = 'fk_lsfsb_progressive_plan'
        AND REFERENCED_TABLE_NAME =
          'learning_curriculum_preparation_plans') = 1,
    'SELECT 1',
    'SIGNAL SQLSTATE ''45000'' SET MESSAGE_TEXT = ''070 schema verification failed'''
  )
);
PREPARE verify_070_stmt FROM @verify_070;
EXECUTE verify_070_stmt;
DEALLOCATE PREPARE verify_070_stmt;
