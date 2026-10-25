SET @column_exists := (
  SELECT COUNT(*)
  FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'sleep_time'
);

SET @sql := IF(
  @column_exists = 0,
  'ALTER TABLE children ADD COLUMN sleep_time VARCHAR(255) AFTER birthday',
  'SELECT 1'
);
PREPARE stmt FROM @sql;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;
