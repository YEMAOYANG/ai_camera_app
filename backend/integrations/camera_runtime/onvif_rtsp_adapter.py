from __future__ import annotations

import asyncio
import hashlib
import json
import time
from typing import Any, Callable, Mapping
from urllib.parse import quote, urlsplit, urlunsplit

import websockets

from integrations.camera_runtime.base import CameraRuntimeAdapter, CameraSnapshot
from integrations.camera_runtime.go2rtc_client import Go2RtcClient
from integrations.onvif.client import (
    OnvifClient,
    OnvifUnavailableError,
    RtspUnavailableError,
    VerifiedOnvifDevice,
)
from services.device_credential_store import EncryptedFileCredentialStore


class OnvifRtspRuntimeAdapter(CameraRuntimeAdapter):
    """Safe ONVIF/RTSP runtime edge.

    ONVIF status and snapshots are handled directly. Continuous RTSP-to-WebRTC
    transport intentionally remains behind a media gateway; raw RTSP endpoints
    and credentials never cross this adapter into an App response.
    """

    adapter_name = "onvif_rtsp_runtime"

    def __init__(
        self,
        *,
        config: Mapping,
        secret_ref: str,
        client: OnvifClient,
        credential_store: EncryptedFileCredentialStore,
        media_gateway: Go2RtcClient | None = None,
        stream_name: str = "",
        recover_runtime: Callable[
            [Mapping[str, Any]],
            tuple[dict[str, Any], VerifiedOnvifDevice] | None,
        ]
        | None = None,
    ):
        self.config = dict(config or {})
        self.secret_ref = str(secret_ref or "")
        self.client = client
        self.credential_store = credential_store
        self.media_gateway = media_gateway
        self.stream_name = str(stream_name or "").strip()
        self.recover_runtime = recover_runtime
        self._verified: VerifiedOnvifDevice | None = None
        self._verified_at = 0.0
        self._registered_source_digest = ""

    def health(self) -> dict:
        verified = self._verify()
        stream_available = self._media_stream_available()
        return {
            "ok": True,
            "status": "online",
            "service": "onvif-camera",
            "camera": {
                "configured": True,
                "connected": True,
                "streamAvailable": stream_available,
                "snapshotAvailable": True,
                "capabilities": {
                    "ptz": False,
                    "detectedPtz": bool(verified.has_ptz),
                    "audio": bool(verified.has_audio),
                },
                "ptz": {
                    "enabled": False,
                    "protocol": "",
                },
                "webrtc": {
                    "enabled": stream_available,
                    "mode": "media_gateway" if stream_available else "unavailable",
                },
            },
        }

    def runtime(self) -> dict:
        verified = self._verify()
        stream_available = self._media_stream_available()
        return {
            "ok": True,
            "status": "connected",
            "camera": {
                "configured": True,
                "connected": True,
                "streamAvailable": stream_available,
                "snapshotAvailable": True,
                "capabilities": {
                    "ptz": False,
                    "detectedPtz": bool(verified.has_ptz),
                    "audio": bool(verified.has_audio),
                },
                "webrtc": {
                    "enabled": stream_available,
                    "mode": "media_gateway" if stream_available else "unavailable",
                },
            },
            "message": (
                "摄像头已连接，实时画面已准备好。"
                if stream_available
                else "摄像头已连接，实时画面暂时不可用。"
            ),
        }

    def speaker_status(self) -> dict:
        return {
            "ok": False,
            "status": "unsupported",
            "message": "当前摄像头尚未接入双向语音协议。",
        }

    def snapshot(self) -> CameraSnapshot:
        credentials = self._credentials()
        try:
            body, content_type = self._fetch_snapshot(credentials)
        except (OnvifUnavailableError, RtspUnavailableError):
            if not self._recover():
                raise
            credentials = self._credentials()
            body, content_type = self._fetch_snapshot(credentials)
        return CameraSnapshot(body=body, content_type=content_type)

    def open_stream(self):
        raise RuntimeError("当前摄像头请使用实时画面连接。")

    def webrtc_session(self) -> dict:
        self._ensure_media_stream()
        if self.media_gateway is None:
            raise RuntimeError("实时画面服务尚未配置。")
        return {
            "ok": True,
            "signalingUrl": self.media_gateway.websocket_url(self.stream_name),
            "stream": self.stream_name,
        }

    def webrtc_offer(self, offer_sdp: str) -> dict:
        offer_sdp = str(offer_sdp or "").strip()
        if not offer_sdp:
            raise RuntimeError("实时画面连接信息不完整。")
        session = self.webrtc_session()
        return asyncio.run(
            self._exchange_webrtc_offer(
                str(session["signalingUrl"]),
                offer_sdp,
            )
        )

    def speak(self, text: str) -> dict:
        raise RuntimeError("当前摄像头尚未接入双向语音协议。")

    def ptz_move(self, direction: str, step: int) -> dict:
        raise RuntimeError("当前 ONVIF 云台控制尚未接入。")

    def start_monitor(self) -> dict:
        return {
            "ok": False,
            "monitor_runtime": {
                "running": False,
                "status": "media_gateway_required",
                "last_error": "实时视频网关尚未配置。",
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
                "status": "media_gateway_required",
                "last_error": "实时视频网关尚未配置。",
            },
        }

    def refresh_monitor_observation(self, *, vision_context: dict | None = None) -> dict:
        return self.monitor_status()

    def task_observation(self, task: dict) -> dict:
        return {
            "verdict": "unavailable",
            "reason": "media_gateway_required",
            "confidence": 0.0,
            "evidence": {},
        }

    def _verify(
        self,
        *,
        allow_recovery: bool = True,
    ) -> VerifiedOnvifDevice:
        now = time.monotonic()
        if self._verified is not None and now - self._verified_at < 10:
            return self._verified
        credentials = self._credentials()
        try:
            verified = self.client.inspect_and_verify(
                device_service_url=self._device_service_url(),
                username=credentials["username"],
                password=credentials["password"],
            )
        except (OnvifUnavailableError, RtspUnavailableError):
            if not allow_recovery or not self._recover():
                raise
            assert self._verified is not None
            return self._verified
        self._verified = verified
        self._verified_at = now
        return verified

    def _recover(self) -> bool:
        if self.recover_runtime is None:
            return False
        recovered = self.recover_runtime(dict(self.config))
        if recovered is None:
            return False
        config, verified = recovered
        self.config = dict(config)
        self._verified = verified
        self._verified_at = time.monotonic()
        self._registered_source_digest = ""
        return True

    def _fetch_snapshot(
        self,
        credentials: Mapping[str, str],
    ) -> tuple[bytes, str]:
        return self.client.fetch_snapshot(
            device_service_url=self._device_service_url(),
            profile_token=self._profile_token(),
            username=credentials["username"],
            password=credentials["password"],
        )

    def _credentials(self) -> dict[str, str]:
        return self.credential_store.load_onvif_credentials(self.secret_ref)

    def _device_service_url(self) -> str:
        value = str(self.config.get("deviceServiceUrl") or "").strip()
        if not value:
            raise RuntimeError("ONVIF 设备地址尚未配置。")
        return value

    def _profile_token(self) -> str:
        value = str(self.config.get("profileToken") or "").strip()
        if not value:
            raise RuntimeError("ONVIF 视频 Profile 尚未配置。")
        return value

    def _media_stream_available(self) -> bool:
        try:
            if self.media_gateway is None or not self.stream_name:
                return False
            verified = self._verify()
            encoding = (
                verified.preview_video_encoding
                or verified.video_encoding
                or ""
            )
            return (
                _normalized_encoding(encoding) == "h264"
                and self.media_gateway.is_healthy()
            )
        except Exception:
            return False

    def _ensure_media_stream(self) -> None:
        if self.media_gateway is None or not self.stream_name:
            raise RuntimeError("实时画面服务尚未配置。")
        verified = self._verify()
        encoding = (
            verified.preview_video_encoding
            or verified.video_encoding
            or ""
        )
        if _normalized_encoding(encoding) != "h264":
            raise RuntimeError("摄像头没有可用于实时预览的视频流。")
        credentials = self._credentials()
        source = _rtsp_uri_with_credentials(
            verified.preview_rtsp_uri or verified.rtsp_uri,
            username=credentials["username"],
            password=credentials["password"],
        )
        source_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        if self._registered_source_digest == source_digest:
            return
        self.media_gateway.register_stream(self.stream_name, source)
        self._registered_source_digest = source_digest

    async def _exchange_webrtc_offer(
        self,
        signaling_url: str,
        offer_sdp: str,
    ) -> dict:
        answer_sdp = ""
        candidates: list[str] = []
        deadline = time.monotonic() + 8
        async with websockets.connect(
            signaling_url,
            open_timeout=4,
            close_timeout=1,
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
                elif message_type == "webrtc/candidate" and value:
                    candidates.append(value)
                    if answer_sdp:
                        break
        if not answer_sdp:
            raise RuntimeError("实时画面暂时无法建立连接。")
        return {
            "ok": True,
            "answer": {
                "type": "answer",
                "sdp": answer_sdp,
                "candidates": candidates,
            },
        }


def _normalized_encoding(value: object) -> str:
    return "".join(
        character
        for character in str(value or "").strip().lower()
        if character.isalnum()
    )


def _rtsp_uri_with_credentials(
    rtsp_uri: str,
    *,
    username: str,
    password: str,
) -> str:
    parsed = urlsplit(str(rtsp_uri or "").strip())
    if parsed.scheme.lower() != "rtsp" or not parsed.hostname:
        raise RuntimeError("摄像头视频流地址无效。")
    hostname = parsed.hostname
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    port = f":{parsed.port}" if parsed.port is not None else ""
    userinfo = (
        f"{quote(str(username), safe='')}:{quote(str(password), safe='')}@"
    )
    return urlunsplit(
        (
            "rtsp",
            f"{userinfo}{hostname}{port}",
            parsed.path or "/",
            parsed.query,
            "",
        )
    )
