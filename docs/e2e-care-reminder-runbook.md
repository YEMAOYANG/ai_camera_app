# E2E 作息提醒 / 摄像头能力联调 Runbook

本文档描述本地 dev 环境下，验证「决策 → internal trigger → speaker command → WebSocket → App/REST 记录」的端到端步骤。

**范围：** 仅联调验收，不含 UI 信息架构收口或 trigger 合同简化。

---

## 架构分工（必读）

| 组件 | 职责 |
|------|------|
| **Guardian App 后端** (`backend/app.py`) | REST API、`/internal/*`、policy、reminder、WebSocket |
| **`camera_observation_worker`** | 从 `ai_camera_test` 拉 snapshot → OpenCV/YOLO prefilter → Kimi（按需）→ POST `/internal/camera/observations` |
| **`ai_camera_test`** | 摄像头 runtime：**snapshot / stream / speaker / status**；**不负责** observation push 到 Guardian（联调默认走 worker 路径） |

若 `ai_camera_test` 侧 `CAMERA_OBSERVATION_PUSH_ENABLED=0`，只要 Guardian worker 正常，observation 链路仍可联调。

---

## 前置条件

### 后端 `.env` 关键项

```env
CAMERA_RUNTIME_PROVIDER=ai_camera_test
AI_CAMERA_TEST_BASE_URL=http://127.0.0.1:8767
INTERNAL_API_TOKEN=<your-internal-token>
TASK_WEBSOCKET_ENABLED=1
CARE_ROUTINE_REMINDER_ENABLED=1

# observation worker（与 App 绑定设备一致）
CAMERA_OBSERVATION_INTERNAL_URL=http://127.0.0.1:8000
CAMERA_OBSERVATION_FAMILY_ID=<family-id>
CAMERA_OBSERVATION_CHILD_ID=<child-id>
CAMERA_OBSERVATION_DEVICE_ID=<device-id>
```

### 端口

| 服务 | 地址 |
|------|------|
| Guardian API | `http://127.0.0.1:8000/api` |
| Guardian WebSocket | `ws://127.0.0.1:8001/api/tasks/stream` |
| ai_camera_test | `http://127.0.0.1:8767` |

### YOLO 模型

Worker 启动前需要 `backend/assets/vision/yolov8n.onnx`。缺失时：

```sh
cd backend
pip install ultralytics onnxruntime
python scripts/export_yolov8n_onnx.py
```

`start-dev.sh` 也会在缺失时尝试一次性导出。

---

## 启动

### 方式 A：一键脚本（推荐首次）

```sh
cd backend
./scripts/start-dev.sh
```

会拉起 ai_camera_test（可选）、Guardian API、WebSocket、observation worker 等。

### 方式 B：screen 会话（长时间联调）

典型会话名：

- `guardian_app` — Guardian API + WS
- `guardian_worker` — observation worker
- `ai_camera_server` — ai_camera_test HTTP
- `ai_camera_go2rtc` — 媒体层

停止 Guardian 后端示例：

```sh
screen -S guardian_app -X quit
screen -S guardian_worker -X quit
```

### 启动后检查

1. `ai_camera_test`：摄像头 connected、speaker enabled、talk stream ready
2. Snapshot：`GET http://127.0.0.1:8767/api/camera/snapshot?format=data_url` → 200
3. Worker 日志：稳定画面可能出现 `session_stable` / `cloud_gate_person_stable` 跳过（gate 正常）

---

## 1. 登录（dev SMS）

使用 **dev SMS 登录测试账号**（如已配置的联调手机号），通过 App 或 API：

```sh
# 请求验证码（dev 环境返回 debugCode）
curl -s -X POST http://127.0.0.1:8000/api/auth/sms/request \
  -H 'Content-Type: application/json' \
  -d '{"phone":"<QA_PHONE>"}'

# 登录（code 用上一步 debugCode）
curl -s -X POST http://127.0.0.1:8000/api/auth/sms/login \
  -H 'Content-Type: application/json' \
  -d '{"phone":"<QA_PHONE>","code":"<DEBUG_CODE>"}'
```

后续 REST 请求使用 `Authorization: Bearer <ACCESS_TOKEN>`。**不要把 token 写入文档或提交到 Git。**

快捷脚本：`backend/scripts/qa-integration.sh`（需先设置 `QA_PHONE` 与 `CAMERA_OBSERVATION_DEVICE_ID`；封装登录 + monitor refresh + routine tick + WS 探测）。

---

## 2. WebSocket 订阅

连接（token 通过 query 或项目现有鉴权方式）：

```text
ws://127.0.0.1:8001/api/tasks/stream?token=<ACCESS_TOKEN>
```

联调时关注的事件类型：

| 场景 | 典型事件 |
|------|----------|
| Observation / policy | `camera_observation.updated`、`reminder_decision.created` |
| 提醒成功 | `reminder_event.created`、`camera_command.created` |
| 画面事件（如有） | `camera_event.created` |

---

## 3. 作息提醒链路

### 3.1 触发 routine tick（dev）

需要已登录家长的 Bearer token：

```sh
curl -s -X POST http://127.0.0.1:8000/api/dev/care/routine-reminder/tick \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{"now": <unix_ms_in_routine_window>}'
```

`now` 可选；省略则使用服务器当前时间。响应中查看 `responses[]`：

- `observation.scenario` — 如 `bedtime`、`wake_up`
- `decision.decision` — `allowed` / `skipped_cooldown` / `skipped_out_of_routine_window` 等
- `decision.shouldSpeak` — 是否允许播报
- `reminderDecisionId` — 供 internal trigger 使用

**注意：** dev tick 可能扫描多个家庭候选，会在 dev 环境产生多条记录；生产用户路径不同。

### 3.2 Internal trigger（speaker）

仅当 decision 为 **`allowed` 且 `shouldSpeak=true`** 且未过期时调用：

```sh
curl -s -X POST http://127.0.0.1:8000/internal/reminders/trigger \
  -H 'Authorization: Bearer <INTERNAL_API_TOKEN>' \
  -H 'Content-Type: application/json' \
  -d '{
    "familyId": "<FAMILY_ID>",
    "childId": "<CHILD_ID>",
    "deviceId": "<DEVICE_ID>",
    "scenario": "bedtime",
    "reminderDecisionId": "<DECISION_ID>"
  }'
```

当前合同要求显式传 `familyId`、`childId`、`scenario`、`reminderDecisionId`（及 device 上下文）。重复 trigger 同一 decision 应幂等。

### 3.3 成功路径预期

HTTP 200，例如：

- `reminder.deliveryStatus` = `command_sent`
- `command.status` = `command_sent`（或等价成功态）
- `command.cameraCommandStatus` = `succeeded`
- `reminder.commandId` 非空（如 `cmd_...`）

WebSocket 应收到：

- `reminder_event.created`
- `camera_command.created`

REST 验证：

```sh
# 看护记录（camera events）
curl -s 'http://127.0.0.1:8000/api/camera/events?deviceId=<DEVICE_ID>' \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'

# 提醒事件
curl -s 'http://127.0.0.1:8000/api/reminders/events' \
  -H 'Authorization: Bearer <ACCESS_TOKEN>'
```

成功示例字段：

- camera events：`displayTitle` 如「已提醒准备睡觉」；`displayMessage` 含播报文案
- reminder events：`scenario=bedtime`，`deliveryStatus=command_sent`

App 侧：首页 / 看护页 / 看护记录应在 WebSocket 推送后刷新，无需杀进程重进。

### 3.4 失败路径预期（cooldown）

routine tick 返回 `decision.decision=skipped_cooldown`（或其它非 allowed）时：

```sh
curl -s -X POST http://127.0.0.1:8000/internal/reminders/trigger ...
```

应返回 **409**，`error=reminder_decision_not_allowed`。

WebSocket 仍可能有 `camera_observation.updated`、`reminder_decision.created`，但**不应**产生成功的 `reminder_event.created` + speak command。

### 3.5 失败路径预期（speaker 离线 / command failed）

command 返回 `status=failed` 时：

- `reminder.deliveryStatus` = `failed`
- `failureReason` 含明确原因（如「提醒没有播出」）
- **不得**伪装为成功

---

## 4. 摄像头能力链路（posture / toy / meal_habit）

由 **observation worker tick** 驱动（非 routine tick）：

1. Worker 拉 snapshot → prefilter → cloud gate → 按需 Kimi
2. Policy 产出 decision
3. 若 allowed + shouldSpeak，由 policy/observation 路径触发 internal trigger（与 contract 测试一致）
4. 同样验证 WS + `/api/camera/events` + `/api/reminders/events`

稳定空房间 / 无 motion 时，worker 日志应显示 gate 跳过，避免每分钟 Kimi。

---

## 5. Freshness（App 展示）

Monitor API 的 `lastObservation.freshness`：

| 值 | App 行为 |
|----|----------|
| `fresh` | 可作为「当前正在…」 |
| `stale` | 「约 X 分钟前观察到…」 |
| `prefilter_only` | 不展示旧 Kimi 结论为当前状态 |

---

## 6. 提交前自动化（checkpoint 门禁）

```sh
cd backend
python3 -m unittest \
  tests.test_care_observation_contract \
  tests.test_camera_observe_cloud_gate_tick \
  tests.test_observation_cloud_gate \
  tests.test_monitor_observation_freshness \
  tests.test_observation_runtime_display \
  tests.test_care_routine_window_resolver \
  tests.test_care_policy_meal_habit_window \
  -v

cd ../mobile
flutter analyze
flutter test

cd ..
git diff --check
```

全量 `python3 -m unittest discover` 中的无关红项（vision regression、profile wakeName 等）**不纳入**本次联调验收。

---

## 7. 已知限制 / 后续项（checkpoint 后）

- internal trigger 合同简化（仅传 `familyId + reminderDecisionId`）
- dev routine tick 按 family/device 过滤
- 看护记录「画面观察 vs 能力提醒」视觉分层
- `track-ui-ia` 信息架构收口
- slice 5 lightweight absent（可选）

---

## 修订记录

| 日期 | 说明 |
|------|------|
| 2026-06-29 | 首次 E2E 联调通过：bedtime allowed → speak succeeded；cooldown 拒绝路径验证 |
