CREATE TABLE IF NOT EXISTS learning_content_generation_jobs (
  id VARCHAR(128) PRIMARY KEY,
  request_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  generator VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  error_code VARCHAR(128),
  error_message VARCHAR(512),
  draft_id VARCHAR(128),
  started_at BIGINT NOT NULL,
  completed_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_content_jobs_request(request_id),
  INDEX idx_learning_content_jobs_course(
    course_id(96), course_version, status, created_at
  )
);

CREATE TABLE IF NOT EXISTS learning_content_enrichment_drafts (
  id VARCHAR(128) PRIMARY KEY,
  job_id VARCHAR(128) NOT NULL,
  request_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  schema_version VARCHAR(128) NOT NULL,
  generator VARCHAR(64) NOT NULL,
  provider VARCHAR(128) NOT NULL,
  model VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL,
  content_hash CHAR(64) NOT NULL,
  payload_json LONGTEXT NOT NULL,
  elapsed_ms INTEGER NOT NULL DEFAULT 0,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_content_drafts_job(job_id),
  UNIQUE KEY uq_learning_content_drafts_request(request_id),
  INDEX idx_learning_content_drafts_course(
    course_id(96), course_version, status, created_at
  ),
  CONSTRAINT fk_learning_content_drafts_job
    FOREIGN KEY (job_id) REFERENCES learning_content_generation_jobs(id)
);
