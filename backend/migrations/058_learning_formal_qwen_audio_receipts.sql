-- Durable formal Qwen3 TTS/WAV/ASR evidence.  These rows are an audio
-- sidecar: the immutable Task-13 classroom JSON and content hash are never
-- rewritten by this migration or by its repository.

CREATE TABLE IF NOT EXISTS learning_formal_qwen_audio_jobs (
  build_item_id VARCHAR(128) PRIMARY KEY,
  release_id VARCHAR(128) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  target_fingerprint CHAR(64) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  package_id VARCHAR(128) NOT NULL,
  package_version INTEGER NOT NULL,
  runtime_classroom_id VARCHAR(128) NOT NULL,
  runtime_request_id VARCHAR(128) NOT NULL,
  upstream_classroom_id VARCHAR(255) NOT NULL,
  classroom_content_sha256 CHAR(64) NOT NULL,
  subject VARCHAR(16) NOT NULL,
  language_code VARCHAR(16) NOT NULL,
  teacher_profile_id VARCHAR(128) NOT NULL,
  teacher_profile_version INTEGER NOT NULL,
  teacher_profile_hash CHAR(64) NOT NULL,
  teacher_name VARCHAR(128) NOT NULL,
  teacher_gender VARCHAR(16) NOT NULL,
  voice_gender VARCHAR(16) NOT NULL,
  voice_contract_version VARCHAR(128) NOT NULL,
  tts_provider_id VARCHAR(32) NOT NULL,
  tts_model_id VARCHAR(64) NOT NULL,
  tts_voice_id VARCHAR(64) NOT NULL,
  tts_fallback_allowed TINYINT NOT NULL DEFAULT 0,
  asr_provider_id VARCHAR(32) NOT NULL,
  asr_model_id VARCHAR(64) NOT NULL,
  asr_fallback_allowed TINYINT NOT NULL DEFAULT 0,
  audio_contract_version VARCHAR(128) NOT NULL,
  pcm_validation_contract_version VARCHAR(128) NOT NULL,
  asr_roundtrip_contract_version VARCHAR(128) NOT NULL,
  speech_manifest_sha256 CHAR(64) NOT NULL,
  expected_segment_count INTEGER NOT NULL DEFAULT 10,
  legacy_media_job_id VARCHAR(128),
  state VARCHAR(32) NOT NULL DEFAULT 'pending',
  tts_attempted_count INTEGER NOT NULL DEFAULT 0,
  tts_completed_count INTEGER NOT NULL DEFAULT 0,
  audio_validated_count INTEGER NOT NULL DEFAULT 0,
  asr_attempted_count INTEGER NOT NULL DEFAULT 0,
  asr_passed_count INTEGER NOT NULL DEFAULT 0,
  claim_token VARCHAR(128),
  claim_deadline_at BIGINT,
  heartbeat_at BIGINT,
  safe_error_code VARCHAR(128),
  terminal_receipt_version VARCHAR(128),
  terminal_receipt_hash CHAR(64),
  started_at BIGINT,
  terminal_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_formal_qwen_audio_job_release_item(release_id, build_item_id),
  UNIQUE KEY uq_formal_qwen_audio_job_runtime(runtime_classroom_id),
  UNIQUE KEY uq_formal_qwen_audio_job_runtime_request(runtime_request_id),
  UNIQUE KEY uq_formal_qwen_audio_job_upstream(upstream_classroom_id),
  INDEX idx_formal_qwen_audio_jobs_claim(state, claim_deadline_at, created_at),
  INDEX idx_formal_qwen_audio_jobs_release(release_id, grade_code, state),
  CONSTRAINT fk_formal_qwen_audio_job_item
    FOREIGN KEY (build_item_id) REFERENCES learning_catalog_build_items(id),
  CONSTRAINT fk_formal_qwen_audio_job_item_receipt
    FOREIGN KEY (build_item_id)
      REFERENCES learning_curriculum_classroom_item_receipts(build_item_id),
  CONSTRAINT fk_formal_qwen_audio_job_release
    FOREIGN KEY (release_id) REFERENCES learning_catalog_releases(id),
  CONSTRAINT fk_formal_qwen_audio_job_runtime
    FOREIGN KEY (runtime_classroom_id)
      REFERENCES learning_openmaic_runtime_classrooms(id),
  CONSTRAINT fk_formal_qwen_audio_job_course
    FOREIGN KEY (course_id, course_version)
      REFERENCES learning_courses(id, version),
  CONSTRAINT fk_formal_qwen_audio_job_package
    FOREIGN KEY (package_id, package_version)
      REFERENCES learning_lesson_packages(id, version),
  CONSTRAINT fk_formal_qwen_audio_job_legacy_media
    FOREIGN KEY (legacy_media_job_id) REFERENCES learning_media_generation_jobs(id),
  CONSTRAINT chk_formal_qwen_audio_job_counts CHECK (
    expected_segment_count = 10
    AND 0 <= asr_passed_count
    AND asr_passed_count <= asr_attempted_count
    AND asr_attempted_count <= audio_validated_count
    AND audio_validated_count <= tts_completed_count
    AND tts_completed_count <= tts_attempted_count
    AND tts_attempted_count <= expected_segment_count
  ),
  CONSTRAINT chk_formal_qwen_audio_job_voice CHECK (
    voice_contract_version = 'mira.openmaic.formal-subject-qwen3-voice.v1'
    AND tts_provider_id = 'qwen-tts'
    AND tts_model_id = 'qwen3-tts-flash'
    AND tts_fallback_allowed = 0
    AND asr_provider_id = 'qwen-asr'
    AND asr_model_id = 'qwen3-asr-flash'
    AND asr_fallback_allowed = 0
    AND (
      (subject = 'chinese' AND language_code = 'zh-CN'
        AND teacher_profile_id = 'mira_chinese_gentle'
        AND teacher_profile_version = 2
        AND teacher_profile_hash = 'a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8'
        AND teacher_name = '小语老师' AND teacher_gender = 'female'
        AND voice_gender = 'female' AND tts_voice_id = 'Serena')
      OR (subject = 'math' AND language_code = 'zh-CN'
        AND teacher_profile_id = 'mira_math_clear'
        AND teacher_profile_version = 2
        AND teacher_profile_hash = '4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb'
        AND teacher_name = '小数老师' AND teacher_gender = 'male'
        AND voice_gender = 'male' AND tts_voice_id = 'Ethan')
      OR (subject = 'english' AND language_code = 'en-US'
        AND teacher_profile_id = 'mira_english_standard'
        AND teacher_profile_version = 2
        AND teacher_profile_hash = '4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040'
        AND teacher_name = 'Mia 老师' AND teacher_gender = 'female'
        AND voice_gender = 'female' AND tts_voice_id = 'Jennifer')
    )
  ),
  CONSTRAINT chk_formal_qwen_audio_job_identity CHECK (
    grade_code <> '' AND package_version > 0
    AND target_fingerprint REGEXP '^[0-9a-f]{64}$'
    AND classroom_content_sha256 REGEXP '^[0-9a-f]{64}$'
    AND teacher_profile_hash REGEXP '^[0-9a-f]{64}$'
    AND speech_manifest_sha256 REGEXP '^[0-9a-f]{64}$'
    AND audio_contract_version = 'mira.learning.formal-qwen-audio.v1'
    AND pcm_validation_contract_version = 'mira.learning.formal-pcm-validation.v1'
    AND asr_roundtrip_contract_version = 'mira.learning.formal-qwen-asr-roundtrip.v1'
  ),
  CONSTRAINT chk_formal_qwen_audio_job_terminal CHECK (
    state IN ('pending', 'processing', 'auto_validated', 'failed', 'ambiguous')
    AND created_at > 0 AND updated_at >= created_at
    AND (
      (state = 'pending' AND claim_token IS NULL AND claim_deadline_at IS NULL
        AND heartbeat_at IS NULL AND safe_error_code IS NULL
        AND terminal_receipt_version IS NULL AND terminal_receipt_hash IS NULL
        AND started_at IS NULL AND terminal_at IS NULL)
      OR (state = 'processing' AND claim_token IS NOT NULL AND claim_token <> ''
        AND claim_deadline_at IS NOT NULL AND claim_deadline_at > 0
        AND heartbeat_at IS NOT NULL AND heartbeat_at > 0
        AND safe_error_code IS NULL AND terminal_receipt_version IS NULL
        AND terminal_receipt_hash IS NULL AND started_at IS NOT NULL
        AND started_at > 0 AND terminal_at IS NULL)
      OR (state = 'auto_validated' AND tts_attempted_count = 10
        AND tts_completed_count = 10 AND audio_validated_count = 10
        AND asr_attempted_count = 10 AND asr_passed_count = 10
        AND claim_token IS NULL AND claim_deadline_at IS NULL
        AND safe_error_code IS NULL AND terminal_receipt_version IS NOT NULL
        AND terminal_receipt_version <> ''
        AND terminal_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND terminal_at IS NOT NULL AND terminal_at > 0)
      OR (state IN ('failed', 'ambiguous') AND claim_token IS NULL
        AND claim_deadline_at IS NULL AND safe_error_code IS NOT NULL
        AND safe_error_code <> '' AND terminal_receipt_version IS NOT NULL
        AND terminal_receipt_version <> ''
        AND terminal_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND terminal_at IS NOT NULL AND terminal_at > 0)
    )
  )
);

CREATE TABLE IF NOT EXISTS learning_formal_qwen_audio_segment_receipts (
  build_item_id VARCHAR(128) NOT NULL,
  scene_order INTEGER NOT NULL,
  scene_id VARCHAR(128) NOT NULL,
  action_id VARCHAR(128) NOT NULL,
  narration_segment_id VARCHAR(128) NOT NULL,
  source_text_sha256 CHAR(64) NOT NULL,
  tts_request_id VARCHAR(128) NOT NULL,
  tts_request_sha256 CHAR(64) NOT NULL,
  asr_request_id VARCHAR(128) NOT NULL,
  asr_request_sha256 CHAR(64),
  state VARCHAR(32) NOT NULL DEFAULT 'pending',
  tts_attempted_at BIGINT,
  tts_completed_at BIGINT,
  provider_audio_result_sha256 CHAR(64),
  provider_media_url_sha256 CHAR(64),
  runtime_audio_sha256 CHAR(64),
  download_sha256 CHAR(64),
  streamed_sha256 CHAR(64),
  storage_key VARCHAR(512),
  write_completed_at BIGINT,
  readback_sha256 CHAR(64),
  readback_completed_at BIGINT,
  asset_id VARCHAR(128),
  mime_type VARCHAR(64),
  byte_size BIGINT,
  pcm_format INTEGER,
  channel_count INTEGER,
  bits_per_sample INTEGER,
  sample_rate_hz INTEGER,
  block_align INTEGER,
  byte_rate INTEGER,
  frame_count BIGINT,
  duration_ms BIGINT,
  normalized_peak_bps INTEGER,
  overall_rms_bps INTEGER,
  active_window_bps INTEGER,
  audio_validated_at BIGINT,
  asr_attempted_at BIGINT,
  asr_completed_at BIGINT,
  asr_result_sha256 CHAR(64),
  normalized_transcript_sha256 CHAR(64),
  asr_similarity_bps INTEGER,
  machine_receipt_version VARCHAR(128),
  machine_receipt_hash CHAR(64),
  safe_error_code VARCHAR(128),
  terminal_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (build_item_id, scene_order),
  UNIQUE KEY uq_formal_qwen_audio_segment_scene(build_item_id, scene_id),
  UNIQUE KEY uq_formal_qwen_audio_segment_action(build_item_id, action_id),
  UNIQUE KEY uq_formal_qwen_audio_segment_narration(narration_segment_id),
  UNIQUE KEY uq_formal_qwen_audio_segment_tts_request(tts_request_id),
  UNIQUE KEY uq_formal_qwen_audio_segment_asr_request(asr_request_id),
  UNIQUE KEY uq_formal_qwen_audio_segment_asset(asset_id),
  INDEX idx_formal_qwen_audio_segments_state(build_item_id, state, scene_order),
  CONSTRAINT fk_formal_qwen_audio_segment_job
    FOREIGN KEY (build_item_id)
      REFERENCES learning_formal_qwen_audio_jobs(build_item_id),
  CONSTRAINT fk_formal_qwen_audio_segment_asset
    FOREIGN KEY (asset_id) REFERENCES learning_media_assets(id),
  CONSTRAINT chk_formal_qwen_audio_segment_identity CHECK (
    scene_order BETWEEN 0 AND 9
    AND scene_id <> '' AND action_id <> '' AND narration_segment_id <> ''
    AND source_text_sha256 REGEXP '^[0-9a-f]{64}$'
    AND tts_request_id <> '' AND tts_request_sha256 REGEXP '^[0-9a-f]{64}$'
  ),
  CONSTRAINT chk_formal_qwen_audio_segment_state CHECK (
    state IN ('pending', 'tts_attempted', 'tts_completed', 'audio_validated',
      'asr_attempted', 'auto_validated', 'failed', 'ambiguous')
    AND created_at > 0 AND updated_at >= created_at
    AND (tts_completed_at IS NULL OR tts_attempted_at IS NOT NULL)
    AND (audio_validated_at IS NULL OR tts_completed_at IS NOT NULL)
    AND (asr_attempted_at IS NULL OR audio_validated_at IS NOT NULL)
    AND (asr_completed_at IS NULL OR asr_attempted_at IS NOT NULL)
    AND (
      (state = 'pending' AND tts_attempted_at IS NULL AND terminal_at IS NULL)
      OR (state = 'tts_attempted' AND tts_attempted_at IS NOT NULL
        AND tts_completed_at IS NULL AND terminal_at IS NULL)
      OR (state = 'tts_completed' AND tts_completed_at IS NOT NULL
        AND audio_validated_at IS NULL AND terminal_at IS NULL)
      OR (state = 'audio_validated' AND audio_validated_at IS NOT NULL
        AND asr_attempted_at IS NULL AND terminal_at IS NULL)
      OR (state = 'asr_attempted' AND asr_attempted_at IS NOT NULL
        AND asr_completed_at IS NULL AND terminal_at IS NULL)
      OR (state = 'auto_validated' AND asr_completed_at IS NOT NULL
        AND asr_similarity_bps BETWEEN 8500 AND 10000
        AND machine_receipt_version IS NOT NULL
        AND machine_receipt_hash REGEXP '^[0-9a-f]{64}$'
        AND safe_error_code IS NULL AND terminal_at IS NOT NULL)
      OR (state IN ('failed', 'ambiguous') AND safe_error_code IS NOT NULL
        AND safe_error_code <> '' AND terminal_at IS NOT NULL)
    )
  ),
  CONSTRAINT chk_formal_qwen_audio_segment_pcm CHECK (
    (
      audio_validated_at IS NULL AND asset_id IS NULL AND mime_type IS NULL
      AND byte_size IS NULL AND pcm_format IS NULL AND channel_count IS NULL
      AND bits_per_sample IS NULL AND sample_rate_hz IS NULL
      AND block_align IS NULL AND byte_rate IS NULL AND frame_count IS NULL
      AND duration_ms IS NULL AND normalized_peak_bps IS NULL
      AND overall_rms_bps IS NULL AND active_window_bps IS NULL
    ) OR (
      audio_validated_at IS NOT NULL AND asset_id IS NOT NULL
      AND mime_type = 'audio/wav' AND byte_size BETWEEN 45 AND 16777216
      AND pcm_format = 1 AND channel_count = 1 AND bits_per_sample = 16
      AND sample_rate_hz BETWEEN 16000 AND 48000 AND block_align = 2
      AND byte_rate = sample_rate_hz * 2 AND frame_count > 0
      AND duration_ms BETWEEN 300 AND 120000
      AND normalized_peak_bps BETWEEN 100 AND 10000
      AND overall_rms_bps BETWEEN 30 AND 10000
      AND active_window_bps BETWEEN 500 AND 10000
      AND runtime_audio_sha256 REGEXP '^[0-9a-f]{64}$'
      AND download_sha256 = runtime_audio_sha256
      AND streamed_sha256 = runtime_audio_sha256
      AND readback_sha256 = runtime_audio_sha256
      AND write_completed_at IS NOT NULL AND readback_completed_at IS NOT NULL
    )
  ),
  CONSTRAINT chk_formal_qwen_audio_segment_asr CHECK (
    (asr_attempted_at IS NULL AND asr_request_sha256 IS NULL
      AND asr_result_sha256 IS NULL AND normalized_transcript_sha256 IS NULL
      AND asr_similarity_bps IS NULL)
    OR (asr_attempted_at IS NOT NULL
      AND asr_request_sha256 REGEXP '^[0-9a-f]{64}$')
  )
);

-- Repair the representative CHECK, FK and index when an interrupted operator
-- clears the migration marker after partial DDL.
SET @repair_058_job_counts = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_formal_qwen_audio_jobs ADD CONSTRAINT chk_formal_qwen_audio_job_counts CHECK (expected_segment_count = 10 AND 0 <= asr_passed_count AND asr_passed_count <= asr_attempted_count AND asr_attempted_count <= audio_validated_count AND audio_validated_count <= tts_completed_count AND tts_completed_count <= tts_attempted_count AND tts_attempted_count <= expected_segment_count)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_formal_qwen_audio_jobs'
    AND CONSTRAINT_NAME = 'chk_formal_qwen_audio_job_counts'
);
PREPARE repair_058_job_counts_stmt FROM @repair_058_job_counts;
EXECUTE repair_058_job_counts_stmt;
DEALLOCATE PREPARE repair_058_job_counts_stmt;

SET @repair_058_segment_fk = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_formal_qwen_audio_segment_receipts ADD CONSTRAINT fk_formal_qwen_audio_segment_job FOREIGN KEY (build_item_id) REFERENCES learning_formal_qwen_audio_jobs(build_item_id)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_formal_qwen_audio_segment_receipts'
    AND CONSTRAINT_NAME = 'fk_formal_qwen_audio_segment_job'
);
PREPARE repair_058_segment_fk_stmt FROM @repair_058_segment_fk;
EXECUTE repair_058_segment_fk_stmt;
DEALLOCATE PREPARE repair_058_segment_fk_stmt;

SET @repair_058_claim_index = (
  SELECT IF(COUNT(*) = 0,
    'CREATE INDEX idx_formal_qwen_audio_jobs_claim ON learning_formal_qwen_audio_jobs(state, claim_deadline_at, created_at)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_formal_qwen_audio_jobs'
    AND INDEX_NAME = 'idx_formal_qwen_audio_jobs_claim'
);
PREPARE repair_058_claim_index_stmt FROM @repair_058_claim_index;
EXECUTE repair_058_claim_index_stmt;
DEALLOCATE PREPARE repair_058_claim_index_stmt;
