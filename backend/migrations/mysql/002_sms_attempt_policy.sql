SET @add_attempt_count = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE sms_codes ADD COLUMN attempt_count INTEGER NOT NULL DEFAULT 0',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'sms_codes'
    AND COLUMN_NAME = 'attempt_count'
);
PREPARE add_attempt_count_stmt FROM @add_attempt_count;
EXECUTE add_attempt_count_stmt;
DEALLOCATE PREPARE add_attempt_count_stmt;

SET @add_last_sent_at = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE sms_codes ADD COLUMN last_sent_at BIGINT NOT NULL DEFAULT 0',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'sms_codes'
    AND COLUMN_NAME = 'last_sent_at'
);
PREPARE add_last_sent_at_stmt FROM @add_last_sent_at;
EXECUTE add_last_sent_at_stmt;
DEALLOCATE PREPARE add_last_sent_at_stmt;
