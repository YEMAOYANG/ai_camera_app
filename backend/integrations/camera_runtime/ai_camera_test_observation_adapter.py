from __future__ import annotations

import base64
import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass

from schemas.vision import with_observation_reliability
from services.observation_payload_builder import build_primary_payload, build_source_event_id
from services.vision_child_context import load_child_vision_context
from services.vision_observation_enrich import enrich_observation
from typing import Any, Callable, Mapping, Optional


JsonRequest = Callable[[str, Optional[dict], Optional[Mapping[str, str]], float], dict[str, Any]]


class ObservationAdapterConfigError(RuntimeError):
    pass


class SnapshotUnavailableError(RuntimeError):
    """Raised when ai_camera_test cannot produce a snapshot (e.g. RTSP offline)."""


@dataclass(frozen=True)
class AiCameraTestObservationConfig:
    base_url: str
    internal_url: str
    internal_token: str
    family_id: str
    child_id: str
    device_id: str
    rtsp_url: str = ""
    interval_seconds: float = 5.0
    timeout_seconds: float = 20.0

    @classmethod
    def from_env(cls, environ: Mapping[str, str] | None = None) -> "AiCameraTestObservationConfig":
        env = environ or os.environ
        base_url = (
            env.get("AI_CAMERA_TEST_BASE_URL")
            or env.get("CAMERA_BACKEND_URL")
            or env.get("APP_CAMERA_BACKEND_URL")
            or ""
        )
        return cls(
            base_url=str(base_url).strip(),
            internal_url=str(env.get("CAMERA_OBSERVATION_INTERNAL_URL") or "").strip(),
            internal_token=str(env.get("INTERNAL_API_TOKEN") or env.get("APP_INTERNAL_API_TOKEN") or "").strip(),
            family_id=str(env.get("CAMERA_OBSERVATION_FAMILY_ID") or "").strip(),
            child_id=str(env.get("CAMERA_OBSERVATION_CHILD_ID") or "").strip(),
            device_id=str(env.get("CAMERA_OBSERVATION_DEVICE_ID") or "").strip(),
            rtsp_url=str(env.get("AI_CAMERA_TEST_RTSP_URL") or "").strip(),
            interval_seconds=_float_env(env.get("CAMERA_OBSERVATION_INTERVAL_SECONDS"), 5.0),
            timeout_seconds=_float_env(env.get("CAMERA_OBSERVATION_TIMEOUT_SECONDS"), 20.0),
        )

    def validate(self) -> None:
        missing = [
            name
            for name, value in (
                ("AI_CAMERA_TEST_BASE_URL", self.base_url),
                ("CAMERA_OBSERVATION_INTERNAL_URL", self.internal_url),
                ("INTERNAL_API_TOKEN", self.internal_token),
                ("CAMERA_OBSERVATION_FAMILY_ID", self.family_id),
                ("CAMERA_OBSERVATION_CHILD_ID", self.child_id),
                ("CAMERA_OBSERVATION_DEVICE_ID", self.device_id),
            )
            if not str(value or "").strip()
        ]
        if missing:
            raise ObservationAdapterConfigError(
                "Missing camera observation worker configuration: " + ", ".join(missing)
            )
        if self.interval_seconds <= 0:
            raise ObservationAdapterConfigError("CAMERA_OBSERVATION_INTERVAL_SECONDS must be positive.")
        if self.timeout_seconds <= 0:
            raise ObservationAdapterConfigError("CAMERA_OBSERVATION_TIMEOUT_SECONDS must be positive.")

    @property
    def snapshot_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/api/camera/snapshot?format=data_url"

    @property
    def observation_url(self) -> str:
        value = self.internal_url.rstrip("/")
        if value.endswith("/internal/camera/observations"):
            return value
        return f"{value}/internal/camera/observations"


DATA_URL_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<data>.+)$", re.DOTALL)


class AiCameraTestObservationAdapter:
    source = "ai_camera_test"

    def __init__(
        self,
        config: AiCameraTestObservationConfig,
        *,
        json_request: JsonRequest | None = None,
        vision_service=None,
        observe_service=None,
    ):
        config.validate()
        self.config = config
        self._json_request = json_request or _json_request
        self.vision_service = vision_service
        self.observe_service = observe_service

    def fetch_snapshot_bytes(self) -> tuple[bytes, str]:
        snapshot = self._json_request(
            self.config.snapshot_url,
            None,
            None,
            self.config.timeout_seconds,
        )
        image = str(snapshot.get("image") or "")
        if not image:
            raise RuntimeError("旧摄像头运行时没有返回可用画面。")
        return _decode_data_url(image)

    def fetch_analysis(self) -> dict:
        body, content_type = self.fetch_snapshot_bytes()
        if self.observe_service is not None:
            result = self.observe_service.run_tick(
                family_id=self.config.family_id,
                child_id=self.config.child_id,
                device_id=self.config.device_id,
                image_bytes=body,
                content_type=content_type,
                source=self.source,
                force_analyze=False,
                post_observation=self.post_observation,
            )
            if result.analysis is not None:
                return result.analysis
            return {"has_person": None, "activity": "", "confidence": 0.0, "description": result.skip_reason}
        if self.vision_service is None:
            raise RuntimeError("Vision 服务未配置，无法分析画面。")
        vision_context = load_child_vision_context(
            self._database_url(),
            family_id=self.config.family_id,
            child_id=self.config.child_id,
        )
        return with_observation_reliability(
            enrich_observation(
                self.vision_service.analyze_snapshot(
                    image_bytes=body,
                    content_type=content_type,
                    device_key=self.config.device_id or self.config.base_url,
                    context=vision_context,
                    force_analyze=False,
                )
            )
        )

    def payloads_from_analysis(
        self,
        analysis: Mapping[str, object],
        *,
        window_start_ms: int,
        window_end_ms: int,
        observed_at: int | None = None,
    ) -> list[dict]:
        observed_at = observed_at if observed_at is not None else window_end_ms
        payload = build_primary_payload(
            analysis,
            family_id=self.config.family_id,
            child_id=self.config.child_id,
            device_id=self.config.device_id,
            source=self.source,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            observed_at=observed_at,
        )
        return [payload] if payload else []

    def post_observation(self, payload: dict) -> dict:
        return self._json_request(
            self.config.observation_url,
            payload,
            {
                "Content-Type": "application/json",
                "X-Mira-Internal-Token": self.config.internal_token,
                "X-Mira-Internal-Source": self.source,
            },
            self.config.timeout_seconds,
        )

    def run_observe_tick(self, *, window_start_ms: int, window_end_ms: int) -> dict:
        try:
            body, content_type = self.fetch_snapshot_bytes()
        except SnapshotUnavailableError as exc:
            return {
                "skipped": True,
                "skip_reason": "snapshot_unavailable",
                "posted": False,
                "observation_count": 0,
                "analysis": None,
                "response": None,
                "message": str(exc),
            }
        service = self.observe_service
        if service is None:
            from services.camera_observe_service import build_observe_service_from_env

            service = build_observe_service_from_env()
        result = service.run_tick(
            family_id=self.config.family_id,
            child_id=self.config.child_id,
            device_id=self.config.device_id,
            image_bytes=body,
            content_type=content_type,
            source=self.source,
            force_analyze=False,
            window_start_ms=window_start_ms,
            window_end_ms=window_end_ms,
            post_observation=self.post_observation,
        )
        return {
            "skipped": result.skipped,
            "skip_reason": result.skip_reason,
            "posted": result.posted,
            "observation_count": result.observation_count,
            "analysis": result.analysis,
            "response": result.response,
        }

    def _database_url(self) -> str:
        return str(os.environ.get("DATABASE_URL") or os.environ.get("APP_DATABASE_URL") or "").strip()


def _decode_data_url(value: str) -> tuple[bytes, str]:
    match = DATA_URL_RE.match(str(value or "").strip())
    if not match:
        raise RuntimeError("snapshot 返回的图片格式无效。")
    mime = str(match.group("mime") or "image/jpeg").strip() or "image/jpeg"
    data = match.group("data")
    try:
        return base64.b64decode(data), mime
    except Exception as exc:
        raise RuntimeError("snapshot 图片解码失败。") from exc


def _json_request(
    url: str,
    payload: dict | None,
    headers: Mapping[str, str] | None,
    timeout: float,
) -> dict:
    data = None
    method = "GET"
    request_headers = dict(headers or {})
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers.setdefault("Content-Type", "application/json")
        method = "POST"
    request = urllib.request.Request(url, data=data, headers=request_headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8", "ignore") or "{}")
    except urllib.error.HTTPError as exc:
        if exc.code in {502, 503, 504}:
            body = exc.read().decode("utf-8", "ignore")
            message = _snapshot_error_message(body, exc)
            raise SnapshotUnavailableError(message) from exc
        raise


def _snapshot_error_message(body: str, exc: urllib.error.HTTPError) -> str:
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        return str(exc.reason or f"HTTP {exc.code}")
    message = str(payload.get("message") or payload.get("error") or "").strip()
    if not message:
        return str(exc.reason or f"HTTP {exc.code}")
    if "No route to host" in message:
        return "摄像头 RTSP 不可达，请检查摄像头是否在线、IP 是否正确。"
    if "Connection refused" in message or "Connection timed out" in message:
        return "摄像头 RTSP 连接失败，请检查网络与 RTSP 地址。"
    first_line = message.splitlines()[0].strip()
    return first_line or str(exc.reason or f"HTTP {exc.code}")


def _float_env(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
