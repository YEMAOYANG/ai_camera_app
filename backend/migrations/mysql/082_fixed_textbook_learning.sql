-- Additive textbook foundation. Does not migrate/re-label existing courses.
CREATE TABLE IF NOT EXISTS learning_textbook_editions (
  edition_id VARCHAR(80) PRIMARY KEY,
  identity_sha256 CHAR(64) NOT NULL,
  identity_json JSON NOT NULL,
  imported_at BIGINT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS learning_textbook_revisions (
  edition_id VARCHAR(80) NOT NULL,
  revision_id VARCHAR(80) NOT NULL,
  grade_code VARCHAR(32) NOT NULL,
  subject VARCHAR(32) NOT NULL,
  manifest_sha256 CHAR(64) NOT NULL,
  manifest_json JSON NOT NULL,
  imported_at BIGINT NOT NULL,
  retired_at BIGINT,
  PRIMARY KEY (edition_id, revision_id),
  CONSTRAINT fk_textbook_revision_edition FOREIGN KEY (edition_id)
    REFERENCES learning_textbook_editions (edition_id),
  INDEX idx_textbook_grade (grade_code, subject, retired_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS learning_textbook_selections (
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  school_year_start INT NOT NULL,
  semester VARCHAR(16) NOT NULL,
  subject VARCHAR(32) NOT NULL,
  edition_id VARCHAR(80) NOT NULL,
  revision_id VARCHAR(80) NOT NULL,
  grade_revision INT NOT NULL,
  selection_revision INT NOT NULL,
  current_node_id VARCHAR(80),
  confirmed_by VARCHAR(128) NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (family_id, child_id, school_year_start, semester, subject),
  CONSTRAINT fk_textbook_selection_revision FOREIGN KEY (edition_id, revision_id)
    REFERENCES learning_textbook_revisions (edition_id, revision_id),
  CONSTRAINT chk_textbook_selection CHECK (selection_revision >= 1 AND grade_revision >= 1
    AND semester IN ('upper', 'lower') AND subject IN ('chinese', 'math', 'english'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS learning_textbook_course_builds (
  content_key CHAR(64) PRIMARY KEY,
  edition_id VARCHAR(80) NOT NULL,
  revision_id VARCHAR(80) NOT NULL,
  node_id VARCHAR(80) NOT NULL,
  part_index INT NOT NULL,
  teaching_revision VARCHAR(80) NOT NULL,
  input_json JSON NOT NULL,
  status VARCHAR(24) NOT NULL,
  course_id VARCHAR(255),
  course_version VARCHAR(64),
  course_content_sha256 CHAR(64),
  review_json JSON,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_textbook_course_version (course_id, course_version),
  UNIQUE KEY uq_textbook_lesson_build (edition_id, revision_id, node_id, part_index, teaching_revision),
  CONSTRAINT fk_textbook_build_revision FOREIGN KEY (edition_id, revision_id)
    REFERENCES learning_textbook_revisions (edition_id, revision_id),
  CONSTRAINT chk_textbook_build CHECK (part_index BETWEEN 1 AND 20
    AND status IN ('prepared', 'published', 'retired')
    AND (status <> 'published' OR (course_id IS NOT NULL AND course_version IS NOT NULL
      AND course_content_sha256 IS NOT NULL AND review_json IS NOT NULL)))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS learning_textbook_selection_events (
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  school_year_start INT NOT NULL,
  semester VARCHAR(16) NOT NULL,
  subject VARCHAR(32) NOT NULL,
  selection_revision INT NOT NULL,
  selection_json JSON NOT NULL,
  created_at BIGINT NOT NULL,
  PRIMARY KEY (family_id, child_id, school_year_start, semester, subject, selection_revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
