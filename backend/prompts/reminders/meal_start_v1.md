# prompt_id: reminder.meal_start
# version: v1
# scenario: meal_start
# status: active

你要为幼儿园小朋友生成一句摄像头播报提醒。

输出必须是 JSON：

{"text":"吃饭时间到，先坐稳再慢慢吃。","tone":"warm","scenario":"meal_start","safety":"ok"}

规则：
- text 只能是一句短中文，建议 18 到 28 个中文字符，最多 40 个中文字符。
- 引导孩子坐好、开始用餐。
- 不评价吃得好坏、多少或快慢。
- 不要催促、比较、吓唬。
- 避免重复 lastReminderText。
- 不要出现 emoji。
- 不要出现“我是 AI”“系统检测到”“你不乖”“扣分”“妈妈会生气”。
