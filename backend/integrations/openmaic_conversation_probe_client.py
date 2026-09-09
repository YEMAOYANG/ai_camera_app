from __future__ import annotations

import json
import uuid
from http.cookiejar import CookieJar
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlparse
from urllib.request import HTTPCookieProcessor, Request, build_opener


class OpenMaicConversationProbeClientError(RuntimeError):
    def __init__(self, code: str, safe_message: str):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


class OpenMaicConversationProbeClient:
    """Real HTTP verifier for the gateway's short-lived probe policy.

    It never calls a model provider.  The gateway is expected to return a
    deterministic challenge proof for its own probe-mode chat and ASR routes.
    The opaque session binding is obtained from the versioned proof emitted by
    the protected endpoints, never from the successful exchange response.
    """

    def __init__(self, public_url: str, *, timeout_seconds: float = 15):
        normalized = str(public_url or "").strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OpenMAIC conversation probe public URL must be HTTP(S).")
        if timeout_seconds <= 0 or timeout_seconds > 60:
            raise ValueError("Conversation probe timeout must be between 0 and 60 seconds.")
        self.public_url = normalized
        self.timeout_seconds = float(timeout_seconds)

    def verify(self, probe: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
        ticket = _required_string(probe, "ticket")
        challenge = _required_string(probe, "challenge")
        classroom_id = _required_string(probe, "classroomId")

        # A new jar proves that the first chat is unauthenticated.
        anonymous = build_opener(HTTPCookieProcessor(CookieJar()))
        no_cookie = self._request(
            anonymous, "POST", "/api/chat", json_body={"stageId": classroom_id, "message": "probe"}
        )
        self._expect_status(no_cookie, 401, "openmaic_probe_no_cookie_not_rejected")

        jar = CookieJar()
        authenticated = build_opener(HTTPCookieProcessor(jar))
        exchange = self._request(
            authenticated,
            "GET",
            "/mira/probe?" + urlencode({"ticket": ticket}),
        )
        self._expect_status(exchange, 204, "openmaic_probe_exchange_failed")
        set_cookies = exchange["headers"].get_all("Set-Cookie") or []
        if not any("HttpOnly" in value and "ompr_" in value for value in set_cookies):
            raise OpenMaicConversationProbeClientError(
                "openmaic_probe_cookie_not_httponly",
                "网关未设置 HttpOnly 探针会话 Cookie",
            )
        wrong_stage = self._request(
            authenticated,
            "POST",
            "/api/chat",
            json_body={
                "stageId": f"wrong-{uuid.uuid4().hex}",
                "message": "probe",
                "probeChallenge": challenge,
            },
        )
        self._expect_status(wrong_stage, 403, "openmaic_probe_wrong_stage_not_rejected")

        chat = self._request(
            authenticated,
            "POST",
            "/api/chat",
            json_body={
                "stageId": classroom_id,
                "message": "Mira gateway probe only; do not invoke a model.",
                "probeChallenge": challenge,
            },
        )
        self._expect_status(chat, 200, "openmaic_probe_chat_failed")
        chat_proof = _sse_proof(chat["body"], "openmaic_probe_sse_proof_invalid")
        _validate_proof_binding(chat_proof, challenge=challenge, classroom_id=classroom_id)

        override = self._request(
            authenticated,
            "POST",
            "/api/transcription",
            multipart_fields={
                "probeChallenge": challenge,
                "providerId": "browser-native",
                "modelId": "browser-native",
            },
        )
        self._expect_status(override, 400, "openmaic_probe_asr_override_not_rejected")
        override_json = _json_body(override, "openmaic_probe_asr_override_invalid")
        if _api_error_code(override_json) != "INVALID_REQUEST":
            raise OpenMaicConversationProbeClientError(
                "openmaic_probe_asr_override_invalid",
                "网关未返回稳定的客户端 ASR 覆盖拒绝",
            )

        clean = self._request(
            authenticated,
            "POST",
            "/api/transcription",
            multipart_fields={"probeChallenge": challenge},
        )
        self._expect_status(clean, 200, "openmaic_probe_clean_asr_failed")
        clean_proof = _proof_from_response(clean, "openmaic_probe_asr_policy_invalid")
        _validate_proof_binding(clean_proof, challenge=challenge, classroom_id=classroom_id)
        policy = clean_proof.get("asrPolicy")
        if (
            not isinstance(policy, Mapping)
            or policy.get("providerId") != "qwen-asr"
            or policy.get("modelId") != "qwen3-asr-flash"
            or policy.get("fallbackAllowed") is not False
        ):
            raise OpenMaicConversationProbeClientError(
                "openmaic_probe_asr_policy_invalid",
                "网关未返回固定 Qwen ASR 策略证明",
            )

        return {
            "chat": {
                "verified": True,
                "noCookieStatus": no_cookie["status"],
                "exchangeStatus": exchange["status"],
                "cookieHttpOnly": True,
                "wrongStageStatus": wrong_stage["status"],
                "chatStatus": chat["status"],
                "proof": chat_proof,
            },
            "transcription": {
                "verified": True,
                "overrideStatus": override["status"],
                "cleanStatus": clean["status"],
                "proof": clean_proof,
            },
        }

    def _request(
        self,
        opener: Any,
        method: str,
        path: str,
        *,
        json_body: Mapping[str, Any] | None = None,
        multipart_fields: Mapping[str, str] | None = None,
    ) -> dict[str, Any]:
        headers = {"Accept": "application/json"}
        data: bytes | None = None
        if json_body is not None:
            data = json.dumps(json_body, separators=(",", ":")).encode("utf-8")
            headers["Content-Type"] = "application/json"
            headers["Accept"] = "text/event-stream, application/json"
        elif multipart_fields is not None:
            boundary = f"----mira-probe-{uuid.uuid4().hex}"
            data = _multipart_body(boundary, multipart_fields)
            headers["Content-Type"] = f"multipart/form-data; boundary={boundary}"
        request = Request(
            self.public_url + path, data=data, headers=headers, method=method
        )
        try:
            response = opener.open(request, timeout=self.timeout_seconds)
            status = response.getcode()
            response_headers = response.headers
            body = response.read().decode("utf-8", errors="replace")
        except HTTPError as exc:
            status = exc.code
            response_headers = exc.headers
            body = exc.read().decode("utf-8", errors="replace")
        except URLError as exc:
            raise OpenMaicConversationProbeClientError(
                "openmaic_probe_gateway_unavailable", "对话网关不可访问"
            ) from exc
        return {"status": status, "headers": response_headers, "body": body}

    @staticmethod
    def _expect_status(response: Mapping[str, Any], expected: int, code: str) -> None:
        if response["status"] != expected:
            raise OpenMaicConversationProbeClientError(code, "网关返回了非预期状态")


def _multipart_body(boundary: str, fields: Mapping[str, str]) -> bytes:
    parts: list[bytes] = []
    for name, value in fields.items():
        parts.extend(
            [
                f"--{boundary}\r\n".encode(),
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(),
                str(value).encode("utf-8"),
                b"\r\n",
            ]
        )
    # This tiny EBML header represents a deterministic silent-webm probe input;
    # gateway probe mode must return policy evidence without calling Qwen.
    parts.extend(
        [
            f"--{boundary}\r\n".encode(),
            b'Content-Disposition: form-data; name="audio"; filename="silent.webm"\r\n',
            b"Content-Type: audio/webm\r\n\r\n",
            b"\x1a\x45\xdf\xa3\x9f\x42\x86\x81\x01",
            b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ]
    )
    return b"".join(parts)


def _required_string(value: Mapping[str, Any], key: str) -> str:
    normalized = str(value.get(key) or "").strip()
    if not normalized:
        raise OpenMaicConversationProbeClientError(
            "invalid_openmaic_probe_context", "探针上下文不完整"
        )
    return normalized


def _json_body(response: Mapping[str, Any], code: str) -> Mapping[str, Any]:
    try:
        parsed = json.loads(str(response["body"]))
    except (TypeError, ValueError) as exc:
        raise OpenMaicConversationProbeClientError(code, "网关返回了无效 JSON") from exc
    if not isinstance(parsed, Mapping):
        raise OpenMaicConversationProbeClientError(code, "网关返回了无效 JSON")
    return parsed


def _proof_from_response(response: Mapping[str, Any], code: str) -> Mapping[str, Any]:
    parsed = _json_body(response, code)
    proof = parsed.get("proof")
    if not isinstance(proof, Mapping):
        raise OpenMaicConversationProbeClientError(code, "网关未返回版本化证明")
    return proof


def _sse_proof(body: str, code: str) -> Mapping[str, Any]:
    for line in body.splitlines():
        if not line.startswith("data:"):
            continue
        try:
            parsed = json.loads(line[5:].strip())
        except ValueError:
            continue
        if isinstance(parsed, Mapping) and parsed.get("schemaVersion") == "mira.openmaic.conversation-proof.v1":
            return parsed
    raise OpenMaicConversationProbeClientError(code, "对话 SSE 未返回版本化证明")


def _validate_proof_binding(
    proof: Mapping[str, Any], *, challenge: str, classroom_id: str
) -> None:
    if (
        proof.get("schemaVersion") != "mira.openmaic.conversation-proof.v1"
        or proof.get("challenge") != challenge
        or proof.get("classroomId") != classroom_id
        or not str(proof.get("runtimeSessionId") or "").strip()
        or proof.get("providerCall") is not False
    ):
        raise OpenMaicConversationProbeClientError(
            "openmaic_probe_proof_binding_invalid", "网关证明未绑定到探针会话"
        )


def _api_error_code(payload: Mapping[str, Any]) -> str:
    top_level = str(payload.get("errorCode") or "").strip()
    if top_level:
        return top_level
    error = payload.get("error")
    if isinstance(error, Mapping):
        return str(error.get("code") or "").strip()
    return str(payload.get("code") or "").strip()
