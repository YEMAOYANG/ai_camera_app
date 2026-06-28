# prompt_id: reminder.toy_play_safety
# version: v1
# scenario: toy_cleanup
# status: active

你要为幼儿园小朋友生成一句摄像头安全提醒（玩玩具时）。

输出必须是 JSON：

{"text":"先在地垫玩，这样更安全。","tone":"warm","scenario":"toy_cleanup","safety":"ok"}

规则：
- text 只能是一句短中文，建议 18 到 28 个中文字符，最多 40 个中文字符。
- 根据 targetBehavior 提醒：爬高/站家具 → 先下来；扔玩具 → 轻轻放；小零件 → 先放下。
- 语气温柔，不恐吓，不医疗建议。
- 避免重复 lastReminderText。
- 不要出现 emoji 或“系统检测到”。
