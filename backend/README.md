# Mira Guardian App Backend

This lightweight backend is the parent-app API boundary. It owns app auth/session
state and proxies selected camera runtime endpoints to the existing
`ai_camera_test` Flask service.

It intentionally does not copy or replace the camera runtime. Keep RTSP, go2rtc,
voice wake, camera speaker, monitor workers, and prompt policy in:

```text
/Users/sqcopenclaw/.openclaw/workspace/ai_camera_test
```

Default ports:

```text
Mira app backend:        http://127.0.0.1:8000
ai_camera_test backend:  http://127.0.0.1:8767
```

Install and run:

```sh
cd backend
python3 -m pip install -r requirements.txt
python3 app.py
```

Run tests:

```sh
cd backend
python3 -m unittest discover -s tests -v
```

Environment:

```text
MIRA_AUTH_DEV_SMS_CODE=0426
MIRA_AUTH_ACCESS_SECONDS=900
MIRA_AUTH_REFRESH_SECONDS=2592000
MIRA_CAMERA_BACKEND_URL=http://127.0.0.1:8767
```

Auth uses an `SmsProvider` abstraction. The default implementation is
`MockSmsProvider`, which keeps the dev verification code stable while reserving
room for Aliyun, Tencent Cloud, Ronglian, Twilio, or another SMS provider.

Setup V1 is available after login:

```text
GET  /api/setup/status
POST /api/setup/parent-identity
POST /api/setup/device
POST /api/setup/wifi
POST /api/setup/child
POST /api/setup/contacts
POST /api/setup/complete
```

All setup APIs require `Authorization: Bearer <accessToken>`. Setup data is
stored in SQLite and returns the next onboarding step so Flutter can resume the
flow after restart.

Tasks, points, rewards, and redemptions V1 are available after login:

```text
Tasks
  GET   /api/tasks/today
  GET   /api/tasks
  GET   /api/tasks/{taskId}
  POST  /api/tasks
  PATCH /api/tasks/{taskId}
  POST  /api/tasks/{taskId}/complete
  POST  /api/tasks/{taskId}/parent-confirm
  POST  /api/tasks/{taskId}/reject-confirmation

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
```

Task completion enters `awaiting_parent_confirmation`. Parent confirmation
marks the task as `confirmed`, grants task reward points, and writes the point
ledger. Reward redemption deducts points. Cancelling an unfulfilled redemption
returns points through a ledger entry. Fulfillment only marks the redemption as
delivered and does not change points.

Device, camera runtime, AI, SMS, and firmware boundaries:

```text
Device
  GET /api/devices
  GET /api/devices/{deviceId}
  GET /api/devices/{deviceId}/status

Camera
  GET /api/camera/health
  GET /api/camera/snapshot
  GET /api/camera/stream
  GET /api/camera/runtime

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

Camera access is wrapped by `CameraRuntimeAdapter`. The current implementation
can bridge the old `ai_camera_test` backend, but public App contracts never
return RTSP URLs, go2rtc URLs, old project paths, provider keys, or raw prompt
files. Device status is wrapped by `HardwareDeviceAdapter`; V1 uses a mock
adapter and reserves room for future self-developed hardware. OTA creates
scheduled mock jobs only; it does not upload, sign, roll out, execute, or verify
firmware on a real device.

Prompt files live under `backend/prompts/` and are referenced by
`prompt_id + version`. Routes and business code should load prompts through the
prompt registry instead of embedding prompt strings directly.

## V1 Structure

The backend stays on Flask for now. It is organized as an App API boundary, not
a camera runtime rewrite.

```text
backend/
  app.py                  # Flask application factory and blueprint registration
  core/                   # config, database, errors, security helpers
  routes/api/v1/          # HTTP route layer
  services/               # business orchestration
  repositories/           # SQLite and file-backed data access
  models/                 # internal dataclasses
  schemas/                # request/response shaping and validation helpers
  prompts/                # versioned prompt files
  tests/                  # unittest coverage
```

Layering rules:

- Routes parse HTTP input and return HTTP responses only.
- Services own product behavior and call repositories/providers.
- Repositories own SQL or filesystem access.
- SQLite remains acceptable for V1, but route handlers must not write SQL.
- `tasks` is the only task/plan module. Do not add a separate day-plan domain.
- Flutter must call backend APIs rather than RTSP, go2rtc, SMS providers, AI
  provider keys, or raw prompt files directly.

Current SQLite tables:

```text
families
users
sms_codes
sessions
setup_progress
parent_identities
devices
wifi_configs
children
emergency_contacts
tasks
point_accounts
point_ledger
reward_items
reward_redemptions
firmware_packages
firmware_jobs
```
