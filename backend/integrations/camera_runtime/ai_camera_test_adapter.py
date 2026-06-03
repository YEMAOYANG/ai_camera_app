from __future__ import annotations

import json
import urllib.request

from integrations.camera_runtime.base import CameraRuntimeAdapter, CameraSnapshot


class AiCameraTestRuntimeAdapter(CameraRuntimeAdapter):
    adapter_name = "ai_camera_test_bridge"

    def __init__(self, base_url: str):
        self.base_url = base_url.rstrip("/")

    def health(self) -> dict:
        return self._fetch_json("/api/health")

    def runtime(self) -> dict:
        return self._fetch_json("/api/voice/runtime")

    def speaker_status(self) -> dict:
        return self._fetch_json("/api/camera/speaker/status")

    def snapshot(self) -> CameraSnapshot:
        with self._open("/api/camera/snapshot", timeout=8.0) as response:
            return CameraSnapshot(
                body=response.read(),
                content_type=response.headers.get("content-type", "image/jpeg"),
            )

    def open_stream(self):
        return self._open("/api/camera/stream", timeout=8.0)

    def _fetch_json(self, path: str, *, timeout: float = 3.0) -> dict:
        with self._open(path, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _open(self, path: str, *, timeout: float):
        return urllib.request.urlopen(f"{self.base_url}{path}", timeout=timeout)
