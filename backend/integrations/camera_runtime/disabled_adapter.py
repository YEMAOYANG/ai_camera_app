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
