# 已审核课堂的音频续接

本次对象为六年级数学《校园活动中的分数与百分数》，Stage `stage-WmNYqudzYa`，原 Native job `omformal_3b6ae9c7b6e8f13472a10d04`。视觉及教学审核已通过，22 段 TTS/ASR 已完成，第 23 段于 2026-09-14 10:45:41 超时且结果未知，后 13 段未派发。

用户于当前任务明确要求继续完成。恢复只处理同一冻结课堂的音频，保留原草稿、讨论修复、审核及费用证据。

## 恢复入口

- `inspect-learner-discussion-audio-tail` 验证原复审 claim、派生课件、质量缓存、完整教师配置、成功音频及失败/未派发边界；不创建执行 claim，不调用 Provider。
- `complete-learner-discussion-audio-tail` 创建单独且不可重复的 claim，在已验证的原 completion namespace 内调用现有 `.repair1` 修复第 23 段，再由原音频生命周期完成后 13 段。
- 原 22 段按固定请求身份复用。源课件和派生课件的质量检查均仅使用已保存缓存。缺失、篡改或不匹配的凭证直接拒绝，不回退到重新生成。
- 第 23 段的原未知费用和原失败证据继续保留；物理修复生成独立请求与 promotion 审计。异常记录到独立 audio-tail failure 文件。

Native 改动作为 `0105-mira-reviewed-learner-audio-tail.patch` 保存，另有 Python 操作包装器 `output/run-primary6-saved-stage.py`。学生端 API、题目、旁白文字和原课堂业务身份未改变。

## 原收尾授权续期

`backend/scripts/renew_saved_stage_tail.py` 提供只读 `plan` 和按精确计划 SHA 执行的 `apply`。它仅延长同一收尾授权的到期时间，追加一次审计，保持其 scope、价格、限额、策略、授权 ID 和所有已终结账目不变。最初已过期的父授权完全不改。

每次调用前，后端检查原授权凭据和续期审计，并确认原有 settled/unknown/released 记录仍完全一致。Native 同时绑定旧 claim 的原 sidecar 和后端验证过的新 sidecar，只允许 `expiresAt` 不同。

本次已应用的续期计划为 `output/primary6-playful-tail-renewal-plan-20260914.json`，有效期延至 12:52:44 +08；该授权操作不调用 Provider。

## 验证与执行证据

- 后端续期及预算重点测试 34 项通过；讨论修复和趣味课审核兼容测试 16 项通过。
- Native 音频、授权、讨论修复及 claim 相关测试 115 项通过。
- 真实课堂预检返回 `audio_tail_preflight_passed`，`providerCalls: 0`，`claimCreated: false`。
- 原音频文件指纹保存在 `output/primary6-audio-tail-baseline-20260914/audio-before.json`。
- 真实执行日志：`output/primary6-playful-audio-tail-execution-20260914.log`。

上述实现和预检不代表课程已经发布。必须取得最终 completion、导入全部 36 段音频、检查真实课堂，再以该最终 manifest 对应的视觉确认执行现有发布流程。最终执行状态以本次输出报告及数据库发布记录为准。

## 本次真实续接结果

2026-09-14 续接已成功退出，最终 completion receipt 为 `361c151d78b2a66a85e700f9734388a16ad34b4f75ffd47a920fc2e534009bc5`。36 段 TTS 和 36 段 ASR 全部成功，原 44 个成功记录文件逐字节保持不变。本轮恰好 14 次 TTS 和 14 次 ASR，均已结算，无额外质量模型调用；原未知费用仍保留。真实 payload、讨论审计、音频 schema 和全部请求哈希通过后端严格校验，原 Runtime 已通过正常 reconciliation 转为 ready。

实际浏览器检查了最终课堂、3D 分数游戏的错误/重试/正确反馈，以及独立挑战的题干和选项。最终视觉确认绑定 `e8dbe7be4020f576d6a6d5f79e33feb6aea9ab64913be1cf99ce57bed067c28d` manifest 和 `c02b56035e916055567988a87a3af19b769fad95fd64d2ae5578d388d07be499` visual receipt。发布收尾沿现有课程库入口进行，学生 API 合约不变。

## 发布租约恢复

实际发布首轮被 `formal validation publisher lease is stale` 拒绝。根因为协调任务从 `retry_wait` 恢复时保留原生成截止时间，`claim_next` 将租约上限截到已过期的时间。`generate_one_library_course.py` 现仅在已审核的指定保存课堂执行 publication 且新取得的 lease 已过期时，调用仓库既有 `renew_saved_classroom_publication_lease`。其原有 owner、token、Runtime、无 Provider 绑定和十分钟上限检查保持不变；生成和复审入口不续租。旧、新截止时间输出到发布日志，数据库保留既有恢复事件。8 项 operator 测试覆盖正常租约、过期恢复、绑定拒绝及复审不续租。

## 发布与运行版本

正式发布重试已成功，日志 `output/primary6-playful-final-publication-resumed-20260914.log` 记录了严格续租及 `published`。最终数据库审计 `output/primary6-playful-final-db-audit-20260914.json` 确认此课程和 release item 已发布、36 段媒体就绪，发布阶段没有新增 Provider 调用。整批年级 release 仍为渐进发布状态，本结论仅针对这一节课。

包含全部 105 个补丁的托管生产构建成功，BUILD_ID 为 `HSfpnDBDOhuR2k3DkIJIz`，TypeScript 构建检查通过。全部源码与105补丁重建结果一致，没有未打包源码改动。

托管全栈重启已完成，Backend、Student Web、OpenMAIC、Gateway 均为 managed/healthy，curriculum worker 正常运行。学生端实际进入新任务 `task_9fc4866ce5914cfda6dabf1d28024cb5`，嵌入的课堂确认为原 Stage。相同学生课堂的真实 UI 点击后进入播放，旁白依次推进并可暂停；未提交测验。最终证据见 `output/primary6-playful-final-validation-20260914.json`。
