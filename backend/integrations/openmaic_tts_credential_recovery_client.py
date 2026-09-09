from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


TTS_CREDENTIAL_RECOVERY_SCHEMA = "mira.openmaic.tts-credential-recovery.v1"
TTS_CREDENTIAL_RECOVERY_KIND = (
    "mira_sample_deterministic_tts_credential_recovery_v1"
)
TTS_CREDENTIAL_RECOVERY_MODE = "deterministic_no_llm_qwen_tts_only"
TTS_CREDENTIAL_RECOVERY_REQUEST_MODE = "tts_credential_recovery"
TTS_CREDENTIAL_RECOVERY_POLICY_VERSION = (
    "mira-sample-tts-credential-recovery.v1"
)
TTS_CREDENTIAL_RECOVERY_CLASSROOM_POLICY_VERSION = (
    "mira-sample-deterministic-classroom.v1"
)
TTS_CREDENTIAL_RECOVERY_CANONICAL_SPEC_SHA256 = (
    "879040700d374f045058b09cbf6ed6e956ebf97d8c8d9008477063458c5ef7b6"
)
TTS_CREDENTIAL_RECOVERY_PARENT_PATCH_SHA256 = (
    "92cd17617965a54d2a1f8a2dee166d62fd52b2a17855c3b5b3d9624ba163b781"
)
TTS_CREDENTIAL_RECOVERY_PATCH_SHA256 = (
    "90bc872069e5094f036150417d109403f06879fbd403952517c1000b5a97b33a"
)
TTS_CREDENTIAL_RECOVERY_PARENT_ERROR = "deterministic_recovery_failed"


class OpenMaicTtsCredentialRecoveryError(RuntimeError):
    def __init__(self, code: str, safe_message: str, *, status_code: int = 502):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.status_code = status_code


@dataclass(frozen=True)
class OpenMaicTtsCredentialRecovery:
    recovery_id: str
    status: str
    step: str
    progress: int
    message: str
    scenes_generated: int
    total_scenes: int
    done: bool
    source: Mapping[str, Any]
    parent: Mapping[str, Any]
    policy: Mapping[str, Any]
    calls: Mapping[str, Any]
    artifact: Mapping[str, Any] | None
    error: Mapping[str, str] | None
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None
    poll_url: str

    def audit_receipt(self) -> dict[str, Any]:
        receipt: dict[str, Any] = {
            "schemaVersion": TTS_CREDENTIAL_RECOVERY_SCHEMA,
            "kind": TTS_CREDENTIAL_RECOVERY_KIND,
            "mode": TTS_CREDENTIAL_RECOVERY_MODE,
            "recoveryId": self.recovery_id,
            "source": dict(self.source),
            "parent": {
                **dict(self.parent),
                "error": dict(self.parent["error"]),
                "calls": {"tts": dict(self.parent["calls"]["tts"])},
            },
            "policy": dict(self.policy),
            "calls": {
                **{
                    key: self.calls[key]
                    for key in (
                        "llm",
                        "webSearch",
                        "imageGeneration",
                        "videoGeneration",
                    )
                },
                "tts": dict(self.calls["tts"]),
            },
            "status": self.status,
            "step": self.step,
            "progress": self.progress,
            "message": self.message,
            "scenesGenerated": self.scenes_generated,
            "totalScenes": self.total_scenes,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
            "pollUrl": self.poll_url,
            "done": self.done,
        }
        if self.started_at is not None:
            receipt["startedAt"] = self.started_at
        if self.completed_at is not None:
            receipt["completedAt"] = self.completed_at
        if self.artifact is not None:
            artifact = dict(self.artifact)
            artifact.pop("url", None)
            artifact["tts"] = dict(self.artifact["tts"])
            receipt["artifact"] = artifact
        if self.error is not None:
            receipt["error"] = dict(self.error)
        return receipt


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class OpenMaicTtsCredentialRecoveryClient:
    MAX_JSON_BYTES = 2 * 1024 * 1024

    def __init__(
        self,
        base_url: str,
        *,
        internal_token: str,
        expected_patch_sha256: str,
        timeout_seconds: float = 30,
    ):
        normalized = str(base_url or "").strip().rstrip("/")
        parsed = urlparse(normalized)
        if (
            parsed.scheme not in {"http", "https"}
            or not parsed.netloc
            or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
            or parsed.username
            or parsed.password
            or parsed.path not in {"", "/"}
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError(
                "OpenMAIC TTS credential recovery URL must be a credential-free loopback origin."
            )
        token = str(internal_token or "").strip()
        if (
            len(token) < 32
            or len(token) > 512
            or any(char.isspace() for char in token)
        ):
            raise ValueError(
                "OpenMAIC TTS credential recovery token must be 32-512 non-space characters."
            )
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ValueError(
                "OpenMAIC TTS credential recovery timeout must be between 0 and 300 seconds."
            )
        self.base_url = normalized
        self._origin = (parsed.scheme, parsed.netloc)
        self._internal_token = token
        self._expected_patch_sha256 = _configured_sha256(
            expected_patch_sha256, "expected patch SHA-256"
        )
        self.timeout_seconds = float(timeout_seconds)
        self._opener = build_opener(_RejectRedirects())

    def verify_runtime_policy(
        self, *, source_job_id: str, parent_recovery_id: str
    ) -> dict[str, Any]:
        source_id = _identifier(source_job_id, "sourceJobId", 128)
        parent_id = _identifier(parent_recovery_id, "parentRecoveryId", 128)
        payload = self._request_json("GET", "/api/health")
        runtime_policy = payload.get("runtimePolicy")
        policy = (
            runtime_policy.get("ttsCredentialRecovery")
            if isinstance(runtime_policy, Mapping)
            else None
        )
        expected = {
            "enabled": True,
            "sourceJobId": source_id,
            "parentRecoveryId": parent_id,
            "policyVersion": TTS_CREDENTIAL_RECOVERY_POLICY_VERSION,
            "canonicalSpecSha256": (
                TTS_CREDENTIAL_RECOVERY_CANONICAL_SPEC_SHA256
            ),
            "patchSha256": self._expected_patch_sha256,
        }
        if (
            payload.get("success") is not True
            or not isinstance(policy, Mapping)
            or set(policy) != set(expected)
            or dict(policy) != expected
        ):
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_runtime_policy_mismatch",
                "OpenMAIC 运行时没有启用固定的 TTS 凭证恢复策略",
                status_code=409,
            )
        return expected

    def start_recovery(
        self,
        *,
        source_job_id: str,
        parent_recovery_id: str,
        recovery_request_id: str,
    ) -> OpenMaicTtsCredentialRecovery:
        source_id = _identifier(source_job_id, "sourceJobId", 128)
        parent_id = _identifier(parent_recovery_id, "parentRecoveryId", 128)
        request_id = _request_identifier(recovery_request_id)
        recovery_id, _request_hash = tts_credential_recovery_identity(
            source_id, parent_id, request_id
        )
        payload = self._request_json(
            "POST",
            self._path(source_id, parent_id),
            {"recoveryRequestId": request_id},
        )
        return self._recovery_from_payload(
            payload,
            expected_source_job_id=source_id,
            expected_parent_recovery_id=parent_id,
            expected_recovery_id=recovery_id,
        )

    def get_recovery(
        self,
        *,
        source_job_id: str,
        parent_recovery_id: str,
        expected_recovery_id: str,
        recovery_request_id: str,
    ) -> OpenMaicTtsCredentialRecovery:
        source_id = _identifier(source_job_id, "sourceJobId", 128)
        parent_id = _identifier(parent_recovery_id, "parentRecoveryId", 128)
        request_id = _request_identifier(recovery_request_id)
        expected_id = _identifier(
            expected_recovery_id, "expectedRecoveryId", 128
        )
        deterministic_id, _request_hash = tts_credential_recovery_identity(
            source_id, parent_id, request_id
        )
        if deterministic_id != expected_id:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_identity_mismatch",
                "TTS 凭证恢复编号与固定幂等合同不一致",
                status_code=409,
            )
        payload = self._request_json("GET", self._path(source_id, parent_id))
        return self._recovery_from_payload(
            payload,
            expected_source_job_id=source_id,
            expected_parent_recovery_id=parent_id,
            expected_recovery_id=expected_id,
        )

    def assert_recovery_absent(
        self,
        *,
        source_job_id: str,
        parent_recovery_id: str,
        expected_recovery_id: str,
        recovery_request_id: str,
    ) -> None:
        source_id = _identifier(source_job_id, "sourceJobId", 128)
        parent_id = _identifier(parent_recovery_id, "parentRecoveryId", 128)
        request_id = _request_identifier(recovery_request_id)
        recovery_id = _identifier(
            expected_recovery_id, "expectedRecoveryId", 128
        )
        deterministic_id, _request_hash = tts_credential_recovery_identity(
            source_id, parent_id, request_id
        )
        if recovery_id != deterministic_id:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_identity_mismatch",
                "TTS 凭证恢复编号与固定幂等合同不一致",
                status_code=409,
            )
        target = self._target(self._path(source_id, parent_id))
        request = Request(
            target,
            method="GET",
            headers={
                "Accept": "application/json",
                "X-Mira-Internal-Token": self._internal_token,
            },
        )
        try:
            with self._opener.open(
                request, timeout=self.timeout_seconds
            ) as response:
                self._require_same_origin(response.geturl())
                response.read(self.MAX_JSON_BYTES + 1)
        except HTTPError as exc:
            if int(getattr(exc, "code", 0) or 0) != 404:
                raise OpenMaicTtsCredentialRecoveryError(
                    "openmaic_tts_credential_absence_not_proven",
                    "OpenMAIC 没有明确证明 TTS 凭证恢复不存在",
                    status_code=int(getattr(exc, "code", 502) or 502),
                ) from exc
            self._require_same_origin(exc.geturl())
            raw = exc.read(self.MAX_JSON_BYTES + 1)
        except (URLError, TimeoutError, OSError) as exc:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_absence_not_proven",
                "暂时无法确认 TTS 凭证恢复不存在",
                status_code=503,
            ) from exc
        else:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_already_claimed",
                "OpenMAIC 已存在该 TTS 凭证恢复，禁止再次派发",
                status_code=409,
            )
        if len(raw) > self.MAX_JSON_BYTES:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_absence_not_proven",
                "TTS 凭证恢复缺席回执超过安全上限",
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_absence_not_proven",
                "OpenMAIC 没有返回固定的 TTS 凭证恢复缺席回执",
                status_code=409,
            ) from exc
        if payload != {
            "success": False,
            "errorCode": "INVALID_REQUEST",
            "error": "TTS credential recovery not found",
        }:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_absence_not_proven",
                "OpenMAIC 没有返回固定的 TTS 凭证恢复缺席回执",
                status_code=409,
            )

    @staticmethod
    def _path(source_job_id: str, parent_recovery_id: str) -> str:
        return (
            f"/api/generate-classroom/{quote(source_job_id, safe='')}"
            f"/deterministic-recovery/{quote(parent_recovery_id, safe='')}"
            "/tts-credential-recovery"
        )

    def _recovery_from_payload(
        self,
        payload: object,
        *,
        expected_source_job_id: str,
        expected_parent_recovery_id: str,
        expected_recovery_id: str,
    ) -> OpenMaicTtsCredentialRecovery:
        if not isinstance(payload, Mapping) or payload.get("success") is not True:
            self._invalid()
        required = {
            "success",
            "schemaVersion",
            "kind",
            "mode",
            "recoveryId",
            "source",
            "parent",
            "policy",
            "calls",
            "status",
            "step",
            "progress",
            "message",
            "scenesGenerated",
            "totalScenes",
            "createdAt",
            "updatedAt",
            "pollUrl",
            "done",
        }
        optional = {"startedAt", "completedAt", "artifact", "error"}
        if not required.issubset(payload) or not set(payload).issubset(
            required | optional
        ):
            self._invalid()
        recovery_id = _identifier(payload.get("recoveryId"), "recoveryId", 128)
        if recovery_id != expected_recovery_id:
            self._invalid()
        status = str(payload.get("status") or "").strip()
        if status not in {"queued", "running", "succeeded", "failed"}:
            self._invalid()
        source = payload.get("source")
        parent = payload.get("parent")
        policy = payload.get("policy")
        calls = payload.get("calls")
        if not all(
            isinstance(value, Mapping)
            for value in (source, parent, policy, calls)
        ):
            self._invalid()
        assert isinstance(source, Mapping)
        assert isinstance(parent, Mapping)
        assert isinstance(policy, Mapping)
        assert isinstance(calls, Mapping)
        if set(source) != {"jobId"}:
            self._invalid()
        normalized_source = {
            "jobId": _identifier(source.get("jobId"), "source.jobId", 128)
        }
        if normalized_source["jobId"] != expected_source_job_id:
            self._invalid()
        normalized_parent = _normalized_parent(
            parent, expected_parent_recovery_id=expected_parent_recovery_id
        )
        expected_parent_sha = tts_credential_parent_snapshot_sha256(
            expected_parent_recovery_id
        )
        if normalized_parent["parentSnapshotSha256"] != expected_parent_sha:
            self._invalid()
        if set(policy) != {
            "version",
            "classroomPolicyVersion",
            "canonicalSpecSha256",
            "parentPatchSha256",
            "patchSha256",
        }:
            self._invalid()
        normalized_policy = {
            "version": _bounded_text(policy.get("version"), 128),
            "classroomPolicyVersion": _bounded_text(
                policy.get("classroomPolicyVersion"), 128
            ),
            "canonicalSpecSha256": _sha256(
                policy.get("canonicalSpecSha256")
            ),
            "parentPatchSha256": _sha256(policy.get("parentPatchSha256")),
            "patchSha256": _sha256(policy.get("patchSha256")),
        }
        if normalized_policy != {
            "version": TTS_CREDENTIAL_RECOVERY_POLICY_VERSION,
            "classroomPolicyVersion": (
                TTS_CREDENTIAL_RECOVERY_CLASSROOM_POLICY_VERSION
            ),
            "canonicalSpecSha256": (
                TTS_CREDENTIAL_RECOVERY_CANONICAL_SPEC_SHA256
            ),
            "parentPatchSha256": TTS_CREDENTIAL_RECOVERY_PARENT_PATCH_SHA256,
            "patchSha256": self._expected_patch_sha256,
        }:
            self._invalid()
        normalized_calls = _normalized_calls(calls)
        artifact = self._artifact(
            payload.get("artifact"),
            expected_classroom_id=tts_credential_classroom_identity(recovery_id),
            required=status == "succeeded",
        )
        raw_error = payload.get("error")
        normalized_error = None
        if raw_error is not None:
            if not isinstance(raw_error, Mapping) or set(raw_error) != {
                "code",
                "message",
            }:
                self._invalid()
            normalized_error = {
                "code": _bounded_text(raw_error.get("code"), 128),
                "message": _bounded_text(raw_error.get("message"), 512),
            }
        progress = _strict_int(payload.get("progress"))
        scenes_generated = _strict_int(payload.get("scenesGenerated"))
        total_scenes = _strict_int(payload.get("totalScenes"))
        done = payload.get("done")
        if (
            not 0 <= progress <= 100
            or total_scenes != 10
            or not 0 <= scenes_generated <= total_scenes
            or not isinstance(done, bool)
            or done != (status in {"succeeded", "failed"})
        ):
            self._invalid()
        if status in {"queued", "running"} and (
            artifact is not None
            or normalized_error is not None
            or payload.get("completedAt") is not None
        ):
            self._invalid()
        if status == "failed" and (
            artifact is not None
            or normalized_error is None
            or normalized_error["code"] != "tts_credential_recovery_failed"
            or payload.get("completedAt") is None
            or progress != 100
        ):
            self._invalid()
        if status == "succeeded" and (
            artifact is None
            or normalized_error is not None
            or payload.get("completedAt") is None
            or progress != 100
            or scenes_generated != 10
            or normalized_calls["tts"] != {
                "expected": 10,
                "attempted": 10,
                "completed": 10,
            }
        ):
            self._invalid()
        expected_poll_url = self._path(
            expected_source_job_id, expected_parent_recovery_id
        )
        if (
            payload.get("schemaVersion") != TTS_CREDENTIAL_RECOVERY_SCHEMA
            or payload.get("kind") != TTS_CREDENTIAL_RECOVERY_KIND
            or payload.get("mode") != TTS_CREDENTIAL_RECOVERY_MODE
            or payload.get("pollUrl") != expected_poll_url
        ):
            self._invalid()
        return OpenMaicTtsCredentialRecovery(
            recovery_id=recovery_id,
            status=status,
            step=_bounded_text(payload.get("step"), 128),
            progress=progress,
            message=_bounded_text(payload.get("message"), 512),
            scenes_generated=scenes_generated,
            total_scenes=total_scenes,
            done=done,
            source=normalized_source,
            parent=normalized_parent,
            policy=normalized_policy,
            calls=normalized_calls,
            artifact=artifact,
            error=normalized_error,
            created_at=_bounded_text(payload.get("createdAt"), 64),
            updated_at=_bounded_text(payload.get("updatedAt"), 64),
            started_at=(
                _bounded_text(payload.get("startedAt"), 64)
                if payload.get("startedAt") is not None
                else None
            ),
            completed_at=(
                _bounded_text(payload.get("completedAt"), 64)
                if payload.get("completedAt") is not None
                else None
            ),
            poll_url=expected_poll_url,
        )

    @staticmethod
    def _artifact(
        value: object, *, expected_classroom_id: str, required: bool
    ) -> dict[str, Any] | None:
        if value is None and not required:
            return None
        if not isinstance(value, Mapping) or set(value) != {
            "classroomId",
            "url",
            "sceneCount",
            "audioCount",
            "contentSha256",
            "artifactSha256",
            "tts",
        }:
            OpenMaicTtsCredentialRecoveryClient._invalid()
        assert isinstance(value, Mapping)
        tts = value.get("tts")
        if not isinstance(tts, Mapping) or set(tts) != {
            "providerId",
            "modelId",
            "voiceId",
            "speechCount",
            "fallbackUsed",
        }:
            OpenMaicTtsCredentialRecoveryClient._invalid()
        artifact = {
            "classroomId": _identifier(
                value.get("classroomId"), "artifact.classroomId", 255
            ),
            "url": _bounded_text(value.get("url"), 1024),
            "sceneCount": _strict_int(value.get("sceneCount")),
            "audioCount": _strict_int(value.get("audioCount")),
            "contentSha256": _sha256(value.get("contentSha256")),
            "artifactSha256": _sha256(value.get("artifactSha256")),
            "tts": {
                "providerId": _bounded_text(tts.get("providerId"), 64),
                "modelId": _bounded_text(tts.get("modelId"), 128),
                "voiceId": _bounded_text(tts.get("voiceId"), 128),
                "speechCount": _strict_int(tts.get("speechCount")),
                "fallbackUsed": tts.get("fallbackUsed"),
            },
        }
        if (
            artifact["classroomId"] != expected_classroom_id
            or artifact["url"] != f"/classroom/{expected_classroom_id}"
            or artifact["sceneCount"] != 10
            or artifact["audioCount"] != 10
            or artifact["tts"]
            != {
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": "Serena",
                "speechCount": 10,
                "fallbackUsed": False,
            }
        ):
            OpenMaicTtsCredentialRecoveryClient._invalid()
        return artifact

    def _request_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = self._target(path)
        data = (
            json.dumps(
                body, ensure_ascii=False, separators=(",", ":")
            ).encode("utf-8")
            if body is not None
            else None
        )
        request = Request(
            target,
            data=data,
            method=method,
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json",
                "X-Mira-Internal-Token": self._internal_token,
            },
        )
        try:
            with self._opener.open(
                request, timeout=self.timeout_seconds
            ) as response:
                self._require_same_origin(response.geturl())
                raw = response.read(self.MAX_JSON_BYTES + 1)
        except HTTPError as exc:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_upstream_rejected",
                "OpenMAIC 拒绝了 TTS 凭证恢复请求",
                status_code=int(getattr(exc, "code", 502) or 502),
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_unavailable",
                "暂时无法连接 OpenMAIC TTS 凭证恢复服务",
                status_code=503,
            ) from exc
        if len(raw) > self.MAX_JSON_BYTES:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_response_too_large",
                "OpenMAIC TTS 凭证恢复回执超过安全上限",
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise OpenMaicTtsCredentialRecoveryError(
                "invalid_openmaic_tts_credential_response",
                "OpenMAIC TTS 凭证恢复回执格式无效",
            ) from exc
        if not isinstance(payload, dict):
            self._invalid()
        return payload

    def _target(self, path: str) -> str:
        target = urljoin(f"{self.base_url}/", path.lstrip("/"))
        self._require_same_origin(target)
        return target

    def _require_same_origin(self, target: str) -> None:
        parsed = urlparse(target)
        if (parsed.scheme, parsed.netloc) != self._origin:
            raise OpenMaicTtsCredentialRecoveryError(
                "openmaic_tts_credential_target_not_allowed",
                "OpenMAIC TTS 凭证恢复请求目标不安全",
            )

    @staticmethod
    def _invalid() -> None:
        raise OpenMaicTtsCredentialRecoveryError(
            "invalid_openmaic_tts_credential_response",
            "OpenMAIC TTS 凭证恢复回执与固定合同不一致",
        )


def tts_credential_parent_snapshot(
    parent_recovery_id: str,
) -> dict[str, Any]:
    parent_id = _identifier(parent_recovery_id, "parentRecoveryId", 128)
    return {
        "artifactAbsent": True,
        "calls": {"tts": {"attempted": 1, "completed": 0, "expected": 10}},
        "error": {"code": TTS_CREDENTIAL_RECOVERY_PARENT_ERROR},
        "recoveryId": parent_id,
        "status": "failed",
    }


def tts_credential_parent_snapshot_sha256(parent_recovery_id: str) -> str:
    return _canonical_sha256(tts_credential_parent_snapshot(parent_recovery_id))


def tts_credential_recovery_identity(
    source_job_id: str,
    parent_recovery_id: str,
    recovery_request_id: str,
) -> tuple[str, str]:
    source_id = _identifier(source_job_id, "sourceJobId", 128)
    parent_id = _identifier(parent_recovery_id, "parentRecoveryId", 128)
    request_id = _request_identifier(recovery_request_id)
    request_hash = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    identity_hash = hashlib.sha256(
        f"{source_id}:{parent_id}:{request_hash}".encode("utf-8")
    ).hexdigest()
    return f"omtts_{identity_hash[:24]}", request_hash


def tts_credential_classroom_identity(recovery_id: str) -> str:
    child_id = _identifier(recovery_id, "recoveryId", 128)
    digest = hashlib.sha256(
        f"mira-tts-child-classroom-v1:{child_id}".encode("utf-8")
    ).hexdigest()
    return f"omclass_{digest[:24]}"


def _normalized_parent(
    value: Mapping[str, Any], *, expected_parent_recovery_id: str
) -> dict[str, Any]:
    if set(value) != {
        "recoveryId",
        "status",
        "error",
        "calls",
        "artifactAbsent",
        "parentSnapshotSha256",
        "parentSnapshotHashBasis",
    }:
        OpenMaicTtsCredentialRecoveryClient._invalid()
    error = value.get("error")
    calls = value.get("calls")
    tts = calls.get("tts") if isinstance(calls, Mapping) else None
    if (
        not isinstance(error, Mapping)
        or set(error) != {"code"}
        or not isinstance(calls, Mapping)
        or set(calls) != {"tts"}
        or not isinstance(tts, Mapping)
        or set(tts) != {"expected", "attempted", "completed"}
    ):
        OpenMaicTtsCredentialRecoveryClient._invalid()
    normalized = {
        "recoveryId": _identifier(
            value.get("recoveryId"), "parent.recoveryId", 128
        ),
        "status": str(value.get("status") or "").strip(),
        "error": {"code": _bounded_text(error.get("code"), 128)},
        "calls": {
            "tts": {
                "expected": _strict_int(tts.get("expected")),
                "attempted": _strict_int(tts.get("attempted")),
                "completed": _strict_int(tts.get("completed")),
            }
        },
        "artifactAbsent": value.get("artifactAbsent"),
        "parentSnapshotSha256": _sha256(
            value.get("parentSnapshotSha256")
        ),
        "parentSnapshotHashBasis": _bounded_text(
            value.get("parentSnapshotHashBasis"), 32
        ),
    }
    expected = tts_credential_parent_snapshot(expected_parent_recovery_id)
    if (
        {key: normalized[key] for key in expected} != expected
        or normalized["parentSnapshotHashBasis"] != "canonical_json_v1"
    ):
        OpenMaicTtsCredentialRecoveryClient._invalid()
    return normalized


def _normalized_calls(value: Mapping[str, Any]) -> dict[str, Any]:
    if set(value) != {
        "llm",
        "webSearch",
        "imageGeneration",
        "videoGeneration",
        "tts",
    }:
        OpenMaicTtsCredentialRecoveryClient._invalid()
    tts = value.get("tts")
    if not isinstance(tts, Mapping) or set(tts) != {
        "expected",
        "attempted",
        "completed",
    }:
        OpenMaicTtsCredentialRecoveryClient._invalid()
    normalized = {
        "llm": _strict_int(value.get("llm")),
        "webSearch": _strict_int(value.get("webSearch")),
        "imageGeneration": _strict_int(value.get("imageGeneration")),
        "videoGeneration": _strict_int(value.get("videoGeneration")),
        "tts": {
            "expected": _strict_int(tts.get("expected")),
            "attempted": _strict_int(tts.get("attempted")),
            "completed": _strict_int(tts.get("completed")),
        },
    }
    if (
        any(
            normalized[key] != 0
            for key in (
                "llm",
                "webSearch",
                "imageGeneration",
                "videoGeneration",
            )
        )
        or normalized["tts"]["expected"] != 10
        or not (
            0
            <= normalized["tts"]["completed"]
            <= normalized["tts"]["attempted"]
            <= 10
        )
    ):
        OpenMaicTtsCredentialRecoveryClient._invalid()
    return normalized


def _identifier(value: object, field: str, max_length: int) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or len(normalized) > max_length
        or not all(char.isalnum() or char in {"-", "_"} for char in normalized)
    ):
        raise OpenMaicTtsCredentialRecoveryError(
            "invalid_openmaic_tts_credential_identifier",
            f"OpenMAIC TTS 凭证恢复字段 {field} 无效",
            status_code=400,
        )
    return normalized


def _request_identifier(value: object) -> str:
    request_id = _identifier(value, "recoveryRequestId", 128)
    if len(request_id) < 8:
        raise OpenMaicTtsCredentialRecoveryError(
            "invalid_openmaic_tts_credential_identifier",
            "OpenMAIC TTS 凭证恢复字段 recoveryRequestId 无效",
            status_code=400,
        )
    return request_id


def _strict_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        OpenMaicTtsCredentialRecoveryClient._invalid()
    return int(value)


def _bounded_text(value: object, max_length: int) -> str:
    if not isinstance(value, str):
        OpenMaicTtsCredentialRecoveryClient._invalid()
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        OpenMaicTtsCredentialRecoveryClient._invalid()
    return normalized


def _sha256(value: object) -> str:
    normalized = _bounded_text(value, 64).lower()
    if len(normalized) != 64 or any(
        char not in "0123456789abcdef" for char in normalized
    ):
        OpenMaicTtsCredentialRecoveryClient._invalid()
    return normalized


def _configured_sha256(value: object, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if len(normalized) != 64 or any(
        char not in "0123456789abcdef" for char in normalized
    ):
        raise ValueError(f"OpenMAIC TTS credential recovery {field} is invalid.")
    return normalized


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
