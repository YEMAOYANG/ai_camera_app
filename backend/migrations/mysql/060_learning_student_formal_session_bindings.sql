-- Immutable formal identity snapshot for a student learning session
--
-- A binding points at release history rather than the mutable grade pointer so
-- an already-started session resumes the same classroom after a later publish.
-- Existing sessions are deliberately not backfilled because they do not carry
-- enough evidence to prove the historical pointer, build item and Runtime row.

-- The original learning runtime used 128-character subject identifiers while
-- the authoritative families/children tables use VARCHAR(255).  Widen the
-- session authority before adding the composite foreign key below so MySQL can
-- enforce the same child identity all the way through the formal binding.
ALTER TABLE learning_sessions
  MODIFY COLUMN family_id VARCHAR(255) NOT NULL,
  MODIFY COLUMN child_id VARCHAR(255) NOT NULL;

SET @add_060_child_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE children ADD UNIQUE INDEX uq_children_formal_family_child(family_id, id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND INDEX_NAME = 'uq_children_formal_family_child'
);
PREPARE add_060_child_authority_stmt FROM @add_060_child_authority;
EXECUTE add_060_child_authority_stmt;
DEALLOCATE PREPARE add_060_child_authority_stmt;

SET @add_060_session_subject_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_sessions ADD UNIQUE INDEX uq_learning_sessions_formal_subject(id, family_id, child_id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_sessions'
    AND INDEX_NAME = 'uq_learning_sessions_formal_subject'
);
PREPARE add_060_session_subject_authority_stmt
  FROM @add_060_session_subject_authority;
EXECUTE add_060_session_subject_authority_stmt;
DEALLOCATE PREPARE add_060_session_subject_authority_stmt;

SET @add_060_session_course_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_sessions ADD UNIQUE INDEX uq_learning_sessions_formal_course(id, course_id, course_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_sessions'
    AND INDEX_NAME = 'uq_learning_sessions_formal_course'
);
PREPARE add_060_session_course_authority_stmt
  FROM @add_060_session_course_authority;
EXECUTE add_060_session_course_authority_stmt;
DEALLOCATE PREPARE add_060_session_course_authority_stmt;

SET @add_060_session_package_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_sessions ADD UNIQUE INDEX uq_learning_sessions_formal_package(id, lesson_package_id, lesson_package_version, lesson_package_content_hash)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_sessions'
    AND INDEX_NAME = 'uq_learning_sessions_formal_package'
);
PREPARE add_060_session_package_authority_stmt
  FROM @add_060_session_package_authority;
EXECUTE add_060_session_package_authority_stmt;
DEALLOCATE PREPARE add_060_session_package_authority_stmt;

SET @add_060_history_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_grade_release_history ADD UNIQUE INDEX uq_learning_grade_history_formal_binding(id, grade_code, pointer_revision, target_fingerprint, contract_version, release_id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_grade_release_history'
    AND INDEX_NAME = 'uq_learning_grade_history_formal_binding'
);
PREPARE add_060_history_authority_stmt FROM @add_060_history_authority;
EXECUTE add_060_history_authority_stmt;
DEALLOCATE PREPARE add_060_history_authority_stmt;

SET @add_060_release_item_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_release_items ADD UNIQUE INDEX uq_learning_release_item_formal_binding(release_id, grade_code, course_id, course_version, package_id, package_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_catalog_release_items'
    AND INDEX_NAME = 'uq_learning_release_item_formal_binding'
);
PREPARE add_060_release_item_authority_stmt
  FROM @add_060_release_item_authority;
EXECUTE add_060_release_item_authority_stmt;
DEALLOCATE PREPARE add_060_release_item_authority_stmt;

SET @add_060_build_release_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD UNIQUE INDEX uq_learning_build_item_formal_release(id, release_id, grade_code)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_catalog_build_items'
    AND INDEX_NAME = 'uq_learning_build_item_formal_release'
);
PREPARE add_060_build_release_authority_stmt
  FROM @add_060_build_release_authority;
EXECUTE add_060_build_release_authority_stmt;
DEALLOCATE PREPARE add_060_build_release_authority_stmt;

SET @add_060_build_course_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD UNIQUE INDEX uq_learning_build_item_formal_course(id, course_id, course_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_catalog_build_items'
    AND INDEX_NAME = 'uq_learning_build_item_formal_course'
);
PREPARE add_060_build_course_authority_stmt
  FROM @add_060_build_course_authority;
EXECUTE add_060_build_course_authority_stmt;
DEALLOCATE PREPARE add_060_build_course_authority_stmt;

SET @add_060_build_package_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_catalog_build_items ADD UNIQUE INDEX uq_learning_build_item_formal_package(id, package_id, package_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_catalog_build_items'
    AND INDEX_NAME = 'uq_learning_build_item_formal_package'
);
PREPARE add_060_build_package_authority_stmt
  FROM @add_060_build_package_authority;
EXECUTE add_060_build_package_authority_stmt;
DEALLOCATE PREPARE add_060_build_package_authority_stmt;

SET @add_060_package_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_lesson_packages ADD UNIQUE INDEX uq_learning_package_formal_binding(id, version, course_id, course_version, public_content_hash)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_lesson_packages'
    AND INDEX_NAME = 'uq_learning_package_formal_binding'
);
PREPARE add_060_package_authority_stmt FROM @add_060_package_authority;
EXECUTE add_060_package_authority_stmt;
DEALLOCATE PREPARE add_060_package_authority_stmt;

SET @add_060_runtime_candidate_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD UNIQUE INDEX uq_learning_runtime_formal_candidate(id, candidate_build_item_id, candidate_release_id, candidate_grade_code, candidate_target_fingerprint, candidate_binding_contract_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND INDEX_NAME = 'uq_learning_runtime_formal_candidate'
);
PREPARE add_060_runtime_candidate_authority_stmt
  FROM @add_060_runtime_candidate_authority;
EXECUTE add_060_runtime_candidate_authority_stmt;
DEALLOCATE PREPARE add_060_runtime_candidate_authority_stmt;

SET @add_060_runtime_course_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD UNIQUE INDEX uq_learning_runtime_formal_course(id, course_id, course_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND INDEX_NAME = 'uq_learning_runtime_formal_course'
);
PREPARE add_060_runtime_course_authority_stmt
  FROM @add_060_runtime_course_authority;
EXECUTE add_060_runtime_course_authority_stmt;
DEALLOCATE PREPARE add_060_runtime_course_authority_stmt;

SET @add_060_runtime_package_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD UNIQUE INDEX uq_learning_runtime_formal_package(id, package_id, package_version)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND INDEX_NAME = 'uq_learning_runtime_formal_package'
);
PREPARE add_060_runtime_package_authority_stmt
  FROM @add_060_runtime_package_authority;
EXECUTE add_060_runtime_package_authority_stmt;
DEALLOCATE PREPARE add_060_runtime_package_authority_stmt;

SET @add_060_runtime_upstream_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_runtime_classrooms ADD UNIQUE INDEX uq_learning_runtime_formal_upstream(id, upstream_classroom_id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_runtime_classrooms'
    AND INDEX_NAME = 'uq_learning_runtime_formal_upstream'
);
PREPARE add_060_runtime_upstream_authority_stmt
  FROM @add_060_runtime_upstream_authority;
EXECUTE add_060_runtime_upstream_authority_stmt;
DEALLOCATE PREPARE add_060_runtime_upstream_authority_stmt;

SET @add_060_publication_receipt_authority = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_classroom_item_receipts ADD UNIQUE INDEX uq_learning_receipt_formal_binding(build_item_id, release_id, runtime_classroom_id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_classroom_item_receipts'
    AND INDEX_NAME = 'uq_learning_receipt_formal_binding'
);
PREPARE add_060_publication_receipt_authority_stmt
  FROM @add_060_publication_receipt_authority;
EXECUTE add_060_publication_receipt_authority_stmt;
DEALLOCATE PREPARE add_060_publication_receipt_authority_stmt;

CREATE TABLE IF NOT EXISTS learning_student_formal_session_bindings (
  learning_session_id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  pointer_history_id VARCHAR(128) NOT NULL,
  pointer_revision INTEGER NOT NULL,
  release_id VARCHAR(128) NOT NULL,
  target_fingerprint CHAR(64) NOT NULL,
  publication_contract_version VARCHAR(128) NOT NULL,
  build_item_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  package_id VARCHAR(128) NOT NULL,
  package_version INTEGER NOT NULL,
  package_content_hash CHAR(64) NOT NULL,
  runtime_classroom_id VARCHAR(128) NOT NULL,
  upstream_classroom_id VARCHAR(255) NOT NULL,
  bound_at BIGINT NOT NULL,
  created_at BIGINT NOT NULL,
  INDEX idx_student_formal_binding_child(
    family_id, child_id, bound_at
  ),
  INDEX idx_student_formal_binding_release(
    release_id, grade_code, bound_at
  ),
  INDEX idx_student_formal_binding_runtime(
    runtime_classroom_id, bound_at
  ),
  CONSTRAINT fk_lsfsb_family
    FOREIGN KEY (family_id) REFERENCES families(id),
  CONSTRAINT fk_lsfsb_child
    FOREIGN KEY (family_id, child_id)
      REFERENCES children(family_id, id),
  CONSTRAINT fk_lsfsb_session_subject
    FOREIGN KEY (learning_session_id, family_id, child_id)
      REFERENCES learning_sessions(id, family_id, child_id),
  CONSTRAINT fk_lsfsb_session_course
    FOREIGN KEY (learning_session_id, course_id, course_version)
      REFERENCES learning_sessions(id, course_id, course_version),
  CONSTRAINT fk_lsfsb_session_package
    FOREIGN KEY (
      learning_session_id, package_id, package_version, package_content_hash
    ) REFERENCES learning_sessions(
      id, lesson_package_id, lesson_package_version,
      lesson_package_content_hash
    ),
  CONSTRAINT fk_lsfsb_history
    FOREIGN KEY (
      pointer_history_id, grade_code, pointer_revision, target_fingerprint,
      publication_contract_version, release_id
    ) REFERENCES learning_curriculum_grade_release_history(
      id, grade_code, pointer_revision, target_fingerprint,
      contract_version, release_id
    ),
  CONSTRAINT fk_lsfsb_release_item
    FOREIGN KEY (
      release_id, grade_code, course_id, course_version,
      package_id, package_version
    ) REFERENCES learning_catalog_release_items(
      release_id, grade_code, course_id, course_version,
      package_id, package_version
    ),
  CONSTRAINT fk_lsfsb_build_release
    FOREIGN KEY (build_item_id, release_id, grade_code)
      REFERENCES learning_catalog_build_items(id, release_id, grade_code),
  CONSTRAINT fk_lsfsb_build_course
    FOREIGN KEY (build_item_id, course_id, course_version)
      REFERENCES learning_catalog_build_items(id, course_id, course_version),
  CONSTRAINT fk_lsfsb_build_package
    FOREIGN KEY (build_item_id, package_id, package_version)
      REFERENCES learning_catalog_build_items(id, package_id, package_version),
  CONSTRAINT fk_lsfsb_package
    FOREIGN KEY (
      package_id, package_version, course_id, course_version,
      package_content_hash
    ) REFERENCES learning_lesson_packages(
      id, version, course_id, course_version, public_content_hash
    ),
  CONSTRAINT fk_lsfsb_runtime_candidate
    FOREIGN KEY (
      runtime_classroom_id, build_item_id, release_id, grade_code,
      target_fingerprint, publication_contract_version
    ) REFERENCES learning_openmaic_runtime_classrooms(
      id, candidate_build_item_id, candidate_release_id, candidate_grade_code,
      candidate_target_fingerprint, candidate_binding_contract_version
    ),
  CONSTRAINT fk_lsfsb_runtime_course
    FOREIGN KEY (runtime_classroom_id, course_id, course_version)
      REFERENCES learning_openmaic_runtime_classrooms(
        id, course_id, course_version
      ),
  CONSTRAINT fk_lsfsb_runtime_package
    FOREIGN KEY (runtime_classroom_id, package_id, package_version)
      REFERENCES learning_openmaic_runtime_classrooms(
        id, package_id, package_version
      ),
  CONSTRAINT fk_lsfsb_runtime_upstream
    FOREIGN KEY (runtime_classroom_id, upstream_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(
        id, upstream_classroom_id
      ),
  CONSTRAINT fk_lsfsb_publication_receipt
    FOREIGN KEY (build_item_id, release_id, runtime_classroom_id)
      REFERENCES learning_curriculum_classroom_item_receipts(
        build_item_id, release_id, runtime_classroom_id
      ),
  CONSTRAINT chk_lsfsb_identity CHECK (
    learning_session_id <> ''
    AND family_id <> '' AND child_id <> ''
    AND grade_code REGEXP '^primary_[1-6]$'
    AND pointer_history_id <> '' AND pointer_revision >= 1
    AND release_id <> ''
    AND target_fingerprint REGEXP '^[0-9a-f]{64}$'
    AND publication_contract_version =
      'mira.learning.formal-publication.v1'
    AND build_item_id <> ''
    AND course_id <> '' AND course_version <> ''
    AND package_id <> '' AND package_version > 0
    AND package_content_hash REGEXP '^[0-9a-f]{64}$'
    AND runtime_classroom_id <> '' AND upstream_classroom_id <> ''
  ),
  CONSTRAINT chk_lsfsb_immutable_timeline CHECK (
    bound_at > 0 AND created_at = bound_at
  )
);

SET @verify_060 = (
  SELECT IF(
    (SELECT COUNT(*) FROM INFORMATION_SCHEMA.TABLES
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings') = 1
    AND (SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS
      WHERE TABLE_SCHEMA = DATABASE()
        AND TABLE_NAME = 'learning_student_formal_session_bindings'
        AND COLUMN_NAME IN (
          'learning_session_id', 'family_id', 'child_id', 'grade_code',
          'pointer_history_id', 'pointer_revision', 'release_id',
          'target_fingerprint', 'publication_contract_version',
          'build_item_id', 'course_id', 'course_version', 'package_id',
          'package_version', 'package_content_hash', 'runtime_classroom_id',
          'upstream_classroom_id', 'bound_at', 'created_at'
        )) = 19,
    'SELECT 1',
    'SIGNAL SQLSTATE ''45000'' SET MESSAGE_TEXT = ''060 schema verification failed'''
  )
);
PREPARE verify_060_stmt FROM @verify_060;
EXECUTE verify_060_stmt;
DEALLOCATE PREPARE verify_060_stmt;
