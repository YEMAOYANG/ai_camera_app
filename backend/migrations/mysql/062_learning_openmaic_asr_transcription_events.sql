-- Additive Runtime event support for session-bound ASR transcripts. Existing
-- rows are not rewritten. Transcript text remains inside payload_json and is
-- explicitly excluded from assessment columns.
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
    AND scene_index >= 0 AND scene_index < 10
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
