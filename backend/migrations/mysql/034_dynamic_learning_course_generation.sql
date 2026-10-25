ALTER TABLE learning_courses
  ADD COLUMN content_origin VARCHAR(64) NOT NULL DEFAULT 'legacy_seed' AFTER status,
  ADD COLUMN generator VARCHAR(64) AFTER content_origin,
  ADD COLUMN generation_request_id VARCHAR(128) AFTER generator,
  ADD COLUMN generation_content_hash CHAR(64) AFTER generation_request_id;

CREATE INDEX idx_learning_courses_dynamic_supply
  ON learning_courses(
    grade_code, subject, status, content_origin, node_code
  );

CREATE TABLE IF NOT EXISTS learning_course_generation_jobs (
  id VARCHAR(128) PRIMARY KEY,
  request_id VARCHAR(128) NOT NULL,
  request_fingerprint CHAR(64) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  node_code VARCHAR(128) NOT NULL,
  generator VARCHAR(64) NOT NULL,
  provider VARCHAR(128) NOT NULL,
  model VARCHAR(255) NOT NULL,
  prompt_version VARCHAR(128) NOT NULL,
  requested_candidate_count INTEGER NOT NULL DEFAULT 1,
  status VARCHAR(32) NOT NULL,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  started_at BIGINT,
  completed_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_course_generation_request(request_id),
  INDEX idx_learning_course_generation_target(
    grade_code, subject, node_code, status, created_at
  )
);

CREATE TABLE IF NOT EXISTS learning_course_generation_candidates (
  id VARCHAR(128) PRIMARY KEY,
  job_id VARCHAR(128) NOT NULL,
  ordinal INTEGER NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  node_code VARCHAR(128) NOT NULL,
  title VARCHAR(255) NOT NULL,
  objective TEXT NOT NULL,
  status VARCHAR(32) NOT NULL,
  content_hash CHAR(64) NOT NULL,
  content_json LONGTEXT NOT NULL,
  validation_json LONGTEXT,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  published_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_course_candidate_ordinal(job_id, ordinal),
  INDEX idx_learning_course_candidates_job(job_id, status, ordinal),
  INDEX idx_learning_course_candidates_target(
    course_id(96), course_version, status
  ),
  CONSTRAINT fk_learning_course_candidates_job
    FOREIGN KEY (job_id) REFERENCES learning_course_generation_jobs(id)
);
