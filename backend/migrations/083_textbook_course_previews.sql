-- Private authoring previews never satisfy formal course publication checks.
CREATE TABLE IF NOT EXISTS learning_textbook_course_previews (
  preview_key CHAR(64) PRIMARY KEY,
  edition_id VARCHAR(80) NOT NULL,
  revision_id VARCHAR(80) NOT NULL,
  node_id VARCHAR(80) NOT NULL,
  input_json JSON NOT NULL,
  runtime_origin VARCHAR(255) NOT NULL,
  status VARCHAR(32) NOT NULL,
  runtime_job_id VARCHAR(128),
  classroom_id VARCHAR(255),
  classroom_sha256 CHAR(64),
  classroom_json JSON,
  result_json JSON,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_textbook_preview_runtime_job (runtime_origin, runtime_job_id),
  CONSTRAINT fk_textbook_preview_revision FOREIGN KEY (edition_id, revision_id)
    REFERENCES learning_textbook_revisions (edition_id, revision_id),
  CONSTRAINT chk_textbook_preview_status CHECK (
    status IN ('queued', 'dispatching', 'generating', 'preview_ready', 'review_required', 'failed', 'dispatch_unknown')
    AND (status <> 'preview_ready' OR (runtime_job_id IS NOT NULL
      AND classroom_id IS NOT NULL AND classroom_sha256 IS NOT NULL AND classroom_json IS NOT NULL))
  )
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
