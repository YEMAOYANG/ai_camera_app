# Mira Guardian App Backend API v1

更新日期：2026-06-03

本文档描述当前家长端 App 第一版已经实现或明确预留的后端接口。后端先采用轻量 Flask 服务，负责 App 登录态、首次设置、任务、积分、奖励、设备状态、摄像头测试后端桥接，以及 AI / Prompt / Firmware 的轻量边界。

摄像头底层运行能力仍由 `/Users/sqcopenclaw/.openclaw/workspace/ai_camera_test` 保持，当前 App 后端只通过 adapter/bridge 读取或代理必要状态。Flutter 合同只面向 App 后端 API，不直接暴露底层流媒体、硬件私有协议或旧测试项目路径。

## 认证模型

登录方式：手机号 + 短信验证码。

未注册手机号在验证码通过后自动创建家长用户和家庭账户。

Token：

- `accessToken`：短时访问令牌，默认 15 分钟。
- `refreshToken`：长时刷新令牌，默认 30 天。
- refresh 成功后会轮换 access token 和 refresh token，旧 refresh token 立即失效。
- App 启动时只要 refresh token 未过期，就不回到登录页。
- 普通 API 请求 access token 过期时，客户端自动调用 refresh 接口并重试一次。

开发验证码：

```text
MIRA_AUTH_DEV_SMS_CODE=0426
```

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
  "debugCode": "0426",
  "message": "验证码已发送"
}
```

### POST `/api/auth/sms/login`

手机号验证码登录。未注册手机号验证通过后自动创建家庭账户。

Request:

```json
{
  "phone": "13800002026",
  "code": "0426"
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

Bridge 目标由环境变量控制：

```text
MIRA_CAMERA_BACKEND_URL=http://127.0.0.1:8767
```

### GET `/api/camera/health`

代理原测试后端 `/api/health`，用于确认摄像头、voice runtime、monitor runtime、speaker runtime 是否可达。

### GET `/api/camera/runtime`

代理原测试后端 `/api/voice/runtime`，用于 App 或调试页读取唤醒监听和语音交互状态。

### GET `/api/camera/speaker/status`

代理原测试后端 `/api/camera/speaker/status`，用于读取喇叭播放队列、busy、cooldown 和错误。

### GET `/api/camera/snapshot`

代理原测试后端 `/api/camera/snapshot`，返回 JPEG。用于 App 看护页后续接真实画面预览。

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
```

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
  PATCH  /api/tasks/{id}
  POST   /api/tasks/{id}/complete
  POST   /api/tasks/{id}/parent-confirm
  POST   /api/tasks/{id}/reject-confirmation
```

Task templates, pause/delay, and standalone evidence endpoints are future expansions. V1 evidence summary is embedded in task payloads.

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

### Camera

Flutter should call backend camera APIs, not underlying stream/runtime protocols directly. V1 does not expose a separate `watch` module.

```text
Camera Bridge
  GET  /api/camera/health
  GET  /api/camera/snapshot
  GET  /api/camera/stream
  GET  /api/camera/runtime
```

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
