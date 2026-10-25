-- Stable authoring reservations. No family or child data belongs in this table.
-- Apply through the reviewed migration workflow, never from application startup.
CREATE TABLE IF NOT EXISTS learning_course_reuse_slots (
  identity_key CHAR(64) PRIMARY KEY,
  course_key CHAR(64) NOT NULL,
  edition_id VARCHAR(80) NOT NULL,
  node_id VARCHAR(80) NOT NULL,
  part_index INT NOT NULL,
  teaching_revision VARCHAR(80) NOT NULL,
  identity_json JSON NOT NULL,
  lesson_scope_sha256 CHAR(64) NOT NULL,
  preview_key CHAR(64),
  published_content_key CHAR(64),
  regeneration_json JSON,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_course_reuse_version (course_key, teaching_revision),
  UNIQUE KEY uq_course_reuse_preview (preview_key),
  CONSTRAINT fk_course_reuse_edition FOREIGN KEY (edition_id)
    REFERENCES learning_textbook_editions (edition_id),
  CONSTRAINT fk_course_reuse_preview FOREIGN KEY (preview_key)
    REFERENCES learning_textbook_course_previews (preview_key),
  CONSTRAINT fk_course_reuse_publication FOREIGN KEY (published_content_key)
    REFERENCES learning_textbook_course_builds (content_key),
  CONSTRAINT chk_course_reuse_part CHECK (part_index BETWEEN 1 AND 20),
  INDEX idx_course_reuse_lookup (course_key, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
