-- A catalog item attempt is a durable lease.  A worker restart may reclaim a
-- stale `processing` row, but it must replay the exact same downstream
-- generation request instead of consuming another attempt or publishing a
-- second candidate.
ALTER TABLE learning_catalog_build_items
  ADD COLUMN claim_origin_status VARCHAR(32) AFTER attempt_count,
  ADD COLUMN active_generation_request_id VARCHAR(128)
    AFTER generation_request_id;

-- Backfill already-started builds before the new claim code is deployed.
-- Attempt one always used the base request id and bounded retries used `.retryN`.
-- The origin value is audit metadata.  Request replay correctness comes from
-- the persisted active_generation_request_id itself.
UPDATE learning_catalog_build_items
SET claim_origin_status = CASE
      WHEN attempt_count > 1 THEN 'failed'
      ELSE 'pending'
    END,
    active_generation_request_id = CASE
      WHEN attempt_count > 1
        THEN CONCAT(generation_request_id, '.retry', attempt_count)
      ELSE generation_request_id
    END
WHERE attempt_count > 0
  AND active_generation_request_id IS NULL;
