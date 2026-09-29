# 学习结果汇入家长日报与周报

沿用 `GET /api/reports/daily`、`GET /api/reports/weekly`，在 `report` 增加可选的 `learning`，原任务、积分和看护字段保持兼容。后端按当前登录家庭关联孩子、课程、会话和报告，Flutter 原报告页直接展示，不新增页面或数据库表。

`learning` 使用 `mira.report.learning.v1`：`lessonCount`、`needsSupportCount`、`reviewCount`、`lessons`。每节包含课程和孩子、记录日期、状态、能力证据范围、首次练习独立题数及提示/家长帮助、本轮新情境结果、待巩固项目、建议和复习时间。普通课程不套用《天地人》的六项指标。

日期采用北京时间。日报取当天快照；周报对同一孩子同一版本课程取周期内最后快照，同一课的重复练习不重复计课。复习次数来自有时间记录的复习历史。

后端 `report_learning_summary.py` 聚合；`textbook_journey_service.py` 在原作答事务中把当日摘要写入会话 `textbookPlay.reportDays`，保存跨日的最后已知快照；`profile_service.py` 合并返回。读取报告不写数据库。旧数据只使用有证据的最后保存日、首次练习报告日期和完成复习日期；不伪造旧日日志，也不把最新进步回填到过去日报。

Flutter 增加报告模型和 `ReportLearningSection`，接入 `profile_pages.dart` 原日报/周报；首页摘要显示课程数量与需留意项，首页刷新同步两种报告。报告页重新进入和手动刷新都会重新读取，已有加载中的请求不重复中断。低年级图片支持的理解与独立识字、朗读、书写分开说明。
