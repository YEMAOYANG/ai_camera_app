from __future__ import annotations

import urllib.error

from integrations.camera_runtime.ai_camera_test_adapter import AiCameraTestRuntimeAdapter
from integrations.camera_runtime.base import CameraRuntimeAdapter, CameraSnapshot


class CameraBridgeError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CameraBridgeService:
    def __init__(self, base_url: str, *, adapter: CameraRuntimeAdapter | None = None):
        self.adapter = adapter or AiCameraTestRuntimeAdapter(base_url)

    def health(self) -> dict:
        return self._runtime_json(self.adapter.health)

    def runtime(self) -> dict:
        return self._runtime_json(self.adapter.runtime)

    def speaker_status(self) -> dict:
        return self._runtime_json(self.adapter.speaker_status)

    def _runtime_json(self, getter) -> dict:
        try:
            payload = getter()
            return {
                "ok": True,
                "cameraRuntime": {
                    "reachable": True,
                    "adapter": self.adapter.adapter_name,
                    "data": payload,
                },
            }
        except Exception as exc:
            return {
                "ok": False,
                "cameraRuntime": {
                    "reachable": False,
                    "adapter": self.adapter.adapter_name,
                    "error": str(exc),
                },
            }

    def fetch_snapshot(self) -> CameraSnapshot:
        try:
            return self.adapter.snapshot()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            raise CameraBridgeError("camera_snapshot_failed", body, exc.code) from exc
        except Exception as exc:
            raise CameraBridgeError("camera_snapshot_failed", str(exc), 502) from exc

    def open_stream(self):
        try:
            return self.adapter.open_stream()
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            raise CameraBridgeError("camera_stream_failed", body, exc.code) from exc
        except Exception as exc:
            raise CameraBridgeError("camera_stream_failed", str(exc), 502) from exc
