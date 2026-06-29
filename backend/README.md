# AI Camera Parent App Backend

This backend is the parent-app API boundary. It owns app auth/session state,
first setup, tasks, points, rewards, device status, prompt registry, and reserved
camera/AI/OTA boundaries.

It intentionally does not expose RTSP, go2rtc, device private protocols, SMS
provider details, AI provider keys, or raw prompts to Flutter. Camera and
hardware integrations must stay behind backend adapters.

Local default port:

```text
App backend: http://127.0.0.1:8000
LAN access for real devices: http://<your-computer-lan-ip>:8000
```

Install and run:

```sh
cd backend
python3 -m pip install -r requirements.txt
cp .env.example .env
python3 scripts/migrate.py
python3 app.py
```

**本地联调（Guardian + ai_camera_test 媒体层 + 观察 worker，一条命令）：**

```sh
cd backend
chmod +x scripts/start-dev.sh   # 首次
./scripts/start-dev.sh
```

脚本会启动 ai_camera_test（go2rtc + gunicorn + speaker/voice/task，不含 monitor_worker）、
Guardian `app.py`（API :8000 + WS :8001）与 `camera_observation_worker`。
**默认会在终端实时输出 API 请求日志**（Flask/Werkzeug access log）；worker 日志在
`/tmp/guardian-dev/guardian-worker.log`。加 `--quiet` 可关闭终端日志跟屏。
按 Ctrl+C 停止 Guardian 进程。

Development defaults bind to `0.0.0.0` so an Android/iOS device on the same
network can reach the backend through the computer LAN IP. If an older local
`.env` still has `APP_HOST=127.0.0.1`, change it to `APP_HOST=0.0.0.0` and
restart the backend.

Production runtime expects a MySQL-compatible database. Create the database and
grant an application user before starting the service:

```sql
CREATE DATABASE IF NOT EXISTS ai_camera_app_dev
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE DATABASE IF NOT EXISTS ai_camera_app_test
  CHARACTER SET utf8mb4
  COLLATE utf8mb4_unicode_ci;

CREATE USER IF NOT EXISTS 'ai_camera_app'@'localhost'
  IDENTIFIED BY 'replace-with-a-strong-password';

GRANT ALL PRIVILEGES ON ai_camera_app_dev.* TO 'ai_camera_app'@'localhost';
GRANT ALL PRIVILEGES ON ai_camera_app_test.* TO 'ai_camera_app'@'localhost';
FLUSH PRIVILEGES;
```

Development manual debugging uses `ai_camera_app_dev`. Unit tests use
`ai_camera_app_test` and reset it. Production must set `APP_DATABASE_URL`
explicitly to a production database; the backend does not provide a production
fallback database URL.

Run tests:

```sh
cd backend
python3 -m unittest discover -s tests -t . -v
```

Tests use the isolated MySQL database configured by `APP_TEST_DATABASE_URL`
or the default local `ai_camera_app_test` database. The test runner resets that
database before each test case and then applies migrations. Development,
test, staging, and production all use MySQL.

Environment:

```text
APP_ENV=development
APP_DATABASE_URL=mysql+pymysql://ai_camera_app:ai_camera_app_dev@127.0.0.1:3306/ai_camera_app_dev?charset=utf8mb4
APP_TEST_DATABASE_URL=mysql+pymysql://ai_camera_app:ai_camera_app_dev@127.0.0.1:3306/ai_camera_app_test?charset=utf8mb4
APP_AUTH_ACCESS_SECONDS=900
APP_AUTH_REFRESH_SECONDS=2592000
APP_ENABLE_DEV_ADAPTERS=1
APP_SMS_PROVIDER=development
APP_HARDWARE_ADAPTER=disabled
APP_CAMERA_RUNTIME_ADAPTER=disabled
APP_AI_PROVIDER=
APP_AI_MODEL=
APP_AI_API_KEY=
APP_AI_BASE_URL=
APP_AI_TIMEOUT_SECONDS=8
```

Auth uses an `SmsProvider` abstraction. `DevelopmentSmsProvider` is allowed only
in development/test with `APP_ENABLE_DEV_ADAPTERS=1`; it generates a random
6-digit code and returns it in the API response for local development. Production
must configure a real SMS provider; otherwise SMS login returns a clear
provider-not-configured error.

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
stored in the configured production database and returns the next onboarding
step so Flutter can resume the flow after restart.

Account and profile APIs are available after login:

```text
GET   /api/account/profile
PATCH /api/account/profile
GET   /api/account/security
POST  /api/account/sessions/{sessionId}/revoke
POST  /api/account/phone/code
PATCH /api/account/phone
POST  /api/account/deletion
```

`/api/account/security` returns the current active login-device list. The app
may revoke non-current sessions; the current session cannot be removed from this
endpoint. Account deletion records a deletion request, marks the user account as
pending deletion, and revokes active sessions while preserving required audit
and statutory-retention boundaries.

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
  POST /api/points/stage-notice/ack

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

Camera access is wrapped by `CameraRuntimeAdapter`. The development/test profile
may opt in to `APP_CAMERA_RUNTIME_ADAPTER=ai_camera_test` with
`APP_CAMERA_BACKEND_URL`, but this bridge is not a production path. Production
defaults to `disabled` until a real camera runtime adapter is configured. Public
App contracts never return RTSP URLs, go2rtc URLs, old project paths, provider
keys, or raw prompt files.

Device status is wrapped by `HardwareDeviceAdapter`. Production defaults to
`disabled_hardware_device` until a real hardware adapter is configured. The
mock hardware adapter is development/test only. OTA creates scheduled V1
boundary jobs only; it does not upload, sign, roll out, execute, or verify
firmware on a real device.

Prompt files live under `backend/prompts/` and are referenced by
`prompt_id + version`. Routes and business code should load prompts through the
prompt registry instead of embedding prompt strings directly.

Task voice reminders use `task.reminder.voice:v1`. When `APP_AI_PROVIDER`,
`APP_AI_MODEL`, and `APP_AI_API_KEY` are configured, the backend asks the model
to generate a short child-facing reminder from task title, description, type,
phase, and age context. `kimi`/`moonshot` use the Moonshot-compatible chat API
(`APP_AI_BASE_URL` defaults to `https://api.moonshot.cn/v1` through the config
layer). If the model is unconfigured or unavailable, the backend falls back to a
local semantic reminder policy.

Camera vision analysis uses `vision.scene_observation:v1` via
`VisionObservationService` (`services/vision_observation_service.py`) and Kimi
K2.6 multimodal API. Configure:

```env
APP_AI_VISION_ENABLED=1
APP_AI_VISION_MODEL=          # optional, defaults to APP_AI_MODEL
APP_AI_VISION_TIMEOUT_SECONDS=20
APP_AI_VISION_MIN_INTERVAL_SECONDS=60
APP_AI_VISION_MAX_CALLS_PER_HOUR=20
```

The runtime adapter only fetches JPEG snapshots from `ai_camera_test`; analysis
no longer calls `/api/analyze_frame` on the legacy runtime.

## V1 Structure

The backend stays on Flask for now. It is organized as an App API boundary, not
a camera runtime rewrite.

```text
backend/
  app.py                  # Flask application factory and blueprint registration
  core/                   # config, database, errors, security helpers
  routes/api/v1/          # HTTP route layer
  services/               # business orchestration
  repositories/           # database and file-backed data access
  models/                 # internal dataclasses
  schemas/                # request/response shaping and validation helpers
  prompts/                # versioned prompt files
  migrations/             # MySQL SQL migrations
  scripts/migrate.py      # migration runner
  tests/                  # unittest coverage
```

Layering rules:

- Routes parse HTTP input and return HTTP responses only.
- Services own product behavior and call repositories/providers.
- Repositories own SQL or filesystem access.
- All environments use MySQL through `APP_DATABASE_URL` or
  `APP_TEST_DATABASE_URL`.
- Development, test, staging, and production should run migrations instead of
  relying on runtime schema creation.
- `tasks` is the only task/plan module. Do not add a separate day-plan domain.
- Flutter must call backend APIs rather than RTSP, go2rtc, SMS providers, AI
  provider keys, or raw prompt files directly.

Current database tables:

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
