-- Keep operator-unblocked failures distinct from a later failed Runtime attempt.
ALTER TABLE learning_course_supply_incidents
  ADD COLUMN failure_runtime_id VARCHAR(255) NULL;
