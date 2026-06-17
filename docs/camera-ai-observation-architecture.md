# Camera AI Observation Architecture

## 0. V1 幼儿园版本边界

当前版本只做幼儿园小朋友版本，主线目标是让家长快速进入 App，完成孩子资料、设备连接/绑定、摄像头基础看护、幼儿园阶段作息/任务/提醒，以及积分、奖励、兑换的基础家长端闭环。

本版本包含：

- 简化首次设置流程、家长身份、孩子资料。
- 设备连接/绑定和未来自研摄像头硬件边界。
- 摄像头基础看护能力、作息时间窗、提醒话术和策略骨架。
- 幼儿园阶段任务、作息、提醒。
- 摄像头 AI 行为观察合同。
- 积分、奖励、兑换的基础家长端闭环。

本版本不做完整闭环：

- 全年龄段复杂任务体系。
- 复杂安全告警闭环和安全区域。
- 真实硬件 OTA 执行。
- 孩子端 App 和孩子端兑换申请完整 UI。
- 复杂成长报告后台、复杂 AI 评测后台 UI。
- 支付、库存、物流、订单履约。

需要预留边界：

- 未来自研摄像头硬件。
- 未来 OTA。
- 未来真实短信供应商。
- 未来告警模块。
- 未来 AI eval / prompt registry。
- 未来孩子端。

## 1. 当前代码能力评估

当前版本已经具备三段基础链路：

- 任务提醒链路：Flutter 任务详情调用 `/api/tasks/<task_id>/reminder`，后端 `TaskService.send_reminder` 通过 `task_reminder_policy.build_task_reminder` 生成任务提醒，再由 `CameraCommandService.internal_speak` 交给 `CameraBridgeService` 和 camera runtime adapter。
- 任务运行链路：`TaskSchedulerRunner` 调用 `TaskRuntimeService.tick`，根据任务时间窗自动开始、延迟、结束任务，并在部分任务类型上调用 `CameraBridgeService.task_observation`。
- 摄像头运行链路：`CameraBridgeService` 将 health、runtime、snapshot、stream、speaker、monitor、task_observation 隐藏在 adapter 后面，当前可接 `disabled`、`mock`、`ai_camera_test`。

当前不足：

- 观察对象仍围绕任务开始/延迟，不是幼儿园看护场景。
- `task_observation` 更像任务状态辅助判断，没有独立的 behavior signal、behavior state、routine window、care policy。
- 现有 task reminder prompt 只服务任务提醒，不要求 JSON，也没有摄像头看护提醒的 prompt registry。
- camera command log 能记录播报命令，但缺少 reminder decision、prompt version、fallback、cooldown、parent review 的独立审计链。
- 旧 `/Users/sqcopenclaw/.openclaw/workspace/ai_camera_test` 可以作为开发 adapter，但不能让 Flutter 触碰 RTSP、go2rtc、旧 worker 或私有协议。

本轮不改现有 `backend/prompts/task/reminder_text.v1.md`。它继续只服务任务提醒。

## 2. 摄像头 AI 观察闭环

目标链路：

```text
camera frame / short clip
  -> vision observation
  -> behavior signal
  -> behavior state engine
  -> care policy engine
  -> AI reminder text generator
  -> camera speaker command
  -> reminder / observation event log
  -> parent app summary
```

阶段 1 只落底层合同：

- 接收内部观察事件。
- 记录原始观察、行为信号、策略决策、提醒事件和家长复核事件。
- 暴露家长 App 可读的能力配置、作息窗口、summary、提醒记录合同。
- 新增摄像头看护提醒 prompt 和 JSON 校验/fallback 机制。

阶段 1 不做：

- 真实视觉模型接入。
- 旧 RTSP monitor worker 改造。
- 完整状态机和播报策略。
- Flutter 首页/设置页大改。

## 3. V1 幼儿园默认能力

默认能力保持保守，不承诺 100% 准确，不做医疗诊断、情绪诊断或完整告警闭环。

能力：

- 坐姿检测：连续观察到贴近或歪靠后，轻提醒或记录。
- 玩具收纳：观察玩具散落、孩子收纳、收纳未完成。
- 用餐开始与用餐习惯：观察入座、开始用餐、频繁离桌、边吃边玩。
- 午睡：观察是否上床、仍然活跃、安静状态。
- 晚间入睡：观察睡前活跃、离床、安静入睡准备。
- 起床：观察起床或仍未起床，周末更克制。
- 转场提醒：准备出门、睡前准备、收纳后去洗漱等。

每个能力需要：

- enabled，默认开启。
- dayType：`school_day`、`weekend`、`holiday`、`custom`。
- time windows。
- min observation seconds，避免一帧误判。
- observation threshold，低于阈值只记录。
- cooldown seconds。
- daily limit。
- parent notify threshold。
- allow speaker。
- record only。
- prompt id/version。
- fallback templates。

## 4. V1 只预留能力

以下只保留模型和接口边界，不在阶段 1 实现：

- 真实视觉模型调用和短视频片段分析。
- 多模型融合和模型版本评估。
- 家长可视化证据截图管理。
- 多设备协同选择播报设备。
- 节假日自动日历接入。
- OTA、硬件协议、私有摄像头协议。
- 完整告警闭环。

## 5. 后端模型设计

核心概念：

- `care_scenario`：看护场景，如 `toy_cleanup`、`posture`、`meal_start`。
- `care_capability_config`：孩子/设备维度的能力配置。
- `care_routine_window`：上学日、周末、假期、自定义的看护作息时间窗。
- `camera_observation_event`：一次来自设备或 adapter 的观察事实。
- `behavior_signal`：从观察中抽出的结构化信号。
- `current_behavior_state`：连续观察后的当前状态，如 `toys_scattered`、`posture_recovered`。这是当前状态表，不保存完整历史；历史来自 `camera_observation_events` 和 `behavior_signals`。
- `reminder_decision`：是否提醒、是否播报、是否通知家长、原因和策略快照。
- `reminder_event`：提醒文本、来源、prompt version、fallback、投递状态。
- `review_item`：需要家长处理或确认的事项，care 只是一个 domain，未来可承载 task、reward、alert。
- `audit_event`：审计日志，阶段 1.5 先用于 internal API 调用审计。

阶段 1 的数据存储只建表和索引，不迁移旧任务数据。

### 数据源边界

- 摄像头能力开关、阈值、冷却、daily limit、allow speaker、record only、prompt id 的唯一来源是 `care_capability_configs`。
- `app_settings` 只保存全局偏好，例如提醒语气、隐私授权、通知偏好；不得镜像单个看护能力配置，避免双写。
- 作息观察时间窗的唯一来源是 `care_routine_windows`。
- `care_routine_windows` 不是任务，不产生任务完成状态、积分、奖励或家长确认。
- 原始摄像头观察事实记录在 `camera_observation_events`。
- 当前行为状态记录在 `current_behavior_states`。
- AI/策略决策记录在 `reminder_decisions`。
- 最终提醒文案记录在 `reminder_events`。
- 真实摄像头播报命令记录在现有 `camera_commands`。
- 家长待处理事项记录在 `review_items`。

### 任务、提醒、摄像头命令边界

- `task_events`：任务生命周期事件，例如开始、完成、确认、奖励，不记录摄像头看护话术。
- `reminder_events`：看护提醒文本、event source、是否测试、prompt version、fallback 和 delivery status，不代表设备已执行。
- `camera_commands`：真实下发到摄像头 runtime 的命令和执行结果，后续由 `reminder_events.command_id` 关联。

## 5.1 CarePolicyEngine 阶段 2A / 2A.5 / 2C 策略

阶段 2A 已将临时 `stage_1_contract` 决策替换为 `CarePolicyEngine`。阶段 2A.5 补齐连续观察累积、internal observation 默认能力初始化、parent notify 优先级。阶段 2C 增加作息窗口 gate 和信号语义 gate。策略引擎只做决策，不生成话术、不下发摄像头命令、不调用真实视觉模型。

输入：

- familyId、childId、deviceId、scenario。
- observation event。
- behavior signals。
- capability config。
- current behavior state。
- recent real reminder events。
- recent allowed decisions。
- routine windows。
- dayType，可选；缺省时按观察时间所在本地星期推断 school_day/weekend。
- now。

输出：

- decision。
- reason。
- shouldSpeak。
- shouldNotifyParent。
- cooldownUntil。
- reminderLevel。
- policySnapshotJson。
- 是否需要创建 review item。

决策顺序：

1. capability 不存在或 disabled：`skipped_disabled`。
2. `record_only=true`：`record_only`。
3. observation score 低于 `confidence_threshold`：`skipped_low_confidence`。
4. 正向、恢复、已开始执行的 signal：`record_only`。
5. 连续观察时长低于 `min_observation_seconds`：`skipped_continuity`。
6. 仍在 cooldown：`skipped_cooldown`。
7. 达到 `parent_notify_threshold`：`parent_notify`，创建或复用 `review_items`。
8. 达到 `daily_limit`：`skipped_daily_limit`。
9. `allow_speaker=false`：`record_only`。
10. 不在启用作息窗口内：`skipped_out_of_routine_window`。
11. 通过策略：`allowed`，`shouldSpeak=true`。

`parent_notify_threshold` 优先于 `daily_limit`。如果两者相同，优先转给家长处理，不继续对孩子重复播报。

cooldown 和 daily limit 只统计真实提醒：

- `reminder_events.is_test = 0`。
- `event_source` 不是 `test` 或 `dry_run`。

同时会查询近期 `allowed` decisions。这样即使摄像头在短时间内重复提交 observation，在真正生成 reminder event 前，也不会连续产生多个 `allowed` decision。

internal observation 会在处理前确保 child 级默认 `care_capability_configs` 已存在，因此不依赖家长是否先打开过看护设置页。worker 上报带 `deviceId` 时，策略先查设备级配置；没有设备级配置时回落到 child 级默认配置。

internal observation 也会确保 child 级默认 `care_routine_windows` 已存在，因此 worker 先上报时不会因为家长尚未打开作息设置页而缺少默认窗口。

`current_behavior_states` 由 observation 的 behavior signals upsert 得到。同一个 `family/child/device/scenario/state` 只保留当前状态；完整历史仍然来自 `camera_observation_events` 和 `behavior_signals`。

连续观察累积规则：

- 同一个 `family/child/device/scenario/state` 在连续窗口内持续出现时累积 `consecutive_seconds`。
- 连续窗口阈值先取 `max(30s, min_observation_seconds)`。
- 低于 `confidence_threshold` 的 signal 只记录 observation/signal，不更新、不重置 `current_behavior_states`。
- signal status 为 `recovered`、`cleared`、`inactive` 时重置 `started_at` 和 `consecutive_seconds`。
- 距离上次观察超过连续窗口阈值时重置 `started_at` 和 `consecutive_seconds`。
- 历史事实仍然只从 `camera_observation_events` 和 `behavior_signals` 追溯。
- `durationSeconds` 表示 worker 在同一 source/scenario 下“本次非重叠观察窗口”的新增持续秒数；worker 不能每帧重复上报整段历史时长，否则会重复累计。

`review_items` 创建规则：

- 仅当 decision 为 `parent_notify` 时创建或复用。
- `domain=care`。
- 默认 `source_type=reminder_decision`，`source_id` 指向对应 decision。
- summary 使用家长可理解短句，不包含工程词。
- 同一个 child/scenario/item type 在 cooldown 或至少 30 分钟内复用 pending item，避免重复待处理。

内部 observation 接口仍允许没有 `sourceEventId`，便于阶段 2A 合同测试和过渡接入。但后续旧 RTSP worker / 视觉 worker 接入时必须传稳定 `sourceEventId`，否则幂等保护不生效。

阶段 2C gate 已实现：真实 speaker command 接入前，`CarePolicyEngine` 会检查当前 dayType 和 `care_routine_windows`；不在对应作息窗口内的 observation 不会触发 `shouldSpeak=true`。

scenario 到 routine window 的保守映射：

- `wake_up` -> `wake_up`。
- `meal_start` / `meal_habit` -> `breakfast` / `lunch` / `dinner` / `meal`。
- `nap_time` -> `nap`。
- `bedtime` -> `bedtime`。
- `toy_cleanup` -> `toy_cleanup` / `cleanup` / `transition`；不会因为 bedtime 窗口而全天或睡前任意播报。
- `posture` -> `posture` / `study` / `reading` / `meal` / 三餐窗口；没有明确窗口时只记录。
- `transition` -> `transition`。

信号语义 gate：

- `cleanup_started`、`meal_started`、`child_at_table`、`seated`、`posture_recovered` 等正向或已开始执行信号只记录，不播报。
- `recovered`、`cleared`、`inactive` 只记录，不播报。
- `policy_snapshot_json` 记录 `signalGateReason` 和 `routineGate`，便于后续排查。

阶段 2C 后策略条件已具备、可进入后续 speaker command 接入的场景如下。这里的“可进入”仅表示后端策略 gate 完整，不代表视觉能力已经完整可靠；还必须有负向/待处理 observation 信号，并命中启用作息窗口：

- `wake_up`
- `meal_start`
- `meal_habit`
- `nap_time`
- `bedtime`
- `toy_cleanup`

仍需保持 observation-only 或先补配置/模型的场景：

- `posture`：默认没有 posture/study/reading 作息窗口，未配置前只记录。
- `transition`：默认没有 transition 作息窗口，未配置前只记录。
- 旧 2B adapter 已可靠产出的负向场景仍有限；`meal_started`、`cleanup_started` 等正向信号只记录，不进入播报。

## 5.2 阶段 2D.0 Trigger 幂等与安全闸门

阶段 2D.0 在真实 speaker command 接入前收紧 `/internal/reminders/trigger`。此阶段仍不下发真实摄像头命令，只生成正式 `reminder_event`。

正式 trigger 规则：

- 非 `dryRun` 必须传 `reminderDecisionId`。
- decision 必须存在，且 `familyId`、`childId`、`scenario` 与请求一致。
- decision 必须是 `allowed` 且 `should_speak=true`。
- 如果 decision 已绑定 `device_id`，请求里的 `deviceId` 不能覆盖或改写它；不一致时拒绝。
- decision 必须在 2 分钟 TTL 内触发，过期返回 `reminder_decision_expired`。
- 同一个 `reminderDecisionId` 已存在正式 internal `reminder_event` 时，直接返回已有 event，不重新生成 AI 文案，不新增 event。
- `dryRun=true` 只预览，不写正式 `reminder_event`，不受正式 TTL 限制。

幂等查询条件：

```text
event_source = internal
is_test = 0
source_type = reminder_decision
source_id = {reminderDecisionId}
```

当前不新增唯一约束 migration。现有字段足以支持应用层幂等查询；后续如果需要并发强一致，可以再评估唯一索引。

## 5.3 阶段 2D.1 Speaker Command 接入

阶段 2D.1 将策略允许的 care reminder 转换为摄像头语音命令。入口仍然只能是 `/internal/reminders/trigger`；旧 RTSP / 视觉 worker 继续保持 observation-only，不允许直接调用 speaker，也不允许调用 `/internal/reminders/trigger`。

接入边界：

- 只有 `decision=allowed` 且 `should_speak=true` 的 `reminder_decision` 可以进入正式 trigger。
- 先生成或复用正式 `reminder_event`，再通过 `CameraCommandService.internal_speak` 创建 `camera_commands`。
- `CameraCommandService` 仍是唯一命令落点；它再通过 `CameraBridgeService` 分发到 `disabled`、`mock`、`ai_camera_test` 或未来自研硬件 adapter。
- Flutter 不接触 speaker command、RTSP、go2rtc、旧 worker 或私有协议。
- `reminder_events.command_id` 关联真实摄像头命令；`camera_commands` 保存命令执行状态和 runtime response。

幂等规则：

- 同一个 `reminderDecisionId` 已存在正式 internal `reminder_event` 时，不重新生成 AI 文案，不新增 event。
- 如果既有 `reminder_event` 已有 `command_id`，重复 trigger 直接返回既有 event 和 command 状态，不重复创建 speaker command。
- 如果既有 `reminder_event` 没有 `command_id`，允许补发一次 speaker command 并回写同一个 event，便于兼容 2D.0 阶段已生成的 reminder event。
- `dryRun=true` 不创建 `reminder_event`，不创建 `camera_commands`。

delivery status 映射：

- AI 文案生成完成但尚未下发：`generated` 或 `fallback_used`。
- camera command 创建并被 runtime adapter 接受：`command_sent`。当前旧 `ai_camera_test` adapter 没有可靠物理播报回执，因此不直接标为 `delivered`。
- camera command 创建或发送失败：`failed`，同时写入 `failure_reason`。

当前不新增 migration。`camera_commands` 已在 `004_camera_runtime_task_events.sql` 中存在；`reminder_events.command_id`、`delivery_status`、`failure_reason` 已在 `022_care_observation_contract.sql` 中预留，足以承载本阶段合同。

## 5.4 阶段 2D.2 设备回执与状态轮询收口

阶段 2D.2 不新增真实设备回执协议，只把当前命令状态查询边界收紧。旧 `ai_camera_test` adapter 没有可靠的物理播报回执，因此后端不能把 `command_sent` 伪装成 `delivered`。

当前 `camera_commands` 状态模型：

- `running`：命令已创建，runtime adapter 正在执行。
- `succeeded`：adapter 调用成功。对旧 `ai_camera_test` 和 `mock` 来说，只代表命令被 runtime 接受，不代表物理扬声器已经播完。
- `failed`：adapter 调用失败，`message` 为家长可理解的失败文案，`response_payload` 保留后端可排查的错误摘要。
- `completed_at`：同步调用结束时间，不等同于真实设备完成播报的回执时间。

`reminder_events.delivery_status` 与 `camera_commands.status` 的映射：

- 无 `command_id`：`generated` 或 `fallback_used`，只代表话术已生成。
- `camera_commands.status=running`：后续异步命令可映射为 `command_created`。
- `camera_commands.status=succeeded`：当前映射为 `command_sent`，不映射为 `delivered`。
- `camera_commands.status=failed`：映射为 `failed`，并写入 `failure_reason`。
- 未来自研硬件提供可靠设备回执后，才允许从 `command_sent` 更新为 `delivered` 或 `failed`。

查询收口：

- `GET /api/reminders/events` 返回的 reminder event 会带 `delivery` 对象，包括 `commandId`、`commandStatus`、`message`、`updatedAt`、`completedAt`。
- 重复 `/internal/reminders/trigger` 时，如果既有 event 已有 `command_id`，返回同一 event 和当前 command 状态；若该 event 已经是 `failed`，`command.ok=false`。
- `failure_reason` 保留在 reminder event 上，供后续首页/设置页展示为家长可理解的失败原因。

并发唯一约束评估：

- 当前应用层通过 `event_source=internal + is_test=0 + source_type=reminder_decision + source_id={reminderDecisionId}` 查询实现幂等。
- 这能覆盖普通重试和 worker 重放，但不能在极端并发下提供数据库级唯一保证。
- 如果真实硬件接入后存在并发 trigger 风险，建议新增 MySQL 兼容唯一索引，例如对正式 internal reminder 使用 `family_id, event_source, is_test, source_type, source_id`。此变更需要单独 migration 评审，避免影响测试事件、dryRun 和历史数据。
- 阶段 2D.2 不新增 migration。

`device_id` 路由边界：

- 阶段 2D.3 已新增 `DeviceRuntimeResolver`，业务层通过 `family_id + device_id` 获取 `CameraBridgeService`。
- 当前 resolver 会校验设备属于家庭，且不是已解绑设备；不传 `device_id` 时使用家庭明确默认设备。
- 阶段 2D.5 之后，resolver 优先读取设备级 `device_runtime_configs`。缺少设备级配置时，只有 development/test 下允许回落应用级 `CAMERA_RUNTIME_PROVIDER` / `CAMERA_RUNTIME_ADAPTER`。
- `CameraCommandService`、`DeviceService.device_status` 和任务运行观察会通过 resolver 获取 bridge，不再直接假设唯一全局摄像头。
- `/api/camera/health`、`/status`、`/runtime`、`/speaker/status`、`/snapshot`、`/stream`、`/webrtc/session`、`/webrtc/offer`、`/monitor/status` 也会通过 resolver 获取 bridge，并支持 query `deviceId`。
- 多设备/自研硬件接入时，业务层仍通过 resolver 选择 adapter；设备凭证不写入业务表，只通过 `secret_ref` 引用安全存储。
- 业务层仍只调用 `CameraCommandService.internal_speak`，不直接知道 RTSP、go2rtc、设备型号或私有协议。

阶段 2D.4 多摄像头闭环：

- 新增 `family_default_devices`，以 `family_id` 为主键保存家庭默认摄像头，保证一个家庭最多一个默认设备。
- 新增设备管理绑定接口，`bindingCode` 在未解绑设备中保持全局 active 唯一；同一家庭重复绑定返回已有设备，不静默新增，不同家庭重复绑定会拒绝。`bindingCode` 只是开发阶段的临时唯一键，未来真实硬件具备 `serialNumber` / `deviceUniqueId` 后，必须迁移到硬件唯一标识做全局去重。
- 首次 setup 只负责第一台摄像头；如果家庭没有默认设备，setup 创建/更新设备后会设为默认。后续新增第二台摄像头必须走 `/api/devices`，不能用 `/api/setup/device` 覆盖第一台。
- setup 中的摄像头唤醒名写入家庭默认设备；如果历史家庭还没有默认设备，先通过 `ensure_default_device` 选择并补齐默认设备，不再按 `created_at` 猜测最早设备。
- 解绑默认设备时，后端按 `created_at ASC, id ASC` 从剩余未解绑设备中选择新的默认设备；如果没有剩余设备，清空默认关系并返回 `defaultDevice: null`。
- 生产语义下，家庭没有默认设备时 camera runtime resolver 返回无设备状态；只有 development/test 下的 mock、disabled、ai_camera_test 允许无设备全局 fallback。
- `/api/camera/status` 的 current task 按 resolved `deviceId` 过滤。历史无 `device_id` 的老任务只在默认设备上展示，避免多摄像头下 A 设备显示 B 设备任务。
- `/api/camera/events` 支持 query `deviceId`。不传时走家庭默认设备；camera command 和 task event 都按 resolved `deviceId` 隔离，避免 A 摄像头看护页显示 B 摄像头事件。
- internal observation 必须带合法 `deviceId`，且设备必须属于当前 family、未解绑。由 observation 产生的 decision、reminder event、speaker command 使用同一个 `deviceId`。
- Flutter 只保存和传递 selectedDeviceId，不展示 provider key、RTSP、go2rtc、prompt、backend 等工程词。

迁移评估：

- 阶段 2D.4 新增 `023_family_default_devices.sql`，只建立默认设备关系表，不新增设备级 runtime provider/config 字段。
- `023` 不做历史回填。原因是当前 dev/测试库已有家庭设备数据可能来自不同阶段，迁移期不应猜测业务默认设备；运行时 `ensure_default_device` 会在读取默认设备、列表、resolver 或 setup 摄像头命名时懒加载补齐。若未来线上数据量变大，可单独新增补偿 migration 或后台任务。
- 阶段 2D.5 新增 `024_device_runtime_configs.sql`，为每台摄像头保存 runtime provider/config。`config_json` 只允许保存 `baseUrl`、adapter name、stream profile、speaker capability 等非敏感配置；密钥、token、真实硬件证书不得明文入库，只能通过 `secret_ref` 指向后续安全存储。
- 不应把 RTSP URL、go2rtc 地址或私有协议细节返回给 Flutter。

阶段 2D.5 设备级 Runtime Provider/Config：

- 新增 `device_runtime_configs`，以 `family_id + device_id` 唯一保存设备级运行时配置。支持 provider：`disabled`、`mock`、`ai_camera_test`，并预留 `future_hardware` / `self_owned_camera`。
- `DeviceRuntimeResolver` 新解析顺序：先校验设备属于当前家庭且未解绑；再读取 active 设备级 runtime config；有配置则按设备配置创建 bridge；无配置时 development/test 可回落全局 provider，staging/production 返回 `device_runtime_not_configured`。
- `ai_camera_test` / `mock` 仍然只允许 development/test profile。`future_hardware` / `self_owned_camera` 只是占位 provider，当前返回“自研摄像头运行时尚未接入”，不会伪装成真实硬件。
- camera read API、speaker command、任务观察和 care reminder speaker command 都继续通过 resolver；Flutter 不知道 provider key，也不接触 RTSP、go2rtc、旧 worker 或私有协议。
- `bindingCode` 仍只是开发阶段临时唯一键。真实硬件阶段必须迁移到 `serialNumber` / `deviceUniqueId` 全局唯一，并补数据库级唯一约束，防止并发重复绑定。

阶段 2D.6 Runtime Config 写入 API 与唯一标识迁移设计：

- 新增设备管理 API：`GET /api/devices/{deviceId}/runtime-config` 与 `PUT /api/devices/{deviceId}/runtime-config`。写入前必须校验当前用户有 `manage_devices`，设备属于当前 family，且设备未解绑。
- `GET runtime-config` 不返回 `secret_ref` 原文，只返回 `hasSecretRef`。返回内容可说明 `future_hardware` / `self_owned_camera` 当前 adapter 尚未实现。
- `PUT runtime-config` 只接受 `disabled`、`mock`、`ai_camera_test`、`future_hardware`、`self_owned_camera`。`mock` / `ai_camera_test` 仍只允许 development/test。
- `config_json` 按 provider allowlist 校验，不能无限制写入。当前允许的非敏感配置包括 `baseUrl`、`streamProfile`、`adapterName`、`speakerCapabilities`、`deviceProfile` 等有限字段。
- 敏感配置校验必须递归、大小写不敏感，覆盖嵌套 key/value。禁止 token、password、apiKey、secret、authorization、cookie、privateKey、certificate、credential 等字段或明显密钥内容。
- URL 类型字段只允许 `http` / `https`，并拒绝 userinfo，例如 `http://user:pass@host`。真实 RTSP/go2rtc 私有细节不应进入 Flutter，也不应作为家长端可见配置。
- `secret_ref` 只保存凭证引用，例如 vault/kms/ref/secret manager 路径；不保存真实 token、证书或密钥。
- serial/device unique ID 迁移方案：真实硬件阶段新增 `serial_number` / `device_unique_id` / `hardware_model` 等字段，并对 `device_unique_id` 建全局唯一索引；绑定流程由 `bindingCode` 去重迁移到 `deviceUniqueId` 去重。`bindingCode` 降级为短期配对码，不再作为设备身份来源。

## 6. Prompt Registry 设计

保留现有任务 prompt：

- `backend/prompts/task/reminder_text.v1.md`

新增摄像头看护提醒 prompt：

- `backend/prompts/reminders/toy_cleanup_v1.md`
- `backend/prompts/reminders/posture_v1.md`
- `backend/prompts/reminders/meal_start_v1.md`
- `backend/prompts/reminders/meal_habit_v1.md`
- `backend/prompts/reminders/nap_time_v1.md`
- `backend/prompts/reminders/bedtime_v1.md`
- `backend/prompts/reminders/wake_up_v1.md`
- `backend/prompts/reminders/transition_v1.md`
- `backend/prompts/reminders/fallback_v1.md`

新增视觉类 prompt：

- `backend/prompts/vision/scene_observation_v1.md`
- `backend/prompts/vision/behavior_summary_v1.md`

摄像头看护提醒 prompt 必须要求模型返回 JSON：

```json
{
  "text": "玩具该回家啦，我们一起把它放回盒子。",
  "tone": "warm",
  "scenario": "toy_cleanup",
  "safety": "ok"
}
```

后端只取 `text` 用于播报，并校验：

- JSON 可解析。
- `text` 不超过长度限制。
- 不重复上一句。
- 不包含禁词。
- 不出现“我是 AI”“系统检测到”“你不乖”“扣分”“妈妈会生气”。
- 不包含解释、URL、列表、换行或不适合语音播报的结构。

校验失败走 fallback。

## 7. API 合同草案

Flutter 可调用：

- `GET /api/care/capabilities`
- `PATCH /api/care/capabilities`
- `GET /api/care/routine-windows`
- `PUT /api/care/routine-windows`
- `GET /api/care/summary`
- `GET /api/reminders/next`
- `GET /api/reminders/events`
- `POST /api/reminders/test`

`PUT /api/care/routine-windows` 默认是按 child 全量替换。若传 `?dayType=school_day`，则只替换该 dayType 下的作息窗口，避免编辑上学日时误删周末或假期。

`GET /api/reminders/events` 默认不返回试听提醒。只有显式传 `includeTest=true` 才返回 `POST /api/reminders/test` 生成的测试记录。

内部接口：

- `POST /internal/camera/observations`
- `POST /internal/reminders/trigger`

内部接口要求：

- 默认需要内部 token。
- 可选来源 IP 限制。
- 生产环境缺少 `INTERNAL_API_TOKEN` 时拒绝启动。
- 每次内部调用写入 audit event。
- Flutter 不调用 internal 接口。
- `POST /internal/camera/observations` 使用 `familyId + source + sourceEventId` 幂等；重复 observation 不重复写 signals 或 decisions。
- `POST /internal/reminders/trigger` 非 `dryRun` 必须传 `reminderDecisionId`。只有 decision 为 `allowed` 且 `should_speak=true`，且未过 TTL、未生成过正式 internal event 时，才允许生成正式 `reminder_event`。
- 重复 trigger 同一个 `reminderDecisionId` 时返回已有正式 event，不再次生成 AI 文案。
- `dryRun=true` 只用于内部链路测试，不写正式提醒事件。

## 8. 旧 RTSP 摄像头 Adapter 迁移方式

旧项目路径：

```text
/Users/sqcopenclaw/.openclaw/workspace/ai_camera_test
```

迁移原则：

- 旧项目只能作为当前后端的 camera runtime adapter。
- Flutter 不接触 RTSP、go2rtc、旧 worker、摄像头型号或私有协议。
- 旧 worker 如果现在会直接分析并播报，接入当前项目时必须改成 observation-only。
- 播报决策、cooldown、prompt、fallback、家长记录都必须回到当前项目后端。
- 阶段 2B 不改旧项目源码，在当前后端新增 observation-only adapter/worker。

阶段 2B 当前项目入口：

- Adapter：`backend/integrations/camera_runtime/ai_camera_test_observation_adapter.py`。
- Worker：`backend/workers/camera_observation_worker.py`。
- Worker 只调用旧项目 `/api/camera/snapshot?format=data_url` 和 `/api/analyze_frame`，再 POST 当前项目 `/internal/camera/observations`。
- Worker 不调用 `/internal/reminders/trigger`，不写 `reminder_events`，不调用 speaker，不改 task 状态。
- 旧 `/api/analyze_frame` 返回里的 `reminder`、`child_message` 不作为播报文本迁移。

本地运行命令：

```sh
cd /Users/sqcopenclaw/Desktop/ai_camera_app/backend
python3 -m workers.camera_observation_worker
```

单次运行：

```sh
cd /Users/sqcopenclaw/Desktop/ai_camera_app/backend
CAMERA_OBSERVATION_RUN_ONCE=1 python3 -m workers.camera_observation_worker
```

环境变量：

- `AI_CAMERA_TEST_BASE_URL`：旧项目 HTTP 入口，例如 `http://127.0.0.1:8767`。
- `AI_CAMERA_TEST_RTSP_URL`：旧项目 RTSP 配置来源，仅用于本地部署说明；当前 worker 不直接打开 RTSP。
- `CAMERA_OBSERVATION_INTERNAL_URL`：当前项目 internal observation 入口，可填完整 `/internal/camera/observations` URL 或当前后端 base URL。
- `INTERNAL_API_TOKEN`：internal 接口 token。
- `CAMERA_OBSERVATION_FAMILY_ID`：dev-only family 映射。
- `CAMERA_OBSERVATION_CHILD_ID`：dev-only child 映射。
- `CAMERA_OBSERVATION_DEVICE_ID`：dev-only device 映射。
- `CAMERA_OBSERVATION_INTERVAL_SECONDS`：轮询间隔，默认 5 秒。

当设备绑定映射可用后，worker 应从当前后端/数据库读取 family-child-device 映射；在此之前，上述 dev-only 配置不得伪装成正式绑定逻辑。

`sourceEventId` 规则：

```text
ai_camera_test:{deviceId}:{scenario}:{windowStartMs}:{windowEndMs}:{signalType}
```

同一观察窗口重试时必须使用相同 `sourceEventId`。稳定 `sourceEventId` 是 `camera_observation_events` 幂等保护的前提。

阶段 2B 可靠接入范围：

- `posture`
- `toy_cleanup`
- `meal_start`
- `meal_habit`

`nap_time`、`bedtime`、`wake_up`、`transition` 继续保留合同和 prompt 边界，等待更可靠的视觉/状态来源后接入，不假装已完成。

阶段 2C gate：

- `CarePolicyEngine` 检查 dayType 和 `care_routine_windows`。
- 不在对应作息窗口内的 observation 只能记录或进入家长处理，不能触发 `shouldSpeak=true`。
- 正向、恢复、已开始执行的 signal 只能记录，不能触发 `shouldSpeak=true`。
- 2C 完成前，2B worker 不允许调用 `/internal/reminders/trigger`。

## 9. 隐私和安全边界

- 后端保存 parent-facing summary 和必要状态。
- raw technical detail 仅保存在后端，不返回给 Flutter。
- 低可信观察只记录，不提醒。
- 连续观察不足不触发。
- 能力关闭后不提醒，不播报。
- 设备离线时不播报，转为记录或家长处理事项。
- 多孩子、多设备必须通过 `childId`、`deviceId` 隔离。
- 提醒日志保留 prompt id/version、text source、fallback used 和 delivery status，便于评估。
- 不做医疗诊断、情绪诊断、安全事故定性。

## 10. 测试计划

阶段 1 覆盖：

- Prompt registry 能发现新 prompt，且旧任务 prompt 仍存在。
- AI reminder JSON 可解析时通过。
- AI 返回非 JSON、禁词、重复文本、过长文本时 fallback。
- `/api/care/capabilities` 返回 V1 默认能力。
- PATCH ability 后配置可读取。
- `/api/care/routine-windows` 可读取和更新上学日/周末窗口。
- internal 接口缺 token 被拒绝。
- internal 接口带测试 token 可记录 observation。
- 低可信 observation 只记录，返回不提醒决策。
- `/api/reminders/test` 不播报，只生成/记录测试提醒。
- 现有任务提醒 prompt 和任务提醒接口回归。

## 11. 分阶段实施计划

阶段 0：

- 输出正式架构文档。
- 明确旧 RTSP adapter 边界。
- 明确 Flutter/Internal API 分层。

阶段 1：

- MySQL 迁移建表。
- 后端模型、repository、service 骨架。
- care/reminders/internal API 合同。
- prompt 目录和 JSON 校验/fallback。
- 最小 Flutter care model/repository 合同。
- 合同测试。

阶段 2A：

- 补 cooldown、daily limit、重复策略。
- `CarePolicyEngine` 替代临时策略。

阶段 2B：

- 旧 RTSP / 视觉 worker observation-only 接入。
- 稳定 `sourceEventId` 幂等。
- 不接真实 speaker command。

阶段 2C：

- 作息窗口 gate。
- dayType 与 `care_routine_windows` 参与策略。
- 信号语义 gate。

阶段 2D.0：

- `/internal/reminders/trigger` 幂等。
- decision TTL 和 family/child/scenario/device 一致性检查。
- 不接真实 speaker command。

阶段 2D.1：

- 接 camera speaker command。
- 记录 delivery status。
- 不接真实视觉大模型，不改旧 RTSP worker 的 observation-only 边界。

阶段 2D.2：

- 查询 reminder event 时带回 camera command 状态。
- 保持 `command_sent` 与 `delivered` 的边界。
- 评估但不新增并发唯一约束 migration。

阶段 2D.3：

- 增加 `DeviceRuntimeResolver`。
- camera write API、camera read API、`DeviceService.device_status` 和任务运行观察通过 resolver 选择 bridge。
- 当前仍回落全局 provider，不新增设备级 runtime config migration。

阶段 2D.4：

- 增加 `family_default_devices` 明确默认摄像头。
- 新增设备管理绑定、获取默认、设为默认接口。
- 收紧 setup/device、task current-in-progress、internal observation 的多设备边界。
- Flutter 增加 selectedDeviceId 轻量数据流，live care 读写接口带 selectedDeviceId。

阶段 2D.5：

- 新增 `device_runtime_configs`，让每台摄像头拥有独立 runtime provider/config。
- resolver 优先设备级配置；缺少配置时仅 development/test 允许全局 fallback。
- 保持 read/write camera API 兼容，不新增真实硬件协议。

阶段 3：

- 首页显示下一次提醒和今日状态。

阶段 4：

- 行为状态机和连续观察。
- 更完整视觉模型/eval 接入。

阶段 5：

- 幼儿园任务模板和上学日/周末任务页调整。

阶段 6：

- 视觉模型接入、eval case、灰度策略和家长解释记录优化。
