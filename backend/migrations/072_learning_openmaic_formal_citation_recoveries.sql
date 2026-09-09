-- A citation recovery is an auditable continuation of the exact second
-- formal Runtime attempt. It cannot allocate another Runtime/provider attempt
-- and freezes the failed OpenMAIC source snapshot before that same job is
-- deliberately promoted to the recovered classroom result.
CREATE TABLE IF NOT EXISTS learning_openmaic_formal_citation_recoveries (
  id VARCHAR(128) PRIMARY KEY,
  recovery_request_id VARCHAR(128) NOT NULL,
  runtime_classroom_id VARCHAR(128) NOT NULL,
  build_item_id VARCHAR(128) NOT NULL,
  status VARCHAR(32) NOT NULL,
  recovery_policy_version VARCHAR(128) NOT NULL,

  source_runtime_status VARCHAR(32) NOT NULL,
  source_quality_status VARCHAR(32) NOT NULL,
  source_runtime_error_code VARCHAR(128) NOT NULL,
  source_runtime_error_message_safe VARCHAR(512),
  source_attempt_ordinal INTEGER NOT NULL,
  source_provider_attempt_ordinal INTEGER NOT NULL,
  source_runtime_request_id VARCHAR(128) NOT NULL,
  source_upstream_job_id VARCHAR(128) NOT NULL,
  source_formal_input_sha256 CHAR(64) NOT NULL,
  source_job_status VARCHAR(32) NOT NULL,
  source_job_error VARCHAR(128) NOT NULL,
  source_job_completed_at VARCHAR(64),
  source_job_snapshot_sha256 CHAR(64),

  upstream_recovery_id VARCHAR(128),
  response_schema_version VARCHAR(128),
  response_kind VARCHAR(64),
  llm_call_count INTEGER,
  web_search_call_count INTEGER,
  fetch_url_call_count INTEGER,
  image_generation_call_count INTEGER,
  video_generation_call_count INTEGER,

  repair_policy_version VARCHAR(128),
  repair_before_scenes_sha256 CHAR(64),
  repair_after_scenes_sha256 CHAR(64),
  repair_sha256 CHAR(64),
  repair_json LONGTEXT,

  upstream_classroom_id VARCHAR(255),
  result_scene_count INTEGER,
  result_speech_action_count INTEGER,
  formal_audio_receipt_sha256 CHAR(64),
  professional_creation_receipt_sha256 CHAR(64),
  research_receipt_sha256 CHAR(64),
  result_json LONGTEXT,
  response_receipt_json LONGTEXT,
  response_receipt_sha256 CHAR(64),
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  terminal_at BIGINT,

  UNIQUE KEY uq_openmaic_formal_citation_request(recovery_request_id),
  UNIQUE KEY uq_openmaic_formal_citation_runtime(runtime_classroom_id),
  UNIQUE KEY uq_openmaic_formal_citation_item(build_item_id),
  UNIQUE KEY uq_openmaic_formal_citation_upstream(upstream_recovery_id),
  UNIQUE KEY uq_openmaic_formal_citation_classroom(upstream_classroom_id),
  INDEX idx_openmaic_formal_citation_status(status, updated_at),
  CONSTRAINT chk_openmaic_formal_citation_status
    CHECK (
      status IN ('reserving', 'running', 'succeeded', 'failed')
      AND recovery_policy_version = 'mira-formal-citation-recovery.v1'
    ),
  CONSTRAINT chk_openmaic_formal_citation_source
    CHECK (
      source_runtime_status = 'failed'
      AND source_quality_status = 'rejected'
      AND source_runtime_error_code = 'openmaic_formal_generation_failed'
      AND source_attempt_ordinal = 2
      AND source_provider_attempt_ordinal = 2
      AND source_job_status = 'failed'
      AND source_job_error =
        'FORMAL_PROFESSIONAL_RESEARCH_CITATION_MISSING'
      AND source_formal_input_sha256 REGEXP '^[0-9a-f]{64}$'
    ),
  CONSTRAINT chk_openmaic_formal_citation_zero_calls
    CHECK (
      (status = 'reserving'
        AND llm_call_count IS NULL
        AND web_search_call_count IS NULL
        AND fetch_url_call_count IS NULL
        AND image_generation_call_count IS NULL
        AND video_generation_call_count IS NULL)
      OR
      (status <> 'reserving'
        AND llm_call_count = 0
        AND web_search_call_count = 0
        AND fetch_url_call_count = 0
        AND image_generation_call_count = 0
        AND video_generation_call_count = 0)
    ),
  CONSTRAINT chk_openmaic_formal_citation_terminal
    CHECK (
      (status IN ('reserving', 'running') AND terminal_at IS NULL)
      OR (status IN ('succeeded', 'failed') AND terminal_at IS NOT NULL)
    ),
  CONSTRAINT chk_openmaic_formal_citation_success
    CHECK (
      status <> 'succeeded'
      OR (
        upstream_recovery_id IS NOT NULL
        AND response_schema_version =
          'mira.openmaic.formal-citation-recovery.v1'
        AND response_kind = 'formal_citation_recovery'
        AND source_job_completed_at IS NOT NULL
        AND source_job_snapshot_sha256 IS NOT NULL
        AND repair_policy_version =
          'mira-formal-citation-footer-canonicalize.v1'
        AND repair_before_scenes_sha256 IS NOT NULL
        AND repair_after_scenes_sha256 IS NOT NULL
        AND repair_sha256 IS NOT NULL
        AND repair_json IS NOT NULL
        AND upstream_classroom_id IS NOT NULL
        AND result_scene_count BETWEEN 1 AND 60
        AND result_speech_action_count >= result_scene_count
        AND result_speech_action_count <= 240
        AND formal_audio_receipt_sha256 IS NOT NULL
        AND professional_creation_receipt_sha256 IS NOT NULL
        AND research_receipt_sha256 IS NOT NULL
        AND result_json IS NOT NULL
        AND response_receipt_json IS NOT NULL
        AND response_receipt_sha256 IS NOT NULL
        AND error_code IS NULL
        AND error_message_safe IS NULL
      )
    ),
  CONSTRAINT fk_openmaic_formal_citation_runtime
    FOREIGN KEY (runtime_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(id),
  CONSTRAINT fk_openmaic_formal_citation_item
    FOREIGN KEY (build_item_id) REFERENCES learning_catalog_build_items(id)
);
