-- A manually approved Stage 2 retry is a new immutable runtime attempt, not
-- an overwrite of the failed classroom row.  This preserves the first
-- upstream job, terminal error and timestamps while allowing exactly one
-- successor for the same published lesson package.
ALTER TABLE learning_openmaic_runtime_classrooms
  ADD COLUMN attempt_ordinal INTEGER NOT NULL DEFAULT 1 AFTER request_id,
  ADD COLUMN retry_of_runtime_id VARCHAR(128) AFTER attempt_ordinal,
  ADD COLUMN retry_reason VARCHAR(64) AFTER retry_of_runtime_id,
  ADD COLUMN expected_previous_job_id VARCHAR(128) AFTER retry_reason,
  DROP INDEX uq_learning_openmaic_runtime_package,
  ADD UNIQUE KEY uq_learning_openmaic_runtime_package_attempt(
    package_id, package_version, attempt_ordinal
  ),
  ADD UNIQUE KEY uq_learning_openmaic_runtime_retry_of(retry_of_runtime_id),
  ADD UNIQUE KEY uq_learning_openmaic_runtime_upstream_job(upstream_job_id),
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
        AND retry_reason IS NOT NULL
        AND expected_previous_job_id IS NOT NULL
      )
    ),
  ADD CONSTRAINT fk_learning_openmaic_runtime_retry_of
    FOREIGN KEY (retry_of_runtime_id)
      REFERENCES learning_openmaic_runtime_classrooms(id);
