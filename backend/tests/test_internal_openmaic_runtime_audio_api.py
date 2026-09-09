from __future__ import annotations

from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from flask import Flask

from core.errors import ApiError
from routes.internal.openmaic_runtime import internal_openmaic_runtime_bp
from services.openmaic_runtime_audio_service import AuthorizedOpenMaicRuntimeAudio


class _Guard:
    def authorize(self, **kwargs):
        if kwargs["headers"].get("X-Mira-Internal-Token") != "internal-token":
            raise ApiError("invalid_internal_token", "内部调用未通过校验。", 401)
        return {
            "auditId": "audit-audio-1",
            "sourceName": kwargs["headers"].get("X-Mira-Internal-Source", ""),
            "sourceIp": "127.0.0.1",
        }


class _AudioService:
    def __init__(self, path: Path):
        self.path = path
        self.manifest_calls = []
        self.asset_calls = []

    def manifest(self, **identity):
        self.manifest_calls.append(identity)
        return {
            "ok": True,
            "schemaVersion": "mira.openmaic.runtime-audio-manifest.v1",
            "classroomId": identity["upstream_classroom_id"],
            "classroomContentSha256": "c" * 64,
            "speechActionCount": 10,
            "assets": [],
        }

    def authorize_asset(self, **identity):
        self.asset_calls.append(identity)
        if identity["asset_id"] != "formal-audio-0":
            raise ApiError("openmaic_runtime_audio_not_found", "课堂音频不存在", 404)
        return AuthorizedOpenMaicRuntimeAudio(
            path=self.path,
            mime_type="audio/wav",
            content_hash="a" * 64,
            byte_size=self.path.stat().st_size,
            duration_ms=1_000,
        )


class InternalOpenMaicRuntimeAudioApiTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="mira-audio-api-")
        path = Path(self.temporary.name) / "audio.wav"
        data = bytearray(64)
        data[0:4] = b"RIFF"
        data[8:12] = b"WAVE"
        path.write_bytes(data)
        self.service = _AudioService(path)
        app = Flask(__name__)
        app.register_blueprint(
            internal_openmaic_runtime_bp,
            url_prefix="/internal/learning/openmaic",
        )
        self.client = app.test_client()
        self.guard_patch = patch(
            "routes.internal.openmaic_runtime.internal_request_guard",
            return_value=_Guard(),
        )
        self.service_patch = patch(
            "routes.internal.openmaic_runtime.openmaic_runtime_audio_service",
            return_value=self.service,
        )
        self.guard_patch.start()
        self.service_patch.start()
        self.addCleanup(self.guard_patch.stop)
        self.addCleanup(self.service_patch.stop)
        self.addCleanup(self.temporary.cleanup)

    def test_manifest_requires_gateway_source_and_exact_runtime_headers(self):
        wrong_source = self.client.get(
            "/internal/learning/openmaic/runtime/audio-manifest",
            headers=self._headers(source="student-web"),
        )
        self.assertEqual(wrong_source.status_code, 403)
        self.assertEqual(self.service.manifest_calls, [])

        missing = self.client.get(
            "/internal/learning/openmaic/runtime/audio-manifest",
            headers={
                "X-Mira-Internal-Token": "internal-token",
                "X-Mira-Internal-Source": "openmaic-runtime-gateway",
            },
        )
        self.assertEqual(missing.status_code, 400)
        self.assertEqual(self.service.manifest_calls, [])

        accepted = self.client.get(
            "/internal/learning/openmaic/runtime/audio-manifest",
            headers=self._headers(),
        )
        self.assertEqual(accepted.status_code, 200, accepted.json)
        self.assertEqual(accepted.json["classroomContentSha256"], "c" * 64)
        self.assertEqual(
            self.service.manifest_calls,
            [
                {
                    "runtime_session_id": "runtime-session-a",
                    "learning_session_id": "learning-session-a",
                    "upstream_classroom_id": "classroom-a",
                }
            ],
        )

    def test_audio_is_private_wav_and_unknown_asset_is_not_exposed(self):
        delivered = self.client.get(
            "/internal/learning/openmaic/runtime/audio/formal-audio-0",
            headers=self._headers(),
        )
        self.assertEqual(delivered.status_code, 200)
        self.assertEqual(delivered.mimetype, "audio/wav")
        self.assertEqual(len(delivered.data), 64)
        self.assertEqual(delivered.headers["Cache-Control"], "private, no-store")
        self.assertEqual(delivered.headers["X-Mira-Audio-Sha256"], "a" * 64)
        self.assertEqual(
            delivered.headers["Cross-Origin-Resource-Policy"], "same-origin"
        )
        delivered.close()

        missing = self.client.get(
            "/internal/learning/openmaic/runtime/audio/formal-audio-other",
            headers=self._headers(),
        )
        self.assertEqual(missing.status_code, 404)
        self.assertEqual(missing.json["error"], "openmaic_runtime_audio_not_found")

    @staticmethod
    def _headers(*, source="openmaic-runtime-gateway"):
        return {
            "X-Mira-Internal-Token": "internal-token",
            "X-Mira-Internal-Source": source,
            "X-Mira-Runtime-Session": "runtime-session-a",
            "X-Mira-Learning-Session": "learning-session-a",
            "X-Mira-Runtime-Classroom-Id": "classroom-a",
        }


if __name__ == "__main__":
    unittest.main()
