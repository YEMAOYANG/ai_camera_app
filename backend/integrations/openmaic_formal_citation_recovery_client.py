from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from integrations.openmaic_full_runtime_client import (
    OpenMaicFullRuntimeClient,
    OpenMaicFullRuntimeError,
    OpenMaicGenerationJob,
)


FORMAL_CITATION_RECOVERY_SCHEMA = (
    "mira.openmaic.formal-citation-recovery.v1"
)
FORMAL_CITATION_RECOVERY_KIND = "formal_citation_recovery"
FORMAL_CITATION_RECOVERY_SOURCE_ERROR = (
    "FORMAL_PROFESSIONAL_RESEARCH_CITATION_MISSING"
)
FORMAL_CITATION_RECOVERY_POLICY_VERSION = (
    "mira-formal-citation-footer-canonicalize.v1"
)


class OpenMaicFormalCitationRecoveryError(RuntimeError):
    def __init__(self, code: str, safe_message: str, *, status_code: int = 502):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.status_code = status_code


@dataclass(frozen=True)
class OpenMaicFormalCitationRecovery:
    recovery_id: str
    source: Mapping[str, Any]
    status: str
    step: str
    progress: int
    message: str
    calls: Mapping[str, int]
    repair: Mapping[str, Any] | None
    result: Mapping[str, Any] | None
    created_at: str
    updated_at: str
    started_at: str | None
    completed_at: str | None
    error: Mapping[str, str] | None
    poll_url: str
    done: bool
    receipt: Mapping[str, Any]

    def audit_receipt(self) -> dict[str, Any]:
        return json.loads(
            json.dumps(
                dict(self.receipt),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    def as_generation_job(self) -> OpenMaicGenerationJob:
        if self.status != "succeeded" or not isinstance(self.result, Mapping):
            raise OpenMaicFormalCitationRecoveryError(
                "openmaic_formal_citation_recovery_incomplete",
                "OpenMAIC 引用恢复尚未产生可验收课堂",
                status_code=409,
            )
        result = self.result
        classroom_id = str(result["classroomId"])
        scenes_count = int(result["scenesCount"])
        speech_action_count = int(result["speechActionCount"])
        try:
            formal_audio = OpenMaicFullRuntimeClient._formal_audio_receipt_from_payload(
                result["formalAudio"],
                classroom_id=classroom_id,
                expected_segment_count=speech_action_count,
            )
            professional = (
                OpenMaicFullRuntimeClient._professional_creation_receipt_from_payload(
                    result["professionalCreation"],
                    runtime_request_id=str(self.source["runtimeRequestId"]),
                    classroom_id=classroom_id,
                )
            )
            research = OpenMaicFullRuntimeClient._research_receipt_from_payload(
                result["research"],
                runtime_request_id=str(self.source["runtimeRequestId"]),
                classroom_id=classroom_id,
            )
        except OpenMaicFullRuntimeError as exc:
            raise OpenMaicFormalCitationRecoveryError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc
        if (
            professional["buildItemId"] != research["buildItemId"]
            or professional["sessionId"] != research["sessionId"]
        ):
            raise OpenMaicFormalCitationRecoveryError(
                "invalid_openmaic_formal_citation_recovery_response",
                "OpenMAIC 引用恢复的专业创作与研究身份不一致",
            )
        return OpenMaicGenerationJob(
            job_id=str(self.source["jobId"]),
            status="succeeded",
            step=self.step,
            progress=100,
            done=True,
            classroom_id=classroom_id,
            scenes_count=scenes_count,
            error=None,
            speech_action_count=speech_action_count,
            runtime_request_id=str(self.source["runtimeRequestId"]),
            formal_contract_version=(
                OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
            ),
            formal_input_sha256=str(self.source["formalInputSha256"]),
            dispatch_ambiguous=False,
            failure_code=None,
            formal_audio=formal_audio,
            professional_creation=professional,
            research=research,
        )


class _RejectRedirects(HTTPRedirectHandler):
    def redirect_request(self, *_args: Any, **_kwargs: Any) -> None:
        return None


class OpenMaicFormalCitationRecoveryClient:
    MAX_JSON_BYTES = 32 * 1024 * 1024

    def __init__(
        self,
        base_url: str,
        *,
        internal_token: str,
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
                "OpenMAIC formal citation recovery URL must be a credential-free loopback origin."
            )
        token = str(internal_token or "").strip()
        if (
            len(token) < 32
            or len(token) > 512
            or any(char.isspace() for char in token)
        ):
            raise ValueError(
                "OpenMAIC formal citation recovery token must be 32-512 non-space characters."
            )
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ValueError(
                "OpenMAIC formal citation recovery timeout must be between 0 and 300 seconds."
            )
        self.base_url = normalized
        self._origin = (parsed.scheme, parsed.netloc)
        self._internal_token = token
        self.timeout_seconds = float(timeout_seconds)
        self._opener = build_opener(_RejectRedirects())

    def start_recovery(
        self,
        *,
        source_job_id: str,
        recovery_request_id: str,
        runtime_request_id: str,
        formal_input_sha256: str,
    ) -> OpenMaicFormalCitationRecovery:
        job_id = _identifier(source_job_id, "sourceJobId", 128)
        request_id = _identifier(recovery_request_id, "recoveryRequestId", 128)
        runtime_id = _identifier(runtime_request_id, "runtimeRequestId", 128)
        input_sha256 = _sha256(formal_input_sha256)
        payload = self._request_json(
            "POST",
            self._path(job_id),
            {
                "recoveryRequestId": request_id,
                "expectedSource": {
                    "runtimeRequestId": runtime_id,
                    "formalInputSha256": input_sha256,
                    "status": "failed",
                    "error": FORMAL_CITATION_RECOVERY_SOURCE_ERROR,
                },
            },
        )
        return self._from_payload(
            payload,
            expected_job_id=job_id,
            expected_runtime_request_id=runtime_id,
            expected_formal_input_sha256=input_sha256,
        )

    def get_recovery(
        self,
        *,
        source_job_id: str,
        expected_recovery_id: str,
        runtime_request_id: str,
        formal_input_sha256: str,
    ) -> OpenMaicFormalCitationRecovery:
        job_id = _identifier(source_job_id, "sourceJobId", 128)
        recovery_id = _identifier(
            expected_recovery_id, "expectedRecoveryId", 128
        )
        runtime_id = _identifier(runtime_request_id, "runtimeRequestId", 128)
        input_sha256 = _sha256(formal_input_sha256)
        recovery = self._from_payload(
            self._request_json("GET", self._path(job_id)),
            expected_job_id=job_id,
            expected_runtime_request_id=runtime_id,
            expected_formal_input_sha256=input_sha256,
        )
        if recovery.recovery_id != recovery_id:
            self._invalid("OpenMAIC 引用恢复编号发生变化")
        return recovery

    @staticmethod
    def _path(source_job_id: str) -> str:
        return (
            "/api/generate-classroom/"
            + quote(source_job_id, safe="")
            + "/formal-citation-recovery"
        )

    def _from_payload(
        self,
        payload: object,
        *,
        expected_job_id: str,
        expected_runtime_request_id: str,
        expected_formal_input_sha256: str,
    ) -> OpenMaicFormalCitationRecovery:
        if not isinstance(payload, Mapping):
            self._invalid()
        required = {
            "schemaVersion",
            "kind",
            "recoveryId",
            "source",
            "status",
            "step",
            "progress",
            "message",
            "calls",
            "repair",
            "result",
            "createdAt",
            "updatedAt",
            "pollUrl",
            "done",
        }
        optional = {"startedAt", "completedAt", "error", "receiptSha256"}
        if not required.issubset(payload) or set(payload) - required - optional:
            self._invalid()
        if (
            payload.get("schemaVersion") != FORMAL_CITATION_RECOVERY_SCHEMA
            or payload.get("kind") != FORMAL_CITATION_RECOVERY_KIND
        ):
            self._invalid()
        recovery_id = _identifier(payload.get("recoveryId"), "recoveryId", 128)
        status = str(payload.get("status") or "").strip().lower()
        if status not in {"queued", "running", "succeeded", "failed"}:
            self._invalid()
        source = payload.get("source")
        if not isinstance(source, Mapping) or set(source) != {
            "jobId",
            "runtimeRequestId",
            "status",
            "error",
            "formalInputSha256",
            "completedAt",
            "jobSnapshotSha256",
        }:
            self._invalid()
        normalized_source = {
            "jobId": _identifier(source.get("jobId"), "source.jobId", 128),
            "runtimeRequestId": _identifier(
                source.get("runtimeRequestId"), "source.runtimeRequestId", 128
            ),
            "status": str(source.get("status") or ""),
            "error": str(source.get("error") or ""),
            "formalInputSha256": _sha256(source.get("formalInputSha256")),
            "completedAt": _timestamp(source.get("completedAt")),
            "jobSnapshotSha256": _sha256(source.get("jobSnapshotSha256")),
        }
        if normalized_source != {
            **normalized_source,
            "jobId": expected_job_id,
            "runtimeRequestId": expected_runtime_request_id,
            "status": "failed",
            "error": FORMAL_CITATION_RECOVERY_SOURCE_ERROR,
            "formalInputSha256": expected_formal_input_sha256,
        }:
            self._invalid("OpenMAIC 引用恢复源任务身份不一致")
        calls = payload.get("calls")
        expected_calls = {
            "llm": 0,
            "webSearch": 0,
            "fetchUrl": 0,
            "imageGeneration": 0,
            "videoGeneration": 0,
        }
        if (
            not isinstance(calls, Mapping)
            or set(calls) != set(expected_calls)
            or any(type(calls[key]) is not int or calls[key] != 0 for key in calls)
        ):
            self._invalid("OpenMAIC 引用恢复产生了禁止的外部调用")
        repair = self._repair(payload.get("repair"), required=status == "succeeded")
        result = self._result(payload.get("result"), required=status == "succeeded")
        if status == "succeeded":
            assert repair is not None and result is not None
            self._validate_repair_research_binding(repair, result)
        done = payload.get("done")
        if type(payload.get("progress")) is not int or not 0 <= int(
            payload["progress"]
        ) <= 100:
            self._invalid()
        if done is not (status in {"succeeded", "failed"}):
            self._invalid()
        error = payload.get("error")
        normalized_error = None
        if status == "failed":
            if not isinstance(error, Mapping) or set(error) != {"code", "message"}:
                self._invalid()
            normalized_error = {
                "code": _text(error.get("code"), 128),
                "message": _text(error.get("message"), 512),
            }
        elif error is not None:
            self._invalid()
        poll_url = str(payload.get("pollUrl") or "")
        if poll_url != self._path(expected_job_id):
            self._invalid()
        normalized = json.loads(
            json.dumps(
                dict(payload),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        raw_receipt_sha256 = payload.get("receiptSha256")
        if status in {"succeeded", "failed"}:
            receipt_sha256 = _sha256(raw_receipt_sha256)
            unsigned = dict(normalized)
            unsigned.pop("receiptSha256")
            if _canonical_sha256(unsigned) != receipt_sha256:
                self._invalid("OpenMAIC 引用恢复终态回执校验失败")
        elif raw_receipt_sha256 is not None:
            self._invalid()
        return OpenMaicFormalCitationRecovery(
            recovery_id=recovery_id,
            source=normalized_source,
            status=status,
            step=_text(payload.get("step"), 128),
            progress=int(payload["progress"]),
            message=_text(payload.get("message"), 512),
            calls=expected_calls,
            repair=repair,
            result=result,
            created_at=_timestamp(payload.get("createdAt")),
            updated_at=_timestamp(payload.get("updatedAt")),
            started_at=(
                _timestamp(payload.get("startedAt"))
                if payload.get("startedAt") is not None
                else None
            ),
            completed_at=(
                _timestamp(payload.get("completedAt"))
                if payload.get("completedAt") is not None
                else None
            ),
            error=normalized_error,
            poll_url=poll_url,
            done=bool(done),
            receipt=normalized,
        )

    def _repair(self, value: object, *, required: bool) -> dict[str, Any] | None:
        if value is None and not required:
            return None
        if not isinstance(value, Mapping) or set(value) != {
            "policyVersion",
            "sourceUrls",
            "repairedSceneIds",
            "beforeScenesSha256",
            "afterScenesSha256",
            "repairSha256",
        }:
            self._invalid()
        assert isinstance(value, Mapping)
        source_urls = value.get("sourceUrls")
        scene_ids = value.get("repairedSceneIds")
        if (
            value.get("policyVersion") != FORMAL_CITATION_RECOVERY_POLICY_VERSION
            or not isinstance(source_urls, list)
            or not source_urls
            or len(source_urls) > 32
            or any(not _safe_url(item) for item in source_urls)
            or len(set(source_urls)) != len(source_urls)
            or not isinstance(scene_ids, list)
            or not scene_ids
            or len(scene_ids) > 60
            or any(not _safe_identifier(item, 128) for item in scene_ids)
            or len(set(scene_ids)) != len(scene_ids)
        ):
            self._invalid()
        normalized = {
            "policyVersion": FORMAL_CITATION_RECOVERY_POLICY_VERSION,
            "sourceUrls": list(source_urls),
            "repairedSceneIds": list(scene_ids),
            "beforeScenesSha256": _sha256(value.get("beforeScenesSha256")),
            "afterScenesSha256": _sha256(value.get("afterScenesSha256")),
            "repairSha256": _sha256(value.get("repairSha256")),
        }
        unsigned = dict(normalized)
        unsigned.pop("repairSha256")
        if (
            normalized["beforeScenesSha256"]
            == normalized["afterScenesSha256"]
            or normalized["repairSha256"] != _canonical_sha256(unsigned)
        ):
            self._invalid("OpenMAIC 引用修复哈希无效")
        return normalized

    def _result(self, value: object, *, required: bool) -> dict[str, Any] | None:
        if value is None and not required:
            return None
        if not isinstance(value, Mapping) or set(value) != {
            "classroomId",
            "url",
            "scenesCount",
            "speechActionCount",
            "formalAudio",
            "professionalCreation",
            "research",
            "createdAt",
        }:
            self._invalid()
        assert isinstance(value, Mapping)
        classroom_id = _identifier(value.get("classroomId"), "classroomId", 255)
        scenes_count = value.get("scenesCount")
        speech_count = value.get("speechActionCount")
        if (
            type(scenes_count) is not int
            or not 1 <= scenes_count <= 60
            or type(speech_count) is not int
            or not scenes_count <= speech_count <= min(240, scenes_count * 20)
            or not isinstance(value.get("formalAudio"), Mapping)
            or not isinstance(value.get("professionalCreation"), Mapping)
            or not isinstance(value.get("research"), Mapping)
        ):
            self._invalid()
        raw_url = _text(value.get("url"), 1024)
        absolute_url = urljoin(f"{self.base_url}/", raw_url)
        parsed_url = urlparse(absolute_url)
        if (
            (parsed_url.scheme, parsed_url.netloc) != self._origin
            or parsed_url.path != f"/classroom/{classroom_id}"
            or parsed_url.fragment
        ):
            self._invalid("OpenMAIC 引用恢复课堂地址无效")
        return {
            "classroomId": classroom_id,
            "url": raw_url,
            "scenesCount": int(scenes_count),
            "speechActionCount": int(speech_count),
            "formalAudio": dict(value["formalAudio"]),
            "professionalCreation": dict(value["professionalCreation"]),
            "research": dict(value["research"]),
            "createdAt": _timestamp(value.get("createdAt")),
        }

    def _validate_repair_research_binding(
        self,
        repair: Mapping[str, Any],
        result: Mapping[str, Any],
    ) -> None:
        research = result.get("research")
        sources = research.get("sources") if isinstance(research, Mapping) else None
        citations = (
            research.get("citations") if isinstance(research, Mapping) else None
        )
        if not isinstance(sources, list) or not isinstance(citations, list):
            self._invalid("OpenMAIC 引用恢复没有研究来源绑定")
        source_urls = set(repair["sourceUrls"])
        repaired_scene_ids = set(repair["repairedSceneIds"])
        receipt_source_urls = {
            str(source.get("url") or "")
            for source in sources
            if isinstance(source, Mapping)
        }
        cited_urls: set[str] = set()
        covered_scene_ids: set[str] = set()
        for citation in citations:
            if not isinstance(citation, Mapping):
                self._invalid()
            url = str(citation.get("url") or "")
            scene_ids = citation.get("sceneIds")
            if url in source_urls and isinstance(scene_ids, list):
                cited_urls.add(url)
                covered_scene_ids.update(str(scene_id) for scene_id in scene_ids)
        if not (
            source_urls
            and source_urls.issubset(receipt_source_urls)
            and source_urls.issubset(cited_urls)
            and repaired_scene_ids
            and repaired_scene_ids.issubset(covered_scene_ids)
        ):
            self._invalid("OpenMAIC 引用修复与研究回执未绑定到同一场景")

    def _request_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        data = (
            json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode(
                "utf-8"
            )
            if body is not None
            else None
        )
        request = Request(
            self._target(path),
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
            raise OpenMaicFormalCitationRecoveryError(
                "openmaic_formal_citation_recovery_rejected",
                "OpenMAIC 拒绝了引用恢复请求",
                status_code=int(getattr(exc, "code", 502) or 502),
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OpenMaicFormalCitationRecoveryError(
                "openmaic_formal_citation_recovery_unavailable",
                "暂时无法连接 OpenMAIC 引用恢复服务",
                status_code=503,
            ) from exc
        if len(raw) > self.MAX_JSON_BYTES:
            raise OpenMaicFormalCitationRecoveryError(
                "openmaic_formal_citation_recovery_response_too_large",
                "OpenMAIC 引用恢复回执超过安全上限",
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise OpenMaicFormalCitationRecoveryError(
                "invalid_openmaic_formal_citation_recovery_response",
                "OpenMAIC 引用恢复回执格式无效",
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
            raise OpenMaicFormalCitationRecoveryError(
                "openmaic_formal_citation_recovery_target_not_allowed",
                "OpenMAIC 引用恢复请求目标不安全",
            )

    @staticmethod
    def _invalid(
        message: str = "OpenMAIC 引用恢复回执与固定合同不一致",
    ) -> None:
        raise OpenMaicFormalCitationRecoveryError(
            "invalid_openmaic_formal_citation_recovery_response", message
        )


def _safe_identifier(value: object, maximum: int) -> bool:
    text = str(value or "")
    return bool(
        text
        and len(text) <= maximum
        and text == text.strip()
        and re.fullmatch(r"[A-Za-z0-9._:-]+", text)
    )


def _identifier(value: object, field: str, maximum: int) -> str:
    if not _safe_identifier(value, maximum):
        raise OpenMaicFormalCitationRecoveryError(
            "invalid_openmaic_formal_citation_recovery_response",
            f"OpenMAIC 引用恢复字段 {field} 无效",
        )
    return str(value)


def _sha256(value: object) -> str:
    text = str(value or "")
    if re.fullmatch(r"[0-9a-f]{64}", text) is None:
        raise OpenMaicFormalCitationRecoveryError(
            "invalid_openmaic_formal_citation_recovery_response",
            "OpenMAIC 引用恢复校验值无效",
        )
    return text


def _text(value: object, maximum: int) -> str:
    text = str(value or "")
    if not text or text != text.strip() or len(text) > maximum:
        raise OpenMaicFormalCitationRecoveryError(
            "invalid_openmaic_formal_citation_recovery_response",
            "OpenMAIC 引用恢复文本字段无效",
        )
    return text


def _timestamp(value: object) -> str:
    text = _text(value, 64)
    if "T" not in text or not (text.endswith("Z") or "+" in text[10:]):
        raise OpenMaicFormalCitationRecoveryError(
            "invalid_openmaic_formal_citation_recovery_response",
            "OpenMAIC 引用恢复时间字段无效",
        )
    return text


def _safe_url(value: object) -> bool:
    text = str(value or "")
    parsed = urlparse(text)
    return bool(
        len(text) <= 2048
        and text == text.strip()
        and parsed.scheme in {"http", "https"}
        and parsed.netloc
        and not parsed.username
        and not parsed.password
        and not parsed.fragment
    )


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            dict(value),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
