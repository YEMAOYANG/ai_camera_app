-- Formal Provider-readiness evidence is separate from the legacy route/session
-- probe.  The legacy proof is retained with provider_call=0, and only the exact
-- five-call ledger below can produce the Provider receipt used by publication.

-- Composite authorities close cross-row binding gaps while staying within the
-- InnoDB index-width budget.  Each statement is restartable after partial DDL.
SET @add_059_item_binding_index = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_curriculum_classroom_item_receipts ADD UNIQUE INDEX uq_learning_classroom_receipt_provider_binding(build_item_id, release_id, runtime_classroom_id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_curriculum_classroom_item_receipts'
    AND INDEX_NAME = 'uq_learning_classroom_receipt_provider_binding'
);
PREPARE add_059_item_binding_index_stmt FROM @add_059_item_binding_index;
EXECUTE add_059_item_binding_index_stmt;
DEALLOCATE PREPARE add_059_item_binding_index_stmt;

SET @add_059_probe_binding_index = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_conversation_probes ADD UNIQUE INDEX uq_openmaic_probe_provider_binding(id, runtime_classroom_id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_conversation_probes'
    AND INDEX_NAME = 'uq_openmaic_probe_provider_binding'
);
PREPARE add_059_probe_binding_index_stmt FROM @add_059_probe_binding_index;
EXECUTE add_059_probe_binding_index_stmt;
DEALLOCATE PREPARE add_059_probe_binding_index_stmt;

SET @add_059_audio_job_binding_index = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_formal_qwen_audio_jobs ADD UNIQUE INDEX uq_formal_qwen_audio_job_provider_binding(build_item_id, runtime_classroom_id, terminal_receipt_hash, state)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_formal_qwen_audio_jobs'
    AND INDEX_NAME = 'uq_formal_qwen_audio_job_provider_binding'
);
PREPARE add_059_audio_job_binding_index_stmt FROM @add_059_audio_job_binding_index;
EXECUTE add_059_audio_job_binding_index_stmt;
DEALLOCATE PREPARE add_059_audio_job_binding_index_stmt;

SET @add_059_audio_segment_binding_index = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_formal_qwen_audio_segment_receipts ADD UNIQUE INDEX uq_formal_qwen_audio_segment_provider_binding(build_item_id, scene_order, tts_request_id, runtime_audio_sha256, machine_receipt_hash, state)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_formal_qwen_audio_segment_receipts'
    AND INDEX_NAME = 'uq_formal_qwen_audio_segment_provider_binding'
);
PREPARE add_059_audio_segment_binding_index_stmt FROM @add_059_audio_segment_binding_index;
EXECUTE add_059_audio_segment_binding_index_stmt;
DEALLOCATE PREPARE add_059_audio_segment_binding_index_stmt;

CREATE TABLE IF NOT EXISTS learning_openmaic_provider_readiness_jobs (
  id VARCHAR(128) PRIMARY KEY,
  request_id VARCHAR(128) NOT NULL,
  request_sha256 CHAR(64) NOT NULL,
  build_item_id VARCHAR(128) NOT NULL,
  release_id VARCHAR(128) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  target_fingerprint CHAR(64) NOT NULL,
  runtime_classroom_id VARCHAR(128) NOT NULL,
  runtime_request_id VARCHAR(128) NOT NULL,
  upstream_classroom_id VARCHAR(255) NOT NULL,
  classroom_content_sha256 CHAR(64) NOT NULL,
  audio_job_terminal_receipt_hash CHAR(64) NOT NULL,
  audio_job_state VARCHAR(32) NOT NULL DEFAULT 'auto_validated',
  validation_scene_order INTEGER NOT NULL,
  validation_tts_request_id VARCHAR(128) NOT NULL,
  validation_audio_sha256 CHAR(64) NOT NULL,
  validation_audio_machine_receipt_hash CHAR(64) NOT NULL,
  validation_segment_state VARCHAR(32) NOT NULL DEFAULT 'auto_validated',
  conversation_probe_id VARCHAR(128) NOT NULL,
  route_session_contract_version VARCHAR(128) NOT NULL,
  route_session_receipt_hash CHAR(64) NOT NULL,
  route_session_provider_call TINYINT NOT NULL DEFAULT 0,
  route_session_status VARCHAR(32) NOT NULL DEFAULT 'passed',
  route_session_completed_at BIGINT NOT NULL,
  provider_contract_version VARCHAR(128) NOT NULL,
  expected_provider_call_count INTEGER NOT NULL DEFAULT 5,
  provider_attempted_count INTEGER NOT NULL DEFAULT 0,
  provider_passed_count INTEGER NOT NULL DEFAULT 0,
  provider_receipt_hash CHAR(64),
  state VARCHAR(32) NOT NULL DEFAULT 'pending',
  claim_token VARCHAR(128),
  claim_deadline_at BIGINT,
  heartbeat_at BIGINT,
  safe_error_code VARCHAR(128),
  started_at BIGINT,
  terminal_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_openmaic_provider_readiness_request(request_id),
  UNIQUE KEY uq_openmaic_provider_readiness_item(build_item_id),
  UNIQUE KEY uq_openmaic_provider_readiness_runtime(runtime_classroom_id),
  INDEX idx_openmaic_provider_readiness_claim(state, claim_deadline_at, created_at),
  INDEX idx_openmaic_provider_readiness_release(release_id, grade_code, state),
  CONSTRAINT fk_openmaic_provider_readiness_item_binding
    FOREIGN KEY (build_item_id, release_id, runtime_classroom_id)
      REFERENCES learning_curriculum_classroom_item_receipts(
        build_item_id, release_id, runtime_classroom_id
      ),
  CONSTRAINT fk_openmaic_provider_readiness_runtime
    FOREIGN KEY (runtime_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(id),
  CONSTRAINT fk_openmaic_provider_readiness_probe_binding
    FOREIGN KEY (conversation_probe_id, runtime_classroom_id)
      REFERENCES learning_openmaic_conversation_probes(id, runtime_classroom_id),
  CONSTRAINT fk_openmaic_provider_readiness_audio_job
    FOREIGN KEY (
      build_item_id, runtime_classroom_id,
      audio_job_terminal_receipt_hash, audio_job_state
    ) REFERENCES learning_formal_qwen_audio_jobs(
      build_item_id, runtime_classroom_id, terminal_receipt_hash, state
    ),
  CONSTRAINT fk_openmaic_provider_readiness_audio_segment
    FOREIGN KEY (
      build_item_id, validation_scene_order, validation_tts_request_id,
      validation_audio_sha256, validation_audio_machine_receipt_hash,
      validation_segment_state
    ) REFERENCES learning_formal_qwen_audio_segment_receipts(
      build_item_id, scene_order, tts_request_id, runtime_audio_sha256,
      machine_receipt_hash, state
    ),
  CONSTRAINT chk_openmaic_provider_readiness_identity CHECK (
    request_sha256 REGEXP '^[0-9a-f]{64}$'
    AND grade_code <> ''
    AND target_fingerprint REGEXP '^[0-9a-f]{64}$'
    AND classroom_content_sha256 REGEXP '^[0-9a-f]{64}$'
    AND audio_job_terminal_receipt_hash REGEXP '^[0-9a-f]{64}$'
    AND audio_job_state = 'auto_validated'
    AND validation_scene_order BETWEEN 0 AND 9
    AND validation_audio_sha256 REGEXP '^[0-9a-f]{64}$'
    AND validation_audio_machine_receipt_hash REGEXP '^[0-9a-f]{64}$'
    AND validation_segment_state = 'auto_validated'
    AND route_session_contract_version = 'mira.openmaic.conversation-proof.v1'
    AND route_session_receipt_hash REGEXP '^[0-9a-f]{64}$'
    AND route_session_provider_call = 0
    AND route_session_status = 'passed'
    AND route_session_completed_at > 0
    AND provider_contract_version = 'mira.openmaic.formal-provider-readiness.v1'
  ),
  CONSTRAINT chk_openmaic_provider_readiness_counts CHECK (
    expected_provider_call_count = 5
    AND 0 <= provider_passed_count
    AND provider_passed_count <= provider_attempted_count
    AND provider_attempted_count <= expected_provider_call_count
  ),
  CONSTRAINT chk_openmaic_provider_readiness_state CHECK (
    state IN ('pending', 'processing', 'auto_validated', 'failed', 'ambiguous')
    AND created_at > 0 AND updated_at >= created_at
    AND (
      (state = 'pending' AND provider_attempted_count = 0
        AND provider_passed_count = 0 AND provider_receipt_hash IS NULL
        AND claim_token IS NULL AND claim_deadline_at IS NULL
        AND heartbeat_at IS NULL AND safe_error_code IS NULL
        AND started_at IS NULL AND terminal_at IS NULL)
      OR (state = 'processing' AND provider_receipt_hash IS NULL
        AND claim_token IS NOT NULL AND claim_token <> ''
        AND claim_deadline_at IS NOT NULL AND claim_deadline_at > 0
        AND heartbeat_at IS NOT NULL AND heartbeat_at > 0
        AND safe_error_code IS NULL AND started_at IS NOT NULL
        AND started_at > 0 AND terminal_at IS NULL)
      OR (state = 'auto_validated' AND provider_attempted_count = 5
        AND provider_passed_count = 5
        AND route_session_status = 'passed'
        AND route_session_provider_call = 0
        AND provider_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND claim_token IS NULL AND claim_deadline_at IS NULL
        AND safe_error_code IS NULL AND terminal_at IS NOT NULL
        AND terminal_at >= route_session_completed_at)
      OR (state IN ('failed', 'ambiguous')
        AND provider_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND claim_token IS NULL AND claim_deadline_at IS NULL
        AND safe_error_code IS NOT NULL AND safe_error_code <> ''
        AND terminal_at IS NOT NULL AND terminal_at > 0)
    )
  )
);

CREATE TABLE IF NOT EXISTS learning_openmaic_provider_readiness_call_receipts (
  readiness_id VARCHAR(128) NOT NULL,
  call_ordinal INTEGER NOT NULL,
  kind VARCHAR(32) NOT NULL,
  subject VARCHAR(16),
  provider_id VARCHAR(32) NOT NULL,
  model_id VARCHAR(64) NOT NULL,
  voice_id VARCHAR(64),
  language_code VARCHAR(16),
  fallback_used TINYINT NOT NULL DEFAULT 0,
  provider_call TINYINT NOT NULL DEFAULT 1,
  request_sha256 CHAR(64) NOT NULL,
  response_sha256 CHAR(64),
  state VARCHAR(32) NOT NULL DEFAULT 'attempted',
  attempted_at BIGINT NOT NULL,
  completed_at BIGINT,
  safe_error_code VARCHAR(128),
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (readiness_id, call_ordinal),
  UNIQUE KEY uq_openmaic_provider_readiness_call_kind(
    readiness_id, kind, subject
  ),
  INDEX idx_openmaic_provider_readiness_calls(
    readiness_id, state, call_ordinal
  ),
  CONSTRAINT fk_openmaic_provider_readiness_call_job
    FOREIGN KEY (readiness_id)
      REFERENCES learning_openmaic_provider_readiness_jobs(id),
  CONSTRAINT chk_openmaic_provider_readiness_call_identity CHECK (
    call_ordinal BETWEEN 1 AND 5
    AND fallback_used = 0
    AND provider_call = 1
    AND request_sha256 REGEXP '^[0-9a-f]{64}$'
    AND (
      (call_ordinal = 1 AND kind = 'kimi_text' AND subject IS NULL
        AND provider_id = 'kimi' AND model_id = 'kimi-k2.6'
        AND voice_id IS NULL AND language_code IS NULL)
      OR (call_ordinal = 2 AND kind = 'qwen_asr'
        AND subject IN ('chinese', 'math', 'english')
        AND provider_id = 'qwen-asr' AND model_id = 'qwen3-asr-flash'
        AND voice_id IS NULL
        AND ((subject IN ('chinese', 'math') AND language_code = 'zh-CN')
          OR (subject = 'english' AND language_code = 'en-US')))
      OR (call_ordinal = 3 AND kind = 'qwen_tts' AND subject = 'chinese'
        AND provider_id = 'qwen-tts' AND model_id = 'qwen3-tts-flash'
        AND voice_id = 'Serena' AND language_code = 'zh-CN')
      OR (call_ordinal = 4 AND kind = 'qwen_tts' AND subject = 'math'
        AND provider_id = 'qwen-tts' AND model_id = 'qwen3-tts-flash'
        AND voice_id = 'Ethan' AND language_code = 'zh-CN')
      OR (call_ordinal = 5 AND kind = 'qwen_tts' AND subject = 'english'
        AND provider_id = 'qwen-tts' AND model_id = 'qwen3-tts-flash'
        AND voice_id = 'Jennifer' AND language_code = 'en-US')
    )
  ),
  CONSTRAINT chk_openmaic_provider_readiness_call_state CHECK (
    state IN ('attempted', 'passed', 'failed', 'ambiguous')
    AND created_at > 0 AND updated_at >= created_at
    AND attempted_at >= created_at AND attempted_at <= updated_at
    AND (
      (state = 'attempted' AND completed_at IS NULL
        AND response_sha256 IS NULL AND safe_error_code IS NULL)
      OR (state = 'passed' AND completed_at IS NOT NULL
        AND completed_at >= attempted_at
        AND response_sha256 REGEXP '^[0-9a-f]{64}$'
        AND safe_error_code IS NULL)
      OR (state IN ('failed', 'ambiguous') AND completed_at IS NOT NULL
        AND completed_at >= attempted_at
        AND response_sha256 REGEXP '^[0-9a-f]{64}$'
        AND safe_error_code IS NOT NULL AND safe_error_code <> '')
    )
  )
);
