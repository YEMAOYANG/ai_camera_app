from __future__ import annotations

from integrations.camera_runtime.base import CameraRuntimeAdapter, CameraSnapshot


class MockCameraRuntimeAdapter(CameraRuntimeAdapter):
    adapter_name = "mock_camera_runtime"

    _tiny_jpeg = bytes.fromhex(
        "ffd8ffe000104a46494600010101006000600000ffdb004300"
        "ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        "ffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
        "ffffffffffffffffffffffffffffffffffffc2000b080001000101"
        "0000ffda0008010100003f00ffd9"
    )

    def health(self) -> dict:
        return {"ok": True, "service": "mock-camera-runtime", "camera": {"connected": True}}

    def runtime(self) -> dict:
        return {"ok": True, "voice": {"state": "idle", "running": False}}

    def speaker_status(self) -> dict:
        return {"ok": True, "running": True, "busy": False, "queue_size": 0}

    def snapshot(self) -> CameraSnapshot:
        return CameraSnapshot(body=self._tiny_jpeg, content_type="image/jpeg")

    def open_stream(self):
        raise RuntimeError("mock runtime does not provide a stream")

    def webrtc_session(self) -> dict:
        return {
            "ok": True,
            "signalingUrl": "ws://127.0.0.1:1984/api/ws?src=mock",
            "stream": "mock",
        }

    def webrtc_offer(self, offer_sdp: str) -> dict:
        return {
            "ok": True,
            "answer": {
                "type": "answer",
                "sdp": "v=0\r\ns=Mock Camera WebRTC\r\n",
                "candidates": [],
            },
        }

    def speak(self, text: str) -> dict:
        return {"ok": True, "speaker": {"text": text, "queued": True}}

    def ptz_move(self, direction: str, step: int) -> dict:
        return {
            "ok": True,
            "status": "queued",
            "direction": direction,
            "step": step,
            "message": "云台控制命令已进入队列",
        }

    def start_monitor(self) -> dict:
        return {"ok": True, "monitor_runtime": {"running": True, "status": "running"}}

    def stop_monitor(self) -> dict:
        return {"ok": True, "monitor_runtime": {"running": False, "status": "stopped"}}

    def monitor_status(self) -> dict:
        return {"ok": True, "monitor_runtime": {"running": False, "status": "idle"}}

    def task_observation(self, task: dict) -> dict:
        return {
            "verdict": "started",
            "reason": "mock_child_ready",
            "confidence": 0.9,
            "evidence": {"activity": "学习", "hasPerson": True, "confidence": 0.9},
        }
