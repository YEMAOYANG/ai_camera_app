SET @add_point_accounts_stage_notice_handled_balance = (
  SELECT IF(COUNT(*) = 0, 'ALTER TABLE point_accounts ADD COLUMN stage_notice_handled_balance INTEGER NOT NULL DEFAULT 0 AFTER balance', 'SELECT 1')
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'point_accounts'
    AND COLUMN_NAME = 'stage_notice_handled_balance'
);
PREPARE add_point_accounts_stage_notice_handled_balance_stmt FROM @add_point_accounts_stage_notice_handled_balance;
EXECUTE add_point_accounts_stage_notice_handled_balance_stmt;
DEALLOCATE PREPARE add_point_accounts_stage_notice_handled_balance_stmt;
