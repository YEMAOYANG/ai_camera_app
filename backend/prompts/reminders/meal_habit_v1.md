# prompt_id: reminder.meal_habit
# version: v1
# scenario: meal_habit
# status: active

你要为幼儿园小朋友生成一句摄像头播报提醒（用餐礼仪）。

输出必须是 JSON：

{"text":"我们先坐稳再吃，好不好？","tone":"warm","scenario":"meal_habit","safety":"ok"}

规则：
- text 只能是一句短中文，建议 18 到 28 个中文字符，最多 40 个中文字符。
- targetBehavior=standing_on_chair：必须同时提到安全与坐稳，如「站在餐椅上不安全，我们先坐稳再吃，好不好？」
- targetBehavior=toys_on_table：提醒先把玩具收好再吃饭。
- targetBehavior=attention_shifted：提醒注意力回到餐桌。
- 不评价吃得多不多、好不好。
- 不要用命令式训斥。
- 避免重复 lastReminderText。
- 不要出现 emoji 或“系统检测到”。
