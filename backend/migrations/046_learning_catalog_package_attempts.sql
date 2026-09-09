-- Course generation and lesson-package compilation are independent bounded
-- stages.  A valid persisted course must survive a classroom/compiler/media
-- failure, while a content-gate rejection must return the item to the course
-- stage without spending a package attempt.
ALTER TABLE learning_catalog_build_items
  ADD COLUMN package_attempt_count INTEGER NOT NULL DEFAULT 0
    AFTER attempt_count,
  ADD COLUMN active_package_request_id VARCHAR(128)
    AFTER active_generation_request_id;

-- Bind every compiled package to the exact immutable course content it was
-- compiled from.  Activation rechecks this hash instead of trusting an old
-- quality_status or package binding alone.
ALTER TABLE learning_lesson_packages
  ADD COLUMN source_course_content_hash CHAR(64) AFTER course_version;

UPDATE learning_lesson_packages AS package
JOIN learning_courses AS course
  ON course.id = package.course_id
 AND course.version = package.course_version
SET package.source_course_content_hash = SHA2(course.content_json, 256)
WHERE package.source_course_content_hash IS NULL;

-- Keep the column nullable for historical orphan packages because 037 did not
-- declare a course FK.  New writes always populate it, and activation rejects
-- NULL/mismatched hashes fail-closed.

CREATE INDEX idx_learning_catalog_build_items_stage
  ON learning_catalog_build_items(
    build_job_id, status, package_attempt_count, updated_at
  );

-- A package already attached to an item represents one completed package
-- attempt.  Preserve the exact classroom request when it is available so
-- media-pending and published replays remain idempotent.
UPDATE learning_catalog_build_items AS item
LEFT JOIN learning_classroom_generation_jobs AS classroom
  ON classroom.course_id = item.course_id
 AND classroom.course_version = item.course_version
 AND classroom.package_id = item.package_id
 AND classroom.package_version = item.package_version
SET item.package_attempt_count = CASE
      WHEN item.package_id IS NOT NULL THEN 1
      ELSE item.package_attempt_count
    END,
    item.active_package_request_id = CASE
      WHEN item.package_id IS NOT NULL
        THEN COALESCE(item.active_package_request_id, classroom.request_id)
      ELSE item.active_package_request_id
    END
WHERE item.course_id IS NOT NULL;

-- Before 046, classroom failures consumed the shared course attempt and left a
-- valid course in failed/processing.  Formally recover those rows to the
-- package-ready stage.  No model call occurs until an explicit catalog /run.
UPDATE learning_catalog_build_items
SET status = 'course_ready',
    package_attempt_count = 0,
    active_package_request_id = NULL,
    package_id = NULL,
    package_version = NULL,
    completed_at = NULL,
    updated_at = CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED)
WHERE course_id IS NOT NULL
  AND package_id IS NULL
  AND status IN ('failed', 'processing');
