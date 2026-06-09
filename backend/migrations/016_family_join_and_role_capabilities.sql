SET @add_families_family_code = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE families ADD COLUMN family_code VARCHAR(32) AFTER name', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'families'
    AND COLUMN_NAME = 'family_code'
);
PREPARE add_families_family_code_stmt FROM @add_families_family_code;
EXECUTE add_families_family_code_stmt;
DEALLOCATE PREPARE add_families_family_code_stmt;

SET @add_families_family_code_updated_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE families ADD COLUMN family_code_updated_at BIGINT AFTER family_code', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'families'
    AND COLUMN_NAME = 'family_code_updated_at'
);
PREPARE add_families_family_code_updated_at_stmt FROM @add_families_family_code_updated_at;
EXECUTE add_families_family_code_updated_at_stmt;
DEALLOCATE PREPARE add_families_family_code_updated_at_stmt;

UPDATE families
SET family_code = UPPER(SUBSTRING(REPLACE(UUID(), '-', ''), 1, 8)),
    family_code_updated_at = COALESCE(family_code_updated_at, created_at)
WHERE family_code IS NULL OR family_code = '';

SET @add_families_family_code_unique = (
  SELECT IF(COUNT(*) = 0, 'CREATE UNIQUE INDEX idx_families_family_code ON families(family_code)', 'SELECT 1')
  FROM INFORMATION_SCHEMA.STATISTICS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'families'
    AND INDEX_NAME = 'idx_families_family_code'
);
PREPARE add_families_family_code_unique_stmt FROM @add_families_family_code_unique;
EXECUTE add_families_family_code_unique_stmt;
DEALLOCATE PREPARE add_families_family_code_unique_stmt;

SET @add_family_invitations_accepted_by = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE family_invitations ADD COLUMN accepted_by VARCHAR(255) AFTER status', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'family_invitations'
    AND COLUMN_NAME = 'accepted_by'
);
PREPARE add_family_invitations_accepted_by_stmt FROM @add_family_invitations_accepted_by;
EXECUTE add_family_invitations_accepted_by_stmt;
DEALLOCATE PREPARE add_family_invitations_accepted_by_stmt;

SET @add_family_invitations_accepted_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE family_invitations ADD COLUMN accepted_at BIGINT AFTER accepted_by', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'family_invitations'
    AND COLUMN_NAME = 'accepted_at'
);
PREPARE add_family_invitations_accepted_at_stmt FROM @add_family_invitations_accepted_at;
EXECUTE add_family_invitations_accepted_at_stmt;
DEALLOCATE PREPARE add_family_invitations_accepted_at_stmt;

SET @add_family_invitations_declined_at = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE family_invitations ADD COLUMN declined_at BIGINT AFTER accepted_at', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'family_invitations'
    AND COLUMN_NAME = 'declined_at'
);
PREPARE add_family_invitations_declined_at_stmt FROM @add_family_invitations_declined_at;
EXECUTE add_family_invitations_declined_at_stmt;
DEALLOCATE PREPARE add_family_invitations_declined_at_stmt;

SET @add_family_invitations_delivery_status = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE family_invitations ADD COLUMN delivery_status VARCHAR(255) AFTER expires_at', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'family_invitations'
    AND COLUMN_NAME = 'delivery_status'
);
PREPARE add_family_invitations_delivery_status_stmt FROM @add_family_invitations_delivery_status;
EXECUTE add_family_invitations_delivery_status_stmt;
DEALLOCATE PREPARE add_family_invitations_delivery_status_stmt;

SET @add_family_invitations_delivery_message = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE family_invitations ADD COLUMN delivery_message VARCHAR(1024) AFTER delivery_status', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'family_invitations'
    AND COLUMN_NAME = 'delivery_message'
);
PREPARE add_family_invitations_delivery_message_stmt FROM @add_family_invitations_delivery_message;
EXECUTE add_family_invitations_delivery_message_stmt;
DEALLOCATE PREPARE add_family_invitations_delivery_message_stmt;

UPDATE family_invitations
SET delivery_status = COALESCE(delivery_status, 'not_configured'),
    delivery_message = COALESCE(delivery_message, '邀请已保存。短信邀请暂未接入，请让对方使用该手机号登录后接受邀请。')
WHERE status = 'pending';

SET @add_app_option_items_metadata_json = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE app_option_items ADD COLUMN metadata_json TEXT AFTER image_asset', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'app_option_items'
    AND COLUMN_NAME = 'metadata_json'
);
PREPARE add_app_option_items_metadata_json_stmt FROM @add_app_option_items_metadata_json;
EXECUTE add_app_option_items_metadata_json_stmt;
DEALLOCATE PREPARE add_app_option_items_metadata_json_stmt;

UPDATE app_option_items
SET metadata_json = '{"capabilities":["manage_family_members","manage_family_code","manage_devices","manage_privacy","manage_subscription","manage_rewards","manage_tasks","confirm_tasks","view_live_care","view_reports","view_points_rewards","manage_account_security"]}'
WHERE catalog_key = 'family_role' AND item_key = 'admin';

UPDATE app_option_items
SET metadata_json = '{"capabilities":["confirm_tasks","view_live_care","view_reports","view_points_rewards","manage_account_security"]}'
WHERE catalog_key = 'family_role' AND item_key = 'guardian';

UPDATE app_option_items
SET metadata_json = '{"capabilities":["view_basic_home","view_alerts","manage_account_security"]}'
WHERE catalog_key = 'family_role' AND item_key = 'viewer';
