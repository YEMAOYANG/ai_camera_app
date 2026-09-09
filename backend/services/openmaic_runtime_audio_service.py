from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path, PurePosixPath
import re
from typing import Any, Mapping

from core.database import Database
from core.errors import ApiError
from core.security import now_ms
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository


_ID_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,159}$")
_HASH_PATTERN = re.compile(r"^[0-9a-f]{64}$")
_MAX_SCENES = 60
_MAX_SPEECH_ACTIONS_PER_SCENE = 20
_MAX_SEGMENTS = 240
_MAX_AUDIO_BYTES = 16 * 1024 * 1024
_RUNTIME_BINDING_CONTRACT = "mira.learning.candidate-runtime-binding.v1"
_AUDIO_CONTRACT = "mira.learning.formal-qwen-audio.v1"
_AUDIO_METADATA_CONTRACT = "mira.openmaic.speech-audio.v1"


@dataclass(frozen=True)
class AuthorizedOpenMaicRuntimeAudio:
    path: Path
    mime_type: str
    content_hash: str
    byte_size: int
    duration_ms: int


class OpenMaicRuntimeAudioService:
    """Read-only delivery boundary for already validated formal narration."""

    def __init__(
        self,
        database_url: str | Path,
        *,
        storage_root: str | Path,
        repository: OpenMaicRuntimeRepository | None = None,
    ):
        self.repository = repository or OpenMaicRuntimeRepository(
            Database(database_url)
        )
        self.storage_root = Path(storage_root).expanduser().resolve()

    def manifest(
        self,
        *,
        runtime_session_id: object,
        learning_session_id: object,
        upstream_classroom_id: object,
    ) -> dict[str, Any]:
        classroom_id = self._identifier(
            upstream_classroom_id, "runtime classroom"
        )
        rows = self._resolve_rows(
            runtime_session_id=runtime_session_id,
            learning_session_id=learning_session_id,
            upstream_classroom_id=classroom_id,
        )
        assets = []
        for row in rows:
            authorized = self._verify_asset(row)
            asset_id = str(row["asset_id"])
            assets.append(
                {
                    "sceneId": str(row["scene_id"]),
                    "actionId": str(row["action_id"]),
                    "audioId": asset_id,
                    "deliveryPath": f"/mira/runtime-audio/{asset_id}",
                    "contentHash": authorized.content_hash,
                    "mimeType": authorized.mime_type,
                    "byteSize": authorized.byte_size,
                    "durationMs": authorized.duration_ms,
                    "audioMetadata": {
                        "schemaVersion": _AUDIO_METADATA_CONTRACT,
                        "providerId": str(row["tts_provider_id"]),
                        "modelId": str(row["tts_model_id"]),
                        "voiceId": str(row["tts_voice_id"]),
                        "fallbackUsed": False,
                    },
                }
            )
        return {
            "ok": True,
            "schemaVersion": "mira.openmaic.runtime-audio-manifest.v1",
            "classroomId": classroom_id,
            "classroomContentSha256": str(
                rows[0]["classroom_content_sha256"]
            ),
            "speechActionCount": len(assets),
            "assets": assets,
        }

    def authorize_asset(
        self,
        *,
        runtime_session_id: object,
        learning_session_id: object,
        upstream_classroom_id: object,
        asset_id: object,
    ) -> AuthorizedOpenMaicRuntimeAudio:
        normalized_asset_id = self._identifier(asset_id, "audio asset")
        rows = self._resolve_rows(
            runtime_session_id=runtime_session_id,
            learning_session_id=learning_session_id,
            upstream_classroom_id=upstream_classroom_id,
        )
        matching = [
            row for row in rows if str(row["asset_id"]) == normalized_asset_id
        ]
        if len(matching) != 1:
            raise ApiError(
                "openmaic_runtime_audio_not_found",
                "课堂音频不存在",
                404,
            )
        return self._verify_asset(matching[0])

    def _resolve_rows(
        self,
        *,
        runtime_session_id: object,
        learning_session_id: object,
        upstream_classroom_id: object,
    ) -> list[Mapping[str, Any]]:
        runtime_id = self._identifier(runtime_session_id, "runtime session")
        learning_id = self._identifier(learning_session_id, "learning session")
        classroom_id = self._identifier(
            upstream_classroom_id, "runtime classroom"
        )
        with self.repository.transaction() as conn:
            rows = list(
                self.repository.list_runtime_audio_assets(
                    conn,
                    runtime_session_id=runtime_id,
                    learning_session_id=learning_id,
                    upstream_classroom_id=classroom_id,
                    now=now_ms(),
                )
            )
        if not rows:
            return self._unavailable()
        expected_segment_count = int(rows[0].get("expected_segment_count") or 0)
        if (
            not 1 <= expected_segment_count <= _MAX_SEGMENTS
            or len(rows) != expected_segment_count
        ):
            return self._unavailable()

        expected_orders = list(range(expected_segment_count))
        if [int(row.get("scene_order", -1)) for row in rows] != expected_orders:
            return self._unavailable()
        if len({str(row.get("action_id") or "") for row in rows}) != len(rows):
            return self._unavailable()
        if len({str(row.get("asset_id") or "") for row in rows}) != len(rows):
            return self._unavailable()

        manifest = self.repository.decode_json(
            rows[0].get("feature_manifest_json"), {}
        )
        classroom_hash = str(manifest.get("classroomContentSha256") or "")
        formal_evidence = manifest.get("formalEvidence")
        scene_count = manifest.get("sceneCount")
        speech_action_count = (
            formal_evidence.get("speechActionCount")
            if isinstance(formal_evidence, Mapping)
            else None
        )
        if (
            type(scene_count) is not int
            or not 1 <= scene_count <= _MAX_SCENES
            or type(speech_action_count) is not int
            or not scene_count <= speech_action_count <= _MAX_SEGMENTS
            or speech_action_count > scene_count * _MAX_SPEECH_ACTIONS_PER_SCENE
            or speech_action_count != expected_segment_count
        ):
            return self._unavailable()
        for row in rows:
            exact = (
                str(row.get("runtime_session_id") or "") == runtime_id
                and str(row.get("learning_session_id") or "") == learning_id
                and str(row.get("upstream_classroom_id") or "")
                == classroom_id
                and row.get("runtime_session_revoked_at") is None
                and int(row.get("runtime_session_expires_at") or 0) >= now_ms()
                and str(row.get("runtime_status") or "") == "ready"
                # Formal candidate sessions are launchable from their durable
                # release/audio/provider contracts while the generic manual
                # review flag remains pending_review.  This mirrors the main
                # runtime-session validator; every formal authority is still
                # rechecked below.
                and str(row.get("runtime_quality_status") or "")
                in {"pending_review", "approved"}
                and row.get("runtime_retired_at") is None
                and str(row.get("candidate_binding_contract_version") or "")
                == _RUNTIME_BINDING_CONTRACT
                and str(row.get("runtime_binding_contract_version") or "")
                == _RUNTIME_BINDING_CONTRACT
                and str(row.get("audio_job_state") or "") == "auto_validated"
                and str(row.get("audio_contract_version") or "")
                == _AUDIO_CONTRACT
                and int(row.get("expected_segment_count") or 0)
                == expected_segment_count
                and all(
                    int(row.get(field) or 0) == expected_segment_count
                    for field in (
                        "tts_attempted_count",
                        "tts_completed_count",
                        "audio_validated_count",
                        "asr_attempted_count",
                        "asr_passed_count",
                    )
                )
                and self._hash(str(row.get("terminal_receipt_hash") or ""))
                and self._hash(classroom_hash)
                and classroom_hash
                == str(row.get("classroom_content_sha256") or "")
                and str(row.get("tts_provider_id") or "") == "qwen-tts"
                and str(row.get("tts_model_id") or "")
                == "qwen3-tts-flash"
                and bool(str(row.get("tts_voice_id") or ""))
                and int(row.get("tts_fallback_allowed") or 0) == 0
            )
            if not exact:
                return self._unavailable()
            self._identifier(row.get("scene_id"), "scene")
            self._identifier(row.get("action_id"), "action")
            self._identifier(row.get("asset_id"), "audio asset")
        return rows

    def _verify_asset(
        self, row: Mapping[str, Any]
    ) -> AuthorizedOpenMaicRuntimeAudio:
        digest = str(row.get("runtime_audio_sha256") or "").lower()
        byte_size = int(row.get("segment_byte_size") or 0)
        duration_ms = int(row.get("segment_duration_ms") or 0)
        exact = (
            str(row.get("segment_state") or "") == "auto_validated"
            and row.get("safe_error_code") is None
            and self._hash(str(row.get("machine_receipt_hash") or ""))
            and self._hash(digest)
            and all(
                str(row.get(field) or "").lower() == digest
                for field in (
                    "download_sha256",
                    "streamed_sha256",
                    "readback_sha256",
                    "asset_content_hash",
                    "variant_content_hash",
                )
            )
            and str(row.get("segment_mime_type") or "").lower() == "audio/wav"
            and str(row.get("asset_mime_type") or "").lower() == "audio/wav"
            and str(row.get("variant_mime_type") or "").lower()
            == "audio/wav"
            and str(row.get("asset_kind") or "") == "audio"
            and str(row.get("asset_status") or "") == "ready"
            and str(row.get("asset_scan_status") or "") == "passed"
            and str(row.get("asset_moderation_status") or "") == "passed"
            and str(row.get("asset_transcode_status") or "")
            in {"passed", "not_required"}
            and str(row.get("variant_key") or "") == "original"
            and str(row.get("variant_status") or "") == "ready"
            and 44 < byte_size <= _MAX_AUDIO_BYTES
            and int(row.get("asset_byte_size") or 0) == byte_size
            and int(row.get("variant_byte_size") or 0) == byte_size
            and 300 <= duration_ms <= 120_000
            and int(row.get("asset_duration_ms") or 0) == duration_ms
            and int(row.get("variant_duration_ms") or 0) == duration_ms
            and int(row.get("pcm_format") or 0) == 1
            and int(row.get("channel_count") or 0) == 1
            and int(row.get("bits_per_sample") or 0) == 16
            and 16_000 <= int(row.get("sample_rate_hz") or 0) <= 48_000
            and int(row.get("block_align") or 0) == 2
            and str(row.get("storage_key") or "")
            == str(row.get("asset_storage_key") or "")
            == str(row.get("variant_storage_key") or "")
        )
        if not exact:
            return self._integrity_failed()

        path = self._safe_storage_path(str(row["storage_key"]))
        try:
            stat = path.stat()
            with path.open("rb") as audio_file:
                header = audio_file.read(12)
                content_hash = hashlib.sha256(header)
                for chunk in iter(lambda: audio_file.read(64 * 1024), b""):
                    content_hash.update(chunk)
        except OSError as exc:
            raise ApiError(
                "openmaic_runtime_audio_storage_missing",
                "课堂音频暂时不可用",
                503,
            ) from exc
        if (
            not path.is_file()
            or stat.st_size != byte_size
            or header[:4] != b"RIFF"
            or header[8:12] != b"WAVE"
            or content_hash.hexdigest() != digest
        ):
            return self._integrity_failed()
        return AuthorizedOpenMaicRuntimeAudio(
            path=path,
            mime_type="audio/wav",
            content_hash=digest,
            byte_size=byte_size,
            duration_ms=duration_ms,
        )

    def _safe_storage_path(self, storage_key: str) -> Path:
        if (
            not storage_key
            or "\\" in storage_key
            or PurePosixPath(storage_key).is_absolute()
            or any(part in {"", ".", ".."} for part in PurePosixPath(storage_key).parts)
        ):
            return self._integrity_failed()
        try:
            path = (self.storage_root / Path(*PurePosixPath(storage_key).parts)).resolve(
                strict=True
            )
            path.relative_to(self.storage_root)
        except (OSError, ValueError) as exc:
            raise ApiError(
                "openmaic_runtime_audio_storage_missing",
                "课堂音频暂时不可用",
                503,
            ) from exc
        return path

    @staticmethod
    def _identifier(value: object, label: str) -> str:
        normalized = str(value or "").strip()
        if not _ID_PATTERN.fullmatch(normalized):
            raise ApiError(
                "openmaic_runtime_audio_binding_invalid",
                f"{label}绑定无效",
                400,
            )
        return normalized

    @staticmethod
    def _hash(value: str) -> bool:
        return _HASH_PATTERN.fullmatch(value) is not None

    @staticmethod
    def _unavailable():
        raise ApiError(
            "openmaic_runtime_audio_unavailable",
            "正式课堂音频尚未就绪",
            503,
        )

    @staticmethod
    def _integrity_failed():
        raise ApiError(
            "openmaic_runtime_audio_integrity_failed",
            "正式课堂音频完整性校验失败",
            503,
        )
