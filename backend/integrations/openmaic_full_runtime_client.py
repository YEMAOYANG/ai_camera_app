from __future__ import annotations

import json
import hashlib
import re
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse
from urllib.request import Request, urlopen


from integrations.openmaic_formal_media import (
    FORMAL_IMAGE_POLICY, LEGACY_PROFESSIONAL_POLICY, PROFESSIONAL_POLICY, VIDEO_PROFESSIONAL_POLICY, INTERACTIVE_PROFESSIONAL_POLICY, MULTISTATE_PROFESSIONAL_POLICY,
    LEGACY_GENERATION_OPTIONS, generation_options, professional_policy,
    professional_image_fields, media_receipt,
)
from integrations.openmaic_formal_video import FORMAL_VIDEO_POLICY, professional_video_fields, video_receipt
from integrations.openmaic_formal_skills import professional_skill_fields
from integrations.openmaic_formal_quality import professional_quality_fields
from integrations.openmaic_formal_interaction import professional_interaction_fields
from integrations.openmaic_asr_revalidation import validate_asr_comparison_revalidation


class OpenMaicFullRuntimeError(RuntimeError):
    def __init__(self, code: str, safe_message: str, *, status_code: int = 502):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.status_code = status_code


@dataclass(frozen=True)
class OpenMaicFormalAudioTtsReceipt:
    request_id: str
    request_sha256: str
    audio_sha256: str
    size_bytes: int
    voice_id: str


@dataclass(frozen=True)
class OpenMaicFormalAudioAsrReceipt:
    request_id: str
    request_sha256: str
    transcript_sha256: str
    normalized_transcript_sha256: str
    similarity_bps: int
    comparison_revalidation: dict[str, Any] | None = None


@dataclass(frozen=True)
class OpenMaicFormalAudioSegmentReceipt:
    scene_order: int
    scene_id: str
    action_id: str
    narration_segment_id: str
    source_text_sha256: str
    text_sha256: str
    tts: OpenMaicFormalAudioTtsReceipt
    asr: OpenMaicFormalAudioAsrReceipt


@dataclass(frozen=True)
class OpenMaicFormalAudioReceipt:
    schema_version: str
    build_item_id: str
    classroom_id: str
    classroom_content_sha256: str
    subject: str
    speech_text_policy_version: str
    teacher_profile_id: str
    teacher_profile_version: int
    teacher_profile_sha256: str
    teacher_gender: str
    expected_segment_count: int
    tts_succeeded_count: int
    asr_passed_count: int
    segments: tuple[OpenMaicFormalAudioSegmentReceipt, ...]
    receipt_sha256: str


@dataclass(frozen=True)
class OpenMaicGenerationJob:
    job_id: str
    status: str
    step: str
    progress: int
    done: bool
    classroom_id: str | None
    scenes_count: int | None
    error: str | None
    speech_action_count: int | None = None
    runtime_request_id: str | None = None
    formal_contract_version: str | None = None
    formal_input_sha256: str | None = None
    dispatch_ambiguous: bool = False
    failure_code: str | None = None
    formal_audio: OpenMaicFormalAudioReceipt | None = None
    professional_creation: dict[str, Any] | None = None
    research: dict[str, Any] | None = None
    media: dict[str, Any] | None = None
    video: dict[str, Any] | None = None


class OpenMaicFullRuntimeClient:
    """Server-only client for a pinned, privately hosted OpenMAIC app."""

    MAX_JSON_BYTES = 32 * 1024 * 1024
    AUDIO_PROBE_BYTES = 4096
    MIN_AUDIO_BYTES = 256
    FORMAL_AUDIO_MAX_BYTES = 16 * 1024 * 1024
    FORMAL_AUDIO_TIMEOUT_SECONDS = 120
    # One OpenMAIC TTS POST can include both a bounded Provider request and a
    # bounded OSS audio download. Keep the caller window larger than those
    # two 120-second phases so the backend never abandons a request while
    # OpenMAIC is still recording its durable outcome.
    FORMAL_AUDIO_REQUEST_TIMEOUT_SECONDS = 270
    SAMPLE_RUNTIME_VERSION = "0.3.2"
    FORMAL_RUNTIME_VERSION = "1.0.0"
    SAMPLE_TTS_POLICY = {
        "enforced": True,
        "providerId": "qwen-tts",
        "modelId": "qwen3-tts-flash",
        "voiceId": "Serena",
    }
    SAMPLE_ASR_POLICY = {
        "enforced": True,
        "providerId": "qwen-asr",
        "modelId": "qwen3-asr-flash",
        "fallbackAllowed": False,
    }
    SAMPLE_STRUCTURED_SCENE_POLICY = {
        "enforced": True,
        "policyId": "deepseek-v4-pro-flash-v1",
        "providerId": "deepseek",
        "modelId": "deepseek-v4-pro",
        "stages": [
            "scene-content",
            "scene-content:slide",
            "scene-content:quiz",
            "scene-content:interactive",
            "scene-content:pbl",
            "scene-actions",
        ],
        "thinking": {"mode": "disabled", "enabled": False},
    }
    FORMAL_RUNTIME_CONTRACT_VERSION = (
        "mira.openmaic.formal-runtime.v4-deepseek-professional"
    )
    FORMAL_PROFESSIONAL_MODEL_POLICY = {
        "schemaVersion": "mira.openmaic.professional-model-policy.v1",
        "policyId": "deepseek-v4-pro-flash-v1",
        "agentDriver": {
            "providerId": "deepseek",
            "modelId": "deepseek-v4-pro",
            "thinking": {"mode": "enabled", "enabled": True, "effort": "high"},
        },
        "coursewareCreator": {
            "providerId": "deepseek",
            "modelId": "deepseek-v4-pro",
            "thinking": {"mode": "disabled", "enabled": False},
        },
        "coursewareVerifier": {
            "providerId": "deepseek",
            "modelId": "deepseek-v4-flash",
            "thinking": {"mode": "disabled", "enabled": False},
        },
        "structuredScene": {
            "policyId": "deepseek-v4-pro-flash-v1",
            "providerId": "deepseek",
            "modelId": "deepseek-v4-pro",
            "thinking": {"mode": "disabled", "enabled": False},
        },
        "fallbackAllowed": False,
    }
    FORMAL_IMAGE_POLICY = FORMAL_IMAGE_POLICY
    FORMAL_VIDEO_POLICY = FORMAL_VIDEO_POLICY
    LEGACY_FORMAL_PROFESSIONAL_CREATION_POLICY = LEGACY_PROFESSIONAL_POLICY
    FORMAL_PROFESSIONAL_CREATION_POLICY = MULTISTATE_PROFESSIONAL_POLICY
    FORMAL_PROFESSIONAL_CREATION_RECEIPT_VERSION = (
        "mira.openmaic.professional-creation-receipt.v1"
    )
    FORMAL_RESEARCH_RECEIPT_VERSION = (
        "mira.openmaic.professional-research-receipt.v1"
    )
    LEGACY_FORMAL_GENERATION_OPTIONS = LEGACY_GENERATION_OPTIONS
    FORMAL_GENERATION_OPTIONS = generation_options(VIDEO_PROFESSIONAL_POLICY)
    FORMAL_PROFESSIONAL_RESEARCH_POLICY = {
        "schemaVersion": "mira.openmaic.professional-research.v1",
        "professionalWorkbench": {
            "upstreamVersion": "1.0.0",
            "primarySkillId": "mira-primary-courseware",
            "proModeAvailableToOperators": True,
            "availableToStudentRuntime": False,
        },
        "webSearch": {
            "defaultEnabled": True,
            "operatorOnly": False,
            "formalGenerationEnabled": True,
            "studentRuntimeEnabled": False,
            "maxCallsPerCourse": 4,
            "citationsRequired": True,
            "primarySourcesPreferred": True,
        },
    }
    FORMAL_AUDIO_LIFECYCLE_VERSION = (
        "mira.openmaic.formal-audio-lifecycle.v2"
    )
    FORMAL_SPEECH_TEXT_POLICY_VERSION = (
        "mira.learning.formal-speech-text.v2"
    )
    COURSEWARE_AUTHORITY = {
        "schemaVersion": "mira.openmaic.courseware-authority.v2-professional",
        "generationOwner": "openmaic",
        "providerInvocation": "professional_agent",
        "classroomCompilation": "professional_skill_workflow",
        "backendProviderCredentialsAccepted": False,
    }
    FORMAL_RUNTIME_CLASSROOM_CONTRACT = {
        "schemaVersion": FORMAL_RUNTIME_CONTRACT_VERSION,
        "scenePlanning": {
            "mode": "adaptive",
            "authority": "openmaic_professional_agent",
            "exactCountRequired": False,
            "allowedSceneTypes": ["slide", "quiz", "interactive", "pbl"],
            "requiredSceneTypes": ["slide", "quiz", "interactive"],
            "defaultDurationMinutes": {"min": 15, "max": 30},
            "scenesPerMinute": {"min": 1, "max": 2},
            "maxSceneCount": 60,
        },
        "roster": {"teacherCount": 1, "peerCount": 4},
        "speechRequiredForEveryScene": True,
        "speechActions": {
            "perScene": {"min": 1, "max": 20},
            "total": {"min": 1, "max": 240},
            "interactiveSpotlightRequired": False,
        },
        "slideSpotlight": {
            "minimumPerSlide": 1,
            "targetMustBeRenderable": True,
            "focusExplanationSequenceRequired": True,
            "consecutiveSpotlightsAllowed": True,
        },
        "distinctPeerDiscussions": 2,
        "teacherEvidence": ["spotlight", "widget_highlight"],
        "interactive": {
            "allowedWidgetTypes": [
                "simulation",
                "diagram",
                "code",
                "game",
                "visualization3d",
            ],
            "widgetConfigRequired": True,
            "productiveScriptRequired": True,
            "noopRejected": True,
            "fake3dRejected": True,
        },
        "whiteboardRequired": False,
    }
    FORMAL_GENERATION_POLICY = {
        "enforced": True,
        "policyId": FORMAL_RUNTIME_CONTRACT_VERSION,
        "idempotencyKey": "runtimeRequestId",
        "queryByRuntimeRequestId": True,
        "speechAudioGenerated": True,
        "coursewareAuthority": COURSEWARE_AUTHORITY,
        "professionalCreation": FORMAL_PROFESSIONAL_CREATION_POLICY,
        "studentRuntimeEvents": {
            "enforced": True,
            "schemaVersion": "mira.openmaic.student-runtime-events.v1",
            "classroomAuthoritySchema": (
                "mira.openmaic.runtime-event-authority.v1"
            ),
            "endpoint": "/mira/runtime-events",
            "authority": "mira-backend",
            "clientIdentityAccepted": False,
            "clientScoreAccepted": False,
        },
        "contract": FORMAL_RUNTIME_CLASSROOM_CONTRACT,
    }
    FORMAL_PROVIDER_READINESS_VERSION = (
        "mira.openmaic.formal-provider-readiness.v2"
    )
    FORMAL_PROVIDER_READINESS_JOB_VERSION = (
        "mira.openmaic.formal-provider-readiness-job.v2"
    )

    def __init__(
        self,
        base_url: str,
        *,
        timeout_seconds: float = 30,
        formal_audio_internal_token: str | None = None,
    ):
        normalized = str(base_url or "").strip().rstrip("/")
        parsed = urlparse(normalized)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("OpenMAIC runtime base URL must be HTTP(S).")
        if parsed.username or parsed.password or parsed.query or parsed.fragment:
            raise ValueError("OpenMAIC runtime base URL must not include credentials or query data.")
        if timeout_seconds <= 0 or timeout_seconds > 300:
            raise ValueError("OpenMAIC runtime timeout must be between 0 and 300 seconds.")
        self.base_url = normalized
        self.timeout_seconds = float(timeout_seconds)
        self._origin = (parsed.scheme, parsed.netloc)
        self._hostname = str(parsed.hostname or "").lower()
        self._port = int(parsed.port or (443 if parsed.scheme == "https" else 80))
        token = str(formal_audio_internal_token or "").strip()
        if token and (
            len(token) < 32
            or len(token) > 512
            or any(char.isspace() for char in token)
        ):
            raise ValueError(
                "OpenMAIC formal audio internal token must be 32-512 non-space characters."
            )
        self._internal_token = token
        self._formal_audio_internal_token = token

    def availability(self) -> dict[str, Any]:
        try:
            payload = self._request_json("GET", "/api/classroom?id=mira-health-probe")
        except OpenMaicFullRuntimeError as exc:
            # A 400/404 from the real classroom route proves the private app is
            # reachable; the probe classroom deliberately does not exist.
            if exc.status_code in {400, 404}:
                return {"available": True, "baseUrlConfigured": True}
            return {
                "available": False,
                "baseUrlConfigured": True,
                "error": exc.code,
            }
        return {"available": isinstance(payload, dict), "baseUrlConfigured": True}

    def sample_generation_readiness(self) -> dict[str, Any]:
        """Probe the exact non-secret runtime policy required by Mira's sample.

        Reachability alone is insufficient: without this preflight, an
        expensive classroom LLM job can run for minutes before deterministic
        speech synthesis discovers that Qwen3-TTS was never configured.
        """

        try:
            payload = self._request_json("GET", "/api/health")
        except OpenMaicFullRuntimeError as exc:
            return {
                "ready": False,
                "requiredVersion": self.SAMPLE_RUNTIME_VERSION,
                "reportedVersion": None,
                "tts": False,
                "runtimePolicy": None,
                "asr": False,
                "asrPolicy": None,
                "structuredScene": None,
                "error": exc.code,
            }

        capabilities = payload.get("capabilities")
        runtime_policy = payload.get("runtimePolicy")
        tts_policy = (
            runtime_policy.get("tts")
            if isinstance(runtime_policy, Mapping)
            else None
        )
        structured_scene_policy = (
            runtime_policy.get("structuredScene")
            if isinstance(runtime_policy, Mapping)
            else None
        )
        asr_policy = (
            runtime_policy.get("asr")
            if isinstance(runtime_policy, Mapping)
            else None
        )
        reported_version = _bounded_health_text(payload.get("version"), 32)
        observed_policy = (
            {
                "enforced": (
                    tts_policy.get("enforced")
                    if isinstance(tts_policy.get("enforced"), bool)
                    else None
                ),
                "providerId": _bounded_health_text(
                    tts_policy.get("providerId"), 64
                ),
                "modelId": _bounded_health_text(tts_policy.get("modelId"), 128),
                "voiceId": _bounded_health_text(tts_policy.get("voiceId"), 128),
            }
            if isinstance(tts_policy, Mapping)
            else None
        )
        tts_ready = (
            isinstance(capabilities, Mapping)
            and capabilities.get("tts") is True
        )
        asr_ready = (
            isinstance(capabilities, Mapping)
            and capabilities.get("asr") is True
        )
        observed_asr_policy = (
            {
                "enforced": (
                    asr_policy.get("enforced")
                    if isinstance(asr_policy.get("enforced"), bool)
                    else None
                ),
                "providerId": _bounded_health_text(
                    asr_policy.get("providerId"), 64
                ),
                "modelId": _bounded_health_text(
                    asr_policy.get("modelId"), 128
                ),
                "fallbackAllowed": (
                    asr_policy.get("fallbackAllowed")
                    if isinstance(asr_policy.get("fallbackAllowed"), bool)
                    else None
                ),
            }
            if isinstance(asr_policy, Mapping)
            else None
        )
        observed_structured_scene = _bounded_structured_scene_policy(
            structured_scene_policy
        )
        ready = bool(
            payload.get("success") is True
            and payload.get("status") == "ok"
            and reported_version == self.SAMPLE_RUNTIME_VERSION
            and tts_ready
            and asr_ready
            and isinstance(tts_policy, Mapping)
            and dict(tts_policy) == self.SAMPLE_TTS_POLICY
            and isinstance(asr_policy, Mapping)
            and dict(asr_policy) == self.SAMPLE_ASR_POLICY
            and isinstance(structured_scene_policy, Mapping)
            and dict(structured_scene_policy)
            == self.SAMPLE_STRUCTURED_SCENE_POLICY
        )
        return {
            "ready": ready,
            "requiredVersion": self.SAMPLE_RUNTIME_VERSION,
            "reportedVersion": reported_version,
            "tts": tts_ready,
            "runtimePolicy": observed_policy,
            "asr": asr_ready,
            "asrPolicy": observed_asr_policy,
            "structuredScene": observed_structured_scene,
            "error": None if ready else "openmaic_sample_generation_not_ready",
        }

    def formal_generation_readiness(self) -> dict[str, Any]:
        """Verify the private Pro Agent, web research and formal policy gate."""

        try:
            payload = self._request_json(
                "GET", "/api/health?scope=formal-generation"
            )
        except OpenMaicFullRuntimeError as exc:
            return {
                "ready": False,
                "contractVersion": self.FORMAL_RUNTIME_CONTRACT_VERSION,
                "requiredVersion": self.FORMAL_RUNTIME_VERSION,
                "reportedVersion": None,
                "capabilities": None,
                "policy": None,
                "professionalResearch": None,
                "modelPolicy": None,
                "webSearch": None,
                "reason": "无法读取正式生成配置；尚未发起课程或搜索调用。",
                "error": exc.code,
            }
        runtime_policy = payload.get("runtimePolicy")
        capabilities = payload.get("capabilities")
        formal_policy = (
            runtime_policy.get("formalGeneration")
            if isinstance(runtime_policy, Mapping)
            else None
        )
        professional_research = (
            runtime_policy.get("professionalResearch")
            if isinstance(runtime_policy, Mapping)
            else None
        )
        model_policy = (
            runtime_policy.get("modelPolicy")
            if isinstance(runtime_policy, Mapping)
            else None
        )
        web_search = runtime_policy.get("webSearch") if isinstance(runtime_policy, Mapping) else None
        search_configured = bool(
            isinstance(web_search, Mapping)
            and set(web_search) == {"schemaVersion", "providerId", "productionMode", "formalProductionConfigured", "verification"}
            and web_search.get("schemaVersion") == "mira.openmaic.web-search-production-config.v1"
            and (web_search.get("providerId"), web_search.get("productionMode"))
                in (("brave", "brave_api"), ("baidu", "baidu_api"))
            and web_search.get("formalProductionConfigured") is True
            and web_search.get("verification") == "configuration_only"
        )
        reported_version = str(payload.get("version") or "") or None
        ready = bool(
            payload.get("success") is True
            and payload.get("status") == "ok"
            and reported_version == self.FORMAL_RUNTIME_VERSION
            and isinstance(capabilities, Mapping)
            and capabilities.get("formalGeneration") is True
            and capabilities.get("professionalAgent") is True
            and capabilities.get("webSearch") is True
            and search_configured
            and capabilities.get("speechAudioGeneration") is True
            and isinstance(formal_policy, Mapping)
            and _canonical_sha256(dict(formal_policy)) == _canonical_sha256(self.FORMAL_GENERATION_POLICY)
            and isinstance(professional_research, Mapping)
            and dict(professional_research)
            == self.FORMAL_PROFESSIONAL_RESEARCH_POLICY
            and isinstance(model_policy, Mapping)
            and dict(model_policy) == self.FORMAL_PROFESSIONAL_MODEL_POLICY
        )
        return {
            "ready": ready,
            "contractVersion": self.FORMAL_RUNTIME_CONTRACT_VERSION,
            "requiredVersion": self.FORMAL_RUNTIME_VERSION,
            "reportedVersion": reported_version,
            "capabilities": (
                dict(capabilities)
                if isinstance(capabilities, Mapping)
                else None
            ),
            "policy": dict(formal_policy) if isinstance(formal_policy, Mapping) else None,
            "professionalResearch": (
                dict(professional_research)
                if isinstance(professional_research, Mapping)
                else None
            ),
            "modelPolicy": (
                dict(model_policy) if isinstance(model_policy, Mapping) else None
            ),
            "webSearch": ({key: web_search.get(key) for key in ("schemaVersion", "providerId", "productionMode", "formalProductionConfigured", "verification")} if isinstance(web_search, Mapping) else None),
            "reason": (
                "正式搜索 API 已配置；此检查未验证实际联网能力。" if ready else
                "Runtime 尚未报告正式搜索配置，请先更新 Runtime；未发起付费生成。" if not isinstance(web_search, Mapping) else
                "正式课程需要配置百度搜索或 Brave Search API Key，并选择对应供应商；公共网页搜索不满足生产配置要求。配置检查不代表已验证联网。" if not search_configured else
                "正式课堂的模型、版本或生成合同尚未就绪。"
            ),
            "error": None if ready else "openmaic_formal_search_configuration_unreported" if not isinstance(web_search, Mapping) else "openmaic_formal_search_api_not_configured" if not search_configured else "openmaic_formal_generation_not_ready",
        }

    def formal_generation_provider_canary(self) -> dict[str, Any]:
        """Make one bounded real call to the pinned formal generation model."""

        try:
            payload = self._request_json(
                "POST",
                "/api/verify-model",
                {"model": "deepseek:deepseek-v4-pro"},
            )
        except OpenMaicFullRuntimeError as exc:
            return {
                "ready": False,
                "providerId": "deepseek",
                "modelId": "deepseek-v4-pro",
                "error": exc.code,
            }
        ready = bool(
            payload.get("success") is True
            and payload.get("message") == "Connection successful"
            and str(payload.get("response") or "").strip()
        )
        return {
            "ready": ready,
            "providerId": "deepseek",
            "modelId": "deepseek-v4-pro",
            "error": None if ready else "openmaic_formal_provider_canary_failed",
        }

    def start_formal_audio_tts(
        self,
        *,
        request_id: str,
        classroom_id: str,
        classroom_content_sha256: str,
        subject: str,
        teacher_profile_id: str,
        teacher_profile_version: int,
        teacher_profile_sha256: str,
        teacher_gender: str,
        scene_id: str,
        scene_order: int,
        action_id: str,
        narration_segment_id: str,
        text: str,
        text_sha256: str,
        paid_budget: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._formal_audio_identity_payload(
            request_id=request_id,
            classroom_id=classroom_id,
            classroom_content_sha256=classroom_content_sha256,
            subject=subject,
            teacher_profile_id=teacher_profile_id,
            teacher_profile_version=teacher_profile_version,
            teacher_profile_sha256=teacher_profile_sha256,
            teacher_gender=teacher_gender,
            scene_id=scene_id,
            scene_order=scene_order,
            action_id=action_id,
            narration_segment_id=narration_segment_id,
        )
        normalized_text = str(text or "").strip()
        if not normalized_text or len(normalized_text) > 4_000:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_audio_text", "正式课堂讲解文本无效", status_code=400
            )
        actual_text_sha256 = hashlib.sha256(normalized_text.encode("utf-8")).hexdigest()
        if str(text_sha256 or "") != actual_text_sha256:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_audio_text_hash", "正式课堂讲解文本校验失败", status_code=400
            )
        payload.update({"text": normalized_text, "textSha256": actual_text_sha256})
        response = self._request_formal_audio_json(
            "POST", "/api/mira/formal-audio/tts", payload, paid_budget=paid_budget
        )
        return self._validate_formal_tts_response(response, request_id=request_id)

    def get_formal_audio_tts(self, request_id: str) -> dict[str, Any]:
        normalized = self._formal_audio_request_id(request_id)
        response = self._request_formal_audio_json(
            "GET", f"/api/mira/formal-audio/tts?requestId={quote(normalized)}"
        )
        return self._validate_formal_tts_response(response, request_id=normalized)

    def download_formal_audio_tts(
        self, request_id: str, *, expected_sha256: str
    ) -> bytes:
        normalized = self._formal_audio_request_id(request_id)
        expected = str(expected_sha256 or "")
        if re.fullmatch(r"[0-9a-f]{64}", expected) is None:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_audio_hash", "正式课堂语音校验值无效", status_code=400
            )
        path = (
            "/api/mira/formal-audio/tts?requestId="
            f"{quote(normalized)}&download=1"
        )
        target = urljoin(f"{self.base_url}/", path.lstrip("/"))
        request = Request(
            target,
            headers={"Accept": "audio/wav", **self._formal_audio_headers()},
            method="GET",
        )
        try:
            with urlopen(
                request, timeout=self.FORMAL_AUDIO_TIMEOUT_SECONDS
            ) as response:
                final = urlparse(response.geturl())
                if (final.scheme, final.netloc) != self._origin:
                    raise OpenMaicFullRuntimeError(
                        "formal_audio_redirect_not_allowed",
                        "OpenMAIC 语音下载返回了不安全的跳转",
                    )
                mime_type = str(response.headers.get("Content-Type") or "").strip().lower()
                content_length = str(response.headers.get("Content-Length") or "")
                if mime_type != "audio/wav" or not content_length.isdigit():
                    raise OpenMaicFullRuntimeError(
                        "invalid_formal_audio_download", "OpenMAIC 语音下载格式无效"
                    )
                declared = int(content_length)
                if not 44 <= declared <= self.FORMAL_AUDIO_MAX_BYTES:
                    raise OpenMaicFullRuntimeError(
                        "formal_audio_download_too_large", "OpenMAIC 语音下载大小无效"
                    )
                raw = response.read(self.FORMAL_AUDIO_MAX_BYTES + 1)
        except OpenMaicFullRuntimeError:
            raise
        except HTTPError as exc:
            raise OpenMaicFullRuntimeError(
                "formal_audio_download_rejected", "OpenMAIC 语音下载失败",
                status_code=int(getattr(exc, "code", 502) or 502),
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OpenMaicFullRuntimeError(
                "formal_audio_download_ambiguous", "OpenMAIC 语音下载结果不确定",
                status_code=503,
            ) from exc
        if len(raw) != declared or len(raw) > self.FORMAL_AUDIO_MAX_BYTES:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_audio_download", "OpenMAIC 语音下载不完整"
            )
        if hashlib.sha256(raw).hexdigest() != expected:
            raise OpenMaicFullRuntimeError(
                "formal_audio_download_hash_mismatch", "OpenMAIC 语音下载校验失败"
            )
        return raw

    def start_formal_audio_asr(
        self,
        *,
        request_id: str,
        tts_request_id: str,
        classroom_id: str,
        classroom_content_sha256: str,
        subject: str,
        teacher_profile_id: str,
        teacher_profile_version: int,
        teacher_profile_sha256: str,
        teacher_gender: str,
        scene_id: str,
        scene_order: int,
        action_id: str,
        narration_segment_id: str,
        audio_sha256: str,
        paid_budget: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = self._formal_audio_identity_payload(
            request_id=request_id,
            classroom_id=classroom_id,
            classroom_content_sha256=classroom_content_sha256,
            subject=subject,
            teacher_profile_id=teacher_profile_id,
            teacher_profile_version=teacher_profile_version,
            teacher_profile_sha256=teacher_profile_sha256,
            teacher_gender=teacher_gender,
            scene_id=scene_id,
            scene_order=scene_order,
            action_id=action_id,
            narration_segment_id=narration_segment_id,
        )
        payload["ttsRequestId"] = self._formal_audio_request_id(tts_request_id)
        if re.fullmatch(r"[0-9a-f]{64}", str(audio_sha256 or "")) is None:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_audio_hash", "正式课堂语音校验值无效", status_code=400
            )
        payload["audioSha256"] = str(audio_sha256)
        response = self._request_formal_audio_json(
            "POST", "/api/mira/formal-audio/asr", payload, paid_budget=paid_budget
        )
        return self._validate_formal_asr_response(
            response, request_id=request_id, require_ephemeral_transcript=True
        )

    def get_formal_audio_asr(self, request_id: str) -> dict[str, Any]:
        normalized = self._formal_audio_request_id(request_id)
        response = self._request_formal_audio_json(
            "GET", f"/api/mira/formal-audio/asr?requestId={quote(normalized)}"
        )
        return self._validate_formal_asr_response(
            response, request_id=normalized, require_ephemeral_transcript=False
        )

    def start_formal_provider_readiness(self, **evidence: Any) -> dict[str, Any]:
        """Run the exact server-owned five-call publication readiness gate.

        Provider/model/voice configuration intentionally does not cross this
        boundary.  The Runtime owns those choices; this client only binds the
        immutable classroom, Task14 audio and route-session evidence.
        """

        payload = self._formal_provider_readiness_payload(evidence)
        response = self._request_formal_audio_json(
            "POST", "/api/mira/formal-provider-readiness", payload
        )
        return self._validate_formal_provider_readiness_response(
            response,
            request_id=payload["requestId"],
            expected_request_sha256=_canonical_sha256(payload),
        )

    def get_formal_provider_readiness(self, request_id: str) -> dict[str, Any]:
        """Observe an existing readiness job without dispatching Provider work."""

        normalized = _formal_readiness_identifier(request_id, max_length=255)
        response = self._request_formal_audio_json(
            "GET",
            "/api/mira/formal-provider-readiness?requestId="
            + quote(normalized, safe=""),
        )
        return self._validate_formal_provider_readiness_response(
            response,
            request_id=normalized,
            expected_request_sha256=None,
        )

    @classmethod
    def _formal_provider_readiness_payload(
        cls, evidence: Mapping[str, Any]
    ) -> dict[str, Any]:
        required = {
            "schemaVersion",
            "requestId",
            "buildItemId",
            "releaseId",
            "gradeCode",
            "targetFingerprint",
            "runtimeClassroomId",
            "runtimeRequestId",
            "upstreamClassroomId",
            "classroomContentSha256",
            "audioJobTerminalReceiptSha256",
            "validation",
            "routeSession",
        }
        if set(evidence) != required:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_request",
                "正式课程 Provider 就绪证据无效",
                status_code=400,
            )
        validation = evidence.get("validation")
        route_session = evidence.get("routeSession")
        if (
            not isinstance(validation, Mapping)
            or set(validation)
            != {
                "subject",
                "sceneOrder",
                "ttsRequestId",
                "audioSha256",
                "machineReceiptSha256",
            }
            or not isinstance(route_session, Mapping)
            or set(route_session)
            != {
                "schemaVersion",
                "conversationProbeId",
                "receiptSha256",
                "providerCall",
            }
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_request",
                "正式课程 Provider 就绪证据无效",
                status_code=400,
            )
        identifier_fields = (
            "requestId",
            "buildItemId",
            "releaseId",
            "runtimeClassroomId",
            "runtimeRequestId",
            "upstreamClassroomId",
        )
        identifiers_valid = all(
            _formal_readiness_identifier_or_none(
                evidence.get(field), max_length=255
            )
            is not None
            for field in identifier_fields
        )
        hashes_valid = all(
            _sha256_or_none(evidence.get(field)) is not None
            for field in (
                "targetFingerprint",
                "classroomContentSha256",
                "audioJobTerminalReceiptSha256",
            )
        ) and all(
            _sha256_or_none(validation.get(field)) is not None
            for field in ("audioSha256", "machineReceiptSha256")
        )
        subject = str(validation.get("subject") or "")
        scene_order = validation.get("sceneOrder")
        if (
            evidence.get("schemaVersion")
            != cls.FORMAL_PROVIDER_READINESS_VERSION
            or not identifiers_valid
            or re.fullmatch(
                r"[a-z][a-z0-9_]{0,63}",
                str(evidence.get("gradeCode") or ""),
            )
            is None
            or not hashes_valid
            or subject not in {"chinese", "math", "english"}
            or type(scene_order) is not int
            or not 0 <= scene_order <= 239
            or _formal_readiness_identifier_or_none(
                validation.get("ttsRequestId"), max_length=255
            )
            is None
            or route_session.get("schemaVersion")
            != "mira.openmaic.conversation-proof.v1"
            or _formal_readiness_identifier_or_none(
                route_session.get("conversationProbeId"), max_length=255
            )
            is None
            or _sha256_or_none(route_session.get("receiptSha256")) is None
            or route_session.get("providerCall") is not False
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_request",
                "正式课程 Provider 就绪证据无效",
                status_code=400,
            )
        return {
            "schemaVersion": cls.FORMAL_PROVIDER_READINESS_VERSION,
            **{
                field: str(evidence[field])
                for field in identifier_fields
            },
            "gradeCode": str(evidence["gradeCode"]),
            "targetFingerprint": str(evidence["targetFingerprint"]),
            "classroomContentSha256": str(
                evidence["classroomContentSha256"]
            ),
            "audioJobTerminalReceiptSha256": str(
                evidence["audioJobTerminalReceiptSha256"]
            ),
            "validation": {
                "subject": subject,
                "sceneOrder": int(scene_order),
                "ttsRequestId": str(validation["ttsRequestId"]),
                "audioSha256": str(validation["audioSha256"]),
                "machineReceiptSha256": str(
                    validation["machineReceiptSha256"]
                ),
            },
            "routeSession": {
                "schemaVersion": "mira.openmaic.conversation-proof.v1",
                "conversationProbeId": str(
                    route_session["conversationProbeId"]
                ),
                "receiptSha256": str(route_session["receiptSha256"]),
                "providerCall": False,
            },
        }

    @classmethod
    def _validate_formal_provider_readiness_response(
        cls,
        response: Mapping[str, Any],
        *,
        request_id: str,
        expected_request_sha256: str | None,
    ) -> dict[str, Any]:
        if _contains_formal_readiness_raw_payload(response):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 就绪返回包含不允许的数据",
            )
        status = str(response.get("state") or "")
        request_sha256 = _sha256_or_none(response.get("requestSha256"))
        validation = response.get("validation")
        route_proof = response.get("routeSessionProof")
        calls = response.get("calls")
        attempted = response.get("providerAttemptedCount")
        passed = response.get("providerPassedCount")
        if (
            response.get("success") is not True
            or response.get("schemaVersion")
            != cls.FORMAL_PROVIDER_READINESS_JOB_VERSION
            or str(response.get("requestId") or "") != request_id
            or request_sha256 is None
            or (
                expected_request_sha256 is not None
                and request_sha256 != expected_request_sha256
            )
            or status
            not in {"running", "auto_validated", "failed", "ambiguous"}
            or type(attempted) is not int
            or type(passed) is not int
            or not 0 <= passed <= attempted <= 5
            or not isinstance(validation, Mapping)
            or not isinstance(route_proof, Mapping)
            or not isinstance(calls, list)
            or len(calls) != attempted
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 就绪返回无效",
            )
        immutable_identifiers = (
            "buildItemId",
            "releaseId",
            "runtimeClassroomId",
            "runtimeRequestId",
            "upstreamClassroomId",
        )
        if any(
            _formal_readiness_identifier_or_none(
                response.get(field), max_length=255
            )
            is None
            for field in immutable_identifiers
        ) or any(
            _sha256_or_none(response.get(field)) is None
            for field in (
                "targetFingerprint",
                "classroomContentSha256",
                "audioJobTerminalReceiptSha256",
            )
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 就绪身份无效",
            )
        grade_code = str(response.get("gradeCode") or "")
        if re.fullmatch(r"[a-z][a-z0-9_]{0,63}", grade_code) is None:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 就绪身份无效",
            )
        normalized_validation = cls._validate_formal_readiness_validation(
            validation
        )
        normalized_route = cls._validate_formal_readiness_route_proof(
            route_proof
        )
        reconstructed_request = {
            "schemaVersion": cls.FORMAL_PROVIDER_READINESS_VERSION,
            "requestId": request_id,
            **{
                field: str(response[field])
                for field in immutable_identifiers
            },
            "gradeCode": grade_code,
            "targetFingerprint": str(response["targetFingerprint"]),
            "classroomContentSha256": str(
                response["classroomContentSha256"]
            ),
            "audioJobTerminalReceiptSha256": str(
                response["audioJobTerminalReceiptSha256"]
            ),
            "validation": normalized_validation,
            "routeSession": normalized_route,
        }
        if request_sha256 != _canonical_sha256(reconstructed_request):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 就绪请求身份无法核对",
            )
        normalized_calls = cls._validate_formal_readiness_calls(
            calls,
            subject=normalized_validation["subject"],
        )
        actual_passed = sum(
            call["state"] == "passed" for call in normalized_calls
        )
        if actual_passed != passed:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 就绪计数无效",
            )
        proof = response.get("providerProof")
        provider_receipt_sha256 = None
        if proof is not None:
            provider_receipt_sha256 = cls._validate_formal_readiness_proof(
                proof,
                calls=normalized_calls,
                attempted=attempted,
                passed=passed,
            )
        done = response.get("done")
        if (
            (status == "running" and (done is not False or proof is not None))
            or (
                status != "running"
                and (done is not True or provider_receipt_sha256 is None)
            )
            or (
                status == "auto_validated"
                and (
                    attempted != 5
                    or passed != 5
                    or any(call["state"] != "passed" for call in normalized_calls)
                )
            )
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 就绪终态无效",
            )
        return {
            "requestId": request_id,
            "requestSha256": request_sha256,
            "status": status,
            **{
                field: str(response[field])
                for field in immutable_identifiers
            },
            "gradeCode": grade_code,
            "targetFingerprint": str(response["targetFingerprint"]),
            "classroomContentSha256": str(
                response["classroomContentSha256"]
            ),
            "audioJobTerminalReceiptSha256": str(
                response["audioJobTerminalReceiptSha256"]
            ),
            "validation": normalized_validation,
            "routeSessionProof": normalized_route,
            "providerAttemptedCount": attempted,
            "providerPassedCount": passed,
            "calls": normalized_calls,
            "providerReceiptSha256": provider_receipt_sha256,
            "safeErrorCode": (
                str(response.get("safeErrorCode"))[:128]
                if status in {"failed", "ambiguous"}
                and response.get("safeErrorCode")
                else None
            ),
        }

    @staticmethod
    def _validate_formal_readiness_validation(
        value: Mapping[str, Any]
    ) -> dict[str, Any]:
        if set(value) != {
            "subject",
            "sceneOrder",
            "ttsRequestId",
            "audioSha256",
            "machineReceiptSha256",
        }:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 就绪音频证据无效",
            )
        subject = str(value.get("subject") or "")
        scene_order = value.get("sceneOrder")
        tts_request_id = _formal_readiness_identifier_or_none(
            value.get("ttsRequestId"), max_length=255
        )
        audio_sha256 = _sha256_or_none(value.get("audioSha256"))
        machine_receipt_sha256 = _sha256_or_none(
            value.get("machineReceiptSha256")
        )
        if (
            subject not in {"chinese", "math", "english"}
            or type(scene_order) is not int
            or not 0 <= scene_order <= 239
            or tts_request_id is None
            or audio_sha256 is None
            or machine_receipt_sha256 is None
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 就绪音频证据无效",
            )
        return {
            "subject": subject,
            "sceneOrder": scene_order,
            "ttsRequestId": tts_request_id,
            "audioSha256": audio_sha256,
            "machineReceiptSha256": machine_receipt_sha256,
        }

    @staticmethod
    def _validate_formal_readiness_route_proof(
        value: Mapping[str, Any]
    ) -> dict[str, Any]:
        if set(value) != {
            "schemaVersion",
            "conversationProbeId",
            "receiptSha256",
            "providerCall",
        }:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC 课堂路由证明无效",
            )
        probe_id = _formal_readiness_identifier_or_none(
            value.get("conversationProbeId"), max_length=255
        )
        receipt_sha256 = _sha256_or_none(value.get("receiptSha256"))
        if (
            value.get("schemaVersion")
            != "mira.openmaic.conversation-proof.v1"
            or probe_id is None
            or receipt_sha256 is None
            or value.get("providerCall") is not False
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC 课堂路由证明无效",
            )
        return {
            "schemaVersion": "mira.openmaic.conversation-proof.v1",
            "conversationProbeId": probe_id,
            "receiptSha256": receipt_sha256,
            "providerCall": False,
        }

    @classmethod
    def _validate_formal_readiness_calls(
        cls,
        values: list[Any],
        *,
        subject: str,
    ) -> list[dict[str, Any]]:
        language = "en-US" if subject == "english" else "zh-CN"
        expected = [
            (
                1,
                "deepseek_text",
                None,
                "deepseek",
                "deepseek-v4-pro",
                None,
                None,
            ),
            (
                2,
                "qwen_asr",
                subject,
                "qwen-asr",
                "qwen3-asr-flash",
                None,
                language,
            ),
            (
                3,
                "qwen_tts",
                "chinese",
                "qwen-tts",
                "qwen3-tts-flash",
                "Serena",
                "zh-CN",
            ),
            (
                4,
                "qwen_tts",
                "math",
                "qwen-tts",
                "qwen3-tts-flash",
                "Ethan",
                "zh-CN",
            ),
            (
                5,
                "qwen_tts",
                "english",
                "qwen-tts",
                "qwen3-tts-flash",
                "Jennifer",
                "en-US",
            ),
        ]
        normalized: list[dict[str, Any]] = []
        allowed = {
            "callOrdinal",
            "kind",
            "subject",
            "providerId",
            "modelId",
            "voiceId",
            "languageCode",
            "fallbackUsed",
            "providerCall",
            "requestSha256",
            "state",
            "attemptedAt",
            "completedAt",
            "responseSha256",
            "safeErrorCode",
        }
        for index, raw in enumerate(values):
            if not isinstance(raw, Mapping) or not set(raw).issubset(allowed):
                raise OpenMaicFullRuntimeError(
                    "invalid_formal_provider_readiness_response",
                    "OpenMAIC Provider 调用证明无效",
                )
            ordinal, kind, call_subject, provider_id, model_id, voice_id, language_code = expected[index]
            state = str(raw.get("state") or "")
            attempted_at = str(raw.get("attemptedAt") or "")
            completed_at = raw.get("completedAt")
            response_sha256 = _sha256_or_none(raw.get("responseSha256"))
            safe_error_code = str(raw.get("safeErrorCode") or "")
            subject_matches = (
                (call_subject is None and "subject" not in raw)
                or raw.get("subject") == call_subject
            )
            voice_matches = (
                (voice_id is None and "voiceId" not in raw)
                or raw.get("voiceId") == voice_id
            )
            language_matches = (
                (language_code is None and "languageCode" not in raw)
                or raw.get("languageCode") == language_code
            )
            terminal = state in {"passed", "failed", "ambiguous"}
            if (
                raw.get("callOrdinal") != ordinal
                or raw.get("kind") != kind
                or not subject_matches
                or raw.get("providerId") != provider_id
                or raw.get("modelId") != model_id
                or not voice_matches
                or not language_matches
                or raw.get("fallbackUsed") is not False
                or raw.get("providerCall") is not True
                or _sha256_or_none(raw.get("requestSha256")) is None
                or state not in {"attempted", "passed", "failed", "ambiguous"}
                or not attempted_at
                or len(attempted_at) > 64
                or (
                    terminal
                    and (
                        not isinstance(completed_at, str)
                        or not completed_at
                        or len(completed_at) > 64
                        or response_sha256 is None
                    )
                )
                or (
                    not terminal
                    and (
                        completed_at is not None
                        or raw.get("responseSha256") is not None
                    )
                )
                or (
                    state in {"failed", "ambiguous"}
                    and (not safe_error_code or len(safe_error_code) > 128)
                )
                or (state in {"attempted", "passed"} and safe_error_code)
            ):
                raise OpenMaicFullRuntimeError(
                    "invalid_formal_provider_readiness_response",
                    "OpenMAIC Provider 调用证明无效",
                )
            item: dict[str, Any] = {
                "callOrdinal": ordinal,
                "kind": kind,
                **({"subject": call_subject} if call_subject else {}),
                "providerId": provider_id,
                "modelId": model_id,
                **({"voiceId": voice_id} if voice_id else {}),
                **({"languageCode": language_code} if language_code else {}),
                "fallbackUsed": False,
                "providerCall": True,
                "requestSha256": str(raw["requestSha256"]),
                "state": state,
                "attemptedAt": attempted_at,
                **({"completedAt": str(completed_at)} if terminal else {}),
                **(
                    {"responseSha256": str(response_sha256)}
                    if terminal
                    else {}
                ),
                **(
                    {"safeErrorCode": safe_error_code}
                    if state in {"failed", "ambiguous"}
                    else {}
                ),
            }
            normalized.append(item)
        return normalized

    @classmethod
    def _validate_formal_readiness_proof(
        cls,
        value: Any,
        *,
        calls: list[dict[str, Any]],
        attempted: int,
        passed: int,
    ) -> str:
        if not isinstance(value, Mapping) or set(value) != {
            "schemaVersion",
            "providerCall",
            "expectedCallCount",
            "attemptedCallCount",
            "passedCallCount",
            "calls",
            "receiptSha256",
        }:
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 发布证明无效",
            )
        proof_calls = value.get("calls")
        normalized_proof_calls = (
            cls._validate_formal_readiness_calls(
                proof_calls, subject=(calls[1]["subject"] if len(calls) > 1 else "math")
            )
            if isinstance(proof_calls, list)
            else None
        )
        safe = {
            "schemaVersion": cls.FORMAL_PROVIDER_READINESS_VERSION,
            "providerCall": attempted > 0,
            "expectedCallCount": 5,
            "attemptedCallCount": attempted,
            "passedCallCount": passed,
            "calls": calls,
        }
        receipt_sha256 = _sha256_or_none(value.get("receiptSha256"))
        if (
            value.get("schemaVersion")
            != cls.FORMAL_PROVIDER_READINESS_VERSION
            or value.get("providerCall") != (attempted > 0)
            or value.get("expectedCallCount") != 5
            or value.get("attemptedCallCount") != attempted
            or value.get("passedCallCount") != passed
            or normalized_proof_calls != calls
            or receipt_sha256 != _canonical_sha256(safe)
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_provider_readiness_response",
                "OpenMAIC Provider 发布证明无效",
            )
        return str(receipt_sha256)

    @classmethod
    def _formal_audio_identity_payload(
        cls,
        *,
        request_id: str,
        classroom_id: str,
        classroom_content_sha256: str,
        subject: str,
        teacher_profile_id: str,
        teacher_profile_version: int,
        teacher_profile_sha256: str,
        teacher_gender: str,
        scene_id: str,
        scene_order: int,
        action_id: str,
        narration_segment_id: str,
    ) -> dict[str, Any]:
        identities = {
            "requestId": cls._formal_audio_request_id(request_id),
            "classroomId": str(classroom_id or "").strip(),
            "teacherProfileId": str(teacher_profile_id or "").strip(),
            "sceneId": str(scene_id or "").strip(),
            "actionId": str(action_id or "").strip(),
            "narrationSegmentId": str(narration_segment_id or "").strip(),
        }
        if any(
            not _safe_identifier(value, max_length=128)
            for value in identities.values()
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_audio_identity", "正式课堂语音身份无效", status_code=400
            )
        if (
            str(subject or "") not in {"chinese", "math", "english"}
            or str(teacher_gender or "") not in {"female", "male"}
            or type(teacher_profile_version) is not int
            or teacher_profile_version != 2
            or type(scene_order) is not int
            or not 0 <= scene_order <= 239
            or re.fullmatch(r"[0-9a-f]{64}", str(classroom_content_sha256 or "")) is None
            or re.fullmatch(r"[0-9a-f]{64}", str(teacher_profile_sha256 or "")) is None
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_audio_identity", "正式课堂语音身份无效", status_code=400
            )
        return {
            **identities,
            "classroomContentSha256": str(classroom_content_sha256),
            "subject": str(subject),
            "teacherProfileVersion": teacher_profile_version,
            "teacherProfileSha256": str(teacher_profile_sha256),
            "teacherGender": str(teacher_gender),
            "sceneOrder": scene_order,
        }

    @staticmethod
    def _formal_audio_request_id(value: str) -> str:
        normalized = str(value or "").strip()
        if not _safe_identifier(normalized, max_length=128):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_audio_request_id", "正式课堂语音请求编号无效", status_code=400
            )
        return normalized

    @staticmethod
    def _validate_formal_tts_response(
        response: Mapping[str, Any], *, request_id: str
    ) -> dict[str, Any]:
        status = str(response.get("state") or "")
        digest = str(response.get("audioSha256") or "")
        if (
            response.get("success") is not True
            or str(response.get("requestId") or "") != request_id
            or status not in {"running", "succeeded", "failed", "ambiguous"}
            or (status == "succeeded" and (
                re.fullmatch(r"[0-9a-f]{64}", digest) is None
                or response.get("mimeType") != "audio/wav"
            ))
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_audio_response", "OpenMAIC 正式语音返回无效"
            )
        return {
            "requestId": request_id,
            "status": status,
            "audioSha256": digest or None,
            "mimeType": response.get("mimeType") if status == "succeeded" else None,
        }

    @staticmethod
    def _validate_formal_asr_response(
        response: Mapping[str, Any], *, request_id: str,
        require_ephemeral_transcript: bool,
    ) -> dict[str, Any]:
        status = str(response.get("state") or "")
        transcript = response.get("transcript")
        transcript_sha256 = str(response.get("transcriptSha256") or "")
        succeeded_payload_valid = bool(
            re.fullmatch(r"[0-9a-f]{64}", transcript_sha256) is not None
            and (
                (
                    require_ephemeral_transcript
                    and isinstance(transcript, str)
                    and bool(transcript.strip())
                    and len(transcript) <= 8_000
                    and hashlib.sha256(transcript.encode("utf-8")).hexdigest()
                    == transcript_sha256
                )
                or (
                    not require_ephemeral_transcript
                    and transcript is None
                )
            )
        )
        if (
            response.get("success") is not True
            or str(response.get("requestId") or "") != request_id
            or status not in {"running", "succeeded", "failed", "ambiguous"}
            or (status == "succeeded" and not succeeded_payload_valid)
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_formal_asr_response", "OpenMAIC 正式语音识别返回无效"
            )
        return {
            "requestId": request_id,
            "status": status,
            "transcript": (
                transcript
                if status == "succeeded" and require_ephemeral_transcript
                else None
            ),
            "transcriptSha256": transcript_sha256 or None,
            "completionUsable": bool(
                status == "succeeded" and require_ephemeral_transcript
            ),
        }

    def _formal_audio_headers(self) -> dict[str, str]:
        if (
            self._origin[0] != "http"
            or
            self._hostname not in {"127.0.0.1", "localhost", "::1"}
            or not self._formal_audio_internal_token
        ):
            raise OpenMaicFullRuntimeError(
                "formal_audio_private_authority_missing",
                "OpenMAIC 正式语音私有授权未配置",
                status_code=503,
            )
        return {
            "X-Mira-Internal-Token": self._formal_audio_internal_token,
            "X-Forwarded-For": "127.0.0.1",
            "X-Forwarded-Host": self._origin[1],
            "X-Forwarded-Port": str(self._port),
            "X-Forwarded-Proto": self._origin[0],
        }

    def _formal_generation_headers(self) -> dict[str, str]:
        if not self._internal_token:
            raise OpenMaicFullRuntimeError(
                "formal_generation_private_authority_missing",
                "OpenMAIC 正式课件私有授权未配置",
                status_code=503,
            )
        return {"X-Mira-Internal-Token": self._internal_token}

    def _request_formal_audio_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        paid_budget: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        headers = self._formal_audio_headers()
        if paid_budget is not None:
            if (set(paid_budget) != {"schemaVersion", "authorizationId", "required"}
                or paid_budget.get("schemaVersion") != "mira.learning.paid-budget-binding.v1"
                or paid_budget.get("required") is not True
                or re.fullmatch(r"[a-f0-9]{64}", str(paid_budget.get("authorizationId") or "")) is None):
                raise OpenMaicFullRuntimeError("invalid_paid_budget_binding", "课程生产预算授权无效", status_code=400)
            headers.update({"X-Mira-Paid-Budget-Required": "1",
                "X-Mira-Paid-Budget-Authorization": paid_budget["authorizationId"]})
        return self._request_json(
            method,
            path,
            body,
            extra_headers=headers,
            timeout_seconds=self.FORMAL_AUDIO_REQUEST_TIMEOUT_SECONDS,
        )

    def start_generation(
        self,
        *,
        requirement: str,
        enable_web_search: bool,
        enable_image_generation: bool,
        enable_video_generation: bool,
        enable_tts: bool,
        agent_mode: str,
        runtime_request_id: str | None = None,
        formal_runtime_contract: Mapping[str, Any] | None = None,
        professional_creation_policy: Mapping[str, Any] | None = None,
        paid_budget: Mapping[str, Any] | None = None,
    ) -> OpenMaicGenerationJob:
        formal = runtime_request_id is not None or formal_runtime_contract is not None
        selected_policy = None
        if formal:
            try:
                selected_policy = professional_policy(
                    professional_creation_policy
                    if professional_creation_policy is not None
                    else (VIDEO_PROFESSIONAL_POLICY if enable_video_generation
                          else PROFESSIONAL_POLICY if enable_image_generation
                          else self.LEGACY_FORMAL_PROFESSIONAL_CREATION_POLICY)
                )
            except ValueError as exc:
                raise OpenMaicFullRuntimeError(
                    "invalid_openmaic_professional_creation_policy",
                    "OpenMAIC 专业图片策略无效", status_code=400,
                ) from exc
            if not _safe_identifier(str(runtime_request_id or ""), max_length=128):
                raise OpenMaicFullRuntimeError(
                    "invalid_openmaic_runtime_request_id",
                    "OpenMAIC 正式生成请求编号无效",
                    status_code=400,
                )
            if (
                not isinstance(formal_runtime_contract, Mapping)
                or dict(formal_runtime_contract)
                != self.FORMAL_RUNTIME_CLASSROOM_CONTRACT
            ):
                raise OpenMaicFullRuntimeError(
                    "invalid_openmaic_formal_runtime_contract",
                    "OpenMAIC 正式课堂合同无效",
                    status_code=400,
                )
            if (
                enable_web_search is not True
                or enable_image_generation is not generation_options(selected_policy)["enableImageGeneration"]
                or enable_video_generation is not generation_options(selected_policy)["enableVideoGeneration"]
                or enable_tts is not False
                or agent_mode != "generate"
            ):
                raise OpenMaicFullRuntimeError(
                    "invalid_openmaic_professional_creation_policy",
                    "OpenMAIC 正式课件必须使用服务端固定的专业创作与联网策略",
                    status_code=400,
                )
        request_payload = {
            "requirement": requirement,
            "enableWebSearch": bool(enable_web_search),
            "enableImageGeneration": bool(enable_image_generation),
            "enableVideoGeneration": bool(enable_video_generation),
            "enableTTS": bool(enable_tts),
            "agentMode": agent_mode,
            **({"paidBudget": dict(paid_budget)} if paid_budget is not None else {}),
            **(
                {
                    "runtimeRequestId": str(runtime_request_id),
                    "formalRuntimeContract": dict(formal_runtime_contract),
                    "coursewareAuthority": dict(self.COURSEWARE_AUTHORITY),
                    "professionalCreationPolicy": json.loads(
                        json.dumps(
                            selected_policy,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    ),
                }
                if formal
                else {}
            ),
        }
        payload = self._request_json(
            "POST",
            "/api/generate-classroom",
            request_payload,
            extra_headers=(
                self._formal_generation_headers() if formal else None
            ),
        )
        job = self._job_from_payload(payload)
        if formal:
            expected_sha256 = self.formal_input_sha256(request_payload)
            if not self.formal_job_identity_matches(
                job,
                runtime_request_id=str(runtime_request_id),
                formal_input_sha256=expected_sha256,
            ):
                raise OpenMaicFullRuntimeError(
                    "openmaic_formal_job_identity_mismatch",
                    "OpenMAIC 正式生成任务身份无法核对",
                    status_code=409,
                )
        return job

    def get_generation_job_by_request_id(
        self, runtime_request_id: str
    ) -> OpenMaicGenerationJob | None:
        """Read patch 0012's idempotency record without starting generation."""

        normalized = str(runtime_request_id or "").strip()
        if not _safe_identifier(normalized, max_length=128):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_runtime_request_id",
                "OpenMAIC 正式生成请求编号无效",
                status_code=400,
            )
        try:
            payload = self._request_json(
                "GET",
                "/api/generate-classroom?runtimeRequestId="
                + quote(normalized, safe=""),
                extra_headers=self._formal_generation_headers(),
            )
        except OpenMaicFullRuntimeError as exc:
            if exc.status_code == 404:
                return None
            raise
        job = self._job_from_payload(payload)
        if (
            job.runtime_request_id != normalized
            or job.formal_contract_version
            != self.FORMAL_RUNTIME_CONTRACT_VERSION
            or re.fullmatch(r"[0-9a-f]{64}", job.formal_input_sha256 or "")
            is None
        ):
            raise OpenMaicFullRuntimeError(
                "openmaic_formal_job_identity_mismatch",
                "OpenMAIC 正式生成任务身份无法核对",
                status_code=409,
            )
        return job

    @classmethod
    def formal_input_sha256(cls, payload: Mapping[str, Any]) -> str:
        canonical = json.dumps(
            dict(payload),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def formal_job_identity_matches(
        cls,
        job: OpenMaicGenerationJob,
        *,
        runtime_request_id: str,
        formal_input_sha256: str,
    ) -> bool:
        return bool(
            job.runtime_request_id == runtime_request_id
            and job.formal_contract_version
            == cls.FORMAL_RUNTIME_CONTRACT_VERSION
            and job.formal_input_sha256 == formal_input_sha256
            and job.dispatch_ambiguous is False
        )

    def get_generation_job(
        self, job_id: str, *, formal: bool = False
    ) -> OpenMaicGenerationJob:
        if not _safe_identifier(job_id, max_length=128):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_job_id",
                "OpenMAIC 生成任务编号无效",
                status_code=400,
            )
        payload = self._request_json(
            "GET",
            f"/api/generate-classroom/{job_id}",
            extra_headers=(
                self._formal_generation_headers() if formal else None
            ),
        )
        job = self._job_from_payload(payload)
        if job.job_id != job_id:
            raise OpenMaicFullRuntimeError(
                "openmaic_formal_job_identity_mismatch",
                "OpenMAIC 正式生成任务身份无法核对",
                status_code=409,
            )
        return job

    def get_classroom(self, classroom_id: str) -> dict[str, Any]:
        if not _safe_identifier(classroom_id, max_length=255):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_classroom_id",
                "OpenMAIC 课堂编号无效",
                status_code=400,
            )
        from urllib.parse import quote

        payload = self._request_json(
            "GET", f"/api/classroom?id={quote(classroom_id, safe='')}"
        )
        classroom = payload.get("classroom") if isinstance(payload, dict) else None
        if not isinstance(classroom, dict):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_classroom",
                "OpenMAIC 返回的课堂内容不完整",
            )
        return classroom

    def read_teaching_conversation(self, *, learning_session_id: str, classroom_id: str,
                                   conversation_id: str | None = None) -> dict[str, Any] | None:
        """Read server-recorded dialogue only over the private authenticated API."""
        for value in (learning_session_id, classroom_id):
            if not _safe_identifier(value, max_length=255):
                raise OpenMaicFullRuntimeError("invalid_teaching_conversation_scope", "课堂指导身份无效", status_code=400)
        if conversation_id is not None and re.fullmatch(r"mtc_[a-f0-9]{64}", conversation_id) is None:
            raise OpenMaicFullRuntimeError("invalid_teaching_conversation_id", "课堂指导身份无效", status_code=400)
        payload = self._request_json("POST", "/api/mira/teaching-conversation/read",
            {"learningSessionId": learning_session_id, "classroomId": classroom_id,
             **({"conversationId": conversation_id} if conversation_id else {})},
            extra_headers=self._formal_generation_headers())
        conversation = payload.get("conversation")
        if conversation is not None and (not isinstance(conversation, dict)
                or conversation.get("learningSessionId") != learning_session_id
                or conversation.get("classroomId") != classroom_id
                or (conversation_id is not None and conversation.get("id") != conversation_id)):
            raise OpenMaicFullRuntimeError("invalid_teaching_conversation_scope", "课堂指导记录身份不一致", status_code=409)
        return conversation

    def video_export_capability(self) -> bool:
        """Probe the pinned runtime and its render service, not local config."""
        payload = self._request_json("GET", "/api/export-video/capability")
        enabled = payload.get("enabled")
        if not isinstance(enabled, bool):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_video_export_capability",
                "OpenMAIC 视频导出能力返回格式无效",
            )
        return enabled

    def media_available(self, reference: str, *, expected_prefix: str) -> bool:
        """Verify same-origin persisted media has bytes and the expected MIME type."""
        normalized = str(reference or "").strip()
        if not normalized or expected_prefix not in {"video/", "audio/", "image/"}:
            return False
        target = urljoin(f"{self.base_url}/", normalized)
        parsed_target = urlparse(target)
        if (
            (parsed_target.scheme, parsed_target.netloc) != self._origin
            or parsed_target.username
            or parsed_target.password
            or parsed_target.fragment
        ):
            return False
        request = Request(
            target,
            headers={
                "Accept": f"{expected_prefix}*",
                "Range": (
                    f"bytes=0-{self.AUDIO_PROBE_BYTES - 1}"
                    if expected_prefix == "audio/"
                    else "bytes=0-0"
                ),
            },
            method="GET",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                final = urlparse(response.geturl())
                if (final.scheme, final.netloc) != self._origin:
                    return False
                content_type = str(response.headers.get("Content-Type") or "")
                content_length = str(response.headers.get("Content-Length") or "")
                if not content_type.casefold().startswith(expected_prefix):
                    return False
                if content_length.isdigit() and int(content_length) <= 0:
                    return False
                if expected_prefix != "audio/":
                    return bool(response.read(1))
                prefix = response.read(self.AUDIO_PROBE_BYTES)
                total_bytes = _media_total_bytes(
                    content_length=content_length,
                    content_range=str(response.headers.get("Content-Range") or ""),
                    bytes_read=len(prefix),
                )
                return bool(
                    total_bytes >= self.MIN_AUDIO_BYTES
                    and _valid_audio_container_prefix(content_type, prefix)
                )
        except (HTTPError, URLError, TimeoutError, OSError):
            return False

    def _job_from_payload(self, payload: object) -> OpenMaicGenerationJob:
        if not isinstance(payload, dict):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_response", "OpenMAIC 返回格式无效"
            )
        job_id = str(payload.get("jobId") or "").strip()
        status = str(payload.get("status") or "").strip().lower()
        if not _safe_identifier(job_id, max_length=128) or status not in {
            "queued",
            "running",
            "succeeded",
            "failed",
        }:
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_job", "OpenMAIC 返回的生成任务无效"
            )
        result = payload.get("result")
        classroom_id = None
        scenes_count = None
        speech_action_count = None
        formal_audio = None
        raw_professional_creation = None
        raw_research = None
        raw_media = None
        raw_video = None
        if isinstance(result, dict):
            raw_classroom_id = str(result.get("classroomId") or "").strip()
            if raw_classroom_id:
                if not _safe_identifier(raw_classroom_id, max_length=255):
                    raise OpenMaicFullRuntimeError(
                        "invalid_openmaic_classroom_id",
                        "OpenMAIC 返回的课堂编号无效",
                    )
                classroom_id = raw_classroom_id
            if type(result.get("scenesCount")) is int:
                scenes_count = int(result["scenesCount"])
            if type(result.get("speechActionCount")) is int:
                speech_action_count = int(result["speechActionCount"])
            raw_formal_audio = result.get("formalAudio")
            if raw_formal_audio is not None:
                if status != "succeeded" or classroom_id is None:
                    raise OpenMaicFullRuntimeError(
                        "invalid_openmaic_formal_audio_receipt",
                        "OpenMAIC 正式语音回执无效",
                    )
                formal_audio = self._formal_audio_receipt_from_payload(
                    raw_formal_audio,
                    classroom_id=classroom_id,
                    professional_creation=result.get("professionalCreation"),
                    expected_segment_count=(
                        speech_action_count
                        if speech_action_count is not None
                        else 0
                    ),
                )
            raw_professional_creation = result.get("professionalCreation")
            raw_research = result.get("research")
            raw_media = result.get("media")
            raw_video = result.get("video")
        progress = payload.get("progress", 100 if status == "succeeded" else 0)
        raw_runtime_request_id = str(payload.get("runtimeRequestId") or "").strip()
        runtime_request_id = raw_runtime_request_id or None
        if runtime_request_id is not None and not _safe_identifier(
            runtime_request_id, max_length=128
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_job", "OpenMAIC 返回的生成任务无效"
            )
        raw_contract_version = str(
            payload.get("formalContractVersion") or ""
        ).strip()
        formal_contract_version = raw_contract_version or None
        formal_job = (
            formal_contract_version == self.FORMAL_RUNTIME_CONTRACT_VERSION
        )
        if formal_job and status == "succeeded" and (
            scenes_count is None
            or not 1 <= scenes_count <= 60
            or speech_action_count is None
            or not scenes_count <= speech_action_count <= 240
            or speech_action_count > scenes_count * 20
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_formal_scene_count",
                "OpenMAIC 正式课堂场景或讲解数量无效",
            )
        if (
            formal_audio is not None
            and formal_contract_version != self.FORMAL_RUNTIME_CONTRACT_VERSION
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_formal_audio_receipt",
                "OpenMAIC 正式语音回执缺少正式课堂身份",
            )
        professional_creation = None
        research = None
        if raw_professional_creation is not None or raw_research is not None:
            if (
                not formal_job
                or status != "succeeded"
                or classroom_id is None
                or runtime_request_id is None
                or raw_professional_creation is None
                or raw_research is None
            ):
                raise OpenMaicFullRuntimeError(
                    "invalid_openmaic_professional_creation_receipt",
                    "OpenMAIC 专业课件创作回执无效",
                )
            professional_creation = (
                self._professional_creation_receipt_from_payload(
                    raw_professional_creation,
                    runtime_request_id=runtime_request_id,
                    classroom_id=classroom_id,
                )
            )
            research = self._research_receipt_from_payload(
                raw_research,
                runtime_request_id=runtime_request_id,
                classroom_id=classroom_id,
            )
            if (
                professional_creation["buildItemId"]
                != research["buildItemId"]
                or professional_creation["sessionId"]
                != research["sessionId"]
            ):
                raise OpenMaicFullRuntimeError(
                    "invalid_openmaic_professional_creation_receipt",
                    "OpenMAIC 专业课件创作与联网研究回执身份不一致",
                )
        if formal_job and status == "succeeded" and (
            professional_creation is None or research is None
        ):
            raise OpenMaicFullRuntimeError(
                "openmaic_formal_professional_evidence_missing",
                "OpenMAIC 正式课件缺少专业创作或联网研究回执",
            )
        media = None
        image_enabled = bool(professional_creation and professional_image_fields(professional_creation))
        if image_enabled or raw_media is not None:
            if not image_enabled or not professional_creation:
                raise OpenMaicFullRuntimeError("invalid_openmaic_media_receipt", "OpenMAIC 图片回执缺少专业图片策略")
            try:
                media = media_receipt(raw_media, runtime_request_id=str(runtime_request_id),
                    classroom_id=str(classroom_id), build_item_id=professional_creation["buildItemId"],
                    session_id=professional_creation["sessionId"])
            except ValueError as exc:
                raise OpenMaicFullRuntimeError("invalid_openmaic_media_receipt", "OpenMAIC 正式图片回执无效") from exc
        raw_input_sha256 = str(payload.get("formalInputSha256") or "").strip()
        formal_input_sha256 = raw_input_sha256 or None
        if formal_input_sha256 is not None and re.fullmatch(
            r"[0-9a-f]{64}", formal_input_sha256
        ) is None:
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_job", "OpenMAIC 返回的生成任务无效"
            )
        raw_error = str(payload.get("error") or "")[:512] or None
        video = None
        video_enabled = bool(professional_creation and professional_video_fields(professional_creation))
        if video_enabled or raw_video is not None:
            if not video_enabled or professional_creation is None:
                raise OpenMaicFullRuntimeError("invalid_openmaic_video_receipt", "OpenMAIC 视频回执缺少专业视频策略")
            try:
                video = video_receipt(raw_video, runtime_request_id=str(runtime_request_id),
                    classroom_id=str(classroom_id), build_item_id=professional_creation["buildItemId"],
                    session_id=professional_creation["sessionId"])
            except ValueError as exc:
                raise OpenMaicFullRuntimeError("invalid_openmaic_video_receipt", "OpenMAIC 正式视频回执无效") from exc
        return OpenMaicGenerationJob(
            job_id=job_id,
            status=status,
            step=str(payload.get("step") or status)[:128],
            progress=max(0, min(100, int(progress or 0))),
            done=bool(payload.get("done", status in {"succeeded", "failed"})),
            classroom_id=classroom_id,
            scenes_count=scenes_count,
            error=raw_error,
            speech_action_count=speech_action_count,
            runtime_request_id=runtime_request_id,
            formal_contract_version=formal_contract_version,
            formal_input_sha256=formal_input_sha256,
            dispatch_ambiguous=payload.get("dispatchAmbiguous") is True,
            failure_code=_generation_failure_code(status, raw_error),
            formal_audio=formal_audio,
            professional_creation=professional_creation,
            research=research,
            media=media,
            video=video,
        )

    @classmethod
    def _professional_creation_receipt_from_payload(
        cls,
        value: object,
        *,
        runtime_request_id: str,
        classroom_id: str,
    ) -> dict[str, Any]:
        code = "invalid_openmaic_professional_creation_receipt"
        try:
            image_fields = professional_image_fields(value) if isinstance(value, Mapping) else {}
            video_fields = professional_video_fields(value) if isinstance(value, Mapping) else {}
            skill_fields = professional_skill_fields(value) if isinstance(value, Mapping) else {}
            quality_fields = professional_quality_fields(value) if isinstance(value, Mapping) else {}
            interaction_fields = professional_interaction_fields(value) if isinstance(value, Mapping) else {}
            if skill_fields and not image_fields:
                raise ValueError("integrated skills require the versioned image policy")
            adaptive = skill_fields.get("skillOrchestration", {}).get("schemaVersion") == "mira.openmaic.skill-orchestration-receipt.v2"
            if adaptive != bool(quality_fields):
                raise ValueError("adaptive skills require final teaching quality evidence")
            if video_fields and not (image_fields and adaptive and quality_fields):
                raise ValueError("formal video requires adaptive image and quality evidence")
            if interaction_fields and not (video_fields and adaptive and quality_fields):
                raise ValueError("formal interaction requires the versioned final quality policy")
        except ValueError as exc:
            raise OpenMaicFullRuntimeError(code, "OpenMAIC 专业创作策略回执无效") from exc
        receipt = _exact_mapping(
            value,
            {
                "schemaVersion",
                "status",
                "runtimeRequestId",
                "buildItemId",
                "classroomId",
                "teachingBriefSha256",
                "sessionId",
                "workflowVersion",
                "skillId",
                "supportingSkillIds",
                "userPromptRequired",
                "studentToolsEnabled",
                "webSearchEnabled",
                "receiptSha256",
                *image_fields,
                *video_fields,
                *skill_fields,
                *quality_fields,
                *interaction_fields,
            },
            code=code,
        )
        build_item_id = _formal_audio_identifier(
            receipt.get("buildItemId"), maximum=128
        )
        session_id = _formal_audio_identifier(
            receipt.get("sessionId"), maximum=128
        )
        teaching_brief_sha256 = _sha256_or_none(
            receipt.get("teachingBriefSha256")
        )
        receipt_sha256 = _sha256_or_none(receipt.get("receiptSha256"))
        if (
            receipt.get("schemaVersion")
            != cls.FORMAL_PROFESSIONAL_CREATION_RECEIPT_VERSION
            or receipt.get("status") != "succeeded"
            or receipt.get("runtimeRequestId") != runtime_request_id
            or build_item_id is None
            or receipt.get("classroomId") != classroom_id
            or teaching_brief_sha256 is None
            or session_id is None
            or receipt.get("workflowVersion") != "openmaic-pro-agent.v1"
            or receipt.get("skillId") != "mira-primary-courseware"
            or receipt.get("supportingSkillIds")
            != ["k12-core-literacy-planning", "deep-interactive"]
            or receipt.get("userPromptRequired") is not False
            or receipt.get("studentToolsEnabled") is not False
            or receipt.get("webSearchEnabled") is not True
            or receipt_sha256 is None
        ):
            raise OpenMaicFullRuntimeError(
                code,
                "OpenMAIC 专业课件创作回执无效",
            )
        unsigned = dict(receipt)
        unsigned.pop("receiptSha256")
        if _canonical_sha256(unsigned) != receipt_sha256:
            raise OpenMaicFullRuntimeError(
                code,
                "OpenMAIC 专业课件创作回执校验失败",
            )
        return json.loads(
            json.dumps(
                dict(receipt),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    @classmethod
    def _research_receipt_from_payload(
        cls,
        value: object,
        *,
        runtime_request_id: str,
        classroom_id: str,
    ) -> dict[str, Any]:
        code = "invalid_openmaic_research_receipt"
        receipt = _exact_mapping(
            value,
            {
                "schemaVersion",
                "status",
                "runtimeRequestId",
                "buildItemId",
                "classroomId",
                "sessionId",
                "providerId",
                "searchCount",
                "resultCount",
                "fetchedSourceCount",
                "citationCount",
                "searches",
                "sources",
                "citations",
                "receiptSha256",
            },
            code=code,
        )
        build_item_id = _formal_audio_identifier(
            receipt.get("buildItemId"), maximum=128
        )
        session_id = _formal_audio_identifier(
            receipt.get("sessionId"), maximum=128
        )
        provider_id = _formal_audio_identifier(
            receipt.get("providerId"), maximum=64
        )
        receipt_sha256 = _sha256_or_none(receipt.get("receiptSha256"))
        counts = (
            receipt.get("searchCount"),
            receipt.get("resultCount"),
            receipt.get("fetchedSourceCount"),
            receipt.get("citationCount"),
        )
        searches = receipt.get("searches")
        sources = receipt.get("sources")
        citations = receipt.get("citations")
        if (
            receipt.get("schemaVersion")
            != cls.FORMAL_RESEARCH_RECEIPT_VERSION
            or receipt.get("status") != "succeeded"
            or receipt.get("runtimeRequestId") != runtime_request_id
            or build_item_id is None
            or receipt.get("classroomId") != classroom_id
            or session_id is None
            or provider_id is None
            or any(type(count) is not int for count in counts)
            # Execution policy controls attempts; a receipt reports actual work.
            # Metering-only runs may legitimately contain more than four searches.
            or int(receipt.get("searchCount") or 0) < 1
            or int(receipt.get("resultCount") or 0) < 1
            or int(receipt.get("fetchedSourceCount") or 0) < 1
            or int(receipt.get("citationCount") or 0) < 1
            or not isinstance(searches, list)
            or len(searches) != receipt.get("searchCount")
            or not isinstance(sources, list)
            or len(sources) != receipt.get("fetchedSourceCount")
            or not isinstance(citations, list)
            or len(citations) != receipt.get("citationCount")
            or int(receipt.get("resultCount") or 0) < len(sources)
            or receipt_sha256 is None
        ):
            raise OpenMaicFullRuntimeError(
                code,
                "OpenMAIC 正式课件联网研究回执无效",
            )

        for search in searches:
            item = _exact_mapping(
                search,
                {"query", "searchedAt", "resultCount"},
                code=code,
            )
            query = str(item.get("query") or "")
            searched_at = str(item.get("searchedAt") or "")
            if (
                query != query.strip()
                or not query
                or len(query) > 512
                or searched_at != searched_at.strip()
                or not searched_at
                or len(searched_at) > 64
                or type(item.get("resultCount")) is not int
                or int(item.get("resultCount") or 0) < 1
            ):
                raise OpenMaicFullRuntimeError(
                    code,
                    "OpenMAIC 正式课件搜索记录无效",
                )

        source_urls: set[str] = set()
        for source in sources:
            item = _exact_mapping(
                source,
                {"title", "url", "textSha256"},
                code=code,
            )
            title = str(item.get("title") or "")
            url = str(item.get("url") or "")
            parsed = urlparse(url)
            if (
                title != title.strip()
                or not title
                or len(title) > 512
                or url != url.strip()
                or len(url) > 2_048
                or parsed.scheme not in {"http", "https"}
                or not parsed.netloc
                or parsed.username
                or parsed.password
                or _sha256_or_none(item.get("textSha256")) is None
            ):
                raise OpenMaicFullRuntimeError(
                    code,
                    "OpenMAIC 正式课件联网材料记录无效",
                )
            source_urls.add(url)

        for citation in citations:
            item = _exact_mapping(
                citation,
                {"url", "sceneIds"},
                code=code,
            )
            url = str(item.get("url") or "")
            scene_ids = item.get("sceneIds")
            if (
                url not in source_urls
                or not isinstance(scene_ids, list)
                or not scene_ids
                or len(scene_ids) > 60
                or any(
                    _formal_audio_identifier(scene_id, maximum=128) is None
                    for scene_id in scene_ids
                )
                or len(set(scene_ids)) != len(scene_ids)
            ):
                raise OpenMaicFullRuntimeError(
                    code,
                    "OpenMAIC 正式课件引用记录无效",
                )
        unsigned = dict(receipt)
        unsigned.pop("receiptSha256")
        if _canonical_sha256(unsigned) != receipt_sha256:
            raise OpenMaicFullRuntimeError(
                code,
                "OpenMAIC 正式课件联网研究回执校验失败",
            )
        return json.loads(
            json.dumps(
                dict(receipt),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )

    @classmethod
    def _formal_audio_receipt_from_payload(
        cls,
        value: object,
        *,
        classroom_id: str,
        expected_segment_count: int,
        professional_creation: object = None,
    ) -> OpenMaicFormalAudioReceipt:
        receipt = _exact_mapping(
            value,
            {
                "schemaVersion",
                "status",
                "buildItemId",
                "classroomId",
                "classroomContentSha256",
                "subject",
                "speechTextPolicyVersion",
                "teacherProfile",
                "expectedSegmentCount",
                "ttsSucceededCount",
                "asrPassedCount",
                "segments",
                "receiptSha256",
            },
            code="invalid_openmaic_formal_audio_receipt",
        )
        teacher = _exact_mapping(
            receipt.get("teacherProfile"),
            {"id", "version", "sha256", "gender"},
            code="invalid_openmaic_formal_audio_receipt",
        )
        build_item_id = _formal_audio_identifier(
            receipt.get("buildItemId"), maximum=128
        )
        observed_classroom_id = _formal_audio_identifier(
            receipt.get("classroomId"), maximum=255
        )
        subject = str(receipt.get("subject") or "")
        teacher_profile_id = _formal_audio_identifier(
            teacher.get("id"), maximum=128
        )
        teacher_profile_version = teacher.get("version")
        teacher_profile_sha256 = _sha256_or_none(teacher.get("sha256"))
        teacher_gender = str(teacher.get("gender") or "")
        classroom_content_sha256 = _sha256_or_none(
            receipt.get("classroomContentSha256")
        )
        receipt_sha256 = _sha256_or_none(receipt.get("receiptSha256"))
        raw_segments = receipt.get("segments")
        if (
            receipt.get("schemaVersion") != cls.FORMAL_AUDIO_LIFECYCLE_VERSION
            or receipt.get("status") != "succeeded"
            or build_item_id is None
            or observed_classroom_id != classroom_id
            or classroom_content_sha256 is None
            or subject not in {"chinese", "math", "english"}
            or receipt.get("speechTextPolicyVersion")
            != cls.FORMAL_SPEECH_TEXT_POLICY_VERSION
            or teacher_profile_id is None
            or type(teacher_profile_version) is not int
            or teacher_profile_version != 2
            or teacher_profile_sha256 is None
            or teacher_gender not in {"female", "male"}
            or type(expected_segment_count) is not int
            or not 1 <= expected_segment_count <= 240
            or receipt.get("expectedSegmentCount") != expected_segment_count
            or receipt.get("ttsSucceededCount") != expected_segment_count
            or receipt.get("asrPassedCount") != expected_segment_count
            or not isinstance(raw_segments, list)
            or len(raw_segments) != expected_segment_count
            or receipt_sha256 is None
        ):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_formal_audio_receipt",
                "OpenMAIC 正式语音回执无效",
            )
        safe_receipt = dict(receipt)
        safe_receipt.pop("receiptSha256")
        if receipt_sha256 != _canonical_sha256(safe_receipt):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_formal_audio_receipt",
                "OpenMAIC 正式语音回执校验失败",
            )

        segments: list[OpenMaicFormalAudioSegmentReceipt] = []
        seen_action_ids: set[str] = set()
        seen_narration_ids: set[str] = set()
        seen_tts_request_ids: set[str] = set()
        seen_asr_request_ids: set[str] = set()
        voice_by_subject = {
            "chinese": "Serena",
            "math": "Ethan",
            "english": "Jennifer",
        }
        for expected_order, raw_segment in enumerate(raw_segments):
            segment = _exact_mapping(
                raw_segment,
                {
                    "sceneOrder",
                    "sceneId",
                    "actionId",
                    "narrationSegmentId",
                    "sourceTextSha256",
                    "textSha256",
                    "tts",
                    "asr",
                },
                code="invalid_openmaic_formal_audio_receipt",
            )
            tts = _exact_mapping(
                segment.get("tts"),
                {
                    "requestId",
                    "requestSha256",
                    "state",
                    "audioSha256",
                    "mimeType",
                    "sizeBytes",
                    "providerId",
                    "modelId",
                    "voiceId",
                    "fallbackUsed",
                },
                code="invalid_openmaic_formal_audio_receipt",
            )
            asr = _exact_mapping(
                segment.get("asr"),
                {
                    "requestId",
                    "requestSha256",
                    "state",
                    "transcriptSha256",
                    "normalizedTranscriptSha256",
                    "similarityBps",
                    "providerId",
                    "modelId",
                    "fallbackUsed",
                    *({"comparisonRevalidation"} if isinstance(segment.get("asr"), Mapping)
                      and "comparisonRevalidation" in segment["asr"] else set()),
                },
                code="invalid_openmaic_formal_audio_receipt",
            )
            scene_id = _formal_audio_identifier(
                segment.get("sceneId"), maximum=128
            )
            action_id = _formal_audio_identifier(
                segment.get("actionId"), maximum=128
            )
            narration_segment_id = _formal_audio_identifier(
                segment.get("narrationSegmentId"), maximum=128
            )
            source_text_sha256 = _sha256_or_none(
                segment.get("sourceTextSha256")
            )
            text_sha256 = _sha256_or_none(segment.get("textSha256"))
            tts_request_id = _formal_audio_identifier(
                tts.get("requestId"), maximum=128
            )
            tts_request_sha256 = _sha256_or_none(tts.get("requestSha256"))
            audio_sha256 = _sha256_or_none(tts.get("audioSha256"))
            size_bytes = tts.get("sizeBytes")
            asr_request_id = _formal_audio_identifier(
                asr.get("requestId"), maximum=128
            )
            asr_request_sha256 = _sha256_or_none(asr.get("requestSha256"))
            transcript_sha256 = _sha256_or_none(asr.get("transcriptSha256"))
            normalized_transcript_sha256 = _sha256_or_none(
                asr.get("normalizedTranscriptSha256")
            )
            similarity_bps = asr.get("similarityBps")
            if (
                type(segment.get("sceneOrder")) is not int
                or segment.get("sceneOrder") != expected_order
                or scene_id is None
                or action_id is None
                or narration_segment_id is None
                or source_text_sha256 is None
                or text_sha256 is None
                or tts_request_id is None
                or tts_request_sha256 is None
                or audio_sha256 is None
                or type(size_bytes) is not int
                or not 44 <= size_bytes <= cls.FORMAL_AUDIO_MAX_BYTES
                or tts.get("state") != "succeeded"
                or tts.get("mimeType") != "audio/wav"
                or tts.get("providerId") != "qwen-tts"
                or tts.get("modelId") != "qwen3-tts-flash"
                or tts.get("voiceId") != voice_by_subject[subject]
                or tts.get("fallbackUsed") is not False
                or asr_request_id is None
                or asr_request_sha256 is None
                or transcript_sha256 is None
                or normalized_transcript_sha256 is None
                or type(similarity_bps) is not int
                or not 8_500 <= similarity_bps <= 10_000
                or asr.get("state") != "succeeded"
                or asr.get("providerId") != "qwen-asr"
                or asr.get("modelId") != "qwen3-asr-flash"
                or asr.get("fallbackUsed") is not False
                or action_id in seen_action_ids
                or narration_segment_id in seen_narration_ids
                or tts_request_id in seen_tts_request_ids
                or asr_request_id in seen_asr_request_ids
            ):
                raise OpenMaicFullRuntimeError(
                    "invalid_openmaic_formal_audio_receipt",
                    "OpenMAIC 正式语音分段回执无效",
                )
            seen_action_ids.add(action_id)
            seen_narration_ids.add(narration_segment_id)
            seen_tts_request_ids.add(tts_request_id)
            seen_asr_request_ids.add(asr_request_id)
            comparison_revalidation = None
            if "comparisonRevalidation" in asr:
                try:
                    comparison_revalidation = validate_asr_comparison_revalidation(
                        asr["comparisonRevalidation"], lifecycle=receipt, segment=segment,
                        professional_creation=professional_creation,
                    )
                except (ValueError, TypeError, KeyError) as exc:
                    raise OpenMaicFullRuntimeError(
                        "invalid_openmaic_formal_audio_receipt",
                        "OpenMAIC 原语音转写复核凭据无效",
                    ) from exc
            segments.append(
                OpenMaicFormalAudioSegmentReceipt(
                    scene_order=expected_order,
                    scene_id=scene_id,
                    action_id=action_id,
                    narration_segment_id=narration_segment_id,
                    source_text_sha256=source_text_sha256,
                    text_sha256=text_sha256,
                    tts=OpenMaicFormalAudioTtsReceipt(
                        request_id=tts_request_id,
                        request_sha256=tts_request_sha256,
                        audio_sha256=audio_sha256,
                        size_bytes=size_bytes,
                        voice_id=str(tts["voiceId"]),
                    ),
                    asr=OpenMaicFormalAudioAsrReceipt(
                        request_id=asr_request_id,
                        request_sha256=asr_request_sha256,
                        transcript_sha256=transcript_sha256,
                        normalized_transcript_sha256=(
                            normalized_transcript_sha256
                        ),
                        similarity_bps=similarity_bps,
                        comparison_revalidation=comparison_revalidation,
                    ),
                )
            )
        return OpenMaicFormalAudioReceipt(
            schema_version=cls.FORMAL_AUDIO_LIFECYCLE_VERSION,
            build_item_id=build_item_id,
            classroom_id=observed_classroom_id,
            classroom_content_sha256=classroom_content_sha256,
            subject=subject,
            speech_text_policy_version=cls.FORMAL_SPEECH_TEXT_POLICY_VERSION,
            teacher_profile_id=teacher_profile_id,
            teacher_profile_version=teacher_profile_version,
            teacher_profile_sha256=teacher_profile_sha256,
            teacher_gender=teacher_gender,
            expected_segment_count=expected_segment_count,
            tts_succeeded_count=expected_segment_count,
            asr_passed_count=expected_segment_count,
            segments=tuple(segments),
            receipt_sha256=receipt_sha256,
        )

    def _request_json(
        self,
        method: str,
        path: str,
        body: Mapping[str, Any] | None = None,
        *,
        extra_headers: Mapping[str, str] | None = None,
        timeout_seconds: float | None = None,
    ) -> dict[str, Any]:
        target = urljoin(f"{self.base_url}/", path.lstrip("/"))
        parsed_target = urlparse(target)
        if (parsed_target.scheme, parsed_target.netloc) != self._origin:
            raise OpenMaicFullRuntimeError(
                "openmaic_target_not_allowed", "OpenMAIC 请求目标不安全"
            )
        data = None
        headers = {"Accept": "application/json"}
        if extra_headers is not None:
            headers.update({str(key): str(value) for key, value in extra_headers.items()})
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = Request(target, data=data, headers=headers, method=method)
        request_timeout = (
            self.timeout_seconds
            if timeout_seconds is None
            else float(timeout_seconds)
        )
        if request_timeout <= 0 or request_timeout > 300:
            raise ValueError("OpenMAIC request timeout must be between 0 and 300 seconds.")
        try:
            with urlopen(request, timeout=request_timeout) as response:
                final = urlparse(response.geturl())
                if (final.scheme, final.netloc) != self._origin:
                    raise OpenMaicFullRuntimeError(
                        "openmaic_redirect_not_allowed",
                        "OpenMAIC 返回了不安全的跳转",
                    )
                raw = response.read(self.MAX_JSON_BYTES + 1)
        except HTTPError as exc:
            safe_status = int(getattr(exc, "code", 502) or 502)
            raise OpenMaicFullRuntimeError(
                "openmaic_upstream_error",
                "OpenMAIC 服务暂时不可用",
                status_code=safe_status,
            ) from exc
        except (URLError, TimeoutError, OSError) as exc:
            raise OpenMaicFullRuntimeError(
                "openmaic_unavailable",
                "暂时无法连接 OpenMAIC 课堂服务",
                status_code=503,
            ) from exc
        if len(raw) > self.MAX_JSON_BYTES:
            raise OpenMaicFullRuntimeError(
                "openmaic_response_too_large", "OpenMAIC 返回内容超过安全上限"
            )
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as exc:
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_response", "OpenMAIC 返回格式无效"
            ) from exc
        if not isinstance(payload, dict):
            raise OpenMaicFullRuntimeError(
                "invalid_openmaic_response", "OpenMAIC 返回格式无效"
            )
        if payload.get("success") is False:
            raise OpenMaicFullRuntimeError(
                "openmaic_upstream_rejected",
                "OpenMAIC 未能处理这次课堂请求",
                status_code=422,
            )
        return payload


def _safe_identifier(value: str, *, max_length: int) -> bool:
    if not value or len(value) > max_length:
        return False
    return all(char.isalnum() or char in {"-", "_"} for char in value)


def _formal_audio_identifier(value: object, *, maximum: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if (
        normalized != value
        or not normalized
        or len(normalized) > maximum
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", normalized) is None
    ):
        return None
    return normalized


def _exact_mapping(
    value: object,
    expected_keys: set[str],
    *,
    code: str,
) -> Mapping[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected_keys:
        raise OpenMaicFullRuntimeError(
            code,
            "OpenMAIC 正式语音回执无效",
        )
    return value


def _generation_failure_code(status: str, error: str | None) -> str | None:
    if status != "failed":
        return None
    normalized = str(error or "").casefold()
    if "allocationquota.freetieronly" in normalized or "free quota exhausted" in normalized:
        return "openmaic_formal_provider_free_quota_exhausted"
    if "insufficient balance" in normalized and (
        "suspended" in normalized or "recharge" in normalized
    ):
        return "openmaic_formal_provider_billing_blocked"
    return "openmaic_formal_generation_failed"


def _formal_readiness_identifier(value: object, *, max_length: int) -> str:
    normalized = _formal_readiness_identifier_or_none(
        value, max_length=max_length
    )
    if normalized is None:
        raise OpenMaicFullRuntimeError(
            "invalid_formal_provider_readiness_request_id",
            "正式课程 Provider 就绪请求编号无效",
            status_code=400,
        )
    return normalized


def _formal_readiness_identifier_or_none(
    value: object, *, max_length: int
) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if (
        not normalized
        or len(normalized) > max_length
        or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:-]*", normalized) is None
    ):
        return None
    return normalized


def _sha256_or_none(value: object) -> str | None:
    if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
        return None
    return value


def _canonical_sha256(value: object) -> str:
    canonical = json.dumps(
        value,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _contains_formal_readiness_raw_payload(value: object) -> bool:
    forbidden = {
        "transcript",
        "raw",
        "rawresponse",
        "rawpayload",
        "requestbody",
        "responsebody",
        "audio",
        "audiourl",
        "base64",
        "apikey",
        "authorization",
        "secret",
        "token",
        "providerkey",
    }
    if isinstance(value, Mapping):
        return any(
            str(key).casefold() in forbidden
            or _contains_formal_readiness_raw_payload(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_formal_readiness_raw_payload(item) for item in value)
    return False


def _media_total_bytes(
    *, content_length: str, content_range: str, bytes_read: int
) -> int:
    range_match = re.fullmatch(
        r"\s*bytes\s+\d+-\d+/(\d+|\*)\s*",
        content_range,
        flags=re.IGNORECASE,
    )
    if range_match is not None and range_match.group(1).isdigit():
        return int(range_match.group(1))
    if content_length.isdigit():
        return int(content_length)
    return int(bytes_read)


def _valid_audio_container_prefix(content_type: str, prefix: bytes) -> bool:
    """Fail closed on mislabeled or truncated classroom audio.

    Qwen3-TTS currently returns WAV, while the OpenMAIC transport can also
    persist MP3, Ogg, WebM, MP4/M4A, AAC or FLAC from reviewed providers.  MIME
    and magic bytes must agree; an ``audio/*`` header plus one arbitrary byte is
    not evidence that a browser can decode the asset.
    """

    if len(prefix) < 12:
        return False
    mime = content_type.partition(";")[0].strip().casefold()
    if mime in {"audio/wav", "audio/wave", "audio/x-wav", "audio/vnd.wave"}:
        return prefix[:4] in {b"RIFF", b"RF64"} and prefix[8:12] == b"WAVE"
    if mime in {"audio/mpeg", "audio/mp3"}:
        return prefix.startswith(b"ID3") or (
            prefix[0] == 0xFF and (prefix[1] & 0xE0) == 0xE0
        )
    if mime in {"audio/ogg", "audio/opus"}:
        return prefix.startswith(b"OggS")
    if mime in {"audio/webm"}:
        return prefix.startswith(b"\x1aE\xdf\xa3")
    if mime in {"audio/mp4", "audio/m4a", "audio/x-m4a"}:
        return prefix[4:8] == b"ftyp"
    if mime in {"audio/aac", "audio/aacp"}:
        return prefix[0] == 0xFF and (prefix[1] & 0xF6) == 0xF0
    if mime in {"audio/flac", "audio/x-flac"}:
        return prefix.startswith(b"fLaC")
    return False


def _bounded_health_text(value: object, max_length: int) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.strip()
    if not normalized or len(normalized) > max_length:
        return None
    return normalized


def _bounded_structured_scene_policy(value: object) -> dict[str, Any] | None:
    """Return only the non-secret structured-output policy allowlist."""

    if not isinstance(value, Mapping):
        return None
    raw_stages = value.get("stages")
    stages = (
        [
            bounded
            for item in raw_stages
            if (bounded := _bounded_health_text(item, 64)) is not None
        ][:8]
        if isinstance(raw_stages, list)
        else None
    )
    thinking = value.get("thinking")
    observed_thinking = (
        {
            "mode": _bounded_health_text(thinking.get("mode"), 32),
            "enabled": (
                thinking.get("enabled")
                if isinstance(thinking.get("enabled"), bool)
                else None
            ),
        }
        if isinstance(thinking, Mapping)
        else None
    )
    return {
        "enforced": (
            value.get("enforced")
            if isinstance(value.get("enforced"), bool)
            else None
        ),
        "policyId": _bounded_health_text(value.get("policyId"), 128),
        "providerId": _bounded_health_text(value.get("providerId"), 64),
        "modelId": _bounded_health_text(value.get("modelId"), 128),
        "stages": stages,
        "thinking": observed_thinking,
    }
