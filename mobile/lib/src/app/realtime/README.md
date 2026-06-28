# App Realtime（`/api/tasks/stream`）

## 架构

- **单连接**：`AppRealtimeController`（见 `task_realtime_repository.dart`）在 `AppRealtimeScope` 内启动，全 App 共享。
- **禁止**：页面级 `WebSocket.connect`、Timer 轮询拉观察/任务（WebRTC 信令除外）。
- **页面**：只 `watch` Riverpod Provider；事件由 `AppRealtimeInvalidationCoordinator` 写入 Provider。

## 三层刷新策略

| 层级 | 机制 | 触发方 | 典型 API |
|------|------|--------|----------|
| **WS 推送** | 观察完成、任务变更、parent_notify、设备状态 | 后端 worker / 策略引擎 | 无（WebSocket） |
| **GET 静默补全** | 对齐 DB、重连 catch-up、回前台 | Coordinator debounce / resume / reconnect | GET monitor/status、care/summary、tasks |
| **POST 分析** | 立刻抓帧 + 跑 AI（成本高） | **仅用户显式** | `POST /camera/monitor/refresh` |

- 回前台、跨日、进入看护 Tab：**不**自动 POST；只做 GET 静默包。
- 「刷新预览」、显式重试：走 `triggerMonitorAnalysis`（全 App 3s cooldown + in-flight 忽略）。
- WS 重连 / 首次 connect：`AppRealtimeScope` 500ms debounce 后 `refreshAllDomainsSilently`。

## 事件 type 目录

| type | 含义 | Coordinator 动作 |
|------|------|------------------|
| `camera_observation.updated` | AI 观察完成 | override monitor + events 直插 + 静默 refresh monitor |
| `camera_monitor.refreshed` | Monitor 刷新 | 同观察 |
| `camera_event.created` | 看护画面事件 | events 直插/refresh |
| `reminder_event.created` | 摄像头语音提醒已播 | events refresh |
| `reminder_decision.created` | 策略决策 | care burst + monitor debounce；`should_notify_parent` 时 WS `event` 带 reviewItem → 首页乐观待办 |
| `camera_command.created` | 摄像头指令 | events |
| `camera_status.changed` | 设备在线状态 | 静默 refresh health/status |
| `task.updated` | 任务数据变更 | 静默 refresh tasks/points/reports |
| `task_status.changed` | 任务状态变更 | 同上 + task detail/events |
| `session_revoked` | 踢下线 | 清 session |

规划扩展（本次未接 UI）：`notification.created`、`alert.created`、`parent_review.created`。

## 信封字段

见后端 `family_event_message`：`type`、`deviceId`、`taskIds`、`eventIds`、`observationId`、`isReliable`、`event`（lightweight）、`sentAt`。

`reminder_decision.created` 的 `event`（仅 parent_notify 且存在 review_item 时）含：`id`、`summary`、`status`、`reviewType`/`itemType`、`scenario`、`childId`、`domain` 等，供 App 秒级展示首页待办。

## 刷新原则

- 有缓存：`ref.refresh(provider.future)` 或 Notifier `refresh(keepPrevious: true)`
- 无缓存：允许全屏 loading
- 后台 refresh 用 `isInitialAsyncLoad` 区分首屏 loading 与静默刷新，避免闪烁
- 不要 invalidate 聚合 `liveCareStatusProvider`（依赖链自动重算）
- 任务周视图：`activeTaskWeekQueryProvider` 注册当前 query；离屏时用 `fallbackTaskWeekQuery` 静默 refresh
