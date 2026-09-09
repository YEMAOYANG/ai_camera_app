ALTER TABLE tasks
  ADD COLUMN learning_slot VARCHAR(32);

UPDATE tasks
SET learning_slot = 'core'
WHERE type = 'learning'
  AND learning_course_id IS NOT NULL
  AND (learning_slot IS NULL OR learning_slot = '');

CREATE INDEX idx_tasks_learning_daily_slot
  ON tasks(family_id(96), child_id(96), scheduled_date(10), learning_slot);
