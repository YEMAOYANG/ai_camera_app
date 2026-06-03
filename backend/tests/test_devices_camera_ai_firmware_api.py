from __future__ import annotations

import json
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import create_app
from tests.support import fresh_test_config, request_debug_code


class _CameraRuntimeHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/api/health":
            self._json({"ok": True, "service": "fake-camera-runtime"})
            return
        if self.path == "/api/voice/runtime":
            self._json({"ok": True, "voice": {"state": "idle", "running": False}})
            return
        if self.path == "/api/camera/speaker/status":
            self._json({"ok": True, "speaker": {"busy": False}})
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

        unreachable_app = create_app(
            fresh_test_config(
                CAMERA_RUNTIME_ADAPTER="ai_camera_test",
                CAMERA_BACKEND_URL="http://127.0.0.1:1",
            )
        )
        unreachable = unreachable_app.test_client().get("/api/camera/health")
        self.assertEqual(unreachable.status_code, 502)
        self.assertFalse(unreachable.json["cameraRuntime"]["reachable"])

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
            json={"bindingCode": "MIRA-BOUNDARY", "deviceName": "客厅米拉", "location": "客厅"},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["device"]["id"]

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}


if __name__ == "__main__":
    unittest.main()
