from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from dataclasses import replace
import hashlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError

from flask import Flask

from core.config import (
    ConfigError,
    _validate_openmaic_tts_credential_recovery_config,
)
from integrations.openmaic_deterministic_recovery_client import (
    RECOVERY_CANONICAL_SPEC_SHA256,
    RECOVERY_KIND,
    RECOVERY_MODE,
    RECOVERY_PATCH_SHA256,
    OpenMaicDeterministicRecovery,
    OpenMaicDeterministicRecoveryError,
    OpenMaicRecoverySourceSnapshot,
)
from integrations.openmaic_tts_credential_recovery_client import (
    TTS_CREDENTIAL_RECOVERY_CANONICAL_SPEC_SHA256,
    TTS_CREDENTIAL_RECOVERY_CLASSROOM_POLICY_VERSION,
    TTS_CREDENTIAL_RECOVERY_KIND,
    TTS_CREDENTIAL_RECOVERY_MODE,
    TTS_CREDENTIAL_RECOVERY_PARENT_PATCH_SHA256,
    TTS_CREDENTIAL_RECOVERY_PATCH_SHA256,
    TTS_CREDENTIAL_RECOVERY_POLICY_VERSION,
    TTS_CREDENTIAL_RECOVERY_REQUEST_MODE,
    TTS_CREDENTIAL_RECOVERY_SCHEMA,
    OpenMaicTtsCredentialRecovery,
    OpenMaicTtsCredentialRecoveryClient,
    OpenMaicTtsCredentialRecoveryError,
    tts_credential_classroom_identity,
    tts_credential_parent_snapshot_sha256,
    tts_credential_recovery_identity,
)
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from routes.internal import openmaic_runtime as runtime_routes
from services import service_factory
from services.openmaic_full_runtime_service import (
    SAMPLE_TTS_CREDENTIAL_RECOVERY_STALE_AFTER_MS,
    OpenMaicFullRuntimeService,
    OpenMaicRuntimeServiceError,
)
from integrations.openmaic_conversation_probe_client import (
    OpenMaicConversationProbeClientError,
)
from tests.test_openmaic_deterministic_recovery import (
    _ClassroomClient,
    _RecoveryRepository,
    _service as _base_service,
    _recovery_classroom,
)


SOURCE_JOB_ID = "uKQl3vMr4d"
PARENT_UPSTREAM_ID = "omrec_383729f8f7f637dc1cdc65d4"
REQUEST_ID = "stage2-qwen-credential-child-v1"
CHILD_ID = "omtts_c7af8d9674def5168b43e8c8"
CLASSROOM_ID = "omclass_3741522de821a05cfb932e6e"


def _parent_upstream() -> OpenMaicDeterministicRecovery:
    source = OpenMaicRecoverySourceSnapshot(
        job_id=SOURCE_JOB_ID,
        completed_at="2026-08-19T23:00:00.000Z",
        job_snapshot_sha256="a" * 64,
    )
    return OpenMaicDeterministicRecovery(
        recovery_id=PARENT_UPSTREAM_ID,
        status="failed",
        step="tts_failed",
        progress=100,
        done=True,
        source=source.to_audit_source(),
        policy={
            "marker": "MIRA_OPENMAIC_SAMPLE_STRUCTURAL_POLICY_V1",
            "version": "mira-sample-deterministic-classroom.v1",
            "canonicalSpecSha256": RECOVERY_CANONICAL_SPEC_SHA256,
            "patchSha256": RECOVERY_PATCH_SHA256,
        },
        calls={
            "llm": 0,
            "webSearch": 0,
            "imageGeneration": 0,
            "videoGeneration": 0,
            "tts": {"expected": 10, "attempted": 1, "completed": 0},
        },
        artifact=None,
        error={
            "code": "deterministic_recovery_failed",
            "message": "Qwen TTS credential rejected before first asset",
        },
        created_at="2026-08-19T23:01:00.000Z",
        updated_at="2026-08-19T23:02:00.000Z",
        started_at="2026-08-19T23:01:01.000Z",
        completed_at="2026-08-19T23:02:00.000Z",
    )


def _child_classroom() -> dict:
    classroom = _recovery_classroom()
    classroom["stage"]["id"] = CLASSROOM_ID
    for scene in classroom["scenes"]:
        scene["stageId"] = CLASSROOM_ID
        for action in scene.get("actions", []):
            if action.get("type") == "speech":
                action["audioUrl"] = (
                    f"/api/classroom-media/{CLASSROOM_ID}/audio/"
                    f"{action['audioId']}.mp3"
                )
    return classroom


def _child_upstream(status: str, classroom: dict | None = None):
    payload = _runtime_payload(status)
    if status == "succeeded":
        assert classroom is not None
        payload["artifact"]["contentSha256"] = hashlib.sha256(
            json.dumps(
                {"stage": classroom["stage"], "scenes": classroom["scenes"]},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
    parser = object.__new__(OpenMaicTtsCredentialRecoveryClient)
    parser._expected_patch_sha256 = TTS_CREDENTIAL_RECOVERY_PATCH_SHA256
    return parser._recovery_from_payload(
        payload,
        expected_source_job_id=SOURCE_JOB_ID,
        expected_parent_recovery_id=PARENT_UPSTREAM_ID,
        expected_recovery_id=CHILD_ID,
    )


def _runtime_payload(status: str = "running") -> dict:
    attempted, completed = (2, 1)
    scenes_generated = 1
    artifact = None
    error = None
    if status == "succeeded":
        attempted = completed = scenes_generated = 10
        artifact = {
            "classroomId": CLASSROOM_ID,
            "url": f"/classroom/{CLASSROOM_ID}",
            "sceneCount": 10,
            "audioCount": 10,
            "contentSha256": "a" * 64,
            "artifactSha256": "b" * 64,
            "tts": {
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": "Serena",
                "speechCount": 10,
                "fallbackUsed": False,
            },
        }
    elif status == "failed":
        error = {
            "code": "tts_credential_recovery_failed",
            "message": "Qwen TTS credential recovery failed",
        }
    terminal = status in {"succeeded", "failed"}
    payload = {
        "success": True,
        "schemaVersion": TTS_CREDENTIAL_RECOVERY_SCHEMA,
        "kind": TTS_CREDENTIAL_RECOVERY_KIND,
        "mode": TTS_CREDENTIAL_RECOVERY_MODE,
        "recoveryId": CHILD_ID,
        "source": {"jobId": SOURCE_JOB_ID},
        "parent": {
            "recoveryId": PARENT_UPSTREAM_ID,
            "status": "failed",
            "error": {"code": "deterministic_recovery_failed"},
            "calls": {
                "tts": {"expected": 10, "attempted": 1, "completed": 0}
            },
            "artifactAbsent": True,
            "parentSnapshotSha256": tts_credential_parent_snapshot_sha256(
                PARENT_UPSTREAM_ID
            ),
            "parentSnapshotHashBasis": "canonical_json_v1",
        },
        "policy": {
            "version": TTS_CREDENTIAL_RECOVERY_POLICY_VERSION,
            "classroomPolicyVersion": (
                TTS_CREDENTIAL_RECOVERY_CLASSROOM_POLICY_VERSION
            ),
            "canonicalSpecSha256": (
                TTS_CREDENTIAL_RECOVERY_CANONICAL_SPEC_SHA256
            ),
            "parentPatchSha256": TTS_CREDENTIAL_RECOVERY_PARENT_PATCH_SHA256,
            "patchSha256": TTS_CREDENTIAL_RECOVERY_PATCH_SHA256,
        },
        "calls": {
            "llm": 0,
            "webSearch": 0,
            "imageGeneration": 0,
            "videoGeneration": 0,
            "tts": {
                "expected": 10,
                "attempted": attempted,
                "completed": completed,
            },
        },
        "status": status,
        "step": "complete" if terminal else "tts",
        "progress": 100 if terminal else 20,
        "message": "safe runtime status",
        "scenesGenerated": scenes_generated,
        "totalScenes": 10,
        "createdAt": "2026-08-20T01:00:00.000Z",
        "updatedAt": "2026-08-20T01:01:00.000Z",
        "pollUrl": (
            f"/api/generate-classroom/{SOURCE_JOB_ID}/deterministic-recovery/"
            f"{PARENT_UPSTREAM_ID}/tts-credential-recovery"
        ),
        "done": terminal,
    }
    if terminal:
        payload["completedAt"] = "2026-08-20T01:01:00.000Z"
    if artifact is not None:
        payload["artifact"] = artifact
    if error is not None:
        payload["error"] = error
    return payload


class _Response:
    def __init__(self, request, payload, *, final_url=None):
        self.request = request
        self.payload = payload
        self.final_url = final_url or request.full_url

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def geturl(self):
        return self.final_url

    def read(self, _limit):
        if isinstance(self.payload, bytes):
            return self.payload
        return json.dumps(self.payload).encode("utf-8")


class _JsonOpener:
    def __init__(self, payload):
        self.payload = payload
        self.requests = []

    def open(self, request, **_kwargs):
        self.requests.append(request)
        return _Response(request, self.payload)


class OpenMaicTtsCredentialRecoveryClientTest(unittest.TestCase):
    def _client(self):
        return OpenMaicTtsCredentialRecoveryClient(
            "http://127.0.0.1:3100",
            internal_token="i" * 32,
            expected_patch_sha256=TTS_CREDENTIAL_RECOVERY_PATCH_SHA256,
        )

    def test_cross_language_ids_and_parent_snapshot_golden(self):
        child_id, request_sha = tts_credential_recovery_identity(
            SOURCE_JOB_ID, PARENT_UPSTREAM_ID, REQUEST_ID
        )
        self.assertEqual(
            request_sha,
            "6ec44ce0a7483bd98fc131c146b23b0b9e1f6e09fe34f778a02a3ecb3c1d46ef",
        )
        self.assertEqual(child_id, CHILD_ID)
        self.assertEqual(tts_credential_classroom_identity(child_id), CLASSROOM_ID)
        self.assertEqual(
            tts_credential_parent_snapshot_sha256(PARENT_UPSTREAM_ID),
            "745f05912348ea17ae9f28fdcff68a21a3485b9c0d2687c85a69d1720e972764",
        )

    def test_post_body_and_success_shape_are_exact(self):
        client = self._client()
        opener = _JsonOpener(_runtime_payload("succeeded"))
        client._opener = opener

        recovery = client.start_recovery(
            source_job_id=SOURCE_JOB_ID,
            parent_recovery_id=PARENT_UPSTREAM_ID,
            recovery_request_id=REQUEST_ID,
        )

        self.assertEqual(recovery.recovery_id, CHILD_ID)
        self.assertEqual(recovery.calls["tts"]["completed"], 10)
        self.assertEqual(
            json.loads(opener.requests[0].data.decode("utf-8")),
            {"recoveryRequestId": REQUEST_ID},
        )
        self.assertNotIn("requestIdSha256", recovery.audit_receipt())

    def test_health_requires_exact_frozen_policy(self):
        client = self._client()
        expected = {
            "enabled": True,
            "sourceJobId": SOURCE_JOB_ID,
            "parentRecoveryId": PARENT_UPSTREAM_ID,
            "policyVersion": TTS_CREDENTIAL_RECOVERY_POLICY_VERSION,
            "canonicalSpecSha256": TTS_CREDENTIAL_RECOVERY_CANONICAL_SPEC_SHA256,
            "patchSha256": TTS_CREDENTIAL_RECOVERY_PATCH_SHA256,
        }
        client._opener = _JsonOpener(
            {"success": True, "runtimePolicy": {"ttsCredentialRecovery": expected}}
        )
        self.assertEqual(
            client.verify_runtime_policy(
                source_job_id=SOURCE_JOB_ID,
                parent_recovery_id=PARENT_UPSTREAM_ID,
            ),
            expected,
        )
        client._opener = _JsonOpener(
            {
                "success": True,
                "runtimePolicy": {
                    "ttsCredentialRecovery": {**expected, "extra": True}
                },
            }
        )
        with self.assertRaises(OpenMaicTtsCredentialRecoveryError):
            client.verify_runtime_policy(
                source_job_id=SOURCE_JOB_ID,
                parent_recovery_id=PARENT_UPSTREAM_ID,
            )

    def test_absence_requires_authenticated_exact_404(self):
        client = self._client()

        class _ErrorOpener:
            def __init__(self, status, payload, *, url=None):
                self.status = status
                self.payload = payload
                self.url = url
                self.requests = []

            def open(self, request, **_kwargs):
                self.requests.append(request)
                raise HTTPError(
                    self.url or request.full_url,
                    self.status,
                    "controlled",
                    {},
                    io.BytesIO(json.dumps(self.payload).encode("utf-8")),
                )

        exact = {
            "success": False,
            "errorCode": "INVALID_REQUEST",
            "error": "TTS credential recovery not found",
        }
        opener = _ErrorOpener(404, exact)
        client._opener = opener
        client.assert_recovery_absent(
            source_job_id=SOURCE_JOB_ID,
            parent_recovery_id=PARENT_UPSTREAM_ID,
            expected_recovery_id=CHILD_ID,
            recovery_request_id=REQUEST_ID,
        )
        headers = {
            key.casefold(): value
            for key, value in opener.requests[0].header_items()
        }
        self.assertEqual(headers["x-mira-internal-token"], "i" * 32)

        cases = (
            (403, exact, None),
            (404, {**exact, "details": "drift"}, None),
            (404, {**exact, "error": "different"}, None),
            (404, exact, "http://evil.invalid/not-found"),
        )
        for status, payload, url in cases:
            with self.subTest(status=status, payload=payload, url=url):
                client._opener = _ErrorOpener(status, payload, url=url)
                with self.assertRaises(OpenMaicTtsCredentialRecoveryError):
                    client.assert_recovery_absent(
                        source_job_id=SOURCE_JOB_ID,
                        parent_recovery_id=PARENT_UPSTREAM_ID,
                        expected_recovery_id=CHILD_ID,
                        recovery_request_id=REQUEST_ID,
                    )

    def test_response_rejects_identity_url_error_and_count_drift(self):
        client = self._client()
        for mutate in (
            lambda payload: payload.__setitem__("kind", "wrong"),
            lambda payload: payload["artifact"].__setitem__(
                "url", "https://evil.invalid/classroom"
            ),
            lambda payload: payload["artifact"].__setitem__("audioCount", 9),
            lambda payload: payload["calls"]["tts"].__setitem__("completed", 9),
            lambda payload: payload.__setitem__("error", {"code": "unexpected"}),
        ):
            payload = _runtime_payload("succeeded")
            mutate(payload)
            with self.subTest(payload=payload):
                with self.assertRaises(OpenMaicTtsCredentialRecoveryError):
                    client._recovery_from_payload(
                        payload,
                        expected_source_job_id=SOURCE_JOB_ID,
                        expected_parent_recovery_id=PARENT_UPSTREAM_ID,
                        expected_recovery_id=CHILD_ID,
                    )

    def test_malformed_json_uses_stable_contract_error(self):
        client = self._client()
        client._opener = _JsonOpener(b"{not-json")
        with self.assertRaises(OpenMaicTtsCredentialRecoveryError) as caught:
            client.start_recovery(
                source_job_id=SOURCE_JOB_ID,
                parent_recovery_id=PARENT_UPSTREAM_ID,
                recovery_request_id=REQUEST_ID,
            )
        self.assertEqual(
            caught.exception.code,
            "invalid_openmaic_tts_credential_response",
        )


class OpenMaicTtsCredentialRecoveryStaticContractTest(unittest.TestCase):
    def test_migration_is_append_only_and_has_strict_child_bindings(self):
        sql = (
            Path(__file__).parents[1]
            / "migrations"
            / "053_openmaic_tts_credential_recovery.sql"
        ).read_text(encoding="utf-8")
        self.assertIn("UNIQUE KEY uq_openmaic_tts_child_parent(parent_recovery_id)", sql)
        self.assertIn("UNIQUE KEY uq_openmaic_tts_child_expected_classroom", sql)
        self.assertIn("tts_credential_recovery_id IS NOT NULL", sql)
        self.assertIn("upstream_child_id IS NOT NULL", sql)
        self.assertIn("status = 'publishing'", sql)
        self.assertIn("static_contract_verified = TRUE", sql)
        self.assertIn("static_contract_verified = FALSE", sql)
        self.assertNotIn("parent_runtime_file_sha256", sql)
        self.assertNotIn("source_job_raw_file_sha256", sql)
        self.assertNotIn("UPDATE learning_openmaic_deterministic_recoveries", sql)
        for line in sql.splitlines():
            if line.lstrip().startswith("--"):
                self.assertNotIn(";", line)

    def test_config_requires_parent_gate_and_disables_redispatch(self):
        valid = {
            "runtime_enabled": True,
            "probe_enabled": True,
            "deterministic_recovery_enabled": True,
            "redispatch_enabled": False,
            "generation_enabled": False,
            "autorun_enabled": False,
            "enabled": True,
            "internal_url": "http://127.0.0.1:3100",
            "internal_token": "i" * 32,
        }
        _validate_openmaic_tts_credential_recovery_config(**valid)
        for drift in (
            {"deterministic_recovery_enabled": False},
            {"redispatch_enabled": True},
            {"generation_enabled": True},
            {"probe_enabled": False},
        ):
            with self.subTest(drift=drift), self.assertRaises(ConfigError):
                _validate_openmaic_tts_credential_recovery_config(
                    **{**valid, **drift}
                )
        self.assertEqual(
            SAMPLE_TTS_CREDENTIAL_RECOVERY_STALE_AFTER_MS,
            15 * 60 * 1000,
        )


class OpenMaicTtsCredentialRecoveryFactoryTest(unittest.TestCase):
    def test_factory_pins_child_patch_and_wires_both_clients(self):
        app = Flask(__name__)
        app.config.update(
            DATABASE_URL="sqlite:///:memory:",
            OPENMAIC_FULL_RUNTIME_ENABLED=True,
            OPENMAIC_FULL_RUNTIME_GENERATION_ENABLED=False,
            OPENMAIC_FULL_RUNTIME_INTERNAL_URL="http://127.0.0.1:3100",
            OPENMAIC_FULL_RUNTIME_PUBLIC_URL="http://127.0.0.1:3101",
            OPENMAIC_FULL_RUNTIME_TIMEOUT_SECONDS=30,
            OPENMAIC_FULL_RUNTIME_LAUNCH_TTL_SECONDS=60,
            OPENMAIC_FULL_RUNTIME_SESSION_TTL_SECONDS=14400,
            OPENMAIC_FULL_RUNTIME_VIDEO_EXPORT_ENABLED=False,
            OPENMAIC_CONVERSATION_PROBE_ENABLED=True,
            OPENMAIC_DETERMINISTIC_RECOVERY_ENABLED=True,
            OPENMAIC_DETERMINISTIC_RECOVERY_REDISPATCH_ENABLED=False,
            OPENMAIC_TTS_CREDENTIAL_RECOVERY_ENABLED=True,
            INTERNAL_API_TOKEN="i" * 32,
        )
        captured = {}

        class _ParentClient:
            def __init__(self, _url, **kwargs):
                captured["parent"] = kwargs

        class _ChildClient:
            def __init__(self, _url, **kwargs):
                captured["child"] = kwargs

        class _Service:
            def __init__(self, _database_url, **kwargs):
                captured["service"] = kwargs

        with app.app_context(), patch.object(
            service_factory,
            "OpenMaicDeterministicRecoveryClient",
            _ParentClient,
        ), patch.object(
            service_factory,
            "OpenMaicTtsCredentialRecoveryClient",
            _ChildClient,
        ), patch.object(
            service_factory, "OpenMaicFullRuntimeService", _Service
        ), patch.object(
            service_factory, "OpenMaicFullRuntimeClient", lambda *_a, **_k: object()
        ), patch.object(
            service_factory, "student_auth_service", lambda: object()
        ), patch.object(
            service_factory, "openmaic_conversation_probe_service", lambda: object()
        ), patch.object(
            service_factory, "openmaic_conversation_probe_client", lambda: object()
        ):
            service_factory.openmaic_full_runtime_service()

        self.assertEqual(
            captured["child"]["expected_patch_sha256"],
            TTS_CREDENTIAL_RECOVERY_PATCH_SHA256,
        )
        self.assertEqual(captured["child"]["internal_token"], "i" * 32)
        self.assertTrue(captured["service"]["tts_credential_recovery_enabled"])
        self.assertIsNotNone(
            captured["service"]["tts_credential_recovery_client"]
        )
        self.assertIsNotNone(captured["service"]["deterministic_recovery_client"])


class OpenMaicTtsCredentialRecoveryRouteTest(unittest.TestCase):
    def test_internal_post_and_get_are_separate(self):
        app = Flask(__name__)
        app.register_blueprint(
            runtime_routes.internal_openmaic_runtime_bp,
            url_prefix="/internal/learning/openmaic",
        )

        class _Service:
            def __init__(self):
                self.post = None
                self.get = None

            def recover_tts_credentials(self, runtime_id, data):
                self.post = (runtime_id, data)
                return {"ok": True, "ttsCredentialRecovery": {"status": "recovering"}}

            def tts_credential_recovery_status(self, runtime_id):
                self.get = runtime_id
                return {"ok": True, "ttsCredentialRecovery": {"status": "failed"}}

        class _Guard:
            @staticmethod
            def authorize(**_kwargs):
                return {"authorized": True}

        service = _Service()
        body = {
            "expectedSourceJobId": SOURCE_JOB_ID,
            "expectedParentRecoveryId": PARENT_UPSTREAM_ID,
            "recoveryRequestId": REQUEST_ID,
            "mode": TTS_CREDENTIAL_RECOVERY_REQUEST_MODE,
        }
        with patch.object(
            runtime_routes,
            "openmaic_full_runtime_service",
            return_value=service,
        ), patch.object(
            runtime_routes,
            "internal_request_guard",
            return_value=_Guard(),
        ):
            client = app.test_client()
            path = (
                "/internal/learning/openmaic/classrooms/runtime-attempt-3/"
                "recovery/tts-credential-recovery"
            )
            posted = client.post(path, json=body)
            polled = client.get(path)

        self.assertEqual(posted.status_code, 200)
        self.assertEqual(polled.status_code, 200)
        self.assertEqual(service.post, ("runtime-attempt-3", body))
        self.assertEqual(service.get, "runtime-attempt-3")


class OpenMaicTtsCredentialRecoveryRepositorySqlTest(unittest.TestCase):
    def test_repository_parameter_contracts_are_complete(self):
        class _Cursor:
            rowcount = 1

            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class _Connection:
            def __init__(self):
                self.statements = []
                self.row = {"id": "local-child-1"}

            def execute(self, statement, params=()):
                assert statement.count("?") == len(params), (
                    statement.count("?"),
                    len(params),
                    statement,
                )
                self.statements.append((statement, params))
                return _Cursor(
                    self.row if statement.lstrip().startswith("SELECT") else None
                )

        repository = object.__new__(OpenMaicRuntimeRepository)
        conn = _Connection()
        hashes = {"db": "d" * 64, "receipt": "e" * 64, "runtime": "f" * 64}
        repository.reserve_tts_credential_recovery(
            conn,
            recovery_id="local-child-1",
            recovery_request_id=REQUEST_ID,
            runtime_id="runtime-attempt-3",
            parent_recovery_id="local-parent-1",
            expected_source_job_id=SOURCE_JOB_ID,
            parent_db_snapshot_sha256=hashes["db"],
            parent_receipt_sha256=hashes["receipt"],
            parent_runtime_snapshot_sha256=hashes["runtime"],
            expected_upstream_child_id=CHILD_ID,
            expected_upstream_classroom_id=CLASSROOM_ID,
            mode=TTS_CREDENTIAL_RECOVERY_MODE,
            kind=TTS_CREDENTIAL_RECOVERY_KIND,
            tts_provider_id="qwen-tts",
            tts_model_id="qwen3-tts-flash",
            tts_voice_id="Serena",
            now=100,
        )
        running = _runtime_payload("running")
        repository.attach_tts_credential_recovery_receipt(
            conn,
            recovery_id="local-child-1",
            upstream_child_id=CHILD_ID,
            parent_runtime_snapshot_sha256=hashes["runtime"],
            policy=running["policy"],
            calls=running["calls"],
            receipt=running,
            now=101,
        )
        repository.update_tts_credential_recovery_observation(
            conn,
            recovery_id="local-child-1",
            receipt=running,
            tts_attempted_count=2,
            tts_completed_count=1,
            progressed=False,
            now=102,
        )
        conn.row = {
            "status": "recovering",
            "updated_at": 102,
            "tts_attempted_call_count": 2,
            "tts_completed_call_count": 1,
        }
        repository.fail_stale_tts_credential_recovery(
            conn,
            recovery_id="local-child-1",
            runtime_id="runtime-attempt-3",
            source_upstream_job_id=SOURCE_JOB_ID,
            expected_status="recovering",
            expected_updated_at=102,
            expected_tts_attempted_count=2,
            expected_tts_completed_count=1,
            stale_cutoff=102,
            error_code="openmaic_tts_credential_upstream_stale",
            error_message_safe="stale",
            now=103,
        )
        conn.row = {"id": "local-child-1"}
        succeeded = _runtime_payload("succeeded")
        repository.claim_tts_credential_recovery_validation(
            conn,
            recovery_id="local-child-1",
            receipt=succeeded,
            now=103,
        )
        repository.complete_tts_credential_static_validation(
            conn,
            recovery_id="local-child-1",
            artifact=succeeded["artifact"],
            receipt=succeeded,
            now=103,
        )
        repository.fail_tts_credential_recovery(
            conn,
            recovery_id="local-child-1",
            runtime_id="runtime-attempt-3",
            source_upstream_job_id=SOURCE_JOB_ID,
            expected_status="validating",
            error_code="openmaic_tts_credential_validation_failed",
            error_message_safe="failed",
            receipt=succeeded,
            tts_attempted_count=10,
            tts_completed_count=10,
            now=104,
        )
        repository.claim_tts_credential_recovery_publication(
            conn,
            recovery_id="local-child-1",
            runtime_id="runtime-attempt-3",
            conversation_probe_id="probe-child-1",
            now=104,
        )
        conn.row = {"id": "local-parent-1"}
        repository.mark_ready_from_tts_credential_recovery(
            conn,
            recovery_id="local-child-1",
            runtime_id="runtime-attempt-3",
            parent_recovery_id="local-parent-1",
            parent_db_snapshot_sha256=hashes["db"],
            parent_receipt_sha256=hashes["receipt"],
            parent_runtime_snapshot_sha256=hashes["runtime"],
            source_upstream_job_id=SOURCE_JOB_ID,
            upstream_child_id=CHILD_ID,
            upstream_classroom_id=CLASSROOM_ID,
            conversation_probe_id="probe-child-1",
            feature_manifest={"verified": True},
            receipt=succeeded,
            now=105,
        )
        self.assertGreaterEqual(len(conn.statements), 10)


class _ParentRuntimeClient:
    def __init__(self, parent):
        self.parent = parent
        self.calls = 0
        self.error = None

    def get_recovery(self, **_kwargs):
        self.calls += 1
        if self.error is not None:
            raise self.error
        return self.parent


class _ChildRuntimeClient:
    def __init__(self, status, classroom):
        self.status = status
        self.classroom = classroom
        self.policy_calls = 0
        self.absence_calls = 0
        self.start_calls = 0
        self.get_calls = 0
        self.policy_error = None
        self.absence_error = None
        self.start_error = None
        self.get_error = None

    def verify_runtime_policy(self, **_kwargs):
        self.policy_calls += 1
        if self.policy_error is not None:
            raise self.policy_error
        return {"enabled": True}

    def assert_recovery_absent(self, **_kwargs):
        self.absence_calls += 1
        if self.absence_error is not None:
            raise self.absence_error

    def start_recovery(self, **_kwargs):
        self.start_calls += 1
        if self.start_error is not None:
            raise self.start_error
        return _child_upstream(self.status, self.classroom)

    def get_recovery(self, **_kwargs):
        self.get_calls += 1
        if self.get_error is not None:
            raise self.get_error
        return _child_upstream(self.status, self.classroom)


class _ChildProbeService:
    def __init__(self, repository, *, parent_mutator=None):
        self.repository = repository
        self.issue_calls = 0
        self.finalize_calls = 0
        self.parent_mutator = parent_mutator
        self.on_finalize = None
        self.raise_after_finalize = False

    def issue_tts_credential_recovery_candidate(
        self, runtime_id, classroom_id, parent_recovery_id, child_recovery_id
    ):
        self.issue_calls += 1
        self.issue_args = (
            runtime_id,
            classroom_id,
            parent_recovery_id,
            child_recovery_id,
        )
        self.repository.probe = {
            "id": "probe-child-1",
            "runtime_classroom_id": runtime_id,
            "upstream_classroom_id": classroom_id,
            "candidate_kind": "tts_credential_recovery",
            "deterministic_recovery_id": parent_recovery_id,
            "tts_credential_recovery_id": child_recovery_id,
            "finalized_at": None,
            "chat_receipt_json": None,
            "transcription_receipt_json": None,
        }
        return {
            "probeId": "probe-child-1",
            "runtimeId": runtime_id,
            "classroomId": classroom_id,
            "candidateKind": "tts_credential_recovery",
        }

    def finalize_probe(self, _probe_id, **kwargs):
        self.finalize_calls += 1
        self.repository.probe.update(
            {
                "finalized_at": 123,
                "chat_receipt_json": deepcopy(kwargs["chat_receipt"]),
                "transcription_receipt_json": deepcopy(
                    kwargs["transcription_receipt"]
                ),
            }
        )
        if self.on_finalize is not None:
            self.on_finalize()
        if self.parent_mutator is not None:
            self.parent_mutator()
        if self.raise_after_finalize:
            raise RuntimeError("probe finalize response lost after commit")


class _ChildProbeClient:
    def __init__(self, *, fail=False, on_verify=None):
        self.fail = fail
        self.on_verify = on_verify
        self.calls = 0

    def verify(self, _probe):
        self.calls += 1
        if self.on_verify is not None:
            self.on_verify()
        if self.fail:
            raise OpenMaicConversationProbeClientError(
                "openmaic_probe_failed", "probe failed"
            )
        return {
            "chat": {
                "verified": True,
                "noCookieStatus": 401,
                "exchangeStatus": 204,
                "cookieHttpOnly": True,
                "wrongStageStatus": 403,
                "chatStatus": 200,
            },
            "transcription": {
                "verified": True,
                "overrideStatus": 400,
                "cleanStatus": 200,
                "proof": {
                    "asrPolicy": {
                        "enforced": True,
                        "providerId": "qwen-asr",
                        "modelId": "qwen3-asr-flash",
                        "fallbackAllowed": False,
                    }
                },
            },
        }


class _ChildRepository(_RecoveryRepository):
    def __init__(self, rows):
        super().__init__(rows)
        self.child = None
        self.child_reserve_calls = 0
        self.child_ready_calls = 0
        self.probe = None
        self.simulate_concurrent_winner = False

    def get_conversation_probe_by_runtime_classroom_for_update(
        self, _conn, *, runtime_classroom_id
    ):
        if self.probe and self.probe["runtime_classroom_id"] == runtime_classroom_id:
            return self.probe
        return None

    def get_tts_credential_recovery_by_request(
        self, _conn, *, recovery_request_id, **_kwargs
    ):
        if self.child and self.child["recovery_request_id"] == recovery_request_id:
            return self.child
        return None

    def get_tts_credential_recovery_by_runtime(
        self, _conn, *, runtime_id, **_kwargs
    ):
        if self.child and self.child["runtime_classroom_id"] == runtime_id:
            return self.child
        return None

    def get_tts_credential_recovery_by_parent(
        self, _conn, *, parent_recovery_id, **_kwargs
    ):
        if self.child and self.child["parent_recovery_id"] == parent_recovery_id:
            return self.child
        return None

    def reserve_tts_credential_recovery(self, _conn, **values):
        self.child_reserve_calls += 1
        runtime = self.rows[values["runtime_id"]]
        parent = self.recovery
        if runtime["status"] != "failed" or parent["status"] != "failed":
            raise RuntimeError("child claim conflict")
        runtime["status"] = "recovering"
        self.child = {
            "id": values["recovery_id"],
            "recovery_request_id": values["recovery_request_id"],
            "runtime_classroom_id": values["runtime_id"],
            "parent_recovery_id": values["parent_recovery_id"],
            "mode": values["mode"],
            "kind": values["kind"],
            "status": "recovering",
            "parent_status": "failed",
            "parent_dispatch_count": 2,
            "parent_error_code": parent["error_code"],
            "parent_error_message_safe": parent["error_message_safe"],
            "parent_terminal_at": parent["terminal_at"],
            "parent_expected_upstream_recovery_id": PARENT_UPSTREAM_ID,
            "parent_upstream_recovery_id": PARENT_UPSTREAM_ID,
            "parent_db_snapshot_sha256": values["parent_db_snapshot_sha256"],
            "parent_receipt_sha256": values["parent_receipt_sha256"],
            "parent_runtime_snapshot_sha256": values[
                "parent_runtime_snapshot_sha256"
            ],
            "source_upstream_job_id": values["expected_source_job_id"],
            "source_job_snapshot_sha256": parent["source_job_snapshot_sha256"],
            "source_generation_contract_sha256": parent[
                "source_generation_contract_sha256"
            ],
            "expected_upstream_child_id": values["expected_upstream_child_id"],
            "upstream_child_id": None,
            "expected_upstream_classroom_id": values[
                "expected_upstream_classroom_id"
            ],
            "upstream_classroom_id": None,
            "policy_version": None,
            "classroom_policy_version": None,
            "canonical_spec_sha256": None,
            "parent_patch_sha256": None,
            "code_patch_sha256": None,
            "llm_call_count": 0,
            "web_search_call_count": 0,
            "image_generation_call_count": 0,
            "video_generation_call_count": 0,
            "tts_expected_call_count": 10,
            "tts_attempted_call_count": 0,
            "tts_completed_call_count": 0,
            "tts_provider_id": values["tts_provider_id"],
            "tts_model_id": values["tts_model_id"],
            "tts_voice_id": values["tts_voice_id"],
            "tts_fallback_used": False,
            "tts_verified_asset_count": None,
            "scene_count": None,
            "audio_count": None,
            "content_sha256": None,
            "final_artifact_sha256": None,
            "artifact_created_at": None,
            "static_contract_verified": False,
            "conversation_probe_verified": False,
            "conversation_probe_id": None,
            "verified_at": None,
            "receipt_json": None,
            "error_code": None,
            "error_message_safe": None,
            "created_at": values["now"],
            "updated_at": values["now"],
            "terminal_at": None,
        }
        if self.simulate_concurrent_winner:
            raise RuntimeError("concurrent same-key winner committed")
        return self.child

    def attach_tts_credential_recovery_receipt(self, _conn, **values):
        if self.child["upstream_child_id"] is not None:
            return False
        if (
            values["upstream_child_id"]
            != self.child["expected_upstream_child_id"]
            or values["parent_runtime_snapshot_sha256"]
            != self.child["parent_runtime_snapshot_sha256"]
        ):
            return False
        tts = values["calls"]["tts"]
        self.child.update(
            {
                "upstream_child_id": values["upstream_child_id"],
                "policy_version": values["policy"]["version"],
                "classroom_policy_version": values["policy"][
                    "classroomPolicyVersion"
                ],
                "canonical_spec_sha256": values["policy"][
                    "canonicalSpecSha256"
                ],
                "parent_patch_sha256": values["policy"]["parentPatchSha256"],
                "code_patch_sha256": values["policy"]["patchSha256"],
                "tts_attempted_call_count": tts["attempted"],
                "tts_completed_call_count": tts["completed"],
                "receipt_json": deepcopy(values["receipt"]),
                "updated_at": values["now"],
            }
        )
        return True

    def update_tts_credential_recovery_observation(self, _conn, **values):
        if (
            self.child["tts_attempted_call_count"] > values["tts_attempted_count"]
            or self.child["tts_completed_call_count"]
            > values["tts_completed_count"]
        ):
            return False
        self.child["tts_attempted_call_count"] = values["tts_attempted_count"]
        self.child["tts_completed_call_count"] = values["tts_completed_count"]
        self.child["receipt_json"] = deepcopy(values["receipt"])
        if values["progressed"]:
            self.child["updated_at"] = values["now"]
        return True

    def claim_tts_credential_recovery_validation(self, _conn, **values):
        if self.child["status"] != "recovering":
            return False
        self.child.update(
            {
                "status": "validating",
                "tts_attempted_call_count": 10,
                "tts_completed_call_count": 10,
                "static_contract_verified": False,
                "receipt_json": deepcopy(values["receipt"]),
                "updated_at": values["now"],
            }
        )
        return True

    def complete_tts_credential_static_validation(self, _conn, **values):
        if (
            self.child["status"] != "validating"
            or self.child["static_contract_verified"]
        ):
            return False
        artifact = values["artifact"]
        self.child.update(
            {
                "upstream_classroom_id": artifact["classroomId"],
                "scene_count": artifact["sceneCount"],
                "audio_count": artifact["audioCount"],
                "content_sha256": artifact["contentSha256"],
                "final_artifact_sha256": artifact["artifactSha256"],
                "artifact_created_at": values["receipt"]["completedAt"],
                "tts_verified_asset_count": 10,
                "static_contract_verified": True,
                "receipt_json": deepcopy(values["receipt"]),
                "updated_at": values["now"],
            }
        )
        return True

    def claim_tts_credential_recovery_publication(self, _conn, **values):
        if (
            self.child["status"] != "validating"
            or not self.child["static_contract_verified"]
            or self.probe is None
            or self.probe.get("id") != values["conversation_probe_id"]
            or self.probe.get("finalized_at") is None
            or self.probe.get("tts_credential_recovery_id")
            != self.child["id"]
        ):
            return False
        self.child["status"] = "publishing"
        self.child["updated_at"] = values["now"]
        return True

    def fail_tts_credential_recovery(self, _conn, **values):
        if self.child["status"] != values["expected_status"]:
            return False
        if (
            values["expected_status"] == "validating"
            and self.probe is not None
            and self.probe.get("finalized_at") is not None
            and self.probe.get("runtime_classroom_id")
            == self.child["runtime_classroom_id"]
            and self.probe.get("upstream_classroom_id")
            == self.child["upstream_classroom_id"]
            and self.probe.get("candidate_kind")
            == "tts_credential_recovery"
            and self.probe.get("deterministic_recovery_id")
            == self.child["parent_recovery_id"]
            and self.probe.get("tts_credential_recovery_id")
            == self.child["id"]
        ):
            return False
        incoming_attempted = values["tts_attempted_count"]
        incoming_completed = values["tts_completed_count"]
        regressed = (
            incoming_attempted is not None
            and incoming_attempted
            < self.child["tts_attempted_call_count"]
        ) or (
            incoming_completed is not None
            and incoming_completed
            < self.child["tts_completed_call_count"]
        )
        self.child.update(
            {
                "status": "failed",
                "error_code": (
                    "openmaic_tts_credential_counter_regression"
                    if regressed
                    else values["error_code"]
                ),
                "error_message_safe": (
                    "TTS 凭证恢复终态计数与已持久化进度不一致"
                    if regressed
                    else values["error_message_safe"]
                ),
                "terminal_at": values["now"],
                "updated_at": values["now"],
                "conversation_probe_verified": False,
            }
        )
        if values["receipt"] is not None and not regressed:
            self.child["receipt_json"] = deepcopy(values["receipt"])
        if incoming_attempted is not None:
            self.child["tts_attempted_call_count"] = max(
                self.child["tts_attempted_call_count"], incoming_attempted
            )
        if incoming_completed is not None:
            self.child["tts_completed_call_count"] = max(
                self.child["tts_completed_call_count"], incoming_completed
            )
        self.rows[values["runtime_id"]]["status"] = "failed"
        return True

    def fail_stale_tts_credential_recovery(self, _conn, **values):
        if not (
            self.child["status"] == values["expected_status"]
            and self.child["updated_at"] == values["expected_updated_at"]
            and self.child["updated_at"] <= values["stale_cutoff"]
            and self.child["tts_attempted_call_count"]
            == values["expected_tts_attempted_count"]
            and self.child["tts_completed_call_count"]
            == values["expected_tts_completed_count"]
        ):
            return False
        if values["expected_status"] in {"validating", "publishing"}:
            finalized = (
                self.probe is not None
                and self.probe.get("finalized_at") is not None
            )
            if values["expected_status"] == "validating" and finalized:
                return False
            if values["expected_status"] == "publishing" and not finalized:
                return False
        return self.fail_tts_credential_recovery(
            _conn,
            recovery_id=values["recovery_id"],
            runtime_id=values["runtime_id"],
            source_upstream_job_id=values["source_upstream_job_id"],
            expected_status=values["expected_status"],
            error_code=values["error_code"],
            error_message_safe=values["error_message_safe"],
            receipt=None,
            tts_attempted_count=None,
            tts_completed_count=None,
            now=values["now"],
        )

    def mark_ready_from_tts_credential_recovery(self, _conn, **values):
        assert self.child["status"] == "publishing"
        assert values["parent_recovery_id"] == self.recovery["id"]
        assert values["parent_db_snapshot_sha256"] == self.child[
            "parent_db_snapshot_sha256"
        ]
        assert values["parent_receipt_sha256"] == self.child[
            "parent_receipt_sha256"
        ]
        assert values["parent_runtime_snapshot_sha256"] == self.child[
            "parent_runtime_snapshot_sha256"
        ]
        self.child_ready_calls += 1
        self.child.update(
            {
                "status": "succeeded",
                "conversation_probe_verified": True,
                "conversation_probe_id": values["conversation_probe_id"],
                "verified_at": values["now"],
                "receipt_json": deepcopy(values["receipt"]),
                "terminal_at": values["now"],
                "updated_at": values["now"],
            }
        )
        runtime = self.rows[values["runtime_id"]]
        runtime.update(
            {
                "status": "ready",
                "quality_status": "pending_review",
                "upstream_classroom_id": values["upstream_classroom_id"],
                "feature_manifest_json": deepcopy(values["feature_manifest"]),
                "error_code": None,
                "error_message_safe": None,
                "ready_at": values["now"],
            }
        )


def _child_request(request_id=REQUEST_ID):
    return {
        "expectedSourceJobId": SOURCE_JOB_ID,
        "expectedParentRecoveryId": PARENT_UPSTREAM_ID,
        "recoveryRequestId": request_id,
        "mode": TTS_CREDENTIAL_RECOVERY_REQUEST_MODE,
    }


def _child_service(*, status="running", probe_fail=False):
    service, base_repository, _base_runtime, _base_recovery, _base_probe = (
        _base_service()
    )
    repository = _ChildRepository(
        [deepcopy(row) for row in base_repository.rows.values()]
    )
    runtime = repository.rows["runtime-attempt-3"]
    runtime.update(
        {
            "status": "failed",
            "upstream_job_id": SOURCE_JOB_ID,
            "upstream_classroom_id": None,
            "error_code": "openmaic_generation_failed",
            "error_message_safe": "original attempt-three generation failure",
        }
    )
    parent_upstream = _parent_upstream()
    parent = {
        "id": "local-parent-recovery-1",
        "recovery_request_id": "approved-parent-recovery-v1",
        "runtime_classroom_id": runtime["id"],
        "mode": RECOVERY_MODE,
        "kind": RECOVERY_KIND,
        "status": "failed",
        "dispatch_count": 2,
        "first_dispatch_error_code": "openmaic_recovery_upstream_rejected",
        "first_dispatch_error_message_safe": "pre-claim forwarded auth rejection",
        "first_dispatch_rejected_at": 10,
        "source_runtime_status": "failed",
        "source_runtime_error_code": "openmaic_generation_failed",
        "source_runtime_error_message_safe": runtime["error_message_safe"],
        "source_upstream_job_id": SOURCE_JOB_ID,
        "source_job_status": "failed",
        "source_job_error": "structured_output_exhausted",
        "source_scenes_generated": 4,
        "source_total_scenes": 10,
        "source_completed_at": parent_upstream.source["completedAt"],
        "source_job_snapshot_sha256": parent_upstream.source[
            "jobSnapshotSha256"
        ],
        "source_generation_contract_sha256": "f" * 64,
        "expected_upstream_recovery_id": PARENT_UPSTREAM_ID,
        "upstream_recovery_id": PARENT_UPSTREAM_ID,
        "policy_id": parent_upstream.policy["marker"],
        "policy_version": parent_upstream.policy["version"],
        "canonical_spec_sha256": RECOVERY_CANONICAL_SPEC_SHA256,
        "code_patch_sha256": RECOVERY_PATCH_SHA256,
        "llm_call_count": 0,
        "web_search_call_count": 0,
        "image_generation_call_count": 0,
        "video_generation_call_count": 0,
        "tts_expected_call_count": 10,
        "tts_attempted_call_count": 1,
        "tts_completed_call_count": 0,
        "tts_provider_id": "qwen-tts",
        "tts_model_id": "qwen3-tts-flash",
        "tts_voice_id": "Serena",
        "tts_fallback_used": False,
        "tts_verified_asset_count": None,
        "upstream_classroom_id": None,
        "scene_count": None,
        "content_sha256": None,
        "final_artifact_sha256": None,
        "artifact_created_at": None,
        "static_contract_verified": False,
        "conversation_probe_verified": False,
        "verified_at": None,
        "error_code": "openmaic_deterministic_recovery_failed",
        "error_message_safe": "parent TTS credential failure",
        "receipt_json": parent_upstream.audit_receipt(),
        "created_at": 20,
        "updated_at": 30,
        "terminal_at": 30,
    }
    repository.recovery = parent
    classroom = _child_classroom()
    classroom_client = _ClassroomClient(classroom)
    parent_client = _ParentRuntimeClient(parent_upstream)
    child_client = _ChildRuntimeClient(status, classroom)
    probe_service = _ChildProbeService(repository)
    probe_client = _ChildProbeClient(fail=probe_fail)
    service.repository = repository
    service.client = classroom_client
    service.deterministic_recovery_enabled = True
    service.deterministic_recovery_redispatch_enabled = False
    service.deterministic_recovery_client = parent_client
    service.tts_credential_recovery_enabled = True
    service.tts_credential_recovery_client = child_client
    service.conversation_probe_service = probe_service
    service.conversation_probe_client = probe_client
    return (
        service,
        repository,
        classroom_client,
        parent_client,
        child_client,
        probe_service,
        probe_client,
    )


class OpenMaicTtsCredentialRecoveryServiceTest(unittest.TestCase):
    def test_concurrent_same_key_reservation_loser_returns_winner_without_post(self):
        (
            service,
            repository,
            runtime_client,
            _parent_client,
            child_client,
            _probe,
            _probe_client,
        ) = _child_service()
        repository.simulate_concurrent_winner = True

        result = service.recover_tts_credentials(
            "runtime-attempt-3", _child_request()
        )

        self.assertTrue(result["ttsCredentialRecovery"]["idempotent"])
        self.assertEqual(repository.child_reserve_calls, 1)
        self.assertEqual(child_client.start_calls, 0)
        self.assertEqual(runtime_client.start_calls, 0)

    def test_reserve_precedes_only_post_and_same_key_is_zero_external(self):
        (
            service,
            repository,
            runtime_client,
            parent_client,
            child_client,
            _probe,
            _probe_client,
        ) = _child_service()
        observed = []
        original_start = child_client.start_recovery

        def start(**kwargs):
            observed.append(
                (
                    repository.child is not None,
                    repository.rows["runtime-attempt-3"]["status"],
                )
            )
            return original_start(**kwargs)

        child_client.start_recovery = start
        parent_before = deepcopy(repository.recovery)

        first = service.recover_tts_credentials(
            "runtime-attempt-3", _child_request()
        )
        external_after_first = (
            child_client.policy_calls,
            child_client.absence_calls,
            parent_client.calls,
            child_client.start_calls,
        )
        replay = service.recover_tts_credentials(
            "runtime-attempt-3", _child_request()
        )

        self.assertEqual(observed, [(True, "recovering")])
        self.assertEqual(repository.child_reserve_calls, 1)
        self.assertEqual(child_client.start_calls, 1)
        self.assertEqual(
            (
                child_client.policy_calls,
                child_client.absence_calls,
                parent_client.calls,
                child_client.start_calls,
            ),
            external_after_first,
        )
        self.assertEqual(first["ttsCredentialRecovery"]["status"], "recovering")
        self.assertTrue(replay["ttsCredentialRecovery"]["idempotent"])
        self.assertEqual(repository.recovery, parent_before)
        self.assertEqual(len(repository.rows), 3)
        self.assertEqual(runtime_client.start_calls, 0)

        with self.assertRaises(OpenMaicRuntimeServiceError) as different:
            service.recover_tts_credentials(
                "runtime-attempt-3", _child_request("different-child-key-v1")
            )
        self.assertEqual(
            different.exception.code,
            "openmaic_tts_credential_recovery_already_used",
        )
        self.assertEqual(child_client.start_calls, 1)

    def test_preflight_failures_never_reserve_or_post(self):
        cases = ("health", "parent", "absence")
        for case in cases:
            with self.subTest(case=case):
                (
                    service,
                    repository,
                    _runtime_client,
                    parent_client,
                    child_client,
                    _probe,
                    _probe_client,
                ) = _child_service()
                if case == "health":
                    child_client.policy_error = OpenMaicTtsCredentialRecoveryError(
                        "policy_drift", "policy drift", status_code=409
                    )
                elif case == "parent":
                    parent_client.error = OpenMaicDeterministicRecoveryError(
                        "parent_drift", "parent drift", status_code=409
                    )
                else:
                    child_client.absence_error = OpenMaicTtsCredentialRecoveryError(
                        "absence_not_proven", "absence drift", status_code=409
                    )
                parent_before = deepcopy(repository.recovery)

                with self.assertRaises(OpenMaicRuntimeServiceError):
                    service.recover_tts_credentials(
                        "runtime-attempt-3", _child_request()
                    )

                self.assertEqual(repository.child_reserve_calls, 0)
                self.assertEqual(child_client.start_calls, 0)
                self.assertEqual(
                    repository.rows["runtime-attempt-3"]["status"], "failed"
                )
                self.assertEqual(repository.recovery, parent_before)

    def test_lost_post_response_reconciles_get_only_and_never_reposts(self):
        (
            service,
            repository,
            runtime_client,
            _parent_client,
            child_client,
            probe,
            _probe_client,
        ) = _child_service(status="succeeded")
        child_client.start_error = OpenMaicTtsCredentialRecoveryError(
            "openmaic_tts_credential_unavailable",
            "response lost after claim",
            status_code=503,
        )

        with self.assertRaises(OpenMaicRuntimeServiceError) as caught:
            service.recover_tts_credentials(
                "runtime-attempt-3", _child_request()
            )
        self.assertEqual(
            caught.exception.code,
            "openmaic_tts_credential_dispatch_uncertain",
        )
        self.assertIsNone(repository.child["upstream_child_id"])
        child_client.start_error = None

        result = service.tts_credential_recovery_status("runtime-attempt-3")
        replay = service.recover_tts_credentials(
            "runtime-attempt-3", _child_request()
        )

        self.assertEqual(result["ttsCredentialRecovery"]["status"], "succeeded")
        self.assertTrue(replay["ttsCredentialRecovery"]["idempotent"])
        self.assertEqual(child_client.start_calls, 1)
        self.assertEqual(child_client.get_calls, 1)
        self.assertEqual(runtime_client.start_calls, 0)
        self.assertEqual(probe.issue_calls, 1)

    def test_partial_terminal_failure_restores_runtime_and_preserves_parent(self):
        (
            service,
            repository,
            runtime_client,
            _parent_client,
            child_client,
            _probe,
            _probe_client,
        ) = _child_service(status="failed")
        parent_before = deepcopy(repository.recovery)

        result = service.recover_tts_credentials(
            "runtime-attempt-3", _child_request()
        )

        self.assertEqual(result["ttsCredentialRecovery"]["status"], "failed")
        self.assertEqual(
            result["ttsCredentialRecovery"]["calls"]["tts"],
            {"expected": 10, "attempted": 2, "completed": 1},
        )
        self.assertEqual(
            repository.rows["runtime-attempt-3"]["error_code"],
            "openmaic_generation_failed",
        )
        self.assertEqual(repository.recovery, parent_before)
        self.assertEqual(child_client.start_calls, 1)
        self.assertEqual(runtime_client.start_calls, 0)

    def test_explicit_child_rejection_is_terminal_and_never_reposts(self):
        (
            service,
            repository,
            _runtime_client,
            _parent_client,
            child_client,
            _probe,
            _probe_client,
        ) = _child_service()
        child_client.start_error = OpenMaicTtsCredentialRecoveryError(
            "openmaic_tts_credential_upstream_rejected",
            "explicit pre-provider rejection",
            status_code=409,
        )

        with self.assertRaises(OpenMaicRuntimeServiceError):
            service.recover_tts_credentials(
                "runtime-attempt-3", _child_request()
            )
        replay = service.recover_tts_credentials(
            "runtime-attempt-3", _child_request()
        )

        self.assertEqual(repository.child["status"], "failed")
        self.assertTrue(replay["ttsCredentialRecovery"]["idempotent"])
        self.assertEqual(child_client.start_calls, 1)

    def test_queued_jumps_to_exact_ten_and_child_probe_ready(self):
        (
            service,
            repository,
            runtime_client,
            _parent_client,
            child_client,
            probe,
            _probe_client,
        ) = _child_service(status="running")
        parent_before = deepcopy(repository.recovery)
        service.recover_tts_credentials("runtime-attempt-3", _child_request())
        child_client.status = "succeeded"

        result = service.tts_credential_recovery_status("runtime-attempt-3")

        runtime = repository.rows["runtime-attempt-3"]
        self.assertEqual(result["ttsCredentialRecovery"]["status"], "succeeded")
        self.assertEqual(
            result["ttsCredentialRecovery"]["calls"]["tts"],
            {"expected": 10, "attempted": 10, "completed": 10},
        )
        self.assertEqual(runtime["status"], "ready")
        self.assertEqual(runtime["quality_status"], "pending_review")
        self.assertEqual(runtime["upstream_job_id"], SOURCE_JOB_ID)
        self.assertEqual(probe.issue_args[2], repository.recovery["id"])
        self.assertEqual(probe.issue_args[3], repository.child["id"])
        self.assertTrue(repository.child["static_contract_verified"])
        self.assertTrue(repository.child["conversation_probe_verified"])
        self.assertEqual(repository.recovery, parent_before)
        self.assertEqual(len(repository.rows), 3)
        self.assertEqual(runtime_client.start_calls, 0)

    def test_probe_failure_is_terminal_but_static_evidence_and_parent_remain(self):
        (
            service,
            repository,
            runtime_client,
            _parent_client,
            child_client,
            probe,
            _probe_client,
        ) = _child_service(status="succeeded", probe_fail=True)
        parent_before = deepcopy(repository.recovery)

        with self.assertRaises(OpenMaicRuntimeServiceError):
            service.recover_tts_credentials(
                "runtime-attempt-3", _child_request()
            )
        replay = service.recover_tts_credentials(
            "runtime-attempt-3", _child_request()
        )

        self.assertEqual(repository.child["status"], "failed")
        self.assertTrue(repository.child["static_contract_verified"])
        self.assertFalse(repository.child["conversation_probe_verified"])
        self.assertEqual(repository.recovery, parent_before)
        self.assertTrue(replay["ttsCredentialRecovery"]["idempotent"])
        self.assertEqual(child_client.start_calls, 1)
        self.assertEqual(probe.issue_calls, 1)
        self.assertEqual(runtime_client.start_calls, 0)

    def test_final_parent_three_hash_drift_is_rejected(self):
        (
            service,
            repository,
            _runtime_client,
            _parent_client,
            _child_client,
            _probe,
            _probe_client,
        ) = _child_service(status="succeeded")

        def mutate_parent():
            repository.recovery["error_message_safe"] = "drifted parent"

        service.conversation_probe_service.parent_mutator = mutate_parent

        with self.assertRaises(OpenMaicRuntimeServiceError):
            service.recover_tts_credentials(
                "runtime-attempt-3", _child_request()
            )

        self.assertEqual(repository.child_ready_calls, 0)
        self.assertEqual(repository.child["status"], "failed")
        self.assertEqual(
            repository.rows["runtime-attempt-3"]["status"], "failed"
        )

    def test_concurrent_get_does_not_restart_or_kill_unfinalized_probe(self):
        (
            service,
            repository,
            _runtime_client,
            _parent_client,
            child_client,
            probe,
            probe_client,
        ) = _child_service(status="succeeded")
        observed = []
        static_gets = []
        static_states = []
        original_get = service.client.get_classroom

        def counted_get(classroom_id):
            # Both external-read phases have a durable unique owner first.
            static_states.append(
                (
                    repository.child["status"],
                    repository.child["static_contract_verified"],
                )
            )
            static_gets.append(classroom_id)
            return original_get(classroom_id)

        service.client.get_classroom = counted_get

        def concurrent_status():
            observed.append(
                service.tts_credential_recovery_status(
                    "runtime-attempt-3"
                )["ttsCredentialRecovery"]["status"]
            )

        probe_client.on_verify = concurrent_status
        result = service.recover_tts_credentials(
            "runtime-attempt-3", _child_request()
        )

        self.assertEqual(observed, ["validating"])
        self.assertEqual(result["ttsCredentialRecovery"]["status"], "succeeded")
        self.assertEqual(probe.issue_calls, 1)
        self.assertEqual(child_client.start_calls, 1)
        self.assertEqual(repository.child_ready_calls, 1)
        self.assertEqual(static_gets, [CLASSROOM_ID, CLASSROOM_ID])
        self.assertEqual(
            static_states,
            [("validating", False), ("publishing", True)],
        )

    def test_get_can_win_finalized_probe_publication_without_duplicate_static(self):
        (
            service,
            repository,
            _runtime_client,
            _parent_client,
            child_client,
            probe,
            _probe_client,
        ) = _child_service(status="succeeded")
        observed = []
        static_gets = []
        original_get = service.client.get_classroom

        def counted_get(classroom_id):
            static_gets.append((classroom_id, repository.child["status"]))
            return original_get(classroom_id)

        service.client.get_classroom = counted_get
        probe.on_finalize = lambda: observed.append(
            service.tts_credential_recovery_status(
                "runtime-attempt-3"
            )["ttsCredentialRecovery"]["status"]
        )

        result = service.recover_tts_credentials(
            "runtime-attempt-3", _child_request()
        )

        self.assertEqual(observed, ["succeeded"])
        self.assertEqual(result["ttsCredentialRecovery"]["status"], "succeeded")
        self.assertEqual(
            static_gets,
            [
                (CLASSROOM_ID, "validating"),
                (CLASSROOM_ID, "publishing"),
            ],
        )
        self.assertEqual(probe.issue_calls, 1)
        self.assertEqual(repository.child_ready_calls, 1)
        self.assertEqual(child_client.start_calls, 1)

    def test_finalize_committed_then_raised_is_reconciled_by_get_publication(self):
        (
            service,
            repository,
            _runtime_client,
            _parent_client,
            child_client,
            probe,
            probe_client,
        ) = _child_service(status="succeeded")
        probe.raise_after_finalize = True

        first = service.recover_tts_credentials(
            "runtime-attempt-3", _child_request()
        )

        self.assertEqual(first["ttsCredentialRecovery"]["status"], "validating")
        self.assertTrue(repository.child["static_contract_verified"])
        self.assertIsNotNone(repository.probe["finalized_at"])
        self.assertEqual(repository.rows["runtime-attempt-3"]["status"], "recovering")
        probe.raise_after_finalize = False

        recovered = service.tts_credential_recovery_status("runtime-attempt-3")

        self.assertEqual(recovered["ttsCredentialRecovery"]["status"], "succeeded")
        self.assertEqual(repository.child_ready_calls, 1)
        self.assertEqual(probe.issue_calls, 1)
        self.assertEqual(probe.finalize_calls, 1)
        self.assertEqual(probe_client.calls, 1)
        self.assertEqual(child_client.start_calls, 1)

    def test_publishing_get_is_observation_only_then_exact_stale_failure(self):
        (
            service,
            repository,
            _runtime_client,
            _parent_client,
            child_client,
            probe,
            probe_client,
        ) = _child_service(status="running")
        service.recover_tts_credentials("runtime-attempt-3", _child_request())
        succeeded = _child_upstream("succeeded", child_client.classroom)
        repository.claim_tts_credential_recovery_validation(
            object(),
            recovery_id=repository.child["id"],
            receipt=succeeded.audit_receipt(),
            now=repository.child["updated_at"],
        )
        repository.complete_tts_credential_static_validation(
            object(),
            recovery_id=repository.child["id"],
            artifact=succeeded.artifact,
            receipt=succeeded.audit_receipt(),
            now=repository.child["updated_at"],
        )
        receipts = probe_client.verify({"probeId": "probe-publishing-stale"})
        repository.probe = {
            "id": "probe-publishing-stale",
            "runtime_classroom_id": "runtime-attempt-3",
            "upstream_classroom_id": CLASSROOM_ID,
            "candidate_kind": "tts_credential_recovery",
            "deterministic_recovery_id": repository.recovery["id"],
            "tts_credential_recovery_id": repository.child["id"],
            "finalized_at": 123,
            "chat_receipt_json": receipts["chat"],
            "transcription_receipt_json": receipts["transcription"],
        }
        self.assertTrue(
            repository.claim_tts_credential_recovery_publication(
                object(),
                recovery_id=repository.child["id"],
                runtime_id="runtime-attempt-3",
                conversation_probe_id="probe-publishing-stale",
                now=repository.child["updated_at"],
            )
        )
        service.client.get_classroom = lambda _classroom_id: (_ for _ in ()).throw(
            AssertionError("publishing GET must not re-read classroom media")
        )
        provider_calls = probe_client.calls

        observed = service.tts_credential_recovery_status("runtime-attempt-3")

        self.assertEqual(observed["ttsCredentialRecovery"]["status"], "publishing")
        self.assertEqual(probe_client.calls, provider_calls)
        self.assertEqual(child_client.get_calls, 0)
        repository.child["created_at"] = 1
        repository.child["updated_at"] = 1
        repository.child["receipt_json"]["updatedAt"] = (
            "2000-01-01T00:00:00.000Z"
        )

        terminal = service.tts_credential_recovery_status("runtime-attempt-3")

        self.assertEqual(terminal["ttsCredentialRecovery"]["status"], "failed")
        self.assertEqual(probe_client.calls, provider_calls)
        self.assertEqual(probe.issue_calls, 0)
        self.assertEqual(child_client.get_calls, 0)

    def test_late_old_upstream_observation_cannot_kill_validating_child(self):
        for old_status in ("running", "failed"):
            with self.subTest(old_status=old_status):
                (
                    service,
                    repository,
                    _runtime_client,
                    _parent_client,
                    child_client,
                    _probe,
                    _probe_client,
                ) = _child_service(status="running")
                service.recover_tts_credentials(
                    "runtime-attempt-3", _child_request()
                )
                stale_read = deepcopy(repository.child)
                succeeded = _child_upstream("succeeded", child_client.classroom)
                repository.claim_tts_credential_recovery_validation(
                    object(),
                    recovery_id=repository.child["id"],
                    receipt=succeeded.audit_receipt(),
                    now=repository.child["updated_at"],
                )
                repository.complete_tts_credential_static_validation(
                    object(),
                    recovery_id=repository.child["id"],
                    artifact=succeeded.artifact,
                    receipt=succeeded.audit_receipt(),
                    now=repository.child["updated_at"],
                )

                result = service._handle_tts_credential_recovery_result(
                    stale_read,
                    _child_upstream(old_status, child_client.classroom),
                    idempotent=True,
                )

                self.assertEqual(
                    result["ttsCredentialRecovery"]["status"], "validating"
                )
                self.assertEqual(repository.child["status"], "validating")
                self.assertTrue(repository.child["static_contract_verified"])

    def test_late_static_failure_cannot_kill_other_validating_winner(self):
        (
            service,
            repository,
            _runtime_client,
            _parent_client,
            child_client,
            _probe,
            _probe_client,
        ) = _child_service(status="running")
        service.recover_tts_credentials("runtime-attempt-3", _child_request())
        stale_read = deepcopy(repository.child)
        succeeded = _child_upstream("succeeded", child_client.classroom)
        repository.claim_tts_credential_recovery_validation(
            object(),
            recovery_id=repository.child["id"],
            receipt=succeeded.audit_receipt(),
            now=repository.child["updated_at"],
        )
        service.client.get_classroom = lambda _classroom_id: (_ for _ in ()).throw(
            ValueError("transient old poll media failure")
        )

        result = service._handle_tts_credential_recovery_result(
            stale_read, succeeded, idempotent=True
        )

        self.assertEqual(result["ttsCredentialRecovery"]["status"], "validating")
        self.assertEqual(repository.child["status"], "validating")
        self.assertIsNone(repository.child["error_code"])

    def test_validating_missing_probe_is_observation_only_then_stales(self):
        (
            service,
            repository,
            _runtime_client,
            _parent_client,
            child_client,
            probe,
            _probe_client,
        ) = _child_service(status="running")
        service.recover_tts_credentials("runtime-attempt-3", _child_request())
        succeeded = _child_upstream("succeeded", child_client.classroom)
        repository.claim_tts_credential_recovery_validation(
            object(),
            recovery_id=repository.child["id"],
            receipt=succeeded.audit_receipt(),
            now=repository.child["updated_at"],
        )
        repository.probe = None
        service.client.get_classroom = lambda _classroom_id: (_ for _ in ()).throw(
            AssertionError("active validating GET must not re-read static media")
        )

        observed = service.tts_credential_recovery_status(
            "runtime-attempt-3"
        )

        self.assertEqual(observed["ttsCredentialRecovery"]["status"], "validating")
        self.assertEqual(probe.issue_calls, 0)
        repository.child["created_at"] = 1
        repository.child["updated_at"] = 1
        repository.child["receipt_json"]["updatedAt"] = (
            "2000-01-01T00:00:00.000Z"
        )
        terminal = service.tts_credential_recovery_status(
            "runtime-attempt-3"
        )
        self.assertEqual(terminal["ttsCredentialRecovery"]["status"], "failed")
        self.assertEqual(probe.issue_calls, 0)

    def test_new_progress_or_finalized_probe_beats_old_stale_observer(self):
        (
            service,
            repository,
            _runtime_client,
            _parent_client,
            child_client,
            _probe,
            probe_client,
        ) = _child_service(status="running")
        service.recover_tts_credentials("runtime-attempt-3", _child_request())
        stale_recovering = deepcopy(repository.child)
        stale_recovering["created_at"] = 1
        stale_recovering["updated_at"] = 1
        repository.child["updated_at"] += 1000
        repository.child["tts_attempted_call_count"] = 3
        repository.child["tts_completed_call_count"] = 2

        self.assertFalse(
            service._terminally_fail_stale_tts_credential_recovery(
                stale_recovering,
                error_code="openmaic_tts_credential_upstream_stale",
                error_message_safe="stale old poll",
            )
        )
        self.assertEqual(repository.child["status"], "recovering")
        succeeded = _child_upstream("succeeded", child_client.classroom)
        repository.claim_tts_credential_recovery_validation(
            object(),
            recovery_id=repository.child["id"],
            receipt=succeeded.audit_receipt(),
            now=1,
        )
        repository.complete_tts_credential_static_validation(
            object(),
            recovery_id=repository.child["id"],
            artifact=succeeded.artifact,
            receipt=succeeded.audit_receipt(),
            now=1,
        )
        repository.child["created_at"] = 1
        repository.child["updated_at"] = 1
        receipts = probe_client.verify({"probeId": "probe-finalized-race"})
        repository.probe = {
            "id": "probe-finalized-race",
            "runtime_classroom_id": "runtime-attempt-3",
            "upstream_classroom_id": CLASSROOM_ID,
            "candidate_kind": "tts_credential_recovery",
            "deterministic_recovery_id": repository.recovery["id"],
            "tts_credential_recovery_id": repository.child["id"],
            "finalized_at": 321,
            "chat_receipt_json": receipts["chat"],
            "transcription_receipt_json": receipts["transcription"],
        }
        stale_validating = deepcopy(repository.child)

        self.assertFalse(
            service._terminally_fail_stale_tts_credential_recovery(
                stale_validating,
                error_code="openmaic_tts_credential_probe_stale",
                error_message_safe="stale probe observer",
            )
        )
        self.assertEqual(repository.child["status"], "validating")

    def test_finalized_probe_resumes_static_and_marks_ready_without_provider(self):
        (
            service,
            repository,
            runtime_client,
            _parent_client,
            child_client,
            probe,
            probe_client,
        ) = _child_service(status="running")
        service.recover_tts_credentials("runtime-attempt-3", _child_request())
        succeeded = _child_upstream("succeeded", child_client.classroom)
        repository.claim_tts_credential_recovery_validation(
            object(),
            recovery_id=repository.child["id"],
            receipt=succeeded.audit_receipt(),
            now=repository.child["updated_at"],
        )
        repository.complete_tts_credential_static_validation(
            object(),
            recovery_id=repository.child["id"],
            artifact=succeeded.artifact,
            receipt=succeeded.audit_receipt(),
            now=repository.child["updated_at"],
        )
        receipts = probe_client.verify({"probeId": "probe-child-resume"})
        repository.probe = {
            "id": "probe-child-resume",
            "runtime_classroom_id": "runtime-attempt-3",
            "upstream_classroom_id": CLASSROOM_ID,
            "candidate_kind": "tts_credential_recovery",
            "deterministic_recovery_id": repository.recovery["id"],
            "tts_credential_recovery_id": repository.child["id"],
            "finalized_at": 123,
            "chat_receipt_json": receipts["chat"],
            "transcription_receipt_json": receipts["transcription"],
        }
        starts_before = child_client.start_calls

        result = service.tts_credential_recovery_status("runtime-attempt-3")

        self.assertEqual(result["ttsCredentialRecovery"]["status"], "succeeded")
        self.assertEqual(child_client.start_calls, starts_before)
        self.assertEqual(probe.issue_calls, 0)
        self.assertEqual(runtime_client.start_calls, 0)

    def test_regressive_running_and_failed_receipts_terminalize_without_count_loss(self):
        for terminal_status in ("running", "failed"):
            with self.subTest(terminal_status=terminal_status):
                (
                    service,
                    repository,
                    _runtime_client,
                    _parent_client,
                    child_client,
                    _probe,
                    _probe_client,
                ) = _child_service(status="running")
                service.recover_tts_credentials(
                    "runtime-attempt-3", _child_request()
                )
                repository.child["tts_attempted_call_count"] = 6
                repository.child["tts_completed_call_count"] = 5
                old_receipt = deepcopy(repository.child["receipt_json"])
                child_client.status = terminal_status

                result = service.tts_credential_recovery_status(
                    "runtime-attempt-3"
                )

                self.assertEqual(
                    result["ttsCredentialRecovery"]["status"], "failed"
                )
                self.assertEqual(
                    result["ttsCredentialRecovery"]["calls"]["tts"],
                    {"expected": 10, "attempted": 6, "completed": 5},
                )
                self.assertEqual(
                    repository.child["error_code"],
                    "openmaic_tts_credential_counter_regression",
                )
                self.assertEqual(repository.child["receipt_json"], old_receipt)

    def test_unchanged_running_stales_after_fifteen_minutes(self):
        (
            service,
            repository,
            _runtime_client,
            _parent_client,
            child_client,
            _probe,
            _probe_client,
        ) = _child_service(status="running")
        service.recover_tts_credentials("runtime-attempt-3", _child_request())
        frozen_upstream = replace(
            _child_upstream("running", child_client.classroom),
            updated_at="2000-01-01T00:00:00.000Z",
        )
        child_client.get_recovery = lambda **_kwargs: frozen_upstream
        repository.child["created_at"] = 1
        repository.child["updated_at"] = 1
        repository.child["receipt_json"] = frozen_upstream.audit_receipt()

        result = service.tts_credential_recovery_status("runtime-attempt-3")

        self.assertEqual(result["ttsCredentialRecovery"]["status"], "failed")
        self.assertEqual(
            result["ttsCredentialRecovery"]["errorCode"],
            "openmaic_tts_credential_upstream_stale",
        )
        self.assertEqual(child_client.start_calls, 1)
