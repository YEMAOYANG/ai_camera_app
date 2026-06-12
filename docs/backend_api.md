# Mira Guardian App Backend API v1

更新日期：2026-06-04

本文档描述当前家长端 App 第一版已经实现或明确预留的后端接口。后端当前保留 Flask 服务，负责 App 登录态、首次设置、任务、积分、奖励、设备状态，以及 AI / Prompt / Camera / Firmware 的轻量边界。

Flutter 合同只面向 App 后端 API，不直接暴露底层流媒体、RTSP/go2rtc、硬件私有协议、短信供应商、AI provider key 或旧测试项目路径。开发/测试环境可以通过 adapter 桥接旧测试运行时，production 必须使用正式 adapter 或返回清晰的未配置状态。

## 认证模型

登录方式：手机号 + 短信验证码。

未注册手机号在验证码通过后自动创建家长用户和家庭账户。

Token：

- `accessToken`：短时访问令牌，默认 15 分钟。
- `refreshToken`：长时刷新令牌，默认 30 天。
- refresh 成功后会轮换 access token 和 refresh token，旧 refresh token 立即失效。
- App 启动时只要 refresh token 未过期，就不回到登录页。
- 普通 API 请求 access token 过期时，客户端自动调用 refresh 接口并重试一次。

开发/测试验证码：

```text
APP_ENV=development
APP_ENABLE_DEV_ADAPTERS=1
APP_SMS_PROVIDER=development
```

development/test 短信 provider 每次请求会生成随机 6 位验证码，并在接口返回
`debugCode`，方便本地调试。production 不允许启用 development provider，后续接入真实短信供应商后替换 provider 即可。

## Auth

### POST `/api/auth/sms/request`

发送登录验证码。

Request:

```json
{
  "phone": "13800002026"
}
```

Response:

```json
{
  "ok": true,
  "codeSent": true,
  "expiresAt": 1780390000000,
  "debugCode": "593204",
  "provider": "development",
  "deliveryStatus": "delivered",
  "message": "验证码已发送"
}
```

### POST `/api/auth/sms/login`

手机号验证码登录。未注册手机号验证通过后自动创建家庭账户。

Request:

```json
{
  "phone": "13800002026",
  "code": "593204"
}
```

Response:

```json
{
  "ok": true,
  "user": {
    "id": "user_xxx",
    "phone": "13800002026",
    "familyId": "fam_xxx",
    "displayName": "家长"
  },
  "family": {
    "id": "fam_xxx",
    "name": "我的家庭"
  },
  "tokens": {
    "accessToken": "mga_xxx",
    "refreshToken": "mgr_xxx",
    "accessTokenExpiresAt": 1780390000000,
    "refreshTokenExpiresAt": 1782982000000,
    "expiresInSeconds": 900
  }
}
```

### POST `/api/auth/token/refresh`

刷新登录态并轮换 refresh token。

Request:

```json
{
  "refreshToken": "mgr_xxx"
}
```

Response: 同 `/api/auth/sms/login` 的用户、家庭和 token 结构。

### GET `/api/auth/session`

读取当前登录家长。

Headers:

```text
Authorization: Bearer mga_xxx
```

Response:

```json
{
  "ok": true,
  "user": {
    "id": "user_xxx",
    "phone": "13800002026",
    "familyId": "fam_xxx",
    "displayName": "家长"
  },
  "family": {
    "id": "fam_xxx",
    "name": "我的家庭"
  }
}
```

### POST `/api/auth/logout`

退出登录，撤销当前 session。

Headers:

```text
Authorization: Bearer mga_xxx
```

Request:

```json
{
  "refreshToken": "mgr_xxx"
}
```

## Camera Bridge

摄像头运行时由 adapter 控制。默认 production 路径为 `disabled`，真实硬件/摄像头 runtime 接入前返回清晰的不可用状态。开发/测试如需桥接旧测试运行时，显式配置：

```text
APP_ENV=development
APP_ENABLE_DEV_ADAPTERS=1
CAMERA_RUNTIME_PROVIDER=ai_camera_test
AI_CAMERA_TEST_BASE_URL=http://127.0.0.1:8767
CAMERA_MONITOR_ENABLED=1
CAMERA_SPEAKER_ENABLED=1
TASK_REMINDER_LEAD_SECONDS=300
```

旧配置名 `APP_CAMERA_RUNTIME_ADAPTER`、`APP_CAMERA_BACKEND_URL` 仍兼容，
但新项目配置优先使用 `CAMERA_RUNTIME_PROVIDER` 和
`AI_CAMERA_TEST_BASE_URL`。production 不允许默认连接本地旧测试运行时。

### GET `/api/camera/health`

返回 camera runtime adapter 健康状态。

### GET `/api/camera/status`

Headers:

```text
Authorization: Bearer mga_xxx
```

Response:

```json
{
  "ok": true,
  "status": {
    "connectionStatus": "online",
    "streamAvailable": true,
    "snapshotAvailable": true,
    "speakerAvailable": true,
    "monitorAvailable": true,
    "lastSeenAt": 1780390000000,
    "runtimeProvider": "ai_camera_test_bridge",
    "currentTask": null,
    "message": "摄像头在线，最新状态已同步。"
  }
}
```

### GET `/api/camera/runtime`

返回 camera runtime 摘要状态。Flutter 不直接接触 RTSP、go2rtc 或旧测试服务路径。

### GET `/api/camera/speaker/status`

返回后端 adapter 暴露的喇叭/播放状态；未配置时返回降级状态。

### GET `/api/camera/snapshot`

返回后端 adapter 提供的 JPEG 快照；未配置或不可达时返回明确错误。

### GET `/api/camera/stream`

返回后端代理的兼容流响应，保留给调试和降级路径。正式 Flutter 实时看护优先使用 WebRTC session 合同，不使用 MJPEG 作为主路径。

### GET `/api/camera/webrtc/session`

Flutter 全屏实时监控页使用。Flutter 先向当前后端申请实时画面连接信息，再用 WebRTC 建立真实流播放。

Headers:

```text
Authorization: Bearer mga_xxx
```

Response:

```json
{
  "ok": true,
  "session": {
    "signalingUrl": "ws://127.0.0.1:1984/api/ws?src=ipc45aw_hd",
    "message": "实时画面连接已准备好。"
  }
}
```

### POST `/api/camera/webrtc/offer`

兼容测试接口。实时监控主路径使用 `GET /api/camera/webrtc/session`，以便持续交换 WebRTC candidate。

Headers:

```text
Authorization: Bearer mga_xxx
```

Request:

```json
{
  "sdp": "v=0\r\n..."
}
```

Response:

```json
{
  "ok": true,
  "session": {
    "type": "answer",
    "sdp": "v=0\r\n...",
    "candidates": [],
    "message": "实时画面连接已准备好。"
  }
}
```

### POST `/api/camera/commands/speak`

Request:

```json
{
  "text": "数学作业快到时间了，我们准备开始吧。",
  "taskId": "task_xxx"
}
```

Response:

```json
{
  "ok": true,
  "command": {
    "commandId": "cmd_xxx",
    "commandType": "speak",
    "status": "succeeded",
    "taskId": "task_xxx",
    "createdAt": 1780390000000,
    "completedAt": 1780390000123,
    "message": "已执行"
  }
}
```

### POST `/api/camera/commands/snapshot`

触发一次快照命令并记录命令结果。

### POST `/api/camera/monitor/start`

启动任务观察并记录命令结果。

### POST `/api/camera/monitor/stop`

停止任务观察并记录命令结果。

### GET `/api/camera/monitor/status`

返回当前观察状态：

```json
{
  "ok": true,
  "monitor": {
    "running": false,
    "status": "idle",
    "lastObservation": null,
    "lastReminder": "",
    "message": "当前没有进行中的观察"
  }
}
```

## V1 App API Contract

认证完成后，业务接口统一使用 `Authorization: Bearer <accessToken>`。

### Setup

```text
GET  /api/setup/status
POST /api/setup/parent-identity
POST /api/setup/device
POST /api/setup/wifi
POST /api/setup/child
POST /api/setup/contacts
POST /api/setup/complete
```

Setup status should return:

```json
{
  "ok": true,
  "setup": {
    "completed": false,
    "parentIdentity": "done",
    "deviceBinding": "pending",
    "wifi": "pending",
    "childProfile": "pending",
    "contacts": "pending",
    "nextStep": "device"
  }
}
```

### Family / Child / Device Setup Boundary

V1 的家庭、孩子和设备初始化数据通过 Setup 接口写入。当前已实现的设备读取接口如下；独立 family/child CRUD、设备解绑、隐私模式写入等完整管理接口保留到后续阶段。

```text
Device
  GET    /api/devices
  GET    /api/devices/{deviceId}
  GET    /api/devices/{deviceId}/status
  POST   /api/devices/{deviceId}/commands
```

`GET /api/devices/{deviceId}/status` 会合并摄像头运行时状态，返回
`connectionStatus`、`lastSeenAt`、`message` 以及 `capabilities.snapshot /
stream / twoWayAudio / monitor`。Flutter 仍然只消费 App 后端字段，不接触底层
runtime 地址或流媒体配置。

### Tasks

There is no standalone day-plan API. Today content, sleep tasks,
schoolbag tasks, check-in tasks, parent confirmations, and task templates belong
to the tasks domain.

```text
Tasks
  GET    /api/tasks/today
  GET    /api/tasks
  GET    /api/tasks/{taskId}
  POST   /api/tasks
  POST   /api/tasks/batch
  PATCH  /api/tasks/{id}
  POST   /api/tasks/{id}/start
  POST   /api/tasks/{id}/complete
  POST   /api/tasks/{id}/parent-confirm
  POST   /api/tasks/{id}/reject-confirmation
  POST   /api/tasks/{id}/reject
  GET    /api/tasks/{id}/events
  WS     /api/tasks/stream
```

`GET /api/tasks` supports `childId`, `date`, `startDate`, `endDate`, and
`status`. Flutter uses `startDate` / `endDate` for the weekly task view. There
is no standalone day-plan API.

`POST /api/tasks/batch` creates several ordinary task records in one request.
It is intended for applying a common day arrangement or saving several time
blocks together. The operation validates each row inside one transaction; if a
row fails, the response message identifies the row and no rows are committed.

Batch create request:

```json
{
  "date": "2026-06-05",
  "tasks": [
    {
      "childId": "child_xxx",
      "title": "数学作业",
      "taskType": "learning",
      "startAt": "2026-06-05T19:00:00",
      "dueAt": "2026-06-05T19:30:00",
      "rewardPoints": 3,
      "requiresParentConfirmation": true
    }
  ]
}
```

Batch create response:

```json
{
  "ok": true,
  "tasks": [
    {
      "id": "task_xxx",
      "taskId": "task_xxx",
      "title": "数学作业",
      "taskType": "learning",
      "scheduledDate": "2026-06-05",
      "scheduledStart": "19:00",
      "scheduledEnd": "19:30",
      "rewardPoints": 3,
      "requiresParentConfirmation": true
    }
  ]
}
```

Task payloads include runtime fields used by the parent app:

- `status`: `scheduled`, `pending`, `reminder_sent`, `in_progress`, `delayed`,
  `awaiting_parent_confirmation`, `completed`, `confirmed`, `rejected`,
  `missed`, `expired`, `cancelled`
- `reminderMinutesBefore`, `reminderStatus`
- `startedAt`, `endedAt`, `missedAt`, `delayedAt`
- `lastReminderAt`, `nextReminderAt`, `delayReminderCount`
- `cameraObservationStatus`, `deviceId`, `timezone`

There is still no standalone day-plan API. Delay/procrastination handling is
part of the tasks runtime state machine.

`POST /api/tasks/{id}/start` 将任务切到 `in_progress`，用于家长手动开始。
自动开始由后端 scheduler 触发；本地开发也可以手动调用 dev tick 复现。

`GET /api/tasks/{id}/events` 返回提醒、自动开始、摄像头命令、完成和确认记录：

```json
{
  "ok": true,
  "events": [
    {
      "id": "evt_xxx",
      "familyId": "fam_xxx",
      "taskId": "task_xxx",
      "eventType": "auto_started",
      "message": "任务已自动开始",
      "payload": {},
      "createdAt": 1780390000000
    }
  ]
}
```

`WS /api/tasks/stream?token={accessToken}` is the authenticated task realtime
channel. The backend sends a message whenever a task action or scheduler tick
changes task state or adds task events. Flutter must refresh backend data after
receiving this message; it must not mutate task status locally.

```json
{
  "type": "task.updated",
  "source": "scheduler",
  "taskIds": ["task_xxx"],
  "tasks": [],
  "events": [
    {
      "familyId": "fam_xxx",
      "taskId": "task_xxx",
      "eventType": "auto_started"
    }
  ],
  "checkedAt": 1780390000000,
  "sentAt": 1780390000200
}
```

Task payload:

```json
{
  "id": "task_xxx",
  "taskId": "task_xxx",
  "familyId": "fam_xxx",
  "childId": "child_xxx",
  "title": "数学作业",
  "description": "25 分钟专注 + 5 分钟休息",
  "type": "learning",
  "taskType": "learning",
  "scheduleType": "weekly",
  "startAt": "2026-06-03T19:00:00",
  "dueAt": "2026-06-03T19:40:00",
  "repeatRule": {"freq": "weekly", "days": [1, 2, 3, 4, 5]},
  "status": "awaiting_parent_confirmation",
  "priority": 2,
  "scheduledDate": "2026-06-03",
  "scheduledStart": "19:00",
  "scheduledEnd": "19:40",
  "rewardPoints": 5,
  "requiresParentConfirmation": true,
  "completionSource": "camera",
  "evidence": {"confidence": 0.86},
  "evidenceSummary": "书写状态稳定，离座后 3 分钟内回座。",
  "aiObservationSummary": "AI 判断任务已完成，建议家长确认。",
  "rejectionReason": null,
  "createdBy": "user_xxx",
  "createdAt": 1780390000000,
  "updatedAt": 1780390000000,
  "completedAt": 1780390000000,
  "confirmedAt": null,
  "rejectedAt": null,
  "pointsGrantedAt": null
}
```

Task status:

```text
pending
in_progress
completed
awaiting_parent_confirmation
confirmed
rejected
expired
cancelled
```

Task type:

```text
learning
life
housework
sleep
schoolbag
reading_interest
sports_outdoor
custom
checkin
parent_confirmation
ai_observed
```

### Points

```text
Points
  GET  /api/points/account
  GET  /api/points/ledger
  POST /api/points/adjust
  POST /api/points/stage-notice/ack
```

Ledger types:

```text
task_completed
parent_adjustment
redemption_spent
redemption_cancelled
system_adjustment
```

### Rewards

```text
Rewards
  GET   /api/rewards/items
  GET   /api/rewards/items/{itemId}
  POST  /api/rewards/items
  PATCH /api/rewards/items/{itemId}
  GET   /api/rewards/redemptions
  POST  /api/rewards/redemptions
  POST  /api/rewards/redemptions/{id}/fulfill
  POST  /api/rewards/redemptions/{id}/cancel
```

V1 redemption statuses:

```text
available
redeemed
fulfilled
cancelled
```

Reserved child-side request statuses:

```text
requested
pending_parent_approval
approved
rejected
```

### Dev Only

仅 `development/test + APP_ENABLE_DEV_ADAPTERS=1` 可用；production 不注册为真实业务入口。

```text
Dev
  POST /api/dev/tasks/scheduler/tick
  GET  /api/dev/tasks/scheduler/status
  POST /api/dev/camera/test-speak
  POST /api/dev/camera/test-snapshot
```

`POST /api/dev/tasks/scheduler/tick` 扫描今天及历史未终态任务：提前提醒、
到点自动开始、拖拉提醒、结束处理和历史补偿。摄像头离线时，任务状态仍合理
推进，同时写入 `reminder_failed`、`monitor_failed` 或
`observation_unavailable` 等事件。

`GET /api/dev/tasks/scheduler/status` 返回本地 scheduler runner 是否运行、
最近 tick 时间、下次 tick 时间和最近结果。

### AI / Prompt Registry

```text
AI
  GET /api/ai/config
  GET /api/ai/prompts
  GET /api/ai/models
  GET /api/ai/eval-cases
```

Prompt entries should include:

```json
{
  "id": "task.observation.summary",
  "version": "v1",
  "scenario": "task",
  "providerPolicy": "default",
  "status": "active"
}
```

### Firmware / OTA Reserved Boundary

V1 reserves structure and API boundaries only. It does not implement real
firmware upload, signing, rollout, or device-side execution.

```text
Firmware / OTA
  GET  /api/firmware/devices/{deviceId}/status
  GET  /api/firmware/packages
  POST /api/firmware/jobs
```

Firmware job detail, cancel, real package upload, signing, rollout, and device execution are future expansions.

Firmware states:

```text
available
scheduled
downloading
installing
success
failed
rollback_required
```

### Alerts

V1 only reserves the alert module boundary. Do not build a complete alert
business loop yet.

当前后端不提供完整 alerts API。Flutter V1 只展示普通告警摘要和状态；安全区域、安全事件详情和复杂事件流留到后续版本。
