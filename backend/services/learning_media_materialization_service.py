from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
import re
import struct
import unicodedata
from typing import Any, Callable, Mapping, Sequence
import uuid

from content.teacher_profiles import (
    FormalSubjectQwenVoiceIdentity,
    SUPPORTED_TEACHER_SUBJECTS,
    get_formal_subject_qwen_voice_identity,
    get_teacher_profile,
)
from core.security import now_ms
from core.database import DatabaseConnection
from repositories.learning_teacher_media_repository import (
    LearningTeacherMediaRepository,
)
from integrations.openmaic_full_runtime_client import (
    OpenMaicFormalAudioReceipt,
    OpenMaicFormalAudioSegmentReceipt,
    OpenMaicFullRuntimeClient,
    OpenMaicFullRuntimeError,
)
from services.learning_media_asset_store import LearningMediaAssetStore
from services.tts_provider import (
    TtsProvider,
    TtsProviderError,
    TtsSynthesisRequest,
)


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")
_PRONUNCIATION_KINDS = frozenset({"general", "pinyin", "english"})
_FORMAL_WAV_MAX_BYTES = 16 * 1024 * 1024
_FORMAL_MAX_SCENE_COUNT = 60
_FORMAL_MAX_SPEECH_ACTIONS_PER_SCENE = 20
_FORMAL_MAX_SPEECH_ACTIONS = 240
_FORMAL_SPEECH_TEXT_POLICY_VERSION = "mira.learning.formal-speech-text.v2"
_CHINESE_LATIN_TOKEN_PATTERN = re.compile(r"(?<![A-Za-z])([A-Za-z]+)(?![A-Za-z])")
_CHINESE_PINYIN_SPOKEN_TOKENS = {
    "a": "啊",
    "o": "喔",
    "e": "鹅",
    "i": "衣",
    "u": "乌",
    "b": "波",
    "p": "坡",
    "m": "摸",
    "f": "佛",
    "d": "得",
    "t": "特",
    "n": "讷",
    "l": "勒",
    "g": "哥",
    "k": "科",
    "h": "喝",
    "j": "鸡",
    "q": "七",
    "x": "西",
    "zh": "知",
    "ch": "吃",
    "sh": "诗",
    "r": "日",
    "z": "资",
    "c": "次",
    "s": "思",
    "y": "衣",
    "w": "乌",
    "ba": "八",
    "che": "车",
}
_CHINESE_DIGITS = "零一二三四五六七八九"
_CHINESE_NUMBER_PATTERN = re.compile(r"\d+")


@dataclass(frozen=True)
class FormalWavEvidence:
    readback_sha256: str
    byte_size: int
    pcm_format: int
    channel_count: int
    bits_per_sample: int
    sample_rate_hz: int
    block_align: int
    byte_rate: int
    frame_count: int
    duration_ms: int
    normalized_peak_bps: int
    overall_rms_bps: int
    active_window_bps: int


def validate_formal_wav(
    audio: bytes,
    *,
    mime_type: str,
    runtime_sha256: str,
    download_sha256: str,
    streamed_sha256: str,
) -> FormalWavEvidence:
    """Validate final-storage bytes against the frozen formal PCM contract."""

    if not isinstance(audio, bytes) or not 44 <= len(audio) <= _FORMAL_WAV_MAX_BYTES:
        raise LearningMediaMaterializationError(
            "formal_audio_size_invalid", "语音文件大小不符合要求"
        )
    if str(mime_type or "").strip().lower() != "audio/wav":
        raise LearningMediaMaterializationError(
            "formal_audio_mime_invalid", "语音文件格式不符合要求"
        )
    readback_sha256 = hashlib.sha256(audio).hexdigest()
    hashes = (
        str(runtime_sha256 or ""),
        str(download_sha256 or ""),
        str(streamed_sha256 or ""),
        readback_sha256,
    )
    if any(re.fullmatch(r"[0-9a-f]{64}", item) is None for item in hashes) or len(set(hashes)) != 1:
        raise LearningMediaMaterializationError(
            "formal_audio_hash_mismatch", "语音文件完整性校验失败"
        )
    if audio[:4] != b"RIFF" or audio[8:12] != b"WAVE":
        raise LearningMediaMaterializationError(
            "formal_audio_riff_invalid", "语音文件容器无效"
        )
    if struct.unpack_from("<I", audio, 4)[0] != len(audio) - 8:
        raise LearningMediaMaterializationError(
            "formal_audio_riff_size_invalid", "语音文件容器长度无效"
        )

    chunks: dict[bytes, list[bytes]] = {b"fmt ": [], b"data": []}
    offset = 12
    while offset < len(audio):
        if offset + 8 > len(audio):
            raise LearningMediaMaterializationError(
                "formal_audio_chunk_invalid", "语音文件数据块无效"
            )
        chunk_id = audio[offset:offset + 4]
        chunk_size = struct.unpack_from("<I", audio, offset + 4)[0]
        start = offset + 8
        end = start + chunk_size
        padded_end = end + (chunk_size & 1)
        if end > len(audio) or padded_end > len(audio):
            raise LearningMediaMaterializationError(
                "formal_audio_chunk_size_invalid", "语音文件数据块长度无效"
            )
        if chunk_id in chunks:
            chunks[chunk_id].append(audio[start:end])
        offset = padded_end
    if offset != len(audio) or len(chunks[b"fmt "]) != 1 or len(chunks[b"data"]) != 1:
        raise LearningMediaMaterializationError(
            "formal_audio_chunk_inventory_invalid", "语音文件数据块不完整"
        )

    fmt = chunks[b"fmt "][0]
    pcm = chunks[b"data"][0]
    if len(fmt) < 16:
        raise LearningMediaMaterializationError(
            "formal_audio_fmt_invalid", "语音文件 PCM 头无效"
        )
    pcm_format, channels, sample_rate, byte_rate, block_align, bits = struct.unpack_from(
        "<HHIIHH", fmt, 0
    )
    if not (
        pcm_format == 1
        and channels == 1
        and bits == 16
        and 16_000 <= sample_rate <= 48_000
        and block_align == 2
        and byte_rate == sample_rate * block_align
        and len(pcm) > 0
        and len(pcm) % block_align == 0
    ):
        raise LearningMediaMaterializationError(
            "formal_audio_pcm_invalid", "语音文件 PCM 参数不符合要求"
        )
    frame_count = len(pcm) // block_align
    duration_ms = frame_count * 1000 // sample_rate
    if not 300 <= duration_ms <= 120_000:
        raise LearningMediaMaterializationError(
            "formal_audio_duration_invalid", "语音文件时长不符合要求"
        )

    samples = [item[0] for item in struct.iter_unpack("<h", pcm)]
    peak = max(abs(sample) for sample in samples) / 32768.0
    rms = math.sqrt(sum((sample / 32768.0) ** 2 for sample in samples) / len(samples))
    window_frames = max(1, sample_rate * 20 // 1000)
    total_windows = (len(samples) + window_frames - 1) // window_frames
    active_windows = 0
    for start in range(0, len(samples), window_frames):
        window = samples[start:start + window_frames]
        window_rms = math.sqrt(
            sum((sample / 32768.0) ** 2 for sample in window) / len(window)
        )
        if window_rms >= 0.005:
            active_windows += 1
    peak_bps = int(peak * 10_000)
    rms_bps = int(rms * 10_000)
    active_bps = active_windows * 10_000 // total_windows
    if peak_bps < 100 or rms_bps < 30 or active_bps < 500:
        raise LearningMediaMaterializationError(
            "formal_audio_silence_invalid", "语音文件未通过非静音校验"
        )
    return FormalWavEvidence(
        readback_sha256=readback_sha256,
        byte_size=len(audio),
        pcm_format=pcm_format,
        channel_count=channels,
        bits_per_sample=bits,
        sample_rate_hz=sample_rate,
        block_align=block_align,
        byte_rate=byte_rate,
        frame_count=frame_count,
        duration_ms=duration_ms,
        normalized_peak_bps=peak_bps,
        overall_rms_bps=rms_bps,
        active_window_bps=active_bps,
    )


def normalize_asr_text(value: object) -> str:
    normalized = unicodedata.normalize("NFKC", str(value or "")).casefold()
    return "".join(
        char for char in normalized if unicodedata.category(char)[:1] in {"L", "N"}
    )


def asr_similarity_bps(expected: object, actual: object) -> int:
    left = normalize_asr_text(expected)
    right = normalize_asr_text(actual)
    if not left or not right:
        return 0
    if len(left) < len(right):
        left, right = right, left
    previous = list(range(len(right) + 1))
    for left_index, left_char in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_char in enumerate(right, start=1):
            current.append(
                min(
                    current[-1] + 1,
                    previous[right_index] + 1,
                    previous[right_index - 1] + (left_char != right_char),
                )
            )
        previous = current
    distance = previous[-1]
    denominator = max(len(left), len(right))
    return max(0, (denominator - distance) * 10_000 // denominator)


def prepare_formal_speech_text(value: object, *, subject: str) -> str:
    """Convert displayed pinyin symbols into deterministic spoken Mandarin."""

    text = str(value or "").strip()
    if subject != "chinese" or not text:
        return text

    def replace(match: re.Match[str]) -> str:
        token = match.group(1)
        return _CHINESE_PINYIN_SPOKEN_TOKENS.get(token.casefold(), token)

    return _CHINESE_LATIN_TOKEN_PATTERN.sub(replace, text)


def _small_integer_to_spoken_chinese(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value)
    if len(normalized) > 1 and normalized.startswith("0"):
        return "".join(_CHINESE_DIGITS[int(char)] for char in normalized)
    number = int(normalized)
    if number > 9_999:
        return "".join(_CHINESE_DIGITS[int(char)] for char in normalized)
    if number < 10:
        return _CHINESE_DIGITS[number]
    units = ((1_000, "千"), (100, "百"), (10, "十"))
    remaining = number
    parts: list[str] = []
    pending_zero = False
    for unit, label in units:
        digit, remaining = divmod(remaining, unit)
        if digit:
            if pending_zero:
                parts.append("零")
                pending_zero = False
            if not (unit == 10 and digit == 1 and not parts):
                parts.append(_CHINESE_DIGITS[digit])
            parts.append(label)
        elif parts and remaining:
            pending_zero = True
    if remaining:
        if pending_zero:
            parts.append("零")
        parts.append(_CHINESE_DIGITS[remaining])
    return "".join(parts)


def prepare_formal_asr_comparison_text(value: object, *, subject: str) -> str:
    """Canonicalize equivalent pinyin, numbers and basic math speech."""

    text = prepare_formal_speech_text(
        unicodedata.normalize("NFKC", str(value or "")), subject=subject
    )
    if subject not in {"chinese", "math"}:
        return text
    text = _CHINESE_NUMBER_PATTERN.sub(
        lambda match: _small_integer_to_spoken_chinese(match.group(0)), text
    )
    text = text.replace("+", "加").replace("=", "等于")
    text = text.replace("×", "乘").replace("*", "乘")
    text = text.replace("÷", "除以")
    number_chars = _CHINESE_DIGITS + "十百千"
    text = re.sub(
        rf"(?<=[{number_chars}])-(?=[{number_chars}])", "减", text
    )
    text = re.sub(
        rf"(?<=[{number_chars}])/(?=[{number_chars}])", "除以", text
    )
    return text


def build_formal_speech_manifest(
    classroom: Mapping[str, Any],
    *,
    build_item_id: str,
    voice: FormalSubjectQwenVoiceIdentity,
) -> dict[str, Any]:
    """Build a deterministic sidecar without mutating the Runtime classroom."""

    stage = classroom.get("stage")
    scenes = classroom.get("scenes")
    if (
        not isinstance(stage, Mapping)
        or not isinstance(scenes, list)
        or not 1 <= len(scenes) <= _FORMAL_MAX_SCENE_COUNT
    ):
        raise LearningMediaMaterializationError(
            "formal_audio_classroom_invalid", "正式课堂场景数量无效"
        )
    normalized_build_item_id = str(build_item_id or "").strip()
    if _ID_PATTERN.fullmatch(normalized_build_item_id) is None:
        raise LearningMediaMaterializationError(
            "formal_audio_build_item_invalid", "正式语音课程标识无效"
        )
    classroom_sha256 = hashlib.sha256(
        json.dumps(
            {"stage": stage, "scenes": scenes},
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    ).hexdigest()
    segments: list[dict[str, Any]] = []
    seen_scene_ids: set[str] = set()
    seen_action_ids: set[str] = set()
    for expected_scene_order, scene in enumerate(scenes):
        if not isinstance(scene, Mapping) or type(scene.get("order")) is not int or scene["order"] != expected_scene_order:
            raise LearningMediaMaterializationError(
                "formal_audio_scene_order_invalid", "正式语音场景顺序无效"
            )
        scene_id = str(scene.get("id") or "").strip()
        actions = scene.get("actions")
        speeches = (
            [action for action in actions if isinstance(action, Mapping) and action.get("type") == "speech"]
            if isinstance(actions, list)
            else []
        )
        if (
            not scene_id
            or scene_id in seen_scene_ids
            or not 1 <= len(speeches) <= _FORMAL_MAX_SPEECH_ACTIONS_PER_SCENE
        ):
            raise LearningMediaMaterializationError(
                "formal_audio_speech_count_invalid",
                "每个正式课堂场景必须包含 1 到 20 段讲解",
            )
        seen_scene_ids.add(scene_id)
        for speech in speeches:
            segment_order = len(segments)
            action_id = str(speech.get("id") or "").strip()
            source_text = str(speech.get("text") or "").strip()
            text = prepare_formal_speech_text(source_text, subject=voice.subject)
            if not action_id or action_id in seen_action_ids or not source_text or not text:
                raise LearningMediaMaterializationError(
                    "formal_audio_speech_invalid", "正式课堂讲解内容无效"
                )
            if segment_order >= _FORMAL_MAX_SPEECH_ACTIONS:
                raise LearningMediaMaterializationError(
                    "formal_audio_speech_count_invalid",
                    "正式课堂全课讲解段数不能超过 240",
                )
            seen_action_ids.add(action_id)
            source_text_sha256 = hashlib.sha256(source_text.encode("utf-8")).hexdigest()
            text_sha256 = hashlib.sha256(text.encode("utf-8")).hexdigest()
            identity = (
                f"{normalized_build_item_id}:{segment_order}:{scene_id}:{action_id}:"
                f"{_FORMAL_SPEECH_TEXT_POLICY_VERSION}:{text_sha256}"
            )
            identity_digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
            segments.append(
                {
                    # v3 formal audio keeps the v2 wire field name, but its
                    # value is the global speech-segment ordinal.
                    "sceneOrder": segment_order,
                    "sceneId": scene_id,
                    "actionId": action_id,
                    "narrationSegmentId": f"formal_narration_{identity_digest[:48]}",
                    "ttsRequestId": f"formal_tts_{identity_digest[:48]}",
                    "asrRequestId": f"formal_asr_{identity_digest[:48]}",
                    "sourceTextSha256": source_text_sha256,
                    "speechTextPolicyVersion": _FORMAL_SPEECH_TEXT_POLICY_VERSION,
                    "text": text,
                    "textSha256": text_sha256,
                    "teacherProfileId": voice.teacher_profile_id,
                    "teacherProfileVersion": voice.teacher_profile_version,
                    "teacherProfileSha256": voice.teacher_profile_hash,
                    "teacherGender": voice.teacher_gender,
                    "voiceId": voice.voice_id,
                    "languageCode": voice.language_code,
                }
            )
    manifest: dict[str, Any] = {
        "schemaVersion": "mira.learning.formal-qwen-audio-sidecar.v1",
        "buildItemId": normalized_build_item_id,
        "classroomContentSha256": classroom_sha256,
        "voiceContract": voice.to_target_payload(),
        "speechTextPolicyVersion": _FORMAL_SPEECH_TEXT_POLICY_VERSION,
        "expectedSegmentCount": len(segments),
        "segments": segments,
    }
    manifest["speechManifestSha256"] = hashlib.sha256(
        json.dumps(
            manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        ).encode("utf-8")
    ).hexdigest()
    return manifest


class LearningMediaMaterializationError(RuntimeError):
    def __init__(self, code: str, safe_message: str):
        super().__init__(safe_message)
        self.code = code
        self.safe_message = safe_message


@dataclass(frozen=True)
class NarrationSegmentSpec:
    text: str
    subtitle: str | None = None
    scene_id: str | None = None
    action_id: str | None = None


class FormalQwenAudioService:
    """Import OpenMAIC-owned formal audio without dispatching Provider work."""

    CLAIM_WINDOW_MS = 65 * 60 * 1000

    def __init__(
        self,
        repository: LearningTeacherMediaRepository,
        *,
        runtime_client: OpenMaicFullRuntimeClient,
        asset_store: LearningMediaAssetStore,
        clock: Callable[[], int] = now_ms,
    ):
        self.repository = repository
        self.runtime_client = runtime_client
        self.asset_store = asset_store
        self.clock = clock

    def process_next(
        self,
        *,
        build_id: str | None = None,
        release_id: str | None = None,
        target_fingerprint: str | None = None,
    ) -> dict[str, Any] | None:
        """Reserve at most one classroom, then completely process one job."""

        scoped = any(
            value is not None
            for value in (build_id, release_id, target_fingerprint)
        )
        if scoped and not all(
            isinstance(value, str) and bool(value)
            for value in (build_id, release_id, target_fingerprint)
        ):
            raise ValueError("formal audio processing scope is incomplete")
        timestamp = int(self.clock())
        with self.repository.transaction() as conn:
            stale = self.repository.terminalize_stale_formal_audio_jobs(
                conn, now=timestamp
            )
        reserved = self._reserve_next_classroom(
            build_id=build_id,
            release_id=release_id,
            target_fingerprint=target_fingerprint,
        )
        claim_now = max(timestamp, int(self.clock()))
        with self.repository.transaction() as conn:
            pending = self.repository.get_next_pending_formal_audio_job(
                conn,
                build_id=build_id,
                release_id=release_id,
                target_fingerprint=target_fingerprint,
            )
            if pending is None:
                return {
                    "state": "idle",
                    "reserved": reserved,
                    "staleAmbiguous": stale,
                } if reserved or stale else None
            build_item_id = str(pending["build_item_id"])
            claim_token = f"formal_audio_claim_{uuid.uuid4().hex}"
            claimed = self.repository.claim_formal_audio_job(
                conn,
                build_item_id=build_item_id,
                claim_token=claim_token,
                claim_deadline_at=claim_now + self.CLAIM_WINDOW_MS,
                now=claim_now,
            )
        if not claimed:
            return {"state": "busy", "buildItemId": build_item_id}
        return self._process_claimed_job(
            build_item_id=build_item_id,
            claim_token=claim_token,
        )

    def _reserve_next_classroom(
        self,
        *,
        build_id: str | None,
        release_id: str | None,
        target_fingerprint: str | None,
    ) -> bool:
        with self.repository.transaction() as conn:
            authority = self.repository.get_next_unreserved_formal_audio_authority(
                conn,
                build_id=build_id,
                release_id=release_id,
                target_fingerprint=target_fingerprint,
            )
        if authority is None:
            return False
        build_item_id = str(authority["build_item_id"])
        voice = get_formal_subject_qwen_voice_identity(str(authority["subject"]))
        classroom = self.runtime_client.get_classroom(
            str(authority["upstream_classroom_id"])
        )
        manifest = build_formal_speech_manifest(
            classroom, build_item_id=build_item_id, voice=voice
        )
        with self.repository.transaction() as conn:
            _job, created = self.repository.reserve_formal_audio_job(
                conn,
                build_item_id=build_item_id,
                classroom_content_sha256=str(
                    manifest["classroomContentSha256"]
                ),
                speech_manifest=manifest,
                voice=voice,
                now=int(self.clock()),
            )
        return bool(created)

    def _process_claimed_job(
        self, *, build_item_id: str, claim_token: str
    ) -> dict[str, Any]:
        with self.repository.transaction() as conn:
            job = self.repository.get_formal_audio_job(
                conn, build_item_id=build_item_id
            )
        if job is None:
            raise RuntimeError("formal audio job disappeared after claim")
        try:
            classroom = self.runtime_client.get_classroom(
                str(job["upstream_classroom_id"])
            )
            generation_job = self.runtime_client.get_generation_job_by_request_id(
                str(job["runtime_request_id"])
            )
            voice = get_formal_subject_qwen_voice_identity(str(job["subject"]))
            manifest = build_formal_speech_manifest(
                classroom, build_item_id=build_item_id, voice=voice
            )
        except Exception:
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=0,
                claim_token=claim_token,
                outcome="ambiguous",
                code="formal_audio_classroom_observation_ambiguous",
            )
        formal_audio = (
            generation_job.formal_audio
            if generation_job is not None
            and generation_job.status == "succeeded"
            and str(generation_job.classroom_id or "")
            == str(job["upstream_classroom_id"])
            else None
        )
        if formal_audio is None:
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=0,
                claim_token=claim_token,
                outcome="failed",
                code="formal_audio_v2_receipt_missing",
            )
        if (
            str(manifest.get("classroomContentSha256") or "")
            != str(job.get("classroom_content_sha256") or "")
            or str(manifest.get("speechManifestSha256") or "")
            != str(job.get("speech_manifest_sha256") or "")
            or not self._receipt_matches_authority(
                formal_audio,
                job=job,
                manifest=manifest,
            )
        ):
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=0,
                claim_token=claim_token,
                outcome="failed",
                code="formal_audio_classroom_contract_drift",
            )
        segment_specs = {
            int(item["sceneOrder"]): item for item in manifest["segments"]
        }
        expected_segment_count = int(job.get("expected_segment_count") or 0)
        if not 1 <= expected_segment_count <= _FORMAL_MAX_SPEECH_ACTIONS:
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=0,
                claim_token=claim_token,
                outcome="failed",
                code="formal_audio_expected_segment_count_invalid",
            )
        for scene_order in range(expected_segment_count):
            result = self._process_segment(
                job=job,
                segment_spec=segment_specs[scene_order],
                receipt_segment=formal_audio.segments[scene_order],
                claim_token=claim_token,
            )
            if result is not None:
                return result
        with self.repository.transaction() as conn:
            terminal = self.repository.get_formal_audio_job(
                conn, build_item_id=build_item_id
            )
        if terminal is None:
            raise RuntimeError("formal audio job disappeared after processing")
        return self._safe_job_result(terminal)

    def _process_segment(
        self,
        *,
        job: Mapping[str, Any],
        segment_spec: Mapping[str, Any],
        receipt_segment: OpenMaicFormalAudioSegmentReceipt,
        claim_token: str,
    ) -> dict[str, Any] | None:
        build_item_id = str(job["build_item_id"])
        scene_order = int(segment_spec["sceneOrder"])
        with self.repository.transaction() as conn:
            segment = self.repository.get_formal_audio_segment(
                conn,
                build_item_id=build_item_id,
                scene_order=scene_order,
            )
        if segment is None:
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                outcome="failed",
                code="formal_audio_segment_missing",
            )
        state = str(segment.get("state") or "")
        if state == "auto_validated":
            return None
        if state != "pending":
            # Provider work is already complete in OpenMAIC.  An interrupted
            # local import still fails closed instead of mutating partial 058
            # evidence or redispatching Provider work.
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                outcome="ambiguous",
                code="formal_audio_interrupted_attempt_ambiguous",
            )

        tts_payload = self._tts_payload(job, segment_spec)
        tts_request_sha256 = self._hash_payload(tts_payload)
        if (
            tts_request_sha256 != str(segment["tts_request_sha256"])
            or tts_request_sha256 != receipt_segment.tts.request_sha256
            or str(segment["tts_request_id"])
            != receipt_segment.tts.request_id
        ):
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                outcome="failed",
                code="formal_tts_request_contract_drift",
            )
        with self.repository.transaction() as conn:
            attempted = self.repository.begin_formal_tts_attempt(
                conn,
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                request_sha256=tts_request_sha256,
                now=int(self.clock()),
            )
        if not attempted:
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                outcome="ambiguous",
                code="formal_tts_attempt_replay_ambiguous",
            )
        audio_sha256 = receipt_segment.tts.audio_sha256
        with self.repository.transaction() as conn:
            self.repository.complete_formal_tts_attempt(
                conn,
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                request_sha256=tts_request_sha256,
                runtime_audio_sha256=audio_sha256,
                provider_media_url_sha256=None,
                now=int(self.clock()),
            )

        try:
            audio = self.runtime_client.download_formal_audio_tts(
                receipt_segment.tts.request_id,
                expected_sha256=audio_sha256,
            )
            if len(audio) != receipt_segment.tts.size_bytes:
                raise LearningMediaMaterializationError(
                    "formal_audio_download_size_mismatch",
                    "OpenMAIC 正式语音大小与回执不一致",
                )
            write_completed_at = int(self.clock())
            stored = self.asset_store.put_audio(
                job_id=build_item_id,
                segment_id=str(segment["narration_segment_id"]),
                content_hash=audio_sha256,
                mime_type="audio/wav",
                audio=audio,
            )
            readback = self.asset_store.read_audio(stored.storage_key)
            readback_completed_at = int(self.clock())
        except Exception as exc:
            outcome = (
                "ambiguous"
                if isinstance(exc, OpenMaicFullRuntimeError)
                and "ambiguous" in exc.code
                else "failed"
            )
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                outcome=outcome,
                code=(
                    "formal_audio_download_ambiguous"
                    if outcome == "ambiguous"
                    else "formal_audio_storage_failed"
                ),
            )
        with self.repository.transaction() as conn:
            asset_id = self.repository.record_formal_audio_write(
                conn,
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                storage_key=stored.storage_key,
                audio_sha256=audio_sha256,
                byte_size=len(readback),
                write_completed_at=write_completed_at,
                readback_completed_at=readback_completed_at,
                now=max(readback_completed_at, int(self.clock())),
            )
        try:
            evidence = validate_formal_wav(
                readback,
                mime_type="audio/wav",
                runtime_sha256=audio_sha256,
                download_sha256=hashlib.sha256(audio).hexdigest(),
                streamed_sha256=stored.content_hash,
            )
        except LearningMediaMaterializationError as exc:
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                outcome="failed",
                code=exc.code,
            )
        with self.repository.transaction() as conn:
            self.repository.complete_formal_audio_validation(
                conn,
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                asset_id=asset_id,
                evidence=asdict(evidence),
                now=int(self.clock()),
            )

        asr_payload = self._asr_payload(
            job, segment_spec, audio_sha256=audio_sha256
        )
        asr_request_sha256 = self._hash_payload(asr_payload)
        if (
            asr_request_sha256 != receipt_segment.asr.request_sha256
            or str(segment["asr_request_id"])
            != receipt_segment.asr.request_id
        ):
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                outcome="failed",
                code="formal_asr_request_contract_drift",
            )
        with self.repository.transaction() as conn:
            attempted = self.repository.begin_formal_asr_attempt(
                conn,
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                request_sha256=asr_request_sha256,
                now=int(self.clock()),
            )
        if not attempted:
            return self._terminalize(
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                outcome="ambiguous",
                code="formal_asr_attempt_replay_ambiguous",
            )
        similarity = receipt_segment.asr.similarity_bps
        with self.repository.transaction() as conn:
            _job, completed = self.repository.complete_formal_asr_pass(
                conn,
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                request_sha256=asr_request_sha256,
                transcript_sha256=receipt_segment.asr.transcript_sha256,
                normalized_transcript_sha256=(
                    receipt_segment.asr.normalized_transcript_sha256
                ),
                similarity_bps=similarity,
                now=int(self.clock()),
            )
        if similarity < 8_500:
            return self._safe_job_result(_job)
        return self._safe_job_result(_job) if completed else None

    @staticmethod
    def _receipt_matches_authority(
        receipt: OpenMaicFormalAudioReceipt,
        *,
        job: Mapping[str, Any],
        manifest: Mapping[str, Any],
    ) -> bool:
        segments = manifest.get("segments")
        expected_segment_count = int(job.get("expected_segment_count") or 0)
        if (
            not 1 <= expected_segment_count <= _FORMAL_MAX_SPEECH_ACTIONS
            or not isinstance(segments, list)
            or len(segments) != expected_segment_count
        ):
            return False
        if not (
            receipt.build_item_id == str(job.get("build_item_id") or "")
            and receipt.classroom_id
            == str(job.get("upstream_classroom_id") or "")
            and receipt.classroom_content_sha256
            == str(job.get("classroom_content_sha256") or "")
            == str(manifest.get("classroomContentSha256") or "")
            and receipt.subject == str(job.get("subject") or "")
            and receipt.speech_text_policy_version
            == str(manifest.get("speechTextPolicyVersion") or "")
            and receipt.teacher_profile_id
            == str(job.get("teacher_profile_id") or "")
            and receipt.teacher_profile_version
            == int(job.get("teacher_profile_version") or 0)
            and receipt.teacher_profile_sha256
            == str(job.get("teacher_profile_hash") or "")
            and receipt.teacher_gender == str(job.get("teacher_gender") or "")
            and receipt.expected_segment_count == expected_segment_count
            and receipt.tts_succeeded_count == expected_segment_count
            and receipt.asr_passed_count == expected_segment_count
            and len(receipt.segments) == expected_segment_count
        ):
            return False
        for expected_order, (expected, observed) in enumerate(
            zip(segments, receipt.segments)
        ):
            if not isinstance(expected, Mapping) or not (
                observed.scene_order == expected_order
                and observed.scene_id == str(expected.get("sceneId") or "")
                and observed.action_id == str(expected.get("actionId") or "")
                and observed.narration_segment_id
                == str(expected.get("narrationSegmentId") or "")
                and observed.source_text_sha256
                == str(expected.get("sourceTextSha256") or "")
                and observed.text_sha256
                == str(expected.get("textSha256") or "")
                and observed.tts.request_id
                == str(expected.get("ttsRequestId") or "")
                and observed.asr.request_id
                == str(expected.get("asrRequestId") or "")
                and observed.tts.voice_id
                == str(expected.get("voiceId") or "")
            ):
                return False
        return True

    @staticmethod
    def _tts_payload(
        job: Mapping[str, Any], segment: Mapping[str, Any]
    ) -> dict[str, Any]:
        return {
            "request_id": str(segment["ttsRequestId"]),
            "classroom_id": str(job["upstream_classroom_id"]),
            "classroom_content_sha256": str(job["classroom_content_sha256"]),
            "subject": str(job["subject"]),
            "teacher_profile_id": str(job["teacher_profile_id"]),
            "teacher_profile_version": int(job["teacher_profile_version"]),
            "teacher_profile_sha256": str(job["teacher_profile_hash"]),
            "teacher_gender": str(job["teacher_gender"]),
            "scene_id": str(segment["sceneId"]),
            "scene_order": int(segment["sceneOrder"]),
            "action_id": str(segment["actionId"]),
            "narration_segment_id": str(segment["narrationSegmentId"]),
            "text": str(segment["text"]),
            "text_sha256": str(segment["textSha256"]),
        }

    @staticmethod
    def _asr_payload(
        job: Mapping[str, Any], segment: Mapping[str, Any], *, audio_sha256: str
    ) -> dict[str, Any]:
        return {
            "request_id": str(segment["asrRequestId"]),
            "tts_request_id": str(segment["ttsRequestId"]),
            "classroom_id": str(job["upstream_classroom_id"]),
            "classroom_content_sha256": str(job["classroom_content_sha256"]),
            "subject": str(job["subject"]),
            "teacher_profile_id": str(job["teacher_profile_id"]),
            "teacher_profile_version": int(job["teacher_profile_version"]),
            "teacher_profile_sha256": str(job["teacher_profile_hash"]),
            "teacher_gender": str(job["teacher_gender"]),
            "scene_id": str(segment["sceneId"]),
            "scene_order": int(segment["sceneOrder"]),
            "action_id": str(segment["actionId"]),
            "narration_segment_id": str(segment["narrationSegmentId"]),
            "audio_sha256": audio_sha256,
        }

    @staticmethod
    def _hash_payload(payload: Mapping[str, Any]) -> str:
        wire = {
            "requestId" if key == "request_id" else
            "ttsRequestId" if key == "tts_request_id" else
            "classroomId" if key == "classroom_id" else
            "classroomContentSha256" if key == "classroom_content_sha256" else
            "teacherProfileId" if key == "teacher_profile_id" else
            "teacherProfileVersion" if key == "teacher_profile_version" else
            "teacherProfileSha256" if key == "teacher_profile_sha256" else
            "teacherGender" if key == "teacher_gender" else
            "sceneId" if key == "scene_id" else
            "sceneOrder" if key == "scene_order" else
            "actionId" if key == "action_id" else
            "narrationSegmentId" if key == "narration_segment_id" else
            "textSha256" if key == "text_sha256" else
            "audioSha256" if key == "audio_sha256" else key: value
            for key, value in payload.items()
        }
        return hashlib.sha256(
            json.dumps(
                wire, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            ).encode("utf-8")
        ).hexdigest()

    def _terminalize(
        self,
        *,
        build_item_id: str,
        scene_order: int,
        claim_token: str,
        outcome: str,
        code: str,
    ) -> dict[str, Any]:
        safe_code = re.sub(r"[^a-z0-9_]", "_", str(code).lower())[:128]
        with self.repository.transaction() as conn:
            job = self.repository.terminalize_formal_audio_job(
                conn,
                build_item_id=build_item_id,
                scene_order=scene_order,
                claim_token=claim_token,
                outcome=outcome,
                safe_error_code=safe_code,
                now=int(self.clock()),
            )
        return self._safe_job_result(job)

    @staticmethod
    def _safe_job_result(job: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "buildItemId": str(job["build_item_id"]),
            "state": str(job["state"]),
            "ttsCompletedCount": int(job.get("tts_completed_count") or 0),
            "audioValidatedCount": int(job.get("audio_validated_count") or 0),
            "asrPassedCount": int(job.get("asr_passed_count") or 0),
            "errorCode": job.get("safe_error_code"),
        }


class LearningMediaMaterializationService:
    """Materialize validated narration intent into review-gated media assets."""

    def __init__(
        self,
        repository: LearningTeacherMediaRepository,
        *,
        tts_provider: TtsProvider | None = None,
        asset_store: LearningMediaAssetStore | None = None,
    ):
        self.repository = repository
        self.tts_provider = tts_provider
        self.asset_store = asset_store

    def enqueue_narration(
        self,
        *,
        idempotency_key: str,
        teacher_profile_id: str,
        teacher_profile_version: int | None,
        subject: str,
        segments: Sequence[NarrationSegmentSpec | Mapping[str, Any]],
        language_code: str | None = None,
        pronunciation_kind: str | None = None,
        package_id: str | None = None,
        package_version: int | None = None,
        course_id: str | None = None,
        course_version: str | None = None,
    ) -> dict[str, Any]:
        with self.repository.transaction() as conn:
            return self.enqueue_narration_in_transaction(
                conn,
                idempotency_key=idempotency_key,
                teacher_profile_id=teacher_profile_id,
                teacher_profile_version=teacher_profile_version,
                subject=subject,
                segments=segments,
                language_code=language_code,
                pronunciation_kind=pronunciation_kind,
                package_id=package_id,
                package_version=package_version,
                course_id=course_id,
                course_version=course_version,
            )

    def enqueue_narration_in_transaction(
        self,
        conn: DatabaseConnection,
        *,
        idempotency_key: str,
        teacher_profile_id: str,
        teacher_profile_version: int | None,
        subject: str,
        segments: Sequence[NarrationSegmentSpec | Mapping[str, Any]],
        language_code: str | None = None,
        pronunciation_kind: str | None = None,
        package_id: str | None = None,
        package_version: int | None = None,
        course_id: str | None = None,
        course_version: str | None = None,
    ) -> dict[str, Any]:
        """Create/replay a media job inside the caller's database transaction.

        Lesson package staging uses this entry point so the private package and
        its narration outbox are committed atomically. Materialization remains
        a separate worker concern.
        """

        normalized_idempotency_key = self._required_id(
            idempotency_key,
            field="idempotency key",
        )
        subject_code = str(subject or "").strip().lower()
        if subject_code not in SUPPORTED_TEACHER_SUBJECTS:
            self._fail("invalid_subject", "subject must be chinese, math, or english")
        try:
            profile = get_teacher_profile(teacher_profile_id, teacher_profile_version)
        except KeyError as exc:
            raise LearningMediaMaterializationError(
                "teacher_profile_not_found",
                "The selected teacher is unavailable",
            ) from exc
        if profile.subject != subject_code:
            self._fail(
                "teacher_subject_mismatch",
                "The selected teacher does not teach this subject",
            )
        language = str(language_code or profile.language_code).strip()
        if language.casefold() != profile.language_code.casefold():
            self._fail(
                "teacher_language_mismatch",
                "The selected teacher does not support this narration language",
            )
        pronunciation = str(
            pronunciation_kind or ("english" if subject_code == "english" else "general")
        ).strip().lower()
        if pronunciation not in _PRONUNCIATION_KINDS:
            self._fail("invalid_pronunciation_kind", "Unsupported pronunciation policy")
        if subject_code == "english" and pronunciation != "english":
            pronunciation = "english"
        if pronunciation == "pinyin" and subject_code != "chinese":
            self._fail("invalid_pronunciation_kind", "Pinyin narration must use Chinese")
        normalized_segments = self._normalize_segments(segments)
        package = self._optional_id(package_id, field="package id")
        course = self._optional_long_id(course_id, field="course id", maximum=255)
        if (package is None) != (package_version is None):
            self._fail(
                "invalid_media_context",
                "package id and package version must be supplied together",
            )
        if (course is None) != (course_version is None):
            self._fail(
                "invalid_media_context",
                "course id and course version must be supplied together",
            )
        binding = profile.bind_tts_provider(
            provider_id=(
                str(self.tts_provider.provider_id)
                if self.tts_provider is not None
                else profile.provider_id
            ),
            provider_model=(
                str(self.tts_provider.model_name)
                if self.tts_provider is not None
                else profile.provider_model
            ),
        )
        request_payload = {
            "schemaVersion": "mira.learning.narration-request.v1",
            "teacherProfile": {"id": profile.profile_id, "version": profile.version},
            "subject": subject_code,
            "languageCode": language,
            "pronunciationKind": pronunciation,
            "package": (
                {"id": package, "version": int(package_version)} if package else None
            ),
            "course": (
                {"id": course, "version": str(course_version)} if course else None
            ),
            "segments": normalized_segments,
        }
        if (
            binding.provider_id != profile.provider_id
            or binding.provider_model != profile.provider_model
        ):
            request_payload["ttsBinding"] = binding.to_private_payload()
        request_hash = self._hash_json(request_payload)
        timestamp = now_ms()
        self.repository.sync_teacher_profile(conn, profile=profile, now=timestamp)
        job, created = self.repository.create_or_get_media_job(
            conn,
            idempotency_key=normalized_idempotency_key,
            request_hash=request_hash,
            package_id=package,
            package_version=int(package_version) if package is not None else None,
            course_id=course,
            course_version=str(course_version) if course is not None else None,
            subject=subject_code,
            language_code=language,
            pronunciation_kind=pronunciation,
            profile=profile,
            provider_id=binding.provider_id,
            provider_model=binding.provider_model,
            segment_count=len(normalized_segments),
            now=timestamp,
        )
        if str(job["request_hash"]) != request_hash:
            self._fail(
                "idempotency_conflict",
                "This idempotency key was already used for a different request",
            )
        if created:
            self.repository.create_narration_segments(
                conn,
                job_id=str(job["id"]),
                segments=normalized_segments,
                language_code=language,
                pronunciation_kind=pronunciation,
                review_policy=(
                    "manual_review"
                    if self.requires_manual_review(subject_code, pronunciation)
                    else "automated_integrity"
                ),
                now=timestamp,
            )
        persisted_segments = self.repository.list_narration_segments(
            conn,
            job_id=str(job["id"]),
        )
        return self._job_payload(job, persisted_segments, created=created)

    def materialize_job(self, *, job_id: str) -> dict[str, Any]:
        normalized_job_id = self._required_id(job_id, field="job id")
        if self.tts_provider is None or self.asset_store is None:
            self._fail(
                "tts_provider_unconfigured",
                "TTS media generation is not configured; the job remains pending",
            )
        timestamp = now_ms()
        with self.repository.transaction() as conn:
            job = self.repository.get_media_job(
                conn,
                job_id=normalized_job_id,
                for_update=True,
            )
            if job is None:
                self._fail("media_job_not_found", "Media generation job was not found")
            if str(job["status"]) != "pending":
                segments = self.repository.list_narration_segments(
                    conn,
                    job_id=normalized_job_id,
                )
                return self._job_payload(job, segments, created=False)
            if not self.repository.claim_media_job(conn, job_id=normalized_job_id, now=timestamp):
                self._fail("media_job_busy", "Media generation job is already being processed")
            segments = self.repository.list_narration_segments(
                conn,
                job_id=normalized_job_id,
            )
        try:
            profile = get_teacher_profile(
                str(job["teacher_profile_id"]),
                int(job["teacher_profile_version"]),
            )
        except KeyError as exc:
            self._record_failure(
                job_id=normalized_job_id,
                segment_id=None,
                code="teacher_profile_not_found",
                safe_message="The teacher profile for this job is unavailable",
            )
            raise LearningMediaMaterializationError(
                "teacher_profile_not_found",
                "The teacher profile for this job is unavailable",
            ) from exc
        manual_review = self.requires_manual_review(
            str(job["subject"]),
            str(job["pronunciation_kind"]),
        )
        active_segment_id: str | None = None
        try:
            self._validate_provider_binding(job)
            for segment in segments:
                active_segment_id = str(segment["id"])
                with self.repository.transaction() as conn:
                    self.repository.mark_segment_generating(
                        conn,
                        segment_id=active_segment_id,
                        now=now_ms(),
                    )
                result = self.tts_provider.synthesize(
                    TtsSynthesisRequest(
                        text=str(segment["source_text"]),
                        language_code=str(segment["language_code"]),
                        voice_prompt=profile.voice_prompt,
                    )
                )
                self._validate_tts_result(result, job)
                checksum = result.verified_checksum_sha256()
                stored = self.asset_store.put_audio(
                    job_id=normalized_job_id,
                    segment_id=active_segment_id,
                    content_hash=checksum,
                    mime_type=result.mime_type,
                    audio=result.audio,
                )
                if stored.content_hash != checksum or stored.byte_size != len(result.audio):
                    self._fail(
                        "media_storage_integrity_failed",
                        "Stored audio failed its checksum verification",
                    )
                with self.repository.transaction() as conn:
                    self.repository.register_segment_asset(
                        conn,
                        job=job,
                        segment=segment,
                        storage_key=stored.storage_key,
                        content_hash=checksum,
                        mime_type=result.mime_type,
                        byte_size=stored.byte_size,
                        duration_ms=result.duration_ms,
                        requires_manual_review=manual_review,
                        now=now_ms(),
                    )
            with self.repository.transaction() as conn:
                self.repository.finish_media_job(
                    conn,
                    job_id=normalized_job_id,
                    requires_manual_review=manual_review,
                    now=now_ms(),
                )
                refreshed = self.repository.get_media_job(conn, job_id=normalized_job_id)
                refreshed_segments = self.repository.list_narration_segments(
                    conn,
                    job_id=normalized_job_id,
                )
            return self._job_payload(refreshed, refreshed_segments, created=False)
        except Exception as exc:
            if isinstance(exc, LearningMediaMaterializationError):
                code = exc.code
                safe_message = exc.safe_message
            elif isinstance(exc, TtsProviderError):
                code = exc.code
                safe_message = exc.safe_message
            else:
                code = "media_materialization_failed"
                safe_message = "Narration audio could not be materialized"
            self._record_failure(
                job_id=normalized_job_id,
                segment_id=active_segment_id,
                code=code,
                safe_message=safe_message,
            )
            if isinstance(exc, LearningMediaMaterializationError):
                raise
            raise LearningMediaMaterializationError(code, safe_message) from exc

    def materialize_next_pending(self) -> dict[str, Any] | None:
        with self.repository.transaction() as conn:
            job = self.repository.get_next_pending_job(conn)
        if job is None:
            return None
        return self.materialize_job(job_id=str(job["id"]))

    def next_pending_job(self) -> dict[str, Any] | None:
        with self.repository.transaction() as conn:
            job = self.repository.get_next_pending_job(conn)
            if job is None:
                return None
            segments = self.repository.list_narration_segments(
                conn,
                job_id=str(job["id"]),
            )
        return self._job_payload(job, segments, created=False)

    def availability(self) -> dict[str, Any]:
        return {
            "configured": self.tts_provider is not None and self.asset_store is not None,
            "provider": (
                str(self.tts_provider.provider_id) if self.tts_provider is not None else None
            ),
            "model": (
                str(self.tts_provider.model_name) if self.tts_provider is not None else None
            ),
            "storageConfigured": self.asset_store is not None,
            "voiceCloneAllowed": False,
        }

    def review_pronunciation_asset(
        self,
        *,
        asset_id: str,
        approved: bool,
        reviewer_type: str,
        reviewer_id: str,
        notes: str = "",
        findings: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_asset_id = self._required_id(asset_id, field="asset id")
        reviewer_kind = str(reviewer_type or "").strip().lower()
        if reviewer_kind not in {"content_reviewer", "operations"}:
            self._fail(
                "invalid_media_reviewer",
                "Pronunciation review requires an authorized human reviewer",
            )
        reviewer = self._required_long_id(reviewer_id, field="reviewer id", maximum=255)
        safe_notes = str(notes or "").strip()[:2000]
        review_findings = dict(findings or {})
        with self.repository.transaction() as conn:
            asset = self.repository.review_asset(
                conn,
                asset_id=normalized_asset_id,
                approved=bool(approved),
                reviewer_type=reviewer_kind,
                reviewer_id=reviewer,
                notes=safe_notes,
                findings=review_findings,
                now=now_ms(),
            )
        if asset is None:
            self._fail(
                "manual_review_not_found",
                "This asset does not have a pending pronunciation review",
            )
        with self.repository.transaction() as conn:
            job = self.repository.get_media_job_by_asset(
                conn,
                asset_id=normalized_asset_id,
            )
            segments = (
                self.repository.list_narration_segments(conn, job_id=str(job["id"]))
                if job is not None
                else []
            )
        return {
            "assetId": str(asset["id"]),
            "status": str(asset["status"]),
            "approved": bool(approved),
            "job": self._job_payload(job, segments, created=False) if job else None,
        }

    def get_job(self, *, job_id: str) -> dict[str, Any]:
        normalized_job_id = self._required_id(job_id, field="job id")
        with self.repository.transaction() as conn:
            job = self.repository.get_media_job(conn, job_id=normalized_job_id)
            if job is None:
                self._fail("media_job_not_found", "Media generation job was not found")
            segments = self.repository.list_narration_segments(
                conn,
                job_id=normalized_job_id,
            )
        return self._job_payload(job, segments, created=False)

    @staticmethod
    def requires_manual_review(subject: str, pronunciation_kind: str) -> bool:
        return str(subject) == "english" or str(pronunciation_kind) == "pinyin"

    def _validate_provider_binding(self, job: Mapping[str, Any]) -> None:
        if self.tts_provider is None:
            self._fail("tts_provider_unconfigured", "TTS media generation is not configured")
        if str(self.tts_provider.provider_id) != str(job["provider_id"]):
            self._fail(
                "tts_provider_mismatch",
                "The configured TTS provider does not match the teacher profile",
            )
        if str(self.tts_provider.model_name) != str(job["provider_model"]):
            self._fail(
                "tts_model_mismatch",
                "The configured TTS model does not match the teacher profile",
            )

    def _validate_tts_result(self, result: Any, job: Mapping[str, Any]) -> None:
        if str(result.provider_id) != str(job["provider_id"]):
            self._fail("tts_provider_mismatch", "TTS response provider mismatch")
        if str(result.model) != str(job["provider_model"]):
            self._fail("tts_model_mismatch", "TTS response model mismatch")
        if not isinstance(result.audio, bytes) or not result.audio:
            self._fail("tts_empty_audio", "TTS returned no audio bytes")
        if str(result.mime_type).split(";", 1)[0].lower() not in {
            "audio/wav",
            "audio/mpeg",
            "audio/flac",
            "audio/ogg",
            "audio/webm",
        }:
            self._fail("tts_invalid_content_type", "TTS returned an unsupported audio type")

    def _record_failure(
        self,
        *,
        job_id: str,
        segment_id: str | None,
        code: str,
        safe_message: str,
    ) -> None:
        with self.repository.transaction() as conn:
            self.repository.fail_media_job(
                conn,
                job_id=job_id,
                segment_id=segment_id,
                error_code=str(code)[:128],
                error_message_safe=str(safe_message)[:512],
                now=now_ms(),
            )

    def _normalize_segments(
        self,
        segments: Sequence[NarrationSegmentSpec | Mapping[str, Any]],
    ) -> list[dict[str, Any]]:
        if not segments or len(segments) > 40:
            self._fail(
                "invalid_narration_segments",
                "A narration job must contain between 1 and 40 segments",
            )
        normalized: list[dict[str, Any]] = []
        for segment in segments:
            if isinstance(segment, NarrationSegmentSpec):
                text = segment.text
                subtitle = segment.subtitle
                scene_id = segment.scene_id
                action_id = segment.action_id
            elif isinstance(segment, Mapping):
                text = segment.get("text")
                subtitle = segment.get("subtitle")
                scene_id = segment.get("sceneId") or segment.get("scene_id")
                action_id = segment.get("actionId") or segment.get("action_id")
            else:
                self._fail("invalid_narration_segments", "Narration segment is invalid")
            source_text = self._clean_copy(text, field="narration text", maximum=2000)
            subtitle_text = self._clean_copy(
                subtitle if subtitle is not None else source_text,
                field="subtitle",
                maximum=2000,
            )
            item = {
                "text": source_text,
                "subtitle": subtitle_text,
                "sceneId": self._optional_id(scene_id, field="scene id"),
                "actionId": self._optional_id(action_id, field="action id"),
            }
            item["textHash"] = self._hash_json(item)
            normalized.append(item)
        return normalized

    @staticmethod
    def _job_payload(
        job: Mapping[str, Any],
        segments: Sequence[Mapping[str, Any]],
        *,
        created: bool,
    ) -> dict[str, Any]:
        return {
            "id": str(job["id"]),
            "created": created,
            "status": str(job["status"]),
            "idempotencyKey": str(job["idempotency_key"]),
            "requestHash": str(job["request_hash"]),
            "teacherProfile": {
                "id": str(job["teacher_profile_id"]),
                "version": int(job["teacher_profile_version"]),
            },
            "package": (
                {
                    "id": str(job["package_id"]),
                    "version": int(job["package_version"]),
                }
                if job.get("package_id") is not None
                else None
            ),
            "course": (
                {
                    "id": str(job["course_id"]),
                    "version": str(job["course_version"]),
                }
                if job.get("course_id") is not None
                else None
            ),
            "subject": str(job["subject"]),
            "languageCode": str(job["language_code"]),
            "pronunciationKind": str(job["pronunciation_kind"]),
            "requiresManualReview": LearningMediaMaterializationService.requires_manual_review(
                str(job["subject"]),
                str(job["pronunciation_kind"]),
            ),
            "segments": [
                {
                    "id": str(segment["id"]),
                    "index": int(segment["segment_index"]),
                    "sceneId": segment.get("scene_id"),
                    "actionId": segment.get("action_id"),
                    "subtitle": str(segment["subtitle_text"]),
                    "status": str(segment["status"]),
                    "assetId": segment.get("asset_id"),
                    "checksum": segment.get("audio_checksum"),
                    "durationMs": segment.get("duration_ms"),
                }
                for segment in segments
            ],
            "error": (
                {
                    "code": str(job["error_code"]),
                    "message": str(job["error_message_safe"]),
                }
                if job.get("error_code")
                else None
            ),
        }

    @staticmethod
    def _hash_json(value: Any) -> str:
        return hashlib.sha256(
            json.dumps(
                value,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()

    @classmethod
    def _required_id(cls, value: Any, *, field: str) -> str:
        normalized = str(value or "").strip()
        if not _ID_PATTERN.fullmatch(normalized):
            cls._fail("invalid_identifier", f"{field} is invalid")
        return normalized

    @classmethod
    def _optional_id(cls, value: Any, *, field: str) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        return cls._required_id(value, field=field)

    @classmethod
    def _required_long_id(cls, value: Any, *, field: str, maximum: int) -> str:
        normalized = str(value or "").strip()
        if not normalized or len(normalized) > maximum or any(ord(char) < 32 for char in normalized):
            cls._fail("invalid_identifier", f"{field} is invalid")
        return normalized

    @classmethod
    def _optional_long_id(cls, value: Any, *, field: str, maximum: int) -> str | None:
        if value is None or str(value).strip() == "":
            return None
        return cls._required_long_id(value, field=field, maximum=maximum)

    @classmethod
    def _clean_copy(cls, value: Any, *, field: str, maximum: int) -> str:
        normalized = " ".join(str(value or "").replace("\x00", " ").split()).strip()
        if not normalized or len(normalized) > maximum:
            cls._fail("invalid_narration_copy", f"{field} is missing or too long")
        return normalized

    @staticmethod
    def _fail(code: str, safe_message: str) -> None:
        raise LearningMediaMaterializationError(code, safe_message)
