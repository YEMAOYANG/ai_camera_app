UPDATE task_templates
SET title = CASE template_key
  WHEN 'kg-small-school-morning' THEN '上学日晨间'
  WHEN 'kg-small-school-entry-calm' THEN '入园前安心'
  WHEN 'kg-small-after-school-buffer' THEN '放学后缓冲'
  WHEN 'kg-small-dinner-slow' THEN '晚餐慢慢吃'
  WHEN 'kg-small-nap-rhythm' THEN '午睡前后'
  WHEN 'kg-small-bedtime-light' THEN '睡前轻节奏'
  WHEN 'kg-small-toy-home' THEN '玩具回位'
  WHEN 'kg-small-weekend-outdoor' THEN '周末上午户外'
  WHEN 'kg-small-weekend-reading' THEN '亲子绘本'
  WHEN 'kg-small-emotion-calm' THEN '情绪安抚'
  WHEN 'kg-middle-school-morning' THEN '晨间自理'
  WHEN 'kg-middle-after-school-talk' THEN '放学后表达'
  WHEN 'kg-middle-meal-before-after' THEN '餐前餐后'
  WHEN 'kg-middle-toy-sort' THEN '玩具分类收纳'
  WHEN 'kg-middle-bedtime-ready' THEN '睡前准备'
  WHEN 'kg-middle-weekend-outdoor' THEN '周末户外'
  WHEN 'kg-middle-family-helper' THEN '家庭小帮手'
  WHEN 'kg-middle-rules-turns' THEN '规则与轮流'
  WHEN 'kg-middle-emotion-words' THEN '情绪表达'
  WHEN 'kg-middle-weekend-reading' THEN '亲子阅读'
  WHEN 'kg-big-school-ready' THEN '晨间自主准备'
  WHEN 'kg-big-after-school-review' THEN '放学后复盘'
  WHEN 'kg-big-table-duty' THEN '餐桌小责任'
  WHEN 'kg-big-bedtime-self' THEN '睡前自主'
  WHEN 'kg-big-weekend-outdoor' THEN '周末户外'
  WHEN 'kg-big-weekend-reading' THEN '亲子阅读'
  WHEN 'kg-big-family-helper' THEN '家庭小帮手'
  WHEN 'kg-big-own-things' THEN '整理自己的物品'
  WHEN 'kg-big-life-prep' THEN '生活准备'
  WHEN 'kg-big-safety-rules' THEN '安全与规则'
  ELSE title
END,
updated_at = 0
WHERE template_key IN (
  'kg-small-school-morning',
  'kg-small-school-entry-calm',
  'kg-small-after-school-buffer',
  'kg-small-dinner-slow',
  'kg-small-nap-rhythm',
  'kg-small-bedtime-light',
  'kg-small-toy-home',
  'kg-small-weekend-outdoor',
  'kg-small-weekend-reading',
  'kg-small-emotion-calm',
  'kg-middle-school-morning',
  'kg-middle-after-school-talk',
  'kg-middle-meal-before-after',
  'kg-middle-toy-sort',
  'kg-middle-bedtime-ready',
  'kg-middle-weekend-outdoor',
  'kg-middle-family-helper',
  'kg-middle-rules-turns',
  'kg-middle-emotion-words',
  'kg-middle-weekend-reading',
  'kg-big-school-ready',
  'kg-big-after-school-review',
  'kg-big-table-duty',
  'kg-big-bedtime-self',
  'kg-big-weekend-outdoor',
  'kg-big-weekend-reading',
  'kg-big-family-helper',
  'kg-big-own-things',
  'kg-big-life-prep',
  'kg-big-safety-rules'
);
