-- Teacher profile versions are immutable because preferences and generated
-- media retain their original profile/version foreign keys.  Version 1 stays
-- byte-for-byte unchanged and version 2 is the current registry snapshot with
-- the canonical VoxCPM2 model identifier.
INSERT INTO learning_teacher_profiles(
  id, version, display_name, avatar_path, subject, language_code,
  teaching_style, provider_id, provider_model, voice_mode, voice_prompt,
  capabilities_json, clone_allowed, status, content_hash, published_at,
  created_at, updated_at
)
VALUES
  (
    'mira_chinese_gentle', 2, '小语老师',
    '/teachers/mi-chinese-v1.png', 'chinese', 'zh-CN', 'gentle_guided',
    'voxcpm2', 'openbmb/VoxCPM2', 'prompt',
    '温柔、耐心、亲切的中文小学老师声音，普通话标准，语速稍慢，吐字清楚，鼓励而不过度夸张',
    '["explain_then_practice","guided_reading","standard_mandarin","pinyin_review_gated"]',
    0, 'active',
    'a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8',
    CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED),
    CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED),
    CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED)
  ),
  (
    'mira_math_clear', 2, '小数老师',
    '/teachers/ashu-math-v1.png', 'math', 'zh-CN', 'clear_structured',
    'voxcpm2', 'openbmb/VoxCPM2', 'prompt',
    '清晰、沉稳、逻辑分明的中文小学数学老师声音，普通话标准，语速适中，步骤之间停顿明确，语气温和',
    '["worked_examples","step_by_step_reasoning","standard_mandarin"]',
    0, 'active',
    '4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb',
    CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED),
    CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED),
    CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED)
  ),
  (
    'mira_english_standard', 2, 'Mia 老师',
    '/teachers/coco-english-v1.png', 'english', 'en-US',
    'standard_pronunciation', 'voxcpm2', 'openbmb/VoxCPM2', 'prompt',
    'standard child-friendly English teacher voice, neutral American English pronunciation, slow clear articulation, warm and encouraging',
    '["listen_and_repeat","phonics","standard_english_pronunciation","pronunciation_review_gated"]',
    0, 'active',
    '4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040',
    CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED),
    CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED),
    CAST(UNIX_TIMESTAMP(CURRENT_TIMESTAMP(3)) * 1000 AS UNSIGNED)
  );
