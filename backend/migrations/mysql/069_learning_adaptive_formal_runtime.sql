-- Make formal classroom length an immutable per-classroom value rather than a
-- global ten-scene constant. Existing ten-scene rows remain valid.

ALTER TABLE learning_formal_qwen_audio_jobs
  ALTER COLUMN expected_segment_count DROP DEFAULT;

ALTER TABLE learning_formal_qwen_audio_jobs
  DROP CHECK chk_formal_qwen_audio_job_counts,
  DROP CHECK chk_formal_qwen_audio_job_terminal,
  ADD CONSTRAINT chk_formal_qwen_audio_job_counts CHECK (
    expected_segment_count BETWEEN 1 AND 240
    AND 0 <= asr_passed_count
    AND asr_passed_count <= asr_attempted_count
    AND asr_attempted_count <= audio_validated_count
    AND audio_validated_count <= tts_completed_count
    AND tts_completed_count <= tts_attempted_count
    AND tts_attempted_count <= expected_segment_count
  ),
  ADD CONSTRAINT chk_formal_qwen_audio_job_terminal CHECK (
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
      OR (state = 'auto_validated'
        AND tts_attempted_count = expected_segment_count
        AND tts_completed_count = expected_segment_count
        AND audio_validated_count = expected_segment_count
        AND asr_attempted_count = expected_segment_count
        AND asr_passed_count = expected_segment_count
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
  );

ALTER TABLE learning_formal_qwen_audio_segment_receipts
  DROP INDEX uq_formal_qwen_audio_segment_scene,
  ADD INDEX idx_formal_qwen_audio_segment_scene(build_item_id, scene_id),
  DROP CHECK chk_formal_qwen_audio_segment_identity,
  ADD CONSTRAINT chk_formal_qwen_audio_segment_identity CHECK (
    scene_order BETWEEN 0 AND 239
    AND scene_id <> '' AND action_id <> '' AND narration_segment_id <> ''
    AND source_text_sha256 REGEXP '^[0-9a-f]{64}$'
    AND tts_request_id <> '' AND tts_request_sha256 REGEXP '^[0-9a-f]{64}$'
  );

ALTER TABLE learning_openmaic_provider_readiness_jobs
  DROP CHECK chk_openmaic_provider_readiness_identity,
  ADD CONSTRAINT chk_openmaic_provider_readiness_identity CHECK (
    request_sha256 REGEXP '^[0-9a-f]{64}$'
    AND grade_code <> ''
    AND target_fingerprint REGEXP '^[0-9a-f]{64}$'
    AND classroom_content_sha256 REGEXP '^[0-9a-f]{64}$'
    AND audio_job_terminal_receipt_hash REGEXP '^[0-9a-f]{64}$'
    AND audio_job_state = 'auto_validated'
    AND validation_scene_order BETWEEN 0 AND 239
    AND validation_audio_sha256 REGEXP '^[0-9a-f]{64}$'
    AND validation_audio_machine_receipt_hash REGEXP '^[0-9a-f]{64}$'
    AND validation_segment_state = 'auto_validated'
    AND route_session_contract_version = 'mira.openmaic.conversation-proof.v1'
    AND route_session_receipt_hash REGEXP '^[0-9a-f]{64}$'
    AND route_session_provider_call = 0
    AND route_session_status = 'passed'
    AND route_session_completed_at > 0
    AND provider_contract_version = 'mira.openmaic.formal-provider-readiness.v1'
  );

ALTER TABLE learning_openmaic_runtime_event_streams
  DROP CHECK chk_openmaic_runtime_stream_state,
  ADD CONSTRAINT chk_openmaic_runtime_stream_state CHECK (
    target_fingerprint REGEXP '^[0-9a-f]{64}$'
    AND expected_scene_count BETWEEN 1 AND 60
    AND last_sequence >= 0
    AND (
      (completed_at IS NULL AND report_id IS NULL)
      OR (completed_at IS NOT NULL AND completed_at > 0 AND report_id IS NOT NULL)
    )
  );

-- MySQL CHECK constraints cannot compare an event row with its parent stream.
-- The service performs that exact comparison under the stream lock, while SQL keeps
-- the same bounded domain as expected_scene_count.
ALTER TABLE learning_openmaic_runtime_events
  DROP CHECK chk_openmaic_runtime_event_identity,
  ADD CONSTRAINT chk_openmaic_runtime_event_identity CHECK (
    sequence >= 1
    AND idempotency_key REGEXP '^[0-9a-f]{64}$'
    AND request_sha256 REGEXP '^[0-9a-f]{64}$'
    AND receipt_sha256 REGEXP '^[0-9a-f]{64}$'
    AND event_type IN (
      'scene_entered', 'action_completed', 'answer_submitted',
      'asr_transcribed', 'classroom_completed'
    )
    AND scene_index >= 0 AND scene_index < 60
    AND (
      (event_type = 'scene_entered' AND action_id IS NULL
        AND question_id IS NULL AND attempt_number IS NULL)
      OR (event_type = 'action_completed' AND action_id IS NOT NULL
        AND question_id IS NULL AND attempt_number IS NULL)
      OR (event_type = 'answer_submitted' AND action_id IS NULL
        AND question_id IS NOT NULL AND attempt_number = 1)
      OR (event_type = 'asr_transcribed' AND action_id IS NULL
        AND question_id IS NULL AND attempt_number IS NULL)
      OR (event_type = 'classroom_completed' AND action_id IS NULL
        AND question_id IS NULL AND attempt_number IS NULL)
    )
  );
