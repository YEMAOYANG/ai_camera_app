INSERT INTO app_option_items(
  catalog_key, item_key, parent_key, label, description, image_asset,
  sort_order, enabled, updated_at, metadata_json
) VALUES
  (
    'point_reward_unit',
    'points',
    NULL,
    '积分',
    '通用分值，适合偏任务化的家庭激励。',
    'assets/images/points/unit-points.png',
    10,
    1,
    0,
    '{"suffix":"分"}'
  ),
  (
    'point_reward_unit',
    'flower',
    NULL,
    '小红花',
    '默认方案，适合低龄儿童和日常正向反馈。',
    'assets/images/points/unit-flower.png',
    20,
    1,
    0,
    '{"suffix":"朵小红花"}'
  ),
  (
    'point_reward_unit',
    'star',
    NULL,
    '小星星',
    '更轻量的阶段激励，适合兴趣任务和成长记录。',
    'assets/images/points/unit-star.png',
    30,
    1,
    0,
    '{"suffix":"颗小星星"}'
  )
ON DUPLICATE KEY UPDATE
  label = VALUES(label),
  description = VALUES(description),
  image_asset = VALUES(image_asset),
  sort_order = VALUES(sort_order),
  enabled = VALUES(enabled),
  metadata_json = VALUES(metadata_json);

INSERT IGNORE INTO app_settings(family_id, setting_key, value, updated_at)
SELECT
  id,
  'points-rewards',
  '{"stageThreshold":10,"unit":"flower"}',
  CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED)
FROM families;
