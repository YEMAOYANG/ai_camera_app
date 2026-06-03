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

Run:

```sh
cd backend
python -m pip install -r requirements.txt
python app.py
```

Environment:

```text
MIRA_AUTH_DEV_SMS_CODE=0426
MIRA_AUTH_ACCESS_SECONDS=900
MIRA_AUTH_REFRESH_SECONDS=2592000
MIRA_CAMERA_BACKEND_URL=http://127.0.0.1:8767
```
