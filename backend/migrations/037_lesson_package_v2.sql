CREATE TABLE IF NOT EXISTS learning_classroom_generation_jobs (
  id VARCHAR(128) PRIMARY KEY,
  request_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  generator VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  source_artifact_id VARCHAR(128),
  package_id VARCHAR(128),
  package_version INTEGER,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  started_at BIGINT,
  completed_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_classroom_jobs_request(request_id),
  INDEX idx_learning_classroom_jobs_course(
    course_id(96), course_version, status, created_at
  )
);

CREATE TABLE IF NOT EXISTS learning_classroom_source_artifacts (
  id VARCHAR(128) PRIMARY KEY,
  job_id VARCHAR(128) NOT NULL,
  request_id VARCHAR(128) NOT NULL,
  source_format VARCHAR(128) NOT NULL,
  source_package_version VARCHAR(64),
  dsl_version VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  source_hash CHAR(64) NOT NULL,
  payload_json LONGTEXT NOT NULL,
  validation_report_json LONGTEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_classroom_source_job(job_id),
  INDEX idx_learning_classroom_source_hash(source_hash),
  CONSTRAINT fk_learning_classroom_source_job
    FOREIGN KEY (job_id) REFERENCES learning_classroom_generation_jobs(id)
);

CREATE TABLE IF NOT EXISTS learning_lesson_packages (
  id VARCHAR(128) NOT NULL,
  version INTEGER NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  schema_version VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  source_artifact_id VARCHAR(128) NOT NULL,
  compiler_version VARCHAR(128) NOT NULL,
  public_content_hash CHAR(64) NOT NULL,
  private_content_hash CHAR(64) NOT NULL,
  public_payload_json LONGTEXT NOT NULL,
  validation_report_json LONGTEXT NOT NULL,
  created_at BIGINT NOT NULL,
  published_at BIGINT,
  retired_at BIGINT,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (id, version),
  UNIQUE KEY uq_learning_lesson_package_public_hash(public_content_hash),
  INDEX idx_learning_lesson_packages_course(
    course_id(96), course_version, status, published_at
  ),
  CONSTRAINT fk_learning_lesson_package_source
    FOREIGN KEY (source_artifact_id)
      REFERENCES learning_classroom_source_artifacts(id)
);

CREATE TABLE IF NOT EXISTS learning_lesson_package_private (
  package_id VARCHAR(128) NOT NULL,
  package_version INTEGER NOT NULL,
  schema_version VARCHAR(128) NOT NULL,
  payload_json LONGTEXT NOT NULL,
  content_hash CHAR(64) NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (package_id, package_version),
  CONSTRAINT fk_learning_lesson_package_private
    FOREIGN KEY (package_id, package_version)
      REFERENCES learning_lesson_packages(id, version)
);

CREATE TABLE IF NOT EXISTS learning_course_lesson_package_bindings (
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  package_id VARCHAR(128) NOT NULL,
  package_version INTEGER NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (course_id, course_version),
  CONSTRAINT fk_learning_course_lesson_package_binding
    FOREIGN KEY (package_id, package_version)
      REFERENCES learning_lesson_packages(id, version)
);

CREATE TABLE IF NOT EXISTS learning_media_assets (
  id VARCHAR(128) PRIMARY KEY,
  kind VARCHAR(32) NOT NULL,
  storage_key VARCHAR(512),
  content_hash CHAR(64),
  mime_type VARCHAR(128),
  byte_size BIGINT,
  width INTEGER,
  height INTEGER,
  duration_ms BIGINT,
  scan_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  moderation_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  transcode_status VARCHAR(32) NOT NULL DEFAULT 'pending',
  status VARCHAR(32) NOT NULL DEFAULT 'pending',
  source_type VARCHAR(64),
  source_ref VARCHAR(512),
  metadata_json LONGTEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

CREATE TABLE IF NOT EXISTS learning_lesson_package_assets (
  package_id VARCHAR(128) NOT NULL,
  package_version INTEGER NOT NULL,
  asset_id VARCHAR(128) NOT NULL,
  scene_id VARCHAR(128) NOT NULL,
  usage_kind VARCHAR(64) NOT NULL,
  required_asset TINYINT NOT NULL DEFAULT 1,
  PRIMARY KEY (
    package_id, package_version, asset_id, scene_id, usage_kind
  ),
  CONSTRAINT fk_learning_lesson_package_asset_package
    FOREIGN KEY (package_id, package_version)
      REFERENCES learning_lesson_packages(id, version),
  CONSTRAINT fk_learning_lesson_package_asset_asset
    FOREIGN KEY (asset_id) REFERENCES learning_media_assets(id)
);

ALTER TABLE learning_sessions
  ADD COLUMN lesson_package_id VARCHAR(128),
  ADD COLUMN lesson_package_version INTEGER,
  ADD COLUMN lesson_package_content_hash CHAR(64),
  ADD COLUMN current_scene_index INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN current_action_index INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN cursor_revision INTEGER NOT NULL DEFAULT 0,
  ADD COLUMN runtime_state_json LONGTEXT,
  ADD COLUMN classroom_completed_at BIGINT;

CREATE INDEX idx_learning_sessions_package
  ON learning_sessions(lesson_package_id, lesson_package_version);

CREATE TABLE IF NOT EXISTS learning_session_runtime_records (
  id VARCHAR(128) PRIMARY KEY,
  session_id VARCHAR(255) NOT NULL,
  seq INTEGER NOT NULL,
  idempotency_key VARCHAR(128) NOT NULL,
  scene_id VARCHAR(128),
  action_id VARCHAR(128),
  record_type VARCHAR(64) NOT NULL,
  payload_json LONGTEXT NOT NULL,
  response_json LONGTEXT NOT NULL,
  created_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_runtime_record_seq(session_id, seq),
  UNIQUE KEY uq_learning_runtime_record_idempotency(
    session_id, idempotency_key
  ),
  INDEX idx_learning_runtime_records_session(session_id, created_at)
);
