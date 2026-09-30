# 自主学习与家长减负优化

沿用 Student Web → OpenMAIC 原生课堂 → Python 学习会话、tasks、reports → Flutter 家长端。保留已有课程、成绩、教材选择、权限与媒体发布门槛，不创建新的今日计划域，不迁移数据库。

改动范围：学生书包与教材目录、OpenMAIC 原生课堂的默认布局/声音/活动、后端教学配置与学习摘要、Flutter 报告。

接口兼容新增：

- 教材目录返回可直接进入的课程建议，前提仍是家长已选教材和后端课程可见性检查。
- 学习摘要增加 `parentSupport`，包含一个具体动作、交回孩子的提示和预计帮助时长；预计时长不当作实际时长。
- `GET /api/reports/learning/{sessionId}/coaching?recordDate=YYYY-MM-DD` 读取辅导记录。
- `PUT /api/reports/learning/{sessionId}/coaching` 接收 `{recordDate, minutes, usualMinutes, reason, revision}`。分钟是家长自报的 0–180 整数；以往用时可不填。原因可为 `none/navigation/understanding/technical/company/other`。同一会话/日期只保留一条版本化记录；重复相同请求幂等，冲突后先读取。
- 服务端检查家庭范围、日期对应的实际学习证据和 `manage_tasks` 权限；读取需要 `view_reports`。存放在既有会话 JSON 的 `parentCoaching` 中，不修改孩子的首次答案、评估或历史学习快照。
- 日周报告返回 `coachingSummary` 及每节课的可编辑记录。缺失记录不是零分钟；只对成对填写的同课记录比较，以往与本次差值可能为负。自报比较不能宣称因果效果。

OpenMAIC 源码修改登记为 `0134-mira-independent-picture-classroom.patch`，更新补丁清单哈希并通过反向应用检查。仅图片活动课堂默认收起侧栏与完整工具，保留原生对话和输入；学生布局不写入运营端偏好。小屏侧栏覆盖显示，不挤压主课件。

导航音频使用 `learning_navigation.v1.json` 中 18 条原创短句、Qwen3 TTS Flash / Serena，保存不可变清单与音频哈希；学生端和原生课堂分别从自己的已验证媒体路径读取，不回退系统朗读。浏览器拦截自动播放时提供可点击重听。

`textbook_journey_registry.py` 按已发布课程哈希加载独立教学定义。目标数、迁移题、练习题图片、音频包、进度分母和报告分母均从本课定义读取；缺失定义或题目与图片不一致拒绝进入。首个通用模板使用图片选项，不复制《天地人》的目标到其他课名。

本轮只新增后四课的范围核验与原创活动草案，没有生成或发布这些课程。新课沿用真实生成、语音、内容审核与发布流程；缺少原创素材清单在模型调用前拒绝，预览、目录和素材就绪均不等于发布完成。

运行检查另外修复两个直接影响可用性的问题：3D 书包画布随异步页面内容重新定位；本地 OpenMAIC 与网关通过独立进程组后台启动，继续使用原有身份和健康校验。未改数据库结构、真实成绩或自动生成开关。

验证与课程供给状态见 `docs/reviews/2026-09-29-independent-learning-acceptance.md`。
