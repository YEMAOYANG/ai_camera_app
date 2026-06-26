from __future__ import annotations

import json
import threading
import unittest
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from app import create_app
from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from models.firmware import FIRMWARE_PACKAGE_ACTIVE
from repositories.device_repository import DeviceRepository
from services.device_service import DeviceService
from services.device_runtime_resolver import DeviceRuntimeResolver
from services.camera_command_service import _parent_camera_command_event
from services.service_factory import auth_service, camera_command_service
from services import task_event_stream
from tests.support import fresh_test_config, request_debug_code


class _CameraRuntimeHandler(BaseHTTPRequestHandler):
    speak_count = 0
    ptz_count = 0
    monitor_running = False
    analyze_payload = {
        "has_person": True,
        "activity": "阅读绘本",
        "confidence": 0.88,
        "description": "孩子正在安静看绘本。",
    }

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
        if self.path == "/api/camera/stream":
            body = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n\xff\xd8\xff\xd9\r\n"
            self.send_response(200)
            self.send_header("Content-Type", "multipart/x-mixed-replace; boundary=frame")
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
        if self.path == "/api/camera/ptz/move":
            self.__class__.ptz_count += 1
            self._json({"ok": True, "status": "queued", "direction": "left", "step": 1})
            return
        if self.path == "/api/monitor/start":
            self.__class__.monitor_running = True
            self._json({"ok": True, "monitor_runtime": {"running": True, "status": "running"}})
            return
        if self.path == "/api/monitor/stop":
            self.__class__.monitor_running = False
            self._json({"ok": True, "monitor_runtime": {"running": False, "status": "stopped"}})
            return
        if self.path == "/api/analyze_frame":
            self._json(dict(self.__class__.analyze_payload))
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
        _CameraRuntimeHandler.ptz_count = 0
        _CameraRuntimeHandler.monitor_running = False
        _CameraRuntimeHandler.analyze_payload = {
            "has_person": True,
            "activity": "阅读绘本",
            "confidence": 0.88,
            "description": "孩子正在安静看绘本。",
        }
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
        self.assertTrue(devices.json["devices"][0]["isDefault"])

        default = self.client.get("/api/devices/default", headers=self._auth_headers())
        self.assertEqual(default.status_code, 200)
        self.assertEqual(default.json["device"]["id"], self.device_id)

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

    def test_bind_duplicate_default_and_unbind_default_device(self):
        second = self.client.post(
            "/api/devices",
            json={"bindingCode": "BIND-SECOND", "name": "儿童房设备", "location": "儿童房"},
            headers=self._auth_headers(),
        )
        self.assertEqual(second.status_code, 200, second.json)
        second_id = second.json["device"]["id"]
        self.assertFalse(second.json["duplicate"])
        self.assertEqual(second.json["defaultDevice"]["id"], self.device_id)

        duplicate = self.client.post(
            "/api/devices",
            json={"bindingCode": "BIND-SECOND", "name": "重复设备", "location": "卧室"},
            headers=self._auth_headers(),
        )
        self.assertEqual(duplicate.status_code, 200, duplicate.json)
        self.assertTrue(duplicate.json["duplicate"])
        self.assertEqual(duplicate.json["device"]["id"], second_id)

        set_default = self.client.post(
            f"/api/devices/{second_id}/set-default",
            headers=self._auth_headers(),
        )
        self.assertEqual(set_default.status_code, 200)
        self.assertEqual(set_default.json["device"]["id"], second_id)

        default = self.client.get("/api/devices/default", headers=self._auth_headers())
        self.assertEqual(default.status_code, 200)
        self.assertEqual(default.json["device"]["id"], second_id)

        speak = self.client.post(
            "/api/camera/commands/speak",
            json={"text": "默认设备提醒"},
            headers=self._auth_headers(),
        )
        self.assertEqual(speak.status_code, 200, speak.json)
        self.assertEqual(speak.json["command"]["deviceId"], second_id)

        unbound = self.client.post(
            f"/api/devices/{second_id}/unbind",
            headers=self._auth_headers(),
        )
        self.assertEqual(unbound.status_code, 200)
        self.assertEqual(unbound.json["defaultDevice"]["id"], self.device_id)

        default_after = self.client.get("/api/devices/default", headers=self._auth_headers())
        self.assertEqual(default_after.status_code, 200)
        self.assertEqual(default_after.json["device"]["id"], self.device_id)

    def test_binding_code_cannot_be_active_in_two_families(self):
        other_client = self.app.test_client()
        other_code = request_debug_code(other_client, "13800002031")
        other_login = other_client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002031", "code": other_code},
        )
        self.assertEqual(other_login.status_code, 200)
        other_token = other_login.json["tokens"]["accessToken"]
        parent = other_client.post(
            "/api/setup/parent-identity",
            json={"displayName": "妈妈", "relationship": "妈妈", "relationshipKey": "mom"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(parent.status_code, 200)

        duplicate = other_client.post(
            "/api/devices",
            json={"bindingCode": "BIND-BOUNDARY", "name": "另一台设备", "location": "卧室"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(duplicate.status_code, 409)
        self.assertEqual(duplicate.json["error"], "device_already_bound")

    def test_discovery_status_marks_bound_devices_before_connect(self):
        other_client = self.app.test_client()
        other_code = request_debug_code(other_client, "13800002032")
        other_login = other_client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002032", "code": other_code},
        )
        self.assertEqual(other_login.status_code, 200)
        other_token = other_login.json["tokens"]["accessToken"]
        parent = other_client.post(
            "/api/setup/parent-identity",
            json={"displayName": "爸爸", "relationship": "爸爸", "relationshipKey": "dad"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(parent.status_code, 200)
        other_device = other_client.post(
            "/api/devices",
            json={"bindingCode": "BIND-DISCOVERY-OTHER", "name": "另一台设备", "location": "卧室"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(other_device.status_code, 200, other_device.json)

        status = self.client.post(
            "/api/devices/discovery-status",
            json={
                "candidates": [
                    {"id": "current", "bindingCode": "BIND-BOUNDARY"},
                    {"id": "other", "bindingCode": "BIND-DISCOVERY-OTHER"},
                    {"id": "new", "bindingCode": "BIND-DISCOVERY-NEW"},
                    {"id": "unknown"},
                ]
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(status.status_code, 200, status.json)
        by_id = {item["id"]: item for item in status.json["candidates"]}
        self.assertEqual(by_id["current"]["bindingState"], "boundToCurrentFamily")
        self.assertFalse(by_id["current"]["isConnectable"])
        self.assertEqual(by_id["other"]["bindingState"], "boundToAnotherFamily")
        self.assertFalse(by_id["other"]["isConnectable"])
        self.assertEqual(by_id["other"]["disabledReason"], "已被其他家庭绑定")
        self.assertNotIn("ownerName", by_id["other"])
        self.assertEqual(by_id["new"]["bindingState"], "available")
        self.assertTrue(by_id["new"]["isConnectable"])
        self.assertEqual(by_id["unknown"]["bindingState"], "unknown")
        self.assertTrue(by_id["unknown"]["isConnectable"])

    def test_unbind_last_default_clears_default_device(self):
        unbound = self.client.post(
            f"/api/devices/{self.device_id}/unbind",
            headers=self._auth_headers(),
        )
        self.assertEqual(unbound.status_code, 200)
        self.assertIsNone(unbound.json["defaultDevice"])

        default = self.client.get("/api/devices/default", headers=self._auth_headers())
        self.assertEqual(default.status_code, 200)
        self.assertIsNone(default.json["device"])

        devices = self.client.get("/api/devices", headers=self._auth_headers())
        self.assertEqual(devices.status_code, 200)
        self.assertEqual(devices.json["devices"], [])

    def test_camera_health_adapter_reachable_and_unreachable(self):
        unauthenticated = self.client.get("/api/camera/health")
        self.assertEqual(unauthenticated.status_code, 401)

        reachable = self.client.get("/api/camera/health", headers=self._auth_headers())
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
        unreachable_client = unreachable_app.test_client()
        code = request_debug_code(unreachable_client, "13800003025")
        login = unreachable_client.post(
            "/api/auth/sms/login",
            json={"phone": "13800003025", "code": code},
        )
        self.assertEqual(login.status_code, 200)
        unreachable = unreachable_client.get(
            "/api/camera/health",
            headers={"Authorization": f"Bearer {login.json['tokens']['accessToken']}"},
        )
        self.assertEqual(unreachable.status_code, 502)
        self.assertFalse(unreachable.json["cameraRuntime"]["reachable"])
        self.assertNotIn("error", unreachable.json["cameraRuntime"])
        self.assertEqual(unreachable.json["cameraRuntime"]["data"]["status"], "unavailable")

        disabled_app = create_app(fresh_test_config(CAMERA_RUNTIME_PROVIDER="disabled"))
        disabled_client = disabled_app.test_client()
        code = request_debug_code(disabled_client, "13800003026")
        login = disabled_client.post(
            "/api/auth/sms/login",
            json={"phone": "13800003026", "code": code},
        )
        snapshot = disabled_client.get(
            "/api/camera/snapshot",
            headers={"Authorization": f"Bearer {login.json['tokens']['accessToken']}"},
        )
        self.assertEqual(snapshot.status_code, 204)
        self.assertEqual(snapshot.headers["X-Mira-Snapshot-Status"], "unavailable")
        self.assertEqual(snapshot.headers["X-Mira-Snapshot-Message"], "snapshot_unavailable")

    def test_camera_status_snapshot_commands_and_monitor(self):
        status = self.client.get("/api/camera/status", headers=self._auth_headers())
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["status"]["connectionStatus"], "online")
        self.assertTrue(status.json["status"]["speakerAvailable"])
        self.assertFalse(status.json["status"]["ptzAvailable"])
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

        ptz = self.client.post(
            "/api/camera/commands/ptz",
            json={"direction": "left", "step": 2},
            headers=self._auth_headers(),
        )
        self.assertEqual(ptz.status_code, 200)
        self.assertEqual(ptz.json["command"]["commandType"], "ptz_move")
        self.assertEqual(ptz.json["command"]["status"], "succeeded")
        self.assertEqual(_CameraRuntimeHandler.ptz_count, 1)

        captured: list[tuple[str, dict]] = []
        original_broadcast = task_event_stream.task_event_stream_server.broadcast
        task_event_stream.task_event_stream_server.broadcast = (
            lambda family_id, payload: captured.append((family_id, payload))
        )
        try:
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
        finally:
            task_event_stream.task_event_stream_server.broadcast = original_broadcast

        pushed_types = [payload["type"] for _, payload in captured]
        self.assertIn("camera_status.changed", pushed_types)
        self.assertIn("camera_event.created", pushed_types)
        self.assertTrue(all(family_id == self.family_id for family_id, _ in captured))

        events = self.client.get("/api/camera/events", headers=self._auth_headers())
        self.assertEqual(events.status_code, 200)
        event_types = [event["eventType"] for event in events.json["events"]]
        self.assertNotIn("speak", event_types)
        self.assertNotIn("ptz_move", event_types)
        self.assertNotIn("start_monitor", event_types)
        self.assertNotIn("stop_monitor", event_types)
        self.assertFalse(
            any(event.get("category") == "care_reminder" for event in events.json["events"])
        )

    def test_camera_monitor_refresh_publishes_lightweight_family_event(self):
        captured: list[tuple[str, dict]] = []
        original_broadcast = task_event_stream.task_event_stream_server.broadcast
        task_event_stream.task_event_stream_server.broadcast = (
            lambda family_id, payload: captured.append((family_id, payload))
        )
        try:
            response = self.client.post(
                "/api/camera/monitor/refresh",
                query_string={"deviceId": self.device_id},
                headers=self._auth_headers(),
            )
        finally:
            task_event_stream.task_event_stream_server.broadcast = original_broadcast

        self.assertEqual(response.status_code, 200, response.json)
        observation = response.json["monitor"]["lastObservation"]
        self.assertTrue(observation["isReliable"])
        self.assertEqual(observation["activity"], "阅读绘本")
        self.assertEqual(
            [payload["type"] for _, payload in captured],
            [
                "camera_event.created",
                "camera_monitor.refreshed",
                "camera_observation.updated",
            ],
        )
        self.assertTrue(all(family_id == self.family_id for family_id, _ in captured))
        for _, payload in captured:
            self.assertEqual(payload["deviceId"], self.device_id)
            self.assertNotIn("image", payload)
            self.assertNotIn("snapshot", payload)
            self.assertNotIn("debug", payload)

        events = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(events.status_code, 200, events.json)
        self.assertTrue(
            any(event["displayTitle"] == "孩子正在阅读绘本" for event in events.json["events"])
        )

    def test_camera_monitor_refresh_marks_no_person_without_child_claim(self):
        _CameraRuntimeHandler.analyze_payload = {
            "has_person": False,
            "activity": "其他",
            "confidence": 0.91,
            "description": "没有看到孩子。",
        }

        response = self.client.post(
            "/api/camera/monitor/refresh",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200, response.json)
        observation = response.json["monitor"]["lastObservation"]
        self.assertTrue(observation["isReliable"])
        self.assertFalse(observation["hasPerson"])
        self.assertEqual(observation["activity"], "")
        self.assertNotIn("看到孩子在", observation["summary"])
        self.assertEqual(observation["summary"], "暂未看到孩子")

    def test_camera_monitor_refresh_records_toy_play_without_cleanup_reminder(self):
        _CameraRuntimeHandler.analyze_payload = {
            "has_person": True,
            "activity": "playing with toys",
            "confidence": 0.9,
            "description": "孩子坐在沙发上玩玩具，周围有积木。",
        }

        response = self.client.post(
            "/api/camera/monitor/refresh",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )

        self.assertEqual(response.status_code, 200, response.json)
        observation = response.json["monitor"]["lastObservation"]
        self.assertTrue(observation["isReliable"])
        self.assertEqual(observation["activity"], "玩玩具")
        self.assertEqual(observation["summary"], "孩子正在玩玩具")
        events = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(events.status_code, 200, events.json)
        self.assertTrue(
            any(event["displayTitle"] == "孩子正在玩玩具" for event in events.json["events"])
        )
        self.assertFalse(
            any("收纳" in event["displayTitle"] for event in events.json["events"])
        )

    def test_camera_events_dedupe_repeated_observations_in_short_window(self):
        _CameraRuntimeHandler.analyze_payload = {
            "has_person": False,
            "activity": "其他",
            "confidence": 0.9,
            "description": "客厅场景，沙发上摆放着毛绒玩具，地垫上有玩具车。",
        }

        first = self.client.post(
            "/api/camera/monitor/refresh",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        second = self.client.post(
            "/api/camera/monitor/refresh",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(second.status_code, 200, second.json)

        events = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(events.status_code, 200, events.json)
        self.assertEqual(len(events.json["events"]), 1, events.json["events"])
        self.assertEqual(events.json["events"][0]["eventType"], "camera_observation")

    def test_camera_event_display_sanitizes_legacy_structured_summary(self):
        event = _parent_camera_command_event(
            {
                "id": "cmd_dirty",
                "source": "camera_command",
                "eventType": "camera_observation",
                "status": "succeeded",
                "createdAt": now_ms(),
                "payload": {
                    "response": {
                        "displayTitle": "{'score': 80, 'skills': [{'name': '坐姿'}]}",
                        "displayMessage": "{'score': 80, 'skills': [{'name': '专注'}]}",
                        "observation": {
                            "hasPerson": True,
                            "isReliable": True,
                            "summary": "{'score': 80, 'skills': [{'name': '坐姿'}]}",
                            "description": "孩子在桌前写字，右手拿着笔，头离纸面比较近。",
                            "rawDetail": {
                                "summary": {
                                    "score": 80,
                                    "skills": [{"name": "坐姿", "score": 92}],
                                }
                            },
                        },
                    }
                },
            }
        )

        self.assertIsNotNone(event)
        visible = f"{event['displayTitle']} {event['displayMessage']} {event['evidenceSummary']}"
        self.assertNotIn("score", visible)
        self.assertNotIn("skills", visible)
        self.assertNotIn("{", visible)
        self.assertNotIn("[", visible)
        self.assertIn("孩子在桌前写字", event["displayMessage"])

    def test_camera_event_display_does_not_turn_negated_toys_into_play(self):
        event = _parent_camera_command_event(
            {
                "id": "cmd_negated_toy",
                "source": "camera_command",
                "eventType": "camera_observation",
                "status": "succeeded",
                "createdAt": now_ms(),
                "payload": {
                    "response": {
                        "observation": {
                            "hasPerson": True,
                            "isReliable": True,
                            "activity": "玩玩具",
                            "summary": "孩子正在玩玩具",
                            "description": "一个人趴在桌上，头部埋在双臂之间，没有看到书本、手机或玩具等物品。",
                        },
                    }
                },
            }
        )

        self.assertIsNotNone(event)
        self.assertNotEqual(event["displayTitle"], "孩子正在玩玩具")
        self.assertIn("趴在桌上", event["displayMessage"])

    def test_family_realtime_camera_event_is_family_scoped(self):
        captured: list[tuple[str, dict]] = []
        original_broadcast = task_event_stream.task_event_stream_server.broadcast
        task_event_stream.task_event_stream_server.broadcast = (
            lambda family_id, payload: captured.append((family_id, payload))
        )
        try:
            task_event_stream.publish_family_event(
                family_id="family_a",
                event_type=task_event_stream.CAMERA_EVENT_CREATED,
                device_id="dev_a",
                event_ids=["evt_a"],
                source="camera_test",
            )
        finally:
            task_event_stream.task_event_stream_server.broadcast = original_broadcast

        self.assertEqual(len(captured), 1)
        self.assertEqual(captured[0][0], "family_a")
        self.assertEqual(captured[0][1]["type"], "camera_event.created")
        self.assertEqual(captured[0][1]["eventIds"], ["evt_a"])

    def test_camera_events_are_scoped_by_device(self):
        second = self.client.post(
            "/api/devices",
            json={"bindingCode": "BIND-EVENTS-SECOND", "name": "儿童房设备", "location": "儿童房"},
            headers=self._auth_headers(),
        )
        self.assertEqual(second.status_code, 200, second.json)
        second_id = second.json["device"]["id"]
        first_command = self.client.post(
            "/api/camera/commands/speak",
            json={"deviceId": self.device_id, "text": "客厅提醒"},
            headers=self._auth_headers(),
        )
        self.assertEqual(first_command.status_code, 200, first_command.json)
        second_command = self.client.post(
            "/api/camera/commands/speak",
            json={"deviceId": second_id, "text": "儿童房提醒"},
            headers=self._auth_headers(),
        )
        self.assertEqual(second_command.status_code, 200, second_command.json)

        first_events = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(first_events.status_code, 200)
        self.assertFalse(
            any(event["eventType"] == "speak" for event in first_events.json["events"])
        )

        second_events = self.client.get(
            "/api/camera/events",
            query_string={"deviceId": second_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(second_events.status_code, 200)
        self.assertFalse(
            any(event["eventType"] == "speak" for event in second_events.json["events"])
        )

    def test_camera_webrtc_session_contract(self):
        session = self.client.get("/api/camera/webrtc/session", headers=self._auth_headers())
        self.assertEqual(session.status_code, 200)
        self.assertTrue(session.json["session"]["signalingUrl"].startswith("ws://"))
        self.assertIn("src=ipc45aw_hd", session.json["session"]["signalingUrl"])
        self.assertEqual(session.json["session"]["message"], "实时画面连接已准备好。")

    def test_camera_read_apis_route_through_device_runtime_resolver(self):
        status = self.client.get(
            "/api/camera/status",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["status"]["connectionStatus"], "online")

        snapshot = self.client.get(
            "/api/camera/snapshot",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(snapshot.status_code, 200)
        self.assertEqual(snapshot.content_type, "image/jpeg")

        stream = self.client.get(
            "/api/camera/stream",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(stream.status_code, 200)
        self.assertTrue(stream.content_type.startswith("multipart/x-mixed-replace"))

        session = self.client.get(
            "/api/camera/webrtc/session",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(session.status_code, 200)
        self.assertIn("signalingUrl", session.json["session"])

    def test_device_runtime_config_overrides_global_provider_by_device(self):
        second = self.client.post(
            "/api/devices",
            json={"bindingCode": "BIND-RUNTIME-SECOND", "name": "儿童房设备", "location": "儿童房"},
            headers=self._auth_headers(),
        )
        self.assertEqual(second.status_code, 200, second.json)
        second_id = second.json["device"]["id"]
        self._set_device_runtime_config(self.device_id, "disabled")
        self._set_device_runtime_config(
            second_id,
            "ai_camera_test",
            {"baseUrl": self.camera_url, "streamProfile": "dev"},
        )

        first_status = self.client.get(
            "/api/camera/status",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(first_status.status_code, 200)
        self.assertEqual(first_status.json["status"]["runtimeProvider"], "disabled_camera_runtime")
        self.assertEqual(first_status.json["status"]["connectionStatus"], "offline")

        second_status = self.client.get(
            "/api/camera/status",
            query_string={"deviceId": second_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(second_status.status_code, 200)
        self.assertEqual(second_status.json["status"]["runtimeProvider"], "ai_camera_test_bridge")
        self.assertEqual(second_status.json["status"]["connectionStatus"], "online")

        second_snapshot = self.client.get(
            "/api/camera/snapshot",
            query_string={"deviceId": second_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(second_snapshot.status_code, 200)
        self.assertEqual(second_snapshot.content_type, "image/jpeg")

        speak = self.client.post(
            "/api/camera/commands/speak",
            json={"deviceId": second_id, "text": "设备级配置提醒"},
            headers=self._auth_headers(),
        )
        self.assertEqual(speak.status_code, 200, speak.json)
        self.assertEqual(speak.json["command"]["status"], "succeeded")
        self.assertEqual(speak.json["command"]["deviceId"], second_id)
        self.assertEqual(_CameraRuntimeHandler.speak_count, 1)

    def test_device_runtime_config_missing_allows_dev_fallback_but_not_production(self):
        dev_status = self.client.get(
            "/api/camera/status",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(dev_status.status_code, 200)
        self.assertEqual(dev_status.json["status"]["runtimeProvider"], "ai_camera_test_bridge")

        resolver = DeviceRuntimeResolver(
            self.app.config["DATABASE_URL"],
            provider="disabled",
            legacy_provider="disabled",
            dev_adapters_enabled=False,
            app_env="production",
        )
        with self.assertRaises(ApiError) as raised:
            resolver.resolve(family_id=self.family_id, device_id=self.device_id)
        self.assertEqual(raised.exception.code, "device_runtime_not_configured")

    def test_other_family_and_unbound_devices_cannot_resolve_runtime_config(self):
        self._set_device_runtime_config(self.device_id, "disabled")
        other_client = self.app.test_client()
        other_code = request_debug_code(other_client, "13800002033")
        other_login = other_client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002033", "code": other_code},
        )
        self.assertEqual(other_login.status_code, 200)
        other_token = other_login.json["tokens"]["accessToken"]
        other_client.post(
            "/api/setup/parent-identity",
            json={"displayName": "妈妈", "relationship": "妈妈", "relationshipKey": "mom"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        other_device = other_client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-RUNTIME-OTHER", "deviceName": "卧室设备", "location": "卧室"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(other_device.status_code, 200)
        other_device_id = other_device.json["device"]["id"]

        rejected = self.client.get(
            "/api/camera/status",
            query_string={"deviceId": other_device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(rejected.status_code, 404)
        self.assertEqual(rejected.json["error"], "device_not_found")

        unbind = self.client.post(
            f"/api/devices/{self.device_id}/unbind",
            headers=self._auth_headers(),
        )
        self.assertEqual(unbind.status_code, 200)
        unbound = self.client.get(
            "/api/camera/status",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(unbound.status_code, 409)
        self.assertEqual(unbound.json["error"], "device_unbound")

    def test_runtime_config_api_writes_sanitized_config_and_hides_secret_ref(self):
        update = self.client.put(
            f"/api/devices/{self.device_id}/runtime-config",
            json={
                "provider": "ai_camera_test",
                "config": {
                    "BaseUrl": self.camera_url,
                    "streamProfile": "dev",
                    "speakerCapabilities": {"enabled": True, "volume": 0.6},
                },
                "secretRef": "vault://camera/dev-runtime",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(update.status_code, 200, update.json)
        runtime_config = update.json["runtimeConfig"]
        self.assertEqual(runtime_config["provider"], "ai_camera_test")
        self.assertTrue(runtime_config["hasSecretRef"])
        self.assertNotIn("secretRef", runtime_config)
        self.assertEqual(runtime_config["config"]["baseUrl"], self.camera_url)
        self.assertEqual(runtime_config["config"]["speakerCapabilities"]["enabled"], True)

        current = self.client.get(
            f"/api/devices/{self.device_id}/runtime-config",
            headers=self._auth_headers(),
        )
        self.assertEqual(current.status_code, 200, current.json)
        self.assertTrue(current.json["runtimeConfig"]["hasSecretRef"])
        self.assertNotIn("secretRef", current.json["runtimeConfig"])

        status = self.client.get(
            "/api/camera/status",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["status"]["runtimeProvider"], "ai_camera_test_bridge")

    def test_runtime_config_get_requires_manage_devices_and_hides_secret_ref(self):
        update = self.client.put(
            f"/api/devices/{self.device_id}/runtime-config",
            json={
                "provider": "ai_camera_test",
                "config": {"baseUrl": self.camera_url},
                "secretRef": "vault://camera/admin-only-runtime",
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(update.status_code, 200, update.json)

        admin_get = self.client.get(
            f"/api/devices/{self.device_id}/runtime-config",
            headers=self._auth_headers(),
        )
        self.assertEqual(admin_get.status_code, 200, admin_get.json)
        self.assertEqual(admin_get.json["runtimeConfig"]["provider"], "ai_camera_test")
        self.assertTrue(admin_get.json["runtimeConfig"]["hasSecretRef"])
        self.assertNotIn("secretRef", admin_get.json["runtimeConfig"])

        viewer_token = self._login_family_member(role="viewer", phone="13800002035")
        viewer_get = self.client.get(
            f"/api/devices/{self.device_id}/runtime-config",
            headers={"Authorization": f"Bearer {viewer_token}"},
        )
        self.assertEqual(viewer_get.status_code, 403)
        self.assertEqual(viewer_get.json["error"], "permission_denied")

    def test_runtime_config_rejects_sensitive_nested_config_bad_url_and_unknown_keys(self):
        sensitive = self.client.put(
            f"/api/devices/{self.device_id}/runtime-config",
            json={
                "provider": "ai_camera_test",
                "config": {
                    "baseUrl": self.camera_url,
                    "speakerCapabilities": {"enabled": True, "apiKey": "should-not-store"},
                },
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(sensitive.status_code, 400)
        self.assertEqual(sensitive.json["error"], "sensitive_runtime_config")

        bad_url = self.client.put(
            f"/api/devices/{self.device_id}/runtime-config",
            json={
                "provider": "ai_camera_test",
                "config": {"baseUrl": "http://user:pass@127.0.0.1:8767"},
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(bad_url.status_code, 400)
        self.assertEqual(bad_url.json["error"], "invalid_runtime_config_url")

        unsupported = self.client.put(
            f"/api/devices/{self.device_id}/runtime-config",
            json={
                "provider": "ai_camera_test",
                "config": {"baseUrl": self.camera_url, "rawRtspUrl": "rtsp://camera.local/stream"},
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(unsupported.status_code, 400)
        self.assertEqual(unsupported.json["error"], "runtime_config_key_not_allowed")

    def test_runtime_config_rejects_cross_family_unbound_and_dev_provider_outside_dev(self):
        with self.app.app_context():
            service = DeviceService(
                self.app.config["DATABASE_URL"],
                auth_service=auth_service(),
                app_env="production",
                dev_adapters_enabled=False,
            )
            with self.assertRaises(ApiError) as raised:
                service.update_runtime_config(
                    self.access_token,
                    self.device_id,
                    {"provider": "mock", "config": {}},
                )
            self.assertEqual(raised.exception.code, "development_adapter_not_allowed")

        other_client = self.app.test_client()
        other_code = request_debug_code(other_client, "13800002034")
        other_login = other_client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002034", "code": other_code},
        )
        self.assertEqual(other_login.status_code, 200)
        other_token = other_login.json["tokens"]["accessToken"]
        other_client.post(
            "/api/setup/parent-identity",
            json={"displayName": "妈妈", "relationship": "妈妈", "relationshipKey": "mom"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        other_device = other_client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-RUNTIME-WRITE-OTHER", "deviceName": "卧室设备"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(other_device.status_code, 200)
        cross_family = self.client.put(
            f"/api/devices/{other_device.json['device']['id']}/runtime-config",
            json={"provider": "disabled", "config": {}},
            headers=self._auth_headers(),
        )
        self.assertEqual(cross_family.status_code, 404)
        self.assertEqual(cross_family.json["error"], "device_not_found")

        unbind = self.client.post(
            f"/api/devices/{self.device_id}/unbind",
            headers=self._auth_headers(),
        )
        self.assertEqual(unbind.status_code, 200)
        unbound_write = self.client.put(
            f"/api/devices/{self.device_id}/runtime-config",
            json={"provider": "disabled", "config": {}},
            headers=self._auth_headers(),
        )
        self.assertEqual(unbound_write.status_code, 409)
        self.assertEqual(unbound_write.json["error"], "device_unbound")

    def test_reserved_runtime_provider_can_be_saved_as_unimplemented_contract(self):
        update = self.client.put(
            f"/api/devices/{self.device_id}/runtime-config",
            json={
                "provider": "self_owned_camera",
                "config": {
                    "adapterName": "self_owned_camera_v1",
                    "streamProfile": "default",
                    "deviceProfile": {"model": "AI Camera Dev", "region": "CN"},
                },
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(update.status_code, 200, update.json)
        runtime_config = update.json["runtimeConfig"]
        self.assertEqual(runtime_config["provider"], "self_owned_camera")
        self.assertFalse(runtime_config["adapterImplemented"])
        self.assertIn("尚未接入", runtime_config["message"])

        status = self.client.get(
            "/api/camera/status",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(status.status_code, 503)
        self.assertEqual(status.json["error"], "camera_runtime_reserved_adapter")

    def test_camera_read_apis_reject_other_family_and_unbound_devices(self):
        other_client = self.app.test_client()
        other_code = request_debug_code(other_client, "13800002029")
        other_login = other_client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002029", "code": other_code},
        )
        self.assertEqual(other_login.status_code, 200)
        other_token = other_login.json["tokens"]["accessToken"]
        other_client.post(
            "/api/setup/parent-identity",
            json={"displayName": "妈妈", "relationship": "妈妈", "relationshipKey": "mom"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        other_device = other_client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-READ-OTHER", "deviceName": "卧室设备", "location": "卧室"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(other_device.status_code, 200)

        rejected = self.client.get(
            "/api/camera/health",
            query_string={"deviceId": other_device.json["device"]["id"]},
            headers=self._auth_headers(),
        )
        self.assertEqual(rejected.status_code, 404)
        self.assertEqual(rejected.json["error"], "device_not_found")

        unbind = self.client.post(
            f"/api/devices/{self.device_id}/unbind",
            headers=self._auth_headers(),
        )
        self.assertEqual(unbind.status_code, 200)
        unbound = self.client.get(
            "/api/camera/health",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(unbound.status_code, 409)
        self.assertEqual(unbound.json["error"], "device_unbound")

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
        self.assertEqual(command.json["command"]["deviceId"], self.device_id)

        missing = self.client.post(
            "/api/devices/dev_missing/commands",
            json={"commandType": "speak", "text": "测试提醒"},
            headers=self._auth_headers(),
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json["error"], "device_not_found")

    def test_runtime_resolver_routes_default_device_and_rejects_other_family_device(self):
        speak = self.client.post(
            "/api/camera/commands/speak",
            json={"text": "默认设备提醒"},
            headers=self._auth_headers(),
        )
        self.assertEqual(speak.status_code, 200, speak.json)
        self.assertEqual(speak.json["command"]["status"], "succeeded")
        self.assertEqual(speak.json["command"]["deviceId"], self.device_id)

        with self.app.app_context():
            internal = camera_command_service().internal_speak(
                family_id=self.family_id,
                text="内部提醒",
            )
        self.assertEqual(internal["status"], "succeeded")
        self.assertEqual(internal["deviceId"], self.device_id)

        other_client = self.app.test_client()
        other_code = request_debug_code(other_client, "13800002028")
        other_login = other_client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002028", "code": other_code},
        )
        self.assertEqual(other_login.status_code, 200)
        other_token = other_login.json["tokens"]["accessToken"]
        parent = other_client.post(
            "/api/setup/parent-identity",
            json={"displayName": "妈妈", "relationship": "妈妈", "relationshipKey": "mom"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(parent.status_code, 200)
        other_device = other_client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-OTHER", "deviceName": "卧室设备", "location": "卧室"},
            headers={"Authorization": f"Bearer {other_token}"},
        )
        self.assertEqual(other_device.status_code, 200)

        rejected = self.client.post(
            f"/api/devices/{other_device.json['device']['id']}/commands",
            json={"commandType": "speak", "text": "不该路由"},
            headers=self._auth_headers(),
        )
        self.assertEqual(rejected.status_code, 404)
        self.assertEqual(rejected.json["error"], "device_not_found")

    def test_camera_status_current_task_is_scoped_by_device(self):
        child_id = self._create_child()
        second = self.client.post(
            "/api/devices",
            json={"bindingCode": "BIND-TASK-SECOND", "name": "餐厅设备", "location": "餐厅"},
            headers=self._auth_headers(),
        )
        self.assertEqual(second.status_code, 200, second.json)
        second_id = second.json["device"]["id"]
        task_a = self._create_task(child_id, self.device_id, "客厅收纳")
        task_b = self._create_task(child_id, second_id, "餐厅用餐")
        self._start_task(task_a)
        self._start_task(task_b)

        status_a = self.client.get(
            "/api/camera/status",
            query_string={"deviceId": self.device_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(status_a.status_code, 200)
        self.assertEqual(status_a.json["status"]["currentTask"]["id"], task_a)

        status_b = self.client.get(
            "/api/camera/status",
            query_string={"deviceId": second_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(status_b.status_code, 200)
        self.assertEqual(status_b.json["status"]["currentTask"]["id"], task_b)

    def test_ai_config_models_and_prompt_registry(self):
        unauthenticated = self.client.get("/api/ai/config")
        self.assertEqual(unauthenticated.status_code, 401)

        config = self.client.get("/api/ai/config", headers=self._auth_headers())
        self.assertEqual(config.status_code, 200)
        self.assertEqual(config.json["promptRegistry"], "file")

        models = self.client.get("/api/ai/models", headers=self._auth_headers())
        self.assertEqual(models.status_code, 200)
        self.assertEqual(models.json["models"][0]["provider"], "development")

        prompts = self.client.get("/api/ai/prompts", headers=self._auth_headers())
        self.assertEqual(prompts.status_code, 200)
        ids = {(item["id"], item["version"]) for item in prompts.json["prompts"]}
        self.assertIn(("task.observation.summary", "v1"), ids)

    def test_firmware_status_packages_and_job(self):
        status = self.client.get(
            f"/api/firmware/devices/{self.device_id}/status",
            headers=self._auth_headers(),
        )
        self.assertEqual(status.status_code, 200)
        self.assertEqual(status.json["firmware"]["execution"], "not_configured")
        self.assertFalse(status.json["firmware"]["updateAvailable"])

        packages = self.client.get("/api/firmware/packages", headers=self._auth_headers())
        self.assertEqual(packages.status_code, 200)
        self.assertEqual(packages.json["packages"], [])

        self._create_firmware_package("fw_2026_06", "2026.06.1")
        packages = self.client.get("/api/firmware/packages", headers=self._auth_headers())
        self.assertEqual(packages.status_code, 200)
        self.assertEqual(len(packages.json["packages"]), 1)
        package_id = packages.json["packages"][0]["id"]

        job = self.client.post(
            "/api/firmware/jobs",
            json={"deviceId": self.device_id, "packageId": package_id},
            headers=self._auth_headers(),
        )
        self.assertEqual(job.status_code, 200)
        self.assertEqual(job.json["job"]["status"], "scheduled")
        self.assertEqual(job.json["execution"], "scheduled")

        status_after = self.client.get(
            f"/api/firmware/devices/{self.device_id}/status",
            headers=self._auth_headers(),
        )
        self.assertEqual(status_after.status_code, 200)
        self.assertEqual(status_after.json["firmware"]["execution"], "available")
        self.assertEqual(status_after.json["firmware"]["lastJob"]["id"], job.json["job"]["id"])

    def _login(self) -> str:
        code = request_debug_code(self.client, "13800002026")
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": "13800002026", "code": code},
        )
        self.assertEqual(login.status_code, 200)
        self.family_id = login.json["family"]["id"]
        return login.json["tokens"]["accessToken"]

    def _create_device(self) -> str:
        parent = self.client.post(
            "/api/setup/parent-identity",
            json={"displayName": "爸爸", "relationship": "爸爸", "relationshipKey": "dad"},
            headers=self._auth_headers(),
        )
        self.assertEqual(parent.status_code, 200)
        response = self.client.post(
            "/api/setup/device",
            json={"bindingCode": "BIND-BOUNDARY", "deviceName": "客厅设备", "location": "客厅"},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["device"]["id"]

    def _create_child(self) -> str:
        wifi = self.client.post(
            "/api/setup/wifi",
            json={"ssid": "Home-5G", "password": "not-stored", "authType": "wpa2"},
            headers=self._auth_headers(),
        )
        self.assertEqual(wifi.status_code, 200)
        response = self.client.post(
            "/api/setup/child",
            json={"name": "小宇", "nickname": "小宇", "ageStage": "kindergarten_middle"},
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200)
        return response.json["child"]["id"]

    def _create_task(self, child_id: str, device_id: str, title: str) -> str:
        response = self.client.post(
            "/api/tasks",
            json={
                "childId": child_id,
                "title": title,
                "taskType": "life",
                "scheduledDate": date.today().isoformat(),
                "scheduledStart": "18:00",
                "deviceId": device_id,
            },
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)
        return response.json["task"]["id"]

    def _start_task(self, task_id: str) -> None:
        response = self.client.post(
            f"/api/tasks/{task_id}/start",
            headers=self._auth_headers(),
        )
        self.assertEqual(response.status_code, 200, response.json)

    def _create_firmware_package(self, package_id: str, version: str) -> None:
        database = Database(self.app.config["DATABASE_URL"])
        with database.transaction() as conn:
            conn.execute(
                """
                INSERT INTO firmware_packages(id, version, channel, status, notes, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    package_id,
                    version,
                    "stable",
                    FIRMWARE_PACKAGE_ACTIVE,
                    "测试固件包",
                    1,
                ),
            )

    def _set_device_runtime_config(
        self,
        device_id: str,
        provider: str,
        config: dict | None = None,
    ) -> None:
        database = Database(self.app.config["DATABASE_URL"])
        repository = DeviceRepository(database)
        with repository.transaction() as conn:
            repository.upsert_device_runtime_config(
                conn,
                family_id=self.family_id,
                device_id=device_id,
                provider=provider,
                config_json=json.dumps(config or {}, ensure_ascii=False),
                secret_ref=None,
                status="active",
                now=now_ms(),
            )

    def _login_family_member(self, *, role: str, phone: str) -> str:
        code = request_debug_code(self.client, phone)
        login = self.client.post(
            "/api/auth/sms/login",
            json={"phone": phone, "code": code},
        )
        self.assertEqual(login.status_code, 200, login.json)
        token = login.json["tokens"]["accessToken"]
        user_id = login.json["user"]["id"]
        database = Database(self.app.config["DATABASE_URL"])
        now = now_ms()
        with database.transaction() as conn:
            conn.execute(
                "UPDATE users SET family_id = ? WHERE id = ?",
                (self.family_id, user_id),
            )
            conn.execute(
                """
                INSERT INTO family_members(
                  id, family_id, user_id, name, phone, role, status,
                  notify_enabled, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, 'active', 1, ?, ?)
                """,
                (
                    f"member_test_{role}_{user_id}",
                    self.family_id,
                    user_id,
                    "只读家人",
                    phone,
                    role,
                    now,
                    now,
                ),
            )
        return token

    def _auth_headers(self) -> dict:
        return {"Authorization": f"Bearer {self.access_token}"}


if __name__ == "__main__":
    unittest.main()
