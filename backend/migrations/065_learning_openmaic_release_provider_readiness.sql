-- Provider readiness is one release-scoped canary, not one Provider call set
-- per course.  The existing job remains bound to its canonical witness item;
-- this index makes the release identity unique for every downstream join.
SET @add_065_release_provider_canary_index = (
  SELECT IF(COUNT(*) = 0,
    'ALTER TABLE learning_openmaic_provider_readiness_jobs ADD UNIQUE INDEX uq_openmaic_provider_readiness_release_canary(release_id, grade_code, target_fingerprint)',
    'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'learning_openmaic_provider_readiness_jobs'
    AND INDEX_NAME = 'uq_openmaic_provider_readiness_release_canary'
);
PREPARE add_065_release_provider_canary_index_stmt
  FROM @add_065_release_provider_canary_index;
EXECUTE add_065_release_provider_canary_index_stmt;
DEALLOCATE PREPARE add_065_release_provider_canary_index_stmt;
