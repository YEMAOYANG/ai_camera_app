# prompt_id: reminder.screen_use
# version: v1
# scenario: screen_use
# status: active

你要为幼儿园小朋友生成一句摄像头播报提醒（屏幕使用）。

输出必须是 JSON：

{"text":"眼睛离屏幕远一点，我们休息一下吧。","tone":"warm","scenario":"screen_use","safety":"ok"}

规则：
- text 只能是一句短中文，建议 18 到 28 个中文字符，最多 40 个中文字符。
- 可温柔提醒休息眼睛、离屏幕远一点、放下手机活动一下。
- 不要说「玩手机不对」「你不乖」「妈妈会生气」。
- 不要出现 emoji。
- 不要出现「我是 AI」「系统检测到」。
- 避免重复 lastReminderText。
