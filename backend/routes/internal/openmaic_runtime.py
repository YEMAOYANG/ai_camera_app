from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request, send_file

from core.database import Database
from core.errors import ApiError, error_response
from repositories.openmaic_runtime_event_repository import (
    OpenMaicRuntimeEventRepository,
)
from schemas.auth import json_body
from services.openmaic_full_runtime_service import OpenMaicRuntimeServiceError
from services.openmaic_conversation_probe_service import (
    OpenMaicConversationProbeError,
)
from integrations.openmaic_conversation_probe_client import (
    OpenMaicConversationProbeClientError,
)
from services.openmaic_runtime_generation_runner import (
    openmaic_runtime_generation_status,
)
from services.openmaic_runtime_event_service import OpenMaicRuntimeEventService
from services.service_factory import (
    internal_request_guard,
    learning_service,
    openmaic_conversation_probe_client,
    openmaic_conversation_probe_service,
    openmaic_full_runtime_service,
    openmaic_runtime_audio_service,
    task_runtime_service,
)


internal_openmaic_runtime_bp = Blueprint("internal_openmaic_runtime", __name__)


@internal_openmaic_runtime_bp.get("/status")
def runtime_status():
    try:
        context = _authorize("/internal/learning/openmaic/status")
        return jsonify(
            {
                **openmaic_full_runtime_service().status(),
                "runner": openmaic_runtime_generation_status(),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.get("/provider-circuit")
def formal_provider_circuit_status():
    try:
        context = _authorize(
            "/internal/learning/openmaic/provider-circuit"
        )
        return jsonify(
            {
                "ok": True,
                "circuit": openmaic_full_runtime_service()
                .formal_provider_circuit_status(),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/provider-circuit/probe")
def probe_formal_provider_circuit():
    try:
        context = _authorize(
            "/internal/learning/openmaic/provider-circuit/probe",
            payload_ref="deepseek-v4-pro",
        )
        return jsonify(
            {
                **openmaic_full_runtime_service()
                .probe_formal_generation_provider(),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/classrooms/generate")
@internal_openmaic_runtime_bp.post("/classrooms/sample")
def generate_classroom():
    try:
        data = json_body(request)
        context = _authorize(
            request.path,
            payload_ref=str(data.get("requestId") or "")[:255],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().generate_classroom(data),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/classrooms/<runtime_id>/retry")
def retry_classroom(runtime_id: str):
    try:
        data = json_body(request)
        context = _authorize(
            "/internal/learning/openmaic/classrooms/retry",
            payload_ref=runtime_id[:128],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().retry_classroom(
                    runtime_id, data
                ),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/classrooms/<runtime_id>/recover")
def recover_classroom(runtime_id: str):
    try:
        data = json_body(request)
        context = _authorize(
            "/internal/learning/openmaic/classrooms/recover",
            payload_ref=runtime_id[:128],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().recover_classroom(
                    runtime_id, data
                ),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post(
    "/classrooms/<runtime_id>/recovery/redispatch"
)
def redispatch_deterministic_recovery(runtime_id: str):
    try:
        data = json_body(request)
        context = _authorize(
            "/internal/learning/openmaic/classrooms/recovery/redispatch",
            payload_ref=runtime_id[:128],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().redispatch_deterministic_recovery(
                    runtime_id, data
                ),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.get("/classrooms/<runtime_id>/recovery")
def deterministic_recovery_status(runtime_id: str):
    try:
        context = _authorize(
            "/internal/learning/openmaic/classrooms/recovery",
            payload_ref=runtime_id[:128],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().deterministic_recovery_status(
                    runtime_id
                ),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post(
    "/classrooms/<runtime_id>/recovery/tts-credential-recovery"
)
def recover_tts_credentials(runtime_id: str):
    try:
        data = json_body(request)
        context = _authorize(
            (
                "/internal/learning/openmaic/classrooms/recovery/"
                "tts-credential-recovery"
            ),
            payload_ref=runtime_id[:128],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().recover_tts_credentials(
                    runtime_id, data
                ),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.get(
    "/classrooms/<runtime_id>/recovery/tts-credential-recovery"
)
def tts_credential_recovery_status(runtime_id: str):
    try:
        context = _authorize(
            (
                "/internal/learning/openmaic/classrooms/recovery/"
                "tts-credential-recovery"
            ),
            payload_ref=runtime_id[:128],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().tts_credential_recovery_status(
                    runtime_id
                ),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.get("/classrooms/jobs/<job_id>")
def generation_job(job_id: str):
    try:
        context = _authorize(
            "/internal/learning/openmaic/classrooms/jobs",
            payload_ref=job_id[:255],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().generation_status(job_id),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/classrooms/<runtime_id>/review")
def review_classroom(runtime_id: str):
    try:
        data = json_body(request)
        context = _authorize(
            "/internal/learning/openmaic/classrooms/review",
            payload_ref=runtime_id[:128],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().review_classroom(
                    runtime_id, data
                ),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/runtime/exchange")
def exchange_launch_ticket():
    try:
        data = json_body(request)
        ticket = str(data.get("ticket") or "").strip()
        context = _authorize(
            "/internal/learning/openmaic/runtime/exchange",
            payload_ref=ticket[:16],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().exchange_launch_ticket(ticket),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/runtime/validate")
def validate_runtime_session():
    try:
        data = json_body(request)
        runtime_token = str(data.get("runtimeToken") or "").strip()
        context = _authorize(
            "/internal/learning/openmaic/runtime/validate",
            payload_ref=runtime_token[:16],
        )
        return jsonify(
            {
                **openmaic_full_runtime_service().validate_runtime_session(
                    runtime_token
                ),
                "internal": context,
            }
        )
    except OpenMaicRuntimeServiceError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.get("/runtime/audio-manifest")
def runtime_audio_manifest():
    try:
        context = _authorize(
            "/internal/learning/openmaic/runtime/audio-manifest",
            payload_ref=str(
                request.headers.get("X-Mira-Runtime-Session") or ""
            )[:64],
        )
        _require_runtime_gateway(context)
        return jsonify(
            {
                **openmaic_runtime_audio_service().manifest(
                    runtime_session_id=_required_gateway_header(
                        "X-Mira-Runtime-Session"
                    ),
                    learning_session_id=_required_gateway_header(
                        "X-Mira-Learning-Session", maximum=255
                    ),
                    upstream_classroom_id=_required_gateway_header(
                        "X-Mira-Runtime-Classroom-Id", maximum=255
                    ),
                ),
                "internal": context,
            }
        )
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.get("/runtime/audio/<asset_id>")
def runtime_audio_asset(asset_id: str):
    try:
        context = _authorize(
            "/internal/learning/openmaic/runtime/audio",
            payload_ref=asset_id[:128],
        )
        _require_runtime_gateway(context)
        asset = openmaic_runtime_audio_service().authorize_asset(
            runtime_session_id=_required_gateway_header(
                "X-Mira-Runtime-Session"
            ),
            learning_session_id=_required_gateway_header(
                "X-Mira-Learning-Session", maximum=255
            ),
            upstream_classroom_id=_required_gateway_header(
                "X-Mira-Runtime-Classroom-Id", maximum=255
            ),
            asset_id=asset_id,
        )
        response = send_file(
            asset.path,
            mimetype=asset.mime_type,
            as_attachment=False,
            download_name=f"{asset_id}.wav",
            conditional=False,
            etag=False,
            max_age=0,
        )
        response.headers["Cache-Control"] = "private, no-store"
        response.headers["Content-Length"] = str(asset.byte_size)
        response.headers["X-Mira-Audio-Sha256"] = asset.content_hash
        response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Content-Security-Policy"] = "default-src 'none'"
        return response
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/runtime/events")
def record_runtime_event():
    try:
        data = json_body(request)
        context = _authorize(
            "/internal/learning/openmaic/runtime/events",
            payload_ref=str(data.get("idempotencyKey") or "")[:64],
        )
        if context.get("sourceName") != "openmaic-runtime-gateway":
            raise ApiError(
                "runtime_event_gateway_required",
                "课堂事件只能由受信任网关提交",
                403,
            )
        runtime_session_id = _required_gateway_header(
            "X-Mira-Runtime-Session"
        )
        learning_session_id = _required_gateway_header(
            "X-Mira-Learning-Session", maximum=255
        )
        classroom_id = _required_gateway_header(
            "X-Mira-Runtime-Classroom-Id", maximum=255
        )
        return jsonify(
            {
                **_runtime_event_service().record(
                    runtime_session_id=runtime_session_id,
                    learning_session_id=learning_session_id,
                    upstream_classroom_id=classroom_id,
                    data=data,
                ),
                "internal": context,
            }
        )
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.get("/runtime/events")
def runtime_event_status():
    try:
        context = _authorize(
            "/internal/learning/openmaic/runtime/events",
            payload_ref=str(
                request.headers.get("X-Mira-Runtime-Session") or ""
            )[:64],
        )
        if context.get("sourceName") != "openmaic-runtime-gateway":
            raise ApiError(
                "runtime_event_gateway_required",
                "课堂事件只能由受信任网关提交",
                403,
            )
        return jsonify(
            {
                **_runtime_event_service().status(
                    runtime_session_id=_required_gateway_header(
                        "X-Mira-Runtime-Session"
                    ),
                    learning_session_id=_required_gateway_header(
                        "X-Mira-Learning-Session", maximum=255
                    ),
                    upstream_classroom_id=_required_gateway_header(
                        "X-Mira-Runtime-Classroom-Id", maximum=255
                    ),
                ),
                "internal": context,
            }
        )
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/runtime/probe/issue")
def issue_conversation_probe():
    try:
        data = json_body(request)
        runtime_id = str(data.get("runtimeId") or "").strip()
        context = _authorize(
            "/internal/learning/openmaic/runtime/probe/issue",
            payload_ref=runtime_id[:128],
        )
        return jsonify(
            {
                **openmaic_conversation_probe_service().issue_probe(runtime_id),
                "internal": context,
            }
        )
    except OpenMaicConversationProbeError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/runtime/probe/exchange")
def exchange_conversation_probe_ticket():
    try:
        data = json_body(request)
        ticket = str(data.get("ticket") or "").strip()
        context = _authorize(
            "/internal/learning/openmaic/runtime/probe/exchange",
            payload_ref=ticket[:16],
        )
        return jsonify(
            {
                **openmaic_conversation_probe_service().exchange_ticket(ticket),
                "internal": context,
            }
        )
    except OpenMaicConversationProbeError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/runtime/probe/validate")
def validate_conversation_probe_runtime_token():
    try:
        data = json_body(request)
        runtime_token = str(data.get("runtimeToken") or "").strip()
        context = _authorize(
            "/internal/learning/openmaic/runtime/probe/validate",
            payload_ref=runtime_token[:16],
        )
        return jsonify(
            {
                **openmaic_conversation_probe_service().validate_runtime_token(
                    runtime_token
                ),
                "internal": context,
            }
        )
    except OpenMaicConversationProbeError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/runtime/probe/finalize")
def finalize_conversation_probe():
    try:
        data = json_body(request)
        probe_id = str(data.get("probeId") or "").strip()
        context = _authorize(
            "/internal/learning/openmaic/runtime/probe/finalize",
            payload_ref=probe_id[:16],
        )
        return jsonify(
            {
                **openmaic_conversation_probe_service().finalize_probe(
                    probe_id,
                    chat_receipt=data.get("chatReceipt") or {},
                    transcription_receipt=data.get("transcriptionReceipt") or {},
                ),
                "internal": context,
            }
        )
    except OpenMaicConversationProbeError as exc:
        return error_response(_api_error(exc))
    except ApiError as exc:
        return error_response(exc)


@internal_openmaic_runtime_bp.post("/runtime/probe/verify")
def verify_and_finalize_conversation_probe():
    """Run the no-model gateway verifier and atomically revoke its ticket."""
    try:
        data = json_body(request)
        runtime_id = str(data.get("runtimeId") or "").strip()
        context = _authorize(
            "/internal/learning/openmaic/runtime/probe/verify",
            payload_ref=runtime_id[:128],
        )
        probe = openmaic_conversation_probe_service().issue_probe(runtime_id)
        client = openmaic_conversation_probe_client()
        if client is None:
            raise OpenMaicConversationProbeError(
                "openmaic_probe_gateway_not_configured",
                "对话网关未配置",
                status_code=503,
            )
        receipts = client.verify(probe)
        finalized = openmaic_conversation_probe_service().finalize_probe(
            str(probe["probeId"]),
            chat_receipt=receipts["chat"],
            transcription_receipt=receipts["transcription"],
        )
        return jsonify(
            {
                **finalized,
                "runtimeId": runtime_id,
                "gatewayVerified": True,
                "internal": context,
            }
        )
    except OpenMaicConversationProbeError as exc:
        return error_response(_api_error(exc))
    except OpenMaicConversationProbeClientError as exc:
        return error_response(ApiError(exc.code, exc.safe_message, 502))
    except ApiError as exc:
        return error_response(exc)


def _authorize(route: str, *, payload_ref: str = "") -> dict:
    return internal_request_guard().authorize(
        route=route,
        headers=request.headers,
        source_ip=request.remote_addr,
        payload_ref=payload_ref,
    )


def _runtime_event_service() -> OpenMaicRuntimeEventService:
    database = Database(current_app.config["DATABASE_URL"])
    return OpenMaicRuntimeEventService(
        repository=OpenMaicRuntimeEventRepository(database),
        learning_service=learning_service(),
        task_runtime_service=task_runtime_service(),
    )


def _require_runtime_gateway(context: dict) -> None:
    if context.get("sourceName") != "openmaic-runtime-gateway":
        raise ApiError(
            "openmaic_runtime_gateway_required",
            "课堂资源只能由受信任网关读取",
            403,
        )


def _required_gateway_header(name: str, *, maximum: int = 128) -> str:
    value = str(request.headers.get(name) or "").strip()
    if not value or len(value) > maximum:
        raise ApiError(
            "runtime_event_binding_required",
            "课堂事件缺少受信任会话绑定",
        )
    return value


def _api_error(
    exc: OpenMaicRuntimeServiceError | OpenMaicConversationProbeError,
) -> ApiError:
    return ApiError(exc.code, exc.safe_message, exc.status_code)
