-- Versioned course-file locators only. No course, session or source bytes move.
CREATE TABLE IF NOT EXISTS course_storage_files (
  storage_id CHAR(64) NOT NULL,
  source_path_sha256 CHAR(64) NOT NULL,
  content_sha256 CHAR(64) NOT NULL,
  source_path TEXT NOT NULL,
  byte_size BIGINT NOT NULL,
  mime_type VARCHAR(128) NOT NULL,
  locator_json LONGTEXT NOT NULL,
  created_at BIGINT NOT NULL,
  PRIMARY KEY (storage_id, source_path_sha256, content_sha256),
  CONSTRAINT chk_course_storage_file_size CHECK (byte_size >= 0),
  CONSTRAINT chk_course_storage_locator CHECK (JSON_VALID(locator_json) AND OCTET_LENGTH(locator_json) <= 16384)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS course_storage_scopes (
  storage_id CHAR(64) NOT NULL,
  scope_key CHAR(64) NOT NULL,
  preview_key CHAR(64),
  content_key CHAR(64),
  classroom_id VARCHAR(255),
  course_id VARCHAR(255),
  course_version VARCHAR(255),
  scope_json LONGTEXT NOT NULL,
  bindings_json LONGTEXT NOT NULL,
  created_at BIGINT NOT NULL,
  PRIMARY KEY (storage_id, scope_key),
  INDEX idx_course_storage_preview (storage_id, preview_key),
  INDEX idx_course_storage_content (storage_id, content_key),
  INDEX idx_course_storage_classroom (storage_id, classroom_id),
  INDEX idx_course_storage_course (storage_id, course_id, course_version),
  CONSTRAINT chk_course_storage_scope CHECK (JSON_VALID(scope_json) AND JSON_VALID(bindings_json)
    AND OCTET_LENGTH(scope_json) + OCTET_LENGTH(bindings_json) <= 8388608)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;

CREATE TABLE IF NOT EXISTS course_storage_heads (
  storage_id CHAR(64) NOT NULL,
  source_path_sha256 CHAR(64) NOT NULL,
  content_sha256 CHAR(64) NOT NULL,
  scope_key CHAR(64) NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (storage_id, source_path_sha256),
  CONSTRAINT fk_course_storage_head_file FOREIGN KEY (storage_id, source_path_sha256, content_sha256)
    REFERENCES course_storage_files (storage_id, source_path_sha256, content_sha256),
  CONSTRAINT fk_course_storage_head_scope FOREIGN KEY (storage_id, scope_key)
    REFERENCES course_storage_scopes (storage_id, scope_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
