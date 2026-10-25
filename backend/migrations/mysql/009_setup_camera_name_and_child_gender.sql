SET @add_setup_camera_name_status = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE setup_progress ADD COLUMN camera_name_status VARCHAR(255) NOT NULL DEFAULT ''pending'' AFTER child_profile_status', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'setup_progress'
    AND COLUMN_NAME = 'camera_name_status'
);
PREPARE add_setup_camera_name_status_stmt FROM @add_setup_camera_name_status;
EXECUTE add_setup_camera_name_status_stmt;
DEALLOCATE PREPARE add_setup_camera_name_status_stmt;

SET @add_setup_camera_name_intro_status = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE setup_progress ADD COLUMN camera_name_intro_status VARCHAR(255) NOT NULL DEFAULT ''pending'' AFTER camera_name_status', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'setup_progress'
    AND COLUMN_NAME = 'camera_name_intro_status'
);
PREPARE add_setup_camera_name_intro_status_stmt FROM @add_setup_camera_name_intro_status;
EXECUTE add_setup_camera_name_intro_status_stmt;
DEALLOCATE PREPARE add_setup_camera_name_intro_status_stmt;

SET @add_setup_camera_name_intro_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE setup_progress ADD COLUMN camera_name_intro_at BIGINT AFTER camera_name_intro_status', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'setup_progress'
    AND COLUMN_NAME = 'camera_name_intro_at'
);
PREPARE add_setup_camera_name_intro_at_stmt FROM @add_setup_camera_name_intro_at;
EXECUTE add_setup_camera_name_intro_at_stmt;
DEALLOCATE PREPARE add_setup_camera_name_intro_at_stmt;

SET @add_children_gender = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE children ADD COLUMN gender VARCHAR(255) NOT NULL DEFAULT ''unspecified'' AFTER nickname', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'gender'
);
PREPARE add_children_gender_stmt FROM @add_children_gender;
EXECUTE add_children_gender_stmt;
DEALLOCATE PREPARE add_children_gender_stmt;

SET @add_children_education_stage = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE children ADD COLUMN education_stage VARCHAR(255) AFTER age_stage', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'education_stage'
);
PREPARE add_children_education_stage_stmt FROM @add_children_education_stage;
EXECUTE add_children_education_stage_stmt;
DEALLOCATE PREPARE add_children_education_stage_stmt;

SET @add_children_grade = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE children ADD COLUMN grade VARCHAR(255) AFTER education_stage', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'grade'
);
PREPARE add_children_grade_stmt FROM @add_children_grade;
EXECUTE add_children_grade_stmt;
DEALLOCATE PREPARE add_children_grade_stmt;

SET @add_devices_wake_name = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE devices ADD COLUMN wake_name VARCHAR(255) AFTER name', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'devices'
    AND COLUMN_NAME = 'wake_name'
);
PREPARE add_devices_wake_name_stmt FROM @add_devices_wake_name;
EXECUTE add_devices_wake_name_stmt;
DEALLOCATE PREPARE add_devices_wake_name_stmt;
