SET @add_reminder_minutes_before = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE tasks ADD COLUMN reminder_minutes_before INTEGER NOT NULL DEFAULT 5',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'reminder_minutes_before'
);
PREPARE add_reminder_minutes_before_stmt FROM @add_reminder_minutes_before;
EXECUTE add_reminder_minutes_before_stmt;
DEALLOCATE PREPARE add_reminder_minutes_before_stmt;

SET @add_reminder_status = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE tasks ADD COLUMN reminder_status VARCHAR(255) NOT NULL DEFAULT ''pending''',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'reminder_status'
);
PREPARE add_reminder_status_stmt FROM @add_reminder_status;
EXECUTE add_reminder_status_stmt;
DEALLOCATE PREPARE add_reminder_status_stmt;

SET @add_started_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE tasks ADD COLUMN started_at BIGINT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'started_at'
);
PREPARE add_started_at_stmt FROM @add_started_at;
EXECUTE add_started_at_stmt;
DEALLOCATE PREPARE add_started_at_stmt;

SET @add_ended_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE tasks ADD COLUMN ended_at BIGINT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'ended_at'
);
PREPARE add_ended_at_stmt FROM @add_ended_at;
EXECUTE add_ended_at_stmt;
DEALLOCATE PREPARE add_ended_at_stmt;

SET @add_missed_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE tasks ADD COLUMN missed_at BIGINT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'missed_at'
);
PREPARE add_missed_at_stmt FROM @add_missed_at;
EXECUTE add_missed_at_stmt;
DEALLOCATE PREPARE add_missed_at_stmt;

SET @add_delayed_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE tasks ADD COLUMN delayed_at BIGINT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'delayed_at'
);
PREPARE add_delayed_at_stmt FROM @add_delayed_at;
EXECUTE add_delayed_at_stmt;
DEALLOCATE PREPARE add_delayed_at_stmt;

SET @add_last_reminder_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE tasks ADD COLUMN last_reminder_at BIGINT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'last_reminder_at'
);
PREPARE add_last_reminder_at_stmt FROM @add_last_reminder_at;
EXECUTE add_last_reminder_at_stmt;
DEALLOCATE PREPARE add_last_reminder_at_stmt;

SET @add_next_reminder_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE tasks ADD COLUMN next_reminder_at BIGINT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'next_reminder_at'
);
PREPARE add_next_reminder_at_stmt FROM @add_next_reminder_at;
EXECUTE add_next_reminder_at_stmt;
DEALLOCATE PREPARE add_next_reminder_at_stmt;

SET @add_delay_reminder_count = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE tasks ADD COLUMN delay_reminder_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'delay_reminder_count'
);
PREPARE add_delay_reminder_count_stmt FROM @add_delay_reminder_count;
EXECUTE add_delay_reminder_count_stmt;
DEALLOCATE PREPARE add_delay_reminder_count_stmt;

SET @add_camera_observation_status = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE tasks ADD COLUMN camera_observation_status VARCHAR(255) NOT NULL DEFAULT ''unknown''',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'camera_observation_status'
);
PREPARE add_camera_observation_status_stmt FROM @add_camera_observation_status;
EXECUTE add_camera_observation_status_stmt;
DEALLOCATE PREPARE add_camera_observation_status_stmt;

SET @add_device_id = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE tasks ADD COLUMN device_id VARCHAR(255)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'device_id'
);
PREPARE add_device_id_stmt FROM @add_device_id;
EXECUTE add_device_id_stmt;
DEALLOCATE PREPARE add_device_id_stmt;

SET @add_timezone = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE tasks ADD COLUMN timezone VARCHAR(255) NOT NULL DEFAULT ''Asia/Shanghai''',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND COLUMN_NAME = 'timezone'
);
PREPARE add_timezone_stmt FROM @add_timezone;
EXECUTE add_timezone_stmt;
DEALLOCATE PREPARE add_timezone_stmt;

SET @add_idx_tasks_scheduler_runtime = (
  SELECT IF(
    COUNT(*) = 0,
    'CREATE INDEX idx_tasks_scheduler_runtime ON tasks(scheduled_date, status, scheduled_start)',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'tasks'
    AND INDEX_NAME = 'idx_tasks_scheduler_runtime'
);
PREPARE add_idx_tasks_scheduler_runtime_stmt FROM @add_idx_tasks_scheduler_runtime;
EXECUTE add_idx_tasks_scheduler_runtime_stmt;
DEALLOCATE PREPARE add_idx_tasks_scheduler_runtime_stmt;
