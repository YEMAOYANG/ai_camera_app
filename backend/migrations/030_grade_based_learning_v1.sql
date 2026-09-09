SET @add_children_grade_code = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE children ADD COLUMN grade_code VARCHAR(64) AFTER grade',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'grade_code'
);
PREPARE add_children_grade_code_stmt FROM @add_children_grade_code;
EXECUTE add_children_grade_code_stmt;
DEALLOCATE PREPARE add_children_grade_code_stmt;

SET @add_children_grade_school_year_start = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE children ADD COLUMN grade_school_year_start INTEGER AFTER grade_code',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'grade_school_year_start'
);
PREPARE add_children_grade_school_year_start_stmt FROM @add_children_grade_school_year_start;
EXECUTE add_children_grade_school_year_start_stmt;
DEALLOCATE PREPARE add_children_grade_school_year_start_stmt;

SET @add_children_grade_confirmed_at = (
  SELECT IF(
    COUNT(*) = 0,
    'ALTER TABLE children ADD COLUMN grade_confirmed_at BIGINT AFTER grade_school_year_start',
    'SELECT 1'
  )
  FROM INFORMATION_SCHEMA.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE()
    AND TABLE_NAME = 'children'
    AND COLUMN_NAME = 'grade_confirmed_at'
);
PREPARE add_children_grade_confirmed_at_stmt FROM @add_children_grade_confirmed_at;
EXECUTE add_children_grade_confirmed_at_stmt;
DEALLOCATE PREPARE add_children_grade_confirmed_at_stmt;

UPDATE children
SET grade_code = CASE
  WHEN TRIM(COALESCE(grade, '')) IN (
    'kindergarten_small', 'small', '小班', '新小班', '幼儿园小班', '幼儿园 小班'
  ) THEN 'kindergarten_small'
  WHEN TRIM(COALESCE(grade, '')) IN (
    'kindergarten_middle', 'middle', '中班', '新中班', '幼儿园中班', '幼儿园 中班'
  ) THEN 'kindergarten_middle'
  WHEN TRIM(COALESCE(grade, '')) IN (
    'kindergarten_big', 'big', '大班', '新大班', '幼儿园大班', '幼儿园 大班'
  ) THEN 'kindergarten_big'
  WHEN TRIM(COALESCE(grade, '')) IN ('primary_1', '一年级', '新一年级', '小学一年级', '小学 一年级') THEN 'primary_1'
  WHEN TRIM(COALESCE(grade, '')) IN ('primary_2', '二年级', '新二年级', '小学二年级', '小学 二年级') THEN 'primary_2'
  WHEN TRIM(COALESCE(grade, '')) IN ('primary_3', '三年级', '新三年级', '小学三年级', '小学 三年级') THEN 'primary_3'
  WHEN TRIM(COALESCE(grade, '')) IN ('primary_4', '四年级', '新四年级', '小学四年级', '小学 四年级') THEN 'primary_4'
  WHEN TRIM(COALESCE(grade, '')) IN ('primary_5', '五年级', '新五年级', '小学五年级', '小学 五年级') THEN 'primary_5'
  WHEN TRIM(COALESCE(grade, '')) IN ('primary_6', '六年级', '新六年级', '小学六年级', '小学 六年级') THEN 'primary_6'
  WHEN TRIM(COALESCE(age_stage, '')) IN (
    'kindergarten_small', '小班', '幼儿园小班', '幼儿园 小班'
  ) THEN 'kindergarten_small'
  WHEN TRIM(COALESCE(age_stage, '')) IN (
    'kindergarten_middle', '中班', '幼儿园中班', '幼儿园 中班'
  ) THEN 'kindergarten_middle'
  WHEN TRIM(COALESCE(age_stage, '')) IN (
    'kindergarten_big', '大班', '幼儿园大班', '幼儿园 大班'
  ) THEN 'kindergarten_big'
  WHEN TRIM(COALESCE(age_stage, '')) IN ('primary_1', '一年级', '小学一年级', '小学 一年级') THEN 'primary_1'
  WHEN TRIM(COALESCE(age_stage, '')) IN ('primary_2', '二年级', '小学二年级', '小学 二年级') THEN 'primary_2'
  WHEN TRIM(COALESCE(age_stage, '')) IN ('primary_3', '三年级', '小学三年级', '小学 三年级') THEN 'primary_3'
  WHEN TRIM(COALESCE(age_stage, '')) IN ('primary_4', '四年级', '小学四年级', '小学 四年级') THEN 'primary_4'
  WHEN TRIM(COALESCE(age_stage, '')) IN ('primary_5', '五年级', '小学五年级', '小学 五年级') THEN 'primary_5'
  WHEN TRIM(COALESCE(age_stage, '')) IN ('primary_6', '六年级', '小学六年级', '小学 六年级') THEN 'primary_6'
  ELSE grade_code
END
WHERE grade_code IS NULL OR TRIM(grade_code) = '';
