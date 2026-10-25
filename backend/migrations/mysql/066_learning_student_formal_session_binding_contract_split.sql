-- Keep the formal publication contract and Runtime candidate-binding contract
-- as separate immutable authorities on every student session binding.

SET @add_066_runtime_binding_contract_version = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_student_formal_session_bindings ADD COLUMN runtime_binding_contract_version VARCHAR(128) NOT NULL DEFAULT ''mira.learning.candidate-runtime-binding.v1'' AFTER publication_contract_version',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND COLUMN_NAME = 'runtime_binding_contract_version'
);
PREPARE add_066_runtime_binding_contract_version_stmt
  FROM @add_066_runtime_binding_contract_version;
EXECUTE add_066_runtime_binding_contract_version_stmt;
DEALLOCATE PREPARE add_066_runtime_binding_contract_version_stmt;

SET @drop_066_conflated_runtime_fk = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_student_formal_session_bindings DROP FOREIGN KEY fk_lsfsb_runtime_candidate',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND CONSTRAINT_NAME = 'fk_lsfsb_runtime_candidate'
    AND COLUMN_NAME = 'publication_contract_version'
    AND REFERENCED_COLUMN_NAME = 'candidate_binding_contract_version'
);
PREPARE drop_066_conflated_runtime_fk_stmt
  FROM @drop_066_conflated_runtime_fk;
EXECUTE drop_066_conflated_runtime_fk_stmt;
DEALLOCATE PREPARE drop_066_conflated_runtime_fk_stmt;

-- MySQL keeps the supporting index when a foreign key is dropped. Remove only
-- the obsolete index whose final column is the publication contract. A
-- correctly rebuilt candidate-binding index is deliberately left untouched.
SET @drop_066_conflated_runtime_index = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_student_formal_session_bindings DROP INDEX fk_lsfsb_runtime_candidate',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND INDEX_NAME = 'fk_lsfsb_runtime_candidate'
    AND COLUMN_NAME = 'publication_contract_version'
);
PREPARE drop_066_conflated_runtime_index_stmt
  FROM @drop_066_conflated_runtime_index;
EXECUTE drop_066_conflated_runtime_index_stmt;
DEALLOCATE PREPARE drop_066_conflated_runtime_index_stmt;

SET @add_066_runtime_binding_fk = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_student_formal_session_bindings ADD CONSTRAINT fk_lsfsb_runtime_candidate FOREIGN KEY (runtime_classroom_id, build_item_id, release_id, grade_code, target_fingerprint, runtime_binding_contract_version) REFERENCES learning_openmaic_runtime_classrooms(id, candidate_build_item_id, candidate_release_id, candidate_grade_code, candidate_target_fingerprint, candidate_binding_contract_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND CONSTRAINT_NAME = 'fk_lsfsb_runtime_candidate'
    AND COLUMN_NAME = 'runtime_binding_contract_version'
    AND REFERENCED_COLUMN_NAME = 'candidate_binding_contract_version'
);
PREPARE add_066_runtime_binding_fk_stmt FROM @add_066_runtime_binding_fk;
EXECUTE add_066_runtime_binding_fk_stmt;
DEALLOCATE PREPARE add_066_runtime_binding_fk_stmt;

SET @add_066_runtime_binding_check = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_student_formal_session_bindings ADD CONSTRAINT chk_lsfsb_runtime_binding_contract CHECK (runtime_binding_contract_version = ''mira.learning.candidate-runtime-binding.v1'')',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND CONSTRAINT_NAME = 'chk_lsfsb_runtime_binding_contract'
    AND CONSTRAINT_TYPE = 'CHECK'
);
PREPARE add_066_runtime_binding_check_stmt
  FROM @add_066_runtime_binding_check;
EXECUTE add_066_runtime_binding_check_stmt;
DEALLOCATE PREPARE add_066_runtime_binding_check_stmt;

SET @drop_066_runtime_binding_default = (
  SELECT IF(COUNT(*) = 1 AND MAX(COLUMN_DEFAULT) IS NOT NULL,
    'ALTER TABLE learning_student_formal_session_bindings ALTER COLUMN runtime_binding_contract_version DROP DEFAULT',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND COLUMN_NAME = 'runtime_binding_contract_version'
);
PREPARE drop_066_runtime_binding_default_stmt
  FROM @drop_066_runtime_binding_default;
EXECUTE drop_066_runtime_binding_default_stmt;
DEALLOCATE PREPARE drop_066_runtime_binding_default_stmt;

SET @verify_066 = (
  SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND COLUMN_NAME = 'runtime_binding_contract_version'
        AND IS_NULLABLE = 'NO'
        AND COLUMN_DEFAULT IS NULL) = 1
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND CONSTRAINT_NAME = 'fk_lsfsb_runtime_candidate'
        AND COLUMN_NAME = 'runtime_binding_contract_version'
        AND REFERENCED_COLUMN_NAME = 'candidate_binding_contract_version') = 1
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND CONSTRAINT_NAME = 'fk_lsfsb_runtime_candidate'
        AND COLUMN_NAME = 'publication_contract_version') = 0
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND CONSTRAINT_NAME = 'chk_lsfsb_runtime_binding_contract'
        AND CONSTRAINT_TYPE = 'CHECK') = 1,
    'SELECT 1',
    'SIGNAL SQLSTATE ''45000'' SET MESSAGE_TEXT = ''066 schema verification failed'''
  )
);
PREPARE verify_066_stmt FROM @verify_066;
EXECUTE verify_066_stmt;
DEALLOCATE PREPARE verify_066_stmt;
