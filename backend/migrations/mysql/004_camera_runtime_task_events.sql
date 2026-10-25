CREATE TABLE IF NOT EXISTS task_events (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  task_id VARCHAR(255) NOT NULL,
  event_type VARCHAR(255) NOT NULL,
  message TEXT,
  payload TEXT,
  created_at BIGINT NOT NULL
);

CREATE INDEX idx_task_events_task_created
  ON task_events(task_id, created_at);

CREATE INDEX idx_task_events_family_created
  ON task_events(family_id, created_at);

CREATE TABLE IF NOT EXISTS camera_commands (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  device_id VARCHAR(255),
  task_id VARCHAR(255),
  command_type VARCHAR(255) NOT NULL,
  status VARCHAR(255) NOT NULL,
  message TEXT,
  request_payload TEXT,
  response_payload TEXT,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL,
  completed_at BIGINT
);

CREATE INDEX idx_camera_commands_family_created
  ON camera_commands(family_id, created_at);

CREATE INDEX idx_camera_commands_task_created
  ON camera_commands(task_id, created_at);
