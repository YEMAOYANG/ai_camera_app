from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Iterable


LEGACY_TEACHER_REGISTRY_VERSION = "mira.teacher-registry.v1"
TEACHER_REGISTRY_VERSION = "mira.teacher-registry.v2"
SUPPORTED_TEACHER_SUBJECTS = frozenset({"chinese", "math", "english"})
SUPPORTED_TTS_PROVIDER_IDS = frozenset({"voxcpm2", "macos-say"})
OPENMAIC_QWEN3_VOICE_CONTRACT_VERSION = "mira.openmaic.qwen3-voice.v1"
OPENMAIC_QWEN3_PROVIDER_ID = "qwen-tts"
OPENMAIC_QWEN3_MODEL_ID = "qwen3-tts-flash"
FORMAL_SUBJECT_QWEN_VOICE_CONTRACT_VERSION = (
    "mira.openmaic.formal-subject-qwen3-voice.v1"
)
FORMAL_QWEN_TTS_PROVIDER_ID = "qwen-tts"
FORMAL_QWEN_TTS_MODEL_ID = "qwen3-tts-flash"
FORMAL_QWEN_ASR_PROVIDER_ID = "qwen-asr"
FORMAL_QWEN_ASR_MODEL_ID = "qwen3-asr-flash"
FORMAL_RUNTIME_TEACHER_AVATARS = {
    "chinese": "/avatars/teacher-2.png",
    "math": "/avatars/teacher.png",
    "english": "/avatars/teacher-2.png",
}


@dataclass(frozen=True)
class OpenMaicQwen3VoiceIdentity:
    """Server-owned OpenMAIC Agent voice identity without credentials.

    OpenMAIC 0.3.2 stores per-Agent TTS selection as ``voiceConfig``.  API
    keys and provider base URLs remain deployment configuration and must never
    enter a course requirement, runtime manifest, or student response.
    """

    teacher_profile_id: str
    teacher_profile_version: int
    provider_id: str
    model_id: str
    voice_id: str
    display_name: str
    language_code: str

    @property
    def selection_id(self) -> str:
        return f"{self.provider_id}::{self.voice_id}"

    def to_runtime_payload(self) -> dict[str, object]:
        return {
            "schemaVersion": OPENMAIC_QWEN3_VOICE_CONTRACT_VERSION,
            "teacherProfile": {
                "id": self.teacher_profile_id,
                "version": self.teacher_profile_version,
            },
            "voiceConfig": {
                "providerId": self.provider_id,
                "modelId": self.model_id,
                "voiceId": self.voice_id,
            },
            "selectionId": self.selection_id,
            "displayName": self.display_name,
            "languageCode": self.language_code,
        }


@dataclass(frozen=True)
class FormalSubjectQwenVoiceIdentity:
    """Immutable formal-course voice authority, separate from sample voices."""

    subject: str
    teacher_profile_id: str
    teacher_profile_version: int
    teacher_profile_hash: str
    teacher_name: str
    teacher_gender: str
    voice_gender: str
    voice_id: str
    language_code: str
    tts_provider_id: str = FORMAL_QWEN_TTS_PROVIDER_ID
    tts_model_id: str = FORMAL_QWEN_TTS_MODEL_ID
    asr_provider_id: str = FORMAL_QWEN_ASR_PROVIDER_ID
    asr_model_id: str = FORMAL_QWEN_ASR_MODEL_ID
    fallback_allowed: bool = False

    def to_target_payload(self) -> dict[str, object]:
        return {
            "schemaVersion": FORMAL_SUBJECT_QWEN_VOICE_CONTRACT_VERSION,
            "teacherProfile": {
                "id": self.teacher_profile_id,
                "version": self.teacher_profile_version,
                "contentHash": self.teacher_profile_hash,
            },
            "teacherName": self.teacher_name,
            "teacherGender": self.teacher_gender,
            "voiceGender": self.voice_gender,
            "voiceId": self.voice_id,
            "languageCode": self.language_code,
            "tts": {
                "providerId": self.tts_provider_id,
                "modelId": self.tts_model_id,
                "fallbackAllowed": self.fallback_allowed,
            },
            "asr": {
                "providerId": self.asr_provider_id,
                "modelId": self.asr_model_id,
                "fallbackAllowed": self.fallback_allowed,
            },
        }


@dataclass(frozen=True)
class TeacherTtsBinding:
    """Private, per-job synthesis binding for a stable teacher identity."""

    teacher_profile_id: str
    teacher_profile_version: int
    provider_id: str
    provider_model: str

    def to_private_payload(self) -> dict[str, object]:
        return {
            "teacherProfile": {
                "id": self.teacher_profile_id,
                "version": self.teacher_profile_version,
            },
            "providerId": self.provider_id,
            "providerModel": self.provider_model,
        }


@dataclass(frozen=True)
class TeacherProfile:
    """A server-owned teaching and voice identity.

    Profiles deliberately support prompt-designed voices only.  Reference
    audio, registered voices and voice cloning are outside this registry so a
    student request can never turn into biometric voice material.
    """

    profile_id: str
    version: int
    registry_version: str
    display_name: str
    avatar_path: str
    subject: str
    language_code: str
    teaching_style: str
    provider_id: str
    provider_model: str
    voice_prompt: str
    capabilities: tuple[str, ...]

    @property
    def voice_mode(self) -> str:
        return "prompt"

    @property
    def clone_allowed(self) -> bool:
        return False

    def bind_tts_provider(
        self,
        *,
        provider_id: str | None = None,
        provider_model: str | None = None,
    ) -> TeacherTtsBinding:
        """Bind this public teacher to the actual private synthesis runtime.

        The profile id and version remain stable for students. The media job,
        however, records the provider/model that really created its audio. This
        allows a development workstation to use macOS system speech without
        claiming that VoxCPM2 generated the bytes.
        """

        normalized_provider = str(provider_id or self.provider_id).strip().lower()
        normalized_model = str(provider_model or self.provider_model).strip()
        if normalized_provider not in SUPPORTED_TTS_PROVIDER_IDS:
            raise ValueError(f"unsupported TTS provider binding: {normalized_provider}")
        if not normalized_model or len(normalized_model) > 128:
            raise ValueError("TTS provider model binding must be 1-128 characters")
        return TeacherTtsBinding(
            teacher_profile_id=self.profile_id,
            teacher_profile_version=self.version,
            provider_id=normalized_provider,
            provider_model=normalized_model,
        )

    @property
    def content_hash(self) -> str:
        return hashlib.sha256(
            json.dumps(
                self.to_storage_payload(include_hash=False),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    def to_storage_payload(self, *, include_hash: bool = True) -> dict[str, object]:
        payload: dict[str, object] = {
            "registryVersion": self.registry_version,
            "id": self.profile_id,
            "version": self.version,
            "displayName": self.display_name,
            "avatarPath": self.avatar_path,
            "subject": self.subject,
            "languageCode": self.language_code,
            "teachingStyle": self.teaching_style,
            "providerId": self.provider_id,
            "providerModel": self.provider_model,
            "voiceMode": self.voice_mode,
            "voicePrompt": self.voice_prompt,
            "capabilities": list(self.capabilities),
            "cloneAllowed": self.clone_allowed,
        }
        if include_hash:
            payload["contentHash"] = self.content_hash
        return payload

    def to_public_payload(self) -> dict[str, object]:
        """Return the student-safe profile without provider internals/prompts."""

        return {
            "id": self.profile_id,
            "version": self.version,
            "displayName": self.display_name,
            "avatarPath": self.avatar_path,
            "subject": self.subject,
            "languageCode": self.language_code,
            "teachingStyle": self.teaching_style,
            "capabilities": list(self.capabilities),
        }


TEACHER_PROFILES: tuple[TeacherProfile, ...] = (
    # Version 1 is an immutable compatibility snapshot.  Existing databases,
    # media jobs and student preferences reference these exact hashes, so even
    # private provider metadata changes require a new profile version.
    TeacherProfile(
        profile_id="mira_chinese_gentle",
        version=1,
        registry_version=LEGACY_TEACHER_REGISTRY_VERSION,
        display_name="小语老师",
        avatar_path="/teachers/mi-chinese-v1.png",
        subject="chinese",
        language_code="zh-CN",
        teaching_style="gentle_guided",
        provider_id="voxcpm2",
        provider_model="voxcpm2",
        voice_prompt=(
            "温柔、耐心、亲切的中文小学老师声音，普通话标准，语速稍慢，"
            "吐字清楚，鼓励而不过度夸张"
        ),
        capabilities=(
            "explain_then_practice",
            "guided_reading",
            "standard_mandarin",
            "pinyin_review_gated",
        ),
    ),
    TeacherProfile(
        profile_id="mira_chinese_gentle",
        version=2,
        registry_version=TEACHER_REGISTRY_VERSION,
        display_name="小语老师",
        avatar_path="/teachers/mi-chinese-v1.png",
        subject="chinese",
        language_code="zh-CN",
        teaching_style="gentle_guided",
        provider_id="voxcpm2",
        provider_model="openbmb/VoxCPM2",
        voice_prompt=(
            "温柔、耐心、亲切的中文小学老师声音，普通话标准，语速稍慢，"
            "吐字清楚，鼓励而不过度夸张"
        ),
        capabilities=(
            "explain_then_practice",
            "guided_reading",
            "standard_mandarin",
            "pinyin_review_gated",
        ),
    ),
    TeacherProfile(
        profile_id="mira_math_clear",
        version=1,
        registry_version=LEGACY_TEACHER_REGISTRY_VERSION,
        display_name="小数老师",
        avatar_path="/teachers/ashu-math-v1.png",
        subject="math",
        language_code="zh-CN",
        teaching_style="clear_structured",
        provider_id="voxcpm2",
        provider_model="voxcpm2",
        voice_prompt=(
            "清晰、沉稳、逻辑分明的中文小学数学老师声音，普通话标准，"
            "语速适中，步骤之间停顿明确，语气温和"
        ),
        capabilities=(
            "worked_examples",
            "step_by_step_reasoning",
            "standard_mandarin",
        ),
    ),
    TeacherProfile(
        profile_id="mira_math_clear",
        version=2,
        registry_version=TEACHER_REGISTRY_VERSION,
        display_name="小数老师",
        avatar_path="/teachers/ashu-math-v1.png",
        subject="math",
        language_code="zh-CN",
        teaching_style="clear_structured",
        provider_id="voxcpm2",
        provider_model="openbmb/VoxCPM2",
        voice_prompt=(
            "清晰、沉稳、逻辑分明的中文小学数学老师声音，普通话标准，"
            "语速适中，步骤之间停顿明确，语气温和"
        ),
        capabilities=(
            "worked_examples",
            "step_by_step_reasoning",
            "standard_mandarin",
        ),
    ),
    TeacherProfile(
        profile_id="mira_english_standard",
        version=1,
        registry_version=LEGACY_TEACHER_REGISTRY_VERSION,
        display_name="Mia 老师",
        avatar_path="/teachers/coco-english-v1.png",
        subject="english",
        language_code="en-US",
        teaching_style="standard_pronunciation",
        provider_id="voxcpm2",
        provider_model="voxcpm2",
        voice_prompt=(
            "standard child-friendly English teacher voice, neutral American English "
            "pronunciation, slow clear articulation, warm and encouraging"
        ),
        capabilities=(
            "listen_and_repeat",
            "phonics",
            "standard_english_pronunciation",
            "pronunciation_review_gated",
        ),
    ),
    TeacherProfile(
        profile_id="mira_english_standard",
        version=2,
        registry_version=TEACHER_REGISTRY_VERSION,
        display_name="Mia 老师",
        avatar_path="/teachers/coco-english-v1.png",
        subject="english",
        language_code="en-US",
        teaching_style="standard_pronunciation",
        provider_id="voxcpm2",
        provider_model="openbmb/VoxCPM2",
        voice_prompt=(
            "standard child-friendly English teacher voice, neutral American English "
            "pronunciation, slow clear articulation, warm and encouraging"
        ),
        capabilities=(
            "listen_and_repeat",
            "phonics",
            "standard_english_pronunciation",
            "pronunciation_review_gated",
        ),
    ),
)

_PROFILE_INDEX = {(profile.profile_id, profile.version): profile for profile in TEACHER_PROFILES}

# Stage 2 deliberately approves exactly one voice for the single
# primary_1/math/number_sense_20 full-runtime sample.  This mapping is separate
# from the controlled LessonPackage narration provider, so adding it does not
# mutate immutable teacher-profile hashes already stored in MySQL.
_OPENMAIC_QWEN3_VOICE_IDENTITIES = {
    ("mira_math_clear", 2): OpenMaicQwen3VoiceIdentity(
        teacher_profile_id="mira_math_clear",
        teacher_profile_version=2,
        provider_id=OPENMAIC_QWEN3_PROVIDER_ID,
        model_id=OPENMAIC_QWEN3_MODEL_ID,
        voice_id="Serena",
        display_name="苏瑶 (Serena)",
        language_code="zh-CN",
    ),
}

# Formal production audio is deliberately separate from the legacy sample
# runtime mapping above.  In particular, the male math teacher uses Ethan;
# the old sample remains Serena and its serialized contract is unchanged.
_FORMAL_SUBJECT_QWEN_VOICE_IDENTITIES = {
    "chinese": FormalSubjectQwenVoiceIdentity(
        subject="chinese",
        teacher_profile_id="mira_chinese_gentle",
        teacher_profile_version=2,
        teacher_profile_hash="a5fd163af249705bda4bb0be5448f65d275eb423285557727f9c50ea442f01f8",
        teacher_name="小语老师",
        teacher_gender="female",
        voice_gender="female",
        voice_id="Serena",
        language_code="zh-CN",
    ),
    "math": FormalSubjectQwenVoiceIdentity(
        subject="math",
        teacher_profile_id="mira_math_clear",
        teacher_profile_version=2,
        teacher_profile_hash="4f5a986a765f69798c8546d7f9091fe297f2a98c5353fdd01cd1aa06884c98fb",
        teacher_name="小数老师",
        teacher_gender="male",
        voice_gender="male",
        voice_id="Ethan",
        language_code="zh-CN",
    ),
    "english": FormalSubjectQwenVoiceIdentity(
        subject="english",
        teacher_profile_id="mira_english_standard",
        teacher_profile_version=2,
        teacher_profile_hash="4725f27c5438c0f68fe8923ac977fa1dd01452b990ac58912b880320750ee040",
        teacher_name="Mia 老师",
        teacher_gender="female",
        voice_gender="female",
        voice_id="Jennifer",
        language_code="en-US",
    ),
}


def get_teacher_profile(profile_id: str, version: int | None = None) -> TeacherProfile:
    normalized_id = str(profile_id or "").strip()
    if version is None:
        candidates = [profile for profile in TEACHER_PROFILES if profile.profile_id == normalized_id]
        if not candidates:
            raise KeyError(f"unknown teacher profile: {normalized_id}")
        return max(candidates, key=lambda item: item.version)
    try:
        return _PROFILE_INDEX[(normalized_id, int(version))]
    except (KeyError, TypeError, ValueError) as exc:
        raise KeyError(f"unknown teacher profile: {normalized_id}@{version}") from exc


def get_openmaic_qwen3_voice_identity(
    teacher_profile_id: str,
    teacher_profile_version: int | None = None,
) -> OpenMaicQwen3VoiceIdentity:
    """Return the approved credential-free OpenMAIC voice for a teacher."""

    profile = get_teacher_profile(teacher_profile_id, teacher_profile_version)
    try:
        return _OPENMAIC_QWEN3_VOICE_IDENTITIES[
            (profile.profile_id, profile.version)
        ]
    except KeyError as exc:
        raise KeyError(
            "teacher profile has no approved OpenMAIC Qwen3 voice identity: "
            f"{profile.profile_id}@{profile.version}"
        ) from exc


def get_formal_subject_qwen_voice_identity(
    subject: str,
) -> FormalSubjectQwenVoiceIdentity:
    normalized = str(subject or "").strip().lower()
    try:
        return _FORMAL_SUBJECT_QWEN_VOICE_IDENTITIES[normalized]
    except KeyError as exc:
        raise KeyError(f"unsupported formal subject voice: {normalized}") from exc


def get_formal_runtime_teacher_contract(subject: str) -> dict[str, object]:
    """Return the shared credential-free teacher contract for formal Runtime."""

    voice = get_formal_subject_qwen_voice_identity(subject)
    profile = get_teacher_profile(
        voice.teacher_profile_id,
        voice.teacher_profile_version,
    )
    runtime_avatar = FORMAL_RUNTIME_TEACHER_AVATARS.get(voice.subject)
    if (
        runtime_avatar is None
        or profile.subject != voice.subject
        or profile.content_hash != voice.teacher_profile_hash
        or profile.display_name != voice.teacher_name
        or profile.language_code != voice.language_code
    ):
        raise ValueError("formal teacher registry is inconsistent")
    return {
        "teacherProfile": {
            "id": profile.profile_id,
            "version": profile.version,
            "contentHash": profile.content_hash,
            "displayName": profile.display_name,
            "avatarPath": profile.avatar_path,
        },
        "runtime": {
            "name": voice.teacher_name,
            "role": "teacher",
            "avatar": runtime_avatar,
            "teacherGender": voice.teacher_gender,
            "voiceGender": voice.voice_gender,
            "voiceConfig": {
                "providerId": voice.tts_provider_id,
                "modelId": voice.tts_model_id,
                "voiceId": voice.voice_id,
            },
        },
    }


def list_teacher_profiles(
    *,
    subject: str | None = None,
    language_code: str | None = None,
    include_legacy_versions: bool = False,
) -> tuple[TeacherProfile, ...]:
    subject_code = str(subject or "").strip().lower()
    language = str(language_code or "").strip().casefold()
    matches = tuple(
        profile
        for profile in TEACHER_PROFILES
        if (not subject_code or profile.subject == subject_code)
        and (not language or profile.language_code.casefold() == language)
    )
    if include_legacy_versions:
        return matches
    latest_versions = {
        profile.profile_id: max(
            candidate.version
            for candidate in matches
            if candidate.profile_id == profile.profile_id
        )
        for profile in matches
    }
    return tuple(
        profile
        for profile in matches
        if profile.version == latest_versions[profile.profile_id]
    )


def validate_teacher_registry(profiles: Iterable[TeacherProfile] = TEACHER_PROFILES) -> None:
    seen: set[tuple[str, int]] = set()
    covered_subjects: set[str] = set()
    for profile in profiles:
        key = (profile.profile_id, profile.version)
        if key in seen:
            raise ValueError(f"duplicate teacher profile: {key}")
        seen.add(key)
        covered_subjects.add(profile.subject)
        if profile.subject not in SUPPORTED_TEACHER_SUBJECTS:
            raise ValueError(f"unsupported teacher subject: {profile.subject}")
        if not profile.registry_version.strip():
            raise ValueError(f"teacher profile registry version is required: {key}")
        if profile.voice_mode != "prompt" or profile.clone_allowed:
            raise ValueError(f"teacher profile must forbid voice cloning: {key}")
        if not profile.voice_prompt.strip() or not profile.capabilities:
            raise ValueError(f"incomplete teacher profile: {key}")
        if not profile.avatar_path.startswith("/teachers/") or ".." in profile.avatar_path:
            raise ValueError(f"invalid teacher avatar path: {key}")
    if covered_subjects != SUPPORTED_TEACHER_SUBJECTS:
        raise ValueError("teacher registry must cover chinese, math, and english")


def validate_openmaic_qwen3_voice_registry() -> None:
    for key, identity in _OPENMAIC_QWEN3_VOICE_IDENTITIES.items():
        profile = _PROFILE_INDEX.get(key)
        if profile is None:
            raise ValueError(f"OpenMAIC voice references an unknown profile: {key}")
        if (
            identity.teacher_profile_id != profile.profile_id
            or identity.teacher_profile_version != profile.version
            or identity.provider_id != OPENMAIC_QWEN3_PROVIDER_ID
            or identity.model_id != OPENMAIC_QWEN3_MODEL_ID
            or not identity.voice_id.strip()
            or identity.language_code != profile.language_code
        ):
            raise ValueError(f"invalid OpenMAIC Qwen3 voice identity: {key}")
        payload = identity.to_runtime_payload()
        serialized = json.dumps(payload, ensure_ascii=False).casefold()
        if "apikey" in serialized or "api_key" in serialized or "baseurl" in serialized:
            raise ValueError(f"OpenMAIC voice identity contains deployment secrets: {key}")


def validate_formal_subject_qwen_voice_registry(
    identities: dict[str, FormalSubjectQwenVoiceIdentity] | None = None,
) -> None:
    registry = (
        _FORMAL_SUBJECT_QWEN_VOICE_IDENTITIES
        if identities is None
        else identities
    )
    if set(registry) != SUPPORTED_TEACHER_SUBJECTS:
        raise ValueError("formal voice registry must cover chinese, math, and english")
    expected = _FORMAL_SUBJECT_QWEN_VOICE_IDENTITIES
    for subject, identity in registry.items():
        if identity != expected[subject]:
            raise ValueError(f"formal subject voice identity is not frozen: {subject}")
        profile = _PROFILE_INDEX.get(
            (identity.teacher_profile_id, identity.teacher_profile_version)
        )
        if (
            profile is None
            or profile.subject != subject
            or profile.display_name != identity.teacher_name
            or profile.language_code != identity.language_code
            or profile.content_hash != identity.teacher_profile_hash
            or identity.teacher_gender != identity.voice_gender
            or identity.teacher_gender not in {"female", "male"}
            or identity.tts_provider_id != FORMAL_QWEN_TTS_PROVIDER_ID
            or identity.tts_model_id != FORMAL_QWEN_TTS_MODEL_ID
            or identity.asr_provider_id != FORMAL_QWEN_ASR_PROVIDER_ID
            or identity.asr_model_id != FORMAL_QWEN_ASR_MODEL_ID
            or identity.fallback_allowed
        ):
            raise ValueError(f"invalid formal subject voice identity: {subject}")


validate_teacher_registry()
validate_openmaic_qwen3_voice_registry()
validate_formal_subject_qwen_voice_registry()
