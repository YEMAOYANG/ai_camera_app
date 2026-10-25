-- A credential child is the sole append-only continuation of the already
-- terminal deterministic recovery. It never changes the parent recovery and
-- never creates a fourth generation attempt.
CREATE TABLE IF NOT EXISTS learning_openmaic_tts_credential_recoveries (
  id VARCHAR(128) PRIMARY KEY,
  recovery_request_id VARCHAR(128) NOT NULL,
  runtime_classroom_id VARCHAR(128) NOT NULL,
  parent_recovery_id VARCHAR(128) NOT NULL,
  mode VARCHAR(64) NOT NULL,
  kind VARCHAR(96) NOT NULL,
  status VARCHAR(32) NOT NULL,

  parent_status VARCHAR(32) NOT NULL,
  parent_dispatch_count INTEGER NOT NULL,
  parent_error_code VARCHAR(128) NOT NULL,
  parent_error_message_safe VARCHAR(512) NOT NULL,
  parent_terminal_at BIGINT NOT NULL,
  parent_expected_upstream_recovery_id VARCHAR(128) NOT NULL,
  parent_upstream_recovery_id VARCHAR(128) NOT NULL,
  parent_db_snapshot_sha256 CHAR(64) NOT NULL,
  parent_receipt_sha256 CHAR(64) NOT NULL,
  parent_runtime_snapshot_sha256 CHAR(64) NOT NULL,
  source_upstream_job_id VARCHAR(128) NOT NULL,
  source_job_snapshot_sha256 CHAR(64) NOT NULL,
  source_generation_contract_sha256 CHAR(64) NOT NULL,
  parent_policy_id VARCHAR(128) NOT NULL,
  parent_policy_version VARCHAR(128) NOT NULL,
  parent_canonical_spec_sha256 CHAR(64) NOT NULL,
  parent_code_patch_sha256 CHAR(64) NOT NULL,
  parent_tts_expected_call_count INTEGER NOT NULL,
  parent_tts_attempted_call_count INTEGER NOT NULL,
  parent_tts_completed_call_count INTEGER NOT NULL,

  expected_upstream_child_id VARCHAR(128) NOT NULL,
  upstream_child_id VARCHAR(128),
  expected_upstream_classroom_id VARCHAR(255) NOT NULL,
  upstream_classroom_id VARCHAR(255),
  policy_version VARCHAR(128),
  classroom_policy_version VARCHAR(128),
  canonical_spec_sha256 CHAR(64),
  parent_patch_sha256 CHAR(64),
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

  scene_count INTEGER,
  audio_count INTEGER,
  content_sha256 CHAR(64),
  final_artifact_sha256 CHAR(64),
  artifact_created_at VARCHAR(64),
  static_contract_verified BOOLEAN NOT NULL DEFAULT FALSE,
  conversation_probe_verified BOOLEAN NOT NULL DEFAULT FALSE,
  conversation_probe_id VARCHAR(128),
  verified_at BIGINT,
  receipt_json LONGTEXT,
  error_code VARCHAR(128),
  error_message_safe VARCHAR(512),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  terminal_at BIGINT,

  UNIQUE KEY uq_openmaic_tts_child_request(recovery_request_id),
  UNIQUE KEY uq_openmaic_tts_child_runtime(runtime_classroom_id),
  UNIQUE KEY uq_openmaic_tts_child_parent(parent_recovery_id),
  UNIQUE KEY uq_openmaic_tts_child_expected(expected_upstream_child_id),
  UNIQUE KEY uq_openmaic_tts_child_expected_classroom(
    expected_upstream_classroom_id
  ),
  UNIQUE KEY uq_openmaic_tts_child_upstream(upstream_child_id),
  UNIQUE KEY uq_openmaic_tts_child_classroom(upstream_classroom_id),
  UNIQUE KEY uq_openmaic_tts_child_probe(conversation_probe_id),
  INDEX idx_openmaic_tts_child_status(status, updated_at),
  CONSTRAINT chk_openmaic_tts_child_mode
    CHECK (mode = 'deterministic_no_llm_qwen_tts_only'),
  CONSTRAINT chk_openmaic_tts_child_kind
    CHECK (
      kind = 'mira_sample_deterministic_tts_credential_recovery_v1'
    ),
  CONSTRAINT chk_openmaic_tts_child_status
    CHECK (
      status IN (
        'recovering', 'validating', 'publishing', 'succeeded', 'failed'
      )
    ),
  CONSTRAINT chk_openmaic_tts_child_parent
    CHECK (
      parent_status = 'failed'
      AND parent_dispatch_count = 2
      AND parent_error_code = 'openmaic_deterministic_recovery_failed'
      AND parent_expected_upstream_recovery_id = parent_upstream_recovery_id
      AND parent_tts_expected_call_count = 10
      AND parent_tts_attempted_call_count = 1
      AND parent_tts_completed_call_count = 0
      AND source_upstream_job_id = 'uKQl3vMr4d'
      AND parent_upstream_recovery_id =
        'omrec_383729f8f7f637dc1cdc65d4'
    ),
  CONSTRAINT chk_openmaic_tts_child_identity
    CHECK (
      LEFT(expected_upstream_child_id, 6) = 'omtts_'
      AND LEFT(expected_upstream_classroom_id, 8) = 'omclass_'
      AND (
        upstream_child_id IS NULL
        OR upstream_child_id = expected_upstream_child_id
      )
      AND (
        upstream_classroom_id IS NULL
        OR upstream_classroom_id = expected_upstream_classroom_id
      )
    ),
  CONSTRAINT chk_openmaic_tts_child_calls
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
  CONSTRAINT chk_openmaic_tts_child_state_evidence
    CHECK (
      (
        status = 'recovering'
        AND error_code IS NULL
        AND error_message_safe IS NULL
        AND terminal_at IS NULL
        AND static_contract_verified = FALSE
        AND conversation_probe_verified = FALSE
        AND upstream_classroom_id IS NULL
        AND tts_verified_asset_count IS NULL
        AND scene_count IS NULL
        AND audio_count IS NULL
        AND content_sha256 IS NULL
        AND final_artifact_sha256 IS NULL
        AND artifact_created_at IS NULL
        AND conversation_probe_id IS NULL
        AND verified_at IS NULL
      )
      OR
      (
        status = 'validating'
        AND upstream_child_id IS NOT NULL
        AND upstream_child_id = expected_upstream_child_id
        AND policy_version IS NOT NULL
        AND classroom_policy_version IS NOT NULL
        AND canonical_spec_sha256 IS NOT NULL
        AND parent_patch_sha256 IS NOT NULL
        AND code_patch_sha256 IS NOT NULL
        AND tts_attempted_call_count = 10
        AND tts_completed_call_count = 10
        AND conversation_probe_verified = FALSE
        AND conversation_probe_id IS NULL
        AND verified_at IS NULL
        AND receipt_json IS NOT NULL
        AND error_code IS NULL
        AND error_message_safe IS NULL
        AND terminal_at IS NULL
        AND (
          (
            static_contract_verified = FALSE
            AND upstream_classroom_id IS NULL
            AND tts_verified_asset_count IS NULL
            AND scene_count IS NULL
            AND audio_count IS NULL
            AND content_sha256 IS NULL
            AND final_artifact_sha256 IS NULL
            AND artifact_created_at IS NULL
          )
          OR
          (
            static_contract_verified = TRUE
            AND upstream_classroom_id IS NOT NULL
            AND upstream_classroom_id = expected_upstream_classroom_id
            AND tts_verified_asset_count IS NOT NULL
            AND tts_verified_asset_count = 10
            AND scene_count IS NOT NULL
            AND scene_count = 10
            AND audio_count IS NOT NULL
            AND audio_count = 10
            AND content_sha256 IS NOT NULL
            AND final_artifact_sha256 IS NOT NULL
            AND artifact_created_at IS NOT NULL
          )
        )
      )
      OR
      (
        status = 'publishing'
        AND upstream_child_id IS NOT NULL
        AND upstream_child_id = expected_upstream_child_id
        AND upstream_classroom_id IS NOT NULL
        AND upstream_classroom_id = expected_upstream_classroom_id
        AND policy_version IS NOT NULL
        AND classroom_policy_version IS NOT NULL
        AND canonical_spec_sha256 IS NOT NULL
        AND parent_patch_sha256 IS NOT NULL
        AND code_patch_sha256 IS NOT NULL
        AND tts_attempted_call_count = 10
        AND tts_completed_call_count = 10
        AND tts_verified_asset_count IS NOT NULL
        AND tts_verified_asset_count = 10
        AND scene_count IS NOT NULL
        AND scene_count = 10
        AND audio_count IS NOT NULL
        AND audio_count = 10
        AND content_sha256 IS NOT NULL
        AND final_artifact_sha256 IS NOT NULL
        AND artifact_created_at IS NOT NULL
        AND static_contract_verified = TRUE
        AND conversation_probe_verified = FALSE
        AND conversation_probe_id IS NULL
        AND verified_at IS NULL
        AND receipt_json IS NOT NULL
        AND error_code IS NULL
        AND error_message_safe IS NULL
        AND terminal_at IS NULL
      )
      OR
      (
        status = 'succeeded'
        AND error_code IS NULL
        AND error_message_safe IS NULL
        AND terminal_at IS NOT NULL
      )
      OR
      (
        status = 'failed'
        AND error_code IS NOT NULL
        AND error_message_safe IS NOT NULL
        AND terminal_at IS NOT NULL
        AND conversation_probe_verified = FALSE
        AND conversation_probe_id IS NULL
        AND verified_at IS NULL
        AND (
          (
            static_contract_verified = FALSE
            AND upstream_classroom_id IS NULL
            AND tts_verified_asset_count IS NULL
            AND scene_count IS NULL
            AND audio_count IS NULL
            AND content_sha256 IS NULL
            AND final_artifact_sha256 IS NULL
            AND artifact_created_at IS NULL
          )
          OR
          (
            static_contract_verified = TRUE
            AND upstream_child_id IS NOT NULL
            AND upstream_child_id = expected_upstream_child_id
            AND upstream_classroom_id IS NOT NULL
            AND upstream_classroom_id = expected_upstream_classroom_id
            AND policy_version IS NOT NULL
            AND classroom_policy_version IS NOT NULL
            AND canonical_spec_sha256 IS NOT NULL
            AND parent_patch_sha256 IS NOT NULL
            AND code_patch_sha256 IS NOT NULL
            AND tts_attempted_call_count = 10
            AND tts_completed_call_count = 10
            AND tts_verified_asset_count IS NOT NULL
            AND tts_verified_asset_count = 10
            AND scene_count IS NOT NULL
            AND scene_count = 10
            AND audio_count IS NOT NULL
            AND audio_count = 10
            AND content_sha256 IS NOT NULL
            AND final_artifact_sha256 IS NOT NULL
            AND artifact_created_at IS NOT NULL
            AND receipt_json IS NOT NULL
          )
        )
      )
    ),
  CONSTRAINT chk_openmaic_tts_child_success
    CHECK (
      status <> 'succeeded'
      OR (
        upstream_child_id IS NOT NULL
        AND upstream_child_id = expected_upstream_child_id
        AND upstream_classroom_id IS NOT NULL
        AND upstream_classroom_id = expected_upstream_classroom_id
        AND policy_version IS NOT NULL
        AND classroom_policy_version IS NOT NULL
        AND canonical_spec_sha256 IS NOT NULL
        AND parent_patch_sha256 IS NOT NULL
        AND code_patch_sha256 IS NOT NULL
        AND tts_attempted_call_count = 10
        AND tts_completed_call_count = 10
        AND tts_verified_asset_count IS NOT NULL
        AND tts_verified_asset_count = 10
        AND scene_count IS NOT NULL
        AND scene_count = 10
        AND audio_count IS NOT NULL
        AND audio_count = 10
        AND content_sha256 IS NOT NULL
        AND final_artifact_sha256 IS NOT NULL
        AND artifact_created_at IS NOT NULL
        AND static_contract_verified = TRUE
        AND conversation_probe_verified = TRUE
        AND conversation_probe_id IS NOT NULL
        AND verified_at IS NOT NULL
        AND receipt_json IS NOT NULL
        AND error_code IS NULL
        AND terminal_at IS NOT NULL
      )
    ),
  CONSTRAINT fk_openmaic_tts_child_runtime
    FOREIGN KEY (runtime_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(id),
  CONSTRAINT fk_openmaic_tts_child_parent
    FOREIGN KEY (parent_recovery_id)
      REFERENCES learning_openmaic_deterministic_recoveries(id),
  CONSTRAINT fk_openmaic_tts_child_probe
    FOREIGN KEY (conversation_probe_id)
      REFERENCES learning_openmaic_conversation_probes(id)
);

-- The child candidate binds both the immutable parent recovery and its unique
-- child audit row. Existing release, generation and recovery bindings retain
-- their original meaning.
ALTER TABLE learning_openmaic_conversation_probes
  DROP CHECK chk_openmaic_probe_candidate_kind,
  DROP CHECK chk_openmaic_probe_recovery_binding,
  ADD COLUMN tts_credential_recovery_id VARCHAR(128)
    AFTER deterministic_recovery_id,
  ADD UNIQUE KEY uq_openmaic_probe_tts_credential_child(
    tts_credential_recovery_id
  ),
  ADD CONSTRAINT chk_openmaic_probe_candidate_kind
    CHECK (
      candidate_kind IN (
        'release', 'generation', 'recovery', 'tts_credential_recovery'
      )
    ),
  ADD CONSTRAINT chk_openmaic_probe_recovery_binding
    CHECK (
      (
        candidate_kind = 'tts_credential_recovery'
        AND deterministic_recovery_id IS NOT NULL
        AND tts_credential_recovery_id IS NOT NULL
      )
      OR
      (
        candidate_kind = 'recovery'
        AND deterministic_recovery_id IS NOT NULL
        AND tts_credential_recovery_id IS NULL
      )
      OR
      (
        candidate_kind IN ('release', 'generation')
        AND deterministic_recovery_id IS NULL
        AND tts_credential_recovery_id IS NULL
      )
    ),
  ADD CONSTRAINT fk_openmaic_probe_tts_credential_child
    FOREIGN KEY (tts_credential_recovery_id)
      REFERENCES learning_openmaic_tts_credential_recoveries(id);
