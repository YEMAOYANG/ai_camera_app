from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import create_app
from tests.support import fresh_test_config, request_debug_code


class _CameraRuntimeHandler(BaseHTTPRequestHandler):
    speak_count = 0
    monitor_running = False

    def do_GET(self):
        if self.path == "/api/health":
            self._json(
                {
                    "ok": True,
                    "service": "fake-camera-runtime",
                    "keys": {"kimi": "set:51"},
                    "camera": {
                        "configured": True,
                        "connected": True,
                        "name": "测试摄像头",
                        "go2rtc_base": "http://127.0.0.1:1984",
                        "preview_stream": "ipc45aw_hd",
                        "webrtc": {
                            "enabled": True,
                            "local_url": "http://127.0.0.1:1984/stream.html?src=x",
                            "stream": "ipc45aw_hd",
                        },
                    },
                }
            )
            return
        if self.path == "/api/voice/runtime":
            self._json({"ok": True, "voice": {"state": "idle", "running": False}})
            return
        if self.path == "/api/camera/speaker/status":
            self._json({"ok": True, "speaker": {"busy": False}})
            return
        if self.path == "/api/monitor/runtime":
            self._json(
                {
                    "ok": True,
                    "monitor_runtime": {
                        "running": self.__class__.monitor_running,
                        "status": "running" if self.__class__.monitor_running else "idle",
                    },
                }
            )
            return
        if self.path == "/api/camera/snapshot":
            body = b"\xff\xd8\xff\xd9"
            self.send_response(200)
            self.send_header("Content-Type", "image/jpeg")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def do_POST(self):
        if self.path == "/api/camera/speaker/speak":
            self.__class__.speak_count += 1
            self._json({"ok": True, "speaker": {"queued": True}})
            return
        if self.path == "/api/monitor/start":
            self.__class__.monitor_running = True
            self._json({"ok": True, "monitor_runtime": {"running": True, "status": "running"}})
            return
        if self.path == "/api/monitor/stop":
            self.__class__.monitor_running = False
            self._json({"ok": True, "monitor_runtime": {"running": False, "status": "stopped"}})
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):
        return

    def _json(self, payload: dict):
        body = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


class DevicesCameraAiFirmwareApiTest(unittest.TestCase):
    def setUp(self):
        _CameraRuntimeHandler.speak_count = 0
        _CameraRuntimeHandler.monitor_running = False
        self.camera_server = ThreadingHTTPServer(("127.0.0.1", 0), _CameraRuntimeHandler)
        self.camera_thread = threading.Thread(target=self.camera_server.serve_forever, daemon=True)
        self.camera_thread.start()
        self.camera_url = f"http://127.0.0.1:{self.camera_server.server_port}"
        self.app = create_app(
            fresh_test_config(
                HARDWARE_ADAPTER="mock",
                CAMERA_RUNTIME_ADAPTER="ai_camera_test",
                CAMERA_BACKEND_URL=self.camera_url,
            )
        )
        self.client = self.app.test_client()
        self.access_token = self._login()
        self.device_id = self._create_device()

    def tearDown(self):
        self.camera_server.shutdown()
        self.camera_server.server_close()

    def test_devices_status_mock(self):
        devices = self.client.get("/api/devices", headers=self._auth_headers())
        self.assertEqual(devices.status_code, 200)
        self.assertEqual(len(devices.json["devices"]), 1)

        detail = self.client.get(f"/api/devices/{self.device_id}", headers=self._auth_headers())
        self.assertEqual(detail.status_code, 200)
        self.assertEqual(detail.json["device"]["id"], self.device_id)

        status = self.client.get(
            f"/api/devices/{self.device_id}/status",
            headers=self._auth_headers(),
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["status"]["connectionStatus"], "online")
        self.assertEqual(status.json["status"]["adapter"], "mock_hardware_device")

    def test_camera_health_adapter_reachable_and_unreachable(self):
        reachable = self.client.get("/api/camera/health")
        self.assertEqual(reachable.status_code, 200)
        self.assertTrue(reachable.json["cameraRuntime"]["reachable"])
        self.assertEqual(reachable.json["cameraRuntime"]["adapter"], "ai_camera_test_bridge")
        self.assertEqual(reachable.json["cameraRuntime"]["data"]["service"], "fake-camera-runtime")
        self.assertNotIn("keys", reachable.json["cameraRuntime"]["data"])
        self.assertNotIn("go2rtc_base", reachable.json["cameraRuntime"]["data"]["camera"])
        self.assertNotIn("source", reachable.json["cameraRuntime"]["data"]["camera"])

        unreachable_app = create_app(
            fresh_test_config(
                CAMERA_RUNTIME_ADAPTER="ai_camera_test",
                CAMERA_BACKEND_URL="http://127.0.0.1:1",
            )
        )
        unreachable = unreachable_app.test_client().get("/api/camera/health")
        self.assertEqual(unreachable.status_code, 502)
        self.assertFalse(unreachable.json["cameraRuntime"]["reachable"])

    def test_camera_status_snapshot_commands_and_monitor(self):
        status = self.client.get("/api/camera/status", headers=self._auth_headers())
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["status"]["connectionStatus"], "online")
        self.assertTrue(status.json["status"]["speakerAvailable"])
        self.assertEqual(status.json["status"]["runtimeProvider"], "ai_camera_test_bridge")

        snapshot = self.client.get("/api/camera/snapshot", headers=self._auth_headers())
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.content_type, "image/jpeg")

        speak = self.client.post(
            "/api/camera/commands/speak",
            json={"text": "准备开始任务"},
            headers=self._auth_headers(),
        )
        self.assertEqual(speak.status_code, 200)
        self.assertEqual(speak.json["command"]["commandType"], "speak")
        self.assertEqual(speak.json["command"]["status"], "succeeded")
        self.assertEqual(_CameraRuntimeHandler.speak_count, 1)

        start = self.client.post("/api/camera/monitor/start", headers=self._auth_headers())
        self.assertEqual(start.status_code, 200)
        self.assertEqual(start.json["command"]["commandType"], "start_monitor")
        self.assertEqual(start.json["command"]["status"], "succeeded")

        monitor = self.client.get("/api/camera/monitor/status", headers=self._auth_headers())
        self.assertEqual(monitor.status_code, 200)
        self.assertTrue(monitor.json["monitor"]["running"])

        stop = self.client.post("/api/camera/monitor/stop", headers=self._auth_headers())
        self.assertEqual(stop.status_code, 200)
        self.assertEqual(stop.json["command"]["status"], "succeeded")

    def test_camera_webrtc_session_contract(self):
        session = self.client.get("/api/camera/webrtc/session", headers=self._auth_headers())
        self.assertEqual(session.status_code, 200)
        self.assertTrue(session.json["session"]["signalingUrl"].startswith("ws://"))
        self.assertIn("src=ipc45aw_hd", session.json["session"]["signalingUrl"])
        self.assertEqual(session.json["session"]["message"], "实时画面连接已准备好。")

    def test_camera_webrtc_offer_contract(self):
        app = create_app(fresh_test_config(CAMERA_RUNTIME_PROVIDER="mock"))
        client = app.test_client()
        code = request_debug_code(client, "13800002027")
        login = client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002027", "code": code},
        )
        self.assertEqual(login.status_code, 200)

        offer = client.post(
            "/api/camera/webrtc/offer",
            json={"sdp": "v=0\r\ns=Camera Test Offer\r\n"},
            headers={"Authorization": f"Bearer {login.json['tokens']['accessToken']}"},
        )
        self.assertEqual(offer.status_code, 200)
        self.assertEqual(offer.json["session"]["type"], "answer")
        self.assertIn("sdp", offer.json["session"])
        self.assertIsInstance(offer.json["session"]["candidates"], list)

    def test_device_status_and_command_include_camera_runtime(self):
        status = self.client.get(
            f"/api/devices/{self.device_id}/status",
            headers=self._auth_headers(),
        )
        self.assertEqual(status.status_code, 200)
        self.assertTrue(status.json["status"]["capabilities"]["snapshot"])
        self.assertIn("camera", status.json["status"])

        command = self.client.post(
            f"/api/devices/{self.device_id}/commands",
            json={"commandType": "speak", "text": "测试提醒"},
            headers=self._auth_headers(),
        )
        self.assertEqual(command.status_code, 200)
        self.assertEqual(command.json["command"]["status"], "succeeded")

    def test_ai_config_models_and_prompt_registry(self):
        config = self.client.get("/api/ai/config")
        self.assertEqual(config.status_code, 200)
        self.assertEqual(config.json["promptRegistry"], "file")

        models = self.client.get("/api/ai/models")
        self.assertEqual(models.status_code, 200)
        self.assertEqual(models.json["models"][0]["provider"], "development")

        prompts = self.client.get("/api/ai/prompts")
        self.assertEqual(prompts.status_code, 200)
        ids = {(item["id"], item["version"]) for item in prompts.json["prompts"]}
        self.assertIn(("task.observation.summary", "v1"), ids)

    def test_firmware_status_packages_and_mock_job(self):
        status = self.client.get(
            f"/api/firmware/devices/{self.device_id}/status",
            headers=self._auth_headers(),
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["firmware"]["execution"], "reserved_boundary_only")

        packages = self.client.get("/api/firmware/packages", headers=self._auth_headers())
        self.assertEqual(packages.status_code, 200)
        self.assertGreaterEqual(len(packages.json["packages"]), 1)
        package_id = packages.json["packages"][0]["id"]

        job = self.client.post(
            "/api/firmware/jobs",
            json={"deviceId": self.device_id, "packageId": package_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(job.status_code, 200)
        self.assertEqual(job.json["job"]["status"], "scheduled")
        self.assertEqual(job.json["execution"], "reserved_boundary_only")

        status_after = self.client.get(
            f"/api/firmware/devices/{self.device_id}/status",
            headers=self._auth_headers(),
        )
        self.assertEqual(status_after.status_code, 200)
        self.assertEqual(status_after.json["firmware"]["lastJob"]["id"], job.json["job"]["id"])

    def _login(self) -> str:
        code = request_debug_code(self.client, "13800002026")
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002026", "code": code},
        )
        self.assertEqual(login.status_code, 200)
        return login.json["tokens"]["accessToken"]

    def _create_device(self) -> str:
        response = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-BOUNDARY", "deviceName": "客厅设备", "location": "客厅"},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["device"]["id"]

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}


if __name__ == "__main__":
    unittest.main()
