ALTER TABLE learning_openmaic_runtime_classrooms
  ADD COLUMN provider_attempt_ordinal INTEGER NULL AFTER attempt_ordinal;

UPDATE learning_openmaic_runtime_classrooms
SET provider_attempt_ordinal = attempt_ordinal
WHERE candidate_build_item_id IS NOT NULL
  AND provider_attempt_ordinal IS NULL;

CREATE UNIQUE INDEX uq_learning_openmaic_candidate_provider_attempt
  ON learning_openmaic_runtime_classrooms(
    candidate_build_item_id, provider_attempt_ordinal
  );

ALTER TABLE learning_openmaic_runtime_classrooms
  DROP CHECK chk_learning_openmaic_runtime_candidate_attempt,
  ADD CONSTRAINT chk_learning_openmaic_runtime_candidate_attempt CHECK (
    (
      candidate_build_item_id IS NULL
      AND provider_attempt_ordinal IS NULL
      AND (
        (attempt_ordinal = 1 AND retry_of_runtime_id IS NULL
          AND retry_reason IS NULL AND expected_previous_job_id IS NULL)
        OR (attempt_ordinal = 2 AND retry_of_runtime_id IS NOT NULL
          AND retry_reason = 'approved_stage2_retry'
          AND expected_previous_job_id IS NOT NULL)
        OR (attempt_ordinal = 3 AND retry_of_runtime_id IS NOT NULL
          AND retry_reason = 'approved_stage2_retry_3'
          AND expected_previous_job_id IS NOT NULL)
      )
    )
    OR (
      candidate_build_item_id IS NOT NULL
      AND attempt_ordinal >= 1 AND attempt_ordinal <= 16
      AND (
        provider_attempt_ordinal IS NULL
        OR (provider_attempt_ordinal >= 1 AND provider_attempt_ordinal <= 3)
      )
      AND (
        (attempt_ordinal = 1 AND retry_of_runtime_id IS NULL
          AND retry_reason IS NULL AND expected_previous_job_id IS NULL)
        OR (attempt_ordinal >= 2 AND retry_of_runtime_id IS NOT NULL
          AND retry_reason = CONCAT('formal_candidate_retry_', attempt_ordinal)
          AND expected_previous_job_id IS NOT NULL)
      )
    )
  );
