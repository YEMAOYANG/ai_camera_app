# Mira Guardian V1 Scope and Architecture Assessment

更新日期：2026-06-03

## 1. Reference Priority

Business flow, page inventory, state references, and interaction intent use `app-prototype-v4/index.html` as the current source of truth. Product documents remain required context, but when they conflict with v4 the default is to follow v4.

`app-prototype-v4` is a business and interaction reference, not a visual system that must be copied blindly. If the prototype contains an obviously unreasonable flow, copy, state, or page boundary, the implementation should explain the reason and adjust using README/docs product judgment.

## 2. Prototype Page Map

### First Use

- `welcome` 欢迎页
- `login` 登录注册
- `parentIdentity` 家长身份
- `bind` 扫码绑定
- `wifi` Wi-Fi 配网
- `bindDone` 绑定成功
- `child` 孩子档案
- `name` 摄像头命名
- `contacts` 紧急联系人

### Home Workbench

- `home` 首页
- `care` 协作待办
- `sleep` 睡眠晨起

### Tasks

- `flow` 任务模板
- `packing` 小书包
- `tasks` 任务日历
- `taskDetail` 任务详情
- `focus` 专注计时

`flow`, `packing`, `sleep`, and `focus` are task subflows or task-type views. They must not become a separate day-plan domain.

### Care and Events

- `watch` 实时看护
- `playback` 事件回放
- `zones` 安全区域
- `safety` 安全事件
- `safetyDetail` 事件详情

### My / Settings

- `my` 我的总览
- `accountProfile` 个人信息
- `accountSecurity` 账号安全
- `subscription` 订阅套餐
- `report` 日报
- `weekly` 周报
- `moments` 成长时刻
- `points` 积分
- `reward` 奖励商店
- `checkin` 打卡审核
- `conversation` 对话人设
- `privacy` 隐私权限
- `notifications` 通知设置
- `family` 家庭成员
- `device` 设备管理
- `education` 学习内容
- `feedback` 帮助与反馈
- `about` 关于我们
- `settings` 设备与规则聚合

## 3. Main Flow

```text
welcome
  -> login
  -> parentIdentity
  -> bind
  -> wifi
  -> bindDone
  -> child
  -> name
  -> contacts
  -> home
```

After setup, bottom navigation focuses on:

```text
home / tasks / watch / my
```

Global task creation can be a floating or bottom action. It is not an independent tab domain.

## 4. V1 Must Build

- welcome/onboarding
- phone SMS login
- automatic family account creation for new phone numbers
- parent identity setup
- device binding entry
- Wi-Fi configuration
- binding complete state
- child profile
- emergency contacts
- home core care status
- today task summary on home
- task list
- task detail
- task completion
- parent task confirmation
- task reward point grant
- basic live-care entry
- camera basic status
- point account
- point ledger
- reward item list
- reward item detail
- reward redemption
- redemption records
- parent manual fulfillment
- settings/profile
- user agreement
- privacy policy

## 5. V1 Reserve Structure Only

- alert center
- safety alert
- safety zone
- safety event
- child-side reward request
- parent approval of child-side reward request
- real hardware OTA execution
- real SMS provider integration
- complex AI eval backend UI
- complex growth reports
- payment
- inventory
- logistics
- order fulfillment

## 6. Do Not Build

- standalone day-plan domain
- separate day-plan table/domain/API
- Flutter feature for a separate day-plan module
- any plan system duplicating tasks

## 7. Current Validation Status

- `README.md` now describes the current V1 backend/Flutter contract instead of the older broad roadmap API list.
- `docs/backend_api.md` separates implemented V1 APIs from reserved future boundaries.
- `docs/mira_guardian_app_design_guidelines.md` and broader product docs may still describe future product directions, but V1 implementation must keep day-specific content inside `tasks`.
- Older prototypes v2/v3 are not current references.
- Flutter home now renders "今日任务摘要" from `tasks/today`; there is no standalone day-plan feature or API.

## 8. Flow Adjustments

`flow` should be treated as task templates, not a business domain named flow.

`packing`, `sleep`, and `checkin` can be task types or task subviews. They can have dedicated screens for ergonomics, but they should share task scheduling, status, evidence, and reward logic.

Child voice reward requests can be represented in V1 as a camera-originated pending item or redemption state. Because there is no child App, the complete child request UI and full approval loop can wait.

## 9. Backend Long-Term Architecture

Recommended direction:

```text
backend/
  app/
    main.py
    core/
      config.py
      database.py
      errors.py
      logging.py
      security.py
    api/v1/
      auth.py
      setup.py
      families.py
      children.py
      devices.py
      camera.py
      tasks.py
      rewards.py
      points.py
      ai.py
      firmware.py
    domain/
      users/
      families/
      children/
      devices/
      camera/
      tasks/
      rewards/
      points/
      ai/
      firmware/
      notifications/
    services/
      auth_service.py
      setup_service.py
      device_service.py
      task_service.py
      reward_service.py
      point_service.py
      camera/
        camera_service.py
        stream_service.py
        snapshot_service.py
        speaker_service.py
        monitor_service.py
      ai/
        ai_orchestrator.py
        model_registry.py
        prompt_registry.py
        policy_engine.py
        eval_service.py
      firmware/
        firmware_service.py
        ota_job_service.py
      notifications/
        sms_service.py
        sms_provider.py
    integrations/
      camera_runtime/
        ai_camera_test_adapter.py
        go2rtc_client.py
      ai_providers/
        openai_client.py
        kimi_client.py
        minimax_client.py
      sms_providers/
        mock_sms_provider.py
        aliyun_sms_provider.py
        tencent_sms_provider.py
      firmware_storage/
        local_firmware_storage.py
    repositories/
    schemas/
    models/
    prompts/
      system/
      vision/
      voice/
      monitor/
      task/
      safety/
    tests/
```

Current lightweight backend can evolve toward this structure over time. It should not copy `ai_camera_test` wholesale; camera runtime stays behind adapters.

## 10. Task Domain Design

Task is the only plan/schedule/to-do domain.

Task fields:

- `taskId`
- `familyId`
- `childId`
- `title`
- `description`
- `taskType`
- `scheduleType`
- `dueAt`
- `startAt`
- `repeatRule`
- `status`
- `priority`
- `rewardPoints`
- `requiresParentConfirmation`
- `completionSource`
- `evidence`
- `aiObservationSummary`
- `createdBy`
- `createdAt`
- `updatedAt`

Task statuses:

- `pending`
- `in_progress`
- `completed`
- `awaiting_parent_confirmation`
- `confirmed`
- `rejected`
- `expired`
- `cancelled`

Task types:

- learning
- housework/life
- sleep
- schoolbag
- checkin
- parent confirmation
- AI observed

## 11. Points, Rewards, and Redemption V1

Data models:

- `point_account`
- `point_ledger`
- `reward_item`
- `reward_category`
- `redemption`
- `redemption_status`
- `reward_rule`
- `task_reward_rule`

Ledger types:

- `task_completed`
- `parent_adjustment`
- `redemption_spent`
- `redemption_cancelled`
- `system_adjustment`

Reward item fields:

- `id`
- `familyId`
- `childId`
- `title`
- `description`
- `pointsCost`
- `category`
- `status`
- `cover/icon`
- `createdBy`
- `createdAt`
- `updatedAt`

Redemption fields:

- `id`
- `childId`
- `rewardItemId`
- `pointsCost`
- `status`
- `requestedBy`
- `approvedBy`
- `fulfilledBy`
- `requestedAt`
- `approvedAt`
- `fulfilledAt`

V1 redemption statuses:

- `available`
- `redeemed`
- `fulfilled`
- `cancelled`

Future child-side statuses:

- `requested`
- `pending_parent_approval`
- `approved`
- `rejected`

## 12. AI and Prompt Abstraction

V1 should reserve:

- AI provider registry
- model registry
- prompt registry
- prompt version
- scenario config
- policy engine
- eval case
- eval result

Prompt requirements:

- prompt files are directory managed
- prompts have id/version
- business code references prompt id/version
- at least minimal eval/test cases exist
- scenarios distinguish learning, tasks, live care, voice, vision, and parent confirmation

V1 does not need complex AI eval UI. V1 should provide CLI/tests or structured fixtures so prompt changes can be regression checked.

## 13. Device and Hardware Abstraction

Device fields:

- `deviceId`
- `familyId`
- `hardwareModel`
- `firmwareVersion`
- `serialNumber`
- `pairingCode`
- `capabilities`
- `online/offline`
- `networkStatus`
- `cameraStatus`
- `micStatus`
- `speakerStatus`
- `aiRuntimeStatus`
- `lastSeenAt`
- `configVersion`

Capabilities:

- `live_stream`
- `snapshot`
- `speaker_playback`
- `mic_capture`
- `wake_word`
- `local_ai`
- `cloud_ai`
- `ota_update`
- `child_presence_detection`
- `task_observation`
- `safety_event_detection`

Reserve device auth, heartbeat, state reports, config downlink, command dispatch and receipt, OTA, and capability differences.

## 14. OTA Reservation

Data models:

- `firmware_package`
- `firmware_version`
- `device_firmware_status`
- `ota_job`
- `ota_job_status`
- `rollout_policy`
- `device_update_command`
- `device_update_result`

States:

- `available`
- `scheduled`
- `downloading`
- `installing`
- `success`
- `failed`
- `rollback_required`

Current implemented API boundary:

- `GET /api/firmware/devices/{deviceId}/status`
- `GET /api/firmware/packages`
- `POST /api/firmware/jobs`

Future OTA expansion:

- `GET /api/firmware/jobs/{jobId}`
- `POST /api/firmware/jobs/{jobId}/cancel`

## 15. SMS Provider Reservation

Keep API stable:

- `POST /api/auth/sms/request`
- `POST /api/auth/sms/login`

Backend provider abstraction:

- `SmsProvider` interface
- `MockSmsProvider`
- provider config
- template id
- rate limit
- resend cooldown
- delivery status
- error mapping

Future providers should not change Flutter login logic.

## 16. V1 API Contract Draft

```text
Auth
  POST /api/auth/sms/request
  POST /api/auth/sms/login
  POST /api/auth/token/refresh
  GET  /api/auth/session
  POST /api/auth/logout

Setup
  GET  /api/setup/status
  POST /api/setup/parent-identity
  POST /api/setup/device
  POST /api/setup/wifi
  POST /api/setup/child
  POST /api/setup/contacts
  POST /api/setup/complete

Device / Camera
  GET /api/devices
  GET /api/devices/{deviceId}
  GET /api/devices/{deviceId}/status
  GET /api/camera/health
  GET /api/camera/snapshot
  GET /api/camera/stream
  GET /api/camera/runtime

Tasks
  GET  /api/tasks/today
  GET  /api/tasks
  GET  /api/tasks/{taskId}
  POST /api/tasks
  PATCH /api/tasks/{taskId}
  POST /api/tasks/{taskId}/complete
  POST /api/tasks/{taskId}/parent-confirm
  POST /api/tasks/{taskId}/reject-confirmation

Points
  GET  /api/points/account
  GET  /api/points/ledger
  POST /api/points/adjust

Rewards
  GET   /api/rewards/items
  GET   /api/rewards/items/{itemId}
  POST  /api/rewards/items
  PATCH /api/rewards/items/{itemId}
  GET   /api/rewards/redemptions
  POST  /api/rewards/redemptions
  POST  /api/rewards/redemptions/{id}/fulfill
  POST  /api/rewards/redemptions/{id}/cancel

AI
  GET /api/ai/config
  GET /api/ai/prompts
  GET /api/ai/models
  GET /api/ai/eval-cases

Firmware / OTA
  GET  /api/firmware/devices/{deviceId}/status
  GET  /api/firmware/packages
  POST /api/firmware/jobs
```

Alerts remain a reserved boundary in V1.

## 17. Flutter Integration Direction

Flutter should reuse Dio, API client, auth repository, session store, and go_router. Pages should not know backend base URLs.

Startup gate should combine:

- `hasSeenOnboarding`
- auth session
- backend setup status
- device binding status

Feature data should come from repositories/use cases:

- auth repository
- setup repository
- device repository
- camera repository
- task repository
- point repository
- reward repository
- AI summary repository

Flutter must not directly access RTSP, go2rtc, device private protocol, SMS provider, AI provider key, or raw prompt content.
