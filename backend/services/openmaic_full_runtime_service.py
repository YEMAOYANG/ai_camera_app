from __future__ import annotations

import json
import logging
import hashlib
import math
import re
from datetime import datetime, timezone
from html.parser import HTMLParser
from typing import Any, Iterable, Mapping, Sequence
from urllib.parse import urlencode, urlsplit

from content.primary_skill_boundaries import boundaries_for
from content.teacher_profiles import (
    get_formal_runtime_teacher_contract,
    get_formal_subject_qwen_voice_identity,
    get_openmaic_qwen3_voice_identity,
    get_teacher_profile,
    list_teacher_profiles,
)
from integrations.openmaic_formal_media import (
    professional_policy, generation_options, professional_image_fields,
    media_receipt, validate_classroom_media, validate_media_manifest,
)
from integrations.openmaic_formal_skills import (
    professional_skill_fields, validate_classroom_skills,
)
from integrations.openmaic_formal_video import (
    professional_video_fields, video_receipt, validate_classroom_video, classroom_video_references,
)
from integrations.openmaic_formal_pedagogy import (
    adaptive_policy, validate_generation_grade_boundary,
)
from integrations.openmaic_formal_quality import (
    professional_quality_fields, validate_classroom_quality,
)
from integrations.openmaic_formal_interaction import professional_interaction_fields, validate_classroom_interaction
from core.database import Database
from core.security import hash_value, new_token, now_ms
from integrations.openmaic_full_runtime_client import (
    OpenMaicFullRuntimeClient,
    OpenMaicFullRuntimeError,
)
from integrations.openmaic_formal_citation_recovery_client import (
    FORMAL_CITATION_RECOVERY_SOURCE_ERROR,
    OpenMaicFormalCitationRecovery,
    OpenMaicFormalCitationRecoveryClient,
    OpenMaicFormalCitationRecoveryError,
)
from integrations.openmaic_conversation_probe_client import (
    OpenMaicConversationProbeClient,
    OpenMaicConversationProbeClientError,
)
from integrations.openmaic_deterministic_recovery_client import (
    RECOVERY_KIND,
    RECOVERY_MODE,
    RECOVERY_SOURCE_SCENES_GENERATED,
    RECOVERY_SOURCE_TOTAL_SCENES,
    OpenMaicDeterministicRecovery,
    OpenMaicDeterministicRecoveryClient,
    OpenMaicDeterministicRecoveryError,
    OpenMaicRecoverySourceSnapshot,
    deterministic_recovery_identity,
)
from integrations.openmaic_tts_credential_recovery_client import (
    TTS_CREDENTIAL_RECOVERY_KIND,
    TTS_CREDENTIAL_RECOVERY_MODE,
    TTS_CREDENTIAL_RECOVERY_REQUEST_MODE,
    OpenMaicTtsCredentialRecovery,
    OpenMaicTtsCredentialRecoveryClient,
    OpenMaicTtsCredentialRecoveryError,
    tts_credential_classroom_identity,
    tts_credential_parent_snapshot_sha256,
    tts_credential_recovery_identity,
)
from repositories.formal_student_runtime_gate import (
    CURRENT_ARTIFACT_PUBLICATION_CONTRACT_VERSION,
)
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from services.student_auth_service import StudentAuthService
from services.openmaic_conversation_probe_service import (
    OpenMaicConversationProbeService,
    OpenMaicConversationProbeError,
)


RUNTIME_FEATURES = frozenset(
    {
        "slides",
        "quiz",
        "video",
        "3d_visualization",
        "simulation",
        "diagram",
        "code",
        "html_game",
        "pbl",
        "multi_agent_roundtable",
        "realtime_whiteboard",
        "teacher_actions",
        "mp4_export",
    }
)

SCENE_TYPES = frozenset({"slide", "quiz", "interactive", "pbl"})
WIDGET_TYPES = frozenset(
    {
        "simulation",
        "diagram",
        "code",
        "game",
        "visualization3d",
        "procedural-skill",
    }
)
PPT_ELEMENT_TYPES = frozenset(
    {
        "text",
        "image",
        "shape",
        "line",
        "chart",
        "table",
        "latex",
        "video",
        "audio",
        "code",
    }
)
ACTION_REQUIRED_FIELDS: dict[str, dict[str, str]] = {
    "spotlight": {"elementId": "string"},
    "laser": {"elementId": "string"},
    "play_video": {"elementId": "string"},
    "speech": {"text": "string"},
    "wb_open": {},
    "wb_draw_text": {"content": "string", "x": "number", "y": "number"},
    "wb_draw_shape": {
        "shape": "string",
        "x": "number",
        "y": "number",
        "width": "number",
        "height": "number",
    },
    "wb_draw_chart": {
        "chartType": "string",
        "x": "number",
        "y": "number",
        "width": "number",
        "height": "number",
        "data": "object",
    },
    "wb_draw_latex": {"latex": "string", "x": "number", "y": "number"},
    "wb_draw_table": {
        "x": "number",
        "y": "number",
        "width": "number",
        "height": "number",
        "data": "array",
    },
    "wb_draw_line": {
        "startX": "number",
        "startY": "number",
        "endX": "number",
        "endY": "number",
    },
    "wb_draw_code": {
        "language": "string",
        "code": "string",
        "x": "number",
        "y": "number",
    },
    "wb_edit_code": {"elementId": "string", "operation": "string"},
    "wb_clear": {},
    "wb_delete": {"elementId": "string"},
    "wb_close": {},
    "discussion": {"topic": "string"},
    "widget_highlight": {"target": "string"},
    "widget_setState": {"state": "object"},
    "widget_annotation": {"target": "string"},
    "widget_reveal": {"target": "string"},
}
WHITEBOARD_DRAW_ACTIONS = frozenset(
    {
        "wb_draw_text",
        "wb_draw_shape",
        "wb_draw_chart",
        "wb_draw_latex",
        "wb_draw_table",
        "wb_draw_line",
        "wb_draw_code",
    }
)
WIDGET_TEACHER_ACTIONS = frozenset(
    {
        "widget_highlight",
        "widget_setState",
        "widget_annotation",
        "widget_reveal",
    }
)
DEFAULT_AGENT_ROLES = {
    "default-1": "teacher",
    "default-2": "assistant",
    "default-3": "student",
    "default-4": "student",
    "default-5": "student",
    "default-6": "student",
}

DEFAULT_RUNTIME_FEATURES = (
    "slides",
    "quiz",
    "video",
    "3d_visualization",
    "simulation",
    "html_game",
    "pbl",
    "multi_agent_roundtable",
    "realtime_whiteboard",
    "teacher_actions",
)

SAMPLE_MODE = "primary_1_math_number_sense_20_v1"
SAMPLE_GRADE_CODE = "primary_1"
SAMPLE_SUBJECT = "math"
SAMPLE_SKILL_ID = "number_sense_20"
SAMPLE_REQUIRED_FEATURES = (
    "slides",
    "quiz",
    "simulation",
    "html_game",
    "3d_visualization",
    "multi_agent_roundtable",
    "teacher_actions",
)
SAMPLE_EXACT_SCENE_COUNT = 10
SAMPLE_MINIMUM_SLIDE_SCENES = 2
SAMPLE_REQUIRED_WIDGET_TYPES = (
    "simulation",
    "game",
    "visualization3d",
)
SAMPLE_MINIMUM_PEER_AGENTS = 3
SAMPLE_MINIMUM_DISCUSSION_ACTIONS = 2
SAMPLE_GENERATION_STALE_AFTER_MS = 30 * 60 * 1000
SAMPLE_RECOVERY_LOCAL_STALE_AFTER_MS = 10 * 60 * 1000
SAMPLE_TTS_CREDENTIAL_RECOVERY_STALE_AFTER_MS = 15 * 60 * 1000
SAMPLE_ALLOWED_REQUEST_FIELDS = frozenset({"requestId", "sampleMode"})
SAMPLE_RETRY_ALLOWED_REQUEST_FIELDS = frozenset(
    {"retryRequestId", "expectedPreviousJobId", "reason"}
)
SAMPLE_RECOVERY_ALLOWED_REQUEST_FIELDS = frozenset(
    {"expectedSourceJobId", "recoveryRequestId", "mode"}
)
SAMPLE_TTS_CREDENTIAL_RECOVERY_ALLOWED_REQUEST_FIELDS = frozenset(
    {
        "expectedSourceJobId",
        "expectedParentRecoveryId",
        "recoveryRequestId",
        "mode",
    }
)
SAMPLE_RETRY_REASON_BY_ATTEMPT = {
    2: "approved_stage2_retry",
    3: "approved_stage2_retry_3",
}
SAMPLE_RETRY_SOURCE_ERROR_BY_ATTEMPT = {
    1: "openmaic_sample_generation_stale",
    2: "openmaic_generation_process_restarted",
}
SAMPLE_MAX_GENERATION_ATTEMPTS = 3
SAMPLE_LEGACY_REQUIREMENT_SCHEMA = "mira.openmaic.sample-classroom.v1"
SAMPLE_ATTEMPT_THREE_UPGRADE_FIELDS = frozenset(
    {
        "schemaVersion",
        "requiredClassroom",
        "speechAudioContract",
        "conversationContract",
    }
)
SAMPLE_LEGACY_CONTRACT_FIELDS = frozenset(
    {
        "schemaVersion",
        "sampleMode",
        "authority",
        "course",
        "learnerConstraints",
        "teacher",
        "requiredClassroom",
        "speechAudioContract",
        "generation",
    }
)
SAMPLE_GENERATION_OPTIONS = {
    "enableWebSearch": False,
    "enableImageGeneration": False,
    "enableVideoGeneration": False,
    "enableTTS": True,
    "agentMode": "generate",
}
SAMPLE_REQUIREMENT_SCHEMA = "mira.openmaic.sample-classroom.v2"
SAMPLE_STRUCTURAL_POLICY_MARKER = "MIRA_OPENMAIC_SAMPLE_STRUCTURAL_POLICY_V1"
SAMPLE_AUDIO_METADATA_SCHEMA = "mira.openmaic.speech-audio.v1"
SAMPLE_ASR_PROVIDER_ID = "qwen-asr"
SAMPLE_ASR_MODEL_ID = "qwen3-asr-flash"
FORMAL_RUNTIME_CLASSROOM_CONTRACT = (
    OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CLASSROOM_CONTRACT
)
FORMAL_CORE_REQUIRED_FEATURES = ()
# Backwards-compatible name for callers that imported the former fixed formal
# feature tuple.  It now denotes only the invariant core; widget capabilities
# are derived from the validated classroom by ``_formal_required_features``.
FORMAL_REQUIRED_FEATURES = FORMAL_CORE_REQUIRED_FEATURES
FORMAL_WIDGET_FEATURE_BY_TYPE = {
    "simulation": "simulation",
    "diagram": "diagram",
    "code": "code",
    "game": "html_game",
    "visualization3d": "3d_visualization",
}


def _formal_required_features(evidence: Mapping[str, Any]) -> tuple[str, ...]:
    """Describe capabilities actually emitted by OpenMAIC.

    The professional prompt may ask for slides, quizzes, agents and rich
    interactions, but publication must not turn those preferences into a
    second hard-coded content rubric.  OpenMAIC owns the lesson design; Mira
    records only the capabilities present in the returned artifact.
    """

    features: list[str] = []
    distribution = evidence.get("sceneDistribution")
    if isinstance(distribution, Mapping):
        if int(distribution.get("slide") or 0) > 0:
            features.append("slides")
        if int(distribution.get("quiz") or 0) > 0:
            features.append("quiz")
        if int(distribution.get("pbl") or 0) > 0:
            features.append("pbl")
    if int(
        evidence.get("discussionActionCount")
        if "discussionActionCount" in evidence
        else evidence.get("distinctDiscussionPeerCount")
        or 0
    ) > 0:
        features.append("multi_agent_roundtable")
    if int(
        evidence.get("teacherActionCount")
        if "teacherActionCount" in evidence
        else bool(
            evidence.get("spotlightVerified")
            or evidence.get("widgetHighlightVerified")
        )
    ) > 0:
        features.append("teacher_actions")
    widget_types = evidence.get("widgetTypes")
    if isinstance(widget_types, list):
        for widget_type in widget_types:
            feature = FORMAL_WIDGET_FEATURE_BY_TYPE.get(str(widget_type))
            if feature and feature not in features:
                features.append(feature)
    return tuple(features)


def _legacy_sample_required_classroom() -> dict[str, Any]:
    return {
        "features": [
            "slides",
            "quiz",
            "simulation",
            "multi_agent_roundtable",
            "teacher_actions",
        ],
        "sceneTypes": ["slide", "quiz", "interactive"],
        "interactive": {
            "widgetType": "simulation",
            "widgetOutlineRequired": True,
        },
        "multiAgent": {
            "teacherRequired": True,
            "nonTeacherAgentRequired": True,
            "discussionActionRequired": True,
        },
        "teacherActionsRequired": True,
    }


def _legacy_sample_speech_audio_contract() -> dict[str, Any]:
    return {
        "schemaVersion": "mira.openmaic.speech-audio.v1",
        "requiredForEverySpeechAction": True,
        "audioUrlMustBeReadable": True,
        "metadataField": "audioMetadata",
        "fallbackMetadataField": "fallbackUsed",
        "providerId": "qwen-tts",
        "modelId": "qwen3-tts-flash",
        "voiceId": "Serena",
        "fallbackAllowed": False,
    }


def _sample_required_classroom() -> dict[str, Any]:
    return {
        "features": list(SAMPLE_REQUIRED_FEATURES),
        "exactSceneCount": SAMPLE_EXACT_SCENE_COUNT,
        "minimumSlideScenes": SAMPLE_MINIMUM_SLIDE_SCENES,
        "sceneTypes": ["slide", "quiz", "interactive"],
        "interactive": {
            "requiredWidgetTypes": list(SAMPLE_REQUIRED_WIDGET_TYPES),
            "widgetOutlineRequired": True,
            "embeddedHtmlRequired": True,
            "controlsRequired": True,
        },
        "multiAgent": {
            "teacherRequired": True,
            "minimumPeerAgents": SAMPLE_MINIMUM_PEER_AGENTS,
            "minimumDiscussionActions": SAMPLE_MINIMUM_DISCUSSION_ACTIONS,
            "distinctPeerDiscussionsRequired": True,
        },
        "teacherActionsRequired": True,
        "narration": {
            "requiredForEveryScene": True,
            "transcriptRequired": True,
        },
    }


def _sample_conversation_contract() -> dict[str, Any]:
    return {
        "textChatRequired": True,
        "voiceInputRequired": True,
        "asr": {
            "providerId": SAMPLE_ASR_PROVIDER_ID,
            "modelId": SAMPLE_ASR_MODEL_ID,
            "fallbackAllowed": False,
        },
    }

# The classroom document is generated upstream and remains untrusted after the
# HTTP client's response-size check. These bounds keep validation work and the
# persisted evidence manifest predictable without constraining normal lessons.
MAX_STAGE_AGENTS = 32
MAX_SLIDE_ELEMENTS = 500
MAX_QUIZ_QUESTIONS = 100
MAX_QUIZ_OPTIONS = 20
MAX_SCENE_ACTIONS = 200
MAX_MEDIA_PROBES = 100
MAX_EVIDENCE_SIGNALS_PER_FEATURE = 100
MAX_DSL_IDENTIFIER_LENGTH = 255
EVIDENCE_TRUNCATED_SIGNAL = "evidence-signals-truncated"


class OpenMaicRuntimeServiceError(RuntimeError):
    def __init__(self, code: str, safe_message: str, *, status_code: int = 422):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message
        self.status_code = status_code


class OpenMaicFullRuntimeService:
    """Mira's release, identity and launch boundary around full OpenMAIC."""

    MANIFEST_SCHEMA = "mira.openmaic.runtime-features.v2"
    SOURCE_VERSION = "openmaic@1.0.0"
    SOURCE_COMMIT = "aa2bfb3c1d406c47100c6744d90e788abdf1f6d5"

    def __init__(
        self,
        database_url: str,
        *,
        student_auth_service: StudentAuthService,
        client: OpenMaicFullRuntimeClient | None,
        enabled: bool = False,
        generation_enabled: bool = False,
        public_url: str = "",
        launch_ttl_seconds: int = 60,
        session_ttl_seconds: int = 4 * 60 * 60,
        video_export_enabled: bool = False,
        conversation_probe_service: OpenMaicConversationProbeService | None = None,
        conversation_probe_client: OpenMaicConversationProbeClient | None = None,
        deterministic_recovery_enabled: bool = False,
        deterministic_recovery_redispatch_enabled: bool = False,
        deterministic_recovery_client: OpenMaicDeterministicRecoveryClient | None = None,
        tts_credential_recovery_enabled: bool = False,
        tts_credential_recovery_client: OpenMaicTtsCredentialRecoveryClient | None = None,
        formal_citation_recovery_enabled: bool = False,
        formal_citation_recovery_source_job_id: str = "",
        formal_citation_recovery_client: OpenMaicFormalCitationRecoveryClient | None = None,
        paid_budget_service: Any | None = None,
    ):
        # Imported lazily because the catalog repository's preparation
        # contract intentionally fingerprints this runtime service.
        from repositories.learning_catalog_repository import (
            LearningCatalogRepository,
        )

        self.repository = OpenMaicRuntimeRepository(Database(database_url))
        self.catalog_repository = LearningCatalogRepository(
            self.repository.database
        )
        self.student_auth_service = student_auth_service
        self.client = client
        self.paid_budget_service = paid_budget_service
        self.enabled = bool(enabled)
        self.generation_enabled = bool(generation_enabled)
        self.public_url = str(public_url or "").strip().rstrip("/")
        self.launch_ttl_seconds = int(launch_ttl_seconds)
        self.session_ttl_seconds = int(session_ttl_seconds)
        self.video_export_enabled = bool(video_export_enabled)
        self.conversation_probe_service = conversation_probe_service
        self.conversation_probe_client = conversation_probe_client
        self.deterministic_recovery_enabled = bool(
            deterministic_recovery_enabled
        )
        self.deterministic_recovery_redispatch_enabled = bool(
            deterministic_recovery_redispatch_enabled
        )
        self.deterministic_recovery_client = deterministic_recovery_client
        self.tts_credential_recovery_enabled = bool(
            tts_credential_recovery_enabled
        )
        self.tts_credential_recovery_client = tts_credential_recovery_client
        self.formal_citation_recovery_enabled = bool(
            formal_citation_recovery_enabled
        )
        self.formal_citation_recovery_source_job_id = str(
            formal_citation_recovery_source_job_id or ""
        ).strip()
        self.formal_citation_recovery_client = formal_citation_recovery_client
        if not 30 <= self.launch_ttl_seconds <= 300:
            raise ValueError("OpenMAIC launch TTL must be between 30 and 300 seconds.")
        if not 300 <= self.session_ttl_seconds <= 24 * 60 * 60:
            raise ValueError("OpenMAIC session TTL must be between 5 minutes and 24 hours.")

    def status(self) -> dict[str, Any]:
        availability: dict[str, Any]
        if self.client is None:
            availability = {"available": False, "baseUrlConfigured": False}
            generation_readiness = {
                "ready": False,
                "requiredVersion": "1.0.0",
                "reportedVersion": None,
                "tts": False,
                "runtimePolicy": None,
                "asr": False,
                "asrPolicy": None,
                "structuredScene": None,
                "error": "openmaic_runtime_not_configured",
            }
        else:
            availability = self.client.availability()
            generation_readiness = self.client.sample_generation_readiness()
        return {
            "ok": True,
            "enabled": self.enabled,
            "generationEnabled": self.generation_enabled,
            "deterministicRecoveryEnabled": bool(
                getattr(self, "deterministic_recovery_enabled", False)
            ),
            "ttsCredentialRecoveryEnabled": bool(
                getattr(self, "tts_credential_recovery_enabled", False)
            ),
            "videoExportEnabled": self.video_export_enabled,
            "source": {
                "version": self.SOURCE_VERSION,
                "commit": self.SOURCE_COMMIT,
                "license": "MIT",
            },
            "capabilities": sorted(RUNTIME_FEATURES),
            "sample": {
                "mode": SAMPLE_MODE,
                "gradeCode": SAMPLE_GRADE_CODE,
                "subject": SAMPLE_SUBJECT,
                "skillId": SAMPLE_SKILL_ID,
                "requiredFeatures": list(SAMPLE_REQUIRED_FEATURES),
                "exactSceneCount": SAMPLE_EXACT_SCENE_COUNT,
                "minimumSlideScenes": SAMPLE_MINIMUM_SLIDE_SCENES,
                "requiredWidgetTypes": list(SAMPLE_REQUIRED_WIDGET_TYPES),
                "maxAttempts": SAMPLE_MAX_GENERATION_ATTEMPTS,
                "manualRetries": 2,
                "automaticRetries": 0,
                "staleAfterMs": SAMPLE_GENERATION_STALE_AFTER_MS,
                "generationReadiness": generation_readiness,
            },
            "availability": availability,
        }

    def formal_provider_circuit_status(self) -> dict[str, Any]:
        with self.repository.transaction() as conn:
            row = self.repository.get_formal_provider_circuit(conn)
        if row is None:
            return {
                "status": "unknown",
                "dispatchAllowed": False,
                "providerId": OpenMaicRuntimeRepository.FORMAL_PROVIDER_ID,
                "modelId": OpenMaicRuntimeRepository.FORMAL_PROVIDER_MODEL_ID,
                "reasonCode": "openmaic_formal_provider_probe_required",
                "lastProbeAt": None,
                "probeSucceededAt": None,
            }
        closed = (
            str(row.get("status") or "") == "closed"
            and int(row.get("probe_succeeded_at") or 0) > 0
        )
        return {
            "status": str(row.get("status") or "unknown"),
            "dispatchAllowed": closed,
            "providerId": OpenMaicRuntimeRepository.FORMAL_PROVIDER_ID,
            "modelId": OpenMaicRuntimeRepository.FORMAL_PROVIDER_MODEL_ID,
            "reasonCode": row.get("reason_code"),
            "lastProbeAt": row.get("last_probe_at"),
            "probeSucceededAt": row.get("probe_succeeded_at"),
        }

    def ensure_initial_formal_provider_probe(self) -> dict[str, Any]:
        """Bootstrap a fresh installation once, without retrying an open fuse.

        Persist intent before the external call. A crash or uncertain response
        requires operator reconciliation, including after a worker restart.
        """
        self._require_generation()
        status = self.formal_provider_circuit_status()
        if status['status'] != 'unknown':
            return status
        claimed_at = now_ms()
        with self.repository.transaction() as conn:
            claimed = self.repository.claim_initial_formal_provider_probe(
                conn, now=claimed_at
            )
        if not claimed:
            return self.formal_provider_circuit_status()
        try:
            result = self.client.formal_generation_provider_canary()
        except Exception:
            # The durable pending marker prevents an automatic paid redispatch.
            return self.formal_provider_circuit_status()
        with self.repository.transaction() as conn:
            self.repository.complete_initial_formal_provider_probe(
                conn, claimed_at=claimed_at,
                ready=result.get('ready') is True, now=now_ms(),
            )
        return self.formal_provider_circuit_status()

    def probe_formal_generation_provider(self) -> dict[str, Any]:
        """Run one explicit bounded Provider canary and persist the fuse."""

        self._require_generation()
        timestamp = now_ms()
        result = self.client.formal_generation_provider_canary()
        with self.repository.transaction() as conn:
            if result.get("ready") is True:
                row = self.repository.close_formal_provider_circuit_after_probe(
                    conn,
                    now=timestamp,
                )
            else:
                row = self.repository.record_formal_provider_probe_failure(
                    conn,
                    reason_code="openmaic_formal_provider_canary_failed",
                    now=timestamp,
                )
        return {
            "ok": result.get("ready") is True,
            "ready": result.get("ready") is True,
            "providerId": OpenMaicRuntimeRepository.FORMAL_PROVIDER_ID,
            "modelId": OpenMaicRuntimeRepository.FORMAL_PROVIDER_MODEL_ID,
            "circuit": {
                "status": str(row.get("status") or "open"),
                "dispatchAllowed": str(row.get("status") or "") == "closed",
                "reasonCode": row.get("reason_code"),
                "lastProbeAt": row.get("last_probe_at"),
                "probeSucceededAt": row.get("probe_succeeded_at"),
            },
        }

    def generate_classroom(self, data: Mapping[str, Any]) -> dict[str, Any]:
        """Create the one explicitly approved Stage 2 sample classroom.

        The public/internal caller supplies only an idempotency key and the
        fixed sample-mode assertion.  Course, grade, subject, skill, teacher,
        voice, features and provider options all come from server-owned active
        release/configuration state.
        """

        self._require_generation()
        unexpected = sorted(set(data) - SAMPLE_ALLOWED_REQUEST_FIELDS)
        if unexpected:
            self._fail(
                "openmaic_sample_context_server_owned",
                "样板课的课程、年级、学科、能力、老师和生成参数只能由服务端确定",
                400,
            )
        request_id = _required_identifier(data.get("requestId"), "requestId", 128)
        if str(data.get("sampleMode") or "").strip() != SAMPLE_MODE:
            self._fail(
                "invalid_openmaic_sample_mode",
                f"sampleMode 必须是 {SAMPLE_MODE}",
                400,
            )
        readiness = self.client.sample_generation_readiness()
        if readiness.get("ready") is not True:
            self._fail(
                "openmaic_sample_generation_not_ready",
                "OpenMAIC 1.0.0 尚未启用固定 Qwen3 语音与结构化课件策略",
                503,
            )
        requested_features = SAMPLE_REQUIRED_FEATURES
        required_features = SAMPLE_REQUIRED_FEATURES
        timestamp = now_ms()
        boundary = _sample_boundary()

        with self.repository.transaction() as conn:
            course = self.repository.get_active_release_course_for_boundary(
                conn,
                grade_code=SAMPLE_GRADE_CODE,
                subject=SAMPLE_SUBJECT,
                skill_id=SAMPLE_SKILL_ID,
                curriculum_version=boundary.curriculum_version,
                boundary_version=boundary.boundary_version,
            )
            if course is None:
                self._fail(
                    "openmaic_sample_course_not_released",
                    "一年级数学数感样板课尚未进入当前正式发布目录",
                    409,
                )
            self._validate_sample_course(course, boundary=boundary)
            generation_contract = self._sample_generation_contract(
                course,
                boundary=boundary,
            )
            existing = self.repository.get_by_request_id(
                conn, request_id=request_id, for_update=True
            )
            if existing is not None:
                if (
                    str(existing["course_id"]) != str(course["course_id"])
                    or str(existing["course_version"])
                    != str(course["course_version"])
                ):
                    self._fail(
                        "openmaic_request_conflict",
                        "requestId 已用于另一门课程",
                        409,
                    )
                existing_manifest = self.repository.decode_json(
                    existing.get("feature_manifest_json"), {}
                )
                if existing_manifest.get("generationContract") != generation_contract:
                    self._fail(
                        "openmaic_request_conflict",
                        "requestId 已用于另一版样板课堂合同",
                        409,
                    )
                return self._runtime_payload(existing)
            package_runtime = self.repository.get_for_package(
                conn,
                package_id=str(course["package_id"]),
                package_version=int(course["package_version"]),
                for_update=True,
            )
            if package_runtime is not None:
                terminal = str(package_runtime.get("status") or "") == "failed"
                self._fail(
                    (
                        "openmaic_sample_terminal_failed"
                        if terminal
                        else "openmaic_sample_already_exists"
                    ),
                    (
                        "样板课上一次生成已终结；本阶段不自动重试"
                        if terminal
                        else "这门样板课已经有一个生成任务"
                    ),
                    409,
                )
            runtime_id = new_token("omc")
            manifest = self._requested_manifest(
                requested_features,
                required_features,
                generation_contract=generation_contract,
            )
            runtime = self.repository.create_runtime_classroom(
                conn,
                runtime_id=runtime_id,
                request_id=request_id,
                course=course,
                feature_manifest=manifest,
                now=timestamp,
            )

        requirement = self._build_requirement(
            course,
            requested_features,
            required_features=required_features,
            generation_contract=generation_contract,
        )
        try:
            job = self.client.start_generation(
                requirement=requirement,
                enable_web_search=SAMPLE_GENERATION_OPTIONS["enableWebSearch"],
                enable_image_generation=SAMPLE_GENERATION_OPTIONS[
                    "enableImageGeneration"
                ],
                enable_video_generation=SAMPLE_GENERATION_OPTIONS[
                    "enableVideoGeneration"
                ],
                enable_tts=SAMPLE_GENERATION_OPTIONS["enableTTS"],
                agent_mode=SAMPLE_GENERATION_OPTIONS["agentMode"],
            )
        except OpenMaicFullRuntimeError as exc:
            with self.repository.transaction() as conn:
                self.repository.mark_failed(
                    conn,
                    runtime_id=str(runtime["id"]),
                    error_code=exc.code,
                    error_message_safe=exc.safe_message,
                    now=now_ms(),
                )
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc

        try:
            with self.repository.transaction() as conn:
                marked = self.repository.mark_generating(
                    conn,
                    runtime_id=str(runtime["id"]),
                    upstream_job_id=job.job_id,
                    now=now_ms(),
                )
                if marked is not True:
                    self._fail(
                        "openmaic_generation_persistence_failed",
                        "OpenMAIC 已接受任务，但本地状态未能安全关联；不会自动重发",
                        503,
                    )
                updated = self.repository.get_runtime_classroom(
                    conn, runtime_id=str(runtime["id"])
                )
        except OpenMaicRuntimeServiceError:
            raise
        except Exception as exc:
            raise OpenMaicRuntimeServiceError(
                "openmaic_generation_persistence_failed",
                "OpenMAIC 已接受任务，但本地状态未能安全关联；不会自动重发",
                status_code=503,
            ) from exc
        return self._runtime_payload(updated, upstream_job=job)

    def retry_classroom(
        self, runtime_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Run one explicitly approved retry without reviving its source.

        Each retry is a separate, durable ``pending`` runtime row committed
        before OpenMAIC is called. Seeing that reservation always means
        "observe, never dispatch", including after a process crash or an
        uncertain post-call database failure. Only the fixed attempt-one to
        attempt-two and attempt-two to attempt-three transitions are allowed.
        """

        runtime_key = _required_identifier(runtime_id, "runtimeId", 128)
        if (
            not isinstance(data, Mapping)
            or set(data) != SAMPLE_RETRY_ALLOWED_REQUEST_FIELDS
        ):
            self._fail(
                "openmaic_retry_contract_invalid",
                "人工重试请求只能包含 retryRequestId、expectedPreviousJobId 和 reason",
                400,
            )
        retry_request_id = _required_identifier(
            data.get("retryRequestId"), "retryRequestId", 128
        )
        expected_previous_job_id = _required_identifier(
            data.get("expectedPreviousJobId"),
            "expectedPreviousJobId",
            128,
        )
        reason = str(data.get("reason") or "").strip()
        if reason not in SAMPLE_RETRY_REASON_BY_ATTEMPT.values():
            self._fail(
                "openmaic_retry_reason_invalid",
                "reason 不是已批准的受控重试原因",
                400,
            )

        # A committed retry row is the idempotency record. Return it
        # before runtime health/config checks so an upstream outage cannot hide
        # an already-reserved or externally accepted paid attempt.
        with self.repository.transaction() as conn:
            existing = self.repository.get_by_request_id(
                conn,
                request_id=retry_request_id,
            )
            if existing is not None:
                source, stored_contract, target_attempt = (
                    self._stored_retry_source_context(
                        conn,
                        runtime_id=runtime_key,
                        expected_previous_job_id=expected_previous_job_id,
                    )
                )
                self._validate_retry_reason(reason, target_attempt=target_attempt)
                self._validate_existing_retry_runtime(
                    existing,
                    source=source,
                    target_attempt=target_attempt,
                    retry_request_id=retry_request_id,
                    expected_previous_job_id=expected_previous_job_id,
                    reason=reason,
                    expected_contract=stored_contract,
                )
                return self._retry_payload(existing, idempotent=True)

            # Validate the requested transition before probing OpenMAIC. This
            # makes a forbidden attempt four fail deterministically even when
            # the runtime is temporarily unavailable.
            _source, _stored_contract, target_attempt = (
                self._stored_retry_source_context(
                    conn,
                    runtime_id=runtime_key,
                    expected_previous_job_id=expected_previous_job_id,
                )
            )
            self._validate_retry_reason(reason, target_attempt=target_attempt)

        self._require_generation()
        readiness = self.client.sample_generation_readiness()
        if readiness.get("ready") is not True:
            self._fail(
                "openmaic_sample_generation_not_ready",
                "OpenMAIC 1.0.0 尚未启用固定 Qwen3 语音与结构化课件策略",
                503,
            )

        timestamp = now_ms()
        reserved_runtime_id = new_token("omc")
        with self.repository.transaction() as conn:
            source, course, expected_contract, target_attempt = (
                self._retry_source_context(
                    conn,
                    runtime_id=runtime_key,
                    expected_previous_job_id=expected_previous_job_id,
                    for_update=True,
                )
            )
            self._validate_retry_reason(reason, target_attempt=target_attempt)
            attempts = self.repository.get_package_runtime_attempts(
                conn,
                package_id=str(source["package_id"]),
                package_version=int(source["package_version"]),
                for_update=True,
            )
            target_runtime = next(
                (
                    item
                    for item in attempts
                    if int(item.get("attempt_ordinal") or 1) == target_attempt
                ),
                None,
            )
            if target_runtime is not None:
                if str(target_runtime.get("request_id") or "") == retry_request_id:
                    self._validate_existing_retry_runtime(
                        target_runtime,
                        source=source,
                        target_attempt=target_attempt,
                        retry_request_id=retry_request_id,
                        expected_previous_job_id=expected_previous_job_id,
                        reason=reason,
                        expected_contract=expected_contract,
                    )
                    return self._retry_payload(target_runtime, idempotent=True)
                self._fail(
                    "openmaic_retry_attempt_limit_reached",
                    "这节样板课的三次生成机会已经使用，不能再次调用模型",
                    409,
                )
            attempt_ordinals = [
                int(item.get("attempt_ordinal") or 1) for item in attempts
            ]
            if not (
                len(attempts) == target_attempt - 1
                and attempt_ordinals == list(range(1, target_attempt))
                and str(attempts[-1].get("id") or "") == runtime_key
            ):
                self._fail(
                    "openmaic_retry_attempt_limit_reached",
                    "这节样板课的受控生成链不完整或三次机会已经使用",
                    409,
                )
            request_conflict = self.repository.get_by_request_id(
                conn,
                request_id=retry_request_id,
                for_update=True,
            )
            if request_conflict is not None:
                self._fail(
                    "openmaic_retry_request_conflict",
                    "retryRequestId 已用于另一条任务或不同的人工重试合同",
                    409,
                )
            if source.get("retired_at") is not None:
                self._fail(
                    "openmaic_retry_not_allowed",
                    "本次生成记录已被其他人工重试占用",
                    409,
                )

            pending_manifest = self._requested_manifest(
                SAMPLE_REQUIRED_FEATURES,
                SAMPLE_REQUIRED_FEATURES,
                generation_contract=expected_contract,
            )
            if not self.repository.retire_runtime_for_retry(
                conn,
                runtime_id=runtime_key,
                source_attempt_ordinal=target_attempt - 1,
                now=timestamp,
            ):
                self._fail(
                    "openmaic_retry_reservation_conflict",
                    "人工重试没有安全锁定上一次失败记录",
                    409,
                )
            reserved = self.repository.create_retry_runtime_classroom(
                conn,
                runtime_id=reserved_runtime_id,
                request_id=retry_request_id,
                retry_of_runtime_id=runtime_key,
                retry_reason=reason,
                expected_previous_job_id=expected_previous_job_id,
                attempt_ordinal=target_attempt,
                source_runtime=source,
                feature_manifest=pending_manifest,
                now=timestamp,
            )

        requirement = self._build_requirement(
            course,
            SAMPLE_REQUIRED_FEATURES,
            required_features=SAMPLE_REQUIRED_FEATURES,
            generation_contract=expected_contract,
        )
        try:
            job = self.client.start_generation(
                requirement=requirement,
                enable_web_search=SAMPLE_GENERATION_OPTIONS["enableWebSearch"],
                enable_image_generation=SAMPLE_GENERATION_OPTIONS[
                    "enableImageGeneration"
                ],
                enable_video_generation=SAMPLE_GENERATION_OPTIONS[
                    "enableVideoGeneration"
                ],
                enable_tts=SAMPLE_GENERATION_OPTIONS["enableTTS"],
                agent_mode=SAMPLE_GENERATION_OPTIONS["agentMode"],
            )
        except OpenMaicFullRuntimeError as exc:
            try:
                with self.repository.transaction() as conn:
                    self.repository.mark_failed(
                        conn,
                        runtime_id=str(reserved["id"]),
                        error_code=exc.code,
                        error_message_safe=exc.safe_message,
                        now=now_ms(),
                    )
            except Exception as persistence_error:
                raise OpenMaicRuntimeServiceError(
                    "openmaic_generation_persistence_failed",
                    "重试启动失败，但本地终态未能确认；不会自动重发",
                    status_code=503,
                ) from persistence_error
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc

        try:
            with self.repository.transaction() as conn:
                marked = self.repository.mark_generating(
                    conn,
                    runtime_id=str(reserved["id"]),
                    upstream_job_id=job.job_id,
                    now=now_ms(),
                )
                if marked is not True:
                    self._fail(
                        "openmaic_generation_persistence_failed",
                        "OpenMAIC 已接受受控重试任务，但本地状态未能安全关联；不会重发",
                        503,
                    )
                updated = self.repository.get_runtime_classroom(
                    conn,
                    runtime_id=str(reserved["id"]),
                )
        except OpenMaicRuntimeServiceError:
            raise
        except Exception as exc:
            raise OpenMaicRuntimeServiceError(
                "openmaic_generation_persistence_failed",
                "OpenMAIC 已接受受控重试任务，但本地状态未能安全关联；不会重发",
                status_code=503,
            ) from exc
        return self._retry_payload(updated, idempotent=False)

    def recover_classroom(
        self, runtime_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Reserve and dispatch the one deterministic, zero-LLM recovery.

        This is not a generation retry.  It keeps attempt three and its failed
        upstream job immutable, creates no runtime row, and never calls
        ``start_generation``.  The same request key is observation-only after
        its reservation commits, including the pre-dispatch crash window.
        """

        runtime_key = _required_identifier(runtime_id, "runtimeId", 128)
        if (
            not isinstance(data, Mapping)
            or set(data) != SAMPLE_RECOVERY_ALLOWED_REQUEST_FIELDS
        ):
            self._fail(
                "openmaic_recovery_contract_invalid",
                "确定性恢复请求只能包含 expectedSourceJobId、recoveryRequestId 和 mode",
                400,
            )
        expected_source_job_id = _required_identifier(
            data.get("expectedSourceJobId"), "expectedSourceJobId", 128
        )
        recovery_request_id = _required_identifier(
            data.get("recoveryRequestId"), "recoveryRequestId", 128
        )
        if str(data.get("mode") or "").strip() != RECOVERY_MODE:
            self._fail(
                "openmaic_recovery_mode_invalid",
                f"mode 必须是 {RECOVERY_MODE}",
                400,
            )

        # A committed reservation is the idempotency authority.  Return it
        # before health checks and make zero upstream calls on every replay.
        with self.repository.transaction() as conn:
            existing = self.repository.get_deterministic_recovery_by_request(
                conn, recovery_request_id=recovery_request_id
            )
            if existing is not None:
                self._validate_existing_recovery(
                    existing,
                    runtime_id=runtime_key,
                    expected_source_job_id=expected_source_job_id,
                    recovery_request_id=recovery_request_id,
                )
                return self._recovery_payload(existing, idempotent=True)
            runtime_recovery = (
                self.repository.get_deterministic_recovery_by_runtime(
                    conn, runtime_id=runtime_key
                )
            )
            if runtime_recovery is not None:
                self._fail(
                    "openmaic_recovery_already_used",
                    "这条第三次生成记录已经使用过唯一的确定性恢复机会",
                    409,
                )
            source, contract = self._deterministic_recovery_source_context(
                conn,
                runtime_id=runtime_key,
                expected_source_job_id=expected_source_job_id,
            )

        self._require_deterministic_recovery()
        assert self.deterministic_recovery_client is not None

        # Prove the exact enabled/source/policy/patch attestation before the
        # local reservation and before any endpoint capable of starting TTS.
        # Idempotent replays returned above make zero health/source calls.
        try:
            self.deterministic_recovery_client.verify_runtime_policy(
                source_job_id=expected_source_job_id
            )
        except OpenMaicDeterministicRecoveryError as exc:
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc

        # This authenticated GET is read-only.  Its canonical hash is frozen
        # into the local reservation before the external recovery POST.
        try:
            source_snapshot = (
                self.deterministic_recovery_client.get_source_snapshot(
                    source_job_id=expected_source_job_id
                )
            )
        except OpenMaicDeterministicRecoveryError as exc:
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc

        timestamp = now_ms()
        local_recovery_id = new_token("omdr")
        expected_upstream_recovery_id, _request_id_sha256 = (
            deterministic_recovery_identity(
                expected_source_job_id, recovery_request_id
            )
        )
        contract_sha256 = _canonical_sha256(contract)
        with self.repository.transaction() as conn:
            existing = self.repository.get_deterministic_recovery_by_request(
                conn,
                recovery_request_id=recovery_request_id,
                for_update=True,
            )
            if existing is not None:
                self._validate_existing_recovery(
                    existing,
                    runtime_id=runtime_key,
                    expected_source_job_id=expected_source_job_id,
                    recovery_request_id=recovery_request_id,
                )
                return self._recovery_payload(existing, idempotent=True)
            if self.repository.get_deterministic_recovery_by_runtime(
                conn, runtime_id=runtime_key, for_update=True
            ) is not None:
                self._fail(
                    "openmaic_recovery_already_used",
                    "这条第三次生成记录已经使用过唯一的确定性恢复机会",
                    409,
                )
            source, locked_contract = self._deterministic_recovery_source_context(
                conn,
                runtime_id=runtime_key,
                expected_source_job_id=expected_source_job_id,
                for_update=True,
            )
            if _canonical_sha256(locked_contract) != contract_sha256:
                self._fail(
                    "openmaic_recovery_source_changed",
                    "确定性恢复的固定课件合同已变化",
                    409,
                )
            try:
                recovery = self.repository.reserve_deterministic_recovery(
                    conn,
                    recovery_id=local_recovery_id,
                    recovery_request_id=recovery_request_id,
                    runtime=source,
                    expected_source_job_id=expected_source_job_id,
                    expected_upstream_recovery_id=(
                        expected_upstream_recovery_id
                    ),
                    source_job_snapshot=source_snapshot.to_audit_source(),
                    source_generation_contract_sha256=contract_sha256,
                    mode=RECOVERY_MODE,
                    kind=RECOVERY_KIND,
                    source_scenes_generated=RECOVERY_SOURCE_SCENES_GENERATED,
                    source_total_scenes=RECOVERY_SOURCE_TOTAL_SCENES,
                    tts_provider_id="qwen-tts",
                    tts_model_id="qwen3-tts-flash",
                    tts_voice_id="Serena",
                    now=timestamp,
                )
            except RuntimeError as exc:
                raise OpenMaicRuntimeServiceError(
                    "openmaic_recovery_reservation_conflict",
                    "确定性恢复没有安全锁定第三次失败记录",
                    status_code=409,
                ) from exc

        try:
            upstream = self.deterministic_recovery_client.start_recovery(
                source_job_id=expected_source_job_id,
                recovery_request_id=recovery_request_id,
                expected_source_snapshot=source_snapshot,
            )
        except OpenMaicDeterministicRecoveryError as exc:
            # Any transport/response failure except an explicit upstream HTTP
            # rejection is ambiguous: patch 0007 may already have claimed the
            # request and scheduled TTS before the response was lost.  Keep the
            # local reservation and reconcile the deterministic recovery id on
            # the independent GET route.  Replays never POST again.
            explicitly_rejected = (
                exc.code == "openmaic_recovery_upstream_rejected"
                and 400 <= int(exc.status_code) < 500
            )
            if not explicitly_rejected:
                raise OpenMaicRuntimeServiceError(
                    "openmaic_recovery_dispatch_uncertain",
                    "确定性恢复可能已被 OpenMAIC 接受；已保留记录并将只读查询，不会重发",
                    status_code=503,
                ) from exc
            self._terminally_fail_recovery(
                recovery_id=local_recovery_id,
                runtime_id=runtime_key,
                error_code=exc.code,
                error_message_safe=exc.safe_message,
            )
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc

        try:
            with self.repository.transaction() as conn:
                attached = self.repository.attach_deterministic_recovery_receipt(
                    conn,
                    recovery_id=local_recovery_id,
                    upstream_recovery_id=upstream.recovery_id,
                    source=upstream.source,
                    policy=upstream.policy,
                    calls=upstream.calls,
                    receipt=upstream.audit_receipt(),
                    now=now_ms(),
                )
                recovery = self.repository.get_deterministic_recovery_by_runtime(
                    conn, runtime_id=runtime_key
                )
                if recovery is None or (
                    not attached
                    and str(recovery.get("upstream_recovery_id") or "")
                    != expected_upstream_recovery_id
                ):
                    raise RuntimeError("openmaic recovery receipt attach conflict")
        except Exception as exc:
            # The deterministic upstream id lets status polling safely attach
            # the accepted record after a local transaction failure.  Do not
            # terminalize and do not risk another POST.
            code = "openmaic_recovery_persistence_uncertain"
            message = (
                "OpenMAIC 可能已接受确定性恢复，但本地回执尚未关联；"
                "后续只读查询将继续核对，不会重发"
            )
            raise OpenMaicRuntimeServiceError(
                code, message, status_code=503
            ) from exc

        assert recovery is not None
        return self._handle_deterministic_recovery_result(
            recovery, upstream, idempotent=False
        )

    def redispatch_deterministic_recovery(
        self, runtime_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Dispatch the same recovery once after an audited pre-claim 403."""

        runtime_key = _required_identifier(runtime_id, "runtimeId", 128)
        if (
            not isinstance(data, Mapping)
            or set(data) != SAMPLE_RECOVERY_ALLOWED_REQUEST_FIELDS
        ):
            self._fail(
                "openmaic_recovery_contract_invalid",
                "确定性恢复请求只能包含 expectedSourceJobId、recoveryRequestId 和 mode",
                400,
            )
        expected_source_job_id = _required_identifier(
            data.get("expectedSourceJobId"), "expectedSourceJobId", 128
        )
        recovery_request_id = _required_identifier(
            data.get("recoveryRequestId"), "recoveryRequestId", 128
        )
        if str(data.get("mode") or "").strip() != RECOVERY_MODE:
            self._fail(
                "openmaic_recovery_mode_invalid",
                f"mode 必须是 {RECOVERY_MODE}",
                400,
            )
        expected_upstream_recovery_id, _request_hash = (
            deterministic_recovery_identity(
                expected_source_job_id, recovery_request_id
            )
        )

        with self.repository.transaction() as conn:
            recovery = self.repository.get_deterministic_recovery_by_request(
                conn, recovery_request_id=recovery_request_id
            )
            if recovery is None:
                self._fail(
                    "openmaic_recovery_not_found",
                    "没有找到可补发的确定性恢复记录",
                    404,
                )
            self._validate_existing_recovery(
                recovery,
                runtime_id=runtime_key,
                expected_source_job_id=expected_source_job_id,
                recovery_request_id=recovery_request_id,
            )
            if int(recovery.get("dispatch_count") or 1) == 2:
                return self._recovery_payload(recovery, idempotent=True)
            source, contract = self._deterministic_recovery_source_context(
                conn,
                runtime_id=runtime_key,
                expected_source_job_id=expected_source_job_id,
            )
            self._validate_deterministic_recovery_redispatch_candidate(
                recovery,
                runtime=source,
                expected_upstream_recovery_id=expected_upstream_recovery_id,
                expected_contract_sha256=_canonical_sha256(contract),
            )

        self._require_deterministic_recovery_redispatch()
        assert self.deterministic_recovery_client is not None

        try:
            self.deterministic_recovery_client.verify_runtime_policy(
                source_job_id=expected_source_job_id
            )
            source_snapshot = (
                self.deterministic_recovery_client.get_source_snapshot(
                    source_job_id=expected_source_job_id
                )
            )
            if (
                source_snapshot.job_id != expected_source_job_id
                or source_snapshot.completed_at
                != str(recovery["source_completed_at"])
                or source_snapshot.job_snapshot_sha256
                != str(recovery["source_job_snapshot_sha256"])
            ):
                self._fail(
                    "openmaic_recovery_source_changed",
                    "确定性恢复源任务与首次冻结快照不一致",
                    409,
                )
            self.deterministic_recovery_client.assert_recovery_absent(
                source_job_id=expected_source_job_id,
                expected_recovery_id=expected_upstream_recovery_id,
                recovery_request_id=recovery_request_id,
            )
        except OpenMaicDeterministicRecoveryError as exc:
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc

        timestamp = now_ms()
        try:
            with self.repository.transaction() as conn:
                recovery = self.repository.get_deterministic_recovery_by_request(
                    conn,
                    recovery_request_id=recovery_request_id,
                    for_update=True,
                )
                if recovery is None:
                    raise RuntimeError("openmaic recovery redispatch row missing")
                self._validate_existing_recovery(
                    recovery,
                    runtime_id=runtime_key,
                    expected_source_job_id=expected_source_job_id,
                    recovery_request_id=recovery_request_id,
                )
                if int(recovery.get("dispatch_count") or 1) == 2:
                    return self._recovery_payload(recovery, idempotent=True)
                source, contract = self._deterministic_recovery_source_context(
                    conn,
                    runtime_id=runtime_key,
                    expected_source_job_id=expected_source_job_id,
                    for_update=True,
                )
                self._validate_deterministic_recovery_redispatch_candidate(
                    recovery,
                    runtime=source,
                    expected_upstream_recovery_id=(
                        expected_upstream_recovery_id
                    ),
                    expected_contract_sha256=_canonical_sha256(contract),
                )
                reserved = (
                    self.repository.reserve_deterministic_recovery_redispatch(
                        conn,
                        recovery_id=str(recovery["id"]),
                        runtime_id=runtime_key,
                        recovery_request_id=recovery_request_id,
                        source_upstream_job_id=expected_source_job_id,
                        expected_upstream_recovery_id=(
                            expected_upstream_recovery_id
                        ),
                        source_job_snapshot_sha256=(
                            source_snapshot.job_snapshot_sha256
                        ),
                        source_generation_contract_sha256=(
                            _canonical_sha256(contract)
                        ),
                        now=timestamp,
                    )
                )
        except OpenMaicRuntimeServiceError:
            raise
        except RuntimeError as exc:
            with self.repository.transaction() as conn:
                current = self.repository.get_deterministic_recovery_by_request(
                    conn, recovery_request_id=recovery_request_id
                )
            if current is not None:
                self._validate_existing_recovery(
                    current,
                    runtime_id=runtime_key,
                    expected_source_job_id=expected_source_job_id,
                    recovery_request_id=recovery_request_id,
                )
                if int(current.get("dispatch_count") or 1) == 2:
                    return self._recovery_payload(current, idempotent=True)
            raise OpenMaicRuntimeServiceError(
                "openmaic_recovery_redispatch_conflict",
                "同一确定性恢复补发没有取得唯一派发权",
                status_code=409,
            ) from exc

        try:
            upstream = self.deterministic_recovery_client.start_recovery(
                source_job_id=expected_source_job_id,
                recovery_request_id=recovery_request_id,
                expected_source_snapshot=source_snapshot,
            )
        except OpenMaicDeterministicRecoveryError as exc:
            explicitly_rejected = (
                exc.code == "openmaic_recovery_upstream_rejected"
                and 400 <= int(exc.status_code) < 500
            )
            if not explicitly_rejected:
                raise OpenMaicRuntimeServiceError(
                    "openmaic_recovery_dispatch_uncertain",
                    "确定性恢复补发可能已被接受；后续只读查询且不会第三次派发",
                    status_code=503,
                ) from exc
            self._terminally_fail_recovery(
                recovery_id=str(reserved["id"]),
                runtime_id=runtime_key,
                error_code=exc.code,
                error_message_safe=exc.safe_message,
            )
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc

        try:
            with self.repository.transaction() as conn:
                attached = self.repository.attach_deterministic_recovery_receipt(
                    conn,
                    recovery_id=str(reserved["id"]),
                    upstream_recovery_id=upstream.recovery_id,
                    source=upstream.source,
                    policy=upstream.policy,
                    calls=upstream.calls,
                    receipt=upstream.audit_receipt(),
                    now=now_ms(),
                )
                current = self.repository.get_deterministic_recovery_by_runtime(
                    conn, runtime_id=runtime_key
                )
                if current is None or (
                    not attached
                    and str(current.get("upstream_recovery_id") or "")
                    != expected_upstream_recovery_id
                ):
                    raise RuntimeError("openmaic recovery redispatch attach conflict")
        except Exception as exc:
            raise OpenMaicRuntimeServiceError(
                "openmaic_recovery_persistence_uncertain",
                "OpenMAIC 可能已接受补发，但本地回执尚未关联；不会第三次派发",
                status_code=503,
            ) from exc
        assert current is not None
        return self._handle_deterministic_recovery_result(
            current, upstream, idempotent=False
        )

    def deterministic_recovery_status(self, runtime_id: str) -> dict[str, Any]:
        """Poll only the independent 0007 recovery record, never generation."""

        runtime_key = _required_identifier(runtime_id, "runtimeId", 128)
        self._require_deterministic_recovery()
        assert self.deterministic_recovery_client is not None
        with self.repository.transaction() as conn:
            recovery = self.repository.get_deterministic_recovery_by_runtime(
                conn, runtime_id=runtime_key
            )
        if recovery is None:
            self._fail(
                "openmaic_recovery_not_found",
                "没有找到这条确定性恢复记录",
                404,
            )
        status = str(recovery.get("status") or "")
        if status in {"succeeded", "failed"}:
            return self._recovery_payload(recovery, idempotent=True)
        if status == "validating":
            if self._deterministic_recovery_is_stale(recovery):
                self._terminally_fail_stale_recovery(
                    recovery,
                    error_code="openmaic_recovery_validation_interrupted",
                    error_message_safe=(
                        "确定性恢复验证进程中断，已终结且不会再次恢复"
                    ),
                )
                with self.repository.transaction() as conn:
                    recovery = (
                        self.repository.get_deterministic_recovery_by_runtime(
                            conn, runtime_id=runtime_key
                        )
                    )
            assert recovery is not None
            return self._recovery_payload(recovery, idempotent=True)
        upstream_recovery_id = str(
            recovery.get("upstream_recovery_id") or ""
        ).strip()
        expected_upstream_recovery_id = str(
            recovery.get("expected_upstream_recovery_id") or ""
        ).strip()
        if not expected_upstream_recovery_id or (
            upstream_recovery_id
            and upstream_recovery_id != expected_upstream_recovery_id
        ):
            self._terminally_fail_recovery(
                recovery_id=str(recovery["id"]),
                runtime_id=runtime_key,
                error_code="openmaic_recovery_identity_mismatch",
                error_message_safe=(
                    "确定性恢复的本地上游编号不符合固定幂等合同"
                ),
            )
            with self.repository.transaction() as conn:
                terminal = self.repository.get_deterministic_recovery_by_runtime(
                    conn, runtime_id=runtime_key
                )
            assert terminal is not None
            return self._recovery_payload(terminal, idempotent=True)
        source_snapshot = OpenMaicRecoverySourceSnapshot(
            job_id=str(recovery["source_upstream_job_id"]),
            completed_at=str(recovery["source_completed_at"]),
            job_snapshot_sha256=str(recovery["source_job_snapshot_sha256"]),
        )
        try:
            upstream = self.deterministic_recovery_client.get_recovery(
                source_job_id=str(recovery["source_upstream_job_id"]),
                expected_recovery_id=expected_upstream_recovery_id,
                recovery_request_id=str(recovery["recovery_request_id"]),
                expected_source_snapshot=source_snapshot,
            )
        except OpenMaicDeterministicRecoveryError as exc:
            if self._deterministic_recovery_is_stale(recovery):
                self._terminally_fail_stale_recovery(
                    recovery,
                    error_code="openmaic_recovery_upstream_stale",
                    error_message_safe=(
                        "确定性恢复的上游记录长期没有可验证进展，已终结且不会重发"
                    ),
                )
                with self.repository.transaction() as conn:
                    terminal = (
                        self.repository.get_deterministic_recovery_by_runtime(
                            conn, runtime_id=runtime_key
                        )
                    )
                assert terminal is not None
                return self._recovery_payload(terminal, idempotent=True)
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc
        if not upstream_recovery_id:
            try:
                with self.repository.transaction() as conn:
                    attached = self.repository.attach_deterministic_recovery_receipt(
                        conn,
                        recovery_id=str(recovery["id"]),
                        upstream_recovery_id=upstream.recovery_id,
                        source=upstream.source,
                        policy=upstream.policy,
                        calls=upstream.calls,
                        receipt=upstream.audit_receipt(),
                        now=now_ms(),
                    )
                    current = (
                        self.repository.get_deterministic_recovery_by_runtime(
                            conn, runtime_id=runtime_key
                        )
                    )
                if current is None or (
                    not attached
                    and str(current.get("upstream_recovery_id") or "")
                    != expected_upstream_recovery_id
                ):
                    raise RuntimeError("openmaic recovery reconcile attach conflict")
                recovery = current
            except Exception as exc:
                raise OpenMaicRuntimeServiceError(
                    "openmaic_recovery_persistence_uncertain",
                    "已找到确定性恢复记录，但本地回执尚未安全关联；不会重发",
                    status_code=503,
                ) from exc
        return self._handle_deterministic_recovery_result(
            recovery, upstream, idempotent=True
        )

    def recover_tts_credentials(
        self, runtime_id: str, data: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Append and dispatch the sole TTS-only child of the failed parent."""

        (
            runtime_key,
            expected_source_job_id,
            expected_parent_upstream_id,
            recovery_request_id,
        ) = self._tts_credential_request(runtime_id, data)

        with self.repository.transaction() as conn:
            existing = self.repository.get_tts_credential_recovery_by_request(
                conn, recovery_request_id=recovery_request_id
            )
            if existing is not None:
                self._validate_existing_tts_credential_recovery(
                    existing,
                    runtime_id=runtime_key,
                    expected_source_job_id=expected_source_job_id,
                    expected_parent_upstream_id=expected_parent_upstream_id,
                    recovery_request_id=recovery_request_id,
                )
                return self._tts_credential_payload(existing, idempotent=True)
            if self.repository.get_tts_credential_recovery_by_runtime(
                conn, runtime_id=runtime_key
            ) is not None:
                self._fail(
                    "openmaic_tts_credential_recovery_already_used",
                    "该终态恢复已经拥有唯一的 TTS 凭证恢复子记录",
                    409,
                )
            runtime, parent, contract = self._tts_credential_source_context(
                conn,
                runtime_id=runtime_key,
                expected_source_job_id=expected_source_job_id,
                expected_parent_upstream_id=expected_parent_upstream_id,
            )
            parent_hashes = self._tts_credential_parent_hashes(parent)

        self._require_tts_credential_recovery()
        assert self.tts_credential_recovery_client is not None
        assert self.deterministic_recovery_client is not None
        try:
            self.tts_credential_recovery_client.verify_runtime_policy(
                source_job_id=expected_source_job_id,
                parent_recovery_id=expected_parent_upstream_id,
            )
            parent_upstream = self.deterministic_recovery_client.get_recovery(
                source_job_id=expected_source_job_id,
                expected_recovery_id=expected_parent_upstream_id,
                recovery_request_id=str(parent["recovery_request_id"]),
                expected_source_snapshot=OpenMaicRecoverySourceSnapshot(
                    job_id=expected_source_job_id,
                    completed_at=str(parent["source_completed_at"]),
                    job_snapshot_sha256=str(
                        parent["source_job_snapshot_sha256"]
                    ),
                ),
            )
            self._validate_tts_credential_parent_upstream(
                parent_upstream,
                parent=parent,
                parent_hashes=parent_hashes,
            )
            expected_child_id, _request_hash = (
                tts_credential_recovery_identity(
                    expected_source_job_id,
                    expected_parent_upstream_id,
                    recovery_request_id,
                )
            )
            self.tts_credential_recovery_client.assert_recovery_absent(
                source_job_id=expected_source_job_id,
                parent_recovery_id=expected_parent_upstream_id,
                expected_recovery_id=expected_child_id,
                recovery_request_id=recovery_request_id,
            )
        except (
            OpenMaicDeterministicRecoveryError,
            OpenMaicTtsCredentialRecoveryError,
        ) as exc:
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc

        local_child_id = new_token("omtc")
        expected_classroom_id = tts_credential_classroom_identity(
            expected_child_id
        )
        contract_sha256 = _canonical_sha256(contract)
        timestamp = now_ms()
        try:
            with self.repository.transaction() as conn:
                existing = (
                    self.repository.get_tts_credential_recovery_by_request(
                        conn,
                        recovery_request_id=recovery_request_id,
                        for_update=True,
                    )
                )
                if existing is not None:
                    self._validate_existing_tts_credential_recovery(
                        existing,
                        runtime_id=runtime_key,
                        expected_source_job_id=expected_source_job_id,
                        expected_parent_upstream_id=(
                            expected_parent_upstream_id
                        ),
                        recovery_request_id=recovery_request_id,
                    )
                    return self._tts_credential_payload(
                        existing, idempotent=True
                    )
                runtime, parent, locked_contract = (
                    self._tts_credential_source_context(
                        conn,
                        runtime_id=runtime_key,
                        expected_source_job_id=expected_source_job_id,
                        expected_parent_upstream_id=(
                            expected_parent_upstream_id
                        ),
                        for_update=True,
                    )
                )
                locked_hashes = self._tts_credential_parent_hashes(parent)
                if (
                    locked_hashes != parent_hashes
                    or _canonical_sha256(locked_contract) != contract_sha256
                ):
                    self._fail(
                        "openmaic_tts_credential_parent_changed",
                        "终态父恢复记录或固定课堂合同已变化",
                        409,
                    )
                child = self.repository.reserve_tts_credential_recovery(
                    conn,
                    recovery_id=local_child_id,
                    recovery_request_id=recovery_request_id,
                    runtime_id=runtime_key,
                    parent_recovery_id=str(parent["id"]),
                    expected_source_job_id=expected_source_job_id,
                    parent_db_snapshot_sha256=parent_hashes["db"],
                    parent_receipt_sha256=parent_hashes["receipt"],
                    parent_runtime_snapshot_sha256=parent_hashes["runtime"],
                    expected_upstream_child_id=expected_child_id,
                    expected_upstream_classroom_id=expected_classroom_id,
                    mode=TTS_CREDENTIAL_RECOVERY_MODE,
                    kind=TTS_CREDENTIAL_RECOVERY_KIND,
                    tts_provider_id="qwen-tts",
                    tts_model_id="qwen3-tts-flash",
                    tts_voice_id="Serena",
                    now=timestamp,
                )
        except OpenMaicRuntimeServiceError:
            raise
        except Exception as exc:
            with self.repository.transaction() as conn:
                current = (
                    self.repository.get_tts_credential_recovery_by_request(
                        conn, recovery_request_id=recovery_request_id
                    )
                )
            if current is not None:
                self._validate_existing_tts_credential_recovery(
                    current,
                    runtime_id=runtime_key,
                    expected_source_job_id=expected_source_job_id,
                    expected_parent_upstream_id=expected_parent_upstream_id,
                    recovery_request_id=recovery_request_id,
                )
                return self._tts_credential_payload(
                    current, idempotent=True
                )
            raise OpenMaicRuntimeServiceError(
                "openmaic_tts_credential_reservation_conflict",
                "TTS 凭证恢复没有安全锁定唯一子记录",
                status_code=409,
            ) from exc

        try:
            upstream = self.tts_credential_recovery_client.start_recovery(
                source_job_id=expected_source_job_id,
                parent_recovery_id=expected_parent_upstream_id,
                recovery_request_id=recovery_request_id,
            )
        except OpenMaicTtsCredentialRecoveryError as exc:
            explicit_rejection = 400 <= int(exc.status_code) < 500
            if not explicit_rejection:
                raise OpenMaicRuntimeServiceError(
                    "openmaic_tts_credential_dispatch_uncertain",
                    "TTS 凭证恢复可能已被接受，后续只读查询且不会重发",
                    status_code=503,
                ) from exc
            failed = self._terminally_fail_tts_credential_recovery(
                child,
                error_code=exc.code,
                error_message_safe=exc.safe_message,
            )
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc

        child = self._attach_tts_credential_recovery(child, upstream)
        return self._handle_tts_credential_recovery_result(
            child, upstream, idempotent=False
        )

    def tts_credential_recovery_status(
        self, runtime_id: str
    ) -> dict[str, Any]:
        runtime_key = _required_identifier(runtime_id, "runtimeId", 128)
        self._require_tts_credential_recovery()
        assert self.tts_credential_recovery_client is not None
        with self.repository.transaction() as conn:
            child = self.repository.get_tts_credential_recovery_by_runtime(
                conn, runtime_id=runtime_key
            )
        if child is None:
            self._fail(
                "openmaic_tts_credential_recovery_not_found",
                "没有找到 TTS 凭证恢复子记录",
                404,
            )
        if str(child.get("status") or "") in {"succeeded", "failed"}:
            return self._tts_credential_payload(child, idempotent=True)
        if str(child.get("status") or "") == "publishing":
            if self._tts_credential_recovery_is_stale(child):
                self._terminally_fail_stale_tts_credential_recovery(
                    child,
                    error_code="openmaic_tts_credential_publication_stale",
                    error_message_safe=(
                        "TTS 凭证恢复发布长期未完成，已终结且不会重跑"
                    ),
                )
                with self.repository.transaction() as conn:
                    child = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn, runtime_id=runtime_key
                        )
                    )
                assert child is not None
            return self._tts_credential_payload(child, idempotent=True)
        if str(child.get("status") or "") == "validating":
            return self._resume_tts_credential_validation(child)
        expected_child_id = str(child["expected_upstream_child_id"])
        try:
            upstream = self.tts_credential_recovery_client.get_recovery(
                source_job_id=str(child["source_upstream_job_id"]),
                parent_recovery_id=str(child["parent_upstream_recovery_id"]),
                expected_recovery_id=expected_child_id,
                recovery_request_id=str(child["recovery_request_id"]),
            )
        except OpenMaicTtsCredentialRecoveryError as exc:
            if self._tts_credential_recovery_is_stale(child):
                self._terminally_fail_stale_tts_credential_recovery(
                    child,
                    error_code="openmaic_tts_credential_upstream_stale",
                    error_message_safe=(
                        "TTS 凭证恢复上游长期没有可验证记录，已终结且不会重发"
                    ),
                )
                with self.repository.transaction() as conn:
                    terminal = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn, runtime_id=runtime_key
                        )
                    )
                assert terminal is not None
                return self._tts_credential_payload(terminal, idempotent=True)
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc
        if not child.get("upstream_child_id"):
            child = self._attach_tts_credential_recovery(child, upstream)
        return self._handle_tts_credential_recovery_result(
            child, upstream, idempotent=True
        )

    def start_formal_citation_recovery(self, runtime_id: str) -> dict[str, Any]:
        """Recover the exact second formal attempt without a provider dispatch."""

        self._require_formal_citation_recovery()
        assert self.formal_citation_recovery_client is not None
        assert self.client is not None
        runtime_key = _required_identifier(runtime_id, "runtimeId", 128)
        with self.repository.transaction() as conn:
            runtime = self.repository.get_runtime_classroom(
                conn, runtime_id=runtime_key
            )
            existing = self.repository.get_formal_citation_recovery_by_runtime(
                conn, runtime_id=runtime_key
            )
        if runtime is None:
            self._fail(
                "openmaic_formal_citation_recovery_not_found",
                "没有找到可恢复的正式课堂尝试",
                404,
            )
        source_job_id = str(runtime.get("upstream_job_id") or "")
        if source_job_id != self.formal_citation_recovery_source_job_id:
            self._fail(
                "openmaic_formal_citation_recovery_source_mismatch",
                "正式课堂不是配置中唯一允许恢复的第二次尝试",
                409,
            )
        manifest = self.repository.decode_json(
            runtime.get("feature_manifest_json"), {}
        )
        generation_contract = (
            manifest.get("generationContract")
            if isinstance(manifest, Mapping)
            else None
        )
        formal_contract = (
            manifest.get("formalRuntimeContract")
            if isinstance(manifest, Mapping)
            else None
        )
        if (
            not isinstance(generation_contract, Mapping)
            or formal_contract != FORMAL_RUNTIME_CLASSROOM_CONTRACT
        ):
            self._fail(
                "openmaic_formal_citation_recovery_source_mismatch",
                "正式课堂引用恢复缺少原始生成合同",
                409,
            )
        formal_input_sha256 = self._formal_input_sha256(
            runtime_request_id=str(runtime["request_id"]),
            generation_contract=generation_contract,
            formal_contract=formal_contract,
            paid_budget=manifest.get("paidBudget"),
        )
        recovery_request_id = f"mira-fcr-{runtime_key}"
        local_recovery_id = "formal_citation_recovery_" + hashlib.sha256(
            (
                f"{runtime_key}:{source_job_id}:{recovery_request_id}:"
                f"{formal_input_sha256}"
            ).encode("utf-8")
        ).hexdigest()[:48]

        if existing is None:
            try:
                source_job = self.client.get_generation_job(
                    source_job_id, formal=True
                )
            except OpenMaicFullRuntimeError as exc:
                raise OpenMaicRuntimeServiceError(
                    exc.code, exc.safe_message, status_code=exc.status_code
                ) from exc
            if not (
                source_job.status == "failed"
                and source_job.error == FORMAL_CITATION_RECOVERY_SOURCE_ERROR
                and OpenMaicFullRuntimeClient.formal_job_identity_matches(
                    source_job,
                    runtime_request_id=str(runtime["request_id"]),
                    formal_input_sha256=formal_input_sha256,
                )
            ):
                self._fail(
                    "openmaic_formal_citation_recovery_source_mismatch",
                    "OpenMAIC 没有证明该任务是可恢复的引用缺失终态",
                    409,
                )
            with self.repository.transaction() as conn:
                existing = self.repository.reserve_formal_citation_recovery(
                    conn,
                    recovery_id=local_recovery_id,
                    recovery_request_id=recovery_request_id,
                    runtime_id=runtime_key,
                    expected_upstream_job_id=source_job_id,
                    formal_input_sha256=formal_input_sha256,
                    now=now_ms(),
                )

        if existing.get("upstream_recovery_id"):
            return self.formal_citation_recovery_status(runtime_key)
        try:
            recovery = self.formal_citation_recovery_client.start_recovery(
                source_job_id=source_job_id,
                recovery_request_id=recovery_request_id,
                runtime_request_id=str(runtime["request_id"]),
                formal_input_sha256=formal_input_sha256,
            )
        except OpenMaicFormalCitationRecoveryError as exc:
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc
        return self._record_formal_citation_recovery(runtime, recovery)

    def formal_citation_recovery_status(
        self, runtime_id: str
    ) -> dict[str, Any]:
        self._require_formal_citation_recovery()
        assert self.formal_citation_recovery_client is not None
        runtime_key = _required_identifier(runtime_id, "runtimeId", 128)
        with self.repository.transaction() as conn:
            runtime = self.repository.get_runtime_classroom(
                conn, runtime_id=runtime_key
            )
            audit = self.repository.get_formal_citation_recovery_by_runtime(
                conn, runtime_id=runtime_key
            )
        if runtime is None or audit is None:
            self._fail(
                "openmaic_formal_citation_recovery_not_found",
                "没有找到正式课堂引用恢复记录",
                404,
            )
        if (
            str(audit.get("status") or "") == "succeeded"
            and str(runtime.get("status") or "") in {"generating", "ready"}
        ):
            if str(runtime.get("status") or "") == "ready":
                return self._runtime_payload(runtime)
            return self.generation_status(str(runtime["upstream_job_id"]))
        if not audit.get("upstream_recovery_id"):
            return self.start_formal_citation_recovery(runtime_key)
        try:
            recovery = self.formal_citation_recovery_client.get_recovery(
                source_job_id=str(audit["source_upstream_job_id"]),
                expected_recovery_id=str(audit["upstream_recovery_id"]),
                runtime_request_id=str(audit["source_runtime_request_id"]),
                formal_input_sha256=str(audit["source_formal_input_sha256"]),
            )
        except OpenMaicFormalCitationRecoveryError as exc:
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc
        return self._record_formal_citation_recovery(runtime, recovery)

    def _record_formal_citation_recovery(
        self,
        runtime: Mapping[str, Any],
        recovery: OpenMaicFormalCitationRecovery,
    ) -> dict[str, Any]:
        if recovery.status == "succeeded":
            # Parse all formal receipts before the terminal audit row can be
            # accepted. The normal generation path repeats the validation
            # against the promoted source job and persisted classroom.
            recovery.as_generation_job()
        receipt = recovery.audit_receipt()
        receipt_sha256 = str(
            receipt.get("receiptSha256") or _canonical_sha256(receipt)
        )
        with self.repository.transaction() as conn:
            audit = self.repository.attach_formal_citation_recovery_receipt(
                conn,
                runtime_id=str(runtime["id"]),
                upstream_recovery_id=recovery.recovery_id,
                status=recovery.status,
                source_job_completed_at=str(recovery.source["completedAt"]),
                source_job_snapshot_sha256=str(
                    recovery.source["jobSnapshotSha256"]
                ),
                calls=recovery.calls,
                repair=recovery.repair,
                result=recovery.result,
                receipt=receipt,
                receipt_sha256=receipt_sha256,
                error=recovery.error,
                now=now_ms(),
            )
            if recovery.status == "failed":
                runtime = self.repository.quarantine_failed_formal_citation_recovery(
                    conn, runtime_id=str(runtime["id"]), now=now_ms()
                )
            else:
                current = self.repository.get_runtime_classroom(
                    conn, runtime_id=str(runtime["id"]), for_update=True
                )
                if current is not None:
                    runtime = current
        if recovery.status == "failed":
            return {
                **self._runtime_payload(runtime),
                "citationRecovery": self._citation_recovery_payload(audit),
            }
        if recovery.status != "succeeded":
            return {
                **self._runtime_payload(runtime),
                "citationRecovery": self._citation_recovery_payload(audit),
            }
        with self.repository.transaction() as conn:
            runtime = self.repository.resume_formal_candidate_from_citation_recovery(
                conn,
                runtime_id=str(runtime["id"]),
                expected_recovery_id=recovery.recovery_id,
                expected_receipt_sha256=receipt_sha256,
                now=now_ms(),
            )
        # The OpenMAIC recovery promotes the same source job atomically. Keep
        # the ordinary generation_status and _complete_formal_candidate as the
        # sole authority that may validate evidence and mark this row ready.
        return self.generation_status(str(runtime["upstream_job_id"]))

    @staticmethod
    def _citation_recovery_payload(audit: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "id": str(audit["id"]),
            "recoveryRequestId": str(audit["recovery_request_id"]),
            "upstreamRecoveryId": audit.get("upstream_recovery_id"),
            "status": str(audit["status"]),
            "sourceJobId": str(audit["source_upstream_job_id"]),
            "responseReceiptSha256": audit.get("response_receipt_sha256"),
            "updatedAt": int(audit["updated_at"]),
        }

    def generation_status(self, upstream_job_id: str) -> dict[str, Any]:
        self._require_generation()
        job_id = _required_identifier(upstream_job_id, "jobId", 128)
        with self.repository.transaction() as conn:
            runtime = self.repository.get_by_upstream_job(
                conn, upstream_job_id=job_id
            )
        if runtime is None:
            self._fail(
                "openmaic_generation_not_found", "没有找到这次课堂生成任务", 404
            )
        requested_manifest = self.repository.decode_json(
            runtime.get("feature_manifest_json"), {}
        )
        # 057 binding is immutable classification authority.  A formal row
        # must never fall through to the legacy/sample completion path merely
        # because its manifest was corrupted after dispatch.
        formal_candidate = bool(runtime.get("candidate_build_item_id"))
        if formal_candidate and (
            not isinstance(requested_manifest, Mapping)
            or requested_manifest.get("formalRuntimeContract")
            != FORMAL_RUNTIME_CLASSROOM_CONTRACT
            or not isinstance(
                requested_manifest.get("generationContract"), Mapping
            )
        ):
            message = (
                "正式候选课堂的本地生成合同无法权威核对，"
                "已隔离且不会自动重发"
            )
            self._quarantine_formal_generation(runtime, message=message)
            raise OpenMaicRuntimeServiceError(
                "openmaic_formal_generation_ambiguous",
                message,
                status_code=503,
            )
        authoritative_formal_job = None
        recoverable_ambiguity = (
            formal_candidate
            and str(runtime["status"]) == "failed"
            and str(runtime.get("quality_status") or "") == "quarantined"
            and runtime.get("error_code") == "openmaic_formal_generation_ambiguous"
            and not runtime.get("upstream_classroom_id")
        )
        if recoverable_ambiguity:
            # Query only the original request. The runtime may reattach its
            # durable Agent, but this path never POSTs another generation.
            try:
                observed = self.client.get_generation_job_by_request_id(
                    str(runtime["request_id"])
                )
            except OpenMaicFullRuntimeError:
                return self._runtime_payload(runtime)
            expected_sha = self._formal_input_sha256(
                runtime_request_id=str(runtime["request_id"]),
                generation_contract=requested_manifest.get("generationContract"),
                formal_contract=requested_manifest.get("formalRuntimeContract"),
                paid_budget=requested_manifest.get("paidBudget"),
            )
            if (
                observed is None
                or str(observed.job_id) != job_id
                or observed.status != "succeeded"
                or not observed.classroom_id
                or not OpenMaicFullRuntimeClient.formal_job_identity_matches(
                    observed,
                    runtime_request_id=str(runtime["request_id"]),
                    formal_input_sha256=expected_sha,
                )
            ):
                return self._runtime_payload(runtime)
            with self.repository.transaction() as conn:
                resumed = self.repository.resume_formal_candidate_after_authoritative_completion(
                    conn,
                    runtime_id=str(runtime["id"]),
                    expected_upstream_job_id=job_id,
                    expected_request_id=str(runtime["request_id"]),
                    expected_feature_manifest_json=str(runtime["feature_manifest_json"]),
                    now=now_ms(),
                )
                runtime = self.repository.get_runtime_classroom(
                    conn, runtime_id=str(runtime["id"])
                )
            if not resumed:
                return self._runtime_payload(runtime)
            authoritative_formal_job = observed
        if str(runtime["status"]) in {"ready", "failed", "recovering"}:
            return self._runtime_payload(runtime)
        updated_at = int(runtime.get("updated_at") or 0)
        if updated_at > 0 and now_ms() - updated_at >= SAMPLE_GENERATION_STALE_AFTER_MS:
            if formal_candidate:
                try:
                    authoritative_formal_job = (
                        self.client.get_generation_job_by_request_id(
                            str(runtime["request_id"])
                        )
                    )
                except OpenMaicFullRuntimeError as exc:
                    self._quarantine_formal_generation(
                        runtime,
                        message=(
                            "正式候选课堂本地等待超时且上游状态无法确认，"
                            "已隔离且不会自动重发"
                        ),
                    )
                    raise OpenMaicRuntimeServiceError(
                        "openmaic_formal_generation_ambiguous",
                        "正式候选课堂上游状态无法确认，已隔离",
                        status_code=503,
                    ) from exc
                if authoritative_formal_job is None or str(
                    authoritative_formal_job.job_id
                ) != str(runtime.get("upstream_job_id") or ""):
                    self._quarantine_formal_generation(
                        runtime,
                        message=(
                            "正式候选课堂本地任务与上游请求编号无法权威核对，"
                            "已隔离且不会自动重发"
                        ),
                    )
                    raise OpenMaicRuntimeServiceError(
                        "openmaic_formal_generation_ambiguous",
                        "正式候选课堂上游任务无法权威核对，已隔离",
                        status_code=503,
                    )
            else:
                with self.repository.transaction() as conn:
                    self.repository.mark_failed(
                        conn,
                        runtime_id=str(runtime["id"]),
                        error_code="openmaic_sample_generation_stale",
                        error_message_safe=(
                            "样板课堂生成超过有限等待时间，已终结且不会自动重试"
                        ),
                        now=now_ms(),
                    )
                    terminal = self.repository.get_runtime_classroom(
                        conn,
                        runtime_id=str(runtime["id"]),
                    )
                return self._runtime_payload(terminal)

        try:
            job = authoritative_formal_job or self.client.get_generation_job(
                job_id,
                formal=formal_candidate,
            )
            if formal_candidate:
                expected_input_sha256 = self._formal_input_sha256(
                    runtime_request_id=str(runtime["request_id"]),
                    generation_contract=requested_manifest.get(
                        "generationContract"
                    ),
                    formal_contract=requested_manifest.get(
                        "formalRuntimeContract"
                    ),
                    paid_budget=requested_manifest.get("paidBudget"),
                )
                if (
                    str(job.job_id) != job_id
                    or not OpenMaicFullRuntimeClient.formal_job_identity_matches(
                        job,
                        runtime_request_id=str(runtime["request_id"]),
                        formal_input_sha256=expected_input_sha256,
                    )
                ):
                    self._quarantine_formal_generation(
                        runtime,
                        message=(
                            "正式候选课堂的上游请求内容或派发状态无法权威核对，"
                            "已隔离且不会自动重发"
                        ),
                    )
                    raise OpenMaicRuntimeServiceError(
                        "openmaic_formal_generation_ambiguous",
                        "正式候选课堂的上游任务身份无法权威核对，已隔离",
                        status_code=503,
                    )
            if job.status == "succeeded":
                if not job.classroom_id:
                    self._fail(
                        "openmaic_generation_incomplete",
                        "OpenMAIC 生成完成但没有课堂结果",
                        502,
                    )
                classroom = self.client.get_classroom(job.classroom_id)
                if formal_candidate:
                    try:
                        runtime = self._complete_formal_candidate(
                            runtime=runtime,
                            job=job,
                            classroom=classroom,
                            requested_manifest=requested_manifest,
                        )
                    except OpenMaicRuntimeServiceError as exc:
                        self._reject_formal_candidate(
                            runtime,
                            error_code=exc.code,
                            message=exc.safe_message,
                        )
                        raise
                    except (RuntimeError, ValueError) as exc:
                        if "candidate completion authority" in str(exc):
                            message = (
                                "正式候选课堂生成期间发布权威已变化，"
                                "已隔离且不会自动重发"
                            )
                            self._quarantine_formal_generation(
                                runtime, message=message
                            )
                            raise OpenMaicRuntimeServiceError(
                                "openmaic_formal_completion_authority_revoked",
                                message,
                                status_code=409,
                            ) from exc
                        code = "openmaic_formal_receipt_reservation_failed"
                        message = (
                            "正式候选课堂无法绑定精确验收回执，本次尝试已拒绝"
                        )
                        self._reject_formal_candidate(
                            runtime,
                            error_code=code,
                            message=message,
                        )
                        raise OpenMaicRuntimeServiceError(
                            code, message, status_code=409
                        ) from exc
                    return self._runtime_payload(runtime, upstream_job=job)
                try:
                    manifest = self._validate_and_manifest(
                        classroom,
                        requested=requested_manifest.get(
                            "enabled", requested_manifest.get("requested", [])
                        ),
                        required=requested_manifest.get("required", []),
                        generation_contract=requested_manifest.get(
                            "generationContract"
                        ),
                    )
                    if manifest["missing"]:
                        self._fail(
                            "openmaic_required_features_missing",
                            "OpenMAIC 成品缺少本次要求的可验证课堂能力",
                            502,
                        )
                    sample_contract = manifest.get("generationContract")
                    if isinstance(sample_contract, Mapping):
                        if (
                            self.conversation_probe_service is None
                            or self.conversation_probe_client is None
                        ):
                            self._fail(
                                "openmaic_sample_conversation_probe_unavailable",
                                "学生对话网关验证器尚未配置",
                                503,
                            )
                        probe = self.conversation_probe_service.issue_generation_candidate(
                            str(runtime["id"]), job.classroom_id
                        )
                        receipts = self.conversation_probe_client.verify(probe)
                        self.conversation_probe_service.finalize_probe(
                            str(probe["probeId"]),
                            chat_receipt=receipts["chat"],
                            transcription_receipt=receipts["transcription"],
                        )
                        manifest["conversation"] = self._sample_conversation_manifest(
                            sample_contract, receipts=receipts
                        )
                except OpenMaicRuntimeServiceError as exc:
                    with self.repository.transaction() as conn:
                        self.repository.mark_failed(
                            conn,
                            runtime_id=str(runtime["id"]),
                            error_code=exc.code,
                            error_message_safe=exc.safe_message,
                            now=now_ms(),
                        )
                    raise
                except (OpenMaicConversationProbeError, OpenMaicConversationProbeClientError) as exc:
                    code = getattr(exc, "code", "openmaic_sample_conversation_probe_failed")
                    message = getattr(exc, "safe_message", "学生对话网关验证未通过")
                    with self.repository.transaction() as conn:
                        self.repository.mark_failed(
                            conn,
                            runtime_id=str(runtime["id"]),
                            error_code=code,
                            error_message_safe=message,
                            now=now_ms(),
                        )
                    raise OpenMaicRuntimeServiceError(code, message, status_code=502) from exc
                with self.repository.transaction() as conn:
                    self.repository.mark_ready(
                        conn,
                        runtime_id=str(runtime["id"]),
                        upstream_classroom_id=job.classroom_id,
                        feature_manifest=manifest,
                        now=now_ms(),
                    )
                    runtime = self.repository.get_runtime_classroom(
                        conn, runtime_id=str(runtime["id"])
                    )
            elif job.status == "failed":
                with self.repository.transaction() as conn:
                    if formal_candidate:
                        failure_code = getattr(job, "failure_code", None)
                        billing_blocked = failure_code in {
                            "openmaic_formal_provider_billing_blocked",
                            "openmaic_formal_provider_free_quota_exhausted",
                        }
                        self.repository.reject_candidate_generation(
                            conn,
                            runtime_id=str(runtime["id"]),
                            error_code=(
                                failure_code
                                if billing_blocked
                                else "openmaic_formal_generation_failed"
                            ),
                            error_message_safe=(
                                "正式课堂生成 Provider 当前不可用，已停止后续派发"
                                if billing_blocked
                                else "OpenMAIC 未能完成正式候选课堂生成"
                            ),
                            now=now_ms(),
                            provider_attempt_consumed=not billing_blocked,
                        )
                        if billing_blocked:
                            self.repository.open_formal_provider_circuit(
                                conn,
                                reason_code=failure_code,
                                runtime_id=str(runtime["id"]),
                                now=now_ms(),
                            )
                    else:
                        self.repository.mark_failed(
                            conn,
                            runtime_id=str(runtime["id"]),
                            error_code="openmaic_generation_failed",
                            error_message_safe="OpenMAIC 未能完成课堂生成",
                            now=now_ms(),
                        )
                    runtime = self.repository.get_runtime_classroom(
                        conn, runtime_id=str(runtime["id"])
                    )
        except OpenMaicFullRuntimeError as exc:
            if formal_candidate:
                self._quarantine_formal_generation(
                    runtime,
                    message=(
                        "正式候选课堂的上游生成状态无法确认，"
                        "已隔离且不会自动重发"
                    ),
                )
                raise OpenMaicRuntimeServiceError(
                    "openmaic_formal_generation_ambiguous",
                    "正式候选课堂的上游生成状态无法确认，已隔离",
                    status_code=503,
                ) from exc
            raise OpenMaicRuntimeServiceError(
                exc.code, exc.safe_message, status_code=exc.status_code
            ) from exc
        return self._runtime_payload(runtime, upstream_job=job)

    @staticmethod
    def _formal_teacher_contract(subject: str) -> dict[str, Any]:
        """Return the exact profile, avatar and Qwen voice shown in Runtime."""
        return get_formal_runtime_teacher_contract(subject)

    def issue_candidate_generation(
        self,
        *,
        build_item_id: str,
        course_id: str,
        course_version: str,
        package_id: str,
        package_version: int,
        target_fingerprint: str,
        runtime_request_id: str,
    ) -> Mapping[str, object]:
        """Issue one 057-bound formal candidate without publishing it.

        The upstream request id is the billing/idempotency identity.  A read
        by that identity always precedes POST.  Any uncertain read or lost
        response that cannot be reconciled is quarantined and never resent.
        """

        self._require_generation()
        item_key = _required_identifier(build_item_id, "buildItemId", 128)
        course_key = _required_identifier(course_id, "courseId", 255)
        course_version_key = _required_identifier(
            course_version, "courseVersion", 64
        )
        package_key = _required_identifier(package_id, "packageId", 128)
        request_key = _required_identifier(
            runtime_request_id, "runtimeRequestId", 128
        )
        if type(package_version) is not int or package_version < 1:
            self._fail(
                "invalid_packageVersion", "packageVersion 无效", 400
            )
        fingerprint = str(target_fingerprint or "").strip()
        if re.fullmatch(r"[0-9a-f]{64}", fingerprint) is None:
            self._fail(
                "invalid_targetFingerprint", "targetFingerprint 无效", 400
            )
        readiness = self.client.formal_generation_readiness()
        if readiness.get("ready") is not True:
            self._fail(
                "openmaic_formal_generation_not_ready",
                "OpenMAIC 正式候选课堂的幂等生成策略尚未就绪",
                503,
            )

        formal_contract = json.loads(
            json.dumps(
                FORMAL_RUNTIME_CLASSROOM_CONTRACT,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            )
        )
        timestamp = now_ms()
        with self.repository.transaction() as conn:
            try:
                authority = self.repository.get_formal_candidate_generation_authority(
                    conn,
                    build_item_id=item_key,
                    course_id=course_key,
                    course_version=course_version_key,
                    package_id=package_key,
                    package_version=package_version,
                    target_fingerprint=fingerprint,
                )
                selected_policy = professional_policy(authority.get("professionalCreationPolicy"))
                selected_options = generation_options(selected_policy)
                teaching_brief = authority.get("teachingBrief")
                teaching_brief_sha256 = str(
                    authority.get("teachingBriefSha256") or ""
                )
                source_content_sha256 = str(
                    authority.get("sourceCourseContentSha256") or ""
                )
                brief_course = (
                    teaching_brief.get("course")
                    if isinstance(teaching_brief, Mapping)
                    else None
                )
                if (
                    not isinstance(teaching_brief, Mapping)
                    or not isinstance(brief_course, Mapping)
                    or str(brief_course.get("id") or "") != course_key
                    or str(brief_course.get("version") or "")
                    != course_version_key
                    or str(teaching_brief.get("sourceCourseContentSha256") or "")
                    != source_content_sha256
                    or re.fullmatch(r"[0-9a-f]{64}", source_content_sha256)
                    is None
                    or _canonical_sha256(teaching_brief)
                    != teaching_brief_sha256
                ):
                    raise ValueError(
                        "formal candidate teaching brief authority mismatch"
                    )
                teacher_contract = self._formal_teacher_contract(
                    str(brief_course.get("subject") or "")
                )
                generation_contract = {
                    "schemaVersion": (
                        OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
                    ),
                    "authority": "mira_backend_formal_candidate",
                    "buildItemId": item_key,
                    "course": {
                        "id": course_key,
                        "version": course_version_key,
                        "packageId": package_key,
                        "packageVersion": package_version,
                    },
                    "targetFingerprint": fingerprint,
                    "runtimeRequestId": request_key,
                    "coursewareAuthority": dict(
                        OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY
                    ),
                    "professionalCreationPolicy": json.loads(
                        json.dumps(
                            selected_policy,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    ),
                    "sourceCourseContentSha256": source_content_sha256,
                    "teachingBriefSha256": teaching_brief_sha256,
                    "teachingBrief": json.loads(
                        json.dumps(
                            teaching_brief,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    ),
                    "teacher": teacher_contract,
                    "requiredClassroom": formal_contract,
                    "generation": json.loads(
                        json.dumps(
                            selected_options,
                            ensure_ascii=False,
                            sort_keys=True,
                            separators=(",", ":"),
                        )
                    ),
                }
                if isinstance(teaching_brief.get("difficultyPolicy"), Mapping):
                    from content.formal_difficulty_policy import formal_difficulty_policy
                    difficulty = formal_difficulty_policy(str(brief_course.get("gradeCode")), str(brief_course.get("subject")),
                        str(brief_course.get("skillId")), str(brief_course.get("difficultyCode")))
                    if _canonical_sha256(difficulty) != _canonical_sha256(teaching_brief["difficultyPolicy"]):
                        raise ValueError("formal candidate difficulty authority mismatch")
                    generation_contract["difficultyPolicy"] = difficulty
                    generation_contract["course"]["difficultyCode"] = difficulty["difficultyCode"]
                if adaptive_policy(selected_policy):
                    generation_contract.update({
                        "gradeBoundary": authority.get("gradeBoundary"),
                        "gradeBoundarySha256": authority.get("gradeBoundarySha256"),
                    })
                validate_generation_grade_boundary(generation_contract)
                paid_budget = None
                if "interactionDesignPolicy" in selected_policy:
                    if self.paid_budget_service is None:
                        self._fail("learning_budget_unavailable", "新课生产预算尚未配置，未发起付费调用", 503)
                    paid_budget = self.paid_budget_service.issue_catalog_production_authorization(
                        build_item_id=item_key, expected_grade=str(brief_course.get("gradeCode") or ""),
                        expected_subject=str(brief_course.get("subject") or ""),
                        expected_skill=str(brief_course.get("skillId") or ""),
                        expected_course_id=course_key, expected_course_version=course_version_key)
                    if paid_budget is None:
                        self._fail("learning_budget_unavailable", "新课生产预算尚未配置，未发起付费调用", 503)
                requirement = json.dumps(
                    generation_contract,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                )
                expected_input_sha256 = (
                    OpenMaicFullRuntimeClient.formal_input_sha256(
                        {
                            "requirement": requirement,
                            "enableWebSearch": True,
                            "enableImageGeneration": selected_options["enableImageGeneration"],
                            "enableVideoGeneration": selected_options["enableVideoGeneration"],
                            "enableTTS": False,
                            "agentMode": "generate",
                            **({"paidBudget": paid_budget} if paid_budget is not None else {}),
                            "runtimeRequestId": request_key,
                            "formalRuntimeContract": formal_contract,
                            "coursewareAuthority": dict(
                                OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY
                            ),
                            "professionalCreationPolicy": json.loads(
                                json.dumps(
                                    selected_policy,
                                    ensure_ascii=False,
                                    sort_keys=True,
                                    separators=(",", ":"),
                                )
                            ),
                        }
                    )
                )
                manifest = self._requested_manifest(
                    FORMAL_CORE_REQUIRED_FEATURES,
                    FORMAL_CORE_REQUIRED_FEATURES,
                    generation_contract=generation_contract,
                )
                manifest["formalRuntimeContract"] = formal_contract
                manifest["sourceCourseContentSha256"] = source_content_sha256
                manifest["teachingBriefSha256"] = teaching_brief_sha256
                if paid_budget is not None:
                    manifest["paidBudget"] = paid_budget
                runtime, created = self.repository.reserve_candidate_runtime(
                    conn,
                    runtime_id=new_token("omfc"),
                    runtime_request_id=request_key,
                    build_item_id=item_key,
                    course_id=course_key,
                    course_version=course_version_key,
                    package_id=package_key,
                    package_version=package_version,
                    target_fingerprint=fingerprint,
                    feature_manifest=manifest,
                    now=timestamp,
                )
            except ValueError as exc:
                message = str(exc)
                code = (
                    "openmaic_formal_dispatch_ambiguous"
                    if "ambiguous" in message
                    or "safely retryable" in message
                    else "openmaic_formal_candidate_conflict"
                )
                logging.getLogger(__name__).warning(
                    "Formal candidate reservation rejected: code=%s reason=%s",
                    code, message[:512],
                )
                self._fail(code, "正式候选课堂状态冲突，未发起生成", 409)

        if not created:
            quality = str(runtime.get("quality_status") or "")
            if quality == "quarantined":
                self._fail(
                    "openmaic_formal_dispatch_ambiguous",
                    "正式候选课堂的上游状态不明，已隔离且不会重发",
                    409,
                )
            if str(runtime.get("status") or "") != "pending":
                return self._runtime_payload(runtime)

        try:
            upstream = self.client.get_generation_job_by_request_id(request_key)
        except OpenMaicFullRuntimeError as exc:
            self._quarantine_formal_candidate(
                runtime,
                message="正式候选课堂的上游请求状态无法确认，已隔离且不会重发",
            )
            raise OpenMaicRuntimeServiceError(
                "openmaic_formal_dispatch_ambiguous",
                "正式候选课堂的上游请求状态无法确认，已隔离且不会重发",
                status_code=503,
            ) from exc

        if upstream is None:
            try:
                upstream = self.client.start_generation(
                    requirement=requirement,
                    enable_web_search=True,
                    enable_image_generation=selected_options["enableImageGeneration"],
                    enable_video_generation=selected_options["enableVideoGeneration"],
                    enable_tts=False,
                    agent_mode="generate",
                    runtime_request_id=request_key,
                    formal_runtime_contract=formal_contract,
                    professional_creation_policy=selected_policy,
                    **({"paid_budget": paid_budget} if paid_budget is not None else {}),
                )
            except OpenMaicFullRuntimeError as dispatch_error:
                try:
                    upstream = self.client.get_generation_job_by_request_id(
                        request_key
                    )
                except OpenMaicFullRuntimeError:
                    upstream = None
                if upstream is None:
                    self._quarantine_formal_candidate(
                        runtime,
                        message=(
                            "正式候选课堂可能已被上游接受，但回执无法确认；"
                            "已隔离且不会重发"
                        ),
                    )
                    raise OpenMaicRuntimeServiceError(
                        "openmaic_formal_dispatch_ambiguous",
                        "正式候选课堂可能已被接受，已隔离且不会重发",
                        status_code=503,
                    ) from dispatch_error

        if not OpenMaicFullRuntimeClient.formal_job_identity_matches(
            upstream,
            runtime_request_id=request_key,
            formal_input_sha256=expected_input_sha256,
        ):
            self._quarantine_formal_candidate(
                runtime,
                message=(
                    "正式候选课堂的上游请求内容或派发状态无法权威核对，"
                    "已隔离且不会重发"
                ),
            )
            raise OpenMaicRuntimeServiceError(
                "openmaic_formal_dispatch_ambiguous",
                "正式候选课堂的上游请求身份无法权威核对，已隔离",
                status_code=503,
            )

        with self.repository.transaction() as conn:
            attached = self.repository.mark_generating(
                conn,
                runtime_id=str(runtime["id"]),
                upstream_job_id=str(upstream.job_id),
                now=now_ms(),
            )
            current = self.repository.get_runtime_classroom(
                conn, runtime_id=str(runtime["id"])
            )
        if current is None or (
            not attached
            and str(current.get("upstream_job_id") or "")
            != str(upstream.job_id)
        ):
            raise OpenMaicRuntimeServiceError(
                "openmaic_formal_generation_persistence_uncertain",
                "正式候选课堂的上游回执未能安全绑定；不会重发",
                status_code=503,
            )
        return self._runtime_payload(current, upstream_job=upstream)

    def _assert_formal_provider_dispatch_allowed(self) -> None:
        with self.repository.transaction() as conn:
            circuit = self.repository.get_formal_provider_circuit(conn)
        if not (
            circuit is not None
            and str(circuit.get("status") or "") == "closed"
            and int(circuit.get("probe_succeeded_at") or 0) > 0
        ):
            self._fail(
                "openmaic_formal_provider_circuit_open",
                "正式课堂生成已暂停，需先通过一次 Provider 最小探针",
                503,
            )

    @staticmethod
    def _formal_input_sha256(
        *,
        runtime_request_id: str,
        generation_contract: object,
        formal_contract: object,
        paid_budget: object = None,
    ) -> str:
        if not isinstance(generation_contract, Mapping) or not isinstance(
            formal_contract, Mapping
        ):
            raise OpenMaicRuntimeServiceError(
                "openmaic_formal_generation_ambiguous",
                "正式候选课堂的请求合同无法权威核对，已隔离",
                status_code=503,
            )
        selected_policy = professional_policy(generation_contract.get("professionalCreationPolicy"))
        selected_options = generation_options(selected_policy)
        if generation_contract.get("generation") != selected_options:
            raise OpenMaicRuntimeServiceError(
                "openmaic_formal_generation_ambiguous", "正式候选课堂的图片策略不一致", status_code=503,
            )
        requirement = json.dumps(
            dict(generation_contract),
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        return OpenMaicFullRuntimeClient.formal_input_sha256(
            {
                "requirement": requirement,
                "enableWebSearch": True,
                "enableImageGeneration": selected_options["enableImageGeneration"],
                "enableVideoGeneration": selected_options["enableVideoGeneration"],
                "enableTTS": False,
                "agentMode": "generate",
                **({"paidBudget": paid_budget} if paid_budget is not None else {}),
                "runtimeRequestId": runtime_request_id,
                "formalRuntimeContract": dict(formal_contract),
                "coursewareAuthority": dict(
                    OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY
                ),
                "professionalCreationPolicy": json.loads(
                    json.dumps(
                        selected_policy,
                        ensure_ascii=False,
                        sort_keys=True,
                        separators=(",", ":"),
                    )
                ),
            }
        )

    def _quarantine_formal_candidate(
        self, runtime: Mapping[str, Any], *, message: str
    ) -> None:
        with self.repository.transaction() as conn:
            self.repository.quarantine_candidate_dispatch(
                conn,
                runtime_id=str(runtime["id"]),
                error_code="openmaic_formal_dispatch_ambiguous",
                error_message_safe=message,
                now=now_ms(),
            )

    def _quarantine_formal_generation(
        self, runtime: Mapping[str, Any], *, message: str
    ) -> None:
        with self.repository.transaction() as conn:
            self.repository.quarantine_candidate_generation(
                conn,
                runtime_id=str(runtime["id"]),
                error_code="openmaic_formal_generation_ambiguous",
                error_message_safe=message,
                now=now_ms(),
            )

    def _reject_formal_candidate(
        self,
        runtime: Mapping[str, Any],
        *,
        error_code: str,
        message: str,
    ) -> None:
        code = (
            error_code
            if str(error_code).startswith("openmaic_formal_")
            else "openmaic_formal_classroom_invalid"
        )
        with self.repository.transaction() as conn:
            self.repository.reject_candidate_generation(
                conn,
                runtime_id=str(runtime["id"]),
                error_code=code,
                error_message_safe=message,
                now=now_ms(),
            )

    def _complete_formal_candidate(
        self,
        *,
        runtime: Mapping[str, Any],
        job: Any,
        classroom: Mapping[str, Any],
        requested_manifest: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        classroom_stage = classroom.get("stage")
        classroom_scenes = classroom.get("scenes")
        if (
            not isinstance(classroom_stage, Mapping)
            or str(classroom_stage.get("id") or "")
            != str(job.classroom_id or "")
        ):
            self._fail(
                "openmaic_formal_classroom_identity_mismatch",
                "正式候选课堂内容与上游课堂身份不一致",
                502,
            )
        if (
            not isinstance(classroom_scenes, list)
            or type(getattr(job, "scenes_count", None)) is not int
            or not 1 <= int(job.scenes_count) <= int(
                FORMAL_RUNTIME_CLASSROOM_CONTRACT["scenePlanning"][
                    "maxSceneCount"
                ]
            )
            or int(job.scenes_count) != len(classroom_scenes)
        ):
            self._fail(
                "openmaic_formal_scene_count_mismatch",
                "正式候选课堂场景数量与上游完成回执不一致",
                502,
            )
        generation_contract = requested_manifest.get("generationContract")
        teaching_brief = (
            generation_contract.get("teachingBrief")
            if isinstance(generation_contract, Mapping)
            else None
        )
        brief_course = (
            teaching_brief.get("course")
            if isinstance(teaching_brief, Mapping)
            else None
        )
        try:
            teacher_contract = self._formal_teacher_contract(
                str(brief_course.get("subject") or "")
                if isinstance(brief_course, Mapping)
                else ""
            )
        except (KeyError, ValueError) as exc:
            self._fail(
                "openmaic_formal_teacher_identity_invalid",
                "正式候选课堂缺少服务端固定老师身份",
                502,
            )
            raise AssertionError("unreachable") from exc
        if (
            not isinstance(generation_contract, Mapping)
            or generation_contract.get("teacher") != teacher_contract
        ):
            self._fail(
                "openmaic_formal_teacher_identity_invalid",
                "正式候选课堂老师合同与生成请求不一致",
                502,
            )
        formal_evidence = self._validate_formal_classroom(
            classroom,
            teacher_contract=teacher_contract,
        )
        if adaptive_policy(generation_contract.get("professionalCreationPolicy")):
            self._validate_locked_formal_assessment(classroom, generation_contract)
        if (
            type(getattr(job, "speech_action_count", None)) is not int
            or int(job.speech_action_count)
            != int(formal_evidence["speechActionCount"])
        ):
            self._fail(
                "openmaic_formal_speech_count_mismatch",
                "正式候选课堂讲解数量与上游完成回执不一致",
                502,
            )
        formal_required_features = _formal_required_features(formal_evidence)
        manifest = self._requested_manifest(
            formal_required_features,
            formal_required_features,
        )
        manifest["enabled"] = list(formal_required_features)
        manifest["requested"] = list(formal_required_features)
        manifest["required"] = list(formal_required_features)
        manifest["present"] = list(formal_required_features)
        manifest["missing"] = []
        feature_evidence = _empty_runtime_evidence()
        for feature in formal_required_features:
            feature_evidence[feature] = {
                "verified": True,
                "signals": [f"openmaic-artifact:{feature}"],
                "reasons": [],
            }
        manifest["evidence"] = feature_evidence
        manifest["platform"] = self._mp4_platform_manifest()
        manifest["sceneTypes"] = sorted(
            {
                str(scene.get("type") or "")
                for scene in classroom_scenes
                if isinstance(scene, Mapping) and scene.get("type")
            }
        )
        manifest["actionTypes"] = sorted(
            {
                str(action.get("type") or "")
                for scene in classroom_scenes
                if isinstance(scene, Mapping)
                for action in (
                    scene.get("actions")
                    if isinstance(scene.get("actions"), list)
                    else []
                )
                if isinstance(action, Mapping) and action.get("type")
            }
        )
        manifest["sceneCount"] = len(classroom_scenes)
        (
            professional_creation,
            research,
            professional_evidence,
            research_evidence,
        ) = self._professional_completion_evidence(
            job=job,
            classroom=classroom,
            runtime=runtime,
            generation_contract=generation_contract,
            teaching_brief_sha256=str(
                requested_manifest.get("teachingBriefSha256") or ""
            ),
        )
        formal_evidence = dict(formal_evidence)
        formal_evidence["professionalCreation"] = professional_evidence
        formal_evidence["research"] = research_evidence
        try:
            quality_evidence = validate_classroom_quality(professional_creation, generation_contract, classroom)
            if quality_evidence is not None:
                formal_evidence["teachingQuality"] = quality_evidence
            interaction_evidence = validate_classroom_interaction(professional_creation, generation_contract, classroom)
            if interaction_evidence is not None:
                formal_evidence["interactionDesign"] = interaction_evidence
                formal_evidence["requiredTeachingActions"] = [
                    {"sceneId": str(scene["id"]), "actionId": str(action["id"])}
                    for scene in sorted(classroom["scenes"], key=lambda value: value["order"])
                    for action in scene["actions"] if action.get("type") == "discussion"
                ]
        except ValueError as exc:
            self._fail("openmaic_formal_teaching_quality_invalid", "正式课堂最终课件与独立教学质量验收不一致", 502)
            raise AssertionError("unreachable") from exc
        if professional_image_fields(professional_creation):
            try:
                media = media_receipt(getattr(job, "media", None),
                    runtime_request_id=str(runtime["request_id"]),
                    classroom_id=str(job.classroom_id),
                    build_item_id=str(runtime["candidate_build_item_id"]),
                    session_id=professional_creation["sessionId"])
                formal_evidence["media"] = validate_classroom_media(media, classroom, self._image_media_available)
            except ValueError as exc:
                self._fail("invalid_openmaic_media_receipt", "正式课堂图片回执、场景引用或可读性验证失败", 502)
                raise AssertionError("unreachable") from exc
            manifest["media"] = media
        elif getattr(job, "media", None) is not None:
            self._fail("invalid_openmaic_media_receipt", "旧版正式课堂不能混入新图片回执", 502)
        if professional_video_fields(professional_creation):
            try:
                video = video_receipt(getattr(job, "video", None),
                    runtime_request_id=str(runtime["request_id"]), classroom_id=str(job.classroom_id),
                    build_item_id=str(runtime["candidate_build_item_id"]), session_id=professional_creation["sessionId"])
                formal_evidence["video"] = validate_classroom_video(video, classroom, self._video_media_available)
            except ValueError as exc:
                self._fail("invalid_openmaic_video_receipt", "正式课堂视频回执、场景引用或可读性验证失败", 502)
                raise AssertionError("unreachable") from exc
            manifest["video"] = video
        elif getattr(job, "video", None) is not None or classroom_video_references(classroom):
            self._fail("invalid_openmaic_video_receipt", "旧版正式课堂不能混入新视频回执或素材", 502)
        classroom_content_sha256 = _canonical_sha256(
            {"stage": classroom_stage, "scenes": classroom.get("scenes")}
        )
        manifest["generationContract"] = generation_contract
        manifest["formalRuntimeContract"] = FORMAL_RUNTIME_CLASSROOM_CONTRACT
        manifest["formalEvidence"] = formal_evidence
        manifest["professionalCreation"] = professional_creation
        manifest["research"] = research
        manifest["classroomContentSha256"] = classroom_content_sha256
        # Preserve the immutable source hashes used by the classroom receipt.
        # The validated manifest replaces the request manifest, so omitting
        # these fields makes a later publication recheck impossible even
        # though the same values remain nested in generationContract.
        manifest["sourceCourseContentSha256"] = requested_manifest.get(
            "sourceCourseContentSha256"
        )
        manifest["teachingBriefSha256"] = requested_manifest.get(
            "teachingBriefSha256"
        )
        if requested_manifest.get("paidBudget") is not None:
            manifest["paidBudget"] = requested_manifest["paidBudget"]
        completed_at = now_ms()
        receipt_payload = {
            "schemaVersion": (
                "mira.learning.formal-classroom-evidence.v2-professional"
            ),
            "buildItemId": str(runtime["candidate_build_item_id"]),
            "runtimeClassroomId": str(runtime["id"]),
            "runtimeRequestId": str(runtime["request_id"]),
            "upstreamJobId": str(job.job_id),
            "upstreamClassroomId": str(job.classroom_id),
            "targetFingerprint": str(
                runtime["candidate_target_fingerprint"]
            ),
            "sourceCourseContentSha256": requested_manifest.get(
                "sourceCourseContentSha256"
            ),
            "teachingBriefSha256": requested_manifest.get(
                "teachingBriefSha256"
            ),
            "classroomContentSha256": classroom_content_sha256,
            "formalRuntimeContract": FORMAL_RUNTIME_CLASSROOM_CONTRACT,
            "professionalCreationReceiptSha256": professional_creation[
                "receiptSha256"
            ],
            "researchReceiptSha256": research["receiptSha256"],
            "evidence": formal_evidence,
        }
        receipt_hash = _canonical_sha256(receipt_payload)

        def classroom_only_receipt(receipt: Mapping[str, Any]) -> bool:
            return bool(
                str(receipt.get("classroom_status") or "") == "passed"
                and str(receipt.get("classroom_receipt_hash") or "")
                == receipt_hash
                and str(receipt.get("runtime_classroom_id") or "")
                == str(runtime["id"])
                and all(
                    str(receipt.get(field) or "") == "pending"
                    for field in (
                        "tts_status",
                        "asr_roundtrip_status",
                        "conversation_provider_status",
                        "publication_status",
                    )
                )
                and int(receipt.get("auto_validated") or 0) == 0
                and int(receipt.get("approved") or 0) == 0
                and all(
                    receipt.get(field) is None
                    for field in (
                        "tts_receipt_hash",
                        "tts_completed_at",
                        "asr_roundtrip_receipt_hash",
                        "asr_roundtrip_completed_at",
                        "conversation_provider_receipt_hash",
                        "conversation_provider_completed_at",
                        "auto_validation_contract_version",
                        "auto_validation_receipt_hash",
                        "auto_validated_at",
                        "approved_by",
                        "approval_receipt_hash",
                        "approved_at",
                        "publication_receipt_hash",
                        "published_at",
                    )
                )
            )

        with self.repository.transaction() as conn:
            current = self.repository.assert_candidate_completion_authority(
                conn,
                runtime_id=str(runtime["id"]),
                build_item_id=str(runtime["candidate_build_item_id"]),
                target_fingerprint=str(
                    runtime["candidate_target_fingerprint"]
                ),
                expected_upstream_job_id=str(job.job_id),
            )
            if str(current.get("status") or "") == "ready":
                existing_manifest = self.repository.decode_json(
                    current.get("feature_manifest_json"), {}
                )
                existing_receipt = (
                    self.catalog_repository.get_classroom_item_receipt(
                        conn,
                        build_item_id=str(runtime["candidate_build_item_id"]),
                        for_update=True,
                    )
                )
                if (
                    str(current.get("upstream_classroom_id") or "")
                    != str(job.classroom_id)
                    or existing_manifest != manifest
                    or not isinstance(existing_receipt, Mapping)
                    or not classroom_only_receipt(existing_receipt)
                ):
                    raise RuntimeError(
                        "formal candidate terminal evidence replay conflict"
                    )
                return current
            self.repository.mark_ready(
                conn,
                runtime_id=str(runtime["id"]),
                upstream_classroom_id=str(job.classroom_id),
                feature_manifest=manifest,
                now=completed_at,
            )
            current = self.repository.get_runtime_classroom(
                conn, runtime_id=str(runtime["id"]), for_update=True
            )
            if current is None or str(current.get("status") or "") != "ready":
                raise RuntimeError("formal candidate did not become ready")
            self.catalog_repository.reserve_classroom_item_receipt(
                conn,
                build_item_id=str(runtime["candidate_build_item_id"]),
                runtime_classroom_id=str(runtime["id"]),
                target_fingerprint=str(
                    runtime["candidate_target_fingerprint"]
                ),
                now=completed_at,
            )
            receipt = self.catalog_repository.record_classroom_item_evidence(
                conn,
                build_item_id=str(runtime["candidate_build_item_id"]),
                evidence_kind="classroom",
                outcome="passed",
                receipt_hash=receipt_hash,
                completed_at=completed_at,
                now=completed_at,
            )
            if not classroom_only_receipt(receipt):
                raise RuntimeError(
                    "formal candidate receipt advanced beyond classroom evidence"
                )
        return current

    def _professional_completion_evidence(
        self,
        *,
        job: Any,
        classroom: Mapping[str, Any],
        runtime: Mapping[str, Any],
        generation_contract: Mapping[str, Any],
        teaching_brief_sha256: str,
    ) -> tuple[
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
        dict[str, Any],
    ]:
        """Bind Pro Agent and same-run web research receipts to publication."""

        professional_raw = getattr(job, "professional_creation", None)
        research_raw = getattr(job, "research", None)
        runtime_request_id = str(runtime.get("request_id") or "")
        build_item_id = str(runtime.get("candidate_build_item_id") or "")
        classroom_id = str(job.classroom_id or "")
        try:
            selected_policy = professional_policy(generation_contract.get("professionalCreationPolicy"))
            selected_options = generation_options(selected_policy)
            validate_generation_grade_boundary(generation_contract)
        except ValueError as exc:
            self._fail("openmaic_formal_professional_evidence_missing", "正式候选课堂的专业图片策略无效", 502)
            raise AssertionError("unreachable") from exc
        if (
            not isinstance(professional_raw, Mapping)
            or not isinstance(research_raw, Mapping)
            or generation_contract.get("coursewareAuthority")
            != OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY
            or generation_contract.get("professionalCreationPolicy")
            != selected_policy
            or generation_contract.get("generation")
            != selected_options
            or re.fullmatch(r"[0-9a-f]{64}", teaching_brief_sha256) is None
        ):
            self._fail(
                "openmaic_formal_professional_evidence_missing",
                "正式候选课堂缺少服务端固定的专业创作或联网研究证据",
                502,
            )
        try:
            professional = (
                OpenMaicFullRuntimeClient._professional_creation_receipt_from_payload(
                    professional_raw,
                    runtime_request_id=runtime_request_id,
                    classroom_id=classroom_id,
                )
            )
            validate_classroom_skills(professional, generation_contract, classroom)
            research = OpenMaicFullRuntimeClient._research_receipt_from_payload(
                research_raw,
                runtime_request_id=runtime_request_id,
                classroom_id=classroom_id,
            )
        except OpenMaicFullRuntimeError as exc:
            self._fail(exc.code, exc.safe_message, 502)
            raise AssertionError("unreachable") from exc
        except ValueError as exc:
            self._fail("openmaic_formal_skill_evidence_invalid", "正式课件缺少完整的技能加载或逐页应用证据", 502)
            raise AssertionError("unreachable") from exc
        if (
            bool(professional_image_fields(professional)) != ("image" in selected_policy)
            or bool(professional_video_fields(professional)) != ("video" in selected_policy)
            or professional.get("buildItemId") != build_item_id
            or research.get("buildItemId") != build_item_id
            or professional.get("teachingBriefSha256")
            != teaching_brief_sha256
            or professional.get("sessionId") != research.get("sessionId")
        ):
            self._fail(
                "openmaic_formal_professional_identity_mismatch",
                "正式候选课堂的专业创作、课程或联网研究身份不一致",
                502,
            )

        scenes = classroom.get("scenes")
        if not isinstance(scenes, list):
            self._fail(
                "openmaic_formal_research_citation_invalid",
                "正式候选课堂无法核对联网引用场景",
                502,
            )
        scene_ids = {
            str(scene.get("id") or "")
            for scene in scenes
            if isinstance(scene, Mapping)
        }
        cited_scene_ids = {
            str(scene_id)
            for citation in research["citations"]
            for scene_id in citation["sceneIds"]
        }
        if not cited_scene_ids or not cited_scene_ids.issubset(scene_ids):
            self._fail(
                "openmaic_formal_research_citation_invalid",
                "正式候选课堂的联网引用未绑定到真实课件场景",
                502,
            )

        professional_evidence = {
            "verified": True,
            "schemaVersion": professional["schemaVersion"],
            "sessionId": professional["sessionId"],
            "workflowVersion": professional["workflowVersion"],
            "skillId": professional["skillId"],
            "supportingSkillIds": list(professional["supportingSkillIds"]),
            "userPromptRequired": False,
            "studentToolsEnabled": False,
            "webSearchEnabled": True,
            **professional_image_fields(professional),
            **professional_video_fields(professional),
            **professional_skill_fields(professional),
            **professional_quality_fields(professional),
            **professional_interaction_fields(professional),
            "receiptSha256": professional["receiptSha256"],
        }
        research_evidence = {
            "verified": True,
            "schemaVersion": research["schemaVersion"],
            "sessionId": research["sessionId"],
            "providerId": research["providerId"],
            "searchCount": research["searchCount"],
            "resultCount": research["resultCount"],
            "fetchedSourceCount": research["fetchedSourceCount"],
            "citationCount": research["citationCount"],
            "citedSceneCount": len(cited_scene_ids),
            "receiptSha256": research["receiptSha256"],
        }
        return professional, research, professional_evidence, research_evidence

    def _formal_runtime_assessment_contract(
        self,
        generation_contract: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        """Project the four scored brief questions without answer authority."""

        def invalid() -> None:
            self._fail(
                "openmaic_formal_assessment_contract_invalid",
                "正式候选课堂缺少服务端锁定的评分题目合同",
                502,
            )

        if not isinstance(generation_contract, Mapping):
            invalid()
        teaching_brief = generation_contract.get("teachingBrief")
        if (
            not isinstance(teaching_brief, Mapping)
            or teaching_brief.get("schemaVersion")
            != "mira.learning.formal-runtime-teaching-brief.v1"
        ):
            invalid()
        authority = teaching_brief.get("authority")
        if not isinstance(authority, Mapping) or dict(authority) != {
            "source": "locked_learning_course",
            "answerContractProvided": False,
            "scoringRulesProvided": False,
            "providerSecretsProvided": False,
        }:
            invalid()
        lesson = teaching_brief.get("lesson")
        if not isinstance(lesson, Mapping):
            invalid()
        flow = lesson.get("teachingFlow")
        questions = lesson.get("questions")
        if not isinstance(flow, Mapping) or not isinstance(questions, list):
            invalid()
        guided_ids = flow.get("guidedQuestionIds")
        independent_ids = flow.get("independentQuestionIds")
        if (
            not isinstance(guided_ids, list)
            or not isinstance(independent_ids, list)
            or len(guided_ids) != 2
            or len(independent_ids) != 2
        ):
            invalid()
        scored_ids = [*guided_ids, *independent_ids]
        if (
            any(
                not _bounded_identifier(question_id)
                or len(str(question_id).strip()) > 128
                or str(question_id) != str(question_id).strip()
                for question_id in scored_ids
            )
            or len(set(str(question_id) for question_id in scored_ids)) != 4
        ):
            invalid()

        questions_by_id: dict[str, Mapping[str, Any]] = {}
        for question in questions:
            if not isinstance(question, Mapping):
                invalid()
            question_id = question.get("id")
            if (
                not _bounded_identifier(question_id)
                or str(question_id) != str(question_id).strip()
                or str(question_id) in questions_by_id
                or any(
                    forbidden in question
                    for forbidden in (
                        "answer",
                        "evaluation",
                        "verificationExpression",
                    )
                )
            ):
                invalid()
            questions_by_id[str(question_id)] = question
        if any(str(question_id) not in questions_by_id for question_id in scored_ids):
            invalid()

        runtime_types = {
            "numeric": "short_answer",
            "exact_text": "short_answer",
            "accepted_text": "short_answer",
            "single_choice": "single",
            "sequence": "multiple",
        }
        expected: list[dict[str, Any]] = []
        for raw_question_id in scored_ids:
            question_id = str(raw_question_id)
            question = questions_by_id[question_id]
            source_type = str(question.get("type") or "")
            prompt = question.get("prompt")
            runtime_type = runtime_types.get(source_type)
            if runtime_type is None or not _nonempty_string(prompt):
                invalid()
            options: list[dict[str, str]] = []
            choices = question.get("choices")
            if source_type in {"single_choice", "sequence"}:
                if (
                    not isinstance(choices, list)
                    or not 2 <= len(choices) <= MAX_QUIZ_OPTIONS
                ):
                    invalid()
                for choice in choices:
                    if (
                        not isinstance(choice, Mapping)
                        or not _nonempty_string(choice.get("id"))
                        or not _nonempty_string(choice.get("label"))
                    ):
                        invalid()
                    options.append(
                        {
                            "value": str(choice["id"]).strip(),
                            "label": str(choice["label"]).strip(),
                        }
                    )
                if len({option["value"] for option in options}) != len(options):
                    invalid()
            elif choices not in (None, []):
                invalid()
            expected.append(
                {
                    "id": question_id,
                    "question": str(prompt).strip(),
                    "runtimeType": runtime_type,
                    "options": options,
                }
            )
        return expected

    def _validate_locked_formal_assessment(
        self, classroom: Mapping[str, Any], generation: Mapping[str, Any]
    ) -> None:
        """Reuse the independently verified course's four scored public items."""

        expected = self._formal_runtime_assessment_contract(generation)
        scenes = classroom.get("scenes")
        actual = [question for scene in sorted(scenes, key=lambda item: item["order"])
                  if scene.get("type") == "quiz"
                  for question in scene["content"].get("questions", [])]
        def mismatch() -> None:
            self._fail("openmaic_formal_assessment_mismatch", "正式课件评分题必须逐题保持锁定内容、类型和选项", 502)
        if len(expected) != 4 or len(actual) != 4:
            mismatch()
        for question, locked in zip(actual, expected):
            if (question.get("id") != locked["id"] or question.get("question") != locked["question"]
                    or question.get("type") != locked["runtimeType"] or question.get("hasAnswer") is not False
                    or question.get("answer") not in (None, [])
                    or any(key in question for key in ("evaluation", "verificationExpression"))):
                mismatch()
            options = question.get("options")
            if locked["options"]:
                if (not isinstance(options, list) or any(not isinstance(option, Mapping) for option in options)
                        or [{"value": option.get("value"), "label": option.get("label")} for option in options] != locked["options"]):
                    mismatch()
            elif options not in (None, []):
                mismatch()

    def _validate_formal_classroom(
        self,
        classroom: Mapping[str, Any],
        *,
        teacher_contract: Mapping[str, Any] | None = None,
        assessment_questions: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Inspect the OpenMAIC artifact without grading its lesson design.

        OpenMAIC professional mode owns page count, scene mix, roster size,
        discussion design, focus effects, widgets and assessment layout.  Mira
        keeps only the stable playback boundary here: one bounded classroom,
        parseable scenes and actions, a bound teacher identity, and speech that
        can be paired with the separately verified audio receipt.
        """

        del assessment_questions  # The generated quiz is authoritative.
        stage = classroom.get("stage")
        scenes = classroom.get("scenes")
        max_scene_count = int(
            FORMAL_RUNTIME_CLASSROOM_CONTRACT["scenePlanning"]["maxSceneCount"]
        )
        if (
            not isinstance(stage, Mapping)
            or not isinstance(scenes, list)
            or not 1 <= len(scenes) <= max_scene_count
        ):
            self._fail(
                "openmaic_formal_classroom_invalid",
                "正式候选课堂缺少可播放的 stage 或 scenes",
                502,
            )
        _validate_stage(stage, fail=self._fail)
        stage_id = str(stage["id"])
        roles = _stage_agent_roles(stage, fail=self._fail)

        teacher_evidence: dict[str, Any] | None = None
        if teacher_contract is not None:
            expected_runtime = teacher_contract.get("runtime")
            configs = stage.get("generatedAgentConfigs")
            matching_teachers = [
                item
                for item in configs
                if isinstance(item, Mapping)
                and str(item.get("role") or "").strip().lower() == "teacher"
                and isinstance(expected_runtime, Mapping)
                and item.get("name") == expected_runtime.get("name")
                and item.get("avatar") == expected_runtime.get("avatar")
                and item.get("voiceConfig") == expected_runtime.get("voiceConfig")
            ] if isinstance(configs, list) else []
            if (
                not isinstance(expected_runtime, Mapping)
                or not isinstance(expected_runtime.get("voiceConfig"), Mapping)
                or len(matching_teachers) != 1
                or expected_runtime.get("teacherGender")
                not in {"female", "male"}
                or expected_runtime.get("voiceGender")
                != expected_runtime.get("teacherGender")
            ):
                self._fail(
                    "openmaic_formal_teacher_identity_mismatch",
                    "正式候选课堂老师身份或音色绑定不一致",
                    502,
                )
            teacher = matching_teachers[0]
            teacher_evidence = {
                "agentId": str(teacher["id"]),
                "name": str(expected_runtime["name"]),
                "avatar": str(expected_runtime["avatar"]),
                "teacherGender": str(expected_runtime["teacherGender"]),
                "voiceGender": str(expected_runtime["voiceGender"]),
                "voiceId": str(expected_runtime["voiceConfig"]["voiceId"]),
            }

        scene_ids: set[str] = set()
        speech_action_ids: set[str] = set()
        ordered_types: list[str] = []
        widget_types: set[str] = set()
        discussion_peers: set[str] = set()
        discussion_action_count = 0
        teacher_action_count = 0
        speech_scene_count = 0
        speech_action_count = 0
        spotlight_observed = False
        widget_highlight_observed = False
        runtime_quiz_question_ids: list[str] = []
        runtime_event_scenes: list[dict[str, Any]] = []

        for expected_order, scene in enumerate(scenes):
            if not isinstance(scene, Mapping):
                self._fail(
                    "openmaic_formal_scene_invalid",
                    "正式候选课堂包含无法播放的场景",
                    502,
                )
            scene_id = str(scene.get("id") or "")
            scene_type = str(scene.get("type") or "")
            content = scene.get("content")
            if (
                not _bounded_identifier(scene_id)
                or scene_id in scene_ids
                or scene.get("stageId") != stage_id
                or not _nonempty_string(scene.get("title"))
                or type(scene.get("order")) is not int
                or int(scene["order"]) != expected_order
                or scene_type not in SCENE_TYPES
                or not isinstance(content, Mapping)
                or content.get("type") != scene_type
            ):
                self._fail(
                    "openmaic_formal_scene_invalid",
                    "正式候选课堂场景结构无法安全播放",
                    502,
                )
            scene_ids.add(scene_id)
            ordered_types.append(scene_type)

            if scene_type == "slide":
                canvas = content.get("canvas")
                elements = canvas.get("elements") if isinstance(canvas, Mapping) else None
                if (
                    not isinstance(elements, list)
                    or len(elements) > MAX_SLIDE_ELEMENTS
                    or any(not isinstance(element, Mapping) for element in elements)
                ):
                    self._fail(
                        "openmaic_formal_slide_invalid",
                        "正式候选课堂课件页无法渲染",
                        502,
                    )
            elif scene_type == "quiz":
                questions = content.get("questions")
                if (
                    not isinstance(questions, list)
                    or len(questions) > MAX_QUIZ_QUESTIONS
                    or any(not isinstance(question, Mapping) for question in questions)
                ):
                    self._fail(
                        "openmaic_formal_quiz_invalid",
                        "正式候选课堂测验页无法渲染",
                        502,
                    )
                runtime_quiz_question_ids.extend(
                    str(question["id"])
                    for question in questions
                    if _bounded_identifier(question.get("id"))
                )
            elif scene_type == "interactive":
                html = content.get("html")
                url = content.get("url")
                if (
                    (html is not None and not isinstance(html, str))
                    or (url is not None and not isinstance(url, str))
                    or (not _nonempty_string(html) and not _nonempty_string(url))
                ):
                    self._fail(
                        "openmaic_formal_interactive_invalid",
                        "正式候选课堂互动页没有可加载内容",
                        502,
                    )
                widget_type = content.get("widgetType")
                if _nonempty_string(widget_type):
                    widget_types.add(str(widget_type).strip())

            actions = scene.get("actions")
            if (
                not isinstance(actions, list)
                or not actions
                or len(actions) > MAX_SCENE_ACTIONS
            ):
                self._fail(
                    "openmaic_formal_actions_invalid",
                    "正式候选课堂场景缺少可播放动作",
                    502,
                )
            scene_speech_count = 0
            scene_action_ids: set[str] = set()
            for action in actions:
                if not isinstance(action, Mapping):
                    self._fail(
                        "openmaic_formal_action_invalid",
                        "正式候选课堂包含无法播放的动作",
                        502,
                    )
                action_id = str(action.get("id") or "")
                action_type = str(action.get("type") or "")
                if (
                    not _bounded_identifier(action_id)
                    or action_id in scene_action_ids
                    or not _nonempty_string(action_type)
                ):
                    self._fail(
                        "openmaic_formal_action_invalid",
                        "正式候选课堂动作缺少唯一编号或类型",
                        502,
                    )
                scene_action_ids.add(action_id)
                if action_type == "speech":
                    if (
                        not _nonempty_string(action.get("text"))
                        or action_id in speech_action_ids
                    ):
                        self._fail(
                            "openmaic_formal_speech_invalid",
                            "正式候选课堂讲解动作缺少可播讲稿或唯一编号",
                            502,
                        )
                    speech_action_ids.add(action_id)
                    scene_speech_count += 1
                    speech_action_count += 1
                elif action_type == "discussion":
                    discussion_action_count += 1
                    peer_id = str(action.get("agentId") or "")
                    if peer_id and roles.get(peer_id) in {"assistant", "student"}:
                        discussion_peers.add(peer_id)
                if action_type in {
                    "spotlight",
                    "laser",
                    *WHITEBOARD_DRAW_ACTIONS,
                    *WIDGET_TEACHER_ACTIONS,
                }:
                    teacher_action_count += 1
                if action_type == "spotlight":
                    spotlight_observed = True
                elif action_type == "widget_highlight":
                    widget_highlight_observed = True
            if scene_speech_count:
                speech_scene_count += 1
            runtime_event_scenes.append(
                {
                    "sceneIndex": expected_order,
                    "sceneId": scene_id,
                    "completionActionId": str(actions[-1]["id"]),
                    "questionIds": (
                        [
                            str(question["id"])
                            for question in content.get("questions", [])
                            if isinstance(question, Mapping)
                            and _bounded_identifier(question.get("id"))
                        ]
                        if scene_type == "quiz"
                        else []
                    ),
                }
            )

        if not 1 <= speech_action_count <= 240:
            self._fail(
                "openmaic_formal_speech_invalid",
                "正式候选课堂没有可生成语音的讲稿",
                502,
            )
        return {
            "sceneDistribution": {
                scene_type: ordered_types.count(scene_type)
                for scene_type in sorted(SCENE_TYPES)
            },
            "peerCount": sum(
                1 for role in roles.values() if role in {"assistant", "student"}
            ),
            "speechSceneCount": speech_scene_count,
            "speechActionCount": speech_action_count,
            "discussionActionCount": discussion_action_count,
            "distinctDiscussionPeerCount": len(discussion_peers),
            "teacherActionCount": teacher_action_count,
            "spotlightVerified": spotlight_observed,
            "widgetHighlightVerified": widget_highlight_observed,
            "widgetTypes": sorted(widget_types),
            "runtimeEventAuthority": {
                "schemaVersion": "mira.openmaic.runtime-event-authority.v1",
                "scenes": runtime_event_scenes,
            },
            "assessmentQuestionIds": runtime_quiz_question_ids,
            **({"teacher": teacher_evidence} if teacher_evidence else {}),
        }

    def _validate_formal_classroom_legacy_contract(
        self,
        classroom: Mapping[str, Any],
        *,
        teacher_contract: Mapping[str, Any] | None = None,
        assessment_questions: Sequence[Mapping[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Retain the former content rubric for historical fixture inspection.

        Formal generation and student launch no longer call this method.
        """

        stage = classroom.get("stage")
        scenes = classroom.get("scenes")
        contract = FORMAL_RUNTIME_CLASSROOM_CONTRACT
        if not isinstance(stage, Mapping) or not isinstance(scenes, list):
            self._fail(
                "openmaic_formal_classroom_invalid",
                "正式候选课堂缺少 stage 或 scenes",
                502,
            )
        _validate_stage(stage, fail=self._fail)
        scene_planning = contract["scenePlanning"]
        speech_policy = contract["speechActions"]
        per_scene_speech = speech_policy["perScene"]
        total_speech = speech_policy["total"]
        max_scene_count = int(scene_planning["maxSceneCount"])
        if not 1 <= len(scenes) <= max_scene_count:
            self._fail(
                "openmaic_formal_scene_count_invalid",
                "正式候选课堂场景数量无效",
                502,
            )
        roles = _stage_agent_roles(stage, fail=self._fail)
        teacher_ids = {key for key, role in roles.items() if role == "teacher"}
        peer_ids = {
            key for key, role in roles.items() if role in {"assistant", "student"}
        }
        if len(teacher_ids) != 1 or len(peer_ids) != 4 or len(roles) != 5:
            self._fail(
                "openmaic_formal_roster_invalid",
                "正式候选课堂必须包含一位老师和四位同伴",
                502,
            )
        teacher_evidence: dict[str, Any] | None = None
        if teacher_contract is not None:
            expected_runtime = teacher_contract.get("runtime")
            configs = stage.get("generatedAgentConfigs")
            teacher_id = next(iter(teacher_ids))
            teacher = next(
                (
                    item
                    for item in configs
                    if isinstance(item, Mapping)
                    and str(item.get("id") or "") == teacher_id
                ),
                None,
            ) if isinstance(configs, list) else None
            if (
                not isinstance(expected_runtime, Mapping)
                or not isinstance(expected_runtime.get("voiceConfig"), Mapping)
                or not isinstance(teacher, Mapping)
                or teacher.get("name") != expected_runtime.get("name")
                or teacher.get("role") != "teacher"
                or teacher.get("avatar") != expected_runtime.get("avatar")
                or teacher.get("voiceConfig")
                != expected_runtime.get("voiceConfig")
                or expected_runtime.get("teacherGender")
                not in {"female", "male"}
                or expected_runtime.get("voiceGender")
                != expected_runtime.get("teacherGender")
            ):
                self._fail(
                    "openmaic_formal_teacher_identity_mismatch",
                    "正式候选课堂老师头像、姓名或音色不一致",
                    502,
                )
            teacher_evidence = {
                "agentId": teacher_id,
                "name": str(expected_runtime["name"]),
                "avatar": str(expected_runtime["avatar"]),
                "teacherGender": str(expected_runtime["teacherGender"]),
                "voiceGender": str(expected_runtime["voiceGender"]),
                "voiceId": str(expected_runtime["voiceConfig"]["voiceId"]),
            }

        ordered_types: list[str] = []
        discussion_peers: set[str] = set()
        spotlight_verified = False
        widget_highlight_verified = False
        widget_types: set[str] = set()
        speech_scene_count = 0
        speech_action_count = 0
        speech_action_ids: set[str] = set()
        runtime_quiz_questions: list[Mapping[str, Any]] = []
        runtime_event_scenes: list[dict[str, Any]] = []
        stage_id = str(stage["id"])
        for expected_order, scene in enumerate(scenes):
            if not isinstance(scene, Mapping):
                self._fail(
                    "openmaic_formal_scene_invalid",
                    "正式候选课堂包含无效场景",
                    502,
                )
            _validate_scene_core(scene, stage_id=stage_id, fail=self._fail)
            if type(scene.get("order")) is not int or scene["order"] != expected_order:
                self._fail(
                    "openmaic_formal_scene_order_invalid",
                    "正式候选课堂场景顺序必须从零连续排列",
                    502,
                )
            scene_type = str(scene["type"])
            ordered_types.append(scene_type)
            content = scene["content"]
            elements: dict[str, Mapping[str, Any]] = {}
            html = ""
            if scene_type == "slide":
                elements = _validate_slide_content(content, fail=self._fail)
                if not any(_renderable_slide_element(item) for item in elements.values()):
                    self._fail(
                        "openmaic_formal_slide_empty",
                        "正式候选课堂的每个课件场景都必须有可见教学内容",
                        502,
                    )
            elif scene_type == "quiz":
                if _validate_quiz_content(
                    content, fail=self._fail, require_answers=False
                ) < 1:
                    self._fail(
                        "openmaic_formal_quiz_empty",
                        "正式候选课堂的每个测验场景都必须有可评分题目",
                        502,
                    )
                quiz_questions = content.get("questions")
                if any(
                    question.get("hasAnswer") is not False
                    or question.get("answer") not in (None, [])
                    for question in quiz_questions
                    if isinstance(question, Mapping)
                ):
                    self._fail(
                        "openmaic_formal_quiz_answer_exposed",
                        "正式候选课堂不得携带服务端答案或评分规则",
                        502,
                    )
                runtime_quiz_questions.extend(quiz_questions)
            elif scene_type == "interactive":
                (
                    widget_type,
                    has_html,
                    has_controls,
                    has_complete_interaction,
                ) = _validate_professional_interactive_content(
                    content,
                    fail=self._fail,
                    required_widget_types=frozenset(
                        contract["interactive"]["allowedWidgetTypes"]
                    ),
                )
                if (
                    not widget_type
                    or not has_html
                    or not has_controls
                    or not has_complete_interaction
                ):
                    self._fail(
                        "openmaic_formal_interactive_invalid",
                        "正式候选课堂的互动场景必须包含真实可操作脚本",
                        502,
                    )
                widget_types.add(widget_type)
                html = str(content.get("html") or "")
            elif scene_type == "pbl":
                if not _validate_pbl_content(content, fail=self._fail):
                    self._fail(
                        "openmaic_formal_pbl_invalid",
                        "正式候选课堂的项目场景必须可以真实执行",
                        502,
                    )
            else:
                self._fail(
                    "openmaic_formal_scene_type_invalid",
                    "正式候选课堂包含不支持的场景类型",
                    502,
                )

            actions = scene.get("actions")
            if not isinstance(actions, list):
                self._fail(
                    "openmaic_formal_actions_invalid",
                    "正式候选课堂动作格式无效",
                    502,
                )
            speech_indexes: list[int] = []
            valid_spotlight_indexes: set[int] = set()
            focus_explanation_verified = False
            for action_index, action in enumerate(actions):
                action_type, action_id = _validate_action(action, fail=self._fail)
                if action_type == "speech":
                    if (
                        not _nonempty_string(action.get("text"))
                        or action_id in speech_action_ids
                    ):
                        self._fail(
                            "openmaic_formal_speech_invalid",
                            "正式候选课堂每个场景都必须有完整讲稿",
                            502,
                        )
                    speech_action_ids.add(action_id)
                    speech_indexes.append(action_index)
                    if (
                        scene_type == "slide"
                        and action_index > 0
                        and action_index - 1 in valid_spotlight_indexes
                    ):
                        focus_explanation_verified = True
                elif action_type == "discussion":
                    peer_id = str(action.get("agentId") or "")
                    if peer_id not in peer_ids:
                        self._fail(
                            "openmaic_formal_discussion_invalid",
                            "正式候选课堂讨论必须绑定同伴 Agent",
                            502,
                        )
                    discussion_peers.add(peer_id)
                elif action_type == "spotlight":
                    target = str(action.get("elementId") or "")
                    if (
                        scene_type != "slide"
                        or target not in elements
                        or not _renderable_slide_element(elements[target])
                    ):
                        self._fail(
                            "openmaic_formal_spotlight_invalid",
                            "正式候选课堂聚光动作必须指向真实课件元素",
                            502,
                        )
                    spotlight_verified = True
                    valid_spotlight_indexes.add(action_index)
                elif action_type == "widget_highlight":
                    # OpenMAIC owns how an interactive widget resolves and
                    # animates its selector (including initially hidden or
                    # dynamically created targets). Mira only requires a
                    # declared selector on an otherwise operable widget.
                    if scene_type != "interactive" or not _nonempty_string(
                        action.get("target")
                    ):
                        self._fail(
                            "openmaic_formal_highlight_invalid",
                            "正式候选课堂高亮动作必须指向真实互动控件",
                            502,
                        )
                    widget_highlight_verified = True
            if not (
                int(per_scene_speech["min"])
                <= len(speech_indexes)
                <= int(per_scene_speech["max"])
            ):
                self._fail(
                    "openmaic_formal_speech_invalid",
                    "正式候选课堂每个场景必须包含 1 到 20 段讲解",
                    502,
                )
            if scene_type == "slide" and (
                len(valid_spotlight_indexes)
                < int(contract["slideSpotlight"]["minimumPerSlide"])
                or not focus_explanation_verified
            ):
                self._fail(
                    "openmaic_formal_slide_focus_sequence_invalid",
                    "正式候选课堂每个课件页都必须包含聚焦后紧邻讲解的有效序列",
                    502,
                )
            speech_scene_count += 1
            speech_action_count += len(speech_indexes)
            runtime_event_scenes.append(
                {
                    "sceneIndex": expected_order,
                    "sceneId": str(scene["id"]),
                    "completionActionId": str(actions[-1]["id"]),
                    "questionIds": (
                        [str(question["id"]) for question in content["questions"]]
                        if scene_type == "quiz"
                        else []
                    ),
                }
            )

        allowed_scene_types = set(scene_planning["allowedSceneTypes"])
        required_scene_types = set(scene_planning["requiredSceneTypes"])
        observed_scene_types = set(ordered_types)
        if not (
            int(total_speech["min"])
            <= speech_action_count
            <= int(total_speech["max"])
        ):
            self._fail(
                "openmaic_formal_speech_invalid",
                "正式候选课堂全课讲解段数必须在 1 到 240 之间",
                502,
            )
        if (
            not observed_scene_types.issubset(allowed_scene_types)
            or not required_scene_types.issubset(observed_scene_types)
        ):
            self._fail(
                "openmaic_formal_scene_distribution_invalid",
                "正式候选课堂必须包含课件、测验和互动场景",
                502,
            )
        if len(discussion_peers) < int(contract["distinctPeerDiscussions"]):
            self._fail(
                "openmaic_formal_discussion_incomplete",
                "正式候选课堂至少需要两位不同同伴参与讨论",
                502,
            )
        if not spotlight_verified or not widget_highlight_verified:
            self._fail(
                "openmaic_formal_teacher_evidence_missing",
                "正式候选课堂缺少真实聚光或互动高亮证据",
                502,
            )
        assessment_question_ids: list[str] = []
        if assessment_questions is not None:
            if len(assessment_questions) != 4 or len(runtime_quiz_questions) != 4:
                self._fail(
                    "openmaic_formal_assessment_mismatch",
                    "正式候选课堂测验与锁定评分题目不一致",
                    502,
                )
            for actual, expected in zip(
                runtime_quiz_questions, assessment_questions
            ):
                expected_options = expected.get("options")
                actual_options = actual.get("options")
                if (
                    str(actual.get("id") or "") != str(expected.get("id") or "")
                    or str(actual.get("question") or "")
                    != str(expected.get("question") or "")
                    or str(actual.get("type") or "")
                    != str(expected.get("runtimeType") or "")
                    or actual.get("hasAnswer") is not False
                    or actual.get("answer") not in (None, [])
                ):
                    self._fail(
                        "openmaic_formal_assessment_mismatch",
                        "正式候选课堂测验与锁定评分题目不一致",
                        502,
                    )
                if expected_options:
                    normalized_options = (
                        [
                            {
                                "value": str(option.get("value") or ""),
                                "label": str(option.get("label") or ""),
                            }
                            for option in actual_options
                        ]
                        if isinstance(actual_options, list)
                        and all(isinstance(option, Mapping) for option in actual_options)
                        else None
                    )
                    if normalized_options != list(expected_options):
                        self._fail(
                            "openmaic_formal_assessment_mismatch",
                            "正式候选课堂测验与锁定评分题目不一致",
                            502,
                        )
                elif actual_options not in (None, []):
                    self._fail(
                        "openmaic_formal_assessment_mismatch",
                        "正式候选课堂测验与锁定评分题目不一致",
                        502,
                    )
                assessment_question_ids.append(str(expected["id"]))
        return {
            "sceneDistribution": {
                scene_type: ordered_types.count(scene_type)
                for scene_type in scene_planning["allowedSceneTypes"]
            },
            "peerCount": 4,
            "speechSceneCount": speech_scene_count,
            "speechActionCount": speech_action_count,
            "distinctDiscussionPeerCount": len(discussion_peers),
            "spotlightVerified": spotlight_verified,
            "widgetHighlightVerified": widget_highlight_verified,
            "widgetTypes": sorted(widget_types),
            "runtimeEventAuthority": {
                "schemaVersion": "mira.openmaic.runtime-event-authority.v1",
                "scenes": runtime_event_scenes,
            },
            **(
                {"assessmentQuestionIds": assessment_question_ids}
                if assessment_questions is not None
                else {}
            ),
            **({"teacher": teacher_evidence} if teacher_evidence else {}),
        }

    def process_next_pending(self) -> dict[str, Any] | None:
        """Resume one persisted sample/formal job without blind redispatch."""

        self._require_generation()
        with self.repository.transaction() as conn:
            generating = self.repository.get_next_generating_runtime(conn)
        if generating is None:
            return None
        return self._process_persisted_runtime(generating)

    def process_pending_batch(
        self,
        *,
        limit: int = 100,
    ) -> dict[str, Any] | None:
        """Reconcile a bounded snapshot without head-of-line blocking.

        Every row was already durably reserved before this method sees it.
        Formal pending rows retain the existing request-id reconciliation
        contract, and generating rows are queried with GET only.  One
        terminal rejection or transient provider error therefore cannot stop
        reconciliation of the remaining jobs in the same worker pass.
        """

        self._require_generation()
        with self.repository.transaction() as conn:
            runtimes = self.repository.list_nonterminal_runtimes(
                conn,
                limit=limit,
            )
        if not runtimes:
            return None

        status_counts: dict[str, int] = {}
        errors: list[dict[str, str]] = []
        processed_count = 0
        for runtime in runtimes:
            try:
                payload = self._process_persisted_runtime(runtime)
            except OpenMaicRuntimeServiceError as exc:
                processed_count += 1
                errors.append(
                    {
                        "runtimeId": str(runtime.get("id") or ""),
                        "code": exc.code,
                        "message": exc.safe_message,
                    }
                )
                continue
            processed_count += 1
            reconciled = (
                payload.get("runtime") if isinstance(payload, Mapping) else None
            )
            status = (
                str(reconciled.get("status") or "unknown")
                if isinstance(reconciled, Mapping)
                else "unknown"
            )
            status_counts[status] = status_counts.get(status, 0) + 1

        return {
            "ok": not errors,
            "processedCount": processed_count,
            "statusCounts": status_counts,
            "errors": errors,
        }

    def _process_persisted_runtime(
        self,
        generating: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Reconcile one authoritative row selected by a worker pass."""

        timestamp = now_ms()
        formal_candidate = bool(generating.get("candidate_build_item_id"))
        updated_at = int(generating.get("updated_at") or 0)
        if (
            not formal_candidate
            and timestamp - updated_at >= SAMPLE_GENERATION_STALE_AFTER_MS
        ):
            with self.repository.transaction() as conn:
                self.repository.mark_failed(
                    conn,
                    runtime_id=str(generating["id"]),
                    error_code="openmaic_sample_generation_stale",
                    error_message_safe=(
                        "样板课堂生成超过有限等待时间，已终结且不会自动重试"
                    ),
                    now=timestamp,
                )
                terminal = self.repository.get_runtime_classroom(
                    conn,
                    runtime_id=str(generating["id"]),
                )
            return self._runtime_payload(terminal)
        if str(generating.get("status") or "") == "pending":
            if formal_candidate:
                return dict(
                    self.issue_candidate_generation(
                        build_item_id=str(
                            generating["candidate_build_item_id"]
                        ),
                        course_id=str(generating["course_id"]),
                        course_version=str(generating["course_version"]),
                        package_id=str(generating["package_id"]),
                        package_version=int(generating["package_version"]),
                        target_fingerprint=str(
                            generating["candidate_target_fingerprint"]
                        ),
                        runtime_request_id=str(generating["request_id"]),
                    )
                )
            # The explicit request may still be between its DB insert and the
            # upstream start call.  The runner never starts or retries it; a
            # later pass will terminally fail it only after the stale limit.
            return self._runtime_payload(generating)
        upstream_job_id = str(generating.get("upstream_job_id") or "")
        if not upstream_job_id:
            if formal_candidate:
                self._quarantine_formal_generation(
                    generating,
                    message=(
                        "正式候选课堂缺少已绑定的上游任务编号，"
                        "已隔离且不会自动重发"
                    ),
                )
                with self.repository.transaction() as conn:
                    terminal = self.repository.get_runtime_classroom(
                        conn, runtime_id=str(generating["id"])
                    )
                return self._runtime_payload(terminal)
            with self.repository.transaction() as conn:
                self.repository.mark_failed(
                    conn,
                    runtime_id=str(generating["id"]),
                    error_code="openmaic_sample_generation_incomplete",
                    error_message_safe="样板课堂缺少上游任务编号，已终结",
                    now=timestamp,
                )
                terminal = self.repository.get_runtime_classroom(
                    conn,
                    runtime_id=str(generating["id"]),
                )
                return self._runtime_payload(terminal)
        return self.generation_status(upstream_job_id)

    def revalidate_formal_feature_evidence(
        self,
        *,
        family_id: str,
        child_id: str,
        learning_session_id: str,
        classroom: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Repair obsolete feature summaries from the exact published artifact.

        This never changes classroom content or publication/audio receipts. The
        complete launch gate must accept the recomputed summary before saving it.
        """
        with self.repository.transaction() as conn:
            authority = self.repository.get_owned_session_runtime(
                conn,
                family_id=family_id,
                child_id=child_id,
                learning_session_id=learning_session_id,
            )
            if authority is None or authority.get("runtime_status") != "ready":
                raise ValueError("a ready owned formal classroom is required")
            manifest = self.repository.decode_json(
                authority.get("feature_manifest_json"), {}
            )
            content_hash = _canonical_sha256(
                {"stage": classroom.get("stage"), "scenes": classroom.get("scenes")}
            )
            if (
                content_hash != manifest.get("classroomContentSha256")
                or not isinstance(classroom.get("stage"), Mapping)
                or classroom["stage"].get("id") != authority.get("upstream_classroom_id")
            ):
                raise ValueError("published classroom content identity changed")
            actual = self._validate_formal_classroom(
                classroom,
                teacher_contract=self._formal_teacher_contract(
                    str(authority.get("course_subject") or "")
                ),
            )
            recorded = manifest.get("formalEvidence")
            if not isinstance(recorded, Mapping) or any(
                actual.get(key) != value
                for key, value in recorded.items()
                if key not in {"professionalCreation", "research", "media"}
            ):
                raise ValueError("published formal classroom evidence changed")
            required = set(_formal_required_features(actual))
            if required != set(manifest.get("required") or []):
                raise ValueError("published classroom capability identity changed")
            evidence = dict(manifest.get("evidence") or {})
            repaired: dict[str, list[str]] = {}
            for scene in classroom["scenes"]:
                if scene.get("type") != "interactive":
                    continue
                content = scene.get("content") or {}
                feature = FORMAL_WIDGET_FEATURE_BY_TYPE.get(content.get("widgetType"))
                if (
                    feature in required
                    and (evidence.get(feature) or {}).get("verified") is not True
                ):
                    repaired.setdefault(feature, []).append(
                        f"scene:{scene['id']}:formal-artifact:{content['widgetType']}"
                    )
            for feature, signals in repaired.items():
                evidence[feature] = {"verified": True, "signals": signals, "reasons": []}
            updated = {**manifest, "evidence": evidence}
            if self._formal_manifest_for_launch(updated, authority) is None:
                raise ValueError("revalidated artifact still fails the complete launch contract")
            if repaired:
                self.repository.replace_formal_feature_evidence(
                    conn,
                    runtime_id=str(authority["runtime_classroom_id"]),
                    expected_manifest=manifest,
                    updated_manifest=updated,
                    now=now_ms(),
                )
            return {
                "runtimeId": authority["runtime_classroom_id"],
                "classroomContentSha256": content_hash,
                "revalidatedFeatures": repaired,
                "launchContractVerified": True,
            }

    def _formal_manifest_for_launch(
        self,
        manifest: object,
        authority: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        try:
            return self._formal_manifest_for_launch_unchecked(
                manifest, authority
            )
        except (TypeError, ValueError, OverflowError):
            return None

    @staticmethod
    def _formal_quality_status_allows_student_access(
        authority: Mapping[str, Any],
    ) -> bool:
        """Keep every formal student-access path on one quality allowlist."""

        return str(authority.get("runtime_quality_status") or "") in {
            "pending_review",
            "approved",
        }

    def _require_formal_quality_for_student_access(
        self,
        authority: Mapping[str, Any],
    ) -> None:
        if not self._formal_quality_status_allows_student_access(authority):
            self._fail(
                "openmaic_formal_quality_not_allowed",
                "正式课堂未通过内容与发音质量审核",
                409,
            )

    @staticmethod
    def _formal_session_binding_state(
        authority: Mapping[str, Any],
        *,
        family_id: str | None = None,
        child_id: str | None = None,
    ) -> tuple[bool, bool]:
        """Return whether an immutable formal binding is present and exact.

        The grade pointer is consulted only while the binding is created.  A
        later pointer switch must not move an in-progress student session to a
        different release, package, or Runtime classroom.
        """

        binding_keys = (
            "formal_binding_learning_session_id",
            "formal_binding_family_id",
            "formal_binding_child_id",
            "formal_binding_grade_code",
            "formal_binding_authority_kind",
            "formal_binding_pointer_history_id",
            "formal_binding_preparation_plan_id",
            "formal_binding_release_id",
            "formal_binding_target_fingerprint",
            "formal_binding_contract_version",
            "formal_binding_runtime_contract_version",
            "formal_binding_build_item_id",
            "formal_binding_course_id",
            "formal_binding_course_version",
            "formal_binding_package_id",
            "formal_binding_package_content_hash",
            "formal_binding_runtime_classroom_id",
            "formal_binding_upstream_classroom_id",
        )
        present = any(authority.get(key) not in (None, "") for key in binding_keys)
        if not present:
            return False, False
        try:
            pointer_revision = int(
                authority.get("formal_binding_pointer_revision") or 0
            )
            binding_grade_revision = int(
                authority.get("formal_binding_grade_selection_revision") or 0
            )
            child_grade_revision = int(
                authority.get("child_grade_selection_revision") or 0
            )
            binding_package_version = int(
                authority.get("formal_binding_package_version") or 0
            )
            session_package_version = int(
                authority.get("lesson_package_version") or 0
            )
        except (TypeError, ValueError, OverflowError):
            return True, False
        target_fingerprint = str(
            authority.get("formal_binding_target_fingerprint") or ""
        )
        expected_family_id = family_id or str(authority.get("family_id") or "")
        expected_child_id = child_id or str(authority.get("child_id") or "")
        authority_kind = str(
            authority.get("formal_binding_authority_kind") or ""
        )
        pointer_authority_valid = bool(
            authority_kind == "active_pointer"
            and str(authority.get("formal_binding_pointer_history_id") or "")
            and pointer_revision >= 1
            and not str(
                authority.get("formal_binding_preparation_plan_id") or ""
            )
            and binding_grade_revision == 0
        )
        progressive_authority_valid = bool(
            authority_kind == "progressive_plan"
            and not str(
                authority.get("formal_binding_pointer_history_id") or ""
            )
            and pointer_revision == 0
            and str(
                authority.get("formal_binding_preparation_plan_id") or ""
            )
            and binding_grade_revision >= 1
            and binding_grade_revision == child_grade_revision
        )
        exact = bool(
            str(authority.get("formal_binding_learning_session_id") or "")
            == str(authority.get("learning_session_id") or "")
            and (
                not expected_family_id
                or str(authority.get("formal_binding_family_id") or "")
                == expected_family_id
            )
            and (
                not expected_child_id
                or str(authority.get("formal_binding_child_id") or "")
                == expected_child_id
            )
            and str(authority.get("formal_binding_grade_code") or "")
            == str(authority.get("candidate_grade_code") or "")
            == str(authority.get("course_grade_code") or "")
            == str(authority.get("child_grade_code") or "")
            and (pointer_authority_valid or progressive_authority_valid)
            and str(authority.get("formal_binding_release_id") or "")
            == str(authority.get("candidate_release_id") or "")
            and re.fullmatch(r"[0-9a-f]{64}", target_fingerprint) is not None
            and target_fingerprint
            == str(authority.get("candidate_target_fingerprint") or "")
            and str(authority.get("formal_binding_contract_version") or "")
            == "mira.learning.formal-publication.v1"
            and str(
                authority.get("formal_binding_runtime_contract_version") or ""
            )
            == str(authority.get("candidate_binding_contract_version") or "")
            == "mira.learning.candidate-runtime-binding.v1"
            and str(authority.get("formal_binding_build_item_id") or "")
            == str(authority.get("candidate_build_item_id") or "")
            and str(authority.get("formal_binding_course_id") or "")
            == str(authority.get("course_id") or "")
            and str(authority.get("formal_binding_course_version") or "")
            == str(authority.get("course_version") or "")
            and str(authority.get("formal_binding_package_id") or "")
            == str(authority.get("lesson_package_id") or "")
            and binding_package_version == session_package_version
            and binding_package_version > 0
            and str(
                authority.get("formal_binding_package_content_hash") or ""
            )
            == str(authority.get("lesson_package_content_hash") or "")
            and re.fullmatch(
                r"[0-9a-f]{64}",
                str(
                    authority.get("formal_binding_package_content_hash") or ""
                ),
            )
            is not None
            and str(
                authority.get("formal_binding_runtime_classroom_id") or ""
            )
            == str(authority.get("runtime_classroom_id") or "")
            and str(
                authority.get("formal_binding_upstream_classroom_id") or ""
            )
            == str(authority.get("upstream_classroom_id") or "")
        )
        return True, exact

    def _formal_manifest_for_launch_unchecked(
        self,
        manifest: object,
        authority: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Return one student-safe formal manifest from exact durable evidence.

        Task-13 classroom JSON remains immutable.  The subject teacher identity
        is attached from the Task-14 sidecar only after the grade pointer, 057
        publication receipt, 058 audio receipt and either the historical 059
        Provider receipt or the artifact-v1 execution receipt all resolve to
        the same build/runtime/course/package/content identity.
        """

        if not isinstance(manifest, Mapping):
            return None
        if not self._formal_quality_status_allows_student_access(authority):
            return None
        generation = manifest.get("generationContract")
        formal_evidence = manifest.get("formalEvidence")
        if not isinstance(generation, Mapping) or not isinstance(
            formal_evidence, Mapping
        ):
            return None
        generation_course = generation.get("course")
        teaching_brief = generation.get("teachingBrief")
        brief_course = (
            teaching_brief.get("course")
            if isinstance(teaching_brief, Mapping)
            else None
        )
        if not isinstance(generation_course, Mapping) or not isinstance(
            brief_course, Mapping
        ):
            return None

        required_features = set(_formal_required_features(formal_evidence))
        feature_lists = (
            manifest.get("enabled"),
            manifest.get("requested"),
            manifest.get("required"),
        )
        evidence = manifest.get("evidence")
        feature_contract_valid = bool(
            all(
                isinstance(features, list)
                and len(features) == len(required_features)
                and set(features) == required_features
                for features in feature_lists
            )
            and isinstance(manifest.get("present"), list)
            and required_features.issubset(set(manifest["present"]))
            and manifest.get("missing") == []
            and isinstance(evidence, Mapping)
            and all(
                isinstance(evidence.get(feature), Mapping)
                and evidence[feature].get("verified") is True
                for feature in required_features
            )
        )
        scene_count = manifest.get("sceneCount")
        scene_planning = FORMAL_RUNTIME_CLASSROOM_CONTRACT["scenePlanning"]
        scene_distribution = formal_evidence.get("sceneDistribution")
        distribution_valid = bool(
            type(scene_count) is int
            and 1 <= scene_count <= int(scene_planning["maxSceneCount"])
            and isinstance(scene_distribution, Mapping)
            and set(scene_distribution).issubset(SCENE_TYPES)
            and all(
                type(scene_distribution.get(scene_type)) is int
                and int(scene_distribution[scene_type]) >= 0
                for scene_type in scene_distribution
            )
            and sum(int(count) for count in scene_distribution.values())
            == scene_count
        )
        widget_types = formal_evidence.get("widgetTypes")
        runtime_event_authority = formal_evidence.get("runtimeEventAuthority")
        runtime_event_scenes = (
            runtime_event_authority.get("scenes")
            if isinstance(runtime_event_authority, Mapping)
            else None
        )
        runtime_event_authority_valid = bool(
            isinstance(runtime_event_authority, Mapping)
            and runtime_event_authority.get("schemaVersion")
            == "mira.openmaic.runtime-event-authority.v1"
            and isinstance(runtime_event_scenes, list)
            and type(scene_count) is int
            and len(runtime_event_scenes) == scene_count
            and all(
                isinstance(scene, Mapping)
                and scene.get("sceneIndex") == index
                for index, scene in enumerate(runtime_event_scenes)
            )
        )
        speech_action_count = formal_evidence.get("speechActionCount")
        speech_scene_count = formal_evidence.get("speechSceneCount")
        peer_count = formal_evidence.get("peerCount")
        distinct_discussion_peer_count = formal_evidence.get(
            "distinctDiscussionPeerCount"
        )
        formal_evidence_valid = bool(
            distribution_valid
            and isinstance(peer_count, int)
            and not isinstance(peer_count, bool)
            and int(peer_count) >= 0
            and isinstance(speech_scene_count, int)
            and not isinstance(speech_scene_count, bool)
            and 1 <= int(speech_scene_count) <= scene_count
            and type(speech_action_count) is int
            and 1 <= speech_action_count <= 240
            and int(speech_scene_count) <= speech_action_count
            and isinstance(distinct_discussion_peer_count, int)
            and not isinstance(distinct_discussion_peer_count, bool)
            and int(distinct_discussion_peer_count) >= 0
            and isinstance(formal_evidence.get("spotlightVerified"), bool)
            and isinstance(formal_evidence.get("widgetHighlightVerified"), bool)
            and isinstance(widget_types, list)
            and widget_types == sorted(set(widget_types))
            and runtime_event_authority_valid
        )

        build_item_id = str(authority.get("candidate_build_item_id") or "")
        release_id = str(authority.get("candidate_release_id") or "")
        grade_code = str(authority.get("candidate_grade_code") or "")
        target_fingerprint = str(
            authority.get("candidate_target_fingerprint") or ""
        )
        runtime_id = str(authority.get("runtime_classroom_id") or "")
        runtime_request_id = str(authority.get("runtime_request_id") or "")
        course_id = str(authority.get("course_id") or "")
        course_version = str(authority.get("course_version") or "")
        package_id = str(authority.get("lesson_package_id") or "")
        package_version = int(authority.get("lesson_package_version") or 0)
        subject = str(authority.get("course_subject") or "")
        classroom_sha256 = str(manifest.get("classroomContentSha256") or "")
        audio_receipt_hash = str(
            authority.get("formal_audio_receipt_hash") or ""
        )
        provider_receipt_hash = str(
            authority.get("formal_provider_receipt_hash") or ""
        )
        artifact_generation_receipt_hash = str(
            authority.get("candidate_generation_evidence_receipt_hash") or ""
        )
        artifact_validation_receipt_hash = str(
            authority.get("candidate_auto_validation_receipt_hash") or ""
        )
        professional_raw = manifest.get("professionalCreation")
        research_raw = manifest.get("research")
        professional_evidence = formal_evidence.get("professionalCreation")
        research_evidence = formal_evidence.get("research")
        try:
            selected_policy = professional_policy(generation.get("professionalCreationPolicy"))
            validate_generation_grade_boundary(generation, {
                "id": course_id, "version": course_version,
                "grade_code": authority.get("course_grade_code"),
                "subject": authority.get("course_subject"),
                "node_code": authority.get("course_node_code"),
                "curriculum_version": authority.get("course_curriculum_version"),
                "boundary_version": authority.get("course_boundary_version"),
            })
            validate_media_manifest(manifest)
            if adaptive_policy(selected_policy):
                if formal_evidence.get("assessmentQuestionIds") != [
                    question["id"] for question in self._formal_runtime_assessment_contract(generation)
                ]:
                    return None
            professional_receipt = (
                OpenMaicFullRuntimeClient._professional_creation_receipt_from_payload(
                    professional_raw,
                    runtime_request_id=runtime_request_id,
                    classroom_id=str(
                        authority.get("upstream_classroom_id") or ""
                    ),
                )
            )
            research_receipt = (
                OpenMaicFullRuntimeClient._research_receipt_from_payload(
                    research_raw,
                    runtime_request_id=runtime_request_id,
                    classroom_id=str(
                        authority.get("upstream_classroom_id") or ""
                    ),
                )
            )
        except (OpenMaicFullRuntimeError, ValueError, KeyError):
            return None
        cited_scene_ids = {
            str(scene_id)
            for citation in research_receipt["citations"]
            for scene_id in citation["sceneIds"]
        }
        professional_generation_valid = bool(
            professional_receipt.get("buildItemId") == build_item_id
            and research_receipt.get("buildItemId") == build_item_id
            and professional_receipt.get("sessionId")
            == research_receipt.get("sessionId")
            and professional_receipt.get("teachingBriefSha256")
            == manifest.get("teachingBriefSha256")
            and generation.get("coursewareAuthority")
            == OpenMaicFullRuntimeClient.COURSEWARE_AUTHORITY
            and generation.get("professionalCreationPolicy")
            == selected_policy
            and generation.get("generation")
            == generation_options(selected_policy)
            and professional_evidence
            == {
                "verified": True,
                "schemaVersion": professional_receipt["schemaVersion"],
                "sessionId": professional_receipt["sessionId"],
                "workflowVersion": professional_receipt["workflowVersion"],
                "skillId": professional_receipt["skillId"],
                "supportingSkillIds": list(
                    professional_receipt["supportingSkillIds"]
                ),
                "userPromptRequired": False,
                "studentToolsEnabled": False,
                "webSearchEnabled": True,
                **professional_image_fields(professional_receipt),
                **professional_video_fields(professional_receipt),
                **professional_skill_fields(professional_receipt),
                **professional_quality_fields(professional_receipt),
                **professional_interaction_fields(professional_receipt),
                "receiptSha256": professional_receipt["receiptSha256"],
            }
            and research_evidence
            == {
                "verified": True,
                "schemaVersion": research_receipt["schemaVersion"],
                "sessionId": research_receipt["sessionId"],
                "providerId": research_receipt["providerId"],
                "searchCount": research_receipt["searchCount"],
                "resultCount": research_receipt["resultCount"],
                "fetchedSourceCount": research_receipt[
                    "fetchedSourceCount"
                ],
                "citationCount": research_receipt["citationCount"],
                "citedSceneCount": len(cited_scene_ids),
                "receiptSha256": research_receipt["receiptSha256"],
            }
        )
        try:
            voice = get_formal_subject_qwen_voice_identity(subject)
            profile = get_teacher_profile(
                voice.teacher_profile_id,
                voice.teacher_profile_version,
            )
            teacher_contract = self._formal_teacher_contract(subject)
        except (KeyError, ValueError):
            return None
        runtime_teacher = teacher_contract["runtime"]
        formal_teacher = formal_evidence.get("teacher")
        teacher_evidence_valid = bool(
            isinstance(formal_teacher, Mapping)
            and _bounded_identifier(formal_teacher.get("agentId"))
            and formal_teacher
            == {
                "agentId": str(formal_teacher.get("agentId")),
                "name": runtime_teacher["name"],
                "avatar": runtime_teacher["avatar"],
                "teacherGender": runtime_teacher["teacherGender"],
                "voiceGender": runtime_teacher["voiceGender"],
                "voiceId": runtime_teacher["voiceConfig"]["voiceId"],
            }
        )
        binding_present, binding_valid = self._formal_session_binding_state(
            authority
        )
        publication_valid = bool(
            build_item_id
            and release_id
            and grade_code
            and runtime_id
            and binding_present
            and binding_valid
            and str(authority.get("candidate_publication_status") or "")
            == "published"
            and int(authority.get("candidate_auto_validated") or 0) == 1
            and str(authority.get("candidate_tts_status") or "") == "passed"
            and str(authority.get("candidate_asr_status") or "") == "passed"
            and str(authority.get("candidate_conversation_status") or "")
            == "passed"
        )
        formal_audio_expected_count = int(
            authority.get("formal_audio_expected_segment_count") or 0
        )
        audio_valid = bool(
            str(authority.get("formal_audio_state") or "") == "auto_validated"
            and str(authority.get("formal_audio_release_id") or "") == release_id
            and str(authority.get("formal_audio_grade_code") or "") == grade_code
            and str(authority.get("formal_audio_target_fingerprint") or "")
            == target_fingerprint
            and str(authority.get("formal_audio_runtime_classroom_id") or "")
            == runtime_id
            and str(authority.get("formal_audio_course_id") or "") == course_id
            and str(authority.get("formal_audio_course_version") or "")
            == course_version
            and str(authority.get("formal_audio_package_id") or "") == package_id
            and int(authority.get("formal_audio_package_version") or 0)
            == package_version
            and str(authority.get("formal_audio_classroom_sha256") or "")
            == classroom_sha256
            and str(authority.get("formal_audio_subject") or "") == subject
            and formal_audio_expected_count == speech_action_count
            and 1 <= formal_audio_expected_count <= 240
            and int(authority.get("formal_audio_tts_attempted_count") or 0)
            == formal_audio_expected_count
            and int(authority.get("formal_audio_tts_completed_count") or 0)
            == formal_audio_expected_count
            and int(authority.get("formal_audio_validated_count") or 0)
            == formal_audio_expected_count
            and int(authority.get("formal_audio_asr_attempted_count") or 0)
            == formal_audio_expected_count
            and int(authority.get("formal_audio_asr_passed_count") or 0)
            == formal_audio_expected_count
        )
        legacy_provider_valid = bool(
            str(authority.get("formal_provider_state") or "")
            == "auto_validated"
            and str(authority.get("formal_provider_release_id") or "")
            == release_id
            and str(authority.get("formal_provider_grade_code") or "")
            == grade_code
            and str(authority.get("formal_provider_target_fingerprint") or "")
            == target_fingerprint
            and int(authority.get("formal_provider_expected_count") or 0) == 5
            and int(authority.get("formal_provider_attempted_count") or 0) == 5
            and int(authority.get("formal_provider_passed_count") or 0) == 5
            and int(authority.get("formal_route_provider_call") or 0) == 0
            and str(authority.get("formal_route_status") or "") == "passed"
        )
        artifact_validation_valid = bool(
            str(
                authority.get("candidate_auto_validation_contract_version")
                or ""
            )
            == CURRENT_ARTIFACT_PUBLICATION_CONTRACT_VERSION
            and str(authority.get("candidate_conversation_status") or "")
            == "passed"
            and int(authority.get("candidate_auto_validated") or 0) == 1
            and re.fullmatch(
                r"[0-9a-f]{64}", artifact_generation_receipt_hash
            )
            is not None
            and artifact_validation_receipt_hash
            == artifact_generation_receipt_hash
        )
        provider_valid = legacy_provider_valid or artifact_validation_valid
        publication_authority_receipt_hash = (
            artifact_validation_receipt_hash
            if artifact_validation_valid
            else provider_receipt_hash
        )
        sha256_values = (
            target_fingerprint,
            classroom_sha256,
            audio_receipt_hash,
            publication_authority_receipt_hash,
            str(professional_receipt.get("receiptSha256") or ""),
            str(research_receipt.get("receiptSha256") or ""),
        )
        generation_valid = bool(
            manifest.get("schemaVersion") == self.MANIFEST_SCHEMA
            and manifest.get("sourceVersion") == self.SOURCE_VERSION
            and manifest.get("sourceCommit") == self.SOURCE_COMMIT
            and manifest.get("formalRuntimeContract")
            == FORMAL_RUNTIME_CLASSROOM_CONTRACT
            and generation.get("schemaVersion")
            == OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION
            and generation.get("authority") == "mira_backend_formal_candidate"
            and str(generation.get("buildItemId") or "") == build_item_id
            and str(generation.get("targetFingerprint") or "")
            == target_fingerprint
            and str(generation.get("runtimeRequestId") or "")
            == runtime_request_id
            and str(generation_course.get("id") or "") == course_id
            and str(generation_course.get("version") or "") == course_version
            and str(generation_course.get("packageId") or "") == package_id
            and int(generation_course.get("packageVersion") or 0)
            == package_version
            and str(brief_course.get("id") or "") == course_id
            and str(brief_course.get("version") or "") == course_version
            and str(brief_course.get("gradeCode") or "") == grade_code
            and str(brief_course.get("subject") or "") == subject
            and generation.get("requiredClassroom")
            == FORMAL_RUNTIME_CLASSROOM_CONTRACT
            and generation.get("teacher") == teacher_contract
        )
        if not (
            feature_contract_valid
            and formal_evidence_valid
            and publication_valid
            and audio_valid
            and provider_valid
            and generation_valid
            and professional_generation_valid
            and teacher_evidence_valid
            and package_version > 0
            and all(re.fullmatch(r"[0-9a-f]{64}", value) for value in sha256_values)
        ):
            return None

        expected_voice = voice.to_target_payload()
        persisted_voice = {
            "schemaVersion": expected_voice["schemaVersion"],
            "teacherProfile": {
                "id": str(
                    authority.get("formal_audio_teacher_profile_id") or ""
                ),
                "version": int(
                    authority.get("formal_audio_teacher_profile_version") or 0
                ),
                "contentHash": str(
                    authority.get("formal_audio_teacher_profile_hash") or ""
                ),
            },
            "teacherName": str(
                authority.get("formal_audio_teacher_name") or ""
            ),
            "teacherGender": str(
                authority.get("formal_audio_teacher_gender") or ""
            ),
            "voiceGender": str(
                authority.get("formal_audio_voice_gender") or ""
            ),
            "voiceId": str(authority.get("formal_audio_voice_id") or ""),
            "languageCode": str(
                authority.get("formal_audio_language_code") or ""
            ),
            "tts": expected_voice["tts"],
            "asr": expected_voice["asr"],
        }
        if persisted_voice != expected_voice:
            return None
        teacher_identity = {
            "verified": True,
            "agentId": str(formal_teacher["agentId"]),
            "subject": subject,
            "avatarPath": profile.avatar_path,
            "runtimeAvatar": str(runtime_teacher["avatar"]),
            **expected_voice,
        }
        existing_teacher = manifest.get("teacherIdentity")
        if existing_teacher is not None and existing_teacher != teacher_identity:
            return None
        student_manifest = dict(manifest)
        student_manifest.pop("paidBudget", None)
        student_manifest["teacherIdentity"] = teacher_identity
        return student_manifest

    def create_student_launch(
        self, access_token: str, learning_session_id: str
    ) -> dict[str, Any]:
        self._require_runtime()
        session_id = _required_identifier(
            learning_session_id, "sessionId", 255
        )
        context = self.student_auth_service.authenticate(access_token)
        principal = context["principal"]
        timestamp = now_ms()
        ticket = new_token("omt")
        with self.repository.transaction() as conn:
            runtime = self.repository.get_owned_session_runtime(
                conn,
                family_id=str(principal["family_id"]),
                child_id=str(principal["child_id"]),
                learning_session_id=session_id,
            )
            if runtime is None:
                self._fail(
                    "learning_session_not_found", "没有找到这节课的学习会话", 404
                )
            if str(runtime.get("child_grade_code") or "") != str(
                runtime.get("course_grade_code") or ""
            ):
                self._fail(
                    "openmaic_student_grade_mismatch",
                    "学生当前年级与这节正式课程不一致",
                    409,
                )
            candidate_release_id = str(
                runtime.get("candidate_release_id") or ""
            )
            candidate_build_item_id = str(
                runtime.get("candidate_build_item_id") or ""
            )
            candidate_identity_present = any(
                (
                    candidate_release_id,
                    candidate_build_item_id,
                    str(runtime.get("candidate_grade_code") or ""),
                    str(runtime.get("candidate_target_fingerprint") or ""),
                )
            )
            formal_candidate = bool(
                candidate_release_id
                and candidate_build_item_id
            )
            if candidate_identity_present and not formal_candidate:
                self._fail(
                    "openmaic_candidate_not_activated",
                    "这节候选课堂的正式发布身份不完整",
                    404,
                )
            if formal_candidate:
                self._require_formal_quality_for_student_access(runtime)
                binding_present, binding_valid = (
                    self._formal_session_binding_state(
                        runtime,
                        family_id=str(principal["family_id"]),
                        child_id=str(principal["child_id"]),
                    )
                )
                if binding_present and not binding_valid:
                    self._fail(
                        "openmaic_session_binding_conflict",
                        "这次学习绑定的正式课堂身份不一致",
                        409,
                    )
                if not binding_valid:
                    self.repository.bind_formal_session_to_active_release(
                        conn,
                        family_id=str(principal["family_id"]),
                        child_id=str(principal["child_id"]),
                        learning_session_id=session_id,
                        now=timestamp,
                    )
                    runtime = self.repository.get_owned_session_runtime(
                        conn,
                        family_id=str(principal["family_id"]),
                        child_id=str(principal["child_id"]),
                        learning_session_id=session_id,
                    )
                    binding_present, binding_valid = (
                        self._formal_session_binding_state(
                            runtime or {},
                            family_id=str(principal["family_id"]),
                            child_id=str(principal["child_id"]),
                        )
                    )
                if not binding_valid:
                    self._fail(
                        "openmaic_candidate_not_activated",
                        "这节正式课堂尚未完成发布绑定",
                        404,
                    )
            if not formal_candidate and (
                str(runtime.get("course_grade_code") or "") != SAMPLE_GRADE_CODE
                or str(runtime.get("course_subject") or "") != SAMPLE_SUBJECT
                or str(runtime.get("course_node_code") or "") != SAMPLE_SKILL_ID
            ):
                self._fail(
                    "openmaic_runtime_not_available",
                    "本阶段只开放一年级数学数感样板课堂",
                    404,
                )
            runtime_id = runtime.get("runtime_classroom_id")
            runtime_status = str(runtime.get("runtime_status") or "")
            if not runtime_id:
                self._fail(
                    "openmaic_runtime_not_available",
                    "这节课暂时没有完整互动课堂",
                    404,
                )
            if runtime_status in {"pending", "generating"}:
                self._fail(
                    "openmaic_runtime_preparing",
                    "完整互动课堂仍在制作中，请稍后再来",
                    409,
                )
            if runtime_status != "ready" or not runtime.get(
                "upstream_classroom_id"
            ):
                self._fail(
                    "openmaic_runtime_not_available",
                    "完整互动课堂暂时不可用",
                    404,
                )
            if (
                not formal_candidate
                and str(runtime.get("runtime_quality_status") or "")
                != "approved"
            ):
                self._fail(
                    "openmaic_runtime_review_pending",
                    "完整互动课堂仍在内容与发音审核中",
                    409,
                )
            manifest = self.repository.decode_json(
                runtime.get("feature_manifest_json"), {}
            )
            if formal_candidate:
                formal_manifest = self._formal_manifest_for_launch(
                    manifest, runtime
                )
                if formal_manifest is None:
                    self._fail(
                        "openmaic_formal_contract_not_verified",
                        "正式课堂的发布、老师、语音或对话合同尚未验证",
                        409,
                )
                manifest = formal_manifest
            else:
                if not self._sample_manifest_verified(manifest):
                    self._fail(
                        "openmaic_sample_contract_not_verified",
                        "样板课堂的课程、老师或正式语音合同尚未验证",
                        409,
                    )
            self.repository.revoke_active_launch_tickets(
                conn,
                principal_id=str(principal["id"]),
                learning_session_id=session_id,
                now=timestamp,
            )
            self.repository.create_launch_ticket(
                conn,
                ticket_id=new_token("omti"),
                token_hash=hash_value(ticket),
                principal=principal,
                learning_session_id=session_id,
                runtime_classroom_id=str(runtime_id),
                expires_at=timestamp + self.launch_ttl_seconds * 1000,
                now=timestamp,
            )
        launch_url = f"{self.public_url}/mira/launch?{urlencode({'ticket': ticket})}"
        return {
            "ok": True,
            "mode": "openmaic_full_runtime",
            "launchUrl": launch_url,
            "expiresAt": timestamp + self.launch_ttl_seconds * 1000,
            "features": manifest,
            "assessmentAuthority": "mira_backend",
        }

    def review_classroom(self, runtime_id: str, data: Mapping[str, Any]) -> dict[str, Any]:
        runtime_key = _required_identifier(runtime_id, "runtimeId", 128)
        decision = str(data.get("decision") or "").strip().lower()
        if decision not in {"approve", "reject"}:
            self._fail(
                "invalid_openmaic_review_decision",
                "decision 必须是 approve 或 reject",
                400,
            )
        reviewer_id = _required_identifier(
            data.get("reviewerId"), "reviewerId", 128
        )
        notes = str(data.get("notes") or "").strip()
        if len(notes) > 1000:
            self._fail(
                "invalid_openmaic_review_notes", "审核备注不能超过 1000 字", 400
            )
        timestamp = now_ms()
        with self.repository.transaction() as conn:
            candidate = self.repository.get_runtime_classroom(
                conn,
                runtime_id=runtime_key,
                for_update=True,
            )
            if decision == "approve" and candidate is not None:
                manifest = self.repository.decode_json(
                    candidate.get("feature_manifest_json"), {}
                )
                if not self._sample_manifest_verified(manifest):
                    self._fail(
                        "openmaic_sample_contract_not_verified",
                        "样板课堂缺少经过核验的 Qwen3 正式语音或课程合同",
                        409,
                    )
            runtime = self.repository.review_runtime_classroom(
                conn,
                runtime_id=runtime_key,
                decision=decision,
                reviewer_id=reviewer_id,
                notes=notes,
                now=timestamp,
            )
            if runtime is not None and decision == "reject":
                self.repository.revoke_runtime_student_access(
                    conn,
                    runtime_classroom_id=runtime_key,
                    now=timestamp,
                )
        if runtime is None:
            self._fail(
                "openmaic_runtime_not_reviewable",
                "只有已生成完成的课堂可以审核",
                409,
            )
        return self._runtime_payload(runtime)

    def exchange_launch_ticket(self, ticket: str) -> dict[str, Any]:
        self._require_runtime()
        normalized_ticket = _required_identifier(ticket, "ticket", 128)
        timestamp = now_ms()
        runtime_token = new_token("omr")
        runtime_session_id = new_token("omrs")
        with self.repository.transaction() as conn:
            row = self.repository.get_launch_ticket_for_update(
                conn, token_hash=hash_value(normalized_ticket)
            )
            if row is None:
                self._fail("openmaic_launch_invalid", "课堂登录票据无效", 401)
            if row.get("revoked_at") is not None or row.get("consumed_at") is not None:
                self._fail("openmaic_launch_consumed", "课堂登录票据已经使用", 401)
            if int(row["expires_at"]) < timestamp:
                self._fail("openmaic_launch_expired", "课堂登录票据已经过期", 401)
            if str(row.get("runtime_status")) != "ready" or not row.get(
                "upstream_classroom_id"
            ):
                self._fail("openmaic_runtime_not_ready", "课堂暂时不可用", 409)
            manifest = self.repository.decode_json(
                row.get("feature_manifest_json"), {}
            )
            formal_candidate = bool(
                row.get("candidate_release_id")
                and row.get("candidate_build_item_id")
            )
            if formal_candidate:
                self._require_formal_quality_for_student_access(row)
                formal_manifest = self._formal_manifest_for_launch(manifest, row)
                if formal_manifest is None:
                    self._fail(
                        "openmaic_formal_contract_not_verified",
                        "正式课堂的发布、老师、语音或对话合同尚未验证",
                        409,
                    )
                manifest = formal_manifest
            else:
                if str(row.get("runtime_quality_status") or "") != "approved":
                    self._fail(
                        "openmaic_runtime_review_pending",
                        "完整互动课堂仍在内容与发音审核中",
                        409,
                    )
                if not self._sample_manifest_verified(manifest):
                    self._fail(
                        "openmaic_sample_contract_not_verified",
                        "样板课堂的课程、老师或正式语音合同尚未验证",
                        409,
                    )
            expires_at = timestamp + self.session_ttl_seconds * 1000
            from services.learning_paid_authority import teaching_budget_bindings
            paid_budgets = teaching_budget_bindings(getattr(self, "paid_budget_service", None), row, manifest, admit=True)
            try:
                self.repository.consume_launch_ticket(
                    conn,
                    ticket_id=str(row["id"]),
                    runtime_session_id=runtime_session_id,
                    runtime_token_hash=hash_value(runtime_token),
                    expires_at=expires_at,
                    now=timestamp,
                )
            except RuntimeError as exc:
                self._fail("openmaic_launch_consumed", "课堂登录票据已经使用", 401)
        return {
            "ok": True,
            "runtimeToken": runtime_token,
            "expiresAt": expires_at,
            "classroomId": str(row["upstream_classroom_id"]),
            "learningSessionId": str(row["learning_session_id"]),
            "features": manifest,
            **({"paidBudgets": paid_budgets} if paid_budgets is not None else {}),
        }

    def validate_runtime_session(self, runtime_token: str) -> dict[str, Any]:
        self._require_runtime()
        token = _required_identifier(runtime_token, "runtimeToken", 128)
        timestamp = now_ms()
        with self.repository.transaction() as conn:
            row = self.repository.get_runtime_session_for_update(
                conn, token_hash=hash_value(token)
            )
            if row is None or row.get("revoked_at") is not None:
                self._fail("openmaic_runtime_session_invalid", "课堂登录已失效", 401)
            if int(row["expires_at"]) < timestamp:
                self._fail("openmaic_runtime_session_expired", "课堂登录已过期", 401)
            if str(row.get("runtime_status")) != "ready" or not row.get(
                "upstream_classroom_id"
            ):
                self._fail("openmaic_runtime_not_ready", "课堂暂时不可用", 409)
            manifest = self.repository.decode_json(
                row.get("feature_manifest_json"), {}
            )
            formal_candidate = bool(
                row.get("candidate_release_id")
                and row.get("candidate_build_item_id")
            )
            if formal_candidate:
                self._require_formal_quality_for_student_access(row)
                formal_manifest = self._formal_manifest_for_launch(manifest, row)
                if formal_manifest is None:
                    self._fail(
                        "openmaic_formal_contract_not_verified",
                        "正式课堂的发布、老师、语音或对话合同尚未验证",
                        409,
                    )
                manifest = formal_manifest
            else:
                if str(row.get("runtime_quality_status") or "") != "approved":
                    self._fail(
                        "openmaic_runtime_review_pending",
                        "完整互动课堂仍在内容与发音审核中",
                        409,
                    )
                if not self._sample_manifest_verified(manifest):
                    self._fail(
                        "openmaic_sample_contract_not_verified",
                        "样板课堂的课程、老师或正式语音合同尚未验证",
                        409,
                    )
            self.repository.touch_runtime_session(
                conn, runtime_session_id=str(row["id"]), now=timestamp
            )
            from services.learning_paid_authority import teaching_budget_bindings
            paid_budgets = teaching_budget_bindings(getattr(self, "paid_budget_service", None), row, manifest, admit=False)
        return {
            "ok": True,
            "runtimeSessionId": str(row["id"]),
            "classroomId": str(row["upstream_classroom_id"]),
            "learningSessionId": str(row["learning_session_id"]),
            "expiresAt": int(row["expires_at"]),
            "features": manifest,
            **({"paidBudgets": paid_budgets} if paid_budgets is not None else {}),
        }

    def _handle_deterministic_recovery_result(
        self,
        recovery: Mapping[str, Any],
        upstream: OpenMaicDeterministicRecovery,
        *,
        idempotent: bool,
    ) -> dict[str, Any]:
        recovery_id = str(recovery["id"])
        runtime_id = str(recovery["runtime_classroom_id"])
        receipt = upstream.audit_receipt()
        if upstream.status in {"queued", "running"}:
            timestamp = now_ms()
            progressed = self._deterministic_recovery_progressed(
                recovery, receipt
            )
            with self.repository.transaction() as conn:
                updated = self.repository.update_deterministic_recovery_observation(
                    conn,
                    recovery_id=recovery_id,
                    receipt=receipt,
                    tts_attempted_count=int(
                        upstream.calls["tts"]["attempted"]
                    ),
                    tts_completed_count=int(upstream.calls["tts"]["completed"]),
                    progressed=progressed,
                    now=timestamp,
                )
                current = self.repository.get_deterministic_recovery_by_runtime(
                    conn, runtime_id=runtime_id
                )
            assert current is not None
            if (
                updated
                and not progressed
                and self._deterministic_recovery_is_stale(
                    current, timestamp=timestamp
                )
            ):
                self._terminally_fail_stale_recovery(
                    current,
                    error_code="openmaic_recovery_upstream_stale",
                    error_message_safe=(
                        "确定性恢复的上游记录长期没有可验证进展，已终结且不会重发"
                    ),
                    receipt=receipt,
                )
                with self.repository.transaction() as conn:
                    current = (
                        self.repository.get_deterministic_recovery_by_runtime(
                            conn, runtime_id=runtime_id
                        )
                    )
                assert current is not None
            return self._recovery_payload(current, idempotent=idempotent)
        if upstream.status == "failed":
            self._terminally_fail_recovery(
                recovery_id=recovery_id,
                runtime_id=runtime_id,
                error_code="openmaic_deterministic_recovery_failed",
                error_message_safe="OpenMAIC 确定性恢复未能完成课件物化",
                receipt=receipt,
            )
            with self.repository.transaction() as conn:
                current = self.repository.get_deterministic_recovery_by_runtime(
                    conn, runtime_id=runtime_id
                )
            assert current is not None
            return self._recovery_payload(current, idempotent=idempotent)

        artifact = upstream.artifact
        if artifact is None:
            self._fail(
                "openmaic_recovery_artifact_missing",
                "确定性恢复完成但没有课堂成品",
                502,
            )
        with self.repository.transaction() as conn:
            claimed = self.repository.claim_deterministic_recovery_validation(
                conn,
                recovery_id=recovery_id,
                artifact=artifact,
                tts_attempted_count=int(
                    upstream.calls["tts"]["attempted"]
                ),
                tts_completed_count=int(upstream.calls["tts"]["completed"]),
                receipt=receipt,
                now=now_ms(),
            )
            current = self.repository.get_deterministic_recovery_by_runtime(
                conn, runtime_id=runtime_id
            )
            runtime = self.repository.get_runtime_classroom(
                conn, runtime_id=runtime_id
            )
        if not claimed:
            assert current is not None
            return self._recovery_payload(current, idempotent=True)
        if runtime is None:
            self._terminally_fail_recovery(
                recovery_id=recovery_id,
                runtime_id=runtime_id,
                error_code="openmaic_recovery_runtime_missing",
                error_message_safe="确定性恢复关联的第三次生成记录不存在",
                receipt=receipt,
            )
            self._fail(
                "openmaic_recovery_runtime_missing",
                "确定性恢复关联的第三次生成记录不存在",
                409,
            )

        try:
            assert self.client is not None
            classroom_id = str(artifact["classroomId"])
            classroom = self.client.get_classroom(classroom_id)
            _validate_recovery_classroom_artifact_identity(
                classroom,
                expected_classroom_id=classroom_id,
                fail=self._fail,
            )
            if (
                _openmaic_classroom_content_sha256(classroom)
                != str(artifact["contentSha256"])
            ):
                self._fail(
                    "openmaic_recovery_content_hash_mismatch",
                    "确定性恢复回执与实际课堂内容摘要不一致",
                    502,
                )
            requested_manifest = self.repository.decode_json(
                runtime.get("feature_manifest_json"), {}
            )
            manifest = self._validate_and_manifest(
                classroom,
                requested=requested_manifest.get(
                    "enabled", requested_manifest.get("requested", [])
                ),
                required=requested_manifest.get("required", []),
                generation_contract=requested_manifest.get(
                    "generationContract"
                ),
            )
            if manifest["missing"]:
                self._fail(
                    "openmaic_required_features_missing",
                    "确定性恢复成品缺少本次要求的可验证课堂能力",
                    502,
                )
            sample_contract = manifest.get("generationContract")
            if not isinstance(sample_contract, Mapping):
                self._fail(
                    "openmaic_recovery_generation_contract_missing",
                    "确定性恢复成品没有固定 v2 样板课堂合同",
                    502,
                )
            if (
                self.conversation_probe_service is None
                or self.conversation_probe_client is None
            ):
                self._fail(
                    "openmaic_sample_conversation_probe_unavailable",
                    "学生对话网关验证器尚未配置",
                    503,
                )
            probe = self.conversation_probe_service.issue_recovery_candidate(
                runtime_id,
                classroom_id,
                recovery_id,
            )
            receipts = self.conversation_probe_client.verify(probe)
            self.conversation_probe_service.finalize_probe(
                str(probe["probeId"]),
                chat_receipt=receipts["chat"],
                transcription_receipt=receipts["transcription"],
            )
            manifest["conversation"] = self._sample_conversation_manifest(
                sample_contract, receipts=receipts
            )
            verified_at = now_ms()
            final_receipt = {
                **receipt,
                "validation": {
                    "staticContractVerified": True,
                    "conversationProbeVerified": True,
                    "verifiedAt": verified_at,
                },
            }
            with self.repository.transaction() as conn:
                self.repository.mark_ready_from_deterministic_recovery(
                    conn,
                    recovery_id=recovery_id,
                    runtime_id=runtime_id,
                    source_upstream_job_id=str(
                        recovery["source_upstream_job_id"]
                    ),
                    upstream_classroom_id=classroom_id,
                    feature_manifest=manifest,
                    receipt=final_receipt,
                    now=verified_at,
                )
                current = self.repository.get_deterministic_recovery_by_runtime(
                    conn, runtime_id=runtime_id
                )
        except (
            OpenMaicRuntimeServiceError,
            OpenMaicFullRuntimeError,
            OpenMaicConversationProbeError,
            OpenMaicConversationProbeClientError,
            RuntimeError,
        ) as exc:
            code = getattr(exc, "code", "openmaic_recovery_validation_failed")
            message = getattr(
                exc,
                "safe_message",
                "确定性恢复成品未通过完整课件与对话验证",
            )
            self._terminally_fail_recovery(
                recovery_id=recovery_id,
                runtime_id=runtime_id,
                error_code=code,
                error_message_safe=message,
                receipt=receipt,
            )
            raise OpenMaicRuntimeServiceError(
                code, message, status_code=getattr(exc, "status_code", 502)
            ) from exc
        except Exception as exc:
            code = "openmaic_recovery_validation_failed"
            message = "确定性恢复成品未通过完整课件与对话验证"
            self._terminally_fail_recovery(
                recovery_id=recovery_id,
                runtime_id=runtime_id,
                error_code=code,
                error_message_safe=message,
                receipt=receipt,
            )
            raise OpenMaicRuntimeServiceError(
                code, message, status_code=502
            ) from exc
        assert current is not None
        return self._recovery_payload(current, idempotent=idempotent)

    def _tts_credential_request(
        self, runtime_id: str, data: Mapping[str, Any]
    ) -> tuple[str, str, str, str]:
        runtime_key = _required_identifier(runtime_id, "runtimeId", 128)
        if (
            not isinstance(data, Mapping)
            or set(data)
            != SAMPLE_TTS_CREDENTIAL_RECOVERY_ALLOWED_REQUEST_FIELDS
        ):
            self._fail(
                "openmaic_tts_credential_contract_invalid",
                "TTS 凭证恢复请求字段不符合固定合同",
                400,
            )
        source_id = _required_identifier(
            data.get("expectedSourceJobId"), "expectedSourceJobId", 128
        )
        parent_id = _required_identifier(
            data.get("expectedParentRecoveryId"),
            "expectedParentRecoveryId",
            128,
        )
        request_id = _required_identifier(
            data.get("recoveryRequestId"), "recoveryRequestId", 128
        )
        if len(request_id) < 8:
            self._fail(
                "invalid_recoveryRequestId", "recoveryRequestId 无效", 400
            )
        if str(data.get("mode") or "").strip() != (
            TTS_CREDENTIAL_RECOVERY_REQUEST_MODE
        ):
            self._fail(
                "openmaic_tts_credential_mode_invalid",
                f"mode 必须是 {TTS_CREDENTIAL_RECOVERY_REQUEST_MODE}",
                400,
            )
        return runtime_key, source_id, parent_id, request_id

    def _tts_credential_source_context(
        self,
        conn: Any,
        *,
        runtime_id: str,
        expected_source_job_id: str,
        expected_parent_upstream_id: str,
        for_update: bool = False,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any], dict[str, Any]]:
        runtime, contract = self._deterministic_recovery_source_context(
            conn,
            runtime_id=runtime_id,
            expected_source_job_id=expected_source_job_id,
            for_update=for_update,
        )
        parent = self.repository.get_deterministic_recovery_by_runtime(
            conn, runtime_id=runtime_id, for_update=for_update
        )
        nullable_artifact_fields = (
            "tts_verified_asset_count",
            "upstream_classroom_id",
            "scene_count",
            "content_sha256",
            "final_artifact_sha256",
            "artifact_created_at",
            "verified_at",
        )
        if (
            parent is None
            or str(parent.get("status") or "") != "failed"
            or int(parent.get("dispatch_count") or 0) != 2
            or str(parent.get("mode") or "") != RECOVERY_MODE
            or str(parent.get("kind") or "") != RECOVERY_KIND
            or str(parent.get("error_code") or "")
            != "openmaic_deterministic_recovery_failed"
            or not str(parent.get("error_message_safe") or "").strip()
            or not isinstance(parent.get("terminal_at"), int)
            or int(parent.get("terminal_at") or 0) <= 0
            or str(parent.get("source_upstream_job_id") or "")
            != expected_source_job_id
            or str(parent.get("source_job_status") or "") != "failed"
            or str(parent.get("source_job_error") or "")
            != "structured_output_exhausted"
            or int(parent.get("source_scenes_generated") or -1) != 4
            or int(parent.get("source_total_scenes") or -1) != 10
            or str(parent.get("expected_upstream_recovery_id") or "")
            != expected_parent_upstream_id
            or str(parent.get("upstream_recovery_id") or "")
            != expected_parent_upstream_id
            or not str(parent.get("policy_id") or "").strip()
            or not str(parent.get("policy_version") or "").strip()
            or not str(parent.get("canonical_spec_sha256") or "").strip()
            or not str(parent.get("code_patch_sha256") or "").strip()
            or int(parent.get("llm_call_count") or 0) != 0
            or int(parent.get("web_search_call_count") or 0) != 0
            or int(parent.get("image_generation_call_count") or 0) != 0
            or int(parent.get("video_generation_call_count") or 0) != 0
            or int(parent.get("tts_expected_call_count") or 0) != 10
            or int(parent.get("tts_attempted_call_count") or 0) != 1
            or int(parent.get("tts_completed_call_count") or 0) != 0
            or str(parent.get("tts_provider_id") or "") != "qwen-tts"
            or str(parent.get("tts_model_id") or "") != "qwen3-tts-flash"
            or str(parent.get("tts_voice_id") or "") != "Serena"
            or bool(parent.get("tts_fallback_used"))
            or any(parent.get(field) is not None for field in nullable_artifact_fields)
            or bool(parent.get("static_contract_verified"))
            or bool(parent.get("conversation_probe_verified"))
            or not isinstance(
                self.repository.decode_json(parent.get("receipt_json"), {}),
                Mapping,
            )
        ):
            self._fail(
                "openmaic_tts_credential_parent_not_allowed",
                "只有固定终态且 TTS 为 10/1/0 的第二次恢复可创建唯一子记录",
                409,
            )
        return runtime, parent, contract

    def _tts_credential_parent_hashes(
        self, parent: Mapping[str, Any]
    ) -> dict[str, str]:
        receipt = self.repository.decode_json(parent.get("receipt_json"), {})
        if not isinstance(receipt, Mapping) or not receipt:
            self._fail(
                "openmaic_tts_credential_parent_receipt_invalid",
                "终态父恢复缺少可验证回执",
                409,
            )
        receipt_sha256 = _canonical_sha256(receipt)
        fields = (
            "id",
            "recovery_request_id",
            "runtime_classroom_id",
            "mode",
            "kind",
            "status",
            "dispatch_count",
            "first_dispatch_error_code",
            "first_dispatch_error_message_safe",
            "first_dispatch_rejected_at",
            "source_runtime_status",
            "source_runtime_error_code",
            "source_runtime_error_message_safe",
            "source_upstream_job_id",
            "source_job_status",
            "source_job_error",
            "source_scenes_generated",
            "source_total_scenes",
            "source_completed_at",
            "source_job_snapshot_sha256",
            "source_generation_contract_sha256",
            "expected_upstream_recovery_id",
            "upstream_recovery_id",
            "policy_id",
            "policy_version",
            "canonical_spec_sha256",
            "code_patch_sha256",
            "llm_call_count",
            "web_search_call_count",
            "image_generation_call_count",
            "video_generation_call_count",
            "tts_expected_call_count",
            "tts_attempted_call_count",
            "tts_completed_call_count",
            "tts_provider_id",
            "tts_model_id",
            "tts_voice_id",
            "tts_fallback_used",
            "tts_verified_asset_count",
            "upstream_classroom_id",
            "scene_count",
            "content_sha256",
            "final_artifact_sha256",
            "artifact_created_at",
            "static_contract_verified",
            "conversation_probe_verified",
            "verified_at",
            "error_code",
            "error_message_safe",
            "created_at",
            "updated_at",
            "terminal_at",
        )
        snapshot = {field: parent.get(field) for field in fields}
        snapshot["receiptSha256"] = receipt_sha256
        return {
            "db": _canonical_sha256(snapshot),
            "receipt": receipt_sha256,
            "runtime": tts_credential_parent_snapshot_sha256(
                str(parent["upstream_recovery_id"])
            ),
        }

    def _validate_tts_credential_parent_upstream(
        self,
        upstream: OpenMaicDeterministicRecovery,
        *,
        parent: Mapping[str, Any],
        parent_hashes: Mapping[str, str],
    ) -> None:
        receipt = upstream.audit_receipt()
        if (
            upstream.status != "failed"
            or upstream.recovery_id
            != str(parent.get("upstream_recovery_id") or "")
            or upstream.artifact is not None
            or upstream.error is None
            or upstream.error.get("code") != "deterministic_recovery_failed"
            or dict(upstream.calls.get("tts") or {})
            != {"expected": 10, "attempted": 1, "completed": 0}
            or _canonical_sha256(receipt) != parent_hashes["receipt"]
            or tts_credential_parent_snapshot_sha256(upstream.recovery_id)
            != parent_hashes["runtime"]
        ):
            self._fail(
                "openmaic_tts_credential_parent_changed",
                "OpenMAIC 终态父恢复与冻结语义不一致",
                409,
            )

    def _validate_existing_tts_credential_recovery(
        self,
        child: Mapping[str, Any],
        *,
        runtime_id: str,
        expected_source_job_id: str,
        expected_parent_upstream_id: str,
        recovery_request_id: str,
    ) -> None:
        expected_child_id, _request_hash = tts_credential_recovery_identity(
            expected_source_job_id,
            expected_parent_upstream_id,
            recovery_request_id,
        )
        if not (
            str(child.get("runtime_classroom_id") or "") == runtime_id
            and str(child.get("recovery_request_id") or "")
            == recovery_request_id
            and str(child.get("source_upstream_job_id") or "")
            == expected_source_job_id
            and str(child.get("parent_upstream_recovery_id") or "")
            == expected_parent_upstream_id
            and str(child.get("mode") or "") == TTS_CREDENTIAL_RECOVERY_MODE
            and str(child.get("kind") or "") == TTS_CREDENTIAL_RECOVERY_KIND
            and str(child.get("expected_upstream_child_id") or "")
            == expected_child_id
            and str(child.get("upstream_child_id") or "")
            in {"", expected_child_id}
            and str(child.get("expected_upstream_classroom_id") or "")
            == tts_credential_classroom_identity(expected_child_id)
        ):
            self._fail(
                "openmaic_tts_credential_request_conflict",
                "recoveryRequestId 已用于不同的 TTS 凭证恢复合同",
                409,
            )

    def _attach_tts_credential_recovery(
        self,
        child: Mapping[str, Any],
        upstream: OpenMaicTtsCredentialRecovery,
    ) -> Mapping[str, Any]:
        try:
            with self.repository.transaction() as conn:
                attached = (
                    self.repository.attach_tts_credential_recovery_receipt(
                        conn,
                        recovery_id=str(child["id"]),
                        upstream_child_id=upstream.recovery_id,
                        parent_runtime_snapshot_sha256=str(
                            upstream.parent["parentSnapshotSha256"]
                        ),
                        policy=upstream.policy,
                        calls=upstream.calls,
                        receipt=upstream.audit_receipt(),
                        now=now_ms(),
                    )
                )
                current = (
                    self.repository.get_tts_credential_recovery_by_runtime(
                        conn, runtime_id=str(child["runtime_classroom_id"])
                    )
                )
            if current is None or (
                not attached
                and str(current.get("upstream_child_id") or "")
                != str(current.get("expected_upstream_child_id") or "")
            ):
                raise RuntimeError("TTS credential child attach conflict")
            return current
        except Exception as exc:
            raise OpenMaicRuntimeServiceError(
                "openmaic_tts_credential_persistence_uncertain",
                "已找到 TTS 凭证恢复，但本地回执尚未安全关联且不会重发",
                status_code=503,
            ) from exc

    def _handle_tts_credential_recovery_result(
        self,
        child: Mapping[str, Any],
        upstream: OpenMaicTtsCredentialRecovery,
        *,
        idempotent: bool,
    ) -> dict[str, Any]:
        receipt = upstream.audit_receipt()
        if upstream.status in {"queued", "running"}:
            previous = self.repository.decode_json(child.get("receipt_json"), {})
            progressed = not isinstance(previous, Mapping) or (
                _canonical_sha256(previous) != _canonical_sha256(receipt)
            )
            with self.repository.transaction() as conn:
                self.repository.update_tts_credential_recovery_observation(
                    conn,
                    recovery_id=str(child["id"]),
                    receipt=receipt,
                    tts_attempted_count=int(
                        upstream.calls["tts"]["attempted"]
                    ),
                    tts_completed_count=int(
                        upstream.calls["tts"]["completed"]
                    ),
                    progressed=progressed,
                    now=now_ms(),
                )
                current = (
                    self.repository.get_tts_credential_recovery_by_runtime(
                        conn, runtime_id=str(child["runtime_classroom_id"])
                    )
                )
            assert current is not None
            incoming_attempted = int(upstream.calls["tts"]["attempted"])
            incoming_completed = int(upstream.calls["tts"]["completed"])
            if str(current.get("status") or "") == "recovering" and (
                int(current.get("tts_attempted_call_count") or 0)
                > incoming_attempted
                or int(current.get("tts_completed_call_count") or 0)
                > incoming_completed
            ):
                self._terminally_fail_tts_credential_recovery(
                    current,
                    error_code=(
                        "openmaic_tts_credential_counter_regression"
                    ),
                    error_message_safe=(
                        "TTS 凭证恢复回执计数低于已持久化进度"
                    ),
                )
                with self.repository.transaction() as conn:
                    current = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn,
                            runtime_id=str(child["runtime_classroom_id"]),
                        )
                    )
                assert current is not None
            elif (
                str(current.get("status") or "") == "recovering"
                and self._tts_credential_recovery_is_stale(current)
            ):
                self._terminally_fail_stale_tts_credential_recovery(
                    current,
                    error_code="openmaic_tts_credential_upstream_stale",
                    error_message_safe=(
                        "TTS 凭证恢复上游十五分钟没有进展，已终结且不会重发"
                    ),
                )
                with self.repository.transaction() as conn:
                    current = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn,
                            runtime_id=str(child["runtime_classroom_id"]),
                        )
                    )
                assert current is not None
            return self._tts_credential_payload(
                current, idempotent=idempotent
            )
        if upstream.status == "failed":
            with self.repository.transaction() as conn:
                current = (
                    self.repository.get_tts_credential_recovery_by_runtime(
                        conn, runtime_id=str(child["runtime_classroom_id"])
                    )
                )
            assert current is not None
            if str(current.get("status") or "") != "recovering":
                return self._tts_credential_payload(
                    current, idempotent=True
                )
            self._terminally_fail_tts_credential_recovery(
                current,
                error_code="openmaic_tts_credential_recovery_failed",
                error_message_safe="OpenMAIC TTS 凭证恢复未能完成",
                receipt=receipt,
                tts_attempted_count=int(upstream.calls["tts"]["attempted"]),
                tts_completed_count=int(upstream.calls["tts"]["completed"]),
            )
            with self.repository.transaction() as conn:
                current = (
                    self.repository.get_tts_credential_recovery_by_runtime(
                        conn, runtime_id=str(child["runtime_classroom_id"])
                    )
                )
            assert current is not None
            return self._tts_credential_payload(current, idempotent=idempotent)
        artifact = upstream.artifact
        claimed_by_this_request = False
        try:
            if artifact is None:
                self._fail(
                    "openmaic_tts_credential_artifact_missing",
                    "TTS 凭证恢复完成但没有课堂成品",
                    502,
                )
            with self.repository.transaction() as conn:
                claimed = (
                    self.repository.claim_tts_credential_recovery_validation(
                        conn,
                        recovery_id=str(child["id"]),
                        receipt=receipt,
                        now=now_ms(),
                    )
                )
                claimed_by_this_request = bool(claimed)
                current = (
                    self.repository.get_tts_credential_recovery_by_runtime(
                        conn, runtime_id=str(child["runtime_classroom_id"])
                    )
                )
            if not claimed:
                assert current is not None
                return self._tts_credential_payload(current, idempotent=True)
            assert current is not None
            self._validate_tts_credential_static(current, artifact)
            with self.repository.transaction() as conn:
                static_completed = (
                    self.repository.complete_tts_credential_static_validation(
                        conn,
                        recovery_id=str(child["id"]),
                        artifact=artifact,
                        receipt=receipt,
                        now=now_ms(),
                    )
                )
                current = (
                    self.repository.get_tts_credential_recovery_by_runtime(
                        conn, runtime_id=str(child["runtime_classroom_id"])
                    )
                )
            if not static_completed:
                assert current is not None
                return self._tts_credential_payload(
                    current, idempotent=True
                )
        except Exception as exc:
            code = getattr(
                exc, "code", "openmaic_tts_credential_validation_failed"
            )
            message = getattr(
                exc,
                "safe_message",
                "TTS 凭证恢复成品未通过完整课件与对话验证",
            )
            with self.repository.transaction() as conn:
                current = (
                    self.repository.get_tts_credential_recovery_by_runtime(
                        conn, runtime_id=str(child["runtime_classroom_id"])
                    )
                )
            if current is None:
                raise OpenMaicRuntimeServiceError(
                    code, message, status_code=getattr(exc, "status_code", 502)
                ) from exc
            expected_failure_status = (
                "validating" if claimed_by_this_request else "recovering"
            )
            if str(current.get("status") or "") != expected_failure_status:
                return self._tts_credential_payload(
                    current, idempotent=True
                )
            failed = self._terminally_fail_tts_credential_recovery(
                current,
                error_code=code,
                error_message_safe=message,
                receipt=receipt,
            )
            if not failed:
                with self.repository.transaction() as conn:
                    current = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn,
                            runtime_id=str(child["runtime_classroom_id"]),
                        )
                    )
                assert current is not None
                return self._tts_credential_payload(
                    current, idempotent=True
                )
            raise OpenMaicRuntimeServiceError(
                code, message, status_code=getattr(exc, "status_code", 502)
            ) from exc
        assert current is not None
        return self._complete_tts_credential_probe(
            current, receipt=receipt
        )

    def _validate_tts_credential_static(
        self, child: Mapping[str, Any], artifact: Mapping[str, Any]
    ) -> dict[str, Any]:
        assert self.client is not None
        classroom_id = str(artifact["classroomId"])
        if classroom_id != str(child["expected_upstream_classroom_id"]):
            self._fail(
                "openmaic_tts_credential_classroom_identity_mismatch",
                "TTS 凭证恢复课堂编号不符合固定 child 合同",
                502,
            )
        classroom = self.client.get_classroom(classroom_id)
        _validate_recovery_classroom_artifact_identity(
            classroom,
            expected_classroom_id=classroom_id,
            fail=self._fail,
        )
        if _openmaic_classroom_content_sha256(classroom) != str(
            artifact["contentSha256"]
        ):
            self._fail(
                "openmaic_tts_credential_content_hash_mismatch",
                "TTS 凭证恢复回执与实际课堂内容摘要不一致",
                502,
            )
        with self.repository.transaction() as conn:
            runtime = self.repository.get_runtime_classroom(
                conn, runtime_id=str(child["runtime_classroom_id"])
            )
        if runtime is None:
            self._fail(
                "openmaic_tts_credential_runtime_missing",
                "TTS 凭证恢复关联的第三次生成记录不存在",
                409,
            )
        requested_manifest = self.repository.decode_json(
            runtime.get("feature_manifest_json"), {}
        )
        manifest = self._validate_and_manifest(
            classroom,
            requested=requested_manifest.get(
                "enabled", requested_manifest.get("requested", [])
            ),
            required=requested_manifest.get("required", []),
            generation_contract=requested_manifest.get("generationContract"),
        )
        speech_audio = manifest.get("speechAudio")
        if (
            manifest["missing"]
            or not isinstance(manifest.get("generationContract"), Mapping)
            or manifest.get("sceneCount") != 10
            or int(artifact.get("sceneCount") or 0) != 10
            or int(artifact.get("audioCount") or 0) != 10
            or not isinstance(speech_audio, Mapping)
            or speech_audio.get("speechActionCount") != 10
            or speech_audio.get("verifiedAssetCount") != 10
        ):
            self._fail(
                "openmaic_tts_credential_static_contract_failed",
                "TTS 凭证恢复成品缺少完整七能力或恰好十段独立音频",
                502,
            )
        return manifest

    def _complete_tts_credential_probe(
        self,
        child: Mapping[str, Any],
        *,
        receipt: Mapping[str, Any],
    ) -> dict[str, Any]:
        if (
            self.conversation_probe_service is None
            or self.conversation_probe_client is None
        ):
            self._fail(
                "openmaic_sample_conversation_probe_unavailable",
                "学生对话网关验证器尚未配置",
                503,
            )
        try:
            probe = (
                self.conversation_probe_service.issue_tts_credential_recovery_candidate(
                    str(child["runtime_classroom_id"]),
                    str(child["upstream_classroom_id"]),
                    str(child["parent_recovery_id"]),
                    str(child["id"]),
                )
            )
            receipts = self.conversation_probe_client.verify(probe)
            self.conversation_probe_service.finalize_probe(
                str(probe["probeId"]),
                chat_receipt=receipts["chat"],
                transcription_receipt=receipts["transcription"],
            )
        except Exception as exc:
            code = getattr(
                exc, "code", "openmaic_tts_credential_probe_failed"
            )
            message = getattr(
                exc,
                "safe_message",
                "TTS 凭证恢复成品未通过学生对话网关验证",
            )
            failed = self._terminally_fail_tts_credential_recovery(
                child,
                error_code=code,
                error_message_safe=message,
                receipt=receipt,
            )
            if not failed:
                with self.repository.transaction() as conn:
                    current = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn,
                            runtime_id=str(child["runtime_classroom_id"]),
                        )
                    )
                assert current is not None
                return self._tts_credential_payload(
                    current, idempotent=True
                )
            raise OpenMaicRuntimeServiceError(
                code, message, status_code=getattr(exc, "status_code", 502)
            ) from exc
        return self._publish_tts_credential_recovery(
            child,
            receipt=receipt,
            probe_id=str(probe["probeId"]),
            receipts=receipts,
        )

    def _publish_tts_credential_recovery(
        self,
        child: Mapping[str, Any],
        *,
        receipt: Mapping[str, Any],
        probe_id: str,
        receipts: Mapping[str, Any],
    ) -> dict[str, Any]:
        with self.repository.transaction() as conn:
            claimed = (
                self.repository.claim_tts_credential_recovery_publication(
                    conn,
                    recovery_id=str(child["id"]),
                    runtime_id=str(child["runtime_classroom_id"]),
                    conversation_probe_id=probe_id,
                    now=now_ms(),
                )
            )
            current = self.repository.get_tts_credential_recovery_by_runtime(
                conn,
                runtime_id=str(child["runtime_classroom_id"]),
            )
        if not claimed:
            assert current is not None
            return self._tts_credential_payload(current, idempotent=True)
        assert current is not None
        try:
            artifact = {
                "classroomId": str(current["upstream_classroom_id"]),
                "sceneCount": int(current["scene_count"]),
                "audioCount": int(current["audio_count"]),
                "contentSha256": str(current["content_sha256"]),
                "artifactSha256": str(current["final_artifact_sha256"]),
            }
            manifest = self._validate_tts_credential_static(
                current, artifact
            )
            return self._mark_ready_from_tts_credential_probe(
                current,
                manifest=manifest,
                receipt=receipt,
                probe_id=probe_id,
                receipts=receipts,
            )
        except Exception as exc:
            code = getattr(
                exc, "code", "openmaic_tts_credential_publication_failed"
            )
            message = getattr(
                exc,
                "safe_message",
                "TTS 凭证恢复成品发布验证失败，且不会重新调用 TTS",
            )
            failed = self._terminally_fail_tts_credential_recovery(
                current,
                error_code=code,
                error_message_safe=message,
                receipt=receipt,
            )
            if not failed:
                with self.repository.transaction() as conn:
                    latest = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn,
                            runtime_id=str(child["runtime_classroom_id"]),
                        )
                    )
                assert latest is not None
                return self._tts_credential_payload(
                    latest, idempotent=True
                )
            raise OpenMaicRuntimeServiceError(
                code, message, status_code=getattr(exc, "status_code", 502)
            ) from exc

    def _mark_ready_from_tts_credential_probe(
        self,
        child: Mapping[str, Any],
        *,
        manifest: dict[str, Any],
        receipt: Mapping[str, Any],
        probe_id: str,
        receipts: Mapping[str, Any],
    ) -> dict[str, Any]:
        sample_contract = manifest.get("generationContract")
        assert isinstance(sample_contract, Mapping)
        manifest["conversation"] = self._sample_conversation_manifest(
            sample_contract, receipts=receipts
        )
        verified_at = now_ms()
        final_receipt = {
            **dict(receipt),
            "validation": {
                "staticContractVerified": True,
                "conversationProbeVerified": True,
                "probeId": probe_id,
                "verifiedAt": verified_at,
            },
        }
        with self.repository.transaction() as conn:
            parent = self.repository.get_deterministic_recovery_by_runtime(
                conn,
                runtime_id=str(child["runtime_classroom_id"]),
                for_update=True,
            )
            current = self.repository.get_tts_credential_recovery_by_runtime(
                conn,
                runtime_id=str(child["runtime_classroom_id"]),
                for_update=True,
            )
            if parent is None or current is None:
                raise RuntimeError("TTS credential finalization rows missing")
            parent_hashes = self._tts_credential_parent_hashes(parent)
            if (
                str(parent.get("id") or "")
                != str(child["parent_recovery_id"])
                or str(parent.get("status") or "") != "failed"
                or parent_hashes
                != {
                    "db": str(child["parent_db_snapshot_sha256"]),
                    "receipt": str(child["parent_receipt_sha256"]),
                    "runtime": str(
                        child["parent_runtime_snapshot_sha256"]
                    ),
                }
                or str(current.get("id") or "") != str(child["id"])
                or str(current.get("parent_recovery_id") or "")
                != str(parent["id"])
            ):
                raise RuntimeError("TTS credential parent changed")
            self.repository.mark_ready_from_tts_credential_recovery(
                conn,
                recovery_id=str(child["id"]),
                runtime_id=str(child["runtime_classroom_id"]),
                parent_recovery_id=str(child["parent_recovery_id"]),
                parent_db_snapshot_sha256=str(
                    child["parent_db_snapshot_sha256"]
                ),
                parent_receipt_sha256=str(
                    child["parent_receipt_sha256"]
                ),
                parent_runtime_snapshot_sha256=str(
                    child["parent_runtime_snapshot_sha256"]
                ),
                source_upstream_job_id=str(child["source_upstream_job_id"]),
                upstream_child_id=str(child["upstream_child_id"]),
                upstream_classroom_id=str(child["upstream_classroom_id"]),
                conversation_probe_id=probe_id,
                feature_manifest=manifest,
                receipt=final_receipt,
                now=verified_at,
            )
            ready = self.repository.get_tts_credential_recovery_by_runtime(
                conn, runtime_id=str(child["runtime_classroom_id"])
            )
        assert ready is not None
        return self._tts_credential_payload(ready, idempotent=True)

    def _resume_tts_credential_validation(
        self, child: Mapping[str, Any]
    ) -> dict[str, Any]:
        receipt = self.repository.decode_json(child.get("receipt_json"), {})
        if not isinstance(receipt, Mapping):
            receipt = {}
        try:
            if not bool(child.get("static_contract_verified")):
                if not self._tts_credential_recovery_is_stale(child):
                    return self._tts_credential_payload(
                        child, idempotent=True
                    )
                self._terminally_fail_stale_tts_credential_recovery(
                    child,
                    error_code="openmaic_tts_credential_static_stale",
                    error_message_safe=(
                        "TTS 凭证恢复静态验证长期未完成，已终结且不会重跑"
                    ),
                )
                with self.repository.transaction() as conn:
                    terminal = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn,
                            runtime_id=str(
                                child["runtime_classroom_id"]
                            ),
                        )
                    )
                assert terminal is not None
                return self._tts_credential_payload(
                    terminal, idempotent=True
                )
            with self.repository.transaction() as conn:
                probe = (
                    self.repository.get_conversation_probe_by_runtime_classroom_for_update(
                        conn,
                        runtime_classroom_id=str(
                            child["runtime_classroom_id"]
                        ),
                    )
                )
            if probe is None:
                if not self._tts_credential_recovery_is_stale(child):
                    return self._tts_credential_payload(
                        child, idempotent=True
                    )
                self._terminally_fail_stale_tts_credential_recovery(
                    child,
                    error_code=(
                        "openmaic_tts_credential_probe_stale"
                    ),
                    error_message_safe=(
                        "TTS 凭证恢复对话验证长期未开始，已终结且不会重跑"
                    ),
                )
                with self.repository.transaction() as conn:
                    terminal = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn,
                            runtime_id=str(
                                child["runtime_classroom_id"]
                            ),
                        )
                    )
                assert terminal is not None
                return self._tts_credential_payload(
                    terminal, idempotent=True
                )
            if (
                str(probe.get("candidate_kind") or "")
                != "tts_credential_recovery"
                or str(probe.get("deterministic_recovery_id") or "")
                != str(child["parent_recovery_id"])
                or str(probe.get("tts_credential_recovery_id") or "")
                != str(child["id"])
                or str(probe.get("upstream_classroom_id") or "")
                != str(child["upstream_classroom_id"])
            ):
                raise RuntimeError("TTS credential probe binding mismatch")
            if probe.get("finalized_at") is None:
                if not self._tts_credential_recovery_is_stale(child):
                    return self._tts_credential_payload(
                        child, idempotent=True
                    )
                self._terminally_fail_stale_tts_credential_recovery(
                    child,
                    error_code="openmaic_tts_credential_probe_stale",
                    error_message_safe=(
                        "TTS 凭证恢复对话验证长期未完成，已终结且不会重跑"
                    ),
                )
                with self.repository.transaction() as conn:
                    terminal = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn,
                            runtime_id=str(
                                child["runtime_classroom_id"]
                            ),
                        )
                    )
                assert terminal is not None
                return self._tts_credential_payload(
                    terminal, idempotent=True
                )
            receipts = {
                "chat": self.repository.decode_json(
                    probe.get("chat_receipt_json"), {}
                ),
                "transcription": self.repository.decode_json(
                    probe.get("transcription_receipt_json"), {}
                ),
            }
            # A finalized probe makes publication claimable, but only the
            # validating -> publishing CAS winner may re-read media and
            # publish. Concurrent losers are observation-only.
            return self._publish_tts_credential_recovery(
                child,
                receipt=receipt,
                probe_id=str(probe["id"]),
                receipts=receipts,
            )
        except OpenMaicRuntimeServiceError:
            raise
        except Exception as exc:
            code = "openmaic_tts_credential_validation_interrupted"
            message = "TTS 凭证恢复验证中断，已终结且不会重新调用 TTS"
            failed = self._terminally_fail_tts_credential_recovery(
                child,
                error_code=code,
                error_message_safe=message,
                receipt=receipt,
            )
            if not failed:
                with self.repository.transaction() as conn:
                    current = (
                        self.repository.get_tts_credential_recovery_by_runtime(
                            conn,
                            runtime_id=str(child["runtime_classroom_id"]),
                        )
                    )
                assert current is not None
                return self._tts_credential_payload(
                    current, idempotent=True
                )
            raise OpenMaicRuntimeServiceError(
                code, message, status_code=getattr(exc, "status_code", 502)
            ) from exc

    def _terminally_fail_tts_credential_recovery(
        self,
        child: Mapping[str, Any],
        *,
        error_code: str,
        error_message_safe: str,
        receipt: Mapping[str, Any] | None = None,
        tts_attempted_count: int | None = None,
        tts_completed_count: int | None = None,
    ) -> bool:
        with self.repository.transaction() as conn:
            failed = self.repository.fail_tts_credential_recovery(
                conn,
                recovery_id=str(child["id"]),
                runtime_id=str(child["runtime_classroom_id"]),
                source_upstream_job_id=str(child["source_upstream_job_id"]),
                expected_status=str(child["status"]),
                error_code=error_code,
                error_message_safe=error_message_safe,
                receipt=receipt,
                tts_attempted_count=tts_attempted_count,
                tts_completed_count=tts_completed_count,
                now=now_ms(),
            )
            return bool(failed)

    def _terminally_fail_stale_tts_credential_recovery(
        self,
        child: Mapping[str, Any],
        *,
        error_code: str,
        error_message_safe: str,
    ) -> bool:
        timestamp = now_ms()
        with self.repository.transaction() as conn:
            return bool(
                self.repository.fail_stale_tts_credential_recovery(
                    conn,
                    recovery_id=str(child["id"]),
                    runtime_id=str(child["runtime_classroom_id"]),
                    source_upstream_job_id=str(
                        child["source_upstream_job_id"]
                    ),
                    expected_status=str(child["status"]),
                    expected_updated_at=int(child.get("updated_at") or 0),
                    expected_tts_attempted_count=int(
                        child.get("tts_attempted_call_count") or 0
                    ),
                    expected_tts_completed_count=int(
                        child.get("tts_completed_call_count") or 0
                    ),
                    stale_cutoff=(
                        timestamp
                        - SAMPLE_TTS_CREDENTIAL_RECOVERY_STALE_AFTER_MS
                    ),
                    error_code=error_code,
                    error_message_safe=error_message_safe,
                    now=timestamp,
                )
            )

    def _tts_credential_recovery_is_stale(
        self, child: Mapping[str, Any]
    ) -> bool:
        checked_at = now_ms()
        local_anchor = max(
            int(child.get("created_at") or 0),
            int(child.get("updated_at") or 0),
        )
        receipt = self.repository.decode_json(child.get("receipt_json"), {})
        upstream_anchor = 0
        if isinstance(receipt, Mapping):
            upstream_anchor = _iso8601_epoch_ms(receipt.get("updatedAt"))
            if upstream_anchor > checked_at + 5 * 60 * 1000:
                upstream_anchor = 0
        anchor = max(local_anchor, upstream_anchor)
        return anchor > 0 and (
            checked_at - anchor
            >= SAMPLE_TTS_CREDENTIAL_RECOVERY_STALE_AFTER_MS
        )

    @staticmethod
    def _tts_credential_payload(
        child: Mapping[str, Any], *, idempotent: bool
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "ttsCredentialRecovery": {
                "id": str(child["id"]),
                "recoveryRequestId": str(child["recovery_request_id"]),
                "runtimeId": str(child["runtime_classroom_id"]),
                "parentRecoveryId": str(child["parent_recovery_id"]),
                "parentUpstreamRecoveryId": str(
                    child["parent_upstream_recovery_id"]
                ),
                "mode": str(child["mode"]),
                "kind": str(child["kind"]),
                "status": str(child["status"]),
                "upstreamRecoveryId": (
                    str(child["upstream_child_id"])
                    if child.get("upstream_child_id")
                    else None
                ),
                "classroomId": (
                    str(child["upstream_classroom_id"])
                    if child.get("upstream_classroom_id")
                    else None
                ),
                "calls": {
                    "llm": int(child.get("llm_call_count") or 0),
                    "webSearch": int(
                        child.get("web_search_call_count") or 0
                    ),
                    "imageGeneration": int(
                        child.get("image_generation_call_count") or 0
                    ),
                    "videoGeneration": int(
                        child.get("video_generation_call_count") or 0
                    ),
                    "tts": {
                        "expected": int(
                            child.get("tts_expected_call_count") or 0
                        ),
                        "attempted": int(
                            child.get("tts_attempted_call_count") or 0
                        ),
                        "completed": int(
                            child.get("tts_completed_call_count") or 0
                        ),
                    },
                },
                "staticContractVerified": bool(
                    child.get("static_contract_verified")
                ),
                "conversationProbeVerified": bool(
                    child.get("conversation_probe_verified")
                ),
                "errorCode": (
                    str(child["error_code"])
                    if child.get("error_code")
                    else None
                ),
                "idempotent": bool(idempotent),
                "updatedAt": int(child["updated_at"]),
            },
        }

    def _deterministic_recovery_source_context(
        self,
        conn: Any,
        *,
        runtime_id: str,
        expected_source_job_id: str,
        for_update: bool = False,
    ) -> tuple[Mapping[str, Any], dict[str, Any]]:
        source = self.repository.get_runtime_classroom(
            conn, runtime_id=runtime_id, for_update=for_update
        )
        if source is None:
            self._fail(
                "openmaic_runtime_not_found",
                "没有找到要恢复的第三次样板课堂记录",
                404,
            )
        attempts = self.repository.get_package_runtime_attempts(
            conn,
            package_id=str(source["package_id"]),
            package_version=int(source["package_version"]),
            for_update=for_update,
        )
        predecessor_id = str(source.get("retry_of_runtime_id") or "")
        predecessor = next(
            (row for row in attempts if str(row.get("id") or "") == predecessor_id),
            None,
        )
        if (
            len(attempts) != 3
            or [int(row.get("attempt_ordinal") or 0) for row in attempts]
            != [1, 2, 3]
            or str(attempts[-1].get("id") or "") != runtime_id
            or int(source.get("attempt_ordinal") or 0) != 3
            or str(source.get("status") or "") != "failed"
            or str(source.get("error_code") or "")
            != "openmaic_generation_failed"
            or str(source.get("upstream_job_id") or "")
            != expected_source_job_id
            or source.get("upstream_classroom_id") is not None
            or source.get("retired_at") is not None
            or str(source.get("retry_reason") or "")
            != SAMPLE_RETRY_REASON_BY_ATTEMPT[3]
            or predecessor is None
            or int(predecessor.get("attempt_ordinal") or 0) != 2
            or str(source.get("expected_previous_job_id") or "")
            != str(predecessor.get("upstream_job_id") or "")
        ):
            self._fail(
                "openmaic_recovery_not_allowed",
                "只有固定 v2 合同下失败的第三次样板任务可以确定性恢复",
                409,
            )
        manifest = self.repository.decode_json(
            source.get("feature_manifest_json"), {}
        )
        enabled_features = (
            manifest.get("enabled") if isinstance(manifest, Mapping) else None
        )
        required_features = (
            manifest.get("required") if isinstance(manifest, Mapping) else None
        )
        if (
            not isinstance(manifest, Mapping)
            or manifest.get("schemaVersion") != self.MANIFEST_SCHEMA
            or not isinstance(enabled_features, list)
            or len(enabled_features) != len(SAMPLE_REQUIRED_FEATURES)
            or set(enabled_features) != set(SAMPLE_REQUIRED_FEATURES)
            or not isinstance(required_features, list)
            or len(required_features) != len(SAMPLE_REQUIRED_FEATURES)
            or set(required_features) != set(SAMPLE_REQUIRED_FEATURES)
        ):
            self._fail(
                "openmaic_recovery_generation_contract_mismatch",
                "第三次任务缺少完整七能力样板合同",
                409,
            )
        try:
            contract = self._validated_sample_contract(
                manifest.get("generationContract")
            )
        except OpenMaicRuntimeServiceError as exc:
            raise OpenMaicRuntimeServiceError(
                "openmaic_recovery_generation_contract_mismatch",
                "第三次任务与固定 v2 完整样板合同不一致",
                status_code=409,
            ) from exc
        expected_contract_fields = {
            "schemaVersion",
            "sampleMode",
            "authority",
            "course",
            "learnerConstraints",
            "teacher",
            "requiredClassroom",
            "speechAudioContract",
            "conversationContract",
            "generation",
        }
        if (
            contract is None
            or set(contract) != expected_contract_fields
            or str(contract["course"].get("id") or "")
            != str(source["course_id"])
            or str(contract["course"].get("version") or "")
            != str(source["course_version"])
            or str(contract["course"].get("packageId") or "")
            != str(source["package_id"])
            or int(contract["course"].get("packageVersion") or 0)
            != int(source["package_version"])
        ):
            self._fail(
                "openmaic_recovery_generation_contract_mismatch",
                "第三次任务与固定 v2 完整样板合同不一致",
                409,
            )
        return source, contract

    def _validate_existing_recovery(
        self,
        recovery: Mapping[str, Any],
        *,
        runtime_id: str,
        expected_source_job_id: str,
        recovery_request_id: str,
    ) -> None:
        expected_upstream_recovery_id, _request_id_sha256 = (
            deterministic_recovery_identity(
                expected_source_job_id, recovery_request_id
            )
        )
        actual_upstream_recovery_id = str(
            recovery.get("upstream_recovery_id") or ""
        )
        dispatch_count = int(recovery.get("dispatch_count") or 1)
        first_dispatch_fields_valid = (
            dispatch_count == 1
            and recovery.get("first_dispatch_error_code") is None
            and recovery.get("first_dispatch_error_message_safe") is None
            and recovery.get("first_dispatch_rejected_at") is None
        ) or (
            dispatch_count == 2
            and str(recovery.get("first_dispatch_error_code") or "")
            == "openmaic_recovery_upstream_rejected"
            and bool(str(recovery.get("first_dispatch_error_message_safe") or "").strip())
            and isinstance(recovery.get("first_dispatch_rejected_at"), int)
            and not isinstance(recovery.get("first_dispatch_rejected_at"), bool)
            and int(recovery["first_dispatch_rejected_at"]) > 0
        )
        if not (
            str(recovery.get("recovery_request_id") or "")
            == recovery_request_id
            and str(recovery.get("runtime_classroom_id") or "") == runtime_id
            and str(recovery.get("source_upstream_job_id") or "")
            == expected_source_job_id
            and str(recovery.get("mode") or "") == RECOVERY_MODE
            and str(recovery.get("kind") or "") == RECOVERY_KIND
            and str(recovery.get("expected_upstream_recovery_id") or "")
            == expected_upstream_recovery_id
            and actual_upstream_recovery_id
            in {"", expected_upstream_recovery_id}
            and first_dispatch_fields_valid
        ):
            self._fail(
                "openmaic_recovery_request_conflict",
                "recoveryRequestId 已用于另一条记录或不同的恢复合同",
                409,
            )

    def _validate_deterministic_recovery_redispatch_candidate(
        self,
        recovery: Mapping[str, Any],
        *,
        runtime: Mapping[str, Any],
        expected_upstream_recovery_id: str,
        expected_contract_sha256: str,
    ) -> None:
        """Fail closed unless this is the exact audited pre-provider 403."""

        nullable_unset_fields = (
            "first_dispatch_error_code",
            "first_dispatch_error_message_safe",
            "first_dispatch_rejected_at",
            "upstream_recovery_id",
            "policy_id",
            "policy_version",
            "canonical_spec_sha256",
            "code_patch_sha256",
            "tts_verified_asset_count",
            "upstream_classroom_id",
            "scene_count",
            "content_sha256",
            "final_artifact_sha256",
            "artifact_created_at",
            "verified_at",
            "receipt_json",
        )
        terminal_at = recovery.get("terminal_at")
        recovery_id = str(recovery.get("id") or "").strip()
        source_snapshot_sha256 = str(
            recovery.get("source_job_snapshot_sha256") or ""
        )
        candidate_valid = (
            bool(recovery_id)
            and str(recovery.get("runtime_classroom_id") or "")
            == str(runtime.get("id") or "")
            and str(recovery.get("mode") or "") == RECOVERY_MODE
            and str(recovery.get("kind") or "") == RECOVERY_KIND
            and str(recovery.get("status") or "") == "failed"
            and int(recovery.get("dispatch_count") or 0) == 1
            and all(recovery.get(field) is None for field in nullable_unset_fields)
            and str(recovery.get("error_code") or "")
            == "openmaic_recovery_upstream_rejected"
            and bool(str(recovery.get("error_message_safe") or "").strip())
            and isinstance(terminal_at, int)
            and not isinstance(terminal_at, bool)
            and int(terminal_at) > 0
            and str(recovery.get("source_runtime_status") or "") == "failed"
            and str(recovery.get("source_runtime_error_code") or "")
            == "openmaic_generation_failed"
            and str(recovery.get("source_upstream_job_id") or "")
            == str(runtime.get("upstream_job_id") or "")
            and str(recovery.get("source_job_status") or "") == "failed"
            and str(recovery.get("source_job_error") or "")
            == "structured_output_exhausted"
            and int(recovery.get("source_scenes_generated") or -1) == 4
            and int(recovery.get("source_total_scenes") or -1) == 10
            and len(str(recovery.get("source_completed_at") or "")) >= 20
            and len(source_snapshot_sha256) == 64
            and all(char in "0123456789abcdef" for char in source_snapshot_sha256)
            and str(recovery.get("source_generation_contract_sha256") or "")
            == expected_contract_sha256
            and str(recovery.get("expected_upstream_recovery_id") or "")
            == expected_upstream_recovery_id
            and int(recovery.get("llm_call_count") or 0) == 0
            and int(recovery.get("web_search_call_count") or 0) == 0
            and int(recovery.get("image_generation_call_count") or 0) == 0
            and int(recovery.get("video_generation_call_count") or 0) == 0
            and int(recovery.get("tts_expected_call_count") or 0) == 10
            and int(recovery.get("tts_attempted_call_count") or 0) == 0
            and int(recovery.get("tts_completed_call_count") or 0) == 0
            and str(recovery.get("tts_provider_id") or "") == "qwen-tts"
            and str(recovery.get("tts_model_id") or "") == "qwen3-tts-flash"
            and str(recovery.get("tts_voice_id") or "") == "Serena"
            and recovery.get("tts_fallback_used") in {False, 0}
            and not bool(recovery.get("static_contract_verified"))
            and not bool(recovery.get("conversation_probe_verified"))
            and str(runtime.get("status") or "") == "failed"
            and int(runtime.get("attempt_ordinal") or 0) == 3
            and str(runtime.get("error_code") or "")
            == "openmaic_generation_failed"
            and runtime.get("upstream_classroom_id") is None
            and runtime.get("retired_at") is None
        )
        if not candidate_valid:
            self._fail(
                "openmaic_recovery_redispatch_not_allowed",
                "只有首次派发在供应商调用前明确拒绝且零调用的同一恢复可以补发",
                409,
            )

    def _deterministic_recovery_progressed(
        self,
        recovery: Mapping[str, Any],
        receipt: Mapping[str, Any],
    ) -> bool:
        previous = self.repository.decode_json(
            recovery.get("receipt_json"), {}
        )
        if not isinstance(previous, Mapping) or not previous:
            return True

        def fingerprint(value: Mapping[str, Any]) -> tuple[Any, ...]:
            calls = value.get("calls")
            tts = calls.get("tts") if isinstance(calls, Mapping) else None
            return (
                value.get("status"),
                value.get("step"),
                value.get("progress"),
                value.get("updatedAt"),
                tts.get("attempted") if isinstance(tts, Mapping) else None,
                tts.get("completed") if isinstance(tts, Mapping) else None,
            )

        return fingerprint(previous) != fingerprint(receipt)

    @staticmethod
    def _deterministic_recovery_is_stale(
        recovery: Mapping[str, Any], *, timestamp: int | None = None
    ) -> bool:
        checked_at = now_ms() if timestamp is None else timestamp
        return (
            checked_at - int(recovery.get("updated_at") or 0)
            >= SAMPLE_RECOVERY_LOCAL_STALE_AFTER_MS
        )

    def _terminally_fail_stale_recovery(
        self,
        recovery: Mapping[str, Any],
        *,
        error_code: str,
        error_message_safe: str,
        receipt: Mapping[str, Any] | None = None,
    ) -> bool:
        with self.repository.transaction() as conn:
            return self.repository.fail_stale_deterministic_recovery(
                conn,
                recovery_id=str(recovery["id"]),
                runtime_id=str(recovery["runtime_classroom_id"]),
                expected_status=str(recovery["status"]),
                expected_updated_at=int(recovery.get("updated_at") or 0),
                expected_tts_attempted_count=int(
                    recovery.get("tts_attempted_call_count") or 0
                ),
                expected_tts_completed_count=int(
                    recovery.get("tts_completed_call_count") or 0
                ),
                error_code=error_code,
                error_message_safe=error_message_safe,
                receipt=receipt,
                now=now_ms(),
            )

    def _terminally_fail_recovery(
        self,
        *,
        recovery_id: str,
        runtime_id: str,
        error_code: str,
        error_message_safe: str,
        receipt: Mapping[str, Any] | None = None,
    ) -> None:
        tts_attempted_count = None
        tts_completed_count = None
        if isinstance(receipt, Mapping):
            calls = receipt.get("calls")
            tts = calls.get("tts") if isinstance(calls, Mapping) else None
            attempted = tts.get("attempted") if isinstance(tts, Mapping) else None
            completed = tts.get("completed") if isinstance(tts, Mapping) else None
            if isinstance(attempted, int) and not isinstance(attempted, bool):
                tts_attempted_count = attempted
            if isinstance(completed, int) and not isinstance(completed, bool):
                tts_completed_count = completed
        with self.repository.transaction() as conn:
            self.repository.fail_deterministic_recovery(
                conn,
                recovery_id=recovery_id,
                runtime_id=runtime_id,
                error_code=error_code,
                error_message_safe=error_message_safe,
                receipt=receipt,
                tts_attempted_count=tts_attempted_count,
                tts_completed_count=tts_completed_count,
                now=now_ms(),
            )

    @staticmethod
    def _recovery_payload(
        recovery: Mapping[str, Any], *, idempotent: bool
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "recovery": {
                "id": str(recovery["id"]),
                "recoveryRequestId": str(recovery["recovery_request_id"]),
                "runtimeId": str(recovery["runtime_classroom_id"]),
                "mode": str(recovery["mode"]),
                "kind": str(recovery["kind"]),
                "status": str(recovery["status"]),
                "dispatchCount": int(recovery.get("dispatch_count") or 1),
                "source": {
                    "jobId": str(recovery["source_upstream_job_id"]),
                    "status": str(recovery["source_job_status"]),
                    "error": str(recovery["source_job_error"]),
                    "scenesGenerated": int(
                        recovery["source_scenes_generated"]
                    ),
                    "totalScenes": int(recovery["source_total_scenes"]),
                    "jobSnapshotSha256": str(
                        recovery["source_job_snapshot_sha256"]
                    ),
                },
                "upstreamRecoveryId": (
                    str(recovery["upstream_recovery_id"])
                    if recovery.get("upstream_recovery_id")
                    else None
                ),
                "classroomId": (
                    str(recovery["upstream_classroom_id"])
                    if recovery.get("upstream_classroom_id")
                    else None
                ),
                "calls": {
                    "llm": int(recovery.get("llm_call_count") or 0),
                    "webSearch": int(
                        recovery.get("web_search_call_count") or 0
                    ),
                    "imageGeneration": int(
                        recovery.get("image_generation_call_count") or 0
                    ),
                    "videoGeneration": int(
                        recovery.get("video_generation_call_count") or 0
                    ),
                    "tts": {
                        "expected": int(
                            recovery.get("tts_expected_call_count") or 0
                        ),
                        "attempted": int(
                            recovery.get("tts_attempted_call_count") or 0
                        ),
                        "completed": int(
                            recovery.get("tts_completed_call_count") or 0
                        ),
                    },
                },
                "staticContractVerified": bool(
                    recovery.get("static_contract_verified")
                ),
                "conversationProbeVerified": bool(
                    recovery.get("conversation_probe_verified")
                ),
                "errorCode": (
                    str(recovery["error_code"])
                    if recovery.get("error_code")
                    else None
                ),
                "idempotent": bool(idempotent),
                "updatedAt": int(recovery["updated_at"]),
            },
        }

    def _stored_retry_source_context(
        self,
        conn: Any,
        *,
        runtime_id: str,
        expected_previous_job_id: str,
        for_update: bool = False,
    ) -> tuple[Mapping[str, Any], dict[str, Any], int]:
        source = self.repository.get_runtime_classroom(
            conn,
            runtime_id=runtime_id,
            for_update=for_update,
        )
        if source is None:
            self._fail(
                "openmaic_runtime_not_found",
                "没有找到要重试的样板课堂记录",
                404,
            )
        source_attempt = int(source.get("attempt_ordinal") or 1)
        target_attempt = source_attempt + 1
        expected_source_error = SAMPLE_RETRY_SOURCE_ERROR_BY_ATTEMPT.get(
            source_attempt
        )
        if (
            expected_source_error is None
            or target_attempt > SAMPLE_MAX_GENERATION_ATTEMPTS
            or str(source.get("status") or "") != "failed"
            or str(source.get("error_code") or "") != expected_source_error
        ):
            self._fail(
                "openmaic_retry_not_allowed",
                "只有符合固定失败原因的第一次或第二次样板生成可以人工重试",
                409,
            )
        if source_attempt == 1:
            valid_chain = all(
                source.get(field) is None
                for field in (
                    "retry_of_runtime_id",
                    "retry_reason",
                    "expected_previous_job_id",
                )
            )
        else:
            predecessor_id = str(source.get("retry_of_runtime_id") or "")
            predecessor = self.repository.get_runtime_classroom(
                conn,
                runtime_id=predecessor_id,
                for_update=for_update,
            )
            identity_fields = (
                "course_id",
                "course_version",
                "package_id",
                "package_version",
            )
            valid_chain = bool(
                predecessor
                and int(predecessor.get("attempt_ordinal") or 0)
                == source_attempt - 1
                and str(source.get("retry_reason") or "")
                == SAMPLE_RETRY_REASON_BY_ATTEMPT[source_attempt]
                and str(source.get("expected_previous_job_id") or "")
                == str(predecessor.get("upstream_job_id") or "")
                and all(
                    str(source.get(field) or "")
                    == str(predecessor.get(field) or "")
                    for field in identity_fields
                )
            )
        if not valid_chain:
            self._fail(
                "openmaic_retry_not_allowed",
                "受控生成的 attempt1→attempt2→attempt3 审计链不完整",
                409,
            )
        if str(source.get("upstream_job_id") or "") != expected_previous_job_id:
            self._fail(
                "openmaic_retry_previous_job_mismatch",
                "expectedPreviousJobId 与上一次失败任务不一致",
                409,
            )

        manifest = self.repository.decode_json(
            source.get("feature_manifest_json"), {}
        )
        stored_contract = (
            manifest.get("generationContract")
            if isinstance(manifest, Mapping)
            else None
        )
        validated_contract = self._frozen_retry_contract(
            stored_contract,
            source=source,
        )
        if validated_contract is None:
            self._fail(
                "openmaic_retry_generation_contract_mismatch",
                "上一次任务缺少固定样板生成合同",
                409,
            )
        contract_course = validated_contract["course"]
        if (
            str(contract_course.get("id") or "")
            != str(source.get("course_id") or "")
            or str(contract_course.get("version") or "")
            != str(source.get("course_version") or "")
            or str(contract_course.get("packageId") or "")
            != str(source.get("package_id") or "")
            or int(contract_course.get("packageVersion") or 0)
            != int(source.get("package_version") or 0)
        ):
            self._fail(
                "openmaic_retry_generation_contract_mismatch",
                "上一次任务记录与其固定样板生成合同不一致",
                409,
            )
        return source, validated_contract, target_attempt

    def _validate_retry_reason(self, reason: str, *, target_attempt: int) -> None:
        expected_reason = SAMPLE_RETRY_REASON_BY_ATTEMPT.get(target_attempt)
        if reason != expected_reason:
            self._fail(
                "openmaic_retry_reason_invalid",
                f"第 {target_attempt} 次生成的 reason 必须是 {expected_reason}",
                400,
            )

    def _frozen_retry_contract(
        self,
        value: object,
        *,
        source: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Validate immutable source-attempt facts without live registries.

        This path can only return an already persisted retry reservation; it
        never authorizes a provider call. Keeping it independent of the
        active catalog and teacher registry ensures configuration drift cannot
        hide an externally accepted paid attempt.
        """

        if not isinstance(value, Mapping) or _contains_forbidden_contract_field(
            value
        ):
            return None
        contract = dict(value)
        course = contract.get("course")
        teacher = contract.get("teacher")
        teacher_profile = (
            teacher.get("profile") if isinstance(teacher, Mapping) else None
        )
        voice_identity = (
            teacher.get("voiceIdentity")
            if isinstance(teacher, Mapping)
            else None
        )
        voice_config = (
            voice_identity.get("voiceConfig")
            if isinstance(voice_identity, Mapping)
            else None
        )
        speech = contract.get("speechAudioContract")
        required_classroom = contract.get("requiredClassroom")
        schema_version = contract.get("schemaVersion")
        is_legacy_contract = schema_version == SAMPLE_LEGACY_REQUIREMENT_SCHEMA
        legacy_fragments_valid = bool(
            set(contract) == SAMPLE_LEGACY_CONTRACT_FIELDS
            and required_classroom == _legacy_sample_required_classroom()
            and speech == _legacy_sample_speech_audio_contract()
        )
        valid = bool(
            schema_version
            in {SAMPLE_LEGACY_REQUIREMENT_SCHEMA, SAMPLE_REQUIREMENT_SCHEMA}
            and contract.get("sampleMode") == SAMPLE_MODE
            and contract.get("authority")
            == {
                "courseContext": "mira_active_catalog_release",
                "studentContext": "authenticated_learning_session",
                "clientOverridesAllowed": False,
            }
            and isinstance(course, Mapping)
            and str(course.get("id") or "") == str(source["course_id"])
            and str(course.get("version") or "")
            == str(source["course_version"])
            and str(course.get("packageId") or "")
            == str(source["package_id"])
            and int(course.get("packageVersion") or 0)
            == int(source["package_version"])
            and course.get("gradeCode") == SAMPLE_GRADE_CODE
            and course.get("subjectCode") == SAMPLE_SUBJECT
            and isinstance(course.get("skill"), Mapping)
            and course["skill"].get("skillId") == SAMPLE_SKILL_ID
            and teacher_profile
            == {
                "id": "mira_math_clear",
                "version": 2,
                "displayName": "小数老师",
                "languageCode": "zh-CN",
                "teachingStyle": "clear_structured",
            }
            and isinstance(voice_identity, Mapping)
            and voice_identity.get("schemaVersion")
            == "mira.openmaic.qwen3-voice.v1"
            and voice_config
            == {
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": "Serena",
            }
            and voice_identity.get("selectionId") == "qwen-tts::Serena"
            and isinstance(required_classroom, Mapping)
            and isinstance(speech, Mapping)
            and (not is_legacy_contract or legacy_fragments_valid)
            and contract.get("generation")
            == {
                **SAMPLE_GENERATION_OPTIONS,
                "automaticRetries": 0,
                "staleAfterMs": SAMPLE_GENERATION_STALE_AFTER_MS,
            }
        )
        return contract if valid else None

    @staticmethod
    def _attempt_three_upgraded_contract(
        stored_contract: Mapping[str, Any],
        expected_contract: Mapping[str, Any],
    ) -> dict[str, Any] | None:
        """Allow only the server-owned Stage 2 parity v1 -> v2 upgrade.

        Attempt two was generated under the original five-feature v1 contract.
        The explicitly approved third attempt may use the current v2 parity
        policy, but only the enumerated parity fields may change. All course,
        package, learner, teacher, Qwen voice, authority and generation fields
        stay byte-for-byte equivalent as decoded JSON values.
        """

        stored = dict(stored_contract)
        expected = dict(expected_contract)
        if (
            stored.get("schemaVersion") != SAMPLE_LEGACY_REQUIREMENT_SCHEMA
            or expected.get("schemaVersion") != SAMPLE_REQUIREMENT_SCHEMA
            or SAMPLE_REQUIREMENT_SCHEMA == SAMPLE_LEGACY_REQUIREMENT_SCHEMA
            or set(stored) != SAMPLE_LEGACY_CONTRACT_FIELDS
            or stored.get("requiredClassroom")
            != _legacy_sample_required_classroom()
            or stored.get("speechAudioContract")
            != _legacy_sample_speech_audio_contract()
        ):
            return None

        added_fields = set(expected) - set(stored)
        removed_fields = set(stored) - set(expected)
        if (
            not added_fields.issubset(SAMPLE_ATTEMPT_THREE_UPGRADE_FIELDS)
            or removed_fields
        ):
            return None
        unchanged_fields = set(stored) - SAMPLE_ATTEMPT_THREE_UPGRADE_FIELDS
        if any(stored.get(field) != expected.get(field) for field in unchanged_fields):
            return None
        if not all(
            isinstance(expected.get(field), Mapping)
            for field in ("requiredClassroom", "speechAudioContract")
        ):
            return None
        return expected

    def _retry_source_context(
        self,
        conn: Any,
        *,
        runtime_id: str,
        expected_previous_job_id: str,
        for_update: bool = False,
    ) -> tuple[Mapping[str, Any], Mapping[str, Any], dict[str, Any], int]:
        source, stored_contract, target_attempt = (
            self._stored_retry_source_context(
                conn,
                runtime_id=runtime_id,
                expected_previous_job_id=expected_previous_job_id,
                for_update=for_update,
            )
        )

        boundary = _sample_boundary()
        course = self.repository.get_active_release_course_for_boundary(
            conn,
            grade_code=SAMPLE_GRADE_CODE,
            subject=SAMPLE_SUBJECT,
            skill_id=SAMPLE_SKILL_ID,
            curriculum_version=boundary.curriculum_version,
            boundary_version=boundary.boundary_version,
        )
        if course is None:
            self._fail(
                "openmaic_sample_course_not_released",
                "一年级数学数感样板课已不在当前正式发布目录",
                409,
            )
        self._validate_sample_course(course, boundary=boundary)
        identity_fields = (
            "course_id",
            "course_version",
            "package_id",
            "package_version",
        )
        if any(
            str(source.get(field) or "") != str(course.get(field) or "")
            for field in identity_fields
        ):
            self._fail(
                "openmaic_retry_generation_contract_mismatch",
                "上一次任务与当前固定样板课程合同不一致",
                409,
            )

        expected_contract = self._sample_generation_contract(
            course,
            boundary=boundary,
        )
        if stored_contract == expected_contract:
            validated_generation_contract = expected_contract
        elif target_attempt == 3:
            validated_generation_contract = self._attempt_three_upgraded_contract(
                stored_contract,
                expected_contract,
            )
        else:
            validated_generation_contract = None
        if validated_generation_contract is None:
            self._fail(
                "openmaic_retry_generation_contract_mismatch",
                "上一次任务与当前课件合同之间不是获批的单向升级",
                409,
            )
        return source, course, validated_generation_contract, target_attempt

    def _validate_existing_retry_runtime(
        self,
        runtime: Mapping[str, Any],
        *,
        source: Mapping[str, Any],
        target_attempt: int,
        retry_request_id: str,
        expected_previous_job_id: str,
        reason: str,
        expected_contract: Mapping[str, Any],
    ) -> None:
        identity_fields = (
            "course_id",
            "course_version",
            "package_id",
            "package_version",
        )
        manifest = self.repository.decode_json(
            runtime.get("feature_manifest_json"), {}
        )
        runtime_contract = (
            manifest.get("generationContract")
            if isinstance(manifest, Mapping)
            else None
        )
        contract_matches = runtime_contract == expected_contract
        if (
            not contract_matches
            and target_attempt == 3
            and isinstance(runtime_contract, Mapping)
        ):
            contract_matches = (
                self._attempt_three_upgraded_contract(
                    expected_contract,
                    runtime_contract,
                )
                is not None
            )
        valid = bool(
            str(runtime.get("request_id") or "") == retry_request_id
            and int(runtime.get("attempt_ordinal") or 0) == target_attempt
            and str(runtime.get("retry_of_runtime_id") or "")
            == str(source["id"])
            and str(runtime.get("retry_reason") or "") == reason
            and str(runtime.get("expected_previous_job_id") or "")
            == expected_previous_job_id
            and runtime.get("retired_at") is None
            and str(runtime.get("status") or "")
            in {"pending", "generating", "ready", "failed"}
            and all(
                str(runtime.get(field) or "")
                == str(source.get(field) or "")
                for field in identity_fields
            )
            and isinstance(manifest, Mapping)
            and contract_matches
        )
        if not valid:
            self._fail(
                "openmaic_retry_request_conflict",
                "retryRequestId 已用于另一条任务或不同的人工重试合同",
                409,
            )

    @staticmethod
    def _retry_payload(
        runtime: Mapping[str, Any], *, idempotent: bool
    ) -> dict[str, Any]:
        return {
            "ok": True,
            "retry": {
                "retryRequestId": str(runtime["request_id"]),
                "runtimeId": str(runtime["id"]),
                "attemptOrdinal": int(runtime.get("attempt_ordinal") or 2),
                "attemptLimit": SAMPLE_MAX_GENERATION_ATTEMPTS,
                "retryOfRuntimeId": str(runtime["retry_of_runtime_id"]),
                "reason": str(runtime["retry_reason"]),
                "status": str(runtime["status"]),
                "upstreamJobId": (
                    str(runtime["upstream_job_id"])
                    if runtime.get("upstream_job_id")
                    else None
                ),
                "errorCode": (
                    str(runtime["error_code"])
                    if runtime.get("error_code")
                    else None
                ),
                "updatedAt": int(runtime["updated_at"]),
                "automaticRetries": 0,
                "idempotent": bool(idempotent),
            },
        }

    def _build_requirement(
        self,
        course: Mapping[str, Any],
        requested_features: Iterable[str],
        *,
        required_features: Iterable[str] = (),
        generation_contract: Mapping[str, Any] | None = None,
    ) -> str:
        enabled = tuple(requested_features)
        required = tuple(required_features)
        contract = dict(
            generation_contract
            or self._sample_generation_contract(
                course,
                boundary=_sample_boundary(),
            )
        )
        if set(required) != set(SAMPLE_REQUIRED_FEATURES) or set(enabled) != set(
            SAMPLE_REQUIRED_FEATURES
        ):
            self._fail(
                "invalid_openmaic_sample_features",
                "样板课必须使用服务端固定的课堂能力合同",
                400,
            )
        return "\n".join(
            [
                SAMPLE_STRUCTURAL_POLICY_MARKER,
                "为 Mira 生成且只生成一节小学一年级数学完整互动样板课堂。",
                "OpenMAIC 1.0.0 的生成 API 只接受 requirement 文本；以下 JSON 是 Mira 服务端强制合同，不是可选建议。",
                json.dumps(
                    contract,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                ),
                "成品必须恰好 10 个连续有序场景，至少 2 个可渲染 slide，并真实包含可判定 quiz。",
                "必须分别生成 widgetType=simulation、game、visualization3d 的三个独立 interactive 场景；每个都必须带 widgetOutline，输出自包含 HTML、脚本和学生可操作控件，禁止用静态图片或文字冒充互动、小游戏或 3D。",
                "成品必须有且只有一位教师、至少三位非教师同伴 Agent，并有至少两条由不同同伴参与的真实 discussion 动作和可执行 teacher actions。",
                "每个场景必须至少有一条包含可展示讲稿文本的 speech；每个 speech 必须使用独立 audioId 和独立、真实可读取的音频 URL，并写入合同指定的 audioMetadata；TTS 失败时必须让任务失败，禁止静默省略语音。",
                "课堂必须保留学生文字对话和麦克风语音入口；语音识别只允许服务端 qwen-asr/qwen3-asr-flash，禁止浏览器原生识别或其他回退。",
                "必须先教再练：情境导入、显性讲解、示范、互动探索、独立检测、总结。",
                "按 mira-primary-courseware 的精品课标准制作：一页只完成一个教学动作，标题用儿童能理解的动作短句，优先用可数物、数轴、位置图、字母块和前后状态解释，不得用装饰图片或重复文字卡片冒充教学设计。",
                "五个 slide 必须分别承担导入、概念发现、完整示范、引导准备和独立检查，版式不能复制成同一套标题加列表。每个讲解 slide 都必须先用 spotlight 聚焦当前正在讲的真实元素，再播放该页讲解。",
                "互动页必须改变可观察状态并立即显示结果；simulation、game、visualization3d 不得只是按钮计数、静态图片或换标题。",
                "互动和测验只提供练习反馈；正式成绩由 Mira 后端判定。不得泄露独立检测答案。",
                "不得扩大到其他年级、学科或能力点，不得收集个人信息、展示广告、外链或开放互联网聊天。",
            ]
        )

    def _sample_generation_contract(
        self,
        course: Mapping[str, Any],
        *,
        boundary: Any,
    ) -> dict[str, Any]:
        self._validate_sample_course(course, boundary=boundary)
        teachers = list_teacher_profiles(subject=SAMPLE_SUBJECT)
        if len(teachers) != 1:
            self._fail(
                "openmaic_sample_teacher_not_configured",
                "样板课必须绑定唯一的服务端数学老师",
                409,
            )
        teacher = teachers[0]
        try:
            voice = get_openmaic_qwen3_voice_identity(
                teacher.profile_id,
                teacher.version,
            )
        except KeyError as exc:
            raise OpenMaicRuntimeServiceError(
                "openmaic_sample_voice_not_configured",
                "样板课老师尚未绑定获批的 Qwen3 音色",
                status_code=409,
            ) from exc
        voice_payload = voice.to_runtime_payload()
        return {
            "schemaVersion": SAMPLE_REQUIREMENT_SCHEMA,
            "sampleMode": SAMPLE_MODE,
            "authority": {
                "courseContext": "mira_active_catalog_release",
                "studentContext": "authenticated_learning_session",
                "clientOverridesAllowed": False,
            },
            "course": {
                "id": str(course["course_id"]),
                "version": str(course["course_version"]),
                "releaseId": str(course["release_id"]),
                "packageId": str(course["package_id"]),
                "packageVersion": int(course["package_version"]),
                "gradeCode": SAMPLE_GRADE_CODE,
                "gradeLabel": "小学一年级",
                "subjectCode": SAMPLE_SUBJECT,
                "subjectLabel": "数学",
                "skill": boundary.to_catalog_payload(),
                "title": str(course["title"]),
                "objective": str(course["objective"]),
            },
            "learnerConstraints": {
                "developmentStage": "early_primary_grade_1",
                "recommendedAgeBand": "6-8",
                "language": "zh-CN",
                "durationMinutes": 10,
                "reading": "短句、口语化指令、一次只要求一个动作",
                "visuals": "用可数物和数轴支持20以内数量、顺序和大小比较",
                "prohibitedContent": list(boundary.excluded_content),
            },
            "teacher": {
                "profile": {
                    "id": teacher.profile_id,
                    "version": teacher.version,
                    "displayName": teacher.display_name,
                    "languageCode": teacher.language_code,
                    "teachingStyle": teacher.teaching_style,
                },
                "voiceIdentity": voice_payload,
            },
            "requiredClassroom": _sample_required_classroom(),
            "speechAudioContract": {
                "schemaVersion": SAMPLE_AUDIO_METADATA_SCHEMA,
                "requiredForEverySpeechAction": True,
                "requiredForEveryScene": True,
                "uniqueAudioRequired": True,
                "audioUrlMustBeReadable": True,
                "metadataField": "audioMetadata",
                "fallbackMetadataField": "fallbackUsed",
                "providerId": voice.provider_id,
                "modelId": voice.model_id,
                "voiceId": voice.voice_id,
                "fallbackAllowed": False,
            },
            "conversationContract": _sample_conversation_contract(),
            "generation": {
                **SAMPLE_GENERATION_OPTIONS,
                "automaticRetries": 0,
                "staleAfterMs": SAMPLE_GENERATION_STALE_AFTER_MS,
            },
        }

    def _validate_sample_course(self, course: Mapping[str, Any], *, boundary: Any) -> None:
        expected = {
            "grade_code": SAMPLE_GRADE_CODE,
            "subject": SAMPLE_SUBJECT,
            "node_code": SAMPLE_SKILL_ID,
            "curriculum_version": boundary.curriculum_version,
            "boundary_version": boundary.boundary_version,
        }
        if any(str(course.get(field) or "") != value for field, value in expected.items()):
            self._fail(
                "openmaic_sample_course_identity_mismatch",
                "正式发布课程与一年级数学数感样板合同不一致",
                409,
            )

    def _validated_sample_contract(
        self, value: object | None
    ) -> dict[str, Any] | None:
        """Return a strictly verified server-owned sample contract.

        Older, non-sample manifests are still understood by the generic DSL
        validator when no contract is supplied.  Once a sample contract is
        present, however, every static policy field is checked again before a
        generated classroom can become ready or be approved for students.
        """

        if value is None:
            return None
        if not isinstance(value, Mapping):
            self._fail(
                "openmaic_sample_generation_contract_invalid",
                "样板课堂生成合同格式无效",
                502,
            )
        contract = dict(value)
        if _contains_forbidden_contract_field(contract):
            self._fail(
                "openmaic_sample_generation_contract_invalid",
                "样板课堂生成合同不得包含密钥或 Provider 地址",
                502,
            )

        boundary = _sample_boundary()
        teachers = list_teacher_profiles(subject=SAMPLE_SUBJECT)
        if len(teachers) != 1:
            self._fail(
                "openmaic_sample_generation_contract_invalid",
                "样板课堂老师合同与服务端注册表不一致",
                502,
            )
        teacher = teachers[0]
        try:
            voice = get_openmaic_qwen3_voice_identity(
                teacher.profile_id,
                teacher.version,
            )
        except KeyError as exc:
            raise OpenMaicRuntimeServiceError(
                "openmaic_sample_generation_contract_invalid",
                "样板课堂 Qwen3 音色合同与服务端注册表不一致",
                status_code=502,
            ) from exc

        authority = contract.get("authority")
        course = contract.get("course")
        learner = contract.get("learnerConstraints")
        teacher_contract = contract.get("teacher")
        required_classroom = contract.get("requiredClassroom")
        speech_contract = contract.get("speechAudioContract")
        conversation_contract = contract.get("conversationContract")
        generation = contract.get("generation")
        dynamic_course_fields_valid = (
            isinstance(course, Mapping)
            and all(
                _nonempty_string(course.get(field))
                for field in (
                    "id",
                    "version",
                    "releaseId",
                    "packageId",
                    "title",
                    "objective",
                )
            )
            and isinstance(course.get("packageVersion"), int)
            and not isinstance(course.get("packageVersion"), bool)
            and int(course["packageVersion"]) > 0
        )
        expected_teacher = {
            "profile": {
                "id": teacher.profile_id,
                "version": teacher.version,
                "displayName": teacher.display_name,
                "languageCode": teacher.language_code,
                "teachingStyle": teacher.teaching_style,
            },
            "voiceIdentity": voice.to_runtime_payload(),
        }
        expected_required_classroom = _sample_required_classroom()
        expected_speech_contract = {
            "schemaVersion": SAMPLE_AUDIO_METADATA_SCHEMA,
            "requiredForEverySpeechAction": True,
            "requiredForEveryScene": True,
            "uniqueAudioRequired": True,
            "audioUrlMustBeReadable": True,
            "metadataField": "audioMetadata",
            "fallbackMetadataField": "fallbackUsed",
            "providerId": voice.provider_id,
            "modelId": voice.model_id,
            "voiceId": voice.voice_id,
            "fallbackAllowed": False,
        }
        expected_conversation_contract = _sample_conversation_contract()
        expected_generation = {
            **SAMPLE_GENERATION_OPTIONS,
            "automaticRetries": 0,
            "staleAfterMs": SAMPLE_GENERATION_STALE_AFTER_MS,
        }
        valid = (
            contract.get("schemaVersion") == SAMPLE_REQUIREMENT_SCHEMA
            and contract.get("sampleMode") == SAMPLE_MODE
            and authority
            == {
                "courseContext": "mira_active_catalog_release",
                "studentContext": "authenticated_learning_session",
                "clientOverridesAllowed": False,
            }
            and dynamic_course_fields_valid
            and course.get("gradeCode") == SAMPLE_GRADE_CODE
            and course.get("gradeLabel") == "小学一年级"
            and course.get("subjectCode") == SAMPLE_SUBJECT
            and course.get("subjectLabel") == "数学"
            and course.get("skill") == boundary.to_catalog_payload()
            and learner
            == {
                "developmentStage": "early_primary_grade_1",
                "recommendedAgeBand": "6-8",
                "language": "zh-CN",
                "durationMinutes": 10,
                "reading": "短句、口语化指令、一次只要求一个动作",
                "visuals": "用可数物和数轴支持20以内数量、顺序和大小比较",
                "prohibitedContent": list(boundary.excluded_content),
            }
            and teacher_contract == expected_teacher
            and required_classroom == expected_required_classroom
            and speech_contract == expected_speech_contract
            and conversation_contract == expected_conversation_contract
            and generation == expected_generation
        )
        if not valid:
            self._fail(
                "openmaic_sample_generation_contract_invalid",
                "样板课堂生成合同与服务端固定课程、老师或语音政策不一致",
                502,
            )
        return contract

    def _sample_manifest_verified(self, manifest: object) -> bool:
        if not isinstance(manifest, Mapping):
            return False
        try:
            contract = self._validated_sample_contract(
                manifest.get("generationContract")
            )
        except OpenMaicRuntimeServiceError:
            return False
        if contract is None:
            return False
        required = set(SAMPLE_REQUIRED_FEATURES)
        enabled = manifest.get("enabled")
        manifest_required = manifest.get("required")
        present = manifest.get("present")
        missing = manifest.get("missing")
        evidence = manifest.get("evidence")
        teacher = manifest.get("teacherIdentity")
        speech = manifest.get("speechAudio")
        narration = manifest.get("sceneNarration")
        conversation = manifest.get("conversation")
        speech_contract = contract["speechAudioContract"]
        conversation_contract = contract["conversationContract"]
        voice_config = contract["teacher"]["voiceIdentity"]["voiceConfig"]
        return bool(
            manifest.get("schemaVersion") == self.MANIFEST_SCHEMA
            and isinstance(enabled, list)
            and len(enabled) == len(required)
            and set(enabled) == required
            and isinstance(manifest_required, list)
            and len(manifest_required) == len(required)
            and set(manifest_required) == required
            and isinstance(present, list)
            and required.issubset(set(present))
            and missing == []
            and isinstance(evidence, Mapping)
            and all(
                isinstance(evidence.get(feature), Mapping)
                and evidence[feature].get("verified") is True
                for feature in required
            )
            and isinstance(teacher, Mapping)
            and teacher.get("verified") is True
            and teacher.get("teacherProfile")
            == contract["teacher"]["profile"]
            and teacher.get("voiceConfig") == voice_config
            and isinstance(speech, Mapping)
            and speech.get("verified") is True
            and isinstance(speech.get("speechActionCount"), int)
            and not isinstance(speech.get("speechActionCount"), bool)
            and int(speech["speechActionCount"]) > 0
            and isinstance(speech.get("verifiedAssetCount"), int)
            and not isinstance(speech.get("verifiedAssetCount"), bool)
            and int(speech["verifiedAssetCount"])
            == int(speech["speechActionCount"])
            and isinstance(speech.get("signals"), list)
            and bool(speech["signals"])
            and all(_nonempty_string(signal) for signal in speech["signals"])
            and speech.get("providerId") == speech_contract["providerId"]
            and speech.get("modelId") == speech_contract["modelId"]
            and speech.get("voiceId") == speech_contract["voiceId"]
            and speech.get("fallbackAllowed") is False
            and manifest.get("sceneCount") == SAMPLE_EXACT_SCENE_COUNT
            and isinstance(narration, Mapping)
            and narration.get("verified") is True
            and narration.get("sceneCount") == SAMPLE_EXACT_SCENE_COUNT
            and narration.get("narratedSceneCount") == SAMPLE_EXACT_SCENE_COUNT
            and narration.get("transcriptSceneCount") == SAMPLE_EXACT_SCENE_COUNT
            and isinstance(narration.get("signals"), list)
            and len(narration["signals"]) >= SAMPLE_EXACT_SCENE_COUNT
            and all(_nonempty_string(signal) for signal in narration["signals"])
            and isinstance(conversation, Mapping)
            and conversation.get("verified") is True
            and conversation.get("textChat")
            is conversation_contract["textChatRequired"]
            and conversation.get("voiceInput")
            is conversation_contract["voiceInputRequired"]
            and conversation.get("asr") == conversation_contract["asr"]
            and isinstance(conversation.get("signals"), list)
            and bool(conversation["signals"])
            and all(_nonempty_string(signal) for signal in conversation["signals"])
        )

    def _requested_manifest(
        self,
        features: Iterable[str],
        required_features: Iterable[str] = (),
        *,
        generation_contract: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        enabled = list(features)
        required = list(required_features)
        manifest = {
            "schemaVersion": self.MANIFEST_SCHEMA,
            "sourceVersion": self.SOURCE_VERSION,
            "sourceCommit": self.SOURCE_COMMIT,
            "enabled": enabled,
            # Compatibility alias for callers that consumed the v1 manifest.
            "requested": enabled,
            "required": required,
            "present": [],
            "missing": required,
            "evidence": _empty_runtime_evidence(reason="generation_pending"),
            "platform": {
                "mp4Export": False,
                "mp4ExportConfigured": self.video_export_enabled,
                "mp4ExportCapabilityProbed": False,
                "mp4ExportClassroomDryRun": False,
                "assessmentAuthority": "mira_backend",
            },
        }
        if generation_contract is not None:
            manifest["generationContract"] = dict(generation_contract)
            manifest["speechAudio"] = {
                "verified": False,
                "reason": "generation_pending",
            }
            manifest["sceneNarration"] = {
                "verified": False,
                "reason": "generation_pending",
            }
            manifest["conversation"] = {
                "verified": False,
                "reason": "generation_pending",
            }
        return manifest

    def _validate_and_manifest(
        self,
        classroom: Mapping[str, Any],
        *,
        requested: Iterable[str],
        required: Iterable[str] = (),
        generation_contract: object | None = None,
    ) -> dict[str, Any]:
        stage = classroom.get("stage")
        scenes = classroom.get("scenes")
        if not isinstance(stage, dict) or not isinstance(scenes, list):
            self._fail(
                "invalid_openmaic_classroom",
                "OpenMAIC 课堂缺少 stage 或 scenes",
                502,
            )
        if not 1 <= len(scenes) <= 80:
            self._fail(
                "invalid_openmaic_scene_count",
                "OpenMAIC 课堂场景数量不在安全范围内",
                502,
            )
        _validate_stage(stage, fail=self._fail)
        stage_id = str(stage["id"])
        agent_roles = _stage_agent_roles(stage, fail=self._fail)
        sample_contract = self._validated_sample_contract(generation_contract)
        teacher_identity = None
        peer_agent_ids: set[str] = set()
        if sample_contract is not None:
            if len(scenes) != SAMPLE_EXACT_SCENE_COUNT:
                self._fail(
                    "openmaic_sample_scene_count_incomplete",
                    f"完整样板课堂必须恰好包含 {SAMPLE_EXACT_SCENE_COUNT} 个场景",
                    502,
                )
            teacher_identity = _validate_sample_teacher_identity(
                stage,
                contract=sample_contract,
                fail=self._fail,
            )
            teacher_agent_id = str(teacher_identity["agentId"])
            peer_agent_ids = {
                agent_id
                for agent_id, role in agent_roles.items()
                if agent_id != teacher_agent_id and role != "teacher"
            }
            if len(peer_agent_ids) < SAMPLE_MINIMUM_PEER_AGENTS:
                self._fail(
                    "openmaic_sample_peer_agents_incomplete",
                    "完整样板课堂必须包含老师之外至少三位同伴 Agent",
                    502,
                )

        present: set[str] = set()
        action_types: set[str] = set()
        scene_types: set[str] = set()
        scene_ids: set[str] = set()
        evidence = _empty_runtime_evidence()
        media_probe_cache: dict[str, bool] = {}
        audio_probe_cache: dict[str, bool] = {}
        audio_evidence_signals: list[str] = []
        narration_evidence_signals: list[str] = []
        audio_ids: set[str] = set()
        audio_urls: set[str] = set()
        scene_orders: list[int] = []
        required_widget_types_present: set[str] = set()
        discussion_action_count = 0
        discussion_peer_ids: set[str] = set()
        slide_scene_count = 0
        speech_action_count = 0
        for scene in scenes:
            if not isinstance(scene, dict):
                self._fail(
                    "invalid_openmaic_scene", "OpenMAIC 课堂包含无效场景", 502
                )
            _validate_scene_core(scene, stage_id=stage_id, fail=self._fail)
            scene_id = str(scene["id"])
            if scene_id in scene_ids:
                self._fail(
                    "invalid_openmaic_scene",
                    "OpenMAIC 课堂包含重复场景编号",
                    502,
                )
            scene_ids.add(scene_id)
            scene_order = scene.get("order")
            if sample_contract is not None and (
                not isinstance(scene_order, int) or isinstance(scene_order, bool)
            ):
                self._fail(
                    "openmaic_sample_scene_order_invalid",
                    "完整样板课堂的场景顺序必须是连续整数",
                    502,
                )
            if isinstance(scene_order, int) and not isinstance(scene_order, bool):
                scene_orders.append(scene_order)
            scene_type = str(scene["type"])
            if (
                sample_contract is not None
                and scene_type
                not in set(sample_contract["requiredClassroom"]["sceneTypes"])
            ):
                self._fail(
                    "openmaic_sample_scene_type_invalid",
                    "完整样板课堂只能包含课件、测验和互动场景",
                    502,
                )
            scene_types.add(scene_type)
            content = scene["content"]
            elements_by_id: dict[str, Mapping[str, Any]] = {}

            if scene_type == "slide":
                elements_by_id = _validate_slide_content(content, fail=self._fail)
                if elements_by_id:
                    slide_scene_count += 1
                    _add_evidence(
                        evidence,
                        "slides",
                        f"scene:{scene_id}:slide-elements:{len(elements_by_id)}",
                    )
            elif scene_type == "quiz":
                question_count = _validate_quiz_content(content, fail=self._fail)
                if question_count:
                    _add_evidence(
                        evidence,
                        "quiz",
                        f"scene:{scene_id}:quiz-questions:{question_count}",
                    )
            elif scene_type == "interactive":
                (
                    widget_type,
                    has_embedded_html,
                    has_interactive_controls,
                    has_complete_interaction,
                ) = _validate_interactive_content(
                    content, fail=self._fail
                )
                if (
                    sample_contract is not None
                    and widget_type in SAMPLE_REQUIRED_WIDGET_TYPES
                    and (
                        not has_embedded_html
                        or not has_interactive_controls
                        or not has_complete_interaction
                    )
                ):
                    self._fail(
                        "openmaic_sample_interactive_incomplete",
                        "模拟、小游戏和 3D 场景必须包含自包含脚本与可操作控件",
                        502,
                    )
                if (
                    has_embedded_html
                    and has_interactive_controls
                    and has_complete_interaction
                    and widget_type
                ):
                    required_widget_types_present.add(widget_type)
                if has_complete_interaction and widget_type == "simulation":
                    _add_evidence(
                        evidence,
                        "simulation",
                        f"scene:{scene_id}:widgetType:simulation",
                    )
                elif has_complete_interaction and widget_type == "game":
                    _add_evidence(
                        evidence,
                        "html_game",
                        f"scene:{scene_id}:widgetType:game",
                    )
                elif has_complete_interaction and widget_type == "visualization3d":
                    _add_evidence(
                        evidence,
                        "3d_visualization",
                        f"scene:{scene_id}:widgetType:visualization3d",
                    )
                elif has_complete_interaction and widget_type == "diagram":
                    _add_evidence(
                        evidence,
                        "diagram",
                        f"scene:{scene_id}:widgetType:diagram",
                    )
                elif has_complete_interaction and widget_type == "code":
                    _add_evidence(
                        evidence,
                        "code",
                        f"scene:{scene_id}:widgetType:code",
                    )
            elif scene_type == "pbl":
                pbl_kind = _validate_pbl_content(content, fail=self._fail)
                if pbl_kind:
                    _add_evidence(
                        evidence,
                        "pbl",
                        f"scene:{scene_id}:pbl:{pbl_kind}",
                    )

            actions = scene.get("actions", [])
            if not isinstance(actions, list):
                self._fail(
                    "invalid_openmaic_actions",
                    "OpenMAIC 场景动作格式无效",
                    502,
                )
            if len(actions) > MAX_SCENE_ACTIONS:
                self._fail(
                    "invalid_openmaic_actions",
                    "OpenMAIC 场景动作数量超过安全上限",
                    502,
                )
            seen_action_ids: set[str] = set()
            scene_speech_count = 0
            for action in actions:
                action_type, action_id = _validate_action(action, fail=self._fail)
                if action_id in seen_action_ids:
                    self._fail(
                        "invalid_openmaic_action",
                        "OpenMAIC 场景包含重复动作编号",
                        502,
                    )
                seen_action_ids.add(action_id)
                action_types.add(action_type)
                action_signal = f"scene:{scene_id}:action:{action_id}:{action_type}"

                if action_type == "speech" and sample_contract is not None:
                    if not _nonempty_string(action.get("text")):
                        self._fail(
                            "openmaic_sample_transcript_missing",
                            "完整样板课堂的每条讲解必须包含可展示讲稿",
                            502,
                        )
                    audio_id = str(action.get("audioId") or "").strip()
                    audio_url = str(action.get("audioUrl") or "").strip()
                    if audio_id in audio_ids or audio_url in audio_urls:
                        self._fail(
                            "openmaic_sample_speech_audio_reused",
                            "完整样板课堂的每条讲解必须使用独立 Qwen 音频资产",
                            502,
                        )
                    audio_ids.add(audio_id)
                    audio_urls.add(audio_url)
                    speech_action_count += 1
                    scene_speech_count += 1
                    _validate_sample_speech_audio(
                        action,
                        contract=sample_contract,
                        media_available=self._audio_media_available,
                        probe_cache=audio_probe_cache,
                        fail=self._fail,
                    )
                    _append_bounded_signal(
                        audio_evidence_signals,
                        (
                            f"scene:{scene_id}:action:{action_id}:audio:"
                            f"{action['audioId']}:asset-probed"
                        ),
                    )
                elif action_type in {"spotlight", "laser"}:
                    target = str(action["elementId"])
                    if scene_type != "slide" or target not in elements_by_id:
                        self._fail(
                            "invalid_openmaic_action_target",
                            "OpenMAIC 教师动作指向了不存在的课件元素",
                            502,
                        )
                    _add_evidence(evidence, "teacher_actions", action_signal)
                elif action_type == "play_video":
                    target = str(action["elementId"])
                    element = elements_by_id.get(target)
                    if scene_type != "slide" or not element or element.get("type") != "video":
                        self._fail(
                            "invalid_openmaic_video_target",
                            "OpenMAIC 视频动作没有指向当前幻灯片的视频元素",
                            502,
                        )
                    media_ref = _playable_video_reference(element)
                    media_available = False
                    if media_ref:
                        cached = media_probe_cache.get(media_ref)
                        if cached is None:
                            if len(media_probe_cache) >= MAX_MEDIA_PROBES:
                                self._fail(
                                    "invalid_openmaic_media_refs",
                                    "OpenMAIC 课堂媒体引用数量超过安全上限",
                                    502,
                                )
                            cached = self._video_media_available(media_ref)
                            media_probe_cache[media_ref] = cached
                        media_available = cached
                    if media_available:
                        _add_evidence(
                            evidence,
                            "video",
                            f"{action_signal}:asset-probed",
                        )
                        _add_evidence(evidence, "teacher_actions", action_signal)

                elif action_type in WHITEBOARD_DRAW_ACTIONS:
                    if _productive_whiteboard_action(action_type, action):
                        _add_evidence(
                            evidence,
                            "realtime_whiteboard",
                            action_signal,
                        )
                        _add_evidence(evidence, "teacher_actions", action_signal)
                elif action_type == "discussion":
                    discussion_agent = str(action.get("agentId") or "").strip()
                    if sample_contract is not None:
                        if discussion_agent not in peer_agent_ids:
                            self._fail(
                                "openmaic_sample_discussion_agent_invalid",
                                "完整样板课堂的讨论动作必须明确指向同伴 Agent",
                                502,
                            )
                        discussion_action_count += 1
                        discussion_peer_ids.add(discussion_agent)
                    if (
                        _has_multi_agent_roster(agent_roles)
                        and (not discussion_agent or discussion_agent in agent_roles)
                    ):
                        _add_evidence(
                            evidence,
                            "multi_agent_roundtable",
                            f"{action_signal}:roster:{len(agent_roles)}",
                        )
                elif action_type in WIDGET_TEACHER_ACTIONS:
                    if scene_type == "interactive" and _productive_widget_action(
                        action_type,
                        action,
                        html=str(content.get("html") or ""),
                    ):
                        _add_evidence(evidence, "teacher_actions", action_signal)

            if sample_contract is not None:
                if scene_speech_count < 1:
                    self._fail(
                        "openmaic_sample_scene_narration_missing",
                        "完整样板课堂的每个场景都必须有正式讲解和讲稿",
                        502,
                    )
                _append_bounded_signal(
                    narration_evidence_signals,
                    f"scene:{scene_id}:transcript:speech-actions:{scene_speech_count}",
                )

        if sample_contract is not None:
            order_start = min(scene_orders) if scene_orders else -1
            expected_orders = list(
                range(order_start, order_start + SAMPLE_EXACT_SCENE_COUNT)
            )
            if order_start not in {0, 1} or sorted(scene_orders) != expected_orders:
                self._fail(
                    "openmaic_sample_scene_order_invalid",
                    "完整样板课堂的十个场景必须按连续顺序排列",
                    502,
                )
            if slide_scene_count < SAMPLE_MINIMUM_SLIDE_SCENES:
                self._fail(
                    "openmaic_sample_slides_incomplete",
                    "完整样板课堂至少需要两个正式讲解课件场景",
                    502,
                )
            if not set(SAMPLE_REQUIRED_WIDGET_TYPES).issubset(
                required_widget_types_present
            ):
                self._fail(
                    "openmaic_sample_interactive_incomplete",
                    "完整样板课堂缺少模拟、小游戏或 3D 互动成品",
                    502,
                )
            if (
                discussion_action_count < SAMPLE_MINIMUM_DISCUSSION_ACTIONS
                or len(discussion_peer_ids) < SAMPLE_MINIMUM_DISCUSSION_ACTIONS
            ):
                self._fail(
                    "openmaic_sample_discussion_incomplete",
                    "完整样板课堂至少需要两位不同同伴参与真实讨论",
                    502,
                )
            if (
                speech_action_count < SAMPLE_EXACT_SCENE_COUNT
                or len(audio_ids) != speech_action_count
                or len(audio_urls) != speech_action_count
                or len(audio_probe_cache) != speech_action_count
            ):
                self._fail(
                    "openmaic_sample_speech_audio_missing",
                    "完整样板课堂的逐场讲解与独立 Qwen 音频不完整",
                    502,
                )

        for feature, feature_evidence in evidence.items():
            if feature_evidence["verified"]:
                present.add(feature)

        enabled_features = _feature_list(
            list(requested), default=(), allow_empty=True
        )
        required_features = _feature_list(
            list(required), default=(), allow_empty=True
        )
        if not set(required_features).issubset(enabled_features):
            self._fail(
                "invalid_openmaic_required_features",
                "OpenMAIC 必需能力不是已启用能力的子集",
                502,
            )
        platform = self._mp4_platform_manifest()
        evidence["mp4_export"] = {
            "verified": False,
            "signals": (
                ["platform-capability-probed"] if platform["mp4Export"] else []
            ),
            "reasons": [
                "openmaic_0_3_2_has_no_server_classroom_export_dry_run"
            ],
        }
        missing = sorted(set(required_features) - present)
        manifest = self._requested_manifest(
            enabled_features,
            required_features,
            generation_contract=sample_contract,
        )
        manifest["present"] = sorted(present)
        manifest["missing"] = missing
        manifest["evidence"] = evidence
        manifest["platform"] = platform
        manifest["sceneTypes"] = sorted(scene_types)
        manifest["actionTypes"] = sorted(action_types)
        manifest["sceneCount"] = len(scenes)
        if sample_contract is not None:
            manifest["teacherIdentity"] = teacher_identity
            manifest["speechAudio"] = {
                "verified": True,
                "speechActionCount": speech_action_count,
                "verifiedAssetCount": len(audio_probe_cache),
                "signals": audio_evidence_signals,
                "providerId": sample_contract["speechAudioContract"]["providerId"],
                "modelId": sample_contract["speechAudioContract"]["modelId"],
                "voiceId": sample_contract["speechAudioContract"]["voiceId"],
                "fallbackAllowed": False,
            }
            manifest["sceneNarration"] = {
                "verified": True,
                "sceneCount": len(scenes),
                "narratedSceneCount": len(narration_evidence_signals),
                "transcriptSceneCount": len(narration_evidence_signals),
                "signals": narration_evidence_signals,
            }
            manifest["conversation"] = {
                "verified": False,
                "reason": "gateway_probe_pending",
                "textChat": sample_contract["conversationContract"]["textChatRequired"],
                "voiceInput": sample_contract["conversationContract"]["voiceInputRequired"],
                "asr": dict(sample_contract["conversationContract"]["asr"]),
                "signals": [],
            }
        return manifest

    def _sample_conversation_manifest(
        self, contract: Mapping[str, Any], *, receipts: Mapping[str, Any]
    ) -> dict[str, Any]:
        conversation_contract = contract["conversationContract"]
        asr_contract = conversation_contract["asr"]
        chat_receipt = receipts.get("chat")
        transcription_receipt = receipts.get("transcription")
        proof = (
            transcription_receipt.get("proof")
            if isinstance(transcription_receipt, Mapping)
            else None
        )
        policy = proof.get("asrPolicy") if isinstance(proof, Mapping) else None
        if not isinstance(chat_receipt, Mapping) or not isinstance(policy, Mapping):
            self._fail(
                "openmaic_sample_conversation_probe_invalid",
                "学生文字与 Qwen 语音对话验证回执无效",
                502,
            )
        return {
            "verified": True,
            "textChat": conversation_contract["textChatRequired"],
            "voiceInput": conversation_contract["voiceInputRequired"],
            "asr": dict(asr_contract),
            "signals": [
                f"receipt:no-cookie:{chat_receipt.get('noCookieStatus')}",
                f"receipt:wrong-stage:{chat_receipt.get('wrongStageStatus')}",
                f"receipt:asr:{policy.get('providerId')}:{policy.get('modelId')}:no-fallback",
            ],
        }

    def _audio_media_available(self, reference: str) -> bool:
        if self.client is None:
            return False
        try:
            return self.client.media_available(reference, expected_prefix="audio/")
        except OpenMaicFullRuntimeError:
            return False

    def _image_media_available(self, reference: str) -> bool:
        if self.client is None:
            return False
        try:
            return self.client.media_available(reference, expected_prefix="image/")
        except OpenMaicFullRuntimeError:
            return False

    def _video_media_available(self, reference: str) -> bool:
        if reference.casefold().startswith("data:video/"):
            _header, separator, payload = reference.partition(",")
            return bool(separator and payload.strip())
        if self.client is None:
            return False
        try:
            return self.client.media_available(reference, expected_prefix="video/")
        except OpenMaicFullRuntimeError:
            return False

    def _mp4_platform_manifest(self) -> dict[str, Any]:
        probed = False
        available = False
        if self.video_export_enabled and self.client is not None:
            try:
                available = self.client.video_export_capability()
                probed = True
            except OpenMaicFullRuntimeError:
                probed = True
        return {
            "mp4Export": available,
            "mp4ExportConfigured": self.video_export_enabled,
            "mp4ExportCapabilityProbed": probed,
            # The pinned v1.0.0 API has a deployment capability probe but no
            # server endpoint that compiles one classroom as a dry run.
            "mp4ExportClassroomDryRun": False,
            "assessmentAuthority": "mira_backend",
        }

    def _runtime_payload(
        self, runtime: Mapping[str, Any], *, upstream_job: object | None = None
    ) -> dict[str, Any]:
        manifest = self.repository.decode_json(
            runtime.get("feature_manifest_json"), {}
        )
        payload: dict[str, Any] = {
            "ok": True,
            "runtime": {
                "id": str(runtime["id"]),
                "requestId": str(runtime["request_id"]),
                "attemptOrdinal": int(runtime.get("attempt_ordinal") or 1),
                "providerAttemptOrdinal": (
                    int(runtime["provider_attempt_ordinal"])
                    if runtime.get("provider_attempt_ordinal") is not None
                    else None
                ),
                "retryOfRuntimeId": (
                    str(runtime["retry_of_runtime_id"])
                    if runtime.get("retry_of_runtime_id")
                    else None
                ),
                "courseId": str(runtime["course_id"]),
                "courseVersion": str(runtime["course_version"]),
                "packageId": str(runtime["package_id"]),
                "packageVersion": int(runtime["package_version"]),
                "status": str(runtime["status"]),
                "qualityStatus": str(runtime.get("quality_status") or "pending_review"),
                "features": manifest,
                "readyAt": runtime.get("ready_at"),
                "updatedAt": int(runtime["updated_at"]),
            },
        }
        if upstream_job is not None:
            payload["job"] = {
                "id": getattr(upstream_job, "job_id"),
                "status": getattr(upstream_job, "status"),
                "step": getattr(upstream_job, "step"),
                "progress": getattr(upstream_job, "progress"),
                "done": getattr(upstream_job, "done"),
            }
        return payload

    def _require_runtime(self) -> None:
        if not self.enabled or self.client is None or not self.public_url:
            self._fail(
                "openmaic_runtime_disabled",
                "完整互动课堂尚未在当前环境启用",
                404,
            )

    def _require_generation(self) -> None:
        self._require_runtime()
        if not self.generation_enabled:
            self._fail(
                "openmaic_generation_disabled",
                "完整课堂生成尚未在当前环境启用",
                503,
            )

    def _require_formal_citation_recovery(self) -> None:
        self._require_generation()
        if (
            not self.formal_citation_recovery_enabled
            or self.formal_citation_recovery_client is None
            or not self.formal_citation_recovery_source_job_id
        ):
            self._fail(
                "openmaic_formal_citation_recovery_disabled",
                "正式课堂引用恢复尚未在当前环境启用",
                503,
            )

    def _require_deterministic_recovery(self) -> None:
        self._require_runtime()
        if self.generation_enabled:
            self._fail(
                "openmaic_recovery_generation_must_be_disabled",
                "确定性恢复启用时必须关闭普通课堂生成",
                503,
            )
        if (
            not self.deterministic_recovery_enabled
            or self.deterministic_recovery_client is None
            or self.conversation_probe_service is None
            or self.conversation_probe_client is None
        ):
            self._fail(
                "openmaic_deterministic_recovery_disabled",
                "确定性零 LLM 恢复尚未在当前环境启用",
                503,
            )

    def _require_deterministic_recovery_redispatch(self) -> None:
        self._require_deterministic_recovery()
        if not self.deterministic_recovery_redispatch_enabled:
            self._fail(
                "openmaic_recovery_redispatch_disabled",
                "确定性恢复补发控制开关尚未启用",
                503,
            )

    def _require_tts_credential_recovery(self) -> None:
        self._require_runtime()
        if self.generation_enabled:
            self._fail(
                "openmaic_tts_credential_generation_must_be_disabled",
                "TTS 凭证恢复启用时必须关闭普通课堂生成",
                503,
            )
        if (
            not self.tts_credential_recovery_enabled
            or not self.deterministic_recovery_enabled
            or self.deterministic_recovery_redispatch_enabled
            or self.tts_credential_recovery_client is None
            or self.deterministic_recovery_client is None
            or self.conversation_probe_service is None
            or self.conversation_probe_client is None
        ):
            self._fail(
                "openmaic_tts_credential_recovery_disabled",
                "一次性 TTS 凭证恢复尚未在当前环境启用",
                503,
            )

    @staticmethod
    def _fail(code: str, message: str, status_code: int) -> None:
        raise OpenMaicRuntimeServiceError(code, message, status_code=status_code)


def _empty_runtime_evidence(*, reason: str = "not_verified") -> dict[str, Any]:
    return {
        feature: {"verified": False, "signals": [], "reasons": [reason]}
        for feature in sorted(RUNTIME_FEATURES)
    }


def _canonical_sha256(value: Mapping[str, Any]) -> str:
    return hashlib.sha256(
        json.dumps(
            value,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()


def _iso8601_epoch_ms(value: object) -> int:
    if not isinstance(value, str) or not value.strip():
        return 0
    text = value.strip()
    if text.endswith("Z"):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return 0
    if parsed.tzinfo is None:
        return 0
    return int(parsed.astimezone(timezone.utc).timestamp() * 1000)


def _openmaic_classroom_content_sha256(value: Mapping[str, Any]) -> str:
    """Match patch 0007's JSON.stringify({ stage, scenes }) digest."""

    return hashlib.sha256(
        json.dumps(
            {"stage": value.get("stage"), "scenes": value.get("scenes")},
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()


def _sample_boundary() -> Any:
    candidates = tuple(
        boundary
        for boundary in boundaries_for(SAMPLE_GRADE_CODE, SAMPLE_SUBJECT)
        if boundary.skill_id == SAMPLE_SKILL_ID
    )
    if len(candidates) != 1:
        raise RuntimeError(
            "primary_1/math/number_sense_20 must resolve to one skill boundary"
        )
    return candidates[0]


def _contains_forbidden_contract_field(value: object) -> bool:
    forbidden = {
        "apikey",
        "api_key",
        "authorization",
        "baseurl",
        "base_url",
        "secret",
        "token",
    }
    if isinstance(value, Mapping):
        return any(
            str(key).strip().casefold() in forbidden
            or _contains_forbidden_contract_field(item)
            for key, item in value.items()
        )
    if isinstance(value, (list, tuple)):
        return any(_contains_forbidden_contract_field(item) for item in value)
    return False


def _add_evidence(
    evidence: dict[str, Any], feature: str, signal: str
) -> None:
    item = evidence[feature]
    item["verified"] = True
    item["reasons"] = []
    if signal in item["signals"]:
        return
    if len(item["signals"]) < MAX_EVIDENCE_SIGNALS_PER_FEATURE:
        item["signals"].append(signal)
        return
    # Preserve the strict v2 evidence shape. When a 101st unique signal
    # arrives, replace the last concrete signal with a deterministic marker
    # rather than adding an unbounded array or an unversioned object field.
    item["signals"][-1] = EVIDENCE_TRUNCATED_SIGNAL


def _append_bounded_signal(signals: list[str], signal: str) -> None:
    if signal in signals:
        return
    if len(signals) < MAX_EVIDENCE_SIGNALS_PER_FEATURE:
        signals.append(signal)
        return
    signals[-1] = EVIDENCE_TRUNCATED_SIGNAL


def _nonempty_string(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _bounded_identifier(value: object) -> bool:
    return _nonempty_string(value) and len(str(value)) <= MAX_DSL_IDENTIFIER_LENGTH


def _finite_number(value: object) -> bool:
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(float(value))
    )


def _validate_stage(stage: Mapping[str, Any], *, fail: Any) -> None:
    if (
        not _bounded_identifier(stage.get("id"))
        or not _nonempty_string(stage.get("name"))
        or not _finite_number(stage.get("createdAt"))
        or not _finite_number(stage.get("updatedAt"))
    ):
        fail(
            "invalid_openmaic_stage",
            "OpenMAIC 课堂 stage 不符合 1.0.0 DSL",
            502,
        )
    agent_ids = stage.get("agentIds")
    if agent_ids is not None and (
        not isinstance(agent_ids, list)
        or len(agent_ids) > MAX_STAGE_AGENTS
        or any(not _bounded_identifier(agent_id) for agent_id in agent_ids)
    ):
        fail(
            "invalid_openmaic_stage_agents",
            "OpenMAIC 课堂 Agent roster 格式无效",
            502,
        )
    configs = stage.get("generatedAgentConfigs")
    if configs is not None:
        if not isinstance(configs, list) or len(configs) > MAX_STAGE_AGENTS:
            fail(
                "invalid_openmaic_stage_agents",
                "OpenMAIC 课堂 Agent roster 格式无效",
                502,
            )
        seen: set[str] = set()
        for config in configs:
            if not isinstance(config, dict) or any(
                not _nonempty_string(config.get(field))
                for field in ("name", "role", "persona", "avatar", "color")
            ) or not _bounded_identifier(config.get("id")) or not _finite_number(
                config.get("priority")
            ):
                fail(
                    "invalid_openmaic_stage_agents",
                    "OpenMAIC 课堂 Agent roster 格式无效",
                    502,
                )
            agent_id = str(config["id"])
            if agent_id in seen:
                fail(
                    "invalid_openmaic_stage_agents",
                    "OpenMAIC 课堂 Agent roster 包含重复编号",
                    502,
                )
            seen.add(agent_id)


def _stage_agent_roles(
    stage: Mapping[str, Any], *, fail: Any
) -> dict[str, str]:
    configs = stage.get("generatedAgentConfigs")
    if isinstance(configs, list) and configs:
        roles = {
            str(config["id"]): str(config["role"]).strip().lower()
            for config in configs
            if isinstance(config, dict)
        }
        if len(roles) != len(configs) or any(
            role not in {"teacher", "assistant", "student"}
            for role in roles.values()
        ):
            fail(
                "invalid_openmaic_stage_agents",
                "OpenMAIC 正式课堂只允许老师、助教和学生角色",
                502,
            )
        return roles
    agent_ids = stage.get("agentIds")
    if not isinstance(agent_ids, list):
        return {}
    unknown = [agent_id for agent_id in agent_ids if agent_id not in DEFAULT_AGENT_ROLES]
    if unknown:
        fail(
            "invalid_openmaic_stage_agents",
            "OpenMAIC 课堂引用了无法解析的预置 Agent",
            502,
        )
    return {str(agent_id): DEFAULT_AGENT_ROLES[str(agent_id)] for agent_id in agent_ids}


def _validate_sample_teacher_identity(
    stage: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    fail: Any,
) -> dict[str, Any]:
    configs = stage.get("generatedAgentConfigs")
    if not isinstance(configs, list):
        fail(
            "openmaic_sample_teacher_identity_missing",
            "样板课堂没有可核验的生成老师配置",
            502,
        )
    teacher_configs = [
        item
        for item in configs
        if isinstance(item, Mapping)
        and str(item.get("role") or "").strip().lower() == "teacher"
    ]
    if len(teacher_configs) != 1:
        fail(
            "openmaic_sample_teacher_identity_missing",
            "样板课堂必须且只能有一位绑定老师",
            502,
        )
    expected_profile = contract["teacher"]["profile"]
    expected_voice = contract["teacher"]["voiceIdentity"]["voiceConfig"]
    teacher = teacher_configs[0]
    if (
        teacher.get("name") != expected_profile["displayName"]
        or teacher.get("voiceConfig") != expected_voice
    ):
        fail(
            "openmaic_sample_teacher_identity_mismatch",
            "样板课堂老师或 Qwen3 音色与服务端固定合同不一致",
            502,
        )
    return {
        "verified": True,
        "agentId": str(teacher["id"]),
        "teacherProfile": dict(expected_profile),
        "voiceConfig": dict(expected_voice),
        "selectionId": contract["teacher"]["voiceIdentity"]["selectionId"],
    }


def _validate_sample_speech_audio(
    action: Mapping[str, Any],
    *,
    contract: Mapping[str, Any],
    media_available: Any,
    probe_cache: dict[str, bool],
    fail: Any,
) -> None:
    speech_contract = contract["speechAudioContract"]
    audio_id = action.get("audioId")
    audio_url = action.get("audioUrl")
    metadata_field = str(speech_contract["metadataField"])
    fallback_field = str(speech_contract["fallbackMetadataField"])
    metadata = action.get(metadata_field)
    if not _bounded_identifier(audio_id) or not _nonempty_string(audio_url):
        fail(
            "openmaic_sample_speech_audio_missing",
            "样板课堂 speech 动作缺少真实音频标识或 URL",
            502,
        )
    reference = str(audio_url).strip()
    if len(reference) > 2048 or not isinstance(metadata, Mapping):
        fail(
            "openmaic_sample_tts_identity_missing",
            "样板课堂 speech 动作缺少正式 TTS 身份元数据",
            502,
        )
    expected_metadata = {
        "schemaVersion": speech_contract["schemaVersion"],
        "providerId": speech_contract["providerId"],
        "modelId": speech_contract["modelId"],
        "voiceId": speech_contract["voiceId"],
        fallback_field: False,
    }
    if dict(metadata) != expected_metadata:
        fail(
            "openmaic_sample_tts_identity_mismatch",
            "样板课堂 speech 音频不是固定 Qwen3 老师音色或发生了回退",
            502,
        )
    available = probe_cache.get(reference)
    if available is None:
        if len(probe_cache) >= MAX_MEDIA_PROBES:
            fail(
                "invalid_openmaic_media_refs",
                "OpenMAIC 课堂媒体引用数量超过安全上限",
                502,
            )
        available = bool(media_available(reference))
        probe_cache[reference] = available
    if not available:
        fail(
            "openmaic_sample_speech_audio_missing",
            "样板课堂 speech 音频无法读取，不能进入审核或发布",
            502,
        )


def _validate_recovery_classroom_artifact_identity(
    classroom: Mapping[str, Any],
    *,
    expected_classroom_id: str,
    fail: Any,
) -> None:
    """Bind the recovery receipt, Stage, and every audio route to one artifact."""

    stage = classroom.get("stage")
    scenes = classroom.get("scenes")
    if (
        not isinstance(stage, Mapping)
        or stage.get("id") != expected_classroom_id
        or not isinstance(scenes, list)
    ):
        fail(
            "openmaic_recovery_classroom_identity_mismatch",
            "确定性恢复课堂编号与实际 Stage 不一致",
            502,
        )
    prefix = f"/api/classroom-media/{expected_classroom_id}/audio/"
    for scene in scenes:
        actions = scene.get("actions") if isinstance(scene, Mapping) else None
        if not isinstance(actions, list):
            continue
        for action in actions:
            if not isinstance(action, Mapping) or action.get("type") != "speech":
                continue
            audio_id = str(action.get("audioId") or "").strip()
            reference = str(action.get("audioUrl") or "").strip()
            parsed = urlsplit(reference)
            filename = parsed.path[len(prefix):] if parsed.path.startswith(prefix) else ""
            if (
                not _bounded_identifier(audio_id)
                or parsed.scheme
                or parsed.netloc
                or parsed.query
                or parsed.fragment
                or "%" in reference
                or not filename
                or "/" in filename
                or filename.startswith(".")
                or ".." in filename
                or not re.fullmatch(r"[A-Za-z0-9_-]+\.[A-Za-z0-9]{2,5}", filename)
                or filename.rsplit(".", 1)[0] != audio_id
            ):
                fail(
                    "openmaic_recovery_audio_identity_mismatch",
                    "确定性恢复音频没有绑定到当前课堂的固定媒体路径",
                    502,
                )


def _validate_scene_core(
    scene: Mapping[str, Any], *, stage_id: str, fail: Any
) -> None:
    scene_type = scene.get("type")
    content = scene.get("content")
    if (
        not _bounded_identifier(scene.get("id"))
        or scene.get("stageId") != stage_id
        or not _nonempty_string(scene.get("title"))
        or not _finite_number(scene.get("order"))
        or scene_type not in SCENE_TYPES
        or not isinstance(content, dict)
        or content.get("type") != scene_type
    ):
        fail(
            "invalid_openmaic_scene",
            "OpenMAIC 场景不符合 1.0.0 DSL",
            502,
        )


def _validate_slide_content(
    content: Mapping[str, Any], *, fail: Any
) -> dict[str, Mapping[str, Any]]:
    canvas = content.get("canvas")
    elements = canvas.get("elements") if isinstance(canvas, dict) else None
    if not isinstance(canvas, dict) or not isinstance(elements, list):
        fail(
            "invalid_openmaic_slide",
            "OpenMAIC 幻灯片缺少可渲染画布",
            502,
        )
    if len(elements) > MAX_SLIDE_ELEMENTS:
        fail(
            "invalid_openmaic_slide",
            "OpenMAIC 幻灯片元素数量超过安全上限",
            502,
        )
    by_id: dict[str, Mapping[str, Any]] = {}
    for element in elements:
        if (
            not isinstance(element, dict)
            or not _bounded_identifier(element.get("id"))
            or element.get("type") not in PPT_ELEMENT_TYPES
        ):
            fail(
                "invalid_openmaic_slide",
                "OpenMAIC 幻灯片包含无效元素",
                502,
            )
        element_id = str(element["id"])
        if element_id in by_id:
            fail(
                "invalid_openmaic_slide",
                "OpenMAIC 幻灯片包含重复元素编号",
                502,
            )
        by_id[element_id] = element
    return by_id


def _renderable_slide_element(element: Mapping[str, Any]) -> bool:
    """Conservatively prove that a slide element can show teaching content."""

    if (
        element.get("visible") is False
        or element.get("hidden") is True
        or str(element.get("display") or "").strip().casefold() == "none"
        or str(element.get("visibility") or "").strip().casefold() == "hidden"
    ):
        return False
    opacity = element.get("opacity")
    if opacity is not None and (
        not _finite_number(opacity) or float(opacity) <= 0
    ):
        return False
    width = element.get("width")
    height = element.get("height")
    if (
        not _finite_number(width)
        or not _finite_number(height)
        or float(width) <= 0
        or float(height) <= 0
    ):
        return False
    element_type = str(element.get("type") or "")
    if element_type == "text":
        return any(
            _nonempty_string(element.get(field))
            for field in ("content", "text")
        )
    if element_type in {"image", "video", "audio"}:
        return any(
            _nonempty_string(element.get(field))
            for field in ("src", "mediaRef", "url")
        )
    if element_type == "latex":
        return _nonempty_string(element.get("latex")) or _nonempty_string(
            element.get("content")
        )
    if element_type == "code":
        return _nonempty_string(element.get("code")) or _nonempty_string(
            element.get("content")
        )
    if element_type == "table":
        rows = element.get("data") or element.get("cells")
        return isinstance(rows, list) and bool(rows)
    if element_type == "chart":
        data = element.get("data")
        return isinstance(data, Mapping) and bool(data)
    # Shapes and lines can be meaningful visual teaching elements when they
    # have real geometry; width/height were already proven positive above.
    return element_type in {"shape", "line"}


def _validate_quiz_content(
    content: Mapping[str, Any], *, fail: Any, require_answers: bool = False
) -> int:
    questions = content.get("questions")
    if not isinstance(questions, list):
        fail(
            "invalid_openmaic_quiz",
            "OpenMAIC 测验缺少 questions 数组",
            502,
        )
    if len(questions) > MAX_QUIZ_QUESTIONS:
        fail(
            "invalid_openmaic_quiz",
            "OpenMAIC 测验题目数量超过安全上限",
            502,
        )
    seen: set[str] = set()
    for question in questions:
        if (
            not isinstance(question, dict)
            or not _bounded_identifier(question.get("id"))
            or question.get("type") not in {"single", "multiple", "short_answer"}
            or not _nonempty_string(question.get("question"))
        ):
            fail(
                "invalid_openmaic_quiz",
                "OpenMAIC 测验包含无效题目",
                502,
            )
        question_id = str(question["id"])
        if question_id in seen:
            fail(
                "invalid_openmaic_quiz",
                "OpenMAIC 测验包含重复题目编号",
                502,
            )
        seen.add(question_id)
        options = question.get("options")
        if options is not None and (
            not isinstance(options, list)
            or len(options) > MAX_QUIZ_OPTIONS
            or any(
                not isinstance(option, dict)
                or not _nonempty_string(option.get("label"))
                or not _nonempty_string(option.get("value"))
                for option in options
            )
        ):
            fail(
                "invalid_openmaic_quiz",
                "OpenMAIC 测验选项格式无效",
                502,
            )
        if isinstance(options, list):
            option_values = [str(option["value"]) for option in options]
            if len(set(option_values)) != len(option_values):
                fail(
                    "invalid_openmaic_quiz",
                    "OpenMAIC 测验包含重复选项值",
                    502,
                )
        if question["type"] in {"single", "multiple"} and (
            not isinstance(options, list) or len(options) < 2
        ):
            fail(
                "invalid_openmaic_quiz",
                "OpenMAIC 选择题缺少有效选项",
                502,
            )
        if require_answers and question["type"] in {"single", "multiple"}:
            answer = question.get("answer")
            valid_values = {
                str(option["value"])
                for option in options
                if isinstance(option, Mapping)
            }
            if (
                not isinstance(answer, list)
                or not answer
                or any(not _nonempty_string(value) for value in answer)
                or not set(str(value) for value in answer).issubset(valid_values)
                or (
                    question["type"] == "single"
                    and len(set(str(value) for value in answer)) != 1
                )
                or question.get("hasAnswer") is not True
            ):
                fail(
                    "invalid_openmaic_quiz_answer",
                    "OpenMAIC 正式选择题缺少可核验答案",
                    502,
                )
        if require_answers and question["type"] == "short_answer" and (
            question.get("hasAnswer") is not False
            or question.get("answer") not in (None, [])
        ):
            fail(
                "invalid_openmaic_quiz_answer",
                "OpenMAIC 正式简答题评分标记无效",
                502,
            )
    return len(questions)


def _validate_interactive_content(
    content: Mapping[str, Any],
    *,
    fail: Any,
    required_widget_types: frozenset[str] = WIDGET_TYPES,
    config_validator: Any = None,
) -> tuple[str | None, bool, bool, bool]:
    html = content.get("html")
    url = content.get("url")
    if not isinstance(html, str) and not isinstance(url, str):
        fail(
            "invalid_openmaic_interactive",
            "OpenMAIC 互动场景缺少 html 或 url",
            502,
        )
    if html is not None and not isinstance(html, str):
        fail(
            "invalid_openmaic_interactive",
            "OpenMAIC 互动场景 html 格式无效",
            502,
        )
    if url is not None and not isinstance(url, str):
        fail(
            "invalid_openmaic_interactive",
            "OpenMAIC 互动场景 url 格式无效",
            502,
        )
    if not _nonempty_string(html) and not _nonempty_string(url):
        fail(
            "invalid_openmaic_interactive",
            "OpenMAIC 互动场景没有可渲染内容",
            502,
        )
    widget_type = content.get("widgetType")
    if widget_type is not None and widget_type not in WIDGET_TYPES:
        fail(
            "invalid_openmaic_widget",
            "OpenMAIC 互动场景 widgetType 无效",
            502,
        )
    config = content.get("widgetConfig")
    config_type = None
    if config is not None:
        if not isinstance(config, dict) or config.get("type") not in WIDGET_TYPES:
            fail(
                "invalid_openmaic_widget",
                "OpenMAIC 互动场景 widgetConfig 无效",
                502,
            )
        config_type = config["type"]
    if widget_type and config_type and widget_type != config_type:
        fail(
            "invalid_openmaic_widget",
            "OpenMAIC 互动场景 widget 类型互相冲突",
            502,
        )
    effective_type = str(widget_type or config_type) if widget_type or config_type else None
    has_embedded_html = isinstance(html, str) and bool(html.strip())
    has_interactive_controls = bool(
        has_embedded_html
        and re.search(
            r"<(?:button|input|select|textarea|canvas)\b",
            html,
            flags=re.IGNORECASE,
        )
    )
    validator = config_validator or _valid_sample_widget_config
    has_complete_interaction = bool(
        effective_type in required_widget_types
        and isinstance(config, Mapping)
        and validator(config, widget_type=effective_type)
        and _embedded_widget_config(html) == dict(config)
        and _html_has_productive_widget_interaction(
            html,
            widget_type=effective_type,
            config=config,
        )
    )
    return (
        effective_type,
        has_embedded_html,
        has_interactive_controls,
        has_complete_interaction,
    )


def _validate_professional_interactive_content(
    content: Mapping[str, Any],
    *,
    fail: Any,
    required_widget_types: frozenset[str],
) -> tuple[str | None, bool, bool, bool]:
    """Validate operability without duplicating OpenMAIC's widget schemas.

    OpenMAIC 1.0 owns the internal config and JavaScript implementation. Mira
    only checks the stable integration boundary: supported declared type,
    renderable HTML, real learner controls, an event binding, and an observable
    update. This intentionally avoids rejecting new official widget fields or
    equivalent JavaScript styles.
    """

    html = content.get("html")
    url = content.get("url")
    if html is not None and not isinstance(html, str):
        fail(
            "invalid_openmaic_interactive",
            "OpenMAIC 互动场景 html 格式无效",
            502,
        )
    if url is not None and not isinstance(url, str):
        fail(
            "invalid_openmaic_interactive",
            "OpenMAIC 互动场景 url 格式无效",
            502,
        )
    if not _nonempty_string(html) and not _nonempty_string(url):
        fail(
            "invalid_openmaic_interactive",
            "OpenMAIC 互动场景没有可渲染内容",
            502,
        )

    config = content.get("widgetConfig")
    config_type = config.get("type") if isinstance(config, Mapping) else None
    widget_type = content.get("widgetType")
    effective_type = str(widget_type or config_type) if widget_type or config_type else None
    has_embedded_html = isinstance(html, str) and bool(html.strip())
    has_interactive_controls = bool(
        has_embedded_html
        and re.search(
            r"<(?:button|input|select|textarea|canvas)\b",
            html,
            flags=re.IGNORECASE,
        )
    )
    executable = _executable_script_source(html) if isinstance(html, str) else ""
    has_complete_interaction = bool(
        effective_type in required_widget_types
        and isinstance(config, Mapping)
        and config
        and _valid_official_widget_value(config)
        and executable
        and not _javascript_has_provably_dead_reachability(executable)
        and _has_learner_event_binding(str(html), executable)
        and _has_observable_widget_update(_javascript_code_only(executable))
    )
    return (
        effective_type,
        has_embedded_html,
        has_interactive_controls,
        has_complete_interaction,
    )


def _embedded_widget_config(html: object) -> dict[str, Any] | None:
    if not isinstance(html, str):
        return None
    match = re.search(
        r"<script\b(?=[^>]*\btype\s*=\s*['\"]application/json['\"])(?=[^>]*\bid\s*=\s*['\"]widget-config['\"])[^>]*>([\s\S]*?)</script\s*>",
        html,
        flags=re.IGNORECASE,
    )
    if match is None:
        return None
    try:
        parsed = json.loads(match.group(1))
    except (TypeError, ValueError):
        return None
    return dict(parsed) if isinstance(parsed, Mapping) else None


def _valid_sample_widget_config(
    config: Mapping[str, Any], *, widget_type: str
) -> bool:
    if config.get("type") != widget_type or len(config) > 64:
        return False
    if widget_type == "simulation":
        return _valid_simulation_widget_config(config)
    if widget_type == "game":
        return _valid_game_widget_config(config)
    if widget_type == "visualization3d":
        return _valid_visualization3d_widget_config(config)
    if widget_type in {"diagram", "code"}:
        return _valid_formal_widget_config(config, widget_type=widget_type)
    return False


def _mapping_has_only(value: Mapping[str, Any], fields: set[str]) -> bool:
    return set(str(key) for key in value).issubset(fields)


def _valid_official_widget_value(value: Any, *, depth: int = 0) -> bool:
    """Bound OpenMAIC 1.0 widget extensions without deleting Pro semantics."""

    if depth > 5:
        return False
    if value is None or isinstance(value, bool):
        return True
    if _finite_number(value):
        return True
    if isinstance(value, str):
        return len(value) <= 2048
    if isinstance(value, list):
        return len(value) <= 128 and all(
            _valid_official_widget_value(item, depth=depth + 1)
            for item in value
        )
    if isinstance(value, Mapping):
        return len(value) <= 64 and all(
            isinstance(key, str)
            and re.fullmatch(r"[A-Za-z][A-Za-z0-9_-]{0,79}", key) is not None
            and _valid_official_widget_value(item, depth=depth + 1)
            for key, item in value.items()
        )
    return False


def _valid_formal_widget_config(
    config: Mapping[str, Any], *, widget_type: str
) -> bool:
    """Strict formal config grammar; unknown Provider fields fail closed."""

    if config.get("type") != widget_type:
        return False
    if widget_type == "diagram":
        return bool(
            _mapping_has_only(
                config,
                {"type", "diagramType", "description", "nodes", "edges", "revealOrder"},
            )
            and config.get("diagramType")
            in {"flowchart", "mindmap", "hierarchy", "system"}
            and _nonempty_string(config.get("description"))
            and isinstance(config.get("nodes"), list)
            and bool(config["nodes"])
            and isinstance(config.get("edges"), list)
            and _valid_official_widget_value(config)
        )
    if widget_type == "code":
        return bool(
            _mapping_has_only(
                config,
                {"type", "language", "description", "starterCode", "testCases", "hints", "solution"},
            )
            and config.get("language")
            in {"python", "javascript", "typescript", "java", "cpp"}
            and _nonempty_string(config.get("description"))
            and _nonempty_string(config.get("starterCode"))
            and isinstance(config.get("testCases"), list)
            and isinstance(config.get("hints"), list)
            and isinstance(config.get("solution"), str)
            and _valid_official_widget_value(config)
        )
    if widget_type == "simulation":
        return _valid_formal_simulation_widget_config(config)
    if widget_type == "game":
        return _valid_formal_game_widget_config(config)
    if widget_type == "visualization3d":
        return _valid_formal_visualization3d_widget_config(config)
    return False


def _valid_formal_simulation_widget_config(config: Mapping[str, Any]) -> bool:
    if not _mapping_has_only(
        config, {"type", "concept", "description", "variables", "presets"}
    ) or not _valid_simulation_widget_config(config):
        return False
    variables = config["variables"]
    bounds: dict[str, tuple[float, float]] = {}
    for variable in variables:
        if not _mapping_has_only(
            variable, {"name", "label", "min", "max", "default", "unit", "step"}
        ):
            return False
        if variable.get("step") is not None and (
            not _finite_number(variable.get("step"))
            or float(variable["step"]) <= 0
        ):
            return False
        bounds[str(variable["name"])] = (
            float(variable["min"]),
            float(variable["max"]),
        )
    for preset in config["presets"]:
        if not _mapping_has_only(preset, {"name", "variables"}):
            return False
        for name, value in preset["variables"].items():
            minimum, maximum = bounds[str(name)]
            if not minimum <= float(value) <= maximum:
                return False
    return True


def _valid_formal_game_widget_config(config: Mapping[str, Any]) -> bool:
    if not _mapping_has_only(
        config,
        {"type", "gameType", "description", "gameConfig", "scoring", "achievements"},
    ) or not _valid_game_widget_config(config):
        return False
    game = config["gameConfig"]
    scoring = config["scoring"]
    achievements = config["achievements"]
    if (
        not _mapping_has_only(
            game,
            {"controls", "targets", "initialConditions", "successCondition", "levels"},
        )
        or not _valid_official_widget_value(game)
        or not _valid_official_widget_value(scoring)
        or not _valid_official_widget_value(achievements)
    ):
        return False
    controls = [str(value) for value in game["controls"]]
    if len(set(controls)) != len(controls):
        return False
    target_ids: list[str] = []
    for target in game["targets"]:
        target_ids.append(str(target["id"]))
    if len(set(target_ids)) != len(target_ids):
        return False
    level_ids: list[str] = []
    for level in game["levels"]:
        if isinstance(level, str):
            continue
        if not isinstance(level, Mapping):
            return False
        if level.get("id") is not None:
            if not _bounded_identifier(level.get("id")):
                return False
            level_ids.append(str(level["id"]))
        if level.get("targetId") is not None and str(level["targetId"]) not in target_ids:
            return False
    if len(set(level_ids)) != len(level_ids):
        return False
    achievement_ids: list[str] = []
    for achievement in achievements:
        achievement_ids.append(str(achievement["id"]))
        if (
            achievement.get("targetId") is not None
            and str(achievement["targetId"]) not in target_ids
        ):
            return False
    return len(set(achievement_ids)) == len(achievement_ids)


def _valid_formal_visualization3d_widget_config(
    config: Mapping[str, Any]
) -> bool:
    if not _mapping_has_only(
        config,
        {
            "type", "visualizationType", "description", "objects",
            "interactions", "camera", "lighting", "presets",
        },
    ) or not _valid_visualization3d_widget_config(
        config
    ) or not _valid_official_widget_value(config):
        return False
    object_ids: list[str] = []
    transform_fields = {"x", "y", "z"}
    for item in config["objects"]:
        if not _mapping_has_only(
            item,
            {
                "id", "type", "name", "label", "position", "rotation",
                "scale", "color", "dimensions", "material", "animation",
                "children",
            },
        ):
            return False
        object_ids.append(str(item["id"]))
        for field in ("position", "rotation", "dimensions"):
            nested = item.get(field)
            if nested is not None and (
                not isinstance(nested, Mapping)
                or not _mapping_has_only(nested, transform_fields)
                or not all(_finite_number(value) for value in nested.values())
            ):
                return False
        scale = item.get("scale")
        if scale is not None and not (
            _finite_number(scale)
            or (
                isinstance(scale, Mapping)
                and _mapping_has_only(scale, transform_fields)
                and all(_finite_number(value) for value in scale.values())
            )
        ):
            return False
    if len(set(object_ids)) != len(object_ids):
        return False
    interaction_ids: list[str] = []
    for interaction in config["interactions"]:
        if not _mapping_has_only(
            interaction,
            {
                "id", "type", "target", "param", "action", "label",
                "min", "max", "default", "step",
            },
        ):
            return False
        if interaction.get("id") is not None:
            if not _bounded_identifier(interaction.get("id")):
                return False
            interaction_ids.append(str(interaction["id"]))
        if (
            interaction.get("target") is not None
            and str(interaction["target"]) != "camera"
            and str(interaction["target"]) not in object_ids
        ):
            return False
    return len(set(interaction_ids)) == len(interaction_ids)


def _valid_simulation_widget_config(config: Mapping[str, Any]) -> bool:
    variables = config.get("variables")
    presets = config.get("presets")
    if (
        not _nonempty_string(config.get("concept"))
        or not _nonempty_string(config.get("description"))
        or not isinstance(variables, list)
        or not 1 <= len(variables) <= 32
        or not isinstance(presets, list)
        or not 1 <= len(presets) <= 32
    ):
        return False
    names: set[str] = set()
    for variable in variables:
        if not isinstance(variable, Mapping):
            return False
        name = str(variable.get("name") or "").strip()
        minimum = variable.get("min")
        maximum = variable.get("max")
        default = variable.get("default")
        if (
            not _bounded_identifier(name)
            or name in names
            or not _nonempty_string(variable.get("label"))
            or not all(_finite_number(value) for value in (minimum, maximum, default))
            or not float(minimum) < float(maximum)
            or not float(minimum) <= float(default) <= float(maximum)
            or (
                variable.get("unit") is not None
                and not isinstance(variable.get("unit"), str)
            )
        ):
            return False
        names.add(name)
    return all(
        isinstance(preset, Mapping)
        and _nonempty_string(preset.get("name"))
        and isinstance(preset.get("variables"), Mapping)
        and bool(preset["variables"])
        and set(str(key) for key in preset["variables"]).issubset(names)
        and all(_finite_number(value) for value in preset["variables"].values())
        for preset in presets
    )


def _valid_game_widget_config(config: Mapping[str, Any]) -> bool:
    game = config.get("gameConfig")
    scoring = config.get("scoring")
    achievements = config.get("achievements")
    if (
        not _nonempty_string(config.get("gameType"))
        or not _nonempty_string(config.get("description"))
        or not isinstance(game, Mapping)
        or not isinstance(scoring, Mapping)
        or not isinstance(achievements, list)
        or not 1 <= len(achievements) <= 64
    ):
        return False
    controls = game.get("controls")
    targets = game.get("targets")
    initial = game.get("initialConditions")
    levels = game.get("levels")
    completion_points = scoring.get("completionPoints")
    return bool(
        isinstance(controls, list)
        and 1 <= len(controls) <= 64
        and all(_bounded_identifier(item) for item in controls)
        and isinstance(targets, list)
        and 1 <= len(targets) <= 64
        and all(
            isinstance(item, Mapping)
            and _bounded_identifier(item.get("id"))
            and _nonempty_string(item.get("type"))
            for item in targets
        )
        and isinstance(initial, Mapping)
        and bool(initial)
        and all(
            _finite_number(value) or isinstance(value, (str, bool))
            for value in initial.values()
        )
        and _nonempty_string(game.get("successCondition"))
        and isinstance(levels, list)
        and 1 <= len(levels) <= 64
        and all(isinstance(level, (str, Mapping)) and bool(level) for level in levels)
        and _finite_number(completion_points)
        and float(completion_points) > 0
        and all(
            isinstance(item, Mapping)
            and _bounded_identifier(item.get("id"))
            and _nonempty_string(item.get("name"))
            and _nonempty_string(item.get("description"))
            for item in achievements
        )
    )


def _valid_visualization3d_widget_config(config: Mapping[str, Any]) -> bool:
    objects = config.get("objects")
    interactions = config.get("interactions")
    return bool(
        _nonempty_string(config.get("visualizationType"))
        and _nonempty_string(config.get("description"))
        and isinstance(objects, list)
        and 1 <= len(objects) <= 128
        and all(
            isinstance(item, Mapping)
            and _bounded_identifier(item.get("id"))
            and _nonempty_string(item.get("type"))
            for item in objects
        )
        and isinstance(interactions, list)
        and 1 <= len(interactions) <= 64
        and all(
            isinstance(item, Mapping)
            and _nonempty_string(item.get("type"))
            and any(
                _nonempty_string(item.get(field))
                for field in ("target", "param", "action")
            )
            for item in interactions
        )
    )


def _html_has_productive_widget_interaction(
    html: str,
    *,
    widget_type: str,
    config: Mapping[str, Any],
) -> bool:
    executable = _executable_script_source(html)
    if (
        not executable
        or not _javascript_named_functions_are_immutable(executable)
        or _javascript_has_provably_dead_reachability(executable)
        or not _has_learner_event_binding(html, executable)
    ):
        return False
    if not _has_observable_widget_update(_javascript_code_only(executable)):
        return False
    if widget_type == "simulation":
        return _html_has_productive_simulation(html, executable, config)
    if widget_type == "game":
        return _html_has_productive_game(html, executable)
    if widget_type == "visualization3d":
        return _html_has_productive_3d(html, executable)
    if widget_type == "diagram":
        # OpenMAIC 1.0 diagrams are self-contained HTML widgets. The generic
        # checks above already prove a learner event reaches an observable DOM
        # update; requiring simulation/game-specific state would reject a real
        # clickable diagram even though it is fully operable.
        return True
    return False


def _executable_script_source(html: str) -> str:
    bodies: list[str] = []
    for match in re.finditer(
        r"<script\b([^>]*)>([\s\S]*?)</script\s*>",
        html,
        flags=re.IGNORECASE,
    ):
        attributes, body = match.groups()
        if re.search(
            r"\btype\s*=\s*['\"]application/json['\"]",
            attributes,
            flags=re.IGNORECASE,
        ):
            continue
        bodies.append(body)
    source = "\n".join(bodies)
    source = re.sub(r"/\*[\s\S]*?\*/", " ", source)
    source = re.sub(r"(^|\s)//[^\n\r]*", r"\1", source)
    return source.strip()


def _has_learner_event_binding(html: str, executable: str) -> bool:
    event_names = (
        "click|input|change|pointerdown|pointerup|mousedown|mouseup|"
        "touchstart|touchend|keydown|keyup|dragstart|drop"
    )
    for match in re.finditer(
        rf"\bon(?:{event_names})\s*=\s*(['\"])(.*?)\1",
        html,
        flags=re.IGNORECASE | re.DOTALL,
    ):
        handler = match.group(2).strip().rstrip(";").strip()
        if _handler_expression_is_productive(handler, executable):
            return True
    registrations = (
        rf"\.addEventListener\s*\(\s*['\"](?:{event_names})['\"]\s*,",
        rf"\.on(?:{event_names})\s*=",
    )
    for pattern in registrations:
        for match in re.finditer(pattern, executable, flags=re.IGNORECASE):
            if _registered_handler_is_productive(executable, match.end()):
                return True
    return False


def _registered_handler_is_productive(source: str, start: int) -> bool:
    tail = source[start:].lstrip()
    if tail.startswith("function"):
        brace = tail.find("{")
        body = _extract_braced_javascript(tail, brace)
        return bool(body is not None and _handler_body_is_productive(body, source))
    arrow_match = re.match(
        r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>",
        tail,
    )
    if arrow_match is not None:
        expression = tail[arrow_match.end() :].lstrip()
        if expression.startswith("{"):
            body = _extract_braced_javascript(expression, 0)
            return bool(body is not None and _handler_body_is_productive(body, source))
        return _handler_expression_is_productive(
            expression.split(")", 1)[0], source
        )
    name_match = re.match(r"([A-Za-z_$][\w$]*)", tail)
    return bool(
        name_match
        and _named_javascript_handler_is_productive(name_match.group(1), source)
    )


def _extract_braced_javascript(source: str, brace_start: int) -> str | None:
    if brace_start < 0 or brace_start >= len(source) or source[brace_start] != "{":
        return None
    depth = 0
    quote: str | None = None
    escaped = False
    for index in range(brace_start, min(len(source), brace_start + 20000)):
        char = source[index]
        if quote is not None:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in {"'", '"', "`"}:
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[brace_start + 1 : index]
    return None


def _named_javascript_function_definitions(
    source: str,
) -> list[tuple[str, str, bool]]:
    executable = _javascript_code_only(source)
    patterns = (
        (r"\bfunction\s+([A-Za-z_$][\w$]*)\s*\([^)]*\)\s*{", False),
        (
            r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
            r"function\s*\([^)]*\)\s*{",
            True,
        ),
        (
            r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
            r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*{",
            True,
        ),
        (
            r"\b(?:window\.)?([A-Za-z_$][\w$]*)\s*=\s*"
            r"function\s*\([^)]*\)\s*{",
            True,
        ),
    )
    definitions: list[tuple[str, str, bool]] = []
    for pattern, assignment_definition in patterns:
        for match in re.finditer(pattern, source):
            if re.fullmatch(
                pattern,
                executable[match.start() : match.end()],
            ) is None:
                continue
            body = _extract_braced_javascript(source, match.end() - 1)
            if body is not None:
                definitions.append(
                    (match.group(1), body, assignment_definition)
                )
    return definitions


def _named_javascript_function_bodies(source: str) -> dict[str, str]:
    bodies: dict[str, str] = {}
    for name, body, _assignment_definition in (
        _named_javascript_function_definitions(source)
    ):
        bodies.setdefault(name, body)
    return bodies


def _javascript_code_only(source: str) -> str:
    """Mask comments and literals so evidence tokens must be executable code."""

    output = list(source)
    index = 0
    state: str | None = None
    escaped = False
    previous_code = ""
    while index < len(source):
        char = source[index]
        following = source[index + 1] if index + 1 < len(source) else ""
        if state == "line_comment":
            if char == "\n":
                state = None
            else:
                output[index] = " "
            index += 1
            continue
        if state == "block_comment":
            output[index] = "\n" if char == "\n" else " "
            if char == "*" and following == "/":
                output[index + 1] = " "
                index += 2
                state = None
            else:
                index += 1
            continue
        if state in {"'", '"', "`", "regex"}:
            output[index] = "\n" if char == "\n" else " "
            terminator = "/" if state == "regex" else state
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == terminator:
                state = None
            index += 1
            continue
        if char == "/" and following == "/":
            output[index] = output[index + 1] = " "
            index += 2
            state = "line_comment"
            continue
        if char == "/" and following == "*":
            output[index] = output[index + 1] = " "
            index += 2
            state = "block_comment"
            continue
        if char in {"'", '"', "`"}:
            output[index] = " "
            state = char
            index += 1
            continue
        if char == "/" and (not previous_code or previous_code in "([{,:;=!?&|"):
            output[index] = " "
            state = "regex"
            index += 1
            continue
        if not char.isspace():
            previous_code = char
        index += 1
    return "".join(output)


def _javascript_has_provably_dead_reachability(source: str) -> bool:
    """Reject formal widget evidence hidden behind statically dead control flow.

    This is deliberately a fail-closed policy, not a general JavaScript
    interpreter.  The formal generator does not need constant-false branches
    or statements after an unconditional terminal.  Rejecting those constructs
    prevents the reachability scanner from treating a named registration call
    as executable merely because its identifier appears in source text.  The
    literal/comment mask keeps decoy text out of this policy, while dynamic
    conditions remain permitted.
    """

    executable = _javascript_code_only(source)
    false_atom = r"(?:false|null|undefined|0(?:\.0*)?)"
    for conditional in re.finditer(
        r"\bif\s*\(", executable, flags=re.IGNORECASE
    ):
        open_parenthesis = executable.find("(", conditional.start())
        close_parenthesis = _javascript_matching_parenthesis(
            executable, open_parenthesis
        )
        if close_parenthesis is None:
            return True
        condition = executable[open_parenthesis + 1 : close_parenthesis].strip()
        while condition.startswith("("):
            grouped_end = _javascript_matching_parenthesis(
                condition, 0, maximum=len(condition) + 1
            )
            if grouped_end != len(condition) - 1:
                break
            condition = condition[1:-1].strip()
        if re.fullmatch(
            rf"(?:true|{false_atom})", condition, flags=re.IGNORECASE
        ):
            return True

    dead_literal_patterns = (
        rf"(?<![A-Za-z0-9_$.]){false_atom}(?![A-Za-z0-9_$.])\s*&&",
        r"(?<![A-Za-z0-9_$.])true(?![A-Za-z0-9_$.])\s*\|\|",
        rf"(?<![A-Za-z0-9_$.]){false_atom}(?![A-Za-z0-9_$.])\s*\?",
    )
    for pattern in dead_literal_patterns:
        for literal in re.finditer(pattern, executable, flags=re.IGNORECASE):
            if _javascript_literal_starts_operand(executable, literal.start()):
                return True

    depth_before: list[int] = []
    depth = 0
    for char in executable:
        depth_before.append(depth)
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)

    for terminal in re.finditer(
        r"\b(?:return|throw)\b", executable, flags=re.IGNORECASE
    ):
        if _javascript_terminal_is_conditionally_guarded(
            executable, terminal.start()
        ):
            continue
        statement_end = _javascript_terminal_statement_end(
            executable, terminal.end()
        )
        terminal_depth = depth_before[terminal.start()]
        for index in range(statement_end, len(executable)):
            current_depth = depth_before[index]
            if current_depth < terminal_depth:
                break
            char = executable[index]
            if current_depth == terminal_depth:
                if char == "}":
                    break
                if not char.isspace() and char != ";":
                    return True
    return False


def _javascript_literal_starts_operand(executable: str, start: int) -> bool:
    prefix = executable[:start].rstrip()
    if not prefix:
        return True
    if prefix.endswith("=>"):
        return True
    if re.search(r"(?:===|!==|==|!=|<=|>=|<|>)$", prefix):
        return False
    if prefix[-1] in "([{,:;?=&|}":
        return True
    return bool(
        re.search(r"\b(?:return|throw|case|yield)\s*$", prefix)
    )


def _javascript_matching_open_parenthesis(
    executable: str, close: int, *, maximum: int = 2048
) -> int | None:
    if close < 0 or close >= len(executable) or executable[close] != ")":
        return None
    depth = 0
    stop = max(-1, close - maximum)
    for index in range(close, stop, -1):
        char = executable[index]
        if char == ")":
            depth += 1
        elif char == "(":
            depth -= 1
            if depth == 0:
                return index
    return None


def _javascript_terminal_is_conditionally_guarded(
    executable: str, start: int
) -> bool:
    index = start - 1
    while index >= 0 and executable[index].isspace():
        index -= 1
    if index >= 0 and executable[index] == ".":
        return True
    if index >= 0 and executable[index] == ")":
        open_parenthesis = _javascript_matching_open_parenthesis(
            executable, index
        )
        if open_parenthesis is not None:
            prefix = executable[:open_parenthesis].rstrip()
            if re.search(r"\b(?:if|while|for|with)\s*$", prefix):
                return True
    prefix = executable[:start].rstrip()
    return re.search(r"\belse\s*$", prefix) is not None


def _javascript_terminal_statement_end(executable: str, start: int) -> int:
    parenthesis_depth = 0
    bracket_depth = 0
    object_depth = 0
    for index in range(start, len(executable)):
        char = executable[index]
        if char == "(":
            parenthesis_depth += 1
        elif char == ")" and parenthesis_depth:
            parenthesis_depth -= 1
        elif char == "[":
            bracket_depth += 1
        elif char == "]" and bracket_depth:
            bracket_depth -= 1
        elif char == "{" and not parenthesis_depth and not bracket_depth:
            object_depth += 1
        elif char == "}" and not parenthesis_depth and not bracket_depth:
            if object_depth:
                object_depth -= 1
            else:
                return index
        elif (
            char in {";", "\n", "\r"}
            and not parenthesis_depth
            and not bracket_depth
            and not object_depth
        ):
            return index + 1
    return len(executable)


def _javascript_brace_depth_at(executable: str, index: int) -> int:
    depth = 0
    for char in executable[: max(0, index)]:
        if char == "{":
            depth += 1
        elif char == "}":
            depth = max(0, depth - 1)
    return depth


def _javascript_matching_parenthesis(
    executable: str, start: int, *, maximum: int = 2048
) -> int | None:
    if start < 0 or start >= len(executable) or executable[start] != "(":
        return None
    depth = 0
    stop = min(len(executable), start + maximum)
    for index in range(start, stop):
        char = executable[index]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
            if depth == 0:
                return index
    return None


def _javascript_has_named_concise_arrow(source: str) -> bool:
    executable = _javascript_code_only(source)
    for declaration in re.finditer(
        r"\b(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*",
        executable,
    ):
        index = declaration.end()
        while index < len(executable) and executable[index].isspace():
            index += 1
        if executable.startswith("async", index) and (
            index + 5 == len(executable)
            or not re.match(r"[A-Za-z0-9_$]", executable[index + 5])
        ):
            index += 5
            while index < len(executable) and executable[index].isspace():
                index += 1
        if index < len(executable) and executable[index] == "(":
            close = _javascript_matching_parenthesis(executable, index)
            if close is None:
                return True
            index = close + 1
        else:
            parameter = re.match(r"[A-Za-z_$][\w$]*", executable[index:])
            if parameter is None:
                continue
            index += parameter.end()
        while index < len(executable) and executable[index].isspace():
            index += 1
        if not executable.startswith("=>", index):
            continue
        index += 2
        while index < len(executable) and executable[index].isspace():
            index += 1
        if index >= len(executable) or executable[index] != "{":
            return True
    return False


def _javascript_named_functions_are_immutable(source: str) -> bool:
    executable = _javascript_code_only(source)
    if _javascript_has_named_concise_arrow(executable):
        return False
    definitions = _named_javascript_function_definitions(source)
    names = [name for name, _body, _assigned in definitions]
    if len(names) != len(set(names)):
        return False
    for name, _body, assignment_definition in definitions:
        assignments = re.findall(
            rf"\b{re.escape(name)}\s*(?:=(?!=|>)|\+=|-=|\*=|/=|%=|"
            r"\+\+|--|\|\|=|&&=|\?\?=)",
            executable,
        )
        if len(assignments) != (1 if assignment_definition else 0):
            return False
    return True


def _javascript_identity_is_unique_const(source: str, name: str) -> bool:
    executable = _javascript_code_only(source)
    declarations = re.findall(
        rf"\b(const|let|var)\s+{re.escape(name)}\b", executable
    )
    if declarations != ["const"]:
        return False
    assignments = re.findall(
        rf"\b{re.escape(name)}\s*(?:=(?!=|>)|\+=|-=|\*=|/=|%=|"
        r"\+\+|--|\|\|=|&&=|\?\?=)",
        executable,
    )
    if len(assignments) != 1:
        return False
    parameter_patterns = (
        rf"\bfunction\b[^(){{}}]*\([^)]*\b{re.escape(name)}\b[^)]*\)",
        rf"\([^)]*\b{re.escape(name)}\b[^)]*\)\s*=>",
        rf"\b{re.escape(name)}\s*=>",
        rf"\bcatch\s*\(\s*{re.escape(name)}\b",
    )
    return not any(re.search(pattern, executable) for pattern in parameter_patterns)


def _javascript_top_level_source(source: str) -> str:
    spans: list[tuple[int, int]] = []
    patterns = (
        r"\bfunction\s+[A-Za-z_$][\w$]*\s*\([^)]*\)\s*{",
        r"\b(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*function\s*\([^)]*\)\s*{",
        r"\b(?:const|let|var)\s+[A-Za-z_$][\w$]*\s*=\s*(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*{",
        r"\b(?:window\.)?[A-Za-z_$][\w$]*\s*=\s*function\s*\([^)]*\)\s*{",
    )
    for pattern in patterns:
        for match in re.finditer(pattern, source):
            body = _extract_braced_javascript(source, match.end() - 1)
            if body is not None:
                spans.append((match.start(), match.end() + len(body) + 1))
    result = source
    for start, end in sorted(spans, reverse=True):
        result = result[:start] + (" " * (end - start)) + result[end:]
    return result


def _javascript_reachable_source(
    entry: str, named_bodies: Mapping[str, str]
) -> str:
    executable_entry = _javascript_code_only(_javascript_top_level_source(entry))
    reachable = [executable_entry]
    pending = list(
        dict.fromkeys(
            re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", executable_entry)
        )
    )
    visited: set[str] = set()
    while pending and len(visited) < 64:
        name = pending.pop(0)
        if name in visited or name not in named_bodies:
            continue
        visited.add(name)
        body = _javascript_code_only(
            _javascript_top_level_source(named_bodies[name])
        )
        reachable.append(body)
        pending.extend(
            called
            for called in re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", body)
            if called not in visited
        )
    return "\n".join(reachable)


def _javascript_reachable_raw_scopes(source: str) -> list[str]:
    """Return top-level and actually called function scopes, preserving offsets."""

    named_bodies = _named_javascript_function_bodies(source)
    top_level = _javascript_top_level_source(source)
    scopes = [top_level]
    pending = list(
        dict.fromkeys(
            re.findall(
                r"\b([A-Za-z_$][\w$]*)\s*\(",
                _javascript_code_only(top_level),
            )
        )
    )
    visited: set[str] = set()
    while pending and len(visited) < 64:
        name = pending.pop(0)
        if name in visited or name not in named_bodies:
            continue
        visited.add(name)
        body = _javascript_top_level_source(named_bodies[name])
        scopes.append(body)
        pending.extend(
            called
            for called in re.findall(
                r"\b([A-Za-z_$][\w$]*)\s*\(",
                _javascript_code_only(body),
            )
            if called not in visited
        )
    return scopes


def _javascript_scope_dom_bindings(scope: str) -> dict[str, str]:
    """Return executable ``getElementById`` bindings from one reachable scope.

    The raw source is needed to recover the string literal target, while the
    same-length executable mask proves the declaration is code rather than a
    token embedded in a string or comment.  Callers supply a scope with nested
    function declarations already removed, so an uncalled local declaration
    cannot become page evidence.
    """

    executable = _javascript_code_only(scope)
    pattern = re.compile(
        r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*"
        r"document\.getElementById\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
    )
    bindings: dict[str, str] = {}
    for match in pattern.finditer(scope):
        code_fragment = executable[match.start() : match.end()]
        if (
            _javascript_brace_depth_at(executable, match.start()) != 0
            or not code_fragment.lstrip().startswith("const ")
            or re.fullmatch(
            r"\b(?:const|let|var)\s+"
            + re.escape(match.group(1))
            + r"\s*=\s*document\.getElementById\s*\(\s*\)",
            code_fragment,
            )
            is None
        ):
            continue
        if _javascript_identity_is_unique_const(scope, match.group(1)):
            bindings[match.group(1)] = match.group(2)
    return bindings


def _javascript_top_level_dom_bindings(source: str) -> dict[str, str]:
    return _javascript_scope_dom_bindings(_javascript_top_level_source(source))


def _registered_event_handler_bodies(
    source: str, *, event_pattern: str
) -> list[str]:
    return [
        body
        for _receiver_id, body in _registered_event_handler_records(
            source, event_pattern=event_pattern
        )
    ]


def _registered_event_handler_records(
    source: str, *, event_pattern: str
) -> list[tuple[str | None, str]]:
    named_bodies = _named_javascript_function_bodies(source)
    scopes = _javascript_reachable_raw_scopes(source)
    global_dom_bindings = _javascript_scope_dom_bindings(scopes[0])
    handlers: list[tuple[str | None, str]] = []
    for scope in scopes:
        executable = _javascript_code_only(scope)
        dom_bindings = dict(global_dom_bindings)
        dom_bindings.update(_javascript_scope_dom_bindings(scope))
        for match in re.finditer(
            rf"\.addEventListener\s*\(\s*['\"](?:{event_pattern})['\"]\s*,",
            scope,
            flags=re.IGNORECASE,
        ):
            if (
                _javascript_brace_depth_at(executable, match.start()) != 0
                or re.fullmatch(
                    r"\.addEventListener\s*\(\s*,",
                    executable[match.start() : match.end()],
                    flags=re.IGNORECASE,
                )
                is None
            ):
                continue
            prefix_start = max(0, match.start() - 512)
            prefix = scope[prefix_start : match.start()]
            receiver_match = re.search(
                r"(?:document\.getElementById\s*\(\s*['\"]([^'\"]+)['\"]\s*\)|"
                r"([A-Za-z_$][\w$]*))\s*$",
                prefix,
            )
            receiver_id: str | None = None
            if receiver_match is not None:
                receiver_start = prefix_start + receiver_match.start()
                receiver_code = executable[receiver_start : match.start()]
                if receiver_match.group(1) is not None:
                    if re.fullmatch(
                        r"document\.getElementById\s*\(\s*\)\s*",
                        receiver_code,
                    ) is not None:
                        receiver_id = receiver_match.group(1)
                elif re.fullmatch(
                    re.escape(str(receiver_match.group(2))) + r"\s*",
                    receiver_code,
                ) is not None:
                    receiver_id = dom_bindings.get(receiver_match.group(2))
            tail = scope[match.end() :].lstrip()
            if tail.startswith("function"):
                brace = tail.find("{")
                body = _extract_braced_javascript(tail, brace)
                if body is not None:
                    handlers.append((receiver_id, body))
                continue
            arrow = re.match(
                r"(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>\s*{", tail
            )
            if arrow is not None:
                body = _extract_braced_javascript(tail, arrow.end() - 1)
                if body is not None:
                    handlers.append((receiver_id, body))
                continue
            named = re.match(r"([A-Za-z_$][\w$]*)", tail)
            if named is not None and named.group(1) in named_bodies:
                handlers.append((receiver_id, named_bodies[named.group(1)]))
    if event_pattern.casefold() == "message":
        for scope in scopes:
            executable = _javascript_code_only(scope)
            for match in re.finditer(
                r"\.onmessage\s*=", scope, flags=re.IGNORECASE
            ):
                if (
                    _javascript_brace_depth_at(executable, match.start()) != 0
                    or re.fullmatch(
                        r"\.onmessage\s*=",
                        executable[match.start() : match.end()],
                        flags=re.IGNORECASE,
                    )
                    is None
                ):
                    continue
                tail = scope[match.end() :].lstrip()
                arrow = re.match(
                    r"(?:function\s*\([^)]*\)|\([^)]*\)|[A-Za-z_$][\w$]*)\s*(?:=>)?\s*{",
                    tail,
                )
                if arrow is not None:
                    body = _extract_braced_javascript(tail, arrow.end() - 1)
                    if body is not None:
                        handlers.append((None, body))
    return handlers


def _handler_expression_is_productive(expression: str, source: str) -> bool:
    normalized = expression.strip().rstrip(";").strip()
    if not normalized or normalized.casefold() in {
        "return",
        "return false",
        "false",
        "void(0)",
    }:
        return False
    if _handler_body_is_productive(normalized, source):
        return True
    calls = re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", normalized)
    return any(_named_javascript_handler_is_productive(name, source) for name in calls)


def _named_javascript_handler_is_productive(name: str, source: str) -> bool:
    escaped = re.escape(name)
    patterns = (
        rf"\bfunction\s+{escaped}\s*\([^)]*\)\s*{{",
        rf"\b(?:const|let|var)\s+{escaped}\s*=\s*(?:function\s*\([^)]*\)|(?:\([^)]*\)|[A-Za-z_$][\w$]*)\s*=>)\s*{{",
        rf"\b(?:window\.)?{escaped}\s*=\s*function\s*\([^)]*\)\s*{{",
    )
    for pattern in patterns:
        match = re.search(pattern, source)
        if match is None:
            continue
        body = _extract_braced_javascript(source, match.end() - 1)
        if body is not None and _handler_body_is_productive(body, source):
            return True
    return False


def _handler_body_is_productive(body: str, source: str) -> bool:
    if _has_observable_widget_update(body):
        return True
    state_update = re.search(
        r"\b(?:score|points|level|progress|gameState|gameOver|won|lost|rotation|value)\b\s*(?:=|\+=|-=|\+\+|--)",
        body,
        flags=re.IGNORECASE,
    )
    if not state_update:
        return False
    calls = re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", body)
    return any(
        (
            name.casefold().startswith(
                ("render", "update", "draw", "refresh", "animate")
            )
            or name.casefold().endswith("loop")
        )
        and _named_javascript_handler_is_productive(name, source)
        for name in calls
    )


def _has_observable_widget_update(executable: str) -> bool:
    patterns = (
        r"\.(?:textContent|innerText|innerHTML|value)\s*=",
        r"\.style(?:\.[A-Za-z_$][\w$]*|\[[^\]]+\])\s*=",
        r"\.classList\.(?:add|remove|toggle|replace)\s*\(",
        r"\.setAttribute\s*\(",
        r"\.dataset(?:\.[A-Za-z_$][\w$]*|\[[^\]]+\])\s*=",
        r"\.(?:clearRect|fillRect|strokeRect|drawImage|fillText|strokeText|arc|lineTo|drawArrays|drawElements|render)\s*\(",
        r"\.(?:rotation|position|scale)\.[xyz]\s*(?:=|\+=|-=|\*=|/=)",
        r"\.(?:position|scale)\.(?:set|add|sub|multiplyScalar|setScalar)\s*\(",
    )
    return any(re.search(pattern, executable) for pattern in patterns)


def _html_has_productive_simulation(
    html: str, executable: str, config: Mapping[str, Any]
) -> bool:
    visible_targets = _html_widget_targets(html)
    operable_targets = _html_operable_widget_targets(html)
    variables = config.get("variables")
    names = [
        str(item["name"])
        for item in variables
        if isinstance(item, Mapping) and _bounded_identifier(item.get("name"))
    ] if isinstance(variables, list) else []
    has_variable_control = bool(
        re.search(
            r"<(?:input|select)\b[^>]*(?:type\s*=\s*['\"]?(?:range|number)|data-var\s*=|id\s*=)",
            html,
            flags=re.IGNORECASE,
        )
        and any(re.search(rf"\b{re.escape(name)}\b", html) for name in names)
    )
    has_output = any(
        re.search(
            r"(?:output|result|status|display|value|canvas|svg)",
            target,
            flags=re.IGNORECASE,
        )
        for target in visible_targets
    )
    named_bodies = _named_javascript_function_bodies(executable)
    control_ids: set[str] = set()
    for name in names:
        for match in re.finditer(
            rf"<(?:input|select)\b(?=[^>]*\bdata-var\s*=\s*['\"]{re.escape(name)}['\"])(?=[^>]*\bid\s*=\s*['\"]([^'\"]+)['\"])[^>]*>",
            html,
            flags=re.IGNORECASE,
        ):
            if match.group(1) in operable_targets:
                control_ids.add(match.group(1))
    input_scopes = [
        _javascript_reachable_source(body, named_bodies)
        for receiver_id, body in _registered_event_handler_records(
            executable, event_pattern="input|change"
        )
        if receiver_id in control_ids
    ]
    productive_input = any(
        re.search(r"\.(?:value|checked)\b", scope)
        and _has_observable_widget_update(scope)
        and (
            re.search(
                r"\.(?:textContent|innerText|innerHTML|value)\s*=", scope
            )
            or re.search(
                r"\.(?:clearRect|fillRect|strokeRect|drawImage|fillText|strokeText|arc|lineTo)\s*\(",
                scope,
            )
        )
        for scope in input_scopes
    )
    return bool(has_variable_control and has_output and productive_input)


def _html_has_productive_game(html: str, executable: str) -> bool:
    visible_targets = _html_widget_targets(html)
    operable_targets = _html_operable_widget_targets(html)
    has_feedback_surface = any(
        re.search(
            r"(?:score|points|level|progress|status|result|win|lose|canvas)",
            target,
            flags=re.IGNORECASE,
        )
        for target in visible_targets
    )
    named_bodies = _named_javascript_function_bodies(executable)
    embedded = _embedded_widget_config(html)
    game_config = embedded.get("gameConfig") if isinstance(embedded, Mapping) else None
    raw_controls = game_config.get("controls") if isinstance(game_config, Mapping) else None
    control_ids = {
        str(value)
        for value in (raw_controls if isinstance(raw_controls, list) else [])
        if _bounded_identifier(value) and str(value) in operable_targets
    }
    learner_scopes = [
        _javascript_reachable_source(body, named_bodies)
        for receiver_id, body in _registered_event_handler_records(
            executable,
            event_pattern=(
                "click|input|change|pointerdown|pointerup|mousedown|mouseup|"
                "touchstart|touchend|keydown|keyup|dragstart|drop"
            ),
        )
        if receiver_id in control_ids
    ]
    productive_handler = any(
        (
            re.search(
                r"\b(?:score|points|level|progress|gameState|gameOver|won|lost|win|lose)\b\s*(?:\+=|-=|\+\+|--|=\s*(?:\b(?:score|points|level|progress)\b\s*[+\-*/]|Math\.))",
                scope,
                flags=re.IGNORECASE,
            )
            or re.search(
                r"\b(?:setScore|setLevel|advanceLevel|completeLevel|endGame|winGame|loseGame)\s*\(",
                scope,
                flags=re.IGNORECASE,
            )
        )
        and re.search(r"\brequestAnimationFrame\s*\(", scope)
        and _has_observable_widget_update(scope)
        for scope in learner_scopes
    )
    return bool(has_feedback_surface and productive_handler)


def _html_has_productive_3d(html: str, executable: str) -> bool:
    named_bodies = _named_javascript_function_bodies(executable)
    reachable_scopes = _javascript_reachable_raw_scopes(executable)
    top_level_scope = reachable_scopes[0]
    page_scope = _javascript_code_only(top_level_scope)
    visible_targets = _html_widget_targets(html)
    operable_targets = _html_operable_widget_targets(html)
    learner_bodies = [
        body
        for receiver_id, body in _registered_event_handler_records(
            executable,
            event_pattern=(
                "click|input|change|pointerdown|pointerup|mousedown|mouseup|"
                "touchstart|touchend|keydown|keyup|dragstart|drop"
            ),
        )
        if receiver_id in operable_targets
    ]
    learner_scope = "\n".join(
        _javascript_reachable_source(body, named_bodies)
        for body in learner_bodies
    )
    global_dom_bindings = _javascript_scope_dom_bindings(top_level_scope)
    renderer_names = {
        match.group(1)
        for match in re.finditer(
            r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*new\s+"
            r"THREE\.WebGLRenderer\s*\(",
            page_scope,
        )
        if _javascript_brace_depth_at(page_scope, match.start()) == 0
    }
    scene_names = {
        match.group(1)
        for match in re.finditer(
            r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*new\s+"
            r"THREE\.Scene\s*\(",
            page_scope,
        )
        if _javascript_brace_depth_at(page_scope, match.start()) == 0
    }
    camera_names = {
        match.group(1)
        for match in re.finditer(
            r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*new\s+"
            r"THREE\.[A-Za-z]+Camera\s*\(",
            page_scope,
        )
        if _javascript_brace_depth_at(page_scope, match.start()) == 0
    }
    gl_names = {
        match.group(1)
        for match in re.finditer(
            r"\bconst\s+([A-Za-z_$][\w$]*)\s*=\s*"
            r"[^;\n]*\.getContext\s*\(",
            page_scope,
        )
        if _javascript_brace_depth_at(page_scope, match.start()) == 0
    }
    identity_names = (
        renderer_names
        | scene_names
        | camera_names
        | gl_names
        | set(global_dom_bindings)
    )
    if not all(
        _javascript_identity_is_unique_const(executable, name)
        for name in identity_names
    ):
        return False
    visible_renderers: set[str] = set()
    # Formal 3D identity is intentionally page-scoped.  Joining JavaScript
    # identifiers across called function scopes lets a local decoy renderer
    # make a different, off-DOM top-level renderer appear visible.
    for scope in (top_level_scope,):
        scope_code = _javascript_code_only(scope)
        dom_bindings = dict(global_dom_bindings)
        dom_bindings.update(_javascript_scope_dom_bindings(scope))
        for renderer in renderer_names:
            initializer_pattern = re.compile(
                rf"\b{re.escape(renderer)}\s*=\s*new\s+THREE\.WebGLRenderer\s*"
                rf"\(\s*\{{([\s\S]{{0,512}}?)\}}\s*\)"
            )
            for initializer in initializer_pattern.finditer(scope):
                if _javascript_brace_depth_at(
                    scope_code, initializer.start()
                ) != 0:
                    continue
                header_code = scope_code[
                    initializer.start() : initializer.start(1)
                ]
                if re.fullmatch(
                    rf"\b{re.escape(renderer)}\s*=\s*new\s+"
                    r"THREE\.WebGLRenderer\s*\(\s*\{",
                    header_code,
                ) is None:
                    continue
                options = initializer.group(1)
                options_code = scope_code[
                    initializer.start(1) : initializer.end(1)
                ]
                canvas_id: str | None = None
                for direct in re.finditer(
                    r"\bcanvas\s*:\s*document\.getElementById\s*"
                    r"\(\s*['\"]([^'\"]+)['\"]\s*\)",
                    options,
                ):
                    if re.fullmatch(
                        r"\bcanvas\s*:\s*document\.getElementById\s*"
                        r"\(\s*\)",
                        options_code[direct.start() : direct.end()],
                    ) is not None:
                        canvas_id = direct.group(1)
                        break
                if canvas_id is None:
                    variable = re.search(
                        r"\bcanvas\s*(?::\s*([A-Za-z_$][\w$]*))?"
                        r"\s*(?:,|$)",
                        options_code,
                    )
                    if variable is not None:
                        canvas_id = dom_bindings.get(
                            variable.group(1) or "canvas"
                        )
                if canvas_id in visible_targets:
                    visible_renderers.add(renderer)
            mount_pattern = re.compile(
                r"document\.getElementById\s*\(\s*['\"]([^'\"]+)['\"]\s*\)"
                rf"\s*\.appendChild\s*\(\s*{re.escape(renderer)}\.domElement\s*\)"
            )
            for mount in mount_pattern.finditer(scope):
                if (
                    _javascript_brace_depth_at(scope_code, mount.start()) == 0
                    and re.fullmatch(
                    r"document\.getElementById\s*\(\s*\)"
                    rf"\s*\.appendChild\s*\(\s*{re.escape(renderer)}\.domElement\s*\)",
                    scope_code[mount.start() : mount.end()],
                    )
                    is not None
                    and mount.group(1) in visible_targets
                ):
                    visible_renderers.add(renderer)
    visible_gl_names: set[str] = set()
    for scope in (top_level_scope,):
        scope_code = _javascript_code_only(scope)
        dom_bindings = dict(global_dom_bindings)
        dom_bindings.update(_javascript_scope_dom_bindings(scope))
        for gl in gl_names:
            for binding in re.finditer(
                rf"\b{re.escape(gl)}\s*=\s*"
                r"([A-Za-z_$][\w$]*)\.getContext\s*\(",
                scope_code,
            ):
                if (
                    _javascript_brace_depth_at(scope_code, binding.start()) == 0
                    and dom_bindings.get(binding.group(1)) in visible_targets
                ):
                    visible_gl_names.add(gl)
    has_canvas = bool(visible_renderers or visible_gl_names)
    has_webgl = bool(renderer_names or gl_names)
    scene_objects: set[str] = set()
    for scene_name in scene_names:
        scene_objects.update(
            match.group(1)
            for match in re.finditer(
                rf"\b{re.escape(scene_name)}\.add\s*\(\s*([A-Za-z_$][\w$]*)\s*\)",
                page_scope,
            )
            if _javascript_brace_depth_at(page_scope, match.start()) == 0
        )
    if not all(
        _javascript_identity_is_unique_const(executable, name)
        for name in scene_objects
    ):
        return False
    three_render = any(
        re.search(
            rf"\b{re.escape(renderer)}\.render\s*\(\s*{re.escape(scene)}\s*,\s*{re.escape(camera)}\s*\)",
            learner_scope,
        )
        for renderer in visible_renderers
        for scene in scene_names
        for camera in camera_names
    )
    webgl_render = any(
        re.search(
            rf"\b{re.escape(gl)}\.(?:drawArrays|drawElements)\s*\(",
            learner_scope,
        )
        for gl in visible_gl_names
    )
    has_direct_webgl_scene = any(
        _javascript_brace_depth_at(page_scope, match.start()) == 0
        for match in re.finditer(
            r"\.(?:createShader|createProgram|bufferData)\s*\(", page_scope
        )
    )
    has_scene = bool(scene_names or has_direct_webgl_scene)
    transformed_scene_object = any(
        re.search(
            rf"\b{re.escape(object_name)}\.(?:rotation|position|scale)\.[xyz]\s*(?:=|\+=|-=|\*=|/=)|"
            rf"\b{re.escape(object_name)}\.(?:rotateX|rotateY|rotateZ|setScalar)\s*\(|"
            rf"\b{re.escape(object_name)}\.(?:position|scale)\.(?:set|add|sub|multiplyScalar|setScalar)\s*\(",
            learner_scope,
        )
        for object_name in scene_objects
    )
    direct_webgl_transform = bool(
        webgl_render
        and re.search(
            r"\b(?:rotation|angle|cameraX|cameraY|cameraZ|zoom)\b\s*(?:=|\+=|-=|\*=|/=)",
            learner_scope,
            flags=re.IGNORECASE,
        )
    )
    return bool(
        has_canvas
        and has_webgl
        and (three_render or webgl_render)
        and has_scene
        and (transformed_scene_object or direct_webgl_transform)
        and bool(learner_bodies)
    )


def _has_live_3d_learner_transform(executable: str) -> bool:
    transform = re.compile(
        r"\.(?:rotation|position|scale)\.[xyz]\s*(?:=|\+=|-=|\*=|/=)|"
        r"\.(?:rotateX|rotateY|rotateZ|setScalar)\s*\(|"
        r"\.(?:position|scale)\.(?:set|add|sub|multiplyScalar|setScalar)\s*\("
    )
    event_names = (
        "click|input|change|pointerdown|pointerup|mousedown|mouseup|"
        "touchstart|touchend|keydown|keyup|dragstart|drop"
    )
    for match in re.finditer(
        rf"\.addEventListener\s*\(\s*['\"](?:{event_names})['\"]\s*,",
        executable,
        flags=re.IGNORECASE,
    ):
        tail = executable[match.end() :].lstrip()
        brace = tail.find("{")
        body = _extract_braced_javascript(tail, brace)
        if body is not None and transform.search(body):
            return True
    return False


def _validate_pbl_content(content: Mapping[str, Any], *, fail: Any) -> str | None:
    project = content.get("projectV2")
    legacy = content.get("projectConfig")
    if project is not None and not _valid_pbl_project(project):
        fail(
            "invalid_openmaic_pbl",
            "OpenMAIC PBL projectV2 结构无效",
            502,
        )
    if legacy is not None and not isinstance(legacy, dict):
        fail(
            "invalid_openmaic_pbl",
            "OpenMAIC PBL projectConfig 结构无效",
            502,
        )
    if _runnable_pbl_project(project):
        return "projectV2-runnable"
    if _runnable_legacy_pbl(legacy):
        return "legacy-runnable"
    return None


def _valid_pbl_project(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    required_arrays = (
        "tags",
        "milestones",
        "roles",
        "submissions",
        "evaluations",
        "threads",
        "engagementEvents",
    )
    if (
        value.get("uiPhase") not in {"hero", "generating", "workspace", "completed"}
        or not isinstance(value.get("title"), str)
        or not isinstance(value.get("description"), str)
        or not isinstance(value.get("language"), str)
        or not isinstance(value.get("proficiency"), str)
        or value.get("status")
        not in {"designing", "review", "active", "completed", "archived"}
        or not isinstance(value.get("createdAt"), str)
        or not isinstance(value.get("updatedAt"), str)
        or any(not isinstance(value.get(field), list) for field in required_arrays)
    ):
        return False
    if any(not isinstance(item, dict) for item in value["roles"]):
        return False
    if any(
        not isinstance(milestone, dict)
        or not isinstance(milestone.get("microtasks"), list)
        or any(not isinstance(item, dict) for item in milestone["microtasks"])
        for milestone in value["milestones"]
    ):
        return False
    return not any(
        not isinstance(thread, dict)
        or not isinstance(thread.get("messages"), list)
        for thread in value["threads"]
    )


def _runnable_pbl_project(value: object) -> bool:
    if not _valid_pbl_project(value):
        return False
    project = value
    assert isinstance(project, dict)
    has_instructor = any(
        role.get("type") == "instructor"
        and _nonempty_string(role.get("id"))
        and isinstance(role.get("name"), str)
        for role in project["roles"]
    )
    return bool(project["milestones"]) and has_instructor and all(
        bool(milestone["microtasks"])
        and all(
            _nonempty_string(task.get("id"))
            and isinstance(task.get("title"), str)
            for task in milestone["microtasks"]
        )
        for milestone in project["milestones"]
    )


def _runnable_legacy_pbl(value: object) -> bool:
    if not isinstance(value, dict):
        return False
    project_info = value.get("projectInfo")
    issueboard = value.get("issueboard")
    chat = value.get("chat")
    agents = value.get("agents")
    return (
        isinstance(project_info, dict)
        and isinstance(agents, list)
        and isinstance(issueboard, dict)
        and isinstance(issueboard.get("issues"), list)
        and bool(issueboard["issues"])
        and all(isinstance(issue, dict) for issue in issueboard["issues"])
        and isinstance(chat, dict)
        and isinstance(chat.get("messages"), list)
        and (
            _nonempty_string(project_info.get("title"))
            or _nonempty_string(project_info.get("description"))
        )
    )


def _matches_action_kind(value: object, kind: str) -> bool:
    if kind == "string":
        return isinstance(value, str)
    if kind == "number":
        return _finite_number(value)
    if kind == "object":
        return isinstance(value, dict)
    if kind == "array":
        return isinstance(value, list)
    return False


def _validate_action(
    action: object, *, fail: Any
) -> tuple[str, str]:
    if not isinstance(action, dict):
        fail(
            "invalid_openmaic_action",
            "OpenMAIC 场景包含无效动作",
            502,
        )
    action_id = action.get("id")
    action_type = action.get("type")
    if not _bounded_identifier(action_id) or action_type not in ACTION_REQUIRED_FIELDS:
        fail(
            "invalid_openmaic_action",
            "OpenMAIC 动作不符合 1.0.0 DSL",
            502,
        )
    for field, kind in ACTION_REQUIRED_FIELDS[str(action_type)].items():
        if field not in action or not _matches_action_kind(action[field], kind):
            fail(
                "invalid_openmaic_action",
                "OpenMAIC 动作缺少必需字段",
                502,
            )
    if action_type == "wb_draw_shape" and action["shape"] not in {
        "rectangle",
        "circle",
        "triangle",
    }:
        fail("invalid_openmaic_action", "OpenMAIC 白板形状无效", 502)
    if action_type == "wb_draw_chart" and action["chartType"] not in {
        "bar",
        "column",
        "line",
        "pie",
        "ring",
        "area",
        "radar",
        "scatter",
    }:
        fail("invalid_openmaic_action", "OpenMAIC 白板图表类型无效", 502)
    if action_type == "wb_edit_code" and action["operation"] not in {
        "insert_after",
        "insert_before",
        "delete_lines",
        "replace_lines",
    }:
        fail("invalid_openmaic_action", "OpenMAIC 白板代码操作无效", 502)
    if action_type == "discussion" and not _nonempty_string(action["topic"]):
        fail("invalid_openmaic_action", "OpenMAIC 讨论主题为空", 502)
    if action_type in {"spotlight", "laser", "play_video"} and not _bounded_identifier(
        action["elementId"]
    ):
        fail("invalid_openmaic_action", "OpenMAIC 动作目标为空", 502)
    if (
        action_type == "discussion"
        and action.get("agentId") is not None
        and not _bounded_identifier(action.get("agentId"))
    ):
        fail("invalid_openmaic_action", "OpenMAIC 讨论 Agent 无效", 502)
    return str(action_type), str(action_id)


def _productive_whiteboard_action(
    action_type: str, action: Mapping[str, Any]
) -> bool:
    if action_type == "wb_draw_text":
        return _nonempty_string(action.get("content"))
    if action_type == "wb_draw_latex":
        return _nonempty_string(action.get("latex"))
    if action_type == "wb_draw_code":
        return _nonempty_string(action.get("language")) and _nonempty_string(
            action.get("code")
        )
    if action_type == "wb_draw_shape":
        return float(action["width"]) > 0 and float(action["height"]) > 0
    if action_type == "wb_draw_chart":
        data = action.get("data")
        return (
            float(action["width"]) > 0
            and float(action["height"]) > 0
            and isinstance(data, dict)
            and isinstance(data.get("series"), list)
            and bool(data["series"])
        )
    if action_type == "wb_draw_table":
        rows = action.get("data")
        return (
            float(action["width"]) > 0
            and float(action["height"]) > 0
            and isinstance(rows, list)
            and bool(rows)
            and all(isinstance(row, list) and bool(row) for row in rows)
        )
    if action_type == "wb_draw_line":
        return (action["startX"], action["startY"]) != (
            action["endX"],
            action["endY"],
        )
    return False


def _productive_widget_action(
    action_type: str,
    action: Mapping[str, Any],
    *,
    html: str,
) -> bool:
    message_type = {
        "widget_highlight": "HIGHLIGHT_ELEMENT",
        "widget_setState": "SET_WIDGET_STATE",
        "widget_annotation": "ANNOTATE_ELEMENT",
        "widget_reveal": "REVEAL_ELEMENT",
    }[action_type]
    if not _html_handles_widget_message(html, message_type):
        return False
    if action_type == "widget_setState":
        return isinstance(action.get("state"), dict) and bool(action["state"])
    target = str(action.get("target") or "").strip()
    target_identity = _widget_action_target_identity(target)
    if not target_identity or target_identity not in _html_widget_targets(html):
        return False
    if action_type == "widget_highlight":
        return _html_has_widget_target_transition(
            html, message_type="HIGHLIGHT_ELEMENT"
        )
    return True


def _widget_action_target_identity(target: str) -> str:
    """Resolve the CSS selectors emitted by OpenMAIC interactive actions."""

    normalized = str(target or "").strip()
    id_match = re.fullmatch(r"#([A-Za-z][A-Za-z0-9_-]{0,127})", normalized)
    if id_match is not None:
        return id_match.group(1)
    attribute_match = re.fullmatch(
        r"\[\s*(data-[A-Za-z][A-Za-z0-9_-]{0,79})\s*=\s*"
        r"(?:\"([^\"]{1,128})\"|'([^']{1,128})'|([^\]\s]{1,128}))\s*\]",
        normalized,
    )
    if attribute_match is not None:
        return next(
            value
            for value in attribute_match.groups()[1:]
            if value is not None
        ).strip()
    return normalized


class _WidgetTargetInspector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.targets: set[str] = set()
        self.operable_targets: set[str] = set()
        self.invalid_targets: set[str] = set()
        self._visibility_stack: list[
            tuple[str, bool, bool, frozenset[str]]
        ] = []
        self._target_css_tokens: dict[str, frozenset[str]] = {}
        self._style_chunks: list[str] = []

    @staticmethod
    def _style_declarations(style: object) -> dict[str, str]:
        declarations: dict[str, str] = {}
        for item in str(style or "").split(";"):
            if ":" not in item:
                continue
            name, value = item.split(":", 1)
            normalized_name = name.strip().casefold()
            normalized_value = re.sub(
                r"\s*!important\s*$", "", value, flags=re.IGNORECASE
            ).strip().casefold()
            if normalized_name:
                declarations[normalized_name] = normalized_value
        return declarations

    @staticmethod
    def _numeric_css_value(value: str) -> float | None:
        normalized = str(value).strip().casefold()
        if re.fullmatch(
            r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:e[+-]?\d+)?",
            normalized,
        ) is None:
            return None
        try:
            parsed = float(normalized)
        except (TypeError, ValueError, OverflowError):
            return None
        return parsed if math.isfinite(parsed) else None

    @classmethod
    def _declarations_hide(cls, declarations: Mapping[str, str]) -> bool:
        opacity = declarations.get("opacity")
        opacity_value = (
            cls._numeric_css_value(opacity) if opacity is not None else None
        )
        opacity_hidden_or_ambiguous = bool(
            opacity is not None
            and (opacity_value is None or opacity_value <= 0)
        )
        zero_dimension = any(
            re.fullmatch(r"[+-]?(?:0+(?:\.0*)?|\.0+)(?:px)?", value)
            is not None
            for value in (
                declarations.get("width", ""),
                declarations.get("height", ""),
            )
        )
        return bool(
            declarations.get("display") == "none"
            or declarations.get("visibility") in {"hidden", "collapse"}
            or opacity_hidden_or_ambiguous
            or zero_dimension
        )

    @staticmethod
    def _self_hidden(
        tag: str, attributes: Mapping[str, str | None]
    ) -> bool:
        normalized_tag = str(tag).casefold()
        declarations = _WidgetTargetInspector._style_declarations(
            attributes.get("style")
        )
        return bool(
            normalized_tag in {"script", "style", "template", "meta", "link"}
            or "hidden" in attributes
            or "inert" in attributes
            or str(attributes.get("type") or "").casefold() == "hidden"
            or str(attributes.get("aria-hidden") or "").casefold() == "true"
            or _WidgetTargetInspector._declarations_hide(declarations)
            or str(attributes.get("width") or "").strip() in {"0", "0px"}
            or str(attributes.get("height") or "").strip() in {"0", "0px"}
        )

    @staticmethod
    def _self_inoperable(attributes: Mapping[str, str | None]) -> bool:
        declarations = _WidgetTargetInspector._style_declarations(
            attributes.get("style")
        )
        return bool(
            "disabled" in attributes
            or "inert" in attributes
            or str(attributes.get("aria-disabled") or "").casefold() == "true"
            or declarations.get("pointer-events") == "none"
        )

    @staticmethod
    def _css_tokens(
        tag: str, attributes: Mapping[str, str | None]
    ) -> frozenset[str]:
        tokens = {str(tag).casefold()}
        element_id = str(attributes.get("id") or "").strip()
        if element_id:
            tokens.add(f"#{element_id}")
        for class_name in str(attributes.get("class") or "").split():
            normalized = class_name.strip()
            if normalized:
                tokens.add(f".{normalized}")
        return frozenset(tokens)

    def _inspect_element(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
        *,
        push: bool,
    ) -> None:
        normalized_tag = str(tag).casefold()
        attributes = {str(name).casefold(): value for name, value in attrs}
        ancestor_hidden = bool(
            self._visibility_stack and self._visibility_stack[-1][1]
        )
        ancestor_inoperable = bool(
            self._visibility_stack and self._visibility_stack[-1][2]
        )
        hidden = ancestor_hidden or self._self_hidden(normalized_tag, attributes)
        inoperable = ancestor_inoperable or self._self_inoperable(attributes)
        ancestor_tokens = (
            set(self._visibility_stack[-1][3])
            if self._visibility_stack
            else set()
        )
        css_tokens = frozenset(
            ancestor_tokens | set(self._css_tokens(normalized_tag, attributes))
        )
        self._record_targets(
            attrs,
            hidden=hidden,
            inoperable=inoperable,
            css_tokens=css_tokens,
        )
        if push:
            self._visibility_stack.append(
                (normalized_tag, hidden, inoperable, css_tokens)
            )

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        normalized_tag = str(tag).casefold()
        void_elements = {
            "area", "base", "br", "col", "embed", "hr", "img", "input",
            "link", "meta", "param", "source", "track", "wbr",
        }
        self._inspect_element(
            normalized_tag, attrs, push=normalized_tag not in void_elements
        )

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self._inspect_element(str(tag).casefold(), attrs, push=False)

    def handle_endtag(self, tag: str) -> None:
        normalized = str(tag).casefold()
        for index in range(len(self._visibility_stack) - 1, -1, -1):
            if self._visibility_stack[index][0] == normalized:
                del self._visibility_stack[index:]
                break

    def handle_data(self, data: str) -> None:
        if self._visibility_stack and self._visibility_stack[-1][0] == "style":
            self._style_chunks.append(str(data))

    def _record_targets(
        self,
        attrs: list[tuple[str, str | None]],
        *,
        hidden: bool,
        inoperable: bool,
        css_tokens: frozenset[str],
    ) -> None:
        element_targets: set[str] = set()
        for name, value in attrs:
            normalized_name = str(name).casefold()
            if (
                (normalized_name == "id" or normalized_name.startswith("data-"))
                and isinstance(value, str)
            ):
                normalized = value.strip()
                if normalized:
                    element_targets.add(normalized)
        for target in element_targets:
            if hidden or target in self.targets:
                self.invalid_targets.add(target)
                self.targets.discard(target)
                self.operable_targets.discard(target)
            elif target not in self.invalid_targets:
                self.targets.add(target)
                if not inoperable:
                    self.operable_targets.add(target)
                self._target_css_tokens[target] = css_tokens

    @staticmethod
    def _css_selector_mentions_tokens(
        selector: str, tokens: frozenset[str]
    ) -> bool:
        normalized = selector.strip()
        if normalized == "*":
            return True
        for token in tokens:
            if token.startswith(("#", ".")):
                if re.search(
                    re.escape(token) + r"(?![A-Za-z0-9_-])", normalized
                ):
                    return True
                attribute = "id" if token.startswith("#") else "class"
                operator = "=" if attribute == "id" else "~="
                value = re.escape(token[1:])
                if re.search(
                    rf"\[\s*{attribute}\s*{re.escape(operator)}\s*"
                    rf"(?:['\"]{value}['\"]|{value})\s*\]",
                    normalized,
                    flags=re.IGNORECASE,
                ):
                    return True
            elif re.search(
                r"(?:^|[\s>+~,])"
                + re.escape(token)
                + r"(?=$|[\s>+~,.#:\[])",
                normalized,
                flags=re.IGNORECASE,
            ):
                return True
        return False

    def apply_styles(self) -> None:
        css = re.sub(r"/\*[\s\S]*?\*/", " ", "\n".join(self._style_chunks))
        for rule in re.finditer(r"([^{}]+)\{([^{}]*)\}", css):
            selectors = [item.strip() for item in rule.group(1).split(",")]
            declarations = self._style_declarations(rule.group(2))
            hidden = self._declarations_hide(declarations)
            inoperable = declarations.get("pointer-events") == "none"
            if not hidden and not inoperable:
                continue
            for target, tokens in tuple(self._target_css_tokens.items()):
                if not any(
                    self._css_selector_mentions_tokens(selector, tokens)
                    for selector in selectors
                ):
                    continue
                if hidden:
                    self.invalid_targets.add(target)
                    self.targets.discard(target)
                    self.operable_targets.discard(target)
                elif inoperable:
                    self.operable_targets.discard(target)


def _html_widget_targets(html: str) -> set[str]:
    inspector = _WidgetTargetInspector()
    try:
        inspector.feed(html)
        inspector.close()
        inspector.apply_styles()
    except (ValueError, TypeError):
        return set()
    return inspector.targets


def _html_operable_widget_targets(html: str) -> set[str]:
    inspector = _WidgetTargetInspector()
    try:
        inspector.feed(html)
        inspector.close()
        inspector.apply_styles()
    except (ValueError, TypeError):
        return set()
    return inspector.operable_targets


def _matching_message_branch_bodies(
    body: str, *, message_type: str
) -> list[str]:
    branches: list[str] = []
    escaped = re.escape(message_type)
    for match in re.finditer(r"\bif\s*\(", body):
        brace = body.find("{", match.end())
        if brace < 0 or brace - match.start() > 1024:
            continue
        condition = body[match.start() : brace]
        if not re.search(rf"['\"]{escaped}['\"]", condition):
            continue
        branch = _extract_braced_javascript(body, brace)
        if branch is not None:
            branches.append(branch)
    for match in re.finditer(
        rf"\bcase\s*['\"]{escaped}['\"]\s*:", body
    ):
        tail = body[match.end() :]
        end = re.search(r"\b(?:case\s+|default\s*:)|}", tail)
        branches.append(tail[: end.start()] if end is not None else tail)
    return branches


def _scope_mutates_requested_widget_target(scope: str) -> bool:
    lookup = (
        r"(?:document\.)?(?:getElementById|querySelector)\s*\([^)]*"
        r"(?:data\s*\.\s*target|\btarget\b)[^)]*\)"
    )
    mutation = (
        r"(?:classList\s*\.\s*(?:add|toggle|remove)|"
        r"style\s*\.[A-Za-z_$][\w$]*\s*=|setAttribute\s*\()"
    )
    if re.search(rf"{lookup}\s*\??\.\s*{mutation}", scope, re.IGNORECASE):
        return True
    for match in re.finditer(
        rf"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*=\s*{lookup}",
        scope,
        flags=re.IGNORECASE,
    ):
        variable = re.escape(match.group(1))
        if re.search(
            rf"\b{variable}\s*\??\.\s*{mutation}",
            scope[match.end() :],
            flags=re.IGNORECASE,
        ):
            return True
    return False


def _html_has_widget_target_transition(
    html: str, *, message_type: str
) -> bool:
    executable = _executable_script_source(html)
    if not executable:
        return False
    named_bodies = _named_javascript_function_bodies(executable)
    for body in _registered_event_handler_bodies(
        executable, event_pattern="message"
    ):
        for branch in _matching_message_branch_bodies(
            body, message_type=message_type
        ):
            scope = _javascript_reachable_source(branch, named_bodies)
            if _scope_mutates_requested_widget_target(scope):
                return True
    return False


def _html_handles_widget_message(html: str, message_type: str) -> bool:
    has_message_listener = bool(
        re.search(
            r"addEventListener\s*\(\s*['\"]message['\"]|\.onmessage\s*=",
            html,
        )
    )
    if not has_message_listener:
        return False
    escaped = re.escape(message_type)
    return bool(
        re.search(
            rf"case\s*['\"]{escaped}['\"]|"
            rf"(?:data\.type|messageType|\btype)\s*={{2,3}}\s*['\"]{escaped}['\"]",
            html,
        )
    )


def _has_multi_agent_roster(agent_roles: Mapping[str, str]) -> bool:
    roles = list(agent_roles.values())
    return (
        len(agent_roles) >= 2
        and "teacher" in roles
        and any(role != "teacher" for role in roles)
    )


def _playable_video_reference(element: Mapping[str, Any]) -> str | None:
    for source in (element.get("src"), element.get("mediaRef")):
        if not isinstance(source, str):
            continue
        candidate = source.strip()
        if not candidate or re.fullmatch(
            r"gen_vid_[\w-]+", candidate, re.IGNORECASE
        ):
            continue
        if candidate.casefold().startswith("data:video/"):
            return candidate
        if re.match(
            r"^https?://", candidate, re.IGNORECASE
        ) or candidate.startswith("/"):
            return candidate
    return None


def _required_identifier(value: object, label: str, max_length: int) -> str:
    normalized = str(value or "").strip()
    if not normalized or len(normalized) > max_length:
        raise OpenMaicRuntimeServiceError(
            f"invalid_{label}", f"{label} 无效", status_code=400
        )
    if not all(character.isalnum() or character in {"-", "_", "."} for character in normalized):
        raise OpenMaicRuntimeServiceError(
            f"invalid_{label}", f"{label} 无效", status_code=400
        )
    return normalized


def _feature_list(
    value: object,
    *,
    default: Iterable[str] | None = None,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if value is None:
        raw: object = list(
            DEFAULT_RUNTIME_FEATURES if default is None else default
        )
    else:
        raw = value
    if not isinstance(raw, (list, tuple)) or (not raw and not allow_empty):
        raise OpenMaicRuntimeServiceError(
            "invalid_openmaic_features", "features 必须是非空数组", status_code=400
        )
    normalized: list[str] = []
    for item in raw:
        feature = str(item or "").strip().lower()
        if feature not in RUNTIME_FEATURES:
            raise OpenMaicRuntimeServiceError(
                "unsupported_openmaic_feature",
                f"不支持的 OpenMAIC 能力：{feature or 'empty'}",
                status_code=400,
            )
        if feature not in normalized:
            normalized.append(feature)
    return tuple(normalized)


def _generation_options(value: object) -> dict[str, Any]:
    raw = value if isinstance(value, dict) else {}
    allowed = {
        "enableWebSearch",
        "enableImageGeneration",
        "enableVideoGeneration",
        "enableTTS",
        "agentMode",
    }
    if set(raw) - allowed:
        raise OpenMaicRuntimeServiceError(
            "invalid_openmaic_options",
            "课堂生成参数包含不允许的字段",
            status_code=400,
        )
    agent_mode = str(raw.get("agentMode") or "generate").strip().lower()
    if agent_mode not in {"default", "generate"}:
        raise OpenMaicRuntimeServiceError(
            "invalid_openmaic_agent_mode",
            "agentMode 必须是 default 或 generate",
            status_code=400,
        )
    return {
        "enableWebSearch": bool(raw.get("enableWebSearch", False)),
        "enableImageGeneration": bool(raw.get("enableImageGeneration", True)),
        "enableVideoGeneration": bool(raw.get("enableVideoGeneration", True)),
        "enableTTS": bool(raw.get("enableTTS", True)),
        "agentMode": agent_mode,
    }
