CREATE TABLE IF NOT EXISTS family_members (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  user_id VARCHAR(255),
  name VARCHAR(255) NOT NULL,
  phone VARCHAR(255),
  role VARCHAR(255) NOT NULL,
  status VARCHAR(255) NOT NULL,
  notify_enabled TINYINT NOT NULL DEFAULT 1,
  created_at BIGINT NOT NULL,
  updated_at BIGINT NOT NULL
);

SET @add_family_members_family_index = (
  SELECT IF(COUNT(*) = 0, 'CREATE INDEX idx_family_members_family ON family_members(family_id, status)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'family_members'
    AND INDEX_NAME = 'idx_family_members_family'
);
PREPARE add_family_members_family_index_stmt FROM @add_family_members_family_index;
EXECUTE add_family_members_family_index_stmt;
DEALLOCATE PREPARE add_family_members_family_index_stmt;

SET @repair_children_education_stage = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE children ADD COLUMN education_stage VARCHAR(255)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'education_stage'
);
PREPARE repair_children_education_stage_stmt FROM @repair_children_education_stage;
EXECUTE repair_children_education_stage_stmt;
DEALLOCATE PREPARE repair_children_education_stage_stmt;

SET @repair_children_grade = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE children ADD COLUMN grade VARCHAR(255)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'grade'
);
PREPARE repair_children_grade_stmt FROM @repair_children_grade;
EXECUTE repair_children_grade_stmt;
DEALLOCATE PREPARE repair_children_grade_stmt;

SET @repair_children_school_name = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE children ADD COLUMN school_name VARCHAR(255)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'school_name'
);
PREPARE repair_children_school_name_stmt FROM @repair_children_school_name;
EXECUTE repair_children_school_name_stmt;
DEALLOCATE PREPARE repair_children_school_name_stmt;

SET @repair_children_interests = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE children ADD COLUMN interests TEXT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'interests'
);
PREPARE repair_children_interests_stmt FROM @repair_children_interests;
EXECUTE repair_children_interests_stmt;
DEALLOCATE PREPARE repair_children_interests_stmt;

SET @repair_children_task_preferences = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE children ADD COLUMN task_preferences TEXT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'task_preferences'
);
PREPARE repair_children_task_preferences_stmt FROM @repair_children_task_preferences;
EXECUTE repair_children_task_preferences_stmt;
DEALLOCATE PREPARE repair_children_task_preferences_stmt;

SET @repair_contacts_default_notify = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE emergency_contacts ADD COLUMN default_notify TINYINT NOT NULL DEFAULT 1', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'emergency_contacts'
    AND COLUMN_NAME = 'default_notify'
);
PREPARE repair_contacts_default_notify_stmt FROM @repair_contacts_default_notify;
EXECUTE repair_contacts_default_notify_stmt;
DEALLOCATE PREPARE repair_contacts_default_notify_stmt;

SET @repair_contacts_updated_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE emergency_contacts ADD COLUMN updated_at BIGINT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'emergency_contacts'
    AND COLUMN_NAME = 'updated_at'
);
PREPARE repair_contacts_updated_at_stmt FROM @repair_contacts_updated_at;
EXECUTE repair_contacts_updated_at_stmt;
DEALLOCATE PREPARE repair_contacts_updated_at_stmt;

UPDATE emergency_contacts
SET updated_at = created_at
WHERE updated_at IS NULL;

SET @repair_devices_unbound_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE devices ADD COLUMN unbound_at BIGINT', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'devices'
    AND COLUMN_NAME = 'unbound_at'
);
PREPARE repair_devices_unbound_at_stmt FROM @repair_devices_unbound_at;
EXECUTE repair_devices_unbound_at_stmt;
DEALLOCATE PREPARE repair_devices_unbound_at_stmt;

CREATE TABLE IF NOT EXISTS app_settings (
  family_id VARCHAR(255) NOT NULL,
  setting_key VARCHAR(255) NOT NULL,
  value TEXT NOT NULL,
  updated_at BIGINT NOT NULL,
  PRIMARY KEY (family_id, setting_key)
);

CREATE TABLE IF NOT EXISTS feedback_items (
  id VARCHAR(255) PRIMARY KEY,
  family_id VARCHAR(255) NOT NULL,
  user_id VARCHAR(255) NOT NULL,
  category VARCHAR(255) NOT NULL,
  content TEXT NOT NULL,
  status VARCHAR(255) NOT NULL,
  created_at BIGINT NOT NULL
);

SET @add_feedback_items_family_created_index = (
  SELECT IF(COUNT(*) = 0, 'CREATE INDEX idx_feedback_items_family_created ON feedback_items(family_id, created_at)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'feedback_items'
    AND INDEX_NAME = 'idx_feedback_items_family_created'
);
PREPARE add_feedback_items_family_created_index_stmt FROM @add_feedback_items_family_created_index;
EXECUTE add_feedback_items_family_created_index_stmt;
DEALLOCATE PREPARE add_feedback_items_family_created_index_stmt;
