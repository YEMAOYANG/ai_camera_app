-- Content-only V2 build items intentionally own the generated course but do
-- not own the later materialized lesson package. Package authority is frozen
-- independently by the release item, lesson package, Runtime and receipt FKs.

SET @drop_067_build_package_fk = (
  SELECT IF(COUNT(*) > 0,
    'ALTER TABLE learning_student_formal_session_bindings DROP FOREIGN KEY fk_lsfsb_build_package',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
  WHERE CONSTRAINT_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_student_formal_session_bindings'
    AND CONSTRAINT_NAME = 'fk_lsfsb_build_package'
    AND REFERENCED_TABLE_NAME = 'learning_catalog_build_items'
);
PREPARE drop_067_build_package_fk_stmt FROM @drop_067_build_package_fk;
EXECUTE drop_067_build_package_fk_stmt;
DEALLOCATE PREPARE drop_067_build_package_fk_stmt;

-- MySQL can retain the supporting index after the FK is dropped. It encodes
-- the same invalid cross-stage identity, so remove only that orphaned index.
SET @drop_067_build_package_index = (
  SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND INDEX_NAME = 'fk_lsfsb_build_package') > 0
    AND
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND CONSTRAINT_NAME = 'fk_lsfsb_build_package'
        AND REFERENCED_TABLE_NAME IS NOT NULL) = 0,
    'ALTER TABLE learning_student_formal_session_bindings DROP INDEX fk_lsfsb_build_package',
    'SELECT 1')
);
PREPARE drop_067_build_package_index_stmt FROM @drop_067_build_package_index;
EXECUTE drop_067_build_package_index_stmt;
DEALLOCATE PREPARE drop_067_build_package_index_stmt;

SET @verify_067 = (
  SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
      WHERE CONSTRAINT_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND CONSTRAINT_NAME = 'fk_lsfsb_build_package'
        AND REFERENCED_TABLE_NAME IS NOT NULL) = 0
    AND
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.STATISTICS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND INDEX_NAME = 'fk_lsfsb_build_package') = 0,
    'SELECT 1',
    'SIGNAL SQLSTATE ''45000'' SET MESSAGE_TEXT = ''067 schema verification failed'''
  )
);
PREPARE verify_067_stmt FROM @verify_067;
EXECUTE verify_067_stmt;
DEALLOCATE PREPARE verify_067_stmt;
