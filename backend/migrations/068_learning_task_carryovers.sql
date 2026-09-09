-- A carryover changes only which historical learning task is presented on a
-- later day.  The source task/date/session remain immutable so resume,
-- reports, mastery, and audit history continue to point at one authority.

CREATE TABLE IF NOT EXISTS learning_task_carryovers (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  child_id VARCHAR(255) NOT NULL,
  source_task_id VARCHAR(255) NOT NULL,
  origin_date VARCHAR(10) NOT NULL,
  target_date VARCHAR(10) NOT NULL,
  target_slot VARCHAR(32) NOT NULL,
  reason VARCHAR(64) NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  CONSTRAINT fk_learning_task_carryover_source
    FOREIGN KEY (source_task_id) REFERENCES tasks(id)
);

CREATE INDEX idx_learning_task_carryover_child_date
  ON learning_task_carryovers(family_id(96), child_id(96), target_date, target_slot);

CREATE INDEX idx_learning_task_carryover_source
  ON learning_task_carryovers(source_task_id, target_date);
