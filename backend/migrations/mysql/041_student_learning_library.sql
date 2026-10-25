CREATE TABLE IF NOT EXISTS student_learning_course_favorites (
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (family_id, child_id, course_id, course_version),
  INDEX idx_student_learning_favorites_recent(
    family_id, child_id, updated_at
  )
);

CREATE INDEX idx_tasks_student_learning_library
  ON tasks(family_id(96), child_id(96), type(32), updated_at, id(96));
