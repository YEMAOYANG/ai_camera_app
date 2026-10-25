-- Additive, opt-in homework analysis. Apply only through the reviewed migration flow.
CREATE TABLE IF NOT EXISTS homework_submissions (
 id VARCHAR(80) PRIMARY KEY, family_id VARCHAR(255) NOT NULL, child_id VARCHAR(255) NOT NULL,
 grade_code VARCHAR(32) NOT NULL, subject VARCHAR(32) NOT NULL, title VARCHAR(160) NOT NULL,
 source VARCHAR(32) NOT NULL, idempotency_key VARCHAR(128) NOT NULL, request_sha256 CHAR(64) NOT NULL,
 revision INT NOT NULL, status VARCHAR(32) NOT NULL, consent_at BIGINT NOT NULL,
 error_code VARCHAR(80), created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL, deleted_at BIGINT,
 UNIQUE KEY uq_homework_create (family_id, child_id, idempotency_key),
 INDEX idx_homework_child (family_id, child_id, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS homework_pages (
 id VARCHAR(80) PRIMARY KEY, submission_id VARCHAR(80) NOT NULL, upload_key VARCHAR(128) NOT NULL,
 content_sha256 CHAR(64) NOT NULL, storage_key VARCHAR(255) NOT NULL, mime_type VARCHAR(40) NOT NULL,
 width INT NOT NULL, height INT NOT NULL, page_order INT NOT NULL, rotation INT NOT NULL,
 crop_json JSON, status VARCHAR(32) NOT NULL, error_code VARCHAR(80), created_at BIGINT NOT NULL,
 UNIQUE KEY uq_homework_page_upload (submission_id, upload_key),
 INDEX idx_homework_pages (submission_id, page_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS homework_items (
 id VARCHAR(80) PRIMARY KEY, submission_id VARCHAR(80) NOT NULL, page_id VARCHAR(80) NOT NULL,
 revision INT NOT NULL, analysis_revision INT NOT NULL, item_order INT NOT NULL,
 result_json JSON NOT NULL, media_json JSON NOT NULL, correction_json JSON NOT NULL,
 updated_at BIGINT NOT NULL,
 INDEX idx_homework_items (submission_id, page_id, item_order)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS homework_item_revisions (
 item_id VARCHAR(80) NOT NULL, revision INT NOT NULL, submission_id VARCHAR(80) NOT NULL,
 result_json JSON NOT NULL, reason VARCHAR(40) NOT NULL, created_at BIGINT NOT NULL,
 PRIMARY KEY (item_id, revision), INDEX idx_homework_revision_submission (submission_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS homework_jobs (
 id VARCHAR(80) PRIMARY KEY, submission_id VARCHAR(80) NOT NULL, revision INT NOT NULL,
 status VARCHAR(32) NOT NULL, lease_token VARCHAR(80), lease_until BIGINT,
 stage VARCHAR(32) NOT NULL, error_code VARCHAR(80), created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
 UNIQUE KEY uq_homework_job (submission_id, revision), INDEX idx_homework_jobs (status, created_at)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS homework_provider_calls (
 id VARCHAR(80) PRIMARY KEY, submission_id VARCHAR(80) NOT NULL, page_id VARCHAR(80) NOT NULL,
 child_id VARCHAR(255) NOT NULL, request_sha256 CHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
 provider VARCHAR(80) NOT NULL, model VARCHAR(160) NOT NULL, prompt_version VARCHAR(40) NOT NULL,
 result_json JSON, receipt_json JSON, error_code VARCHAR(80), dispatched_at BIGINT,
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
 UNIQUE KEY uq_homework_call (submission_id, page_id, request_sha256),
 INDEX idx_homework_call_cache (child_id, request_sha256, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS homework_actions (
 id VARCHAR(80) PRIMARY KEY, submission_id VARCHAR(80) NOT NULL, item_id VARCHAR(80) NOT NULL,
 idempotency_key VARCHAR(128) NOT NULL, request_sha256 CHAR(64) NOT NULL,
 result_json JSON NOT NULL, created_at BIGINT NOT NULL,
 UNIQUE KEY uq_homework_action (submission_id, item_id, idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS homework_file_deletions (
 storage_key VARCHAR(255) PRIMARY KEY, created_at BIGINT NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS homework_audio_receipts (
 id VARCHAR(80) PRIMARY KEY, submission_id VARCHAR(80) NOT NULL, item_id VARCHAR(80) NOT NULL,
 revision INT NOT NULL, request_sha256 CHAR(64) NOT NULL, status VARCHAR(32) NOT NULL,
 character_count INT NOT NULL, result_json JSON, error_code VARCHAR(80),
 created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
 INDEX idx_homework_audio_submission (submission_id, status)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS homework_capture_authorizations (
 child_id VARCHAR(255) NOT NULL, task_id VARCHAR(255) NOT NULL, family_id VARCHAR(255) NOT NULL,
 device_id VARCHAR(255) NOT NULL, revision INT NOT NULL, enabled TINYINT NOT NULL,
 expires_at BIGINT NOT NULL, granted_by VARCHAR(255) NOT NULL, updated_at BIGINT NOT NULL,
 PRIMARY KEY (child_id, task_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
CREATE TABLE IF NOT EXISTS homework_capture_requests (
 id VARCHAR(80) PRIMARY KEY, family_id VARCHAR(255) NOT NULL, child_id VARCHAR(255) NOT NULL,
 task_id VARCHAR(255) NOT NULL, device_id VARCHAR(255) NOT NULL, idempotency_key VARCHAR(128) NOT NULL,
 authorization_revision INT NOT NULL, status VARCHAR(32) NOT NULL, submission_id VARCHAR(80),
 receipt_json JSON, error_code VARCHAR(80), created_at BIGINT NOT NULL, updated_at BIGINT NOT NULL,
 UNIQUE KEY uq_homework_capture (family_id, child_id, idempotency_key)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_bin;
