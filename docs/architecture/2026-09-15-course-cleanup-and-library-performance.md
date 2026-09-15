# 旧课堂清理与课程列表性能

用户要求删除旧版《校园活动中的分数与百分数》，并明确删除该课堂的学习记录。同时排查课程列表接口缓慢，以及 3D 与小游戏的关系。

## 操作边界

- 旧课：`candidate_primary_6_math_91e56dc8caa0_catalog_gen_ddaa5bc7be54a293272cc3e_e09aad2c36fc`，版本 `0.0.0-candidate`，Stage `stage-p83SomVEUh`。
- 保留的新课：`candidate_primary_6_math_91e56dc8caa0_catalog_gen_ea873d206248a13de584960e263a14d02c8f`，Stage `stage-WmNYqudzYa`。
- 旧课从产品中删除，课程、发布项和 Runtime 使用已有退役字段；旧课的学习任务、会话、答案、报告、掌握记录和事件物理删除。生成、费用及发布审计保留，不改其他课程、家庭或账号。
- 清理使用精确标识、事务和前后行数核对；不保存答案或聊天的长期备份。

## 性能变更与接口合约

课程列表保留原鉴权、发布、资产和 Runtime 可用性谓词，返回格式不变，不加入跨请求缓存。预计涉及课程列表服务及 `student_learning_library_repository.py`、`learning_repository.py`、共享课程库存查询的执行方式。

真实旧数据的三次 `StudentLearningService.library` 只读基线耗时为 7.68–7.73 秒，共 20 条 SQL，测试未计入认证步骤。历史列表约 3.34 秒，继续学习项约 2.97 秒。复杂可用性查询反复对 LONGTEXT 型 `feature_manifest_json` 调用 JSON_EXTRACT 是主要成本。

同一事务、相同数据的单查询对照中，将 manifest 一次物化为 MySQL JSON 后，历史列表从 3366.5 毫秒降至约 20 毫秒，六行完整结果 SHA 相同。正式优化结果和验证记录以本次输出报告为准；旧课清理造成的数据量减少不得作为性能优化收益。

## 3D 与小游戏

新课有两个互动页：分数条模拟和 3D 分块塔。分块塔的类型为 game/puzzle，包含目标分数、调整、检查和重开，3D 模型与游戏被合并在同一页；并无另一个隐藏的小游戏页。

现有策略允许 3D 位于游戏内，也支持分开的 3D 和小游戏。不是每门课程都必须同时出现两者。用户本次追问了这种组合规则，未执行新的付费生成或覆盖已签名课堂。独立新增游戏页应走新的课件修订、音频继承审计和发布复核。

## 完成结果

旧课已按精确计划哈希执行退役，5个学习任务、3次会话、1份报告、1份掌握记录及相关事件、票据和绑定均已删除；6个旧课堂教学聊天目录（22个文件）也已删除，没有创建答案或聊天长期备份。新课堂、它的学习记录及生成/音频/费用审计保持不变。

优化最终落在 `formal_student_runtime_gate.py`、`student_learning_library_repository.py`、`learning_repository.py` 和 `course_supply_inventory.py`。54项相关测试通过。清理前同数据完整服务对照为7818.09毫秒与253.84/237.61毫秒，响应完全一致；最终未退役范围优化在清理后另做同快照对照为5275.57毫秒与247.61/233.94毫秒。两组数据量差异没有计入代码优化收益。详见 `output/student-library-performance-notes-20260915.md`。

Backend已托管重启，课程工作进程恢复；所有服务健康。实际学生页面只显示一门新课，旧课已完成记录也不再出现；列表API返回200。最终报告为 `output/course-cleanup-and-library-performance-20260915.json`。本轮未新增小游戏页或调用付费生成模型。
