-- Big-class school-readiness templates and middle/big differentiation.

INSERT INTO task_templates(
  id, template_key, title, subtitle, grade, age_group, schedule_type,
  day_type, tags_json, status, sort_order, created_at, updated_at
) VALUES
  (
    'kg-big-entry-items',
    'kg-big-entry-items',
    '入园物品准备',
    '核对明天要带的东西',
    'big',
    'kindergarten_big',
    'weekday',
    'school_day',
    '["school_day","morning","self_care","school_ready"]',
    'active',
    311,
    0,
    0
  ),
  (
    'kg-big-pre-writing',
    'kg-big-pre-writing',
    '小手准备',
    '画线条涂色，不要求写字',
    'big',
    'kindergarten_big',
    'weekly',
    'weekend',
    '["weekend","reading","school_ready"]',
    'active',
    312,
    0,
    0
  ),
  (
    'kg-big-time-task',
    'kg-big-time-task',
    '时间小任务',
    '认识时间，限时完成小事',
    'big',
    'kindergarten_big',
    'daily',
    'school_day',
    '["school_day","self_care","school_ready","rules"]',
    'active',
    313,
    0,
    0
  )
ON DUPLICATE KEY UPDATE
  title = VALUES(title),
  subtitle = VALUES(subtitle),
  grade = VALUES(grade),
  age_group = VALUES(age_group),
  schedule_type = VALUES(schedule_type),
  day_type = VALUES(day_type),
  tags_json = VALUES(tags_json),
  status = VALUES(status),
  sort_order = VALUES(sort_order),
  updated_at = VALUES(updated_at);

INSERT INTO task_template_items(
  id, template_id, start_time, end_time, task_type, title,
  reward_points, requires_parent_confirmation, sort_order, created_at, updated_at
) VALUES
  ('kg-big-entry-items-1', 'kg-big-entry-items', '19:30', '19:40', 'housework', '核对水杯和备用衣物', 1, 1, 1, 0, 0),
  ('kg-big-entry-items-2', 'kg-big-entry-items', '19:40', '19:50', 'housework', '把老师通知放固定位置', 1, 1, 2, 0, 0),
  ('kg-big-entry-items-3', 'kg-big-entry-items', '19:50', '20:00', 'custom', '说说明天要带什么', 0, 0, 3, 0, 0),
  ('kg-big-pre-writing-1', 'kg-big-pre-writing', '15:00', '15:10', 'reading_interest', '握笔画线条或涂色', 1, 0, 1, 0, 0),
  ('kg-big-pre-writing-2', 'kg-big-pre-writing', '15:10', '15:20', 'housework', '收拾蜡笔归位', 1, 0, 2, 0, 0),
  ('kg-big-pre-writing-3', 'kg-big-pre-writing', '15:20', '15:30', 'custom', '给作品取个名字', 0, 0, 3, 0, 0),
  ('kg-big-time-task-1', 'kg-big-time-task', '16:30', '16:40', 'custom', '看钟说现在几点', 0, 0, 1, 0, 0),
  ('kg-big-time-task-2', 'kg-big-time-task', '16:40', '16:55', 'housework', '限时整理一项物品', 1, 0, 2, 0, 0),
  ('kg-big-time-task-3', 'kg-big-time-task', '16:55', '17:05', 'custom', '完成后告诉家长', 0, 0, 3, 0, 0)
ON DUPLICATE KEY UPDATE
  template_id = VALUES(template_id),
  start_time = VALUES(start_time),
  end_time = VALUES(end_time),
  task_type = VALUES(task_type),
  title = VALUES(title),
  reward_points = VALUES(reward_points),
  requires_parent_confirmation = VALUES(requires_parent_confirmation),
  sort_order = VALUES(sort_order),
  updated_at = VALUES(updated_at);

UPDATE task_templates
SET
  subtitle = '为上小学做生活准备',
  tags_json = '["school_day","self_care","rules","cleanup","school_ready"]',
  updated_at = 0
WHERE template_key = 'kg-big-life-prep';

UPDATE task_templates
SET
  subtitle = '承担更多家里的小责任',
  updated_at = 0
WHERE template_key = 'kg-big-family-helper';

UPDATE task_template_items
SET
  title = '餐后擦自己的桌面',
  task_type = 'housework',
  requires_parent_confirmation = 0,
  updated_at = 0
WHERE id = 'kg-big-family-helper-1';

UPDATE task_template_items
SET
  title = '整理自己的抽屉或书架',
  task_type = 'housework',
  requires_parent_confirmation = 1,
  updated_at = 0
WHERE id = 'kg-big-family-helper-2';

UPDATE task_template_items
SET
  title = '完成后告诉家人',
  task_type = 'custom',
  updated_at = 0
WHERE id = 'kg-big-family-helper-3';
