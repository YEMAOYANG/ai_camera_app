from __future__ import annotations

import json
import urllib.error

from core.security import now_ms
from integrations.camera_runtime.base import CameraRuntimeAdapter, CameraSnapshot
from schemas.camera import camera_status_payload


class CameraBridgeError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 502):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status_code = status_code


class CameraBridgeService:
    def __init__(self, base_url: str | None = None, *, adapter: CameraRuntimeAdapter):
        self.adapter = adapter

    def health(self) -> dict:
        return self._runtime_json(self.adapter.health)

    def runtime(self) -> dict:
        return self._runtime_json(self.adapter.runtime)

    def speaker_status(self) -> dict:
        return self._runtime_json(self.adapter.speaker_status)

    def status(self, *, current_task: dict | None = None) -> dict:
        health = self._runtime_json(self.adapter.health)
        runtime = self._runtime_json(self.adapter.runtime)
        speaker = self._runtime_json(self.adapter.speaker_status)
        monitor = self.monitor_status()
        reachable = bool(health.get("cameraRuntime", {}).get("reachable"))
        runtime_reachable = bool(runtime.get("cameraRuntime", {}).get("reachable"))
        speaker_reachable = bool(speaker.get("cameraRuntime", {}).get("reachable"))
        monitor_runtime = monitor.get("monitorRuntime", {})
        monitor_reachable = bool(monitor_runtime.get("reachable"))
        monitor_data = monitor_runtime.get("data") or {}
        monitor_payload = monitor_data.get("monitor_runtime") or monitor_data
        health_data = health.get("cameraRuntime", {}).get("data") or {}
        camera_data = health_data.get("camera") if isinstance(health_data, dict) else {}
        monitor_available = monitor_reachable and (
            bool(monitor_payload.get("running"))
            or str(monitor_payload.get("status", "")).lower() not in {"", "unconfigured", "unavailable"}
        )
        ptz_available = reachable and _camera_supports_ptz(camera_data)
        status_value = "online" if reachable else "offline"
        if reachable and not runtime_reachable:
            status_value = "connecting"
        if not reachable and health.get("ok") is False:
            status_value = "offline"
        message = (
            "摄像头在线，最新状态已同步。"
            if reachable
            else "摄像头暂时离线，任务仍会按计划记录。"
        )
        return {
            "ok": True,
            "status": camera_status_payload(
                connection_status=status_value,
                stream_available=reachable,
                snapshot_available=reachable,
                speaker_available=speaker_reachable,
                monitor_available=monitor_available,
                ptz_available=ptz_available,
                last_seen_at=now_ms() if reachable else None,
                runtime_provider=self.adapter.adapter_name,
                current_task=current_task,
                message=message,
            ),
        }

    def speak(self, text: str) -> dict:
        try:
            return self._require_ok(self.adapter.speak(text), "camera_speak_failed")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            raise CameraBridgeError("camera_speak_failed", body, exc.code) from exc
        except Exception as exc:
            raise CameraBridgeError("camera_speak_failed", str(exc), 502) from exc

    def ptz_move(self, direction: str, step: int) -> dict:
        try:
            return self._require_ok(self.adapter.ptz_move(direction, step), "camera_ptz_failed")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            raise CameraBridgeError("camera_ptz_failed", body, exc.code) from exc
        except Exception as exc:
            raise CameraBridgeError("camera_ptz_failed", str(exc), 502) from exc

    def start_monitor(self) -> dict:
        try:
            return self._require_ok(self.adapter.start_monitor(), "camera_monitor_start_failed")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            raise CameraBridgeError("camera_monitor_start_failed", body, exc.code) from exc
        except Exception as exc:
            raise CameraBridgeError("camera_monitor_start_failed", str(exc), 502) from exc

    def stop_monitor(self) -> dict:
        try:
            return self._require_ok(self.adapter.stop_monitor(), "camera_monitor_stop_failed")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            raise CameraBridgeError("camera_monitor_stop_failed", body, exc.code) from exc
        except Exception as exc:
            raise CameraBridgeError("camera_monitor_stop_failed", str(exc), 502) from exc

    def monitor_status(self) -> dict:
        try:
            payload = self.adapter.monitor_status()
            return {
                "ok": True,
                "monitorRuntime": {
                    "reachable": True,
                    "adapter": self.adapter.adapter_name,
                    "data": payload,
                },
            }
        except Exception as exc:
            return {
                "ok": False,
                "monitorRuntime": {
                    "reachable": False,
                    "adapter": self.adapter.adapter_name,
                    "error": str(exc),
                    "data": {
                        "monitor_runtime": {
                            "running": False,
                            "status": "unavailable",
                            "last_error": str(exc),
                        }
                    },
                },
            }

    def task_observation(self, task: dict) -> dict:
        try:
            if not hasattr(self.adapter, "task_observation"):
                return {"verdict": "unavailable", "reason": "observation_not_supported", "evidence": {}}
            payload = self.adapter.task_observation(task)
            if not isinstance(payload, dict):
                return {"verdict": "unavailable", "reason": "invalid_observation", "evidence": {}}
            return {
                "verdict": str(payload.get("verdict") or "unavailable"),
                "reason": str(payload.get("reason") or ""),
                "confidence": float(payload.get("confidence") or 0.0),
                "evidence": payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {},
            }
        except Exception as exc:
            return {"verdict": "unavailable", "reason": str(exc), "confidence": 0.0, "evidence": {}}

    def _runtime_json(self, getter) -> dict:
        try:
            payload = getter()
            if isinstance(payload, dict) and payload.get("ok") is False:
                return {
                    "ok": False,
                    "cameraRuntime": {
                        "reachable": False,
                        "adapter": self.adapter.adapter_name,
                        "data": self._public_runtime_payload(payload),
                    },
                }
            return {
                "ok": True,
                "cameraRuntime": {
                    "reachable": True,
                    "adapter": self.adapter.adapter_name,
                    "data": self._public_runtime_payload(payload),
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

    def webrtc_session(self) -> dict:
        try:
            payload = self._require_ok(
                self.adapter.webrtc_session(),
                "camera_webrtc_session_failed",
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            raise CameraBridgeError("camera_webrtc_session_failed", body, exc.code) from exc
        except Exception as exc:
            raise CameraBridgeError("camera_webrtc_session_failed", str(exc), 502) from exc
        signaling_url = str(payload.get("signalingUrl") or "").strip()
        if not signaling_url:
            raise CameraBridgeError(
                "camera_webrtc_session_failed",
                "实时画面暂时无法建立连接。",
                502,
            )
        return {
            "ok": True,
            "session": {
                "signalingUrl": signaling_url,
                "message": "实时画面连接已准备好。",
            },
        }

    def webrtc_offer(self, offer_sdp: str) -> dict:
        try:
            payload = self._require_ok(
                self.adapter.webrtc_offer(offer_sdp),
                "camera_webrtc_failed",
            )
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", "ignore")
            raise CameraBridgeError("camera_webrtc_failed", body, exc.code) from exc
        except Exception as exc:
            raise CameraBridgeError("camera_webrtc_failed", str(exc), 502) from exc
        answer = payload.get("answer") if isinstance(payload, dict) else {}
        if not isinstance(answer, dict) or not answer.get("sdp"):
            raise CameraBridgeError("camera_webrtc_failed", "实时画面暂时无法建立连接。", 502)
        return {
            "ok": True,
            "session": {
                "type": "answer",
                "sdp": str(answer.get("sdp") or ""),
                "candidates": [
                    str(candidate)
                    for candidate in answer.get("candidates", [])
                    if str(candidate or "").strip()
                ],
                "message": "实时画面连接已准备好。",
            },
        }

    def _require_ok(self, payload: dict, code: str) -> dict:
        if isinstance(payload, dict) and payload.get("ok") is False:
            message = payload.get("message") or payload.get("status") or "摄像头暂时不可用。"
            raise CameraBridgeError(code, str(message), 502)
        return payload

    def _public_runtime_payload(self, payload: object) -> dict:
        if not isinstance(payload, dict):
            return {}

        public: dict = {}
        for key in ("ok", "status", "service", "message"):
            if key in payload and isinstance(payload[key], (str, bool, int, float)):
                public[key] = payload[key]

        camera = payload.get("camera")
        if isinstance(camera, dict):
            capabilities = camera.get("capabilities") if isinstance(camera.get("capabilities"), dict) else {}
            ptz = camera.get("ptz") if isinstance(camera.get("ptz"), dict) else {}
            public["camera"] = {
                "configured": bool(camera.get("configured")),
                "connected": bool(camera.get("connected")),
                "capabilities": {
                    "ptz": bool(capabilities.get("ptz") or ptz.get("enabled")),
                },
                "ptz": {
                    "enabled": bool(ptz.get("enabled") or capabilities.get("ptz")),
                    "protocol": str(ptz.get("protocol") or ""),
                },
                "webrtc": {
                    "enabled": bool((camera.get("webrtc") or {}).get("enabled"))
                    if isinstance(camera.get("webrtc"), dict)
                    else False,
                    "mode": str((camera.get("webrtc") or {}).get("mode") or "")
                    if isinstance(camera.get("webrtc"), dict)
                    else "",
                },
            }

        voice = payload.get("voice")
        if isinstance(voice, dict):
            public["voice"] = {
                "state": str(voice.get("state") or ""),
                "running": bool(voice.get("running")),
            }

        voice_runtime = payload.get("voice_runtime")
        if isinstance(voice_runtime, dict):
            public["voiceRuntime"] = {
                "state": str(voice_runtime.get("state") or ""),
                "running": bool(voice_runtime.get("running")),
                "stale": bool(voice_runtime.get("stale")),
            }

        speaker = payload.get("speaker")
        if isinstance(speaker, dict):
            public["speaker"] = {
                "busy": bool(speaker.get("busy")),
                "running": bool(speaker.get("running")),
                "queueSize": int(speaker.get("queue_size") or speaker.get("queueSize") or 0),
            }
        if "busy" in payload or "queue_size" in payload:
            public["speaker"] = {
                "busy": bool(payload.get("busy")),
                "running": bool(payload.get("running", True)),
                "queueSize": int(payload.get("queue_size") or 0),
            }

        monitor_runtime = payload.get("monitor_runtime")
        if isinstance(monitor_runtime, dict):
            public["monitorRuntime"] = {
                "running": bool(monitor_runtime.get("running")),
                "stale": bool(monitor_runtime.get("stale")),
                "status": str(monitor_runtime.get("status") or monitor_runtime.get("state") or ""),
            }

        task_runtime = payload.get("task_runtime")
        if isinstance(task_runtime, dict):
            snapshot = task_runtime.get("snapshot") if isinstance(task_runtime.get("snapshot"), dict) else {}
            public["taskRuntime"] = {
                "running": bool(task_runtime.get("running") or task_runtime.get("alive")),
                "state": str(task_runtime.get("state") or snapshot.get("status") or ""),
            }

        return public or {"status": "available"}


def json_text(value: object) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _camera_supports_ptz(camera_data: object) -> bool:
    if not isinstance(camera_data, dict):
        return False
    capabilities = camera_data.get("capabilities")
    if isinstance(capabilities, dict) and capabilities.get("ptz") is True:
        return True
    ptz = camera_data.get("ptz")
    return isinstance(ptz, dict) and ptz.get("enabled") is True
