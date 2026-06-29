from __future__ import annotations

from flask import Blueprint, jsonify, request

from core.errors import ApiError, error_response
from schemas.auth import json_body
from services.service_factory import conversation_service, conversation_sync_service, internal_request_guard, voice_runtime_service


internal_voice_bp = Blueprint("internal_voice", __name__)


@internal_voice_bp.post("/profile-sync")
def sync_voice_profile():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/voice/profile-sync",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("familyId") or "")[:255],
        )
        family_id = str(data.get("familyId") or "").strip()
        if not family_id:
            raise ApiError("missing_familyId", "缺少 familyId。", 400)
        payload = conversation_sync_service().sync_family_conversation(family_id=family_id) or {}
        return jsonify({"ok": True, "sync": payload, "internal": context})
    except ApiError as exc:
        return error_response(exc)


@internal_voice_bp.post("/heartbeat")
def voice_heartbeat():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/voice/heartbeat",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("deviceId") or "")[:255],
        )
        family_id = str(data.get("familyId") or "").strip()
        device_id = str(data.get("deviceId") or "").strip()
        snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), dict) else {}
        profile = data.get("interactionProfile") if isinstance(data.get("interactionProfile"), dict) else {}
        if not family_id or not device_id:
            raise ApiError("missing_voice_context", "缺少 familyId 或 deviceId。", 400)
        voice_runtime_service().record_heartbeat(
            family_id=family_id,
            device_id=device_id,
            snapshot=snapshot,
            profile=profile,
            running=bool(data.get("running", True)),
        )
        return jsonify({"ok": True, "internal": context})
    except ApiError as exc:
        return error_response(exc)

@internal_voice_bp.get("/profile")
def voice_profile():
    try:
        context = internal_request_guard().authorize(
            route="/internal/voice/profile",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(request.args.get("deviceId") or "")[:255],
        )
        family_id = str(request.args.get("familyId") or "").strip()
        device_id = str(request.args.get("deviceId") or "").strip() or None
        if not family_id:
            raise ApiError("missing_familyId", "缺少 familyId。", 400)
        payload = conversation_service().internal_profile(
            family_id=family_id,
            device_id=device_id,
        )
        payload["internal"] = context
        return jsonify(payload)
    except ApiError as exc:
        return error_response(exc)


@internal_voice_bp.post("/wake-evaluate")
def voice_wake_evaluate():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/voice/wake-evaluate",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("deviceId") or "")[:255],
        )
        family_id = str(data.get("familyId") or "").strip()
        device_id = str(data.get("deviceId") or "").strip() or None
        text = str(data.get("text") or "").strip()
        if not family_id:
            raise ApiError("missing_familyId", "缺少 familyId。", 400)
        require_confirmation = data.get("requireConfirmation")
        if require_confirmation is None:
            require_confirmation = True
        payload = conversation_service().internal_wake_evaluate(
            family_id=family_id,
            device_id=device_id,
            text=text,
            require_confirmation=bool(require_confirmation),
        )
        payload["internal"] = context
        return jsonify(payload)
    except ApiError as exc:
        return error_response(exc)


@internal_voice_bp.post("/session/end")
def voice_session_end():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/voice/session/end",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("deviceId") or "")[:255],
        )
        family_id = str(data.get("familyId") or "").strip()
        device_id = str(data.get("deviceId") or "").strip() or None
        if not family_id:
            raise ApiError("missing_familyId", "缺少 familyId。", 400)
        payload = conversation_service().internal_end_session(
            family_id=family_id,
            device_id=device_id,
        )
        payload["internal"] = context
        return jsonify(payload)
    except ApiError as exc:
        return error_response(exc)


@internal_voice_bp.post("/chat")
def voice_chat():
    try:
        data = json_body(request)
        context = internal_request_guard().authorize(
            route="/internal/voice/chat",
            headers=request.headers,
            source_ip=request.remote_addr,
            payload_ref=str(data.get("deviceId") or "")[:255],
        )
        family_id = str(data.get("familyId") or "").strip()
        device_id = str(data.get("deviceId") or "").strip() or None
        text = str(data.get("text") or "").strip()
        if not family_id:
            raise ApiError("missing_familyId", "缺少 familyId。", 400)
        payload = conversation_service().internal_chat(
            family_id=family_id,
            device_id=device_id,
            text=text,
        )
        payload["internal"] = context
        return jsonify(payload)
    except ApiError as exc:
        return error_response(exc)

