from __future__ import annotations

from integrations.camera_runtime.base import CameraRuntimeAdapter, CameraSnapshot


class DisabledCameraRuntimeAdapter(CameraRuntimeAdapter):
    adapter_name = "disabled_camera_runtime"

    def health(self) -> dict:
        return {
            "ok": False,
            "status": "unconfigured",
            "message": "摄像头运行时尚未配置。",
        }

    def runtime(self) -> dict:
        return {
            "ok": False,
            "status": "unconfigured",
            "message": "摄像头运行时尚未配置。",
        }

    def speaker_status(self) -> dict:
        return {
            "ok": False,
            "status": "unconfigured",
            "message": "摄像头运行时尚未配置。",
        }

    def snapshot(self) -> CameraSnapshot:
        raise RuntimeError("摄像头运行时尚未配置。")

    def open_stream(self):
        raise RuntimeError("摄像头运行时尚未配置。")

    def webrtc_session(self) -> dict:
        raise RuntimeError("摄像头运行时尚未配置。")

    def webrtc_offer(self, offer_sdp: str) -> dict:
        raise RuntimeError("摄像头运行时尚未配置。")

    def speak(self, text: str) -> dict:
        raise RuntimeError("摄像头运行时尚未配置。")

    def start_monitor(self) -> dict:
        return {
            "ok": False,
            "monitor_runtime": {
                "running": False,
                "status": "unconfigured",
                "last_error": "摄像头运行时尚未配置。",
            },
        }

    def stop_monitor(self) -> dict:
        return {
            "ok": True,
            "monitor_runtime": {
                "running": False,
                "status": "stopped",
                "last_error": "",
            },
        }

    def monitor_status(self) -> dict:
        return {
            "ok": False,
            "monitor_runtime": {
                "running": False,
                "status": "unconfigured",
                "last_error": "摄像头运行时尚未配置。",
            },
        }

    def task_observation(self, task: dict) -> dict:
        return {"verdict": "unavailable", "reason": "camera_unavailable", "evidence": {}}
