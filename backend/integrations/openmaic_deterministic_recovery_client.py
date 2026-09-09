from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


RECOVERY_SCHEMA = "mira.openmaic.deterministic-recovery.v1"
RECOVERY_KIND = "mira_sample_deterministic_no_llm_v1"
RECOVERY_MODE = "deterministic_no_llm"
RECOVERY_POLICY_MARKER = "MIRA_OPENMAIC_SAMPLE_STRUCTURAL_POLICY_V1"
RECOVERY_POLICY_VERSION = "mira-sample-deterministic-classroom.v1"
RECOVERY_SOURCE_ERROR = "structured_output_exhausted"
RECOVERY_SOURCE_SCENES_GENERATED = 4
RECOVERY_SOURCE_TOTAL_SCENES = 10
RECOVERY_SNAPSHOT_HASH_BASIS = "canonical_json_v1"
# Build-time attestation for the single approved patch 0007 artifact.  These
# are deliberately code-pinned rather than copied from the runtime health
# response or an operator-controlled environment value.
RECOVERY_CANONICAL_SPEC_SHA256 = (
    "879040700d374f045058b09cbf6ed6e956ebf97d8c8d9008477063458c5ef7b6"
)
RECOVERY_PATCH_SHA256 = (
    "92cd17617965a54d2a1f8a2dee166d62fd52b2a17855c3b5b3d9624ba163b781"
)


class OpenMaicDeterministicRecoveryError(RuntimeError):
    def __init__(self, code: str, safe_message: str, *, status_code: int = 502):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.status_code = status_code


@dataclass(frozen=True)
class OpenMaicRecoverySourceSnapshot:
    job_id: str
    completed_at: str
    job_snapshot_sha256: str

    def to_audit_source(self) -> dict[str, Any]:
        return {
            "jobId": self.job_id,
            "status": "failed",
            "error": RECOVERY_SOURCE_ERROR,
            "scenesGenerated": RECOVERY_SOURCE_SCENES_GENERATED,
            "totalScenes": RECOVERY_SOURCE_TOTAL_SCENES,
            "completedAt": self.completed_at,
            "jobSnapshotSha256": self.job_snapshot_sha256,
            "jobSnapshotHashBasis": RECOVERY_SNAPSHOT_HASH_BASIS,
        }


@dataclass(frozen=True)
class OpenMaicDeterministicRecovery:
    recovery_id: str
    status: str
    step: str
    progress: int
    done: bool
    source: Mapping[str, Any]
    policy: Mapping[str, Any]
    calls: Mapping[str, Any]
    artifact: Mapping[str, Any] | None
    error: Mapping[str, str] | None
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None

    def audit_receipt(self) -> dict[str, Any]:
        """Return the secret-free, bounded recovery receipt persisted by Mira."""

        receipt: dict[str, Any] = {
            "schemaVersion": RECOVERY_SCHEMA,
            "kind": RECOVERY_KIND,
            "recoveryId": self.recovery_id,
            "mode": RECOVERY_MODE,
            "source": dict(self.source),
            "policy": dict(self.policy),
            "calls": {
                **{key: self.calls[key] for key in (
                    "llm", "webSearch", "imageGeneration", "videoGeneration"
                )},
                "tts": dict(self.calls["tts"]),
            },
            "status": self.status,
            "step": self.step,
            "progress": self.progress,
            "done": self.done,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.started_at:
            receipt["startedAt"] = self.started_at
        if self.completed_at:
            receipt["completedAt"] = self.completed_at
        if self.artifact is not None:
            artifact = dict(self.artifact)
            artifact.pop("url", None)
            receipt["artifact"] = artifact
        if self.error:
            receipt["error"] = dict(self.error)
        return receipt


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class OpenMaicDeterministicRecoveryClient:
    """Strict loopback-only client for OpenMAIC patch 0007.

    The internal token is used only on the two deterministic-recovery routes.
    Redirects are disabled so the credential cannot be forwarded to another
    origin.  Normal generation and classroom APIs remain on the existing
    ``OpenMaicFullRuntimeClient`` and are never called by ``start_recovery``.
    """

    MAX_JSON_BYTES = 2 * 1024 * 1024

    def __init__(
        self,
        base_url: str,
        *,
        internal_token: str,
        expected_canonical_spec_sha256: str,
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
                "OpenMAIC deterministic recovery URL must be a credential-free loopback origin."
            )
        token = str(internal_token or "").strip()
        if len(token) < 32 or len(token) > 512 or any(char.isspace() for char in token):
            raise ValueError(
                "OpenMAIC deterministic recovery internal token must be 32-512 non-space characters."
            )
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ValueError(
                "OpenMAIC deterministic recovery timeout must be between 0 and 300 seconds."
            )
        self.base_url = normalized
        self._origin = (parsed.scheme, parsed.netloc)
        self._internal_token = token
        self._expected_canonical_spec_sha256 = _configured_sha256(
            expected_canonical_spec_sha256,
            "expected canonical spec SHA-256",
        )
        self._expected_patch_sha256 = _configured_sha256(
            expected_patch_sha256,
            "expected patch SHA-256",
        )
        self.timeout_seconds = float(timeout_seconds)
        self._opener = build_opener(_RejectRedirects())

    def verify_runtime_policy(self, *, source_job_id: str) -> dict[str, Any]:
        """Fail closed on the exact non-secret 0007 policy before reservation."""

        source_id = _identifier(source_job_id, "sourceJobId", 128)
        payload = self._request_json("GET", "/api/health")
        runtime_policy = payload.get("runtimePolicy")
        recovery_policy = (
            runtime_policy.get("deterministicRecovery")
            if isinstance(runtime_policy, Mapping)
            else None
        )
        expected = {
            "enabled": True,
            "sourceJobId": source_id,
            "policyVersion": RECOVERY_POLICY_VERSION,
            "canonicalSpecSha256": self._expected_canonical_spec_sha256,
            "patchSha256": self._expected_patch_sha256,
        }
        if (
            payload.get("success") is not True
            or not isinstance(recovery_policy, Mapping)
            or set(recovery_policy) != set(expected)
            or dict(recovery_policy) != expected
        ):
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_runtime_policy_mismatch",
                "OpenMAIC 运行时没有启用本次固定确定性恢复策略",
                status_code=409,
            )
        return expected

    def start_recovery(
        self,
        *,
        source_job_id: str,
        recovery_request_id: str,
        expected_source_snapshot: OpenMaicRecoverySourceSnapshot,
    ) -> OpenMaicDeterministicRecovery:
        source_id = _identifier(source_job_id, "sourceJobId", 128)
        request_id = _identifier(recovery_request_id, "recoveryRequestId", 128)
        expected_recovery_id, _request_id_sha256 = deterministic_recovery_identity(
            source_id, request_id
        )
        payload = self._request_json(
            "POST",
            self._path(source_id),
            {
                "recoveryRequestId": request_id,
                "expectedSource": {
                    "status": "failed",
                    "error": RECOVERY_SOURCE_ERROR,
                    "scenesGenerated": RECOVERY_SOURCE_SCENES_GENERATED,
                    "totalScenes": RECOVERY_SOURCE_TOTAL_SCENES,
                },
            },
        )
        return self._recovery_from_payload(
            payload,
            expected_source_snapshot=expected_source_snapshot,
            expected_recovery_id=expected_recovery_id,
        )

    def get_source_snapshot(
        self, *, source_job_id: str
    ) -> OpenMaicRecoverySourceSnapshot:
        """Authenticate and freeze the failed source before any recovery POST."""

        source_id = _identifier(source_job_id, "sourceJobId", 128)
        payload = self._request_json(
            "GET", f"/api/generate-classroom/{quote(source_id, safe='')}"
        )
        if (
            payload.get("success") is not True
            or payload.get("jobId") != source_id
            or payload.get("status") != "failed"
            or payload.get("error") != RECOVERY_SOURCE_ERROR
            or payload.get("scenesGenerated") != RECOVERY_SOURCE_SCENES_GENERATED
            or payload.get("totalScenes") != RECOVERY_SOURCE_TOTAL_SCENES
            or payload.get("done") is not True
        ):
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_source_not_allowed",
                "只有固定失败状态的第三次样板任务可以确定性恢复",
                status_code=409,
            )
        completed_at = _bounded_text(payload.get("completedAt"), 64)
        canonical = {
            "completedAt": completed_at,
            "error": RECOVERY_SOURCE_ERROR,
            "id": source_id,
            "requirementMarker": RECOVERY_POLICY_MARKER,
            "scenesGenerated": RECOVERY_SOURCE_SCENES_GENERATED,
            "status": "failed",
            "totalScenes": RECOVERY_SOURCE_TOTAL_SCENES,
        }
        digest = hashlib.sha256(
            json.dumps(
                canonical,
                ensure_ascii=False,
                separators=(",", ":"),
                sort_keys=True,
            ).encode("utf-8")
        ).hexdigest()
        return OpenMaicRecoverySourceSnapshot(
            job_id=source_id,
            completed_at=completed_at,
            job_snapshot_sha256=digest,
        )

    def get_recovery(
        self,
        *,
        source_job_id: str,
        expected_recovery_id: str,
        recovery_request_id: str,
        expected_source_snapshot: OpenMaicRecoverySourceSnapshot,
    ) -> OpenMaicDeterministicRecovery:
        source_id = _identifier(source_job_id, "sourceJobId", 128)
        recovery_id = _identifier(expected_recovery_id, "recoveryId", 128)
        request_id = _identifier(
            recovery_request_id, "recoveryRequestId", 128
        )
        deterministic_id, _request_id_sha256 = deterministic_recovery_identity(
            source_id, request_id
        )
        if deterministic_id != recovery_id:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_identity_mismatch",
                "本地恢复编号与固定幂等合同不一致",
                status_code=409,
            )
        payload = self._request_json("GET", self._path(source_id))
        recovery = self._recovery_from_payload(
            payload,
            expected_source_snapshot=expected_source_snapshot,
            expected_recovery_id=recovery_id,
        )
        if recovery.recovery_id != recovery_id:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_identity_mismatch",
                "OpenMAIC 恢复记录与已保留的恢复任务不一致",
                status_code=409,
            )
        return recovery

    def assert_recovery_absent(
        self,
        *,
        source_job_id: str,
        expected_recovery_id: str,
        recovery_request_id: str,
    ) -> dict[str, Any]:
        """Require the authenticated 0007 GET to return its exact 404 body."""

        source_id = _identifier(source_job_id, "sourceJobId", 128)
        recovery_id = _identifier(expected_recovery_id, "recoveryId", 128)
        request_id = _identifier(
            recovery_request_id, "recoveryRequestId", 128
        )
        deterministic_id, _request_hash = deterministic_recovery_identity(
            source_id, request_id
        )
        if recovery_id != deterministic_id:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_identity_mismatch",
                "本地恢复编号与固定幂等合同不一致",
                status_code=409,
            )

        target = urljoin(f"{self.base_url}/", self._path(source_id).lstrip("/"))
        parsed = urlparse(target)
        if (parsed.scheme, parsed.netloc) != self._origin:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_target_not_allowed",
                "OpenMAIC 恢复请求目标不安全",
            )
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
                final = urlparse(response.geturl())
                if (final.scheme, final.netloc) != self._origin:
                    raise OpenMaicDeterministicRecoveryError(
                        "openmaic_recovery_redirect_not_allowed",
                        "OpenMAIC 恢复接口返回了不安全的跳转",
                    )
                response.read(self.MAX_JSON_BYTES + 1)
        except HTTPError as exc:
            if int(getattr(exc, "code", 0) or 0) != 404:
                raise OpenMaicDeterministicRecoveryError(
                    "openmaic_recovery_absence_not_proven",
                    "OpenMAIC 没有明确证明恢复记录不存在",
                    status_code=int(getattr(exc, "code", 502) or 502),
                ) from exc
            final = urlparse(exc.geturl())
            if (final.scheme, final.netloc) != self._origin:
                raise OpenMaicDeterministicRecoveryError(
                    "openmaic_recovery_redirect_not_allowed",
                    "OpenMAIC 恢复接口返回了不安全的跳转",
                ) from exc
            raw = exc.read(self.MAX_JSON_BYTES + 1)
        except (URLError, TimeoutError, OSError) as exc:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_absence_not_proven",
                "暂时无法确认 OpenMAIC 恢复记录不存在",
                status_code=503,
            ) from exc
        else:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_already_claimed",
                "OpenMAIC 已存在这条确定性恢复记录，禁止再次派发",
                status_code=409,
            )

        if len(raw) > self.MAX_JSON_BYTES:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_absence_not_proven",
                "OpenMAIC 恢复缺席回执超过安全上限",
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_absence_not_proven",
                "OpenMAIC 没有返回固定的恢复缺席回执",
                status_code=409,
            ) from exc
        expected = {
            "success": False,
            "errorCode": "INVALID_REQUEST",
            "error": "Deterministic recovery not found",
        }
        if not isinstance(payload, dict) or payload != expected:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_absence_not_proven",
                "OpenMAIC 没有返回固定的恢复缺席回执",
                status_code=409,
            )
        return {
            "absent": True,
            "sourceJobId": source_id,
            "expectedRecoveryId": recovery_id,
        }

    @staticmethod
    def _path(source_job_id: str) -> str:
        return (
            f"/api/generate-classroom/{quote(source_job_id, safe='')}"
            "/deterministic-recovery"
        )

    def _recovery_from_payload(
        self,
        payload: object,
        *,
        expected_source_snapshot: OpenMaicRecoverySourceSnapshot,
        expected_recovery_id: str,
    ) -> OpenMaicDeterministicRecovery:
        if not isinstance(payload, Mapping) or payload.get("success") is not True:
            self._invalid()
        recovery_id = _identifier(payload.get("recoveryId"), "recoveryId", 128)
        if recovery_id != expected_recovery_id:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_identity_mismatch",
                "OpenMAIC 恢复记录与已保留的幂等请求不一致",
                status_code=409,
            )
        status = str(payload.get("status") or "").strip().lower()
        if status not in {"queued", "running", "succeeded", "failed"}:
            self._invalid()
        source = payload.get("source")
        policy = payload.get("policy")
        calls = payload.get("calls")
        if not isinstance(source, Mapping) or not isinstance(
            policy, Mapping
        ) or not isinstance(calls, Mapping):
            self._invalid()
        if set(source) != {
            "jobId",
            "status",
            "error",
            "scenesGenerated",
            "totalScenes",
            "completedAt",
            "jobSnapshotSha256",
            "jobSnapshotHashBasis",
        } or set(policy) != {
            "marker",
            "version",
            "canonicalSpecSha256",
            "patchSha256",
        } or set(calls) != {
            "llm",
            "webSearch",
            "imageGeneration",
            "videoGeneration",
            "tts",
        }:
            self._invalid()
        normalized_source = {
            "jobId": _identifier(source.get("jobId"), "source.jobId", 128),
            "status": str(source.get("status") or "").strip(),
            "error": str(source.get("error") or "").strip(),
            "scenesGenerated": _strict_int(source.get("scenesGenerated")),
            "totalScenes": _strict_int(source.get("totalScenes")),
            "completedAt": _bounded_text(source.get("completedAt"), 64),
            "jobSnapshotSha256": _sha256(source.get("jobSnapshotSha256")),
            "jobSnapshotHashBasis": _bounded_text(
                source.get("jobSnapshotHashBasis"), 32
            ),
        }
        if normalized_source != expected_source_snapshot.to_audit_source():
            self._invalid()
        normalized_policy = {
            "marker": _bounded_text(policy.get("marker"), 128),
            "version": _bounded_text(policy.get("version"), 128),
            "canonicalSpecSha256": _sha256(policy.get("canonicalSpecSha256")),
            "patchSha256": _sha256(policy.get("patchSha256")),
        }
        if normalized_policy["marker"] != RECOVERY_POLICY_MARKER:
            self._invalid()
        if normalized_policy != {
            "marker": RECOVERY_POLICY_MARKER,
            "version": RECOVERY_POLICY_VERSION,
            "canonicalSpecSha256": self._expected_canonical_spec_sha256,
            "patchSha256": self._expected_patch_sha256,
        }:
            self._invalid()
        tts = calls.get("tts")
        if not isinstance(tts, Mapping) or set(tts) != {
            "expected",
            "attempted",
            "completed",
        }:
            self._invalid()
        normalized_calls = {
            "llm": _strict_int(calls.get("llm")),
            "webSearch": _strict_int(calls.get("webSearch")),
            "imageGeneration": _strict_int(calls.get("imageGeneration")),
            "videoGeneration": _strict_int(calls.get("videoGeneration")),
            "tts": {
                "expected": _strict_int(tts.get("expected")),
                "attempted": _strict_int(tts.get("attempted")),
                "completed": _strict_int(tts.get("completed")),
            },
        }
        if (
            any(normalized_calls[key] != 0 for key in (
                "llm", "webSearch", "imageGeneration", "videoGeneration"
            ))
            or normalized_calls["tts"]["expected"] != 10
            or not (
                0
                <= normalized_calls["tts"]["completed"]
                <= normalized_calls["tts"]["attempted"]
                <= normalized_calls["tts"]["expected"]
            )
        ):
            self._invalid()

        artifact = self._artifact(payload.get("artifact"), required=status == "succeeded")
        if status == "succeeded" and (
            normalized_calls["tts"]["attempted"] != 10
            or
            normalized_calls["tts"]["completed"] != 10
            or artifact is None
            or artifact["sceneCount"] != 10
            or artifact["tts"]["speechCount"] != 10
            or payload.get("error") is not None
            or payload.get("completedAt") is None
            or payload.get("progress") != 100
        ):
            self._invalid()
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
        if status in {"queued", "running"} and (
            artifact is not None or normalized_error is not None
        ):
            self._invalid()
        if status == "failed" and (
            artifact is not None
            or normalized_error is None
            or normalized_error["code"] != "deterministic_recovery_failed"
            or payload.get("completedAt") is None
        ):
            self._invalid()
        done = payload.get("done")
        if not isinstance(done, bool) or done != (status in {"succeeded", "failed"}):
            self._invalid()
        progress = _strict_int(payload.get("progress"))
        if not 0 <= progress <= 100:
            self._invalid()
        if (
            payload.get("schemaVersion") != RECOVERY_SCHEMA
            or payload.get("kind") != RECOVERY_KIND
            or payload.get("mode") != RECOVERY_MODE
        ):
            self._invalid()
        return OpenMaicDeterministicRecovery(
            recovery_id=recovery_id,
            status=status,
            step=_bounded_text(payload.get("step"), 128),
            progress=progress,
            done=done,
            source=normalized_source,
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
        )

    @staticmethod
    def _artifact(value: object, *, required: bool) -> dict[str, Any] | None:
        if value is None and not required:
            return None
        if not isinstance(value, Mapping):
            OpenMaicDeterministicRecoveryClient._invalid()
        assert isinstance(value, Mapping)
        if set(value) != {
            "classroomId",
            "url",
            "sceneCount",
            "contentSha256",
            "artifactSha256",
            "tts",
        }:
            OpenMaicDeterministicRecoveryClient._invalid()
        tts = value.get("tts")
        if not isinstance(tts, Mapping) or set(tts) != {
            "providerId",
            "modelId",
            "voiceId",
            "speechCount",
            "fallbackUsed",
        }:
            OpenMaicDeterministicRecoveryClient._invalid()
        artifact = {
            "classroomId": _identifier(value.get("classroomId"), "artifact.classroomId", 255),
            "url": _bounded_text(value.get("url"), 1024),
            "sceneCount": _strict_int(value.get("sceneCount")),
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
        if artifact["tts"] != {
            "providerId": "qwen-tts",
            "modelId": "qwen3-tts-flash",
            "voiceId": "Serena",
            "speechCount": 10,
            "fallbackUsed": False,
        }:
            OpenMaicDeterministicRecoveryClient._invalid()
        return artifact

    def _request_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        target = urljoin(f"{self.base_url}/", path.lstrip("/"))
        parsed = urlparse(target)
        if (parsed.scheme, parsed.netloc) != self._origin:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_target_not_allowed",
                "OpenMAIC 恢复请求目标不安全",
            )
        data = (
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
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
            with self._opener.open(request, timeout=self.timeout_seconds) as response:
                final = urlparse(response.geturl())
                if (final.scheme, final.netloc) != self._origin:
                    raise OpenMaicDeterministicRecoveryError(
                        "openmaic_recovery_redirect_not_allowed",
                        "OpenMAIC 恢复接口返回了不安全的跳转",
                    )
                raw = response.read(self.MAX_JSON_BYTES + 1)
        except HTTPError as exc:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_upstream_rejected",
                "OpenMAIC 拒绝了这次确定性恢复",
                status_code=int(getattr(exc, "code", 502) or 502),
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_unavailable",
                "暂时无法连接 OpenMAIC 确定性恢复服务",
                status_code=503,
            ) from exc
        if len(raw) > self.MAX_JSON_BYTES:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_response_too_large",
                "OpenMAIC 恢复回执超过安全上限",
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise OpenMaicDeterministicRecoveryError(
                "invalid_openmaic_recovery_response",
                "OpenMAIC 恢复回执格式无效",
            ) from exc
        if not isinstance(payload, dict):
            self._invalid()
        return payload

    @staticmethod
    def _invalid() -> None:
        raise OpenMaicDeterministicRecoveryError(
            "invalid_openmaic_recovery_response",
            "OpenMAIC 恢复回执与固定零 LLM 合同不一致",
        )


def _identifier(value: object, field: str, max_length: int) -> str:
    normalized = str(value or "").strip()
    if (
        not normalized
        or len(normalized) > max_length
        or not all(char.isalnum() or char in {"-", "_"} for char in normalized)
    ):
        raise OpenMaicDeterministicRecoveryError(
            "invalid_openmaic_recovery_identifier",
            f"OpenMAIC 恢复字段 {field} 无效",
            status_code=400,
        )
    return normalized


def _strict_int(value: object) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        OpenMaicDeterministicRecoveryClient._invalid()
    return int(value)


def _bounded_text(value: object, max_length: int) -> str:
    if not isinstance(value, str):
        OpenMaicDeterministicRecoveryClient._invalid()
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        OpenMaicDeterministicRecoveryClient._invalid()
    return normalized


def _sha256(value: object) -> str:
    normalized = _bounded_text(value, 64).lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        OpenMaicDeterministicRecoveryClient._invalid()
    return normalized


def _configured_sha256(value: object, field: str) -> str:
    normalized = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", normalized):
        raise ValueError(f"OpenMAIC deterministic recovery {field} is invalid.")
    return normalized


def deterministic_recovery_identity(
    source_job_id: str, recovery_request_id: str
) -> tuple[str, str]:
    source_id = _identifier(source_job_id, "sourceJobId", 128)
    request_id = _identifier(recovery_request_id, "recoveryRequestId", 128)
    request_hash = hashlib.sha256(request_id.encode("utf-8")).hexdigest()
    identity_hash = hashlib.sha256(
        f"{source_id}:{request_hash}".encode("utf-8")
    ).hexdigest()
    return f"omrec_{identity_hash[:24]}", request_hash
