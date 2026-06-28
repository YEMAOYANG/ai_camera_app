from __future__ import annotations

import json

from flask import Blueprint, Response, current_app, jsonify, request, stream_with_context

from core.database import Database
from core.errors import ApiError, error_response
from repositories.care_repository import CareRepository
from schemas.auth import bearer_token, json_body
from schemas.vision import observation_is_reliable
from services.camera_bridge_service import CameraBridgeError
from services.parent_facing_copy import build_child_vision_context
from core.security import now_ms
from services.service_factory import (
    auth_service,
    camera_command_service,
    camera_observe_service,
    device_runtime_resolver,
    profile_service,
    task_service,
)
from services.task_event_stream import (
    CAMERA_MONITOR_REFRESHED,
    CAMERA_OBSERVATION_UPDATED,
    publish_family_event,
)


camera_bp = Blueprint("camera", __name__)


def _json_response(payload: dict):
    if payload["ok"]:
        return jsonify(payload)
    return jsonify(payload), 502


def _resolve_camera_runtime_for_request():
    access_token = bearer_token(request)
    context = auth_service().authenticate(access_token)
    device_id = str(request.args.get("deviceId") or "").strip() or None
    resolved = device_runtime_resolver().resolve(
        family_id=context["family"]["id"],
        device_id=device_id,
    )
    return access_token, context, resolved


def _observe_child_id(access_token: str, *, family_id: str) -> str:
    try:
        child = profile_service().current_child(access_token).get("child") or {}
    except Exception:
        child = {}
    child_id = str(child.get("id") or "").strip()
    if child_id:
        return child_id
    repository = CareRepository(Database(current_app.config["DATABASE_URL"]))
    with repository.transaction() as conn:
        children = repository.list_children(conn, family_id=family_id)
    if children:
        return str(children[0].get("id") or "").strip()
    return ""


@camera_bp.get("/health")
def camera_health():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        return _json_response(resolved.bridge.health())
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/status")
def camera_status():
    try:
        access_token, _, resolved = _resolve_camera_runtime_for_request()
        current_task = task_service().current_in_progress(
            access_token,
            device_id=resolved.device_id,
            include_unassigned=bool((resolved.device or {}).get("is_default")),
        )
        return jsonify(resolved.bridge.status(current_task=current_task))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/runtime")
def camera_runtime():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        return _json_response(resolved.bridge.runtime())
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/speaker/status")
def speaker_status():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        return _json_response(resolved.bridge.speaker_status())
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/snapshot")
def snapshot():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        result = resolved.bridge.fetch_snapshot()
        return Response(
            result.body,
            mimetype=result.content_type,
            headers={"Cache-Control": "no-store"},
        )
    except CameraBridgeError as exc:
        return Response(
            status=204,
            headers={
                "Cache-Control": "no-store",
                "X-Mira-Snapshot-Status": "unavailable",
                "X-Mira-Snapshot-Error": exc.code,
                "X-Mira-Snapshot-Message": "snapshot_unavailable",
            },
        )
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/stream")
def stream():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        upstream = resolved.bridge.open_stream()
        content_type = upstream.headers.get("content-type", "multipart/x-mixed-replace")

        def generate():
            with upstream:
                while True:
                    chunk = upstream.read(8192)
                    if not chunk:
                        break
                    yield chunk

        return Response(
            stream_with_context(generate()),
            content_type=content_type,
            headers={"Cache-Control": "no-store"},
        )
    except CameraBridgeError as exc:
        return jsonify({"ok": False, "error": exc.code, "message": exc.message}), exc.status_code
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/webrtc/session")
def webrtc_session():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        return jsonify(resolved.bridge.webrtc_session())
    except CameraBridgeError as exc:
        return jsonify({"ok": False, "error": exc.code, "message": "实时画面暂时无法连接，请稍后再试。"}), exc.status_code
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/webrtc/offer")
def webrtc_offer():
    try:
        _, _, resolved = _resolve_camera_runtime_for_request()
        data = json_body(request)
        offer_sdp = str(data.get("sdp") or "").strip()
        if not offer_sdp:
            return jsonify({"ok": False, "error": "invalid_webrtc_offer", "message": "实时画面连接信息不完整。"}), 400
        return jsonify(resolved.bridge.webrtc_offer(offer_sdp))
    except CameraBridgeError as exc:
        return jsonify({"ok": False, "error": exc.code, "message": "实时画面暂时无法连接，请稍后再试。"}), exc.status_code
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/commands/speak")
def speak_command():
    try:
        return jsonify(camera_command_service().speak(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/commands/snapshot")
def snapshot_command():
    try:
        return jsonify(camera_command_service().snapshot(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/commands/ptz")
def ptz_command():
    try:
        return jsonify(camera_command_service().ptz_move(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/monitor/start")
def monitor_start():
    try:
        return jsonify(camera_command_service().monitor_start(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/monitor/stop")
def monitor_stop():
    try:
        return jsonify(camera_command_service().monitor_stop(bearer_token(request), json_body(request)))
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/monitor/status")
def monitor_status():
    try:
        access_token, context, resolved = _resolve_camera_runtime_for_request()
        payload = resolved.bridge.monitor_status()
        response = _monitor_response(payload)
        child_id = _observe_child_id(access_token, family_id=context["family"]["id"])
        _merge_stored_observation_into_response(
            response,
            family_id=context["family"]["id"],
            device_id=resolved.device_id,
        )
        _merge_runtime_display_into_response(
            response,
            family_id=context["family"]["id"],
            child_id=child_id,
            device_id=resolved.device_id,
        )
        return jsonify(response)
    except ApiError as exc:
        return error_response(exc)


@camera_bp.post("/monitor/refresh")
def monitor_refresh():
    try:
        access_token, context, resolved = _resolve_camera_runtime_for_request()
        child_id = _observe_child_id(access_token, family_id=context["family"]["id"])
        device_id = resolved.device_id or ""
        snapshot = resolved.bridge.fetch_snapshot()
        observe_result = camera_observe_service().run_tick(
            family_id=context["family"]["id"],
            child_id=child_id,
            device_id=device_id,
            image_bytes=snapshot.body,
            content_type=snapshot.content_type or "image/jpeg",
            source="camera_monitor",
            force_analyze=True,
            force_post=True,
        )
        observation = observe_result.analysis if isinstance(observe_result.analysis, dict) else {}
        if isinstance(observation, dict):
            observation = dict(observation)
            observation.setdefault("observedAt", now_ms())
        payload = _monitor_refresh_payload(observation)
        response = _monitor_response(payload)
        _merge_stored_observation_into_response(
            response,
            family_id=context["family"]["id"],
            device_id=device_id,
            trust_current=True,
        )
        event_ids: list[str] = []
        response_payload = observe_result.response or {}
        care_event = response_payload.get("careEvent") if isinstance(response_payload, dict) else None
        if isinstance(care_event, dict):
            event_id = str(care_event.get("id") or care_event.get("commandId") or "").strip()
            if event_id:
                event_ids = [event_id]
        is_reliable = bool(observation.get("isReliable")) if isinstance(observation, dict) else False
        realtime_event = None
        if event_ids and isinstance(observation, dict):
            from services.camera_command_service import lightweight_camera_event_from_observation

            realtime_event = lightweight_camera_event_from_observation(
                event_id=event_ids[0],
                device_id=device_id,
                observation=observation,
            )
        publish_family_event(
            family_id=context["family"]["id"],
            event_type=CAMERA_MONITOR_REFRESHED,
            device_id=device_id,
            is_reliable=is_reliable,
            source="camera_monitor",
        )
        publish_family_event(
            family_id=context["family"]["id"],
            event_type=CAMERA_OBSERVATION_UPDATED,
            device_id=device_id,
            observation_id=_observation_id(observation),
            event_ids=event_ids,
            is_reliable=is_reliable,
            source="camera_monitor",
            event=realtime_event,
        )
        return jsonify(response)
    except CameraBridgeError as exc:
        return jsonify(
            {
                "ok": False,
                "error": exc.code,
                "message": "摄像头画面暂不可用，请稍后再试。",
            }
        ), exc.status_code
    except ApiError as exc:
        return error_response(exc)


@camera_bp.get("/events")
def camera_events():
    try:
        access_token, _, resolved = _resolve_camera_runtime_for_request()
        return jsonify(
            camera_command_service().recent_events(
                access_token,
                request.args,
                device_id=resolved.device_id,
                include_unassigned=bool((resolved.device or {}).get("is_default")),
            )
        )
    except ApiError as exc:
        return error_response(exc)


def _monitor_refresh_payload(observation: dict) -> dict:
    return {
        "ok": True,
        "monitorRuntime": {
            "data": {
                "monitor_runtime": {
                    "running": False,
                    "status": "refreshed",
                    "last_tick_at": now_ms(),
                    "last_observation": observation,
                    "last_reminder": "",
                }
            }
        },
    }


def _extract_monitor_status(payload: dict) -> dict:
    if not isinstance(payload, dict):
        return {}
    runtime = payload.get("monitorRuntime")
    if isinstance(runtime, dict):
        data = runtime.get("data")
        if isinstance(data, dict):
            nested = data.get("monitor_runtime")
            if isinstance(nested, dict):
                return nested
            if "last_observation" in data or "status" in data or "state" in data:
                return data
    direct = payload.get("monitor_runtime")
    if isinstance(direct, dict):
        return direct
    return {}


def _monitor_response(payload: dict) -> dict:
    status = _extract_monitor_status(payload)
    running = bool(status.get("running"))
    normalized = _normalize_monitor_observation(status.get("last_observation"))
    monitor_status = status.get("status") or status.get("state") or "unavailable"
    return {
        "ok": True,
        "monitor": {
            "running": running,
            "status": monitor_status,
            "lastObservation": normalized,
            "lastReminder": status.get("last_reminder") or "",
            "message": _monitor_message(
                running=running,
                status=str(monitor_status),
                has_observation=normalized is not None,
            ),
        },
    }


def _monitor_message(*, running: bool, status: str, has_observation: bool) -> str:
    if running:
        return "摄像头正在观察当前任务"
    if status == "refreshed":
        if has_observation:
            return "观察已刷新"
        return "观察已刷新，沿用最近一次记录"
    if has_observation:
        return "最近一次观察"
    return "当前没有进行中的观察"


def _merge_stored_observation_into_response(
    response: dict,
    *,
    family_id: str,
    device_id: str | None,
    trust_current: bool = False,
) -> None:
    monitor = response.get("monitor")
    if not isinstance(monitor, dict):
        return
    current = monitor.get("lastObservation")
    if trust_current and isinstance(current, dict) and str(current.get("summary") or "").strip():
        return
    stored = _latest_stored_observation(family_id=family_id, device_id=device_id)
    if stored is None:
        return
    current = monitor.get("lastObservation")
    current_summary = str((current or {}).get("summary") or "").strip() if isinstance(current, dict) else ""
    stored_summary = str(stored.get("summary") or "").strip()
    should_merge = (
        not isinstance(current, dict)
        or not current_summary
        or (stored_summary and _stored_observation_is_newer(stored, current))
    )
    if not should_merge:
        return
    monitor["lastObservation"] = stored
    if str(monitor.get("status") or "") == "refreshed":
        monitor["message"] = "观察已刷新"
    elif not monitor.get("message") or monitor.get("message") == "当前没有进行中的观察":
        monitor["message"] = "最近一次观察"


def _merge_runtime_display_into_response(
    response: dict,
    *,
    family_id: str,
    child_id: str,
    device_id: str | None,
) -> None:
    if not child_id or not device_id:
        return
    display = _latest_runtime_display_observation(
        family_id=family_id,
        child_id=child_id,
        device_id=device_id,
    )
    if display is None:
        return
    monitor = response.get("monitor")
    if not isinstance(monitor, dict):
        return
    current = monitor.get("lastObservation")
    if not isinstance(current, dict) or _stored_observation_is_newer(display, current):
        monitor["lastObservation"] = display


def _latest_runtime_display_observation(
    *,
    family_id: str,
    child_id: str,
    device_id: str,
) -> dict | None:
    from services.observation_runtime_state import ObservationRuntimeStateStore

    repository = CareRepository(Database(current_app.config["DATABASE_URL"]))
    store = ObservationRuntimeStateStore(repository)
    with repository.transaction() as conn:
        runtime = store.load(
            conn,
            family_id=family_id,
            child_id=child_id,
            device_id=device_id,
        )
    display = runtime.get("display")
    if not isinstance(display, dict) or not int(display.get("observed_at") or 0):
        return None
    normalized = _normalize_monitor_observation(
        {
            "has_person": display.get("has_person"),
            "activity": display.get("activity"),
            "raw_activity": display.get("raw_activity"),
            "confidence": display.get("confidence"),
            "observedAt": display.get("observed_at"),
            "description": display.get("description"),
            "decision_reason": display.get("decision_reason"),
            "isReliable": display.get("isReliable"),
        }
    )
    if normalized is None:
        return None
    description = str(display.get("description") or "").strip()
    if description:
        normalized["description"] = description[:180]
    return normalized


def _normalize_monitor_observation(value: object) -> dict | None:
    if not isinstance(value, dict):
        return None
    from services.vision_observation_enrich import enrich_observation

    enriched = enrich_observation(_monitor_observation_source(value))
    has_person_value = enriched.get("has_person")
    has_person = has_person_value is True
    activity = str(enriched.get("activity") or "").strip()
    if has_person_value is False:
        activity = ""
    elif _is_generic_activity(activity):
        activity = ""
    confidence = _float_or_zero(enriched.get("confidence") or value.get("confidence"))
    observed_at = _int_or_zero(
        value.get("observedAt")
        or value.get("observed_at")
        or value.get("timestamp")
        or value.get("time")
        or enriched.get("observed_at")
    )
    summary = _summary_text(
        {
            **value,
            **enriched,
            "description": enriched.get("description") or value.get("description"),
        },
        activity=activity,
        has_person_value=has_person_value,
    )
    is_reliable = observation_is_reliable(
        has_person=has_person_value,
        confidence=confidence,
    )
    if has_person_value is False:
        activity = ""
    has_activity = bool(activity)
    if not is_reliable:
        summary = ""
    return {
        "hasPerson": has_person,
        "activity": activity,
        "confidence": confidence,
        "observedAt": observed_at,
        "summary": summary,
        "isReliable": is_reliable,
        "hasMeaningfulActivity": has_activity,
        "source": "camera",
    }


def _summary_text(value: dict, *, activity: str, has_person_value: object) -> str:
    raw_summary = str(
        value.get("summary")
        or value.get("description")
        or value.get("child_message")
        or ""
    ).strip()
    if has_person_value is False:
        return "暂未看到孩子"
    if activity == "玩玩具":
        return "孩子正在玩玩具"
    if activity == "吃饭":
        return "孩子正在吃饭"
    if activity:
        return f"孩子正在{activity}"
    if raw_summary and not _is_generic_activity(raw_summary):
        if _summary_contains_screen_claim(raw_summary) and activity not in {"看电视", "玩手机"}:
            return "画面暂时无法判断" if has_person_value is True else "暂未看到孩子"
        return raw_summary[:80]
    if has_person_value is True:
        return "画面暂时无法判断"
    return ""


def _monitor_observation_source(value: dict) -> dict:
    return {
        "has_person": value.get("has_person", value.get("hasPerson")),
        "activity": value.get("activity") or value.get("raw_activity"),
        "raw_activity": value.get("raw_activity") or value.get("activity"),
        "confidence": value.get("confidence"),
        "description": value.get("description"),
        "child_message": value.get("child_message"),
        "decision_reason": value.get("decision_reason") or value.get("decisionReason"),
        "posture_status": value.get("posture_status"),
        "bad_posture": value.get("bad_posture"),
        "is_meal_scene": value.get("is_meal_scene"),
        "meal_standing": value.get("meal_standing"),
        "toys_on_table": value.get("toys_on_table"),
        "toys_scattered": value.get("toys_scattered"),
    }


def _activity_label(value: object, *, raw_text: str = "") -> str:
    activity = str(value or "").strip()
    combined = f"{activity} {raw_text}".strip().lower()
    if _mentions_toy_play(combined):
        return "玩玩具"
    if not activity or _is_generic_activity(activity):
        return ""
    return activity[:40]


def _summary_contains_screen_claim(text: str) -> bool:
    blocked = ("看屏幕", "看电视", "玩手机", "注视", "用眼距离")
    return any(token in text for token in blocked)


def _is_generic_activity(value: str) -> bool:
    normalized = value.strip().lower()
    return normalized in {"其他", "未知", "无明显活动", "other", "unknown", "normal"}


def _mentions_toy_play(value: str) -> bool:
    normalized = value.lower()
    return any(
        token in normalized
        for token in ("玩具", "积木", "toy", "toys", "play", "playing")
    )


def _analysis_text(value: dict) -> str:
    parts = [
        value.get("activity"),
        value.get("raw_activity"),
        value.get("summary"),
        value.get("description"),
        value.get("child_message"),
    ]
    return " ".join(str(part or "") for part in parts)


def _float_or_zero(value: object) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _int_or_zero(value: object) -> int:
    try:
        return int(float(value or 0))
    except (TypeError, ValueError):
        return 0


def _observation_id(value: object) -> str:
    if not isinstance(value, dict):
        return ""
    for key in ("id", "observationId", "sourceEventId", "observedAt"):
        current = str(value.get(key) or "").strip()
        if current:
            return current[:255]
    return ""


def _record_monitor_observation_event(
    *,
    access_token: str,
    context: dict,
    device_id: str | None,
    observation: object,
) -> list[str]:
    if not isinstance(observation, dict) or not device_id:
        return []
    if not observation.get("isReliable"):
        return []
    try:
        child = profile_service().current_child(access_token).get("child") or {}
    except Exception:
        child = {}
    event = camera_command_service().record_observation_event(
        family_id=context["family"]["id"],
        child_id=str(child.get("id") or "").strip(),
        device_id=device_id,
        observation=observation,
    )
    if not event:
        return []
    event_id = str(event.get("id") or "").strip()
    return [event_id] if event_id else []


def _latest_stored_observation(*, family_id: str, device_id: str | None) -> dict | None:
    if not device_id:
        return None
    repository = CareRepository(Database(current_app.config["DATABASE_URL"]))
    with repository.transaction() as conn:
        row = repository.latest_camera_observation_for_device(
            conn,
            family_id=family_id,
            device_id=device_id,
        )
    if row is None:
        return None
    raw = _json_dict(row.get("raw_detail_json"))
    normalized = _normalize_monitor_observation(
        {
            "id": row["id"],
            "has_person": raw.get("has_person"),
            "activity": raw.get("activity") or raw.get("raw_activity"),
            "raw_activity": raw.get("raw_activity"),
            "confidence": row.get("confidence"),
            "observedAt": row.get("observed_at"),
            "summary": row.get("parent_summary"),
            "description": raw.get("description"),
            "child_message": raw.get("child_message"),
            "decision_reason": raw.get("decision_reason"),
            "sourceEventId": row.get("source_event_id") or "",
        }
    )
    if normalized is None:
        return None
    normalized["id"] = row["id"]
    normalized["description"] = str(raw.get("description") or "")[:180]
    normalized["decisionReason"] = str(raw.get("decision_reason") or "")[:180]
    return normalized


def _stored_observation_is_newer(stored: dict, current: object) -> bool:
    if not isinstance(current, dict):
        return True
    return _int_or_zero(stored.get("observedAt")) >= _int_or_zero(current.get("observedAt"))


def _json_dict(value: object) -> dict:
    if not value:
        return {}
    if isinstance(value, dict):
        return value
    try:
        parsed = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return parsed if isinstance(parsed, dict) else {}
