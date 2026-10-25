SET @add_users_account_status = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE users ADD COLUMN account_status VARCHAR(255) NOT NULL DEFAULT ''active'' AFTER display_name', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'users'
    AND COLUMN_NAME = 'account_status'
);
PREPARE add_users_account_status_stmt FROM @add_users_account_status;
EXECUTE add_users_account_status_stmt;
DEALLOCATE PREPARE add_users_account_status_stmt;

SET @add_users_deletion_requested_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE users ADD COLUMN deletion_requested_at BIGINT AFTER created_at', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'users'
    AND COLUMN_NAME = 'deletion_requested_at'
);
PREPARE add_users_deletion_requested_at_stmt FROM @add_users_deletion_requested_at;
EXECUTE add_users_deletion_requested_at_stmt;
DEALLOCATE PREPARE add_users_deletion_requested_at_stmt;

SET @add_users_deleted_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE users ADD COLUMN deleted_at BIGINT AFTER deletion_requested_at', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'users'
    AND COLUMN_NAME = 'deleted_at'
);
PREPARE add_users_deleted_at_stmt FROM @add_users_deleted_at;
EXECUTE add_users_deleted_at_stmt;
DEALLOCATE PREPARE add_users_deleted_at_stmt;

SET @add_sessions_device_label = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE sessions ADD COLUMN device_label VARCHAR(255) AFTER user_id', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'sessions'
    AND COLUMN_NAME = 'device_label'
);
PREPARE add_sessions_device_label_stmt FROM @add_sessions_device_label;
EXECUTE add_sessions_device_label_stmt;
DEALLOCATE PREPARE add_sessions_device_label_stmt;

SET @add_sessions_device_type = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE sessions ADD COLUMN device_type VARCHAR(255) AFTER device_label', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'sessions'
    AND COLUMN_NAME = 'device_type'
);
PREPARE add_sessions_device_type_stmt FROM @add_sessions_device_type;
EXECUTE add_sessions_device_type_stmt;
DEALLOCATE PREPARE add_sessions_device_type_stmt;

SET @add_sessions_platform = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE sessions ADD COLUMN platform VARCHAR(255) AFTER device_type', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'sessions'
    AND COLUMN_NAME = 'platform'
);
PREPARE add_sessions_platform_stmt FROM @add_sessions_platform;
EXECUTE add_sessions_platform_stmt;
DEALLOCATE PREPARE add_sessions_platform_stmt;

SET @add_sessions_app_version = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE sessions ADD COLUMN app_version VARCHAR(255) AFTER platform', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'sessions'
    AND COLUMN_NAME = 'app_version'
);
PREPARE add_sessions_app_version_stmt FROM @add_sessions_app_version;
EXECUTE add_sessions_app_version_stmt;
DEALLOCATE PREPARE add_sessions_app_version_stmt;

SET @add_sessions_last_active_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE sessions ADD COLUMN last_active_at BIGINT AFTER app_version', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'sessions'
    AND COLUMN_NAME = 'last_active_at'
);
PREPARE add_sessions_last_active_at_stmt FROM @add_sessions_last_active_at;
EXECUTE add_sessions_last_active_at_stmt;
DEALLOCATE PREPARE add_sessions_last_active_at_stmt;

UPDATE sessions
SET
  device_label = COALESCE(device_label, '已登录设备'),
  device_type = COALESCE(device_type, 'unknown'),
  platform = COALESCE(platform, 'unknown'),
  last_active_at = COALESCE(last_active_at, rotated_at, created_at)
WHERE device_label IS NULL
   OR device_type IS NULL
   OR platform IS NULL
   OR last_active_at IS NULL;

CREATE TABLE IF NOT EXISTS account_deletion_requests (
  id VARCHAR(255) PRIMARY KEY,
  user_id VARCHAR(255) NOT NULL,
  family_id VARCHAR(255) NOT NULL,
  status VARCHAR(255) NOT NULL,
  reason VARCHAR(255),
  requested_at BIGINT NOT NULL,
  completed_at BIGINT,
  cancelled_at BIGINT
);
