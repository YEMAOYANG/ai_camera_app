-- An attempt-three deterministic recovery is a separate, auditable control
-- record.  It never creates an attempt four and never rewrites the failed
-- OpenMAIC generation job.  Source runtime/job facts are copied into this row
-- before the recovery materializer can be called and are never overwritten.
CREATE TABLE IF NOT EXISTS learning_openmaic_deterministic_recoveries (
  id VARCHAR(128) PRIMARY KEY,
  recovery_request_id VARCHAR(128) NOT NULL,
  runtime_classroom_id VARCHAR(128) NOT NULL,
  mode VARCHAR(64) NOT NULL,
  kind VARCHAR(96) NOT NULL,
  status VARCHAR(32) NOT NULL,

  source_runtime_status VARCHAR(32) NOT NULL,
  source_runtime_error_code VARCHAR(128) NOT NULL,
  source_runtime_error_message_safe VARCHAR(512),
  source_upstream_job_id VARCHAR(128) NOT NULL,
  source_job_status VARCHAR(32) NOT NULL,
  source_job_error VARCHAR(128) NOT NULL,
  source_scenes_generated INTEGER NOT NULL,
  source_total_scenes INTEGER NOT NULL,
  source_completed_at VARCHAR(64) NOT NULL,
  -- Computed from the authenticated source-job GET and frozen before the
  -- recovery POST.  The 0007 response must echo the same canonical hash.
  source_job_snapshot_sha256 CHAR(64) NOT NULL,
  source_generation_contract_sha256 CHAR(64) NOT NULL,

  expected_upstream_recovery_id VARCHAR(128) NOT NULL,
  upstream_recovery_id VARCHAR(128),
  policy_id VARCHAR(128),
  policy_version VARCHAR(128),
  canonical_spec_sha256 CHAR(64),
  code_patch_sha256 CHAR(64),

  llm_call_count INTEGER NOT NULL DEFAULT 0,
  web_search_call_count INTEGER NOT NULL DEFAULT 0,
  image_generation_call_count INTEGER NOT NULL DEFAULT 0,
  video_generation_call_count INTEGER NOT NULL DEFAULT 0,
  tts_expected_call_count INTEGER NOT NULL DEFAULT 10,
  tts_attempted_call_count INTEGER NOT NULL DEFAULT 0,
  tts_completed_call_count INTEGER NOT NULL DEFAULT 0,
  tts_provider_id VARCHAR(64) NOT NULL,
  tts_model_id VARCHAR(128) NOT NULL,
  tts_voice_id VARCHAR(128) NOT NULL,
  tts_fallback_used BOOLEAN NOT NULL DEFAULT FALSE,
  tts_verified_asset_count INTEGER,

  upstream_classroom_id VARCHAR(255),
  scene_count INTEGER,
  content_sha256 CHAR(64),
  final_artifact_sha256 CHAR(64),
  artifact_created_at VARCHAR(64),
  static_contract_verified BOOLEAN NOT NULL DEFAULT FALSE,
  conversation_probe_verified BOOLEAN NOT NULL DEFAULT FALSE,
  verified_at BIGINT,
  receipt_json LONGTEXT,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  terminal_at BIGINT,

  UNIQUE KEY uq_openmaic_recovery_request(recovery_request_id),
  UNIQUE KEY uq_openmaic_recovery_runtime(runtime_classroom_id),
  UNIQUE KEY uq_openmaic_recovery_upstream(upstream_recovery_id),
  UNIQUE KEY uq_openmaic_recovery_expected_upstream(expected_upstream_recovery_id),
  UNIQUE KEY uq_openmaic_recovery_classroom(upstream_classroom_id),
  INDEX idx_openmaic_recovery_status(status, updated_at),
  CONSTRAINT chk_openmaic_recovery_mode
    CHECK (mode = 'deterministic_no_llm'),
  CONSTRAINT chk_openmaic_recovery_kind
    CHECK (kind = 'mira_sample_deterministic_no_llm_v1'),
  CONSTRAINT chk_openmaic_recovery_status
    CHECK (status IN ('recovering', 'validating', 'succeeded', 'failed')),
  CONSTRAINT chk_openmaic_recovery_upstream_identity
    CHECK (
      LEFT(expected_upstream_recovery_id, 6) = 'omrec_'
      AND (
        upstream_recovery_id IS NULL
        OR upstream_recovery_id = expected_upstream_recovery_id
      )
    ),
  CONSTRAINT chk_openmaic_recovery_source
    CHECK (
      source_runtime_status = 'failed'
      AND source_runtime_error_code = 'openmaic_generation_failed'
      AND source_job_status = 'failed'
      AND source_job_error = 'structured_output_exhausted'
      AND source_total_scenes = 10
      AND source_scenes_generated = 4
    ),
  CONSTRAINT chk_openmaic_recovery_call_counts
    CHECK (
      llm_call_count = 0
      AND web_search_call_count = 0
      AND image_generation_call_count = 0
      AND video_generation_call_count = 0
      AND tts_expected_call_count = 10
      AND tts_attempted_call_count >= 0
      AND tts_attempted_call_count <= tts_expected_call_count
      AND tts_completed_call_count >= 0
      AND tts_completed_call_count <= tts_attempted_call_count
      AND tts_provider_id = 'qwen-tts'
      AND tts_model_id = 'qwen3-tts-flash'
      AND tts_voice_id = 'Serena'
      AND tts_fallback_used = FALSE
    ),
  CONSTRAINT chk_openmaic_recovery_success_complete
    CHECK (
      status <> 'succeeded'
      OR (
        upstream_recovery_id IS NOT NULL
        AND upstream_recovery_id = expected_upstream_recovery_id
        AND source_job_snapshot_sha256 IS NOT NULL
        AND policy_id IS NOT NULL
        AND policy_version IS NOT NULL
        AND canonical_spec_sha256 IS NOT NULL
        AND code_patch_sha256 IS NOT NULL
        AND upstream_classroom_id IS NOT NULL
        AND scene_count = 10
        AND content_sha256 IS NOT NULL
        AND final_artifact_sha256 IS NOT NULL
        AND tts_attempted_call_count = 10
        AND tts_completed_call_count = 10
        AND tts_verified_asset_count = 10
        AND static_contract_verified = TRUE
        AND conversation_probe_verified = TRUE
        AND verified_at IS NOT NULL
        AND receipt_json IS NOT NULL
        AND terminal_at IS NOT NULL
      )
    ),
  CONSTRAINT fk_openmaic_recovery_runtime
    FOREIGN KEY (runtime_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(id)
);

-- Probe credentials for a recovered artifact use a dedicated candidate kind
-- and bind to the recovery audit row. They cannot masquerade as the normal
-- generation-candidate path.
ALTER TABLE learning_openmaic_conversation_probes
  ADD COLUMN candidate_kind VARCHAR(32) NOT NULL DEFAULT 'release'
    AFTER upstream_classroom_id,
  ADD COLUMN deterministic_recovery_id VARCHAR(128)
    AFTER candidate_kind,
  ADD CONSTRAINT chk_openmaic_probe_candidate_kind
    CHECK (candidate_kind IN ('release', 'generation', 'recovery')),
  ADD CONSTRAINT chk_openmaic_probe_recovery_binding
    CHECK (
      (candidate_kind = 'recovery' AND deterministic_recovery_id IS NOT NULL)
      OR
      (candidate_kind IN ('release', 'generation') AND deterministic_recovery_id IS NULL)
    ),
  ADD CONSTRAINT fk_openmaic_probe_recovery
    FOREIGN KEY (deterministic_recovery_id)
      REFERENCES learning_openmaic_deterministic_recoveries(id);
