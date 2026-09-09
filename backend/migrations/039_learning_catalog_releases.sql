ALTER TABLE learning_courses
  ADD COLUMN curriculum_version VARCHAR(128) AFTER node_code,
  ADD COLUMN boundary_version VARCHAR(255) AFTER curriculum_version,
  ADD COLUMN quality_status VARCHAR(32) NOT NULL DEFAULT 'legacy_unreviewed' AFTER status,
  ADD COLUMN retired_at BIGINT AFTER published_at;

CREATE INDEX idx_learning_courses_catalog_candidate
  ON learning_courses(
    curriculum_version, grade_code, subject, node_code,
    boundary_version(96), quality_status, status, retired_at
  );

ALTER TABLE learning_course_generation_jobs
  ADD COLUMN curriculum_version VARCHAR(128) AFTER node_code,
  ADD COLUMN boundary_version VARCHAR(255) AFTER curriculum_version;

ALTER TABLE learning_course_generation_candidates
  ADD COLUMN curriculum_version VARCHAR(128) AFTER node_code,
  ADD COLUMN boundary_version VARCHAR(255) AFTER curriculum_version;

CREATE TABLE IF NOT EXISTS learning_skill_boundaries (
  grade_code VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  skill_id VARCHAR(128) NOT NULL,
  curriculum_version VARCHAR(128) NOT NULL,
  boundary_version VARCHAR(255) NOT NULL,
  title VARCHAR(255) NOT NULL,
  payload_json LONGTEXT NOT NULL,
  quality_status VARCHAR(32) NOT NULL,
  status VARCHAR(32) NOT NULL,
  retired_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (curriculum_version, boundary_version),
  INDEX idx_learning_skill_boundary_node(
    curriculum_version, grade_code, subject, skill_id
  ),
  INDEX idx_learning_skill_boundaries_current(
    grade_code, subject, skill_id, status, quality_status, retired_at
  )
);

CREATE TABLE IF NOT EXISTS learning_catalog_releases (
  id VARCHAR(128) PRIMARY KEY,
  curriculum_version VARCHAR(128) NOT NULL,
  title VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL,
  quality_status VARCHAR(32) NOT NULL,
  required_boundary_count INTEGER NOT NULL DEFAULT 0,
  ready_item_count INTEGER NOT NULL DEFAULT 0,
  activated_at BIGINT,
  retired_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  INDEX idx_learning_catalog_releases_active(
    curriculum_version, status, quality_status, activated_at
  )
);

CREATE TABLE IF NOT EXISTS learning_catalog_build_jobs (
  id VARCHAR(128) PRIMARY KEY,
  request_id VARCHAR(128) NOT NULL,
  release_id VARCHAR(128) NOT NULL,
  curriculum_version VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  target_spec_json LONGTEXT NOT NULL,
  total_item_count INTEGER NOT NULL DEFAULT 0,
  ready_item_count INTEGER NOT NULL DEFAULT 0,
  failed_item_count INTEGER NOT NULL DEFAULT 0,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  started_at BIGINT,
  completed_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_catalog_build_request(request_id),
  UNIQUE KEY uq_learning_catalog_build_release(release_id),
  INDEX idx_learning_catalog_build_status(status, updated_at),
  CONSTRAINT fk_learning_catalog_build_release
    FOREIGN KEY (release_id) REFERENCES learning_catalog_releases(id)
);

CREATE TABLE IF NOT EXISTS learning_catalog_build_items (
  id VARCHAR(128) PRIMARY KEY,
  build_job_id VARCHAR(128) NOT NULL,
  release_id VARCHAR(128) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  skill_id VARCHAR(128) NOT NULL,
  curriculum_version VARCHAR(128) NOT NULL,
  boundary_version VARCHAR(255) NOT NULL,
  variant_ordinal INTEGER NOT NULL DEFAULT 1,
  status VARCHAR(32) NOT NULL,
  attempt_count INTEGER NOT NULL DEFAULT 0,
  generation_request_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255),
  course_version VARCHAR(64),
  package_id VARCHAR(128),
  package_version INTEGER,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  started_at BIGINT,
  completed_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_catalog_build_target(
    build_job_id, grade_code, subject, skill_id, variant_ordinal
  ),
  INDEX idx_learning_catalog_build_items_next(
    build_job_id, status, grade_code, subject, skill_id, variant_ordinal
  ),
  CONSTRAINT fk_learning_catalog_build_item_job
    FOREIGN KEY (build_job_id) REFERENCES learning_catalog_build_jobs(id),
  CONSTRAINT fk_learning_catalog_build_item_release
    FOREIGN KEY (release_id) REFERENCES learning_catalog_releases(id)
);

CREATE TABLE IF NOT EXISTS learning_catalog_release_items (
  release_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  skill_id VARCHAR(128) NOT NULL,
  curriculum_version VARCHAR(128) NOT NULL,
  boundary_version VARCHAR(255) NOT NULL,
  variant_ordinal INTEGER NOT NULL DEFAULT 1,
  package_id VARCHAR(128) NOT NULL,
  package_version INTEGER NOT NULL,
  status VARCHAR(32) NOT NULL,
  quality_status VARCHAR(32) NOT NULL,
  published_at BIGINT,
  retired_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (release_id, course_id, course_version),
  UNIQUE KEY uq_learning_catalog_release_boundary_variant(
    release_id, boundary_version(160), variant_ordinal
  ),
  INDEX idx_learning_catalog_release_recommendation(
    release_id, grade_code, subject, skill_id, status, quality_status
  ),
  CONSTRAINT fk_learning_catalog_release_item_release
    FOREIGN KEY (release_id) REFERENCES learning_catalog_releases(id),
  CONSTRAINT fk_learning_catalog_release_item_course
    FOREIGN KEY (course_id, course_version)
      REFERENCES learning_courses(id, version),
  CONSTRAINT fk_learning_catalog_release_item_package
    FOREIGN KEY (package_id, package_version)
      REFERENCES learning_lesson_packages(id, version)
);

-- Historical tasks and sessions intentionally keep their course references.
-- The old pinyin_syllables rows predate the narrowed a/o/e boundary and are
-- retired in place so they can never be selected for a new assignment.
UPDATE learning_courses
SET status = 'retired',
  quality_status = 'retired_boundary_mismatch',
  retired_at = COALESCE(
    retired_at,
    CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED)
  ),
  updated_at = CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED)
WHERE content_origin = 'openmaic_generated'
  AND grade_code = 'primary_1'
  AND subject = 'chinese'
  AND node_code = 'pinyin_syllables'
  AND (boundary_version IS NULL OR boundary_version = '');
