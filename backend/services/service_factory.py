from __future__ import annotations

from pathlib import Path
from urllib.parse import urlparse

from flask import current_app

from core.config import (
    BACKEND_ROOT,
    LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS,
)
from core.database import Database
from core.errors import ApiError
from integrations.hardware.disabled_adapter import DisabledHardwareDeviceAdapter
from integrations.hardware.mock_adapter import MockHardwareDeviceAdapter
from services.auth_service import AuthService
from services.student_auth_service import StudentAuthService
from integrations.ai.kimi_vision_provider import OpenAICompatibleVisionProvider
from integrations.ai.unavailable_vision_provider import UnavailableVisionProvider
from services.ai_text_provider import OpenAICompatibleTextProvider, UnavailableAiTextProvider
from services.vision_observation_service import VisionObservationService
from services.camera_bridge_service import CameraBridgeService
from services.camera_ai_observation_service import CameraAiObservationService
from integrations.camera_runtime.python_open_cv_yolo_prefilter import default_local_vision_prefilter
from integrations.camera_runtime.go2rtc_client import Go2RtcClient
from integrations.onvif.client import OnvifClient
from integrations.tts.macos_say import MacOsSayTtsProvider
from integrations.tts.voxcpm2 import VoxCpm2HttpProvider
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from integrations.openmaic_formal_citation_recovery_client import (
    OpenMaicFormalCitationRecoveryClient,
)
from integrations.openmaic_conversation_probe_client import (
    OpenMaicConversationProbeClient,
)
from integrations.openmaic_deterministic_recovery_client import (
    RECOVERY_CANONICAL_SPEC_SHA256,
    RECOVERY_PATCH_SHA256,
    OpenMaicDeterministicRecoveryClient,
)
from integrations.openmaic_tts_credential_recovery_client import (
    TTS_CREDENTIAL_RECOVERY_PATCH_SHA256,
    OpenMaicTtsCredentialRecoveryClient,
)
from integrations.openmaic_question_adapter import (
    OpenMaicQuestionAdapter,
    OpenMaicQuestionPhaseAdapter,
)
from services.camera_observe_service import CameraObserveService
from services.camera_command_service import CameraCommandService
from services.care_config_service import CareConfigService
from services.device_service import DeviceService
from services.device_credential_store import EncryptedFileCredentialStore
from services.device_runtime_resolver import DeviceRuntimeResolver
from services.firmware_service import FirmwareService
from services.ai_care_reminder_service import AiCareReminderService
from services.internal_request_guard import InternalRequestGuard
from services.learning_content_generation_service import LearningContentGenerationService
from services.learning_content_pipeline_service import LearningContentPipelineService
from services.dynamic_learning_course_generation_service import (
    DynamicLearningCourseGenerationService,
    StagedContentCandidateGenerator,
)
from repositories.dynamic_learning_course_repository import (
    DynamicLearningCourseRepository,
)
from services.learning_service import LearningService
from services.learning_curriculum_preparation_service import (
    LearningCurriculumPreparationService,
)
from services.learning_curriculum_preparation_runner import (
    CheckpointSharedBuildAdapter,
    FormalProductionStageAdapter,
)
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.learning_catalog_validator import LearningCatalogValidator
from services.learning_generated_course_validator import (
    LearningGeneratedCourseValidator,
)
from repositories.learning_teacher_media_repository import (
    LearningTeacherMediaRepository,
)
from repositories.learning_curriculum_preparation_repository import (
    LearningCurriculumPreparationRepository,
)
from services.learning_media_asset_store import FilesystemLearningMediaAssetStore
from services.learning_media_materialization_service import (
    FormalQwenAudioService,
    LearningMediaMaterializationService,
)
from services.lesson_package_service import LessonPackageService
from services.lesson_runtime_service import LessonRuntimeService
from services.student_learning_service import StudentLearningService
from services.student_learning_media_service import StudentLearningMediaService
from services.openmaic_full_runtime_service import OpenMaicFullRuntimeService
from services.openmaic_runtime_audio_service import OpenMaicRuntimeAudioService
from services.openmaic_conversation_probe_service import (
    OpenMaicConversationProbeService,
)
from services.point_service import PointService
from services.profile_service import ProfileService
from services.reward_service import RewardService
from services.routine_reminder_service import RoutineReminderService
from services.setup_service import SetupService
from services.sms_provider import DevelopmentSmsProvider, SmsProvider, UnavailableSmsProvider
from services.prompt_registry import PromptRegistry
from services.task_service import TaskService
from services.task_template_service import TaskTemplateService
from services.task_runtime_service import TaskRuntimeService
from services.conversation_app_service import ConversationAppService
from services.conversation_sync_service import ConversationSyncService
from services.voice_conversation_service import VoiceConversationService
from services.voice_runtime_app_service import VoiceRuntimeAppService


class _ParentRetryQuestionPhaseCanonicalizer:
    """Pure request/hash authority for retry audits; never executes a phase."""

    canonicalize_phase = OpenMaicQuestionPhaseAdapter.canonicalize_phase

    def __init__(self, profile: dict[str, object]):
        self.provider_name = str(profile["name"])
        self.model_name = str(profile["model"])
        self.base_url = str(profile["baseUrl"])
        self.api_key_env = str(profile["apiKeyEnv"])
        self.provider_timeout_ms = int(profile["timeoutMs"])
        self.max_tokens = int(profile["maxTokens"])
        self.temperature = float(profile["temperature"])


class _ParentRetryCatalogAuditService(LearningCatalogReleaseService):
    """Catalog retry auditor with canonicalization but no execution adapter."""

    def __init__(self, database_url: str, profile: dict[str, object] | None):
        profiles = (
            {"generator": dict(profile), "verifier": dict(profile)}
            if profile is not None
            else {}
        )
        super().__init__(
            database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
            primary_one_host_validator=LearningGeneratedCourseValidator(),
            question_phase_provider_profiles=profiles,
        )
        self._parent_retry_canonicalizer = (
            _ParentRetryQuestionPhaseCanonicalizer(profile)
            if profile is not None
            else None
        )

    def _content_provider_preflight(self, command):
        canonicalizer = self._parent_retry_canonicalizer
        if canonicalizer is None:
            raise ValueError("parent retry Provider profile is unavailable")
        return canonicalizer.canonicalize_phase(command)


def auth_service() -> AuthService:
    return AuthService(
        current_app.config["DATABASE_URL"],
        access_token_seconds=current_app.config["AUTH_ACCESS_TOKEN_SECONDS"],
        refresh_token_seconds=current_app.config["AUTH_REFRESH_TOKEN_SECONDS"],
        sms_code_ttl_seconds=current_app.config["SMS_CODE_TTL_SECONDS"],
        sms_resend_cooldown_seconds=current_app.config["SMS_RESEND_COOLDOWN_SECONDS"],
        sms_max_attempts=current_app.config["SMS_MAX_ATTEMPTS"],
        sms_provider=sms_provider(),
    )


def student_auth_service() -> StudentAuthService:
    return StudentAuthService(
        current_app.config["DATABASE_URL"],
        parent_auth_service=auth_service(),
        pepper=current_app.config["STUDENT_AUTH_PEPPER"],
        access_token_seconds=current_app.config["STUDENT_ACCESS_TOKEN_SECONDS"],
        refresh_token_seconds=current_app.config["STUDENT_REFRESH_TOKEN_SECONDS"],
        device_token_seconds=current_app.config["STUDENT_DEVICE_TOKEN_SECONDS"],
        pairing_code_ttl_seconds=current_app.config[
            "STUDENT_PAIRING_CODE_TTL_SECONDS"
        ],
        qr_challenge_ttl_seconds=current_app.config[
            "STUDENT_QR_CHALLENGE_TTL_SECONDS"
        ],
        qr_approval_exchange_seconds=current_app.config[
            "STUDENT_QR_APPROVAL_EXCHANGE_SECONDS"
        ],
        qr_polling_interval_ms=current_app.config[
            "STUDENT_QR_POLLING_INTERVAL_MS"
        ],
        qr_active_challenge_limit=current_app.config[
            "STUDENT_QR_ACTIVE_CHALLENGE_LIMIT"
        ],
        qr_ip_active_challenge_limit=current_app.config[
            "STUDENT_QR_IP_ACTIVE_CHALLENGE_LIMIT"
        ],
        qr_rate_limit_window_seconds=current_app.config[
            "STUDENT_QR_RATE_LIMIT_WINDOW_SECONDS"
        ],
        qr_rate_limit_max=current_app.config["STUDENT_QR_RATE_LIMIT_MAX"],
        qr_ip_rate_limit_max=current_app.config[
            "STUDENT_QR_IP_RATE_LIMIT_MAX"
        ],
        qr_retention_seconds=current_app.config["STUDENT_QR_RETENTION_SECONDS"],
        pin_pbkdf2_iterations=current_app.config[
            "STUDENT_PIN_PBKDF2_ITERATIONS"
        ],
        pin_max_attempts=current_app.config["STUDENT_PIN_MAX_ATTEMPTS"],
        pin_lock_seconds=current_app.config["STUDENT_PIN_LOCK_SECONDS"],
        formal_learning_access_checker=(
            current_app.extensions.get("mira_formal_learning_access_checker")
            if current_app.testing
            else None
        ),
    )


def setup_service() -> SetupService:
    return SetupService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        preparation_service=learning_curriculum_preparation_service(),
        camera_command_service_factory=camera_command_service,
    )


def learning_curriculum_preparation_service() -> LearningCurriculumPreparationService:
    service = current_app.extensions.get(
        "mira_learning_curriculum_preparation_service"
    )
    if isinstance(service, LearningCurriculumPreparationService):
        return service
    service = LearningCurriculumPreparationService(
        current_app.config["DATABASE_URL"],
        course_library_enabled=bool(current_app.config.get("LEARNING_COURSE_LIBRARY_ENABLED", False)),
        auth_service=auth_service(),
        repository=learning_curriculum_preparation_repository(),
        retry_repository_factory=(
            learning_curriculum_preparation_parent_retry_repository
        ),
        shared_build_repository_factory=(
            learning_curriculum_preparation_parent_retry_repository
        ),
    )
    current_app.extensions["mira_learning_curriculum_preparation_service"] = service
    return service


def learning_curriculum_preparation_repository() -> LearningCurriculumPreparationRepository:
    repository = current_app.extensions.get(
        "mira_learning_curriculum_preparation_repository"
    )
    if isinstance(repository, LearningCurriculumPreparationRepository):
        return repository
    repository = LearningCurriculumPreparationRepository(
        Database(current_app.config["DATABASE_URL"])
    )
    current_app.extensions[
        "mira_learning_curriculum_preparation_repository"
    ] = repository
    return repository


def learning_curriculum_preparation_status_repository() -> LearningCurriculumPreparationRepository:
    repository = current_app.extensions.get(
        "mira_learning_curriculum_preparation_status_repository"
    )
    if isinstance(repository, LearningCurriculumPreparationRepository):
        return repository
    repository = LearningCurriculumPreparationRepository(
        Database(current_app.config["DATABASE_URL"])
    )
    current_app.extensions[
        "mira_learning_curriculum_preparation_status_repository"
    ] = repository
    return repository


def learning_curriculum_preparation_parent_retry_repository() -> LearningCurriculumPreparationRepository:
    repository = current_app.extensions.get(
        "mira_learning_curriculum_preparation_parent_retry_repository"
    )
    if isinstance(repository, LearningCurriculumPreparationRepository):
        return repository
    database_url = current_app.config["DATABASE_URL"]
    profile = _checkpoint_question_phase_profile()
    audit_service = _ParentRetryCatalogAuditService(database_url, profile)
    repository = LearningCurriculumPreparationRepository(
        Database(database_url),
        content_proof_auditor=audit_service.audit_locked_content_proofs,
        content_parent_retry_auditor=(
            audit_service.audit_content_parent_retry_authority
        ),
    )
    current_app.extensions[
        "mira_learning_curriculum_preparation_parent_retry_repository"
    ] = repository
    return repository


def learning_curriculum_preparation_checkpoint_adapter() -> CheckpointSharedBuildAdapter:
    adapter = current_app.extensions.get(
        "mira_learning_curriculum_preparation_checkpoint_adapter"
    )
    if isinstance(adapter, FormalProductionStageAdapter):
        return adapter
    database_url = current_app.config["DATABASE_URL"]
    profile = _checkpoint_question_phase_profile()
    if profile is None:
        restricted_catalog_service = LearningCatalogReleaseService(
            database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
        )
    else:
        phase_adapter = OpenMaicQuestionPhaseAdapter(
            provider_name=str(profile["name"]),
            model_name=str(profile["model"]),
            base_url=str(profile["baseUrl"]),
            api_key_env=str(profile["apiKeyEnv"]),
            provider_timeout_ms=int(profile["timeoutMs"]),
            max_tokens=int(profile["maxTokens"]),
            temperature=float(profile["temperature"]),
            process_timeout_seconds=(
                int(profile["timeoutMs"])
                + OpenMaicQuestionPhaseAdapter.PROCESS_SHUTDOWN_ALLOWANCE_MS
            )
            / 1000.0,
        )
        staged_generator = StagedContentCandidateGenerator(
            repository=DynamicLearningCourseRepository(Database(database_url)),
            adapter=phase_adapter,
        )
        restricted_catalog_service = LearningCatalogReleaseService(
            database_url,
            dynamic_generation_service=None,
            lesson_package_service=None,
            catalog_validator=LearningCatalogValidator(),
            staged_content_candidate_generator=staged_generator,
            primary_one_host_validator=LearningGeneratedCourseValidator(),
            question_phase_provider_profiles={
                "generator": dict(profile),
                "verifier": dict(profile),
            },
        )
    checkpoint_repository = LearningCurriculumPreparationRepository(
        Database(database_url),
        content_proof_auditor=(
            restricted_catalog_service.audit_locked_content_proofs
        ),
        content_dispatch_graph_auditor=(
            restricted_catalog_service.audit_content_host_retry_graph
        ),
        content_parent_retry_auditor=(
            restricted_catalog_service.audit_content_parent_retry_authority
        ),
        content_provider_dependency_auditor=(
            restricted_catalog_service.audit_content_provider_dependency_retry
        ),
        content_host_dependency_auditor=(
            restricted_catalog_service.audit_content_host_dependency_retry
        ),
    )
    formal_repository = LearningTeacherMediaRepository(Database(database_url))
    formal_runtime_enabled = bool(
        current_app.config.get("OPENMAIC_FULL_RUNTIME_ENABLED") is True
        and current_app.config.get(
            "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED"
        ) is True
        and str(
            current_app.config.get("OPENMAIC_FULL_RUNTIME_INTERNAL_URL") or ""
        ).strip()
        and str(current_app.config.get("INTERNAL_API_TOKEN") or "").strip()
    )
    runtime_service = (
        openmaic_full_runtime_service() if formal_runtime_enabled else None
    )
    runtime_client = getattr(runtime_service, "client", None)
    formal_audio_service = (
        FormalQwenAudioService(
            formal_repository,
            runtime_client=runtime_client,
            asset_store=FilesystemLearningMediaAssetStore(
                _backend_relative_path(
                    str(
                        current_app.config.get("LEARNING_MEDIA_STORAGE_ROOT")
                        or "data/learning-media"
                    )
                )
            ),
        )
        if (
            isinstance(runtime_client, OpenMaicFullRuntimeClient)
            and formal_runtime_enabled
            and current_app.config.get(
                "LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED", False
            ) is True
        )
        else None
    )
    adapter = FormalProductionStageAdapter(
        restricted_catalog_service,
        repository=checkpoint_repository,
        runtime_candidate_processor=lambda: process_next_formal_runtime_candidate(),
        formal_repository=formal_repository,
        formal_audio_service=formal_audio_service,
        formal_audio_validation_enabled=(
            current_app.config.get(
                "LEARNING_FORMAL_AUDIO_VALIDATION_ENABLED", False
            ) is True
        ),
        formal_auto_publication_enabled=(
            current_app.config.get(
                "LEARNING_FORMAL_AUTO_PUBLICATION_ENABLED", False
            ) is True
        ),
        formal_provider_readiness_client=(
            runtime_client
            if isinstance(runtime_client, OpenMaicFullRuntimeClient)
            else None
        ),
        formal_route_probe_service=(
            openmaic_conversation_probe_service()
            if current_app.config.get(
                "OPENMAIC_CONVERSATION_PROBE_ENABLED", False
            )
            else None
        ),
        formal_route_probe_client=openmaic_conversation_probe_client(),
        max_progressive_published_courses=current_app.config.get(
            "LEARNING_CURRICULUM_PREPARATION_PROGRESSIVE_PUBLICATION_LIMIT"
        ),
        plan_lease_ms=int(
            current_app.config.get(
                "LEARNING_CURRICULUM_PREPARATION_LEASE_SECONDS",
                LEARNING_CURRICULUM_PREPARATION_MIN_LEASE_SECONDS,
            )
        )
        * 1000,
    )
    current_app.extensions[
        "mira_learning_curriculum_preparation_checkpoint_adapter"
    ] = adapter
    return adapter


def _checkpoint_question_phase_profile() -> dict[str, object] | None:
    # Learning courseware has one generation authority: OpenMAIC.  The backend
    # intentionally does not project its camera/observation AI Provider into
    # the learning pipeline and never gives the Sidecar a model credential.
    base_url = str(
        current_app.config.get("OPENMAIC_FULL_RUNTIME_INTERNAL_URL") or ""
    ).strip()
    internal_token = str(
        current_app.config.get("INTERNAL_API_TOKEN") or ""
    ).strip()
    parsed = urlparse(base_url)
    if (
        not internal_token
        or parsed.scheme not in {"http", "https"}
        or not parsed.netloc
    ):
        return None
    return {
        "name": "openmaic_runtime",
        "model": "courseware-v2",
        "baseUrl": base_url.rstrip("/"),
        "apiKeyEnv": "INTERNAL_API_TOKEN",
        # This bounds one private OpenMAIC courseware call. OpenMAIC owns the
        # model credential and the paid invocation; the backend only waits for
        # the result and persists its receipt.
        "timeoutMs": 300_000,
        "maxTokens": 8_000,
        "temperature": 0.6,
    }


def task_service() -> TaskService:
    return TaskService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        camera_command_service_factory=camera_command_service,
        ai_text_provider=ai_text_provider(),
        prompt_registry=prompt_registry(),
    )


def learning_service() -> LearningService:
    service = current_app.extensions.get("mira_learning_service")
    if isinstance(service, LearningService):
        return service
    service = LearningService(
        current_app.config["DATABASE_URL"],
        course_library_enabled=bool(current_app.config.get("LEARNING_COURSE_LIBRARY_ENABLED", False)),
        auth_service=auth_service(),
        static_catalog_enabled=bool(
            current_app.config.get("LEARNING_STATIC_CATALOG_ENABLED", False)
        ),
        dynamic_generation_service=(
            dynamic_learning_course_generation_service()
            if current_app.config.get("LEARNING_DYNAMIC_GENERATION_ENABLED")
            else None
        ),
        dynamic_pool_target=int(
            current_app.config.get("LEARNING_DYNAMIC_POOL_TARGET", 1)
        ),
    )
    current_app.extensions["mira_learning_service"] = service
    return service


def student_learning_service() -> StudentLearningService:
    service = current_app.extensions.get("mira_student_learning_service")
    if isinstance(service, StudentLearningService):
        return service
    service = StudentLearningService(
        current_app.config["DATABASE_URL"],
        course_library_enabled=bool(current_app.config.get("LEARNING_COURSE_LIBRARY_ENABLED", False)),
        student_auth_service=student_auth_service(),
        static_catalog_enabled=bool(
            current_app.config.get("LEARNING_STATIC_CATALOG_ENABLED", False)
        ),
        dynamic_generation_service=(
            dynamic_learning_course_generation_service()
            if current_app.config.get("LEARNING_DYNAMIC_GENERATION_ENABLED")
            else None
        ),
        dynamic_pool_target=int(
            current_app.config.get("LEARNING_DYNAMIC_POOL_TARGET", 1)
        ),
        lesson_runtime_service=lesson_runtime_service(),
        classroom_student_release_enabled=bool(
            current_app.config.get(
                "LEARNING_CLASSROOM_STUDENT_RELEASE_ENABLED",
                False,
            )
        ),
    )
    current_app.extensions["mira_student_learning_service"] = service
    return service


def student_learning_media_service() -> StudentLearningMediaService:
    service = current_app.extensions.get("mira_student_learning_media_service")
    if isinstance(service, StudentLearningMediaService):
        return service
    service = StudentLearningMediaService(
        current_app.config["DATABASE_URL"],
        student_auth_service=student_auth_service(),
        storage_root=_backend_relative_path(
            str(
                current_app.config.get("LEARNING_MEDIA_STORAGE_ROOT")
                or "data/learning-media"
            )
        ),
    )
    current_app.extensions["mira_student_learning_media_service"] = service
    return service


def openmaic_full_runtime_service() -> OpenMaicFullRuntimeService:
    service = current_app.extensions.get("mira_openmaic_full_runtime_service")
    if isinstance(service, OpenMaicFullRuntimeService):
        return service
    enabled = bool(current_app.config.get("OPENMAIC_FULL_RUNTIME_ENABLED", False))
    internal_url = str(
        current_app.config.get("OPENMAIC_FULL_RUNTIME_INTERNAL_URL") or ""
    ).strip()
    client = (
        OpenMaicFullRuntimeClient(
            internal_url,
            timeout_seconds=float(
                current_app.config.get("OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS", 30)
            ),
            formal_audio_internal_token=str(
                current_app.config.get("INTERNAL_API_TOKEN") or ""
            ),
        )
        if enabled and internal_url
        else None
    )
    recovery_enabled = bool(
        current_app.config.get(
            "OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED", False
        )
    )
    tts_credential_recovery_enabled = bool(
        current_app.config.get(
            "OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED", False
        )
    )
    formal_citation_recovery_enabled = bool(
        current_app.config.get(
            "OPENMAIC_FORMAL_CITATION_RECOVERY_ENABLED", False
        )
    )
    recovery_client = (
        OpenMaicDeterministicRecoveryClient(
            internal_url,
            internal_token=str(
                current_app.config.get("INTERNAL_API_TOKEN") or ""
            ),
            expected_canonical_spec_sha256=(
                RECOVERY_CANONICAL_SPEC_SHA256
            ),
            expected_patch_sha256=RECOVERY_PATCH_SHA256,
            timeout_seconds=float(
                current_app.config.get(
                    "OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS", 30
                )
            ),
        )
        if enabled and recovery_enabled and internal_url
        else None
    )
    tts_credential_recovery_client = (
        OpenMaicTtsCredentialRecoveryClient(
            internal_url,
            internal_token=str(
                current_app.config.get("INTERNAL_API_TOKEN") or ""
            ),
            expected_patch_sha256=TTS_CREDENTIAL_RECOVERY_PATCH_SHA256,
            timeout_seconds=float(
                current_app.config.get(
                    "OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS", 30
                )
            ),
        )
        if enabled and tts_credential_recovery_enabled and internal_url
        else None
    )
    formal_citation_recovery_client = (
        OpenMaicFormalCitationRecoveryClient(
            internal_url,
            internal_token=str(
                current_app.config.get("INTERNAL_API_TOKEN") or ""
            ),
            timeout_seconds=float(
                current_app.config.get(
                    "OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS", 30
                )
            ),
        )
        if enabled and formal_citation_recovery_enabled and internal_url
        else None
    )
    service = OpenMaicFullRuntimeService(
        current_app.config["DATABASE_URL"],
        student_auth_service=student_auth_service(),
        client=client,
        enabled=enabled,
        generation_enabled=bool(
            current_app.config.get(
                "OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED", False
            )
        ),
        public_url=str(
            current_app.config.get("OPENMAIC_FULL_RUNTIME_PUBLIC_URL") or ""
        ),
        launch_ttl_seconds=int(
            current_app.config.get("OPENMAIC_FULL_RUNTIME_LAUNCH_TTL_SECONDS", 60)
        ),
        session_ttl_seconds=int(
            current_app.config.get(
                "OPENMAIC_FULL_RUNTIME_SESSION_TTL_SECONDS", 14400
            )
        ),
        video_export_enabled=bool(
            current_app.config.get(
                "OPENMAIC_FULL_RUNTIME_VIDEO_EXPORT_ENABLED", False
            )
        ),
        conversation_probe_service=(
            openmaic_conversation_probe_service()
            if current_app.config.get("OPENMAIC_CONVERSATION_PROBE_ENABLED", False)
            else None
        ),
        conversation_probe_client=openmaic_conversation_probe_client(),
        deterministic_recovery_enabled=recovery_enabled,
        deterministic_recovery_redispatch_enabled=bool(
            current_app.config.get(
                "OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED", False
            )
        ),
        deterministic_recovery_client=recovery_client,
        tts_credential_recovery_enabled=tts_credential_recovery_enabled,
        tts_credential_recovery_client=tts_credential_recovery_client,
        formal_citation_recovery_enabled=formal_citation_recovery_enabled,
        formal_citation_recovery_source_job_id=str(
            current_app.config.get(
                "OPENMAIC_FORMAL_CITATION_RECOVERY_SOURCE_JOB_ID"
            )
            or ""
        ),
        formal_citation_recovery_client=formal_citation_recovery_client,
    )
    current_app.extensions["mira_openmaic_full_runtime_service"] = service
    return service


def openmaic_runtime_audio_service() -> OpenMaicRuntimeAudioService:
    service = current_app.extensions.get("mira_openmaic_runtime_audio_service")
    if isinstance(service, OpenMaicRuntimeAudioService):
        return service
    service = OpenMaicRuntimeAudioService(
        current_app.config["DATABASE_URL"],
        storage_root=_backend_relative_path(
            str(
                current_app.config.get("LEARNING_MEDIA_STORAGE_ROOT")
                or "data/learning-media"
            )
        ),
    )
    current_app.extensions["mira_openmaic_runtime_audio_service"] = service
    return service


def openmaic_conversation_probe_service() -> OpenMaicConversationProbeService:
    service = current_app.extensions.get("mira_openmaic_conversation_probe_service")
    if isinstance(service, OpenMaicConversationProbeService):
        return service
    service = OpenMaicConversationProbeService(
        current_app.config["DATABASE_URL"],
        enabled=bool(
            current_app.config.get("OPENMAIC_CONVERSATION_PROBE_ENABLED", False)
        ),
        ttl_seconds=int(
            current_app.config.get("OPENMAIC_CONVERSATION_PROBE_TTL_SECONDS", 90)
        ),
    )
    current_app.extensions["mira_openmaic_conversation_probe_service"] = service
    return service


def openmaic_conversation_probe_client() -> OpenMaicConversationProbeClient | None:
    if not current_app.config.get("OPENMAIC_CONVERSATION_PROBE_ENABLED", False):
        return None
    service = current_app.extensions.get("mira_openmaic_conversation_probe_client")
    if isinstance(service, OpenMaicConversationProbeClient):
        return service
    public_url = str(
        current_app.config.get("OPENMAIC_FULL_RUNTIME_PUBLIC_URL") or ""
    ).strip()
    if not public_url:
        return None
    service = OpenMaicConversationProbeClient(
        public_url,
        timeout_seconds=float(
            current_app.config.get("OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS", 30)
        ),
    )
    current_app.extensions["mira_openmaic_conversation_probe_client"] = service
    return service


def learning_content_generation_service() -> LearningContentGenerationService:
    return LearningContentGenerationService()


def learning_content_pipeline_service() -> LearningContentPipelineService:
    return LearningContentPipelineService(
        current_app.config["DATABASE_URL"],
        generation_service=learning_content_generation_service(),
    )


def lesson_package_service() -> LessonPackageService:
    service = current_app.extensions.get("mira_lesson_package_service")
    if isinstance(service, LessonPackageService):
        return service
    service = LessonPackageService(
        current_app.config["DATABASE_URL"],
        media_service=learning_media_materialization_service(),
    )
    current_app.extensions["mira_lesson_package_service"] = service
    return service


def process_next_formal_runtime_candidate():
    """Wire the candidate package boundary to the full Runtime boundary."""

    runtime = openmaic_full_runtime_service()
    readiness = runtime.ensure_initial_formal_provider_probe()
    if readiness.get("dispatchAllowed") is not True:
        return {"blockedReason": "provider_probe_required"}
    return lesson_package_service().process_next_formal_candidate(
        runtime
    )


def learning_media_materialization_service() -> LearningMediaMaterializationService:
    service = current_app.extensions.get("mira_learning_media_materialization_service")
    if isinstance(service, LearningMediaMaterializationService):
        return service
    provider_id = str(
        current_app.config.get("LEARNING_TTS_PROVIDER") or "voxcpm2"
    ).strip().lower()
    if provider_id == "macos-say":
        provider = MacOsSayTtsProvider(
            app_env=str(current_app.config.get("APP_ENV") or ""),
            timeout_seconds=float(
                current_app.config.get("LEARNING_MACOS_SAY_TIMEOUT_SECONDS", 30)
            ),
        )
    else:
        base_url = str(
            current_app.config.get("LEARNING_VOXCPM_BASE_URL") or ""
        ).strip()
        provider = (
            VoxCpm2HttpProvider(
                base_url=base_url,
                backend=str(
                    current_app.config.get("LEARNING_VOXCPM_BACKEND")
                    or "vllm-omni"
                ),
                model_name=str(
                    current_app.config.get("LEARNING_VOXCPM_MODEL")
                    or "openbmb/VoxCPM2"
                ),
                timeout_seconds=float(
                    current_app.config.get("LEARNING_VOXCPM_TIMEOUT_SECONDS", 30)
                ),
            )
            if base_url
            else None
        )
    storage_root = _backend_relative_path(
        str(
            current_app.config.get("LEARNING_MEDIA_STORAGE_ROOT")
            or "data/learning-media"
        )
    )
    service = LearningMediaMaterializationService(
        LearningTeacherMediaRepository(
            Database(current_app.config["DATABASE_URL"])
        ),
        tts_provider=provider,
        asset_store=FilesystemLearningMediaAssetStore(storage_root),
    )
    current_app.extensions["mira_learning_media_materialization_service"] = service
    return service


def lesson_runtime_service() -> LessonRuntimeService:
    service = current_app.extensions.get("mira_lesson_runtime_service")
    if isinstance(service, LessonRuntimeService):
        return service
    service = LessonRuntimeService(current_app.config["DATABASE_URL"])
    current_app.extensions["mira_lesson_runtime_service"] = service
    return service


def dynamic_learning_course_generation_service() -> DynamicLearningCourseGenerationService:
    service = current_app.extensions.get(
        "mira_dynamic_learning_course_generation_service"
    )
    if isinstance(service, DynamicLearningCourseGenerationService):
        return service
    service = DynamicLearningCourseGenerationService(
        current_app.config["DATABASE_URL"],
        adapter=OpenMaicQuestionAdapter(
            timeout_seconds=float(
                current_app.config.get("OPENMAIC_QUESTION_TIMEOUT_SECONDS", 420)
            )
        ),
        classroom_enqueue=lesson_package_service().enqueue,
    )
    current_app.extensions[
        "mira_dynamic_learning_course_generation_service"
    ] = service
    return service


def learning_catalog_release_service() -> LearningCatalogReleaseService:
    service = current_app.extensions.get("mira_learning_catalog_release_service")
    if isinstance(service, LearningCatalogReleaseService):
        return service
    service = LearningCatalogReleaseService(
        current_app.config["DATABASE_URL"],
        dynamic_generation_service=dynamic_learning_course_generation_service(),
        lesson_package_service=lesson_package_service(),
    )
    current_app.extensions["mira_learning_catalog_release_service"] = service
    return service


def task_template_service() -> TaskTemplateService:
    return TaskTemplateService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
    )


def point_service() -> PointService:
    return PointService(current_app.config["DATABASE_URL"], auth_service=auth_service())


def reward_service() -> RewardService:
    return RewardService(current_app.config["DATABASE_URL"], auth_service=auth_service())


def profile_service() -> ProfileService:
    return ProfileService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        preparation_service=learning_curriculum_preparation_service(),
    )


def device_service() -> DeviceService:
    return DeviceService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        hardware_adapter=hardware_adapter(),
        runtime_resolver=device_runtime_resolver(),
        onvif_client=onvif_client(),
        credential_store=device_credential_store(),
        onvif_discovery_ttl_seconds=int(
            current_app.config.get("ONVIF_DISCOVERY_TOKEN_TTL_SECONDS", 90)
        ),
        onvif_supported_manufacturers=tuple(
            current_app.config.get("ONVIF_SUPPORTED_MANUFACTURERS") or ("Vatilon",)
        ),
        onvif_supported_models=tuple(
            current_app.config.get("ONVIF_SUPPORTED_MODELS") or ("T62",)
        ),
        onvif_bootstrap_credentials_enabled=bool(
            current_app.config.get("ONVIF_BOOTSTRAP_CREDENTIALS_ENABLED")
        ),
        onvif_bootstrap_username=str(
            current_app.config.get("ONVIF_BOOTSTRAP_USERNAME") or ""
        ),
        onvif_bootstrap_password=str(
            current_app.config.get("ONVIF_BOOTSTRAP_PASSWORD") or ""
        ),
        app_env=str(current_app.config.get("APP_ENV", "production")),
        dev_adapters_enabled=bool(current_app.config.get("DEV_ADAPTERS_ENABLED")),
    )


def onvif_client() -> OnvifClient:
    return OnvifClient(
        discovery_timeout_seconds=float(
            current_app.config.get("ONVIF_DISCOVERY_TIMEOUT_SECONDS", 1.5)
        ),
        http_timeout_seconds=float(
            current_app.config.get("ONVIF_HTTP_TIMEOUT_SECONDS", 4)
        ),
        rtsp_timeout_seconds=float(
            current_app.config.get("ONVIF_RTSP_TIMEOUT_SECONDS", 4)
        ),
    )


def device_credential_store() -> EncryptedFileCredentialStore:
    app_env = str(current_app.config.get("APP_ENV", "production")).strip().lower()
    root = _backend_relative_path(
        str(current_app.config.get("DEVICE_SECRET_STORE_DIR") or "")
    )
    key_file_value = str(current_app.config.get("DEVICE_SECRET_KEY_FILE") or "")
    return EncryptedFileCredentialStore(
        root=root,
        key=str(current_app.config.get("DEVICE_SECRET_KEY") or ""),
        key_file=_backend_relative_path(key_file_value) if key_file_value else None,
        allow_key_generation=app_env in {"development", "test"},
    )


def _backend_relative_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else BACKEND_ROOT / path


def firmware_service() -> FirmwareService:
    return FirmwareService(current_app.config["DATABASE_URL"], auth_service=auth_service())


def camera_bridge_service() -> CameraBridgeService:
    return device_runtime_resolver().global_bridge()


def device_runtime_resolver() -> DeviceRuntimeResolver:
    provider = str(current_app.config.get("CAMERA_RUNTIME_PROVIDER", "disabled"))
    return DeviceRuntimeResolver(
        current_app.config["DATABASE_URL"],
        provider=provider,
        legacy_provider=str(current_app.config.get("CAMERA_RUNTIME_ADAPTER", provider)),
        ai_camera_test_base_url=current_app.config.get("AI_CAMERA_TEST_BASE_URL"),
        camera_backend_url=current_app.config.get("CAMERA_BACKEND_URL"),
        dev_adapters_enabled=bool(current_app.config.get("DEV_ADAPTERS_ENABLED")),
        app_env=str(current_app.config.get("APP_ENV", "production")),
        vision_service_factory=lambda: build_vision_observation_service_from_config(current_app.config),
        onvif_client=onvif_client(),
        credential_store=device_credential_store(),
        media_gateway=media_gateway_client(),
    )


def media_gateway_client() -> Go2RtcClient | None:
    if not bool(current_app.config.get("MEDIA_GATEWAY_ENABLED")) or not bool(
        current_app.config.get("TASK_WEBSOCKET_ENABLED")
    ):
        return None
    return Go2RtcClient(
        str(
            current_app.config.get("MEDIA_GATEWAY_API_BASE_URL")
            or "http://127.0.0.1:1984"
        ),
        public_base_url=(
            str(current_app.config.get("MEDIA_GATEWAY_PUBLIC_BASE_URL") or "")
            or None
        ),
        timeout_seconds=float(
            current_app.config.get("MEDIA_GATEWAY_TIMEOUT_SECONDS", 5)
        ),
    )


def camera_command_service() -> CameraCommandService:
    return CameraCommandService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        runtime_resolver=device_runtime_resolver(),
    )


def care_config_service() -> CareConfigService:
    return CareConfigService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
    )


def ai_care_reminder_service() -> AiCareReminderService:
    return AiCareReminderService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        ai_text_provider=ai_text_provider(),
        prompt_registry=prompt_registry(),
        camera_command_service=camera_command_service(),
    )


def camera_ai_observation_service() -> CameraAiObservationService:
    return CameraAiObservationService(current_app.config["DATABASE_URL"])


def camera_observe_service() -> CameraObserveService:
    return CameraObserveService(
        current_app.config["DATABASE_URL"],
        vision_service=vision_observation_service(),
        vision_prefilter=default_local_vision_prefilter(),
    )


def routine_reminder_service() -> RoutineReminderService:
    return RoutineReminderService(current_app.config["DATABASE_URL"])


def internal_request_guard() -> InternalRequestGuard:
    return InternalRequestGuard(
        current_app.config["DATABASE_URL"],
        token=current_app.config.get("INTERNAL_API_TOKEN", ""),
        allowed_sources=current_app.config.get("INTERNAL_ALLOWED_SOURCES", []),
    )


def task_runtime_service() -> TaskRuntimeService:
    return TaskRuntimeService(
        current_app.config["DATABASE_URL"],
        camera_command_service=camera_command_service(),
        ai_text_provider=ai_text_provider(),
        prompt_registry=prompt_registry(),
        reminder_lead_seconds=int(current_app.config.get("TASK_REMINDER_LEAD_SECONDS", 300)),
        delay_reminder_interval_seconds=int(
            current_app.config.get("TASK_DELAY_REMINDER_INTERVAL_SECONDS", 180)
        ),
        max_delay_reminders=int(current_app.config.get("TASK_DELAY_REMINDER_MAX_COUNT", 3)),
        monitor_enabled=bool(current_app.config.get("CAMERA_MONITOR_ENABLED", True)),
        speaker_enabled=bool(current_app.config.get("CAMERA_SPEAKER_ENABLED", True)),
    )


def sms_provider() -> SmsProvider:
    provider = str(current_app.config.get("SMS_PROVIDER", "")).strip().lower()
    if provider == "development":
        _require_dev_adapter("APP_SMS_PROVIDER=development")
        return DevelopmentSmsProvider(
            template_id=current_app.config.get("SMS_TEMPLATE_ID", "login-code"),
        )
    if provider in {"aliyun", "tencent", "twilio"}:
        return UnavailableSmsProvider(provider)
    return UnavailableSmsProvider(provider or "unconfigured")


def prompt_registry() -> PromptRegistry:
    return PromptRegistry(current_app.config["PROMPT_ROOT"])


def ai_text_provider():
    provider = str(current_app.config.get("AI_PROVIDER", "")).strip().lower()
    api_key = str(current_app.config.get("AI_API_KEY", "")).strip()
    model = str(current_app.config.get("AI_MODEL", "")).strip()
    base_url = str(current_app.config.get("AI_BASE_URL", "")).strip()
    timeout = float(current_app.config.get("AI_TIMEOUT_SECONDS", 8))
    if provider in {"moonshot", "kimi", "openai", "openai_compatible"}:
        return OpenAICompatibleTextProvider(
            provider_name="moonshot" if provider == "kimi" else provider,
            api_key=api_key,
            base_url=base_url,
            model_name=model,
            timeout_seconds=timeout,
            disable_thinking=provider in {"moonshot", "kimi"},
        )
    return UnavailableAiTextProvider()


def ai_vision_provider():
    return build_ai_vision_provider_from_config(current_app.config)


def vision_observation_service() -> VisionObservationService:
    return build_vision_observation_service_from_config(current_app.config)


def build_ai_vision_provider_from_config(config: dict):
    if not bool(config.get("AI_VISION_ENABLED", True)):
        return UnavailableVisionProvider()
    provider = str(config.get("AI_PROVIDER", "")).strip().lower()
    api_key = str(config.get("AI_API_KEY", "")).strip()
    model = str(config.get("AI_VISION_MODEL") or config.get("AI_MODEL") or "").strip()
    base_url = str(config.get("AI_BASE_URL", "")).strip()
    timeout = float(config.get("AI_VISION_TIMEOUT_SECONDS", 20))
    max_bytes = int(config.get("AI_VISION_MAX_BYTES", 524288))
    max_dimension = int(config.get("AI_VISION_MAX_DIMENSION", 1280))
    jpeg_quality = int(config.get("AI_VISION_JPEG_QUALITY", 85))
    if provider in {"moonshot", "kimi", "openai", "openai_compatible"} and api_key and base_url and model:
        # kimi-k2.6 thinking 会吃掉 max_tokens，导致 content 为空；视觉观察只需 JSON 输出。
        disable_thinking = provider in {"moonshot", "kimi"} or str(model).startswith("kimi-k")
        return OpenAICompatibleVisionProvider(
            provider_name="moonshot" if provider == "kimi" else provider,
            api_key=api_key,
            base_url=base_url,
            model_name=model,
            timeout_seconds=timeout,
            max_bytes=max_bytes,
            max_image_dimension=max_dimension,
            jpeg_quality=jpeg_quality,
            disable_thinking=disable_thinking,
        )
    return UnavailableVisionProvider()


def build_vision_observation_service_from_config(config: dict) -> VisionObservationService:
    prompt_root = str(config.get("PROMPT_ROOT") or "")
    return VisionObservationService(
        vision_provider=build_ai_vision_provider_from_config(config),
        prompt_registry=PromptRegistry(prompt_root),
        enabled=bool(config.get("AI_VISION_ENABLED", True)),
        min_interval_seconds=float(config.get("AI_VISION_MIN_INTERVAL_SECONDS", 60)),
        max_calls_per_hour=int(config.get("AI_VISION_MAX_CALLS_PER_HOUR", 20)),
        backoff_seconds=float(config.get("AI_VISION_BACKOFF_SECONDS", 300)),
    )


def hardware_adapter():
    adapter = str(current_app.config.get("HARDWARE_ADAPTER", "disabled")).lower()
    if adapter == "mock":
        _require_dev_adapter("APP_HARDWARE_ADAPTER=mock")
        return MockHardwareDeviceAdapter()
    if adapter == "disabled":
        return DisabledHardwareDeviceAdapter()
    raise ApiError("hardware_unknown_adapter", "未知硬件设备适配器。", 503)


def _require_dev_adapter(label: str) -> None:
    if current_app.config.get("DEV_ADAPTERS_ENABLED") and current_app.config.get("APP_ENV") in {
        "development",
        "test",
    }:
        return
    raise ApiError(
        "development_adapter_not_allowed",
        f"{label} 只能在 development/test profile 下启用。",
        503,
    )

def conversation_service() -> ConversationAppService:
    database_url = current_app.config["DATABASE_URL"]
    return ConversationAppService(
        database_url,
        auth_service=auth_service(),
        conversation_service=VoiceConversationService(
            database_url,
            ai_text_provider=ai_text_provider(),
            prompt_registry=prompt_registry(),
        ),
    )


def conversation_sync_service() -> ConversationSyncService:
    return ConversationSyncService(current_app.config["DATABASE_URL"])


def voice_runtime_service() -> VoiceRuntimeAppService:
    return VoiceRuntimeAppService(
        current_app.config["DATABASE_URL"],
        auth_service=auth_service(),
        sync_service=conversation_sync_service(),
    )
