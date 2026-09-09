-- Provider quota, rate-limit and transport outages are recoverable leases, not
-- failed course-content attempts.  Keep the exact attempt/request id so an
-- operator can explicitly replay it after the provider is healthy.

UPDATE learning_catalog_build_items
SET status = 'external_failed', claim_origin_status = 'external_failed',
  completed_at = NULL, updated_at = updated_at
WHERE course_id IS NULL
  AND status = 'failed'
  AND error_code IN (
    'generation_failed',
    'dynamic_generation_failed',
    'openmaic_unavailable'
  )
  AND LOWER(COALESCE(error_message_safe, '')) REGEXP
    'http[[:space:]]+(408|425|429|5[0-9][0-9])|quota|rate[[:space:]]*limit|too[[:space:]]+many[[:space:]]+requests|(time|timed)[[:space:]]*out|timeout|connection[[:space:]]+(reset|refused|aborted|closed)|temporar(y|ily)[[:space:]]+unavailable|service[[:space:]]+unavailable|bad[[:space:]]+gateway|gateway[[:space:]]+timeout|name[[:space:]]+resolution|dns';

UPDATE learning_catalog_build_jobs AS job
JOIN (
  SELECT build_job_id,
    COUNT(*) AS total_count,
    SUM(CASE WHEN status = 'ready' THEN 1 ELSE 0 END) AS ready_count,
    SUM(CASE WHEN status = 'failed' THEN 1 ELSE 0 END) AS failed_count,
    SUM(CASE WHEN status = 'external_failed' THEN 1 ELSE 0 END) AS external_count
  FROM learning_catalog_build_items
  GROUP BY build_job_id
) AS counts ON counts.build_job_id = job.id
SET job.total_item_count = counts.total_count,
  job.ready_item_count = counts.ready_count,
  job.failed_item_count = counts.failed_count,
  job.status = 'running',
  job.completed_at = NULL,
  job.updated_at = job.updated_at
WHERE counts.external_count > 0;

UPDATE learning_catalog_releases AS release_row
JOIN learning_catalog_build_jobs AS job ON job.release_id = release_row.id
JOIN (
  SELECT build_job_id,
    SUM(CASE WHEN status = 'external_failed' THEN 1 ELSE 0 END) AS external_count
  FROM learning_catalog_build_items
  GROUP BY build_job_id
) AS counts ON counts.build_job_id = job.id
SET release_row.quality_status = 'building',
  release_row.updated_at = release_row.updated_at
WHERE counts.external_count > 0
  AND release_row.status = 'draft';
