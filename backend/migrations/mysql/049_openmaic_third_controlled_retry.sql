-- The user explicitly approved one third Stage 2 generation after attempt two
-- was terminally failed because its generation process restarted. Preserve
-- attempts one and two as immutable audit rows and permit exactly one
-- attempt-two -> attempt-three successor.
ALTER TABLE learning_openmaic_runtime_classrooms
  DROP CHECK chk_learning_openmaic_runtime_attempt,
  ADD CONSTRAINT chk_learning_openmaic_runtime_attempt
    CHECK (
      (
        attempt_ordinal = 1
        AND retry_of_runtime_id IS NULL
        AND retry_reason IS NULL
        AND expected_previous_job_id IS NULL
      )
      OR (
        attempt_ordinal = 2
        AND retry_of_runtime_id IS NOT NULL
        AND retry_reason = 'approved_stage2_retry'
        AND expected_previous_job_id IS NOT NULL
      )
      OR (
        attempt_ordinal = 3
        AND retry_of_runtime_id IS NOT NULL
        AND retry_reason = 'approved_stage2_retry_3'
        AND expected_previous_job_id IS NOT NULL
      )
    );
