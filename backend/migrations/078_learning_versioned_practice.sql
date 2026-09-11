-- Practice projects only released Host-validated questions. Classroom contracts
-- and historical learning sessions remain untouched.
CREATE TABLE IF NOT EXISTS learning_practice_questions (
  id CHAR(64) PRIMARY KEY,
  source_key_sha256 CHAR(64) NOT NULL UNIQUE,
  grade_code VARCHAR(32) NOT NULL,
  subject VARCHAR(32) NOT NULL,
  skill_id VARCHAR(128) NOT NULL,
  release_id VARCHAR(255) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  source_question_id VARCHAR(128) NOT NULL,
  source_content_sha256 CHAR(64) NOT NULL,
  contract_sha256 CHAR(64) NOT NULL,
  dedupe_sha256 CHAR(64) NOT NULL,
  question_json JSON NOT NULL,
  created_at BIGINT NOT NULL,
  INDEX idx_practice_question_scope(grade_code, subject, skill_id),
  CONSTRAINT chk_practice_question_identity CHECK (
    id REGEXP '^[0-9a-f]{64}$' AND contract_sha256 REGEXP '^[0-9a-f]{64}$'
    AND source_content_sha256 REGEXP '^[0-9a-f]{64}$'
    AND dedupe_sha256 REGEXP '^[0-9a-f]{64}$'
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS learning_practice_sessions (
  id VARCHAR(80) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  grade_code VARCHAR(32) NOT NULL,
  grade_revision INT NOT NULL,
  subject VARCHAR(32) NOT NULL,
  skill_id VARCHAR(128),
  request_key_sha256 CHAR(64) NOT NULL UNIQUE,
  request_sha256 CHAR(64) NOT NULL,
  status VARCHAR(24) NOT NULL,
  total_questions INT NOT NULL,
  current_index INT NOT NULL DEFAULT 0,
  correct_count INT NOT NULL DEFAULT 0,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  completed_at BIGINT,
  INDEX idx_practice_student(child_id, subject, status),
  CONSTRAINT chk_practice_session_state CHECK (
    status IN ('in_progress', 'completed') AND total_questions BETWEEN 1 AND 5
    AND current_index BETWEEN 0 AND total_questions
    AND correct_count BETWEEN 0 AND current_index AND grade_revision >= 1
    AND ((status = 'in_progress' AND current_index < total_questions AND completed_at IS NULL)
      OR (status = 'completed' AND current_index = total_questions AND completed_at IS NOT NULL))
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS learning_practice_session_questions (
  session_id VARCHAR(80) NOT NULL,
  ordinal INT NOT NULL,
  question_id CHAR(64) NOT NULL,
  contract_sha256 CHAR(64) NOT NULL,
  snapshot_json JSON NOT NULL,
  response_sha256 CHAR(64),
  feedback_json JSON,
  answered_at BIGINT,
  PRIMARY KEY(session_id, ordinal),
  UNIQUE KEY uq_practice_session_question(session_id, question_id),
  CONSTRAINT fk_practice_session FOREIGN KEY(session_id) REFERENCES learning_practice_sessions(id),
  CONSTRAINT fk_practice_question FOREIGN KEY(question_id) REFERENCES learning_practice_questions(id),
  CONSTRAINT chk_practice_attempt CHECK (
    ordinal BETWEEN 0 AND 4 AND contract_sha256 REGEXP '^[0-9a-f]{64}$'
    AND ((response_sha256 IS NULL AND feedback_json IS NULL AND answered_at IS NULL)
      OR (response_sha256 REGEXP '^[0-9a-f]{64}$' AND feedback_json IS NOT NULL AND answered_at IS NOT NULL))
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE IF NOT EXISTS learning_practice_exposures (
  id CHAR(64) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  dedupe_sha256 CHAR(64) NOT NULL,
  session_id VARCHAR(80) NOT NULL,
  question_id CHAR(64) NOT NULL,
  created_at BIGINT NOT NULL,
  INDEX idx_practice_seen(child_id, dedupe_sha256),
  CONSTRAINT fk_practice_exposure_session FOREIGN KEY(session_id) REFERENCES learning_practice_sessions(id),
  CONSTRAINT fk_practice_exposure_question FOREIGN KEY(question_id) REFERENCES learning_practice_questions(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
