from __future__ import annotations

import asyncio
import json
import time
import urllib.parse
import urllib.request

import websockets

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

    def webrtc_session(self) -> dict:
        health = self.health()
        camera = health.get("camera") if isinstance(health, dict) else {}
        if not isinstance(camera, dict):
            camera = {}
        go2rtc_base = str(camera.get("go2rtc_base") or "").rstrip("/")
        stream = str(
            camera.get("preview_stream")
            or camera.get("stream")
            or (camera.get("webrtc") or {}).get("stream")
            or ""
        ).strip()
        if not go2rtc_base or not stream:
            raise RuntimeError("WebRTC preview stream is not available")
        return {
            "ok": True,
            "signalingUrl": self._go2rtc_ws_url(go2rtc_base, stream),
            "stream": stream,
        }

    def webrtc_offer(self, offer_sdp: str) -> dict:
        offer_sdp = str(offer_sdp or "").strip()
        if not offer_sdp:
            raise RuntimeError("WebRTC offer is empty")
        health = self.health()
        camera = health.get("camera") if isinstance(health, dict) else {}
        if not isinstance(camera, dict):
            camera = {}
        go2rtc_base = str(camera.get("go2rtc_base") or "").rstrip("/")
        stream = str(
            camera.get("preview_stream")
            or camera.get("stream")
            or (camera.get("webrtc") or {}).get("stream")
            or ""
        ).strip()
        if not go2rtc_base or not stream:
            raise RuntimeError("WebRTC preview stream is not available")
        ws_url = self._go2rtc_ws_url(go2rtc_base, stream)
        return asyncio.run(self._exchange_webrtc_offer(ws_url, offer_sdp))

    def speak(self, text: str) -> dict:
        return self._post_json("/api/camera/speaker/speak", {"text": text}, timeout=12.0)

    def ptz_move(self, direction: str, step: int) -> dict:
        return self._post_json(
            "/api/camera/ptz/move",
            {"direction": direction, "step": step},
            timeout=8.0,
        )

    def start_monitor(self) -> dict:
        return self._post_json("/api/monitor/start", {}, timeout=8.0)

    def stop_monitor(self) -> dict:
        return self._post_json("/api/monitor/stop", {}, timeout=8.0)

    def monitor_status(self) -> dict:
        return self._fetch_json("/api/monitor/runtime")

    def task_observation(self, task: dict) -> dict:
        payload = self.monitor_status()
        runtime = payload.get("monitor_runtime") if isinstance(payload, dict) else {}
        if not isinstance(runtime, dict):
            return {"verdict": "unavailable", "reason": "monitor_unavailable", "evidence": {}}
        observation = runtime.get("last_observation") or runtime.get("observation")
        if not isinstance(observation, dict):
            snapshot = runtime.get("snapshot")
            if isinstance(snapshot, dict):
                observation = snapshot.get("last_observation")
        if not isinstance(observation, dict):
            return {"verdict": "insufficient", "reason": "no_recent_observation", "evidence": {}}
        return self._decide_task_observation(task, observation)

    def _decide_task_observation(self, task: dict, observation: dict) -> dict:
        activity = str(observation.get("activity") or observation.get("raw_activity") or "")
        description = str(observation.get("description") or observation.get("child_message") or "")
        text = f"{activity} {description}"
        task_type = str(task.get("type") or task.get("task_type") or "")
        confidence = float(observation.get("confidence") or 0.0)
        evidence = {
            "activity": activity,
            "description": description[:160],
            "hasPerson": bool(observation.get("has_person")),
            "confidence": confidence,
            "homeworkLike": bool(observation.get("homework_like")),
        }
        if observation.get("has_person") is False:
            return {
                "verdict": "not_started",
                "reason": "child_not_present",
                "confidence": max(confidence, 0.6),
                "evidence": evidence,
            }
        if activity in {"离开", "走动", "玩玩具", "看电视", "玩手机", "看手机", "打游戏"}:
            return {
                "verdict": "not_started",
                "reason": "distracted_or_away",
                "confidence": max(confidence, 0.5),
                "evidence": evidence,
            }
        if task_type in {"learning", "reading_interest", "schoolbag"}:
            started_words = ("看书", "阅读", "作业", "书本", "练习册", "写字", "学习", "整理书包")
            if observation.get("homework_like") or any(word in text for word in started_words):
                return {
                    "verdict": "started",
                    "reason": "task_evidence_confirmed",
                    "confidence": confidence,
                    "evidence": evidence,
                }
        if observation.get("has_person") and confidence >= 0.7:
            return {
                "verdict": "started",
                "reason": "child_present",
                "confidence": confidence,
                "evidence": evidence,
            }
        return {
            "verdict": "insufficient",
            "reason": "present_without_task_evidence",
            "confidence": confidence,
            "evidence": evidence,
        }

    def _fetch_json(self, path: str, *, timeout: float = 3.0) -> dict:
        with self._open(path, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _post_json(self, path: str, payload: dict, *, timeout: float) -> dict:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))

    def _open(self, path: str, *, timeout: float):
        return urllib.request.urlopen(f"{self.base_url}{path}", timeout=timeout)

    def _go2rtc_ws_url(self, base_url: str, stream: str) -> str:
        parsed = urllib.parse.urlparse(base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        netloc = parsed.netloc
        if not netloc:
            raise RuntimeError("WebRTC base URL is invalid")
        query = urllib.parse.urlencode({"src": stream})
        return urllib.parse.urlunparse((scheme, netloc, "/api/ws", "", query, ""))

    async def _exchange_webrtc_offer(self, ws_url: str, offer_sdp: str) -> dict:
        answer_sdp = ""
        candidates: list[str] = []
        deadline = time.monotonic() + 8.0
        async with websockets.connect(
            ws_url,
            open_timeout=4.0,
            close_timeout=1.0,
            max_size=8 * 1024 * 1024,
        ) as websocket:
            await websocket.send(
                json.dumps(
                    {"type": "webrtc/offer", "value": offer_sdp},
                    ensure_ascii=False,
                )
            )
            while time.monotonic() < deadline:
                timeout = max(0.2, deadline - time.monotonic())
                try:
                    raw = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                except TimeoutError:
                    break
                if not isinstance(raw, str):
                    continue
                message = json.loads(raw)
                message_type = str(message.get("type") or "")
                value = str(message.get("value") or "")
                if message_type == "webrtc/answer":
                    answer_sdp = value
                    if candidates:
                        break
                    continue
                if message_type == "webrtc/candidate":
                    if value:
                        candidates.append(value)
                    elif answer_sdp:
                        break
                    continue
                if message_type == "error":
                    raise RuntimeError(value or "WebRTC signaling failed")
        if not answer_sdp:
            raise RuntimeError("WebRTC answer was not returned")
        return {
            "ok": True,
            "answer": {
                "type": "answer",
                "sdp": answer_sdp,
                "candidates": candidates,
            },
        }
