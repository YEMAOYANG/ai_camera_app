-- A placement is a single, immutable opportunity per child and prerequisite.
-- Reserved questions remain exposed after abandonment, grade changes or failure.
CREATE TABLE IF NOT EXISTS learning_placement_attempts (
  id VARCHAR(80) PRIMARY KEY,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  curriculum_version VARCHAR(64) NOT NULL,
  grade_code VARCHAR(32) NOT NULL,
  grade_revision INT NOT NULL,
  subject VARCHAR(32) NOT NULL,
  lesson_id VARCHAR(128) NOT NULL,
  policy_json JSON NOT NULL,
  status VARCHAR(24) NOT NULL,
  total_questions INT NOT NULL,
  current_index INT NOT NULL DEFAULT 0,
  correct_count INT NOT NULL DEFAULT 0,
  passed INT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  completed_at BIGINT,
  UNIQUE KEY uq_placement_opportunity(family_id, child_id, curriculum_version, lesson_id),
  CONSTRAINT chk_placement_state CHECK (
    status IN ('in_progress', 'completed', 'invalidated') AND total_questions >= 5
    AND current_index BETWEEN 0 AND total_questions
    AND correct_count BETWEEN 0 AND current_index AND grade_revision >= 1
    AND ((status='in_progress' AND current_index<total_questions AND passed IS NULL AND completed_at IS NULL)
      OR (status='completed' AND current_index=total_questions AND passed IS NOT NULL AND passed IN (0,1) AND completed_at IS NOT NULL)
      OR (status='invalidated' AND passed IS NULL AND completed_at IS NOT NULL))
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS learning_placement_questions (
  attempt_id VARCHAR(80) NOT NULL,
  ordinal INT NOT NULL,
  question_id VARCHAR(80) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  source_question_id VARCHAR(128) NOT NULL,
  assessment_set_id VARCHAR(128) NOT NULL,
  question_fingerprint CHAR(64) NOT NULL,
  source_content_sha256 CHAR(64) NOT NULL,
  authority_sha256 CHAR(64) NOT NULL,
  snapshot_sha256 CHAR(64) NOT NULL,
  snapshot_json JSON NOT NULL,
  response_sha256 CHAR(64),
  correct INT,
  answered_at BIGINT,
  PRIMARY KEY(attempt_id, ordinal),
  UNIQUE KEY uq_placement_question(question_id),
  UNIQUE KEY uq_placement_fingerprint(attempt_id, question_fingerprint),
  INDEX idx_placement_exposure(question_fingerprint),
  CONSTRAINT fk_placement_attempt FOREIGN KEY(attempt_id) REFERENCES learning_placement_attempts(id),
  CONSTRAINT chk_placement_question CHECK (
    ordinal >= 0
    AND ((response_sha256 IS NULL AND correct IS NULL AND answered_at IS NULL)
      OR (response_sha256 IS NOT NULL AND response_sha256 REGEXP '^[0-9a-f]{64}$' AND correct IS NOT NULL AND correct IN (0,1) AND answered_at IS NOT NULL))
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
