from __future__ import annotations

import base64
import json
import os
import re
import urllib.request
from dataclasses import dataclass

from services.vision_child_context import load_child_vision_context
from typing import Any, Callable, Mapping, Optional


JsonRequest = Callable[[str, Optional[dict], Optional[Mapping[str, str]], float], dict[str, Any]]


POSTURE_RISK_VALUES = {"bad_posture", "leaning_too_close", "low_head", "slouching"}
MEAL_RE = re.compile(r"(吃饭|用餐|餐桌|饭菜|餐具|碗|筷子|勺子|餐盘)")
TOY_CLEANUP_RE = re.compile(r"(收玩具|整理玩具|收拾玩具|玩具盒|放回|归位)")
TOY_CLEANUP_DONE_RE = re.compile(r"(玩具已收好|已经收好|收纳完成|玩具归位|整理好了|整齐)")
TOY_LEFT_RE = re.compile(r"(离开[^，。,.]{0,12}(玩具|玩具区)|玩具[^，。,.]{0,18}(还在|散落|没收|未收))")
PLAYING_TOYS_RE = re.compile(r"(玩玩具|玩积木|搭积木|摆弄玩具|操作玩具|playing with toys)")
TOY_NEGATION_RE = re.compile(r"(没有|没|未|未见|看不到|没有看到)[^，。,.]{0,18}(玩具|积木|toy|toys)")
POSTURE_RE = re.compile(r"(低头|头低|趴桌|身体前倾|弯腰|离[^，。,.]{0,8}(桌|书|纸)[^，。,.]{0,8}(近|太近|过近))")


class ObservationAdapterConfigError(RuntimeError):
    pass


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
    def analyze_url(self) -> str:
        return f"{self.base_url.rstrip('/')}/api/analyze_frame"

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
    ):
        config.validate()
        self.config = config
        self._json_request = json_request or _json_request
        self.vision_service = vision_service

    def _database_url(self) -> str:
        return str(os.environ.get("DATABASE_URL") or os.environ.get("APP_DATABASE_URL") or "").strip()

    def fetch_analysis(self) -> dict:
        snapshot = self._json_request(
            self.config.snapshot_url,
            None,
            None,
            self.config.timeout_seconds,
        )
        image = str(snapshot.get("image") or "")
        if not image:
            raise RuntimeError("旧摄像头运行时没有返回可用画面。")
        body, content_type = _decode_data_url(image)
        if self.vision_service is None:
            raise RuntimeError("Vision 服务未配置，无法分析画面。")
        vision_context = load_child_vision_context(
            self._database_url(),
            family_id=self.config.family_id,
            child_id=self.config.child_id,
        )
        return with_observation_reliability(
            self.vision_service.analyze_snapshot(
                image_bytes=body,
                content_type=content_type,
                device_key=self.config.device_id or self.config.base_url,
                context=vision_context,
                force_analyze=True,
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
        duration_seconds = max(1, int((window_end_ms - window_start_ms) / 1000))
        observed_at = observed_at if observed_at is not None else window_end_ms
        confidence = _score(analysis.get("confidence"))
        payloads = []
        for scenario, signal_type, signal_value, summary in _scenario_signals(analysis):
            source_event_id = build_source_event_id(
                device_id=self.config.device_id,
                scenario=scenario,
                window_start_ms=window_start_ms,
                window_end_ms=window_end_ms,
                signal_type=signal_type,
            )
            payloads.append(
                {
                    "familyId": self.config.family_id,
                    "childId": self.config.child_id,
                    "deviceId": self.config.device_id,
                    "scenario": scenario,
                    "observedAt": observed_at,
                    "confidence": confidence,
                    "evidenceType": "snapshot",
                    "parentSummary": summary,
                    "source": self.source,
                    "sourceEventId": source_event_id,
                    "signals": [
                        {
                            "signalType": signal_type,
                            "signalValue": signal_value,
                            "confidence": confidence,
                            "durationSeconds": duration_seconds,
                            "metadata": _signal_metadata(analysis),
                        }
                    ],
                    "rawDetail": _raw_detail(analysis),
                }
            )
        return payloads

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


def build_source_event_id(
    *,
    device_id: str,
    scenario: str,
    window_start_ms: int,
    window_end_ms: int,
    signal_type: str,
) -> str:
    return f"ai_camera_test:{device_id}:{scenario}:{window_start_ms}:{window_end_ms}:{signal_type}"


def _scenario_signals(analysis: Mapping[str, object]) -> list[tuple[str, str, str, str]]:
    result: list[tuple[str, str, str, str]] = []
    text = _analysis_text(analysis)
    activity = str(analysis.get("activity") or analysis.get("raw_activity") or "")
    posture_status = str(analysis.get("posture_status") or "").strip()
    has_person = analysis.get("has_person")
    toys_scattered = bool(analysis.get("toys_scattered"))
    toys_visible = bool(analysis.get("toys_visible"))
    playing_toys = (
        activity == "玩玩具" or PLAYING_TOYS_RE.search(text)
    ) and not TOY_NEGATION_RE.search(text)

    posture_signal = ""
    if posture_status in POSTURE_RISK_VALUES:
        posture_signal = posture_status
    elif bool(analysis.get("bad_posture")):
        posture_signal = "bad_posture"
    elif has_person is True and POSTURE_RE.search(text):
        posture_signal = "posture_risk"
    if has_person is True and posture_signal:
        result.append(("posture", posture_signal, "active", "观察到坐姿需要留意。"))

    if TOY_CLEANUP_DONE_RE.search(text):
        result.append(("toy_cleanup", "cleanup_done", "recovered", "观察到玩具已经收好。"))
    elif TOY_CLEANUP_RE.search(text):
        result.append(("toy_cleanup", "cleanup_started", "active", "观察到孩子正在收纳玩具。"))
    elif TOY_LEFT_RE.search(text) or (has_person is False and toys_scattered):
        result.append(("toy_cleanup", "child_left_toys_uncollected", "active", "孩子离开后，玩具还没有收好。"))
    elif has_person is True and playing_toys:
        result.append(("toy_cleanup", "toy_playing_observed", "active", "观察到孩子正在玩玩具。"))
    elif toys_scattered and not playing_toys:
        result.append(("toy_cleanup", "child_left_toys_uncollected", "active", "观察到玩具还没有收好。"))

    if activity == "吃饭" or MEAL_RE.search(text):
        result.append(("meal_start", "meal_started", "active", "观察到孩子进入用餐状态。"))
        if any(word in text for word in ("走动", "离开餐桌", "玩", "分心")):
            result.append(("meal_habit", "meal_attention_shifted", "active", "观察到用餐时注意力离开餐桌。"))

    return result


def _analysis_text(analysis: Mapping[str, object]) -> str:
    return "".join(
        str(analysis.get(key) or "")
        for key in (
            "activity",
            "raw_activity",
            "posture_status",
            "description",
            "decision_reason",
        )
    )


def _signal_metadata(analysis: Mapping[str, object]) -> dict:
    return {
        "activity": str(analysis.get("activity") or analysis.get("raw_activity") or "")[:80],
        "method": str(analysis.get("method") or "")[:80],
        "activityStability": _score(analysis.get("activity_stability")),
    }


def _raw_detail(analysis: Mapping[str, object]) -> dict:
    allowed_keys = {
        "has_person",
        "activity",
        "raw_activity",
        "bad_posture",
        "posture_status",
        "toys_visible",
        "toys_scattered",
        "confidence",
        "description",
        "child_message",
        "decision_reason",
        "activity_history",
        "events",
        "summary",
        "method",
        "activity_stability",
        "vision_cadence",
        "vision_backoff",
    }
    return {
        key: analysis.get(key)
        for key in allowed_keys
        if key in analysis
    }


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
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "ignore") or "{}")


def _score(value: object) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, min(1.0, parsed))


def _float_env(value: object, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default
