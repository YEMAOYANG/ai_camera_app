# Mira Guardian App Backend API v1

更新日期：2026-06-02

本文档描述当前家长端 App 第一版需要的后端接口。后端先采用轻量 Flask 服务，负责 App 登录态、家庭账户启动数据和摄像头测试后端桥接。

摄像头能力仍由 `/Users/sqcopenclaw/.openclaw/workspace/ai_camera_test` 保持：RTSP、go2rtc、语音唤醒、摄像头喇叭、实时观察、任务 runtime 和 prompt policy 不在本仓库重写。当前 App 后端只通过 bridge 读取或代理必要状态。

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

## 后续 App 业务接口规划

认证完成后，业务接口统一使用 `Authorization: Bearer <accessToken>`。

第一版后续建议按以下边界落地：

```text
Family
  GET    /api/families/current
  POST   /api/families
  POST   /api/families/invite
  PATCH  /api/families/members/{id}

Device
  GET    /api/devices
  POST   /api/devices/bind
  PATCH  /api/devices/{id}
  POST   /api/devices/{id}/privacy

Child
  GET    /api/children
  POST   /api/children
  PATCH  /api/children/{id}

Tasks
  GET    /api/tasks/today
  POST   /api/tasks
  PATCH  /api/tasks/{id}
  POST   /api/tasks/{id}/pause
  POST   /api/tasks/{id}/delay
  POST   /api/tasks/{id}/complete
  GET    /api/tasks/{id}/evidence
  POST   /api/tasks/{id}/confirm
  POST   /api/tasks/{id}/reject

Watch
  GET    /api/watch/status
  POST   /api/watch/snapshot
  POST   /api/watch/talk/start
  POST   /api/watch/talk/end

Alerts
  GET    /api/alerts
  PATCH  /api/alerts/{id}/read
  PATCH  /api/alerts/{id}/resolve
```
