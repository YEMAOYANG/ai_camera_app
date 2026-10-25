ALTER TABLE tasks
  ADD COLUMN learning_course_id VARCHAR(255),
  ADD COLUMN learning_course_version VARCHAR(64),
  ADD COLUMN learning_assignment_key CHAR(64);

CREATE UNIQUE INDEX uq_tasks_learning_assignment_key
  ON tasks(learning_assignment_key);

CREATE INDEX idx_tasks_learning_course
  ON tasks(family_id(96), child_id(96), scheduled_date(10), learning_course_id(96));

CREATE TABLE IF NOT EXISTS learning_courses (
  id VARCHAR(255) NOT NULL,
  version VARCHAR(64) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  node_code VARCHAR(128) NOT NULL,
  title VARCHAR(255) NOT NULL,
  objective TEXT NOT NULL,
  status VARCHAR(32) NOT NULL,
  content_json LONGTEXT NOT NULL,
  published_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (id, version),
  INDEX idx_learning_courses_recommendation(
    grade_code, subject, status, published_at
  )
);

CREATE TABLE IF NOT EXISTS learning_sessions (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  task_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  status VARCHAR(32) NOT NULL,
  current_question_index INTEGER NOT NULL DEFAULT 0,
  correct_count INTEGER NOT NULL DEFAULT 0,
  attempted_count INTEGER NOT NULL DEFAULT 0,
  answers_json LONGTEXT NOT NULL,
  started_at BIGINT NOT NULL,
  completed_at BIGINT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_sessions_task(family_id, task_id),
  INDEX idx_learning_sessions_child(family_id, child_id, updated_at)
);

CREATE TABLE IF NOT EXISTS learning_reports (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  task_id VARCHAR(128) NOT NULL,
  session_id VARCHAR(128) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  learning_date VARCHAR(10) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  score INTEGER NOT NULL,
  correct_count INTEGER NOT NULL,
  independent_correct_count INTEGER NOT NULL,
  hint_count INTEGER NOT NULL,
  total_questions INTEGER NOT NULL,
  mastery_level VARCHAR(32) NOT NULL,
  summary TEXT NOT NULL,
  strengths_json LONGTEXT NOT NULL,
  next_step TEXT NOT NULL,
  created_at BIGINT NOT NULL,
  UNIQUE KEY uq_learning_reports_session(family_id, session_id),
  INDEX idx_learning_reports_latest(family_id, child_id, created_at)
);

CREATE TABLE IF NOT EXISTS learning_mastery_states (
  family_id VARCHAR(128) NOT NULL,
  child_id VARCHAR(128) NOT NULL,
  node_code VARCHAR(128) NOT NULL,
  subject VARCHAR(64) NOT NULL,
  grade_code VARCHAR(64) NOT NULL,
  attempts INTEGER NOT NULL DEFAULT 0,
  correct_count INTEGER NOT NULL DEFAULT 0,
  independent_correct_count INTEGER NOT NULL DEFAULT 0,
  hint_count INTEGER NOT NULL DEFAULT 0,
  latest_score INTEGER NOT NULL DEFAULT 0,
  mastery_level VARCHAR(32) NOT NULL,
  last_practiced_at BIGINT NOT NULL,
  next_review_date VARCHAR(10) NOT NULL,
  course_id VARCHAR(255) NOT NULL,
  course_version VARCHAR(64) NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (family_id, child_id, node_code, subject),
  INDEX idx_learning_mastery_review(
    family_id, child_id, next_review_date, mastery_level
  )
);
