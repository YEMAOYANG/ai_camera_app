SET @add_sessions_device_model = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE sessions ADD COLUMN device_model VARCHAR(255) AFTER device_type', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'sessions'
    AND COLUMN_NAME = 'device_model'
);
PREPARE add_sessions_device_model_stmt FROM @add_sessions_device_model;
EXECUTE add_sessions_device_model_stmt;
DEALLOCATE PREPARE add_sessions_device_model_stmt;

SET @add_sessions_device_hardware = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE sessions ADD COLUMN device_hardware VARCHAR(255) AFTER device_model', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'sessions'
    AND COLUMN_NAME = 'device_hardware'
);
PREPARE add_sessions_device_hardware_stmt FROM @add_sessions_device_hardware;
EXECUTE add_sessions_device_hardware_stmt;
DEALLOCATE PREPARE add_sessions_device_hardware_stmt;

SET @add_sessions_os_version = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE sessions ADD COLUMN os_version VARCHAR(255) AFTER platform', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'sessions'
    AND COLUMN_NAME = 'os_version'
);
PREPARE add_sessions_os_version_stmt FROM @add_sessions_os_version;
EXECUTE add_sessions_os_version_stmt;
DEALLOCATE PREPARE add_sessions_os_version_stmt;
