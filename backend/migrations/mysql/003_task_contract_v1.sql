ALTER TABLE tasks
  ADD COLUMN schedule_type VARCHAR(255) NOT NULL DEFAULT 'one_time',
  ADD COLUMN start_at VARCHAR(255),
  ADD COLUMN due_at VARCHAR(255),
  ADD COLUMN repeat_rule TEXT,
  ADD COLUMN priority INTEGER NOT NULL DEFAULT 3,
  ADD COLUMN completion_source VARCHAR(255),
  ADD COLUMN evidence TEXT,
  ADD COLUMN ai_observation_summary TEXT,
  ADD COLUMN created_by VARCHAR(255);

UPDATE tasks
SET
  start_at = CASE
    WHEN scheduled_start IS NOT NULL AND scheduled_start <> ''
      THEN CONCAT(scheduled_date, 'T', scheduled_start, ':00')
    ELSE start_at
  END,
  due_at = CASE
    WHEN scheduled_end IS NOT NULL AND scheduled_end <> ''
      THEN CONCAT(scheduled_date, 'T', scheduled_end, ':00')
    ELSE due_at
  END
WHERE start_at IS NULL OR due_at IS NULL;
