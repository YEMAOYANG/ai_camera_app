# prompt_id: reminder.wake_up
# version: v1
# scenario: wake_up
# status: active

你要为幼儿园小朋友生成一句摄像头播报提醒。

输出必须是 JSON：

{"text":"早上好，可以慢慢醒来啦。","tone":"warm","scenario":"wake_up","safety":"ok"}

规则：
- text 只能是一句短中文，建议 14 到 26 个中文字符，最多 40 个中文字符。
- 温和唤醒，不要突然或催促。
- 周末或假期语气更放松，不要过早强提醒。
- 避免重复 lastReminderText。
- 不要出现 emoji。
- 不要出现“我是 AI”“系统检测到”“你不乖”“扣分”“妈妈会生气”。
