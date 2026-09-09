CREATE TABLE IF NOT EXISTS learning_teacher_profiles (
  id VARCHAR(128) NOT NULL,
  version INTEGER NOT NULL,
  display_name VARCHAR(128) NOT NULL,
  avatar_path VARCHAR(255) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  language_code VARCHAR(32) NOT NULL,
  teaching_style VARCHAR(64) NOT NULL,
  provider_id VARCHAR(64) NOT NULL,
  provider_model VARCHAR(128) NOT NULL,
  voice_mode VARCHAR(32) NOT NULL,
  voice_prompt TEXT NOT NULL,
  capabilities_json LONGTEXT NOT NULL,
  clone_allowed TINYINT NOT NULL DEFAULT 0,
  status VARCHAR(32) NOT NULL,
  content_hash CHAR(64) NOT NULL,
  published_at BIGINT,
  retired_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (id, version),
  UNIQUE KEY uq_learning_teacher_profile_hash(content_hash),
  INDEX idx_learning_teacher_profile_catalog(
    subject, language_code, status, version
  )
);

CREATE TABLE IF NOT EXISTS learning_student_teacher_preferences (
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  teacher_profile_id VARCHAR(128) NOT NULL,
  teacher_profile_version INTEGER NOT NULL,
  updated_by_user_id VARCHAR(255),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (family_id, child_id, subject),
  INDEX idx_learning_teacher_preferences_child(child_id, subject),
  CONSTRAINT fk_learning_teacher_preference_child
    FOREIGN KEY (child_id) REFERENCES children(id),
  CONSTRAINT fk_learning_teacher_preference_profile
    FOREIGN KEY (teacher_profile_id, teacher_profile_version)
      REFERENCES learning_teacher_profiles(id, version)
);

CREATE TABLE IF NOT EXISTS learning_media_generation_jobs (
  id VARCHAR(128) PRIMARY KEY,
  idempotency_key VARCHAR(128) NOT NULL,
  request_hash CHAR(64) NOT NULL,
  package_id VARCHAR(128),
  package_version INTEGER,
  course_id VARCHAR(255),
  course_version VARCHAR(64),
  subject VARCHAR(64) NOT NULL,
  language_code VARCHAR(32) NOT NULL,
  pronunciation_kind VARCHAR(32) NOT NULL,
  teacher_profile_id VARCHAR(128) NOT NULL,
  teacher_profile_version INTEGER NOT NULL,
  provider_id VARCHAR(64) NOT NULL,
  provider_model VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  segment_count INTEGER NOT NULL DEFAULT 0,
  asset_count INTEGER NOT NULL DEFAULT 0,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  started_at BIGINT,
  completed_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_media_job_idempotency(idempotency_key),
  INDEX idx_learning_media_jobs_queue(status, created_at, id),
  INDEX idx_learning_media_jobs_package(
    package_id, package_version, status, created_at
  ),
  INDEX idx_learning_media_jobs_course(
    course_id(96), course_version, status, created_at
  ),
  CONSTRAINT fk_learning_media_job_teacher
    FOREIGN KEY (teacher_profile_id, teacher_profile_version)
      REFERENCES learning_teacher_profiles(id, version)
);

CREATE TABLE IF NOT EXISTS learning_narration_segments (
  id VARCHAR(128) PRIMARY KEY,
  job_id VARCHAR(128) NOT NULL,
  segment_index INTEGER NOT NULL,
  scene_id VARCHAR(128),
  action_id VARCHAR(128),
  source_text TEXT NOT NULL,
  subtitle_text TEXT NOT NULL,
  text_hash CHAR(64) NOT NULL,
  language_code VARCHAR(32) NOT NULL,
  pronunciation_kind VARCHAR(32) NOT NULL,
  review_policy VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  asset_id VARCHAR(128),
  audio_checksum CHAR(64),
  duration_ms BIGINT,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_narration_job_index(job_id, segment_index),
  INDEX idx_learning_narration_job_status(job_id, status, segment_index),
  INDEX idx_learning_narration_asset(asset_id),
  CONSTRAINT fk_learning_narration_job
    FOREIGN KEY (job_id) REFERENCES learning_media_generation_jobs(id),
  CONSTRAINT fk_learning_narration_asset
    FOREIGN KEY (asset_id) REFERENCES learning_media_assets(id)
);

CREATE TABLE IF NOT EXISTS learning_media_asset_variants (
  asset_id VARCHAR(128) NOT NULL,
  variant_key VARCHAR(64) NOT NULL,
  storage_key VARCHAR(512) NOT NULL,
  content_hash CHAR(64) NOT NULL,
  mime_type VARCHAR(128) NOT NULL,
  byte_size BIGINT NOT NULL,
  duration_ms BIGINT,
  status VARCHAR(32) NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (asset_id, variant_key),
  UNIQUE KEY uq_learning_media_variant_storage(storage_key(191)),
  INDEX idx_learning_media_variant_hash(content_hash),
  INDEX idx_learning_media_variant_status(status, updated_at),
  CONSTRAINT fk_learning_media_variant_asset
    FOREIGN KEY (asset_id) REFERENCES learning_media_assets(id)
);

CREATE TABLE IF NOT EXISTS learning_media_quality_reviews (
  id VARCHAR(128) PRIMARY KEY,
  asset_id VARCHAR(128) NOT NULL,
  review_kind VARCHAR(64) NOT NULL,
  required_review TINYINT NOT NULL DEFAULT 1,
  status VARCHAR(32) NOT NULL,
  reviewer_type VARCHAR(32),
  reviewer_id VARCHAR(255),
  findings_json LONGTEXT NOT NULL,
  notes TEXT,
  reviewed_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_media_review_kind(asset_id, review_kind),
  INDEX idx_learning_media_review_queue(
    required_review, status, review_kind, created_at
  ),
  INDEX idx_learning_media_review_asset(asset_id, status),
  CONSTRAINT fk_learning_media_review_asset
    FOREIGN KEY (asset_id) REFERENCES learning_media_assets(id)
);
