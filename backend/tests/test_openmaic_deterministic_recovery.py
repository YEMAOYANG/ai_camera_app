from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import hashlib
import io
import json
import unittest
from unittest.mock import patch
from urllib.error import HTTPError

from flask import Flask

from integrations.openmaic_conversation_probe_client import (
    OpenMaicConversationProbeClientError,
)
from integrations.openmaic_deterministic_recovery_client import (
    RECOVERY_CANONICAL_SPEC_SHA256,
    RECOVERY_KIND,
    RECOVERY_MODE,
    RECOVERY_PATCH_SHA256,
    OpenMaicDeterministicRecovery,
    OpenMaicDeterministicRecoveryClient,
    OpenMaicDeterministicRecoveryError,
    OpenMaicRecoverySourceSnapshot,
    deterministic_recovery_identity,
)
from services.openmaic_full_runtime_service import (
    OpenMaicFullRuntimeService,
    OpenMaicRuntimeServiceError,
    SAMPLE_REQUIRED_FEATURES,
)
from services.openmaic_conversation_probe_service import (
    OpenMaicConversationProbeService,
)
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from core.config import ConfigError, _validate_openmaic_deterministic_recovery_config
from tests.test_openmaic_full_runtime import (
    _sample_contract,
    _sample_course,
    _sample_parity_classroom,
)
from routes.internal import openmaic_runtime as recovery_routes
from services import service_factory


def _source_snapshot() -> OpenMaicRecoverySourceSnapshot:
    return OpenMaicRecoverySourceSnapshot(
        job_id="job-attempt-3",
        completed_at="2026-08-18T03:15:00.000Z",
        job_snapshot_sha256="a" * 64,
    )


def _parser_client() -> OpenMaicDeterministicRecoveryClient:
    client = object.__new__(OpenMaicDeterministicRecoveryClient)
    client._expected_canonical_spec_sha256 = "b" * 64
    client._expected_patch_sha256 = "c" * 64
    return client


def _recovery_classroom() -> dict:
    classroom = _sample_parity_classroom()
    classroom_id = "recovered-classroom-1"
    classroom["stage"]["id"] = classroom_id
    for scene in classroom["scenes"]:
        scene["stageId"] = classroom_id
        for action in scene.get("actions", []):
            if action.get("type") == "speech":
                action["audioUrl"] = (
                    f"/api/classroom-media/{classroom_id}/audio/"
                    f"{action['audioId']}.mp3"
                )
    return classroom


def _upstream_recovery(status: str) -> OpenMaicDeterministicRecovery:
    snapshot = _source_snapshot()
    recovery_id, _request_id_sha256 = deterministic_recovery_identity(
        "job-attempt-3", "approved-deterministic-recovery-1"
    )
    artifact = None
    error = None
    attempted = 4 if status == "failed" else 0
    completed = 3 if status == "failed" else 0
    if status == "succeeded":
        attempted = 10
        completed = 10
        classroom = _recovery_classroom()
        content_sha256 = hashlib.sha256(
            json.dumps(
                {"stage": classroom["stage"], "scenes": classroom["scenes"]},
                ensure_ascii=False,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        artifact = {
            "classroomId": "recovered-classroom-1",
            "url": "/classroom/recovered-classroom-1",
            "sceneCount": 10,
            "contentSha256": content_sha256,
            "artifactSha256": "e" * 64,
            "tts": {
                "providerId": "qwen-tts",
                "modelId": "qwen3-tts-flash",
                "voiceId": "Serena",
                "speechCount": 10,
                "fallbackUsed": False,
            },
        }
    if status == "failed":
        error = {
            "code": "deterministic_recovery_failed",
            "message": "Qwen TTS stopped after four scenes",
        }
    return OpenMaicDeterministicRecovery(
        recovery_id=recovery_id,
        status=status,
        step="complete" if status in {"succeeded", "failed"} else "tts",
        progress=100 if status in {"succeeded", "failed"} else 20,
        done=status in {"succeeded", "failed"},
        source=snapshot.to_audit_source(),
        policy={
            "marker": "MIRA_OPENMAIC_SAMPLE_STRUCTURAL_POLICY_V1",
            "version": "mira-sample-deterministic-classroom.v1",
            "canonicalSpecSha256": "b" * 64,
            "patchSha256": "c" * 64,
        },
        calls={
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
        artifact=artifact,
        error=error,
        created_at="2026-08-18T03:16:00.000Z",
        updated_at="2026-08-18T03:20:00.000Z",
        started_at="2026-08-18T03:16:01.000Z",
        completed_at=(
            "2026-08-18T03:20:00.000Z"
            if status in {"succeeded", "failed"}
            else None
        ),
    )


class _RecoveryClient:
    def __init__(self, status: str = "running"):
        self.status = status
        self.policy_calls = 0
        self.source_calls = 0
        self.start_calls = 0
        self.poll_calls = 0
        self.reject_source = False
        self.reject_policy = False
        self.start_error = None
        self.absence_calls = 0
        self.absence_error = None
        self.source_snapshot = None

    def verify_runtime_policy(self, *, source_job_id):
        self.policy_calls += 1
        if self.reject_policy:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_runtime_policy_mismatch",
                "policy mismatch",
                status_code=409,
            )
        return {"enabled": True, "sourceJobId": source_job_id}

    def get_source_snapshot(self, *, source_job_id):
        self.source_calls += 1
        if self.reject_source:
            raise OpenMaicDeterministicRecoveryError(
                "openmaic_recovery_source_not_allowed",
                "source rejected",
                status_code=409,
            )
        self.last_source_job_id = source_job_id
        return self.source_snapshot or _source_snapshot()

    def start_recovery(self, **kwargs):
        self.start_calls += 1
        self.start_kwargs = kwargs
        if self.start_error is not None:
            raise self.start_error
        return _upstream_recovery(self.status)

    def assert_recovery_absent(self, **kwargs):
        self.absence_calls += 1
        self.absence_kwargs = kwargs
        if self.absence_error is not None:
            raise self.absence_error
        return {
            "absent": True,
            "sourceJobId": kwargs["source_job_id"],
            "expectedRecoveryId": kwargs["expected_recovery_id"],
        }

    def get_recovery(self, **kwargs):
        self.poll_calls += 1
        self.poll_kwargs = kwargs
        return _upstream_recovery(self.status)


class _ClassroomClient:
    def __init__(self, classroom: dict):
        self.classroom = classroom
        self.start_calls = 0

    def start_generation(self, **_kwargs):
        self.start_calls += 1
        raise AssertionError("deterministic recovery must not call start_generation")

    def get_classroom(self, classroom_id):
        self.classroom_id = classroom_id
        return deepcopy(self.classroom)

    @staticmethod
    def media_available(_reference, *, expected_prefix):
        return expected_prefix == "audio/"


class _ProbeService:
    def __init__(self):
        self.issue_calls = 0
        self.finalize_calls = 0

    def issue_recovery_candidate(self, runtime_id, classroom_id, recovery_id):
        self.issue_calls += 1
        self.issue_args = (runtime_id, classroom_id, recovery_id)
        return {
            "probeId": "omp-recovery-1",
            "runtimeId": runtime_id,
            "classroomId": classroom_id,
            "candidateKind": "recovery",
        }

    def finalize_probe(self, _probe_id, **_kwargs):
        self.finalize_calls += 1


class _ProbeClient:
    def __init__(self, *, fail: bool = False):
        self.fail = fail
        self.calls = 0

    def verify(self, _probe):
        self.calls += 1
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


class _RecoveryRepository:
    def __init__(self, rows):
        self.rows = {row["id"]: row for row in rows}
        self.recovery = None
        self.reserve_calls = 0
        self.redispatch_reserve_calls = 0
        self.simulate_concurrent_redispatch_winner = False
        self.ready_calls = 0
        self.created_probe = None

    @contextmanager
    def transaction(self):
        yield object()

    @staticmethod
    def decode_json(value, _fallback):
        return value

    def get_runtime_classroom(self, _conn, *, runtime_id, **_kwargs):
        return self.rows.get(runtime_id)

    def get_package_runtime_attempts(
        self, _conn, *, package_id, package_version, **_kwargs
    ):
        return sorted(
            [
                row
                for row in self.rows.values()
                if row["package_id"] == package_id
                and int(row["package_version"]) == int(package_version)
            ],
            key=lambda row: row["attempt_ordinal"],
        )

    def get_deterministic_recovery_by_request(
        self, _conn, *, recovery_request_id, **_kwargs
    ):
        if self.recovery and self.recovery["recovery_request_id"] == recovery_request_id:
            return self.recovery
        return None

    def get_deterministic_recovery_by_runtime(
        self, _conn, *, runtime_id, **_kwargs
    ):
        if self.recovery and self.recovery["runtime_classroom_id"] == runtime_id:
            return self.recovery
        return None

    def reserve_deterministic_recovery(self, _conn, **values):
        self.reserve_calls += 1
        runtime = values["runtime"]
        assert runtime["status"] == "failed"
        runtime["status"] = "recovering"
        snapshot = values["source_job_snapshot"]
        self.recovery = {
            "id": values["recovery_id"],
            "recovery_request_id": values["recovery_request_id"],
            "runtime_classroom_id": runtime["id"],
            "mode": values["mode"],
            "kind": values["kind"],
            "status": "recovering",
            "dispatch_count": 1,
            "first_dispatch_error_code": None,
            "first_dispatch_error_message_safe": None,
            "first_dispatch_rejected_at": None,
            "source_runtime_status": "failed",
            "source_runtime_error_code": "openmaic_generation_failed",
            "source_runtime_error_message_safe": runtime["error_message_safe"],
            "source_upstream_job_id": values["expected_source_job_id"],
            "source_job_status": "failed",
            "source_job_error": "structured_output_exhausted",
            "source_scenes_generated": values["source_scenes_generated"],
            "source_total_scenes": values["source_total_scenes"],
            "source_completed_at": snapshot["completedAt"],
            "source_job_snapshot_sha256": snapshot["jobSnapshotSha256"],
            "source_generation_contract_sha256": values[
                "source_generation_contract_sha256"
            ],
            "expected_upstream_recovery_id": values[
                "expected_upstream_recovery_id"
            ],
            "upstream_recovery_id": None,
            "policy_id": None,
            "policy_version": None,
            "canonical_spec_sha256": None,
            "code_patch_sha256": None,
            "upstream_classroom_id": None,
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
            "content_sha256": None,
            "final_artifact_sha256": None,
            "artifact_created_at": None,
            "static_contract_verified": False,
            "conversation_probe_verified": False,
            "verified_at": None,
            "error_code": None,
            "error_message_safe": None,
            "receipt_json": None,
            "terminal_at": None,
            "updated_at": values["now"],
        }
        return self.recovery

    def reserve_deterministic_recovery_redispatch(self, _conn, **values):
        self.redispatch_reserve_calls += 1
        runtime = self.rows[values["runtime_id"]]
        recovery = self.recovery
        if not (
            recovery is not None
            and runtime["status"] == "failed"
            and runtime["attempt_ordinal"] == 3
            and runtime["error_code"] == "openmaic_generation_failed"
            and runtime["upstream_job_id"] == values["source_upstream_job_id"]
            and recovery["id"] == values["recovery_id"]
            and recovery["recovery_request_id"] == values["recovery_request_id"]
            and recovery["status"] == "failed"
            and recovery["dispatch_count"] == 1
            and recovery["error_code"]
            == "openmaic_recovery_upstream_rejected"
            and recovery["upstream_recovery_id"] is None
            and recovery["tts_attempted_call_count"] == 0
            and recovery["tts_completed_call_count"] == 0
            and recovery["source_job_snapshot_sha256"]
            == values["source_job_snapshot_sha256"]
            and recovery["source_generation_contract_sha256"]
            == values["source_generation_contract_sha256"]
            and recovery["expected_upstream_recovery_id"]
            == values["expected_upstream_recovery_id"]
        ):
            raise RuntimeError("redispatch CAS conflict")
        recovery.update(
            {
                "dispatch_count": 2,
                "first_dispatch_error_code": recovery["error_code"],
                "first_dispatch_error_message_safe": recovery[
                    "error_message_safe"
                ],
                "first_dispatch_rejected_at": recovery["terminal_at"],
                "status": "recovering",
                "error_code": None,
                "error_message_safe": None,
                "terminal_at": None,
                "updated_at": values["now"],
            }
        )
        runtime["status"] = "recovering"
        if self.simulate_concurrent_redispatch_winner:
            raise RuntimeError("concurrent redispatch winner committed")
        return recovery

    def attach_deterministic_recovery_receipt(self, _conn, **values):
        if self.recovery["upstream_recovery_id"] is not None:
            return False
        if (
            values["upstream_recovery_id"]
            != self.recovery["expected_upstream_recovery_id"]
        ):
            return False
        self.recovery.update(
            {
                "upstream_recovery_id": values["upstream_recovery_id"],
                "policy_id": values["policy"]["marker"],
                "policy_version": values["policy"]["version"],
                "canonical_spec_sha256": values["policy"]["canonicalSpecSha256"],
                "code_patch_sha256": values["policy"]["patchSha256"],
                "tts_attempted_call_count": values["calls"]["tts"][
                    "attempted"
                ],
                "tts_completed_call_count": values["calls"]["tts"]["completed"],
                "receipt_json": deepcopy(values["receipt"]),
                "updated_at": values["now"],
            }
        )
        return True

    def update_deterministic_recovery_observation(self, _conn, **values):
        if (
            self.recovery["tts_attempted_call_count"]
            > values["tts_attempted_count"]
            or self.recovery["tts_completed_call_count"]
            > values["tts_completed_count"]
        ):
            return False
        self.recovery["tts_attempted_call_count"] = values[
            "tts_attempted_count"
        ]
        self.recovery["tts_completed_call_count"] = values["tts_completed_count"]
        self.recovery["receipt_json"] = deepcopy(values["receipt"])
        if values["progressed"]:
            self.recovery["updated_at"] = values["now"]
        return True

    def claim_deterministic_recovery_validation(self, _conn, **values):
        if self.recovery["status"] != "recovering":
            return False
        artifact = values["artifact"]
        self.recovery.update(
            {
                "status": "validating",
                "upstream_classroom_id": artifact["classroomId"],
                "scene_count": artifact["sceneCount"],
                "tts_attempted_call_count": values["tts_attempted_count"],
                "tts_completed_call_count": values["tts_completed_count"],
                "receipt_json": deepcopy(values["receipt"]),
                "updated_at": values["now"],
            }
        )
        return True

    def fail_deterministic_recovery(self, _conn, **values):
        if self.recovery["status"] not in {"recovering", "validating"}:
            return False
        self.recovery.update(
            {
                "status": "failed",
                "error_code": values["error_code"],
                "error_message_safe": values["error_message_safe"],
                "tts_attempted_call_count": (
                    values["tts_attempted_count"]
                    if values["tts_attempted_count"] is not None
                    else self.recovery["tts_attempted_call_count"]
                ),
                "tts_completed_call_count": (
                    values["tts_completed_count"]
                    if values["tts_completed_count"] is not None
                    else self.recovery["tts_completed_call_count"]
                ),
                "updated_at": values["now"],
                "terminal_at": values["now"],
            }
        )
        runtime = self.rows[values["runtime_id"]]
        runtime["status"] = "failed"
        return True

    def fail_stale_deterministic_recovery(self, _conn, **values):
        if not (
            self.recovery["status"] == values["expected_status"]
            and self.recovery["updated_at"] == values["expected_updated_at"]
            and self.recovery["tts_attempted_call_count"]
            == values["expected_tts_attempted_count"]
            and self.recovery["tts_completed_call_count"]
            == values["expected_tts_completed_count"]
        ):
            return False
        self.recovery.update(
            {
                "status": "failed",
                "error_code": values["error_code"],
                "updated_at": values["now"],
            }
        )
        self.rows[values["runtime_id"]]["status"] = "failed"
        return True

    def mark_ready_from_deterministic_recovery(self, _conn, **values):
        assert self.recovery["status"] == "validating"
        runtime = self.rows[values["runtime_id"]]
        assert runtime["upstream_job_id"] == values["source_upstream_job_id"]
        self.ready_calls += 1
        self.recovery.update(
            {
                "status": "succeeded",
                "static_contract_verified": True,
                "conversation_probe_verified": True,
                "updated_at": values["now"],
            }
        )
        runtime.update(
            {
                "status": "ready",
                "upstream_classroom_id": values["upstream_classroom_id"],
                "feature_manifest_json": values["feature_manifest"],
                "error_code": None,
                "error_message_safe": None,
                "ready_at": values["now"],
            }
        )

    def get_conversation_probe_by_runtime_classroom_for_update(
        self, _conn, *, runtime_classroom_id
    ):
        return None

    def create_conversation_probe(self, _conn, **values):
        self.created_probe = values


def _service(*, recovery_status="running", corrupt_classroom=False, probe_fail=False):
    service = object.__new__(OpenMaicFullRuntimeService)
    service.enabled = True
    service.generation_enabled = False
    service.deterministic_recovery_enabled = True
    service.deterministic_recovery_redispatch_enabled = True
    service.public_url = "http://127.0.0.1:3101"
    service.video_export_enabled = False
    service.launch_ttl_seconds = 60
    service.session_ttl_seconds = 14400
    course = _sample_course()
    contract = _sample_contract(service)
    manifest = service._requested_manifest(
        SAMPLE_REQUIRED_FEATURES,
        SAMPLE_REQUIRED_FEATURES,
        generation_contract=contract,
    )
    base = {
        "course_id": course["course_id"],
        "course_version": course["course_version"],
        "package_id": course["package_id"],
        "package_version": course["package_version"],
        "quality_status": "pending_review",
        "upstream_classroom_id": None,
        "error_message_safe": None,
        "ready_at": None,
        "created_at": 1,
        "updated_at": 2,
    }
    attempt_one = {
        **base,
        "id": "runtime-attempt-1",
        "request_id": "request-1",
        "attempt_ordinal": 1,
        "retry_of_runtime_id": None,
        "retry_reason": None,
        "expected_previous_job_id": None,
        "status": "failed",
        "upstream_job_id": "job-attempt-1",
        "error_code": "openmaic_sample_generation_stale",
        "retired_at": 10,
        "feature_manifest_json": {},
    }
    attempt_two = {
        **base,
        "id": "runtime-attempt-2",
        "request_id": "request-2",
        "attempt_ordinal": 2,
        "retry_of_runtime_id": "runtime-attempt-1",
        "retry_reason": "approved_stage2_retry",
        "expected_previous_job_id": "job-attempt-1",
        "status": "failed",
        "upstream_job_id": "job-attempt-2",
        "error_code": "openmaic_generation_process_restarted",
        "retired_at": 20,
        "feature_manifest_json": {},
    }
    attempt_three = {
        **base,
        "id": "runtime-attempt-3",
        "request_id": "request-3",
        "attempt_ordinal": 3,
        "retry_of_runtime_id": "runtime-attempt-2",
        "retry_reason": "approved_stage2_retry_3",
        "expected_previous_job_id": "job-attempt-2",
        "status": "failed",
        "upstream_job_id": "job-attempt-3",
        "error_code": "openmaic_generation_failed",
        "error_message_safe": "OpenMAIC generation failed",
        "retired_at": None,
        "feature_manifest_json": manifest,
    }
    repository = _RecoveryRepository([attempt_one, attempt_two, attempt_three])
    service.repository = repository
    classroom = _recovery_classroom()
    if corrupt_classroom:
        classroom["scenes"] = classroom["scenes"][:-1]
    classroom_client = _ClassroomClient(classroom)
    recovery_client = _RecoveryClient(recovery_status)
    probe_service = _ProbeService()
    probe_client = _ProbeClient(fail=probe_fail)
    service.client = classroom_client
    service.deterministic_recovery_client = recovery_client
    service.conversation_probe_service = probe_service
    service.conversation_probe_client = probe_client
    return (
        service,
        repository,
        classroom_client,
        recovery_client,
        probe_service,
    )


def _request():
    return {
        "expectedSourceJobId": "job-attempt-3",
        "recoveryRequestId": "approved-deterministic-recovery-1",
        "mode": RECOVERY_MODE,
    }


def _prepare_first_dispatch_rejection(service, recovery_client):
    recovery_client.start_error = OpenMaicDeterministicRecoveryError(
        "openmaic_recovery_upstream_rejected",
        "runtime rejected forwarded authentication before claim",
        status_code=403,
    )
    try:
        service.recover_classroom("runtime-attempt-3", _request())
    except OpenMaicRuntimeServiceError as exc:
        if exc.code != "openmaic_recovery_upstream_rejected":
            raise
    else:
        raise AssertionError("the first dispatch must be explicitly rejected")
    finally:
        recovery_client.start_error = None


class OpenMaicDeterministicRecoveryTest(unittest.TestCase):
    def test_reserves_same_attempt_and_replay_is_zero_external_calls(self):
        service, repository, runtime_client, recovery_client, _probe = _service()

        first = service.recover_classroom("runtime-attempt-3", _request())
        replay = service.recover_classroom("runtime-attempt-3", _request())

        self.assertEqual(repository.reserve_calls, 1)
        self.assertEqual(recovery_client.policy_calls, 1)
        self.assertEqual(recovery_client.source_calls, 1)
        self.assertEqual(recovery_client.start_calls, 1)
        self.assertEqual(runtime_client.start_calls, 0)
        self.assertEqual(len(repository.rows), 3)
        self.assertEqual(repository.rows["runtime-attempt-3"]["upstream_job_id"], "job-attempt-3")
        self.assertEqual(first["recovery"]["status"], "recovering")
        self.assertTrue(replay["recovery"]["idempotent"])

    def test_wrong_source_is_rejected_before_reservation_or_recovery_post(self):
        service, repository, _runtime, recovery_client, _probe = _service()
        recovery_client.reject_source = True

        with self.assertRaises(OpenMaicRuntimeServiceError) as caught:
            service.recover_classroom("runtime-attempt-3", _request())

        self.assertEqual(caught.exception.code, "openmaic_recovery_source_not_allowed")
        self.assertEqual(repository.reserve_calls, 0)
        self.assertEqual(recovery_client.start_calls, 0)
        self.assertEqual(repository.rows["runtime-attempt-3"]["status"], "failed")

    def test_internal_body_rejects_any_field_outside_frozen_contract(self):
        service, repository, _runtime, recovery_client, _probe = _service()
        invalid = {**_request(), "retry": True}

        with self.assertRaises(OpenMaicRuntimeServiceError) as caught:
            service.recover_classroom("runtime-attempt-3", invalid)

        self.assertEqual(caught.exception.code, "openmaic_recovery_contract_invalid")
        self.assertEqual(repository.reserve_calls, 0)
        self.assertEqual(recovery_client.policy_calls, 0)
        self.assertEqual(recovery_client.start_calls, 0)

    def test_runtime_policy_mismatch_is_rejected_before_source_or_reservation(self):
        service, repository, _runtime, recovery_client, _probe = _service()
        recovery_client.reject_policy = True

        with self.assertRaises(OpenMaicRuntimeServiceError) as caught:
            service.recover_classroom("runtime-attempt-3", _request())

        self.assertEqual(
            caught.exception.code,
            "openmaic_recovery_runtime_policy_mismatch",
        )
        self.assertEqual(recovery_client.policy_calls, 1)
        self.assertEqual(recovery_client.source_calls, 0)
        self.assertEqual(recovery_client.start_calls, 0)
        self.assertEqual(repository.reserve_calls, 0)

    def test_success_reuses_full_validator_and_recovery_probe_then_pending_review(self):
        service, repository, runtime_client, recovery_client, probe = _service(
            recovery_status="succeeded"
        )

        result = service.recover_classroom("runtime-attempt-3", _request())

        runtime = repository.rows["runtime-attempt-3"]
        self.assertEqual(result["recovery"]["status"], "succeeded")
        self.assertEqual(runtime["status"], "ready")
        self.assertEqual(runtime["quality_status"], "pending_review")
        self.assertEqual(runtime["upstream_job_id"], "job-attempt-3")
        self.assertEqual(runtime_client.start_calls, 0)
        self.assertEqual(recovery_client.start_calls, 1)
        self.assertEqual(probe.issue_calls, 1)
        self.assertEqual(probe.issue_args[2], repository.recovery["id"])
        self.assertTrue(repository.recovery["static_contract_verified"])
        self.assertTrue(repository.recovery["conversation_probe_verified"])

    def test_static_validator_failure_is_terminal_and_preserves_source_error(self):
        service, repository, runtime_client, _recovery, probe = _service(
            recovery_status="succeeded", corrupt_classroom=True
        )

        with self.assertRaises(OpenMaicRuntimeServiceError):
            service.recover_classroom("runtime-attempt-3", _request())

        runtime = repository.rows["runtime-attempt-3"]
        self.assertEqual(repository.recovery["status"], "failed")
        self.assertEqual(runtime["status"], "failed")
        self.assertEqual(runtime["error_code"], "openmaic_generation_failed")
        self.assertEqual(runtime["upstream_job_id"], "job-attempt-3")
        self.assertEqual(runtime_client.start_calls, 0)
        self.assertEqual(probe.issue_calls, 0)

    def test_recovery_rejects_stage_or_audio_not_bound_to_artifact_classroom(self):
        for mutation, expected_code in (
            (
                lambda classroom: classroom["stage"].__setitem__("id", "other-stage"),
                "openmaic_recovery_classroom_identity_mismatch",
            ),
            (
                lambda classroom: classroom["scenes"][0]["actions"][0].__setitem__(
                    "audioUrl",
                    "https://evil.invalid/api/classroom-media/other/audio/audio-1.mp3",
                ),
                "openmaic_recovery_audio_identity_mismatch",
            ),
        ):
            with self.subTest(expected_code=expected_code):
                service, repository, runtime_client, _recovery, probe = _service(
                    recovery_status="succeeded"
                )
                mutation(runtime_client.classroom)

                with self.assertRaises(OpenMaicRuntimeServiceError) as caught:
                    service.recover_classroom("runtime-attempt-3", _request())

                self.assertEqual(caught.exception.code, expected_code)
                self.assertEqual(repository.recovery["status"], "failed")
                self.assertEqual(probe.issue_calls, 0)

    def test_probe_failure_is_terminal_and_cannot_recover_again(self):
        service, repository, runtime_client, recovery_client, probe = _service(
            recovery_status="succeeded", probe_fail=True
        )

        with self.assertRaises(OpenMaicRuntimeServiceError):
            service.recover_classroom("runtime-attempt-3", _request())
        replay = service.recover_classroom("runtime-attempt-3", _request())

        self.assertEqual(repository.recovery["status"], "failed")
        self.assertTrue(replay["recovery"]["idempotent"])
        self.assertEqual(recovery_client.start_calls, 1)
        self.assertEqual(runtime_client.start_calls, 0)
        self.assertEqual(probe.issue_calls, 1)

    def test_partial_tts_failure_receipt_does_not_claim_ten_completed_calls(self):
        service, repository, _runtime, recovery_client, _probe = _service(
            recovery_status="failed"
        )

        result = service.recover_classroom("runtime-attempt-3", _request())

        self.assertEqual(result["recovery"]["status"], "failed")
        self.assertEqual(
            result["recovery"]["calls"]["tts"],
            {"expected": 10, "attempted": 4, "completed": 3},
        )
        self.assertEqual(recovery_client.start_calls, 1)
        self.assertEqual(repository.rows["runtime-attempt-3"]["error_code"], "openmaic_generation_failed")

    def test_queued_can_jump_directly_to_succeeded_without_sticking_recovering(self):
        service, repository, _runtime, recovery_client, probe = _service(
            recovery_status="running"
        )
        service.recover_classroom("runtime-attempt-3", _request())
        recovery_client.status = "succeeded"

        result = service.deterministic_recovery_status("runtime-attempt-3")

        self.assertEqual(result["recovery"]["status"], "succeeded")
        self.assertEqual(result["recovery"]["calls"]["tts"]["completed"], 10)
        self.assertEqual(repository.rows["runtime-attempt-3"]["status"], "ready")
        self.assertEqual(probe.issue_calls, 1)

    def test_lost_post_response_reconciles_by_expected_id_without_reposting(self):
        service, repository, runtime_client, recovery_client, probe = _service(
            recovery_status="succeeded"
        )
        recovery_client.start_error = OpenMaicDeterministicRecoveryError(
            "openmaic_recovery_unavailable",
            "response lost after accept",
            status_code=503,
        )

        with self.assertRaises(OpenMaicRuntimeServiceError) as caught:
            service.recover_classroom("runtime-attempt-3", _request())

        self.assertEqual(caught.exception.code, "openmaic_recovery_dispatch_uncertain")
        self.assertIsNone(repository.recovery["upstream_recovery_id"])
        expected_id, _request_hash = deterministic_recovery_identity(
            "job-attempt-3", "approved-deterministic-recovery-1"
        )
        self.assertEqual(expected_id, "omrec_f54011a1b88892a2ffa3f124")
        self.assertEqual(
            repository.recovery["expected_upstream_recovery_id"], expected_id
        )

        replay = service.recover_classroom("runtime-attempt-3", _request())
        self.assertTrue(replay["recovery"]["idempotent"])
        self.assertEqual(recovery_client.start_calls, 1)
        self.assertEqual(recovery_client.policy_calls, 1)
        self.assertEqual(recovery_client.source_calls, 1)

        result = service.deterministic_recovery_status("runtime-attempt-3")

        self.assertEqual(result["recovery"]["status"], "succeeded")
        self.assertEqual(recovery_client.poll_calls, 1)
        self.assertEqual(recovery_client.start_calls, 1)
        self.assertEqual(runtime_client.start_calls, 0)
        self.assertEqual(repository.rows["runtime-attempt-3"]["status"], "ready")
        self.assertEqual(probe.issue_calls, 1)

    def test_frozen_upstream_observation_stales_terminal_without_reposting(self):
        service, repository, _runtime, recovery_client, _probe = _service(
            recovery_status="running"
        )
        service.recover_classroom("runtime-attempt-3", _request())
        repository.recovery["updated_at"] = 1

        result = service.deterministic_recovery_status("runtime-attempt-3")

        self.assertEqual(result["recovery"]["status"], "failed")
        self.assertEqual(
            result["recovery"]["errorCode"],
            "openmaic_recovery_upstream_stale",
        )
        self.assertEqual(recovery_client.start_calls, 1)
        self.assertEqual(recovery_client.poll_calls, 1)
        self.assertEqual(repository.rows["runtime-attempt-3"]["status"], "failed")

    def test_older_poller_cannot_regress_counts_or_stale_fail_new_progress(self):
        service, repository, _runtime, _recovery_client, _probe = _service(
            recovery_status="running"
        )
        service.recover_classroom("runtime-attempt-3", _request())
        stale_read = deepcopy(repository.recovery)
        stale_read["updated_at"] = 1
        repository.recovery["tts_attempted_call_count"] = 6
        repository.recovery["tts_completed_call_count"] = 5
        repository.recovery["updated_at"] = 9_999_999_999_999

        result = service._handle_deterministic_recovery_result(
            stale_read,
            _upstream_recovery("running"),
            idempotent=True,
        )

        self.assertEqual(result["recovery"]["status"], "recovering")
        self.assertEqual(
            result["recovery"]["calls"]["tts"],
            {"expected": 10, "attempted": 6, "completed": 5},
        )
        self.assertEqual(repository.rows["runtime-attempt-3"]["status"], "recovering")

    def test_unexpected_validator_exception_is_terminal_not_validating_forever(self):
        service, repository, runtime_client, _recovery, _probe = _service(
            recovery_status="succeeded"
        )
        runtime_client.get_classroom = lambda _classroom_id: (_ for _ in ()).throw(
            ValueError("unsafe internal detail")
        )

        with self.assertRaises(OpenMaicRuntimeServiceError) as caught:
            service.recover_classroom("runtime-attempt-3", _request())

        self.assertEqual(caught.exception.code, "openmaic_recovery_validation_failed")
        self.assertEqual(repository.recovery["status"], "failed")
        self.assertEqual(repository.rows["runtime-attempt-3"]["status"], "failed")
        self.assertNotIn("unsafe internal detail", caught.exception.safe_message)

    def test_recovery_probe_uses_dedicated_candidate_binding(self):
        service, repository, _runtime, _recovery, _probe = _service()
        runtime = repository.rows["runtime-attempt-3"]
        runtime["status"] = "recovering"
        repository.recovery = {
            "id": "omdr-dedicated-1",
            "runtime_classroom_id": runtime["id"],
            "status": "validating",
            "upstream_classroom_id": "recovered-classroom-1",
            "source_job_snapshot_sha256": "a" * 64,
        }
        probe_service = OpenMaicConversationProbeService(
            enabled=True, repository=repository
        )

        probe_service.issue_recovery_candidate(
            runtime["id"], "recovered-classroom-1", "omdr-dedicated-1"
        )

        self.assertEqual(repository.created_probe["candidate_kind"], "recovery")
        self.assertEqual(
            repository.created_probe["deterministic_recovery_id"],
            "omdr-dedicated-1",
        )

    def test_recovery_config_requires_generation_and_autorun_off(self):
        common = {
            "runtime_enabled": True,
            "probe_enabled": True,
            "enabled": True,
            "redispatch_enabled": False,
            "internal_url": "http://127.0.0.1:3100",
            "internal_token": "x" * 32,
        }
        for field in ("generation_enabled", "autorun_enabled"):
            values = {**common, "generation_enabled": False, "autorun_enabled": False}
            values[field] = True
            with self.assertRaises(ConfigError):
                _validate_openmaic_deterministic_recovery_config(**values)

        with self.assertRaises(ConfigError):
            _validate_openmaic_deterministic_recovery_config(
                **{
                    **common,
                    "enabled": False,
                    "redispatch_enabled": True,
                    "generation_enabled": False,
                    "autorun_enabled": False,
                }
            )
        _validate_openmaic_deterministic_recovery_config(
            **{
                **common,
                "redispatch_enabled": True,
                "generation_enabled": False,
                "autorun_enabled": False,
            }
        )

    def test_redispatch_success_preserves_first_rejection_and_attempt_three(self):
        service, repository, runtime_client, recovery_client, _probe = _service(
            recovery_status="succeeded"
        )
        _prepare_first_dispatch_rejection(service, recovery_client)
        first_message = repository.recovery["error_message_safe"]
        first_rejected_at = repository.recovery["terminal_at"]

        result = service.redispatch_deterministic_recovery(
            "runtime-attempt-3", _request()
        )

        self.assertEqual(result["recovery"]["status"], "succeeded")
        self.assertEqual(result["recovery"]["dispatchCount"], 2)
        self.assertEqual(repository.recovery["dispatch_count"], 2)
        self.assertEqual(
            repository.recovery["first_dispatch_error_code"],
            "openmaic_recovery_upstream_rejected",
        )
        self.assertEqual(
            repository.recovery["first_dispatch_error_message_safe"],
            first_message,
        )
        self.assertEqual(
            repository.recovery["first_dispatch_rejected_at"],
            first_rejected_at,
        )
        self.assertEqual(recovery_client.start_calls, 2)
        self.assertEqual(recovery_client.absence_calls, 1)
        self.assertEqual(repository.redispatch_reserve_calls, 1)
        self.assertEqual(len(repository.rows), 3)
        self.assertEqual(
            repository.rows["runtime-attempt-3"]["upstream_job_id"],
            "job-attempt-3",
        )
        self.assertEqual(runtime_client.start_calls, 0)

    def test_redispatch_replay_and_concurrent_loser_never_post(self):
        service, repository, _runtime, recovery_client, _probe = _service()
        _prepare_first_dispatch_rejection(service, recovery_client)
        repository.simulate_concurrent_redispatch_winner = True

        loser = service.redispatch_deterministic_recovery(
            "runtime-attempt-3", _request()
        )
        external_after_loser = (
            recovery_client.policy_calls,
            recovery_client.source_calls,
            recovery_client.absence_calls,
            recovery_client.start_calls,
        )
        service.deterministic_recovery_redispatch_enabled = False
        replay = service.redispatch_deterministic_recovery(
            "runtime-attempt-3", _request()
        )

        self.assertEqual(loser["recovery"]["dispatchCount"], 2)
        self.assertTrue(loser["recovery"]["idempotent"])
        self.assertTrue(replay["recovery"]["idempotent"])
        self.assertEqual(
            (
                recovery_client.policy_calls,
                recovery_client.source_calls,
                recovery_client.absence_calls,
                recovery_client.start_calls,
            ),
            external_after_loser,
        )
        self.assertEqual(recovery_client.start_calls, 1)

    def test_redispatch_preflight_drift_or_absence_failure_keeps_first_failure(self):
        cases = ("policy", "source", "absence")
        for case in cases:
            with self.subTest(case=case):
                service, repository, _runtime, recovery_client, _probe = _service()
                _prepare_first_dispatch_rejection(service, recovery_client)
                if case == "policy":
                    recovery_client.reject_policy = True
                elif case == "source":
                    recovery_client.source_snapshot = OpenMaicRecoverySourceSnapshot(
                        job_id="job-attempt-3",
                        completed_at="2026-08-18T03:15:01.000Z",
                        job_snapshot_sha256="d" * 64,
                    )
                else:
                    recovery_client.absence_error = (
                        OpenMaicDeterministicRecoveryError(
                            "openmaic_recovery_absence_not_proven",
                            "fixed absence receipt was not returned",
                            status_code=409,
                        )
                    )

                with self.assertRaises(OpenMaicRuntimeServiceError):
                    service.redispatch_deterministic_recovery(
                        "runtime-attempt-3", _request()
                    )

                self.assertEqual(repository.recovery["dispatch_count"], 1)
                self.assertEqual(repository.recovery["status"], "failed")
                self.assertEqual(repository.redispatch_reserve_calls, 0)
                self.assertEqual(recovery_client.start_calls, 1)

    def test_redispatch_timeout_reconciles_without_a_third_post(self):
        service, repository, runtime_client, recovery_client, _probe = _service(
            recovery_status="succeeded"
        )
        _prepare_first_dispatch_rejection(service, recovery_client)
        recovery_client.start_error = OpenMaicDeterministicRecoveryError(
            "openmaic_recovery_unavailable",
            "response lost after second dispatch",
            status_code=503,
        )

        with self.assertRaises(OpenMaicRuntimeServiceError) as caught:
            service.redispatch_deterministic_recovery(
                "runtime-attempt-3", _request()
            )
        self.assertEqual(caught.exception.code, "openmaic_recovery_dispatch_uncertain")
        self.assertEqual(repository.recovery["dispatch_count"], 2)
        self.assertEqual(repository.recovery["status"], "recovering")
        self.assertIsNone(repository.recovery["upstream_recovery_id"])
        recovery_client.start_error = None

        result = service.deterministic_recovery_status("runtime-attempt-3")
        replay = service.redispatch_deterministic_recovery(
            "runtime-attempt-3", _request()
        )

        self.assertEqual(result["recovery"]["status"], "succeeded")
        self.assertTrue(replay["recovery"]["idempotent"])
        self.assertEqual(recovery_client.start_calls, 2)
        self.assertEqual(recovery_client.poll_calls, 1)
        self.assertEqual(runtime_client.start_calls, 0)

    def test_second_explicit_rejection_is_terminal_and_never_third_dispatch(self):
        service, repository, _runtime, recovery_client, _probe = _service()
        _prepare_first_dispatch_rejection(service, recovery_client)
        recovery_client.start_error = OpenMaicDeterministicRecoveryError(
            "openmaic_recovery_upstream_rejected",
            "second explicit pre-claim rejection",
            status_code=403,
        )

        with self.assertRaises(OpenMaicRuntimeServiceError):
            service.redispatch_deterministic_recovery(
                "runtime-attempt-3", _request()
            )
        recovery_client.start_error = None
        replay = service.redispatch_deterministic_recovery(
            "runtime-attempt-3", _request()
        )

        self.assertEqual(repository.recovery["dispatch_count"], 2)
        self.assertEqual(repository.recovery["status"], "failed")
        self.assertEqual(
            repository.recovery["first_dispatch_error_code"],
            "openmaic_recovery_upstream_rejected",
        )
        self.assertTrue(replay["recovery"]["idempotent"])
        self.assertEqual(recovery_client.start_calls, 2)

    def test_redispatch_and_normal_recovery_gates_fail_closed(self):
        service, repository, _runtime, recovery_client, _probe = _service()
        _prepare_first_dispatch_rejection(service, recovery_client)
        service.deterministic_recovery_redispatch_enabled = False

        with self.assertRaises(OpenMaicRuntimeServiceError) as redispatch_error:
            service.redispatch_deterministic_recovery(
                "runtime-attempt-3", _request()
            )
        self.assertEqual(
            redispatch_error.exception.code,
            "openmaic_recovery_redispatch_disabled",
        )
        self.assertEqual(recovery_client.absence_calls, 0)
        self.assertEqual(repository.redispatch_reserve_calls, 0)

        fresh, fresh_repository, _runtime, fresh_client, _probe = _service()
        fresh.deterministic_recovery_enabled = False
        with self.assertRaises(OpenMaicRuntimeServiceError) as recovery_error:
            fresh.recover_classroom("runtime-attempt-3", _request())
        self.assertEqual(
            recovery_error.exception.code,
            "openmaic_deterministic_recovery_disabled",
        )
        self.assertEqual(fresh_client.start_calls, 0)
        self.assertEqual(fresh_repository.reserve_calls, 0)


class OpenMaicDeterministicRecoveryClientContractTest(unittest.TestCase):
    def test_redispatch_absence_requires_authenticated_exact_404(self):
        client = OpenMaicDeterministicRecoveryClient(
            "http://127.0.0.1:3100",
            internal_token="s" * 32,
            expected_canonical_spec_sha256="b" * 64,
            expected_patch_sha256="c" * 64,
        )
        expected_id, _request_hash = deterministic_recovery_identity(
            "job-attempt-3", "approved-deterministic-recovery-1"
        )

        class _ErrorOpener:
            def __init__(self, status, payload):
                self.status = status
                self.payload = payload
                self.requests = []

            def open(self, request, **_kwargs):
                self.requests.append(request)
                raise HTTPError(
                    request.full_url,
                    self.status,
                    "controlled test response",
                    {},
                    io.BytesIO(json.dumps(self.payload).encode("utf-8")),
                )

        exact = {
            "success": False,
            "errorCode": "INVALID_REQUEST",
            "error": "Deterministic recovery not found",
        }
        opener = _ErrorOpener(404, exact)
        client._opener = opener
        result = client.assert_recovery_absent(
            source_job_id="job-attempt-3",
            expected_recovery_id=expected_id,
            recovery_request_id="approved-deterministic-recovery-1",
        )

        self.assertTrue(result["absent"])
        headers = {
            key.casefold(): value
            for key, value in opener.requests[0].header_items()
        }
        self.assertEqual(headers["x-mira-internal-token"], "s" * 32)

        for status, payload in (
            (403, exact),
            (404, {**exact, "details": "not an exact absence receipt"}),
            (404, {**exact, "error": "some other not-found response"}),
            (302, exact),
        ):
            with self.subTest(status=status, payload=payload):
                client._opener = _ErrorOpener(status, payload)
                with self.assertRaises(OpenMaicDeterministicRecoveryError):
                    client.assert_recovery_absent(
                        source_job_id="job-attempt-3",
                        expected_recovery_id=expected_id,
                        recovery_request_id=(
                            "approved-deterministic-recovery-1"
                        ),
                    )

        class _SuccessResponse:
            def __init__(self, request):
                self.request = request

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return self.request.full_url

            def read(self, _limit):
                return b'{"success":true}'

        class _SuccessOpener:
            @staticmethod
            def open(request, **_kwargs):
                return _SuccessResponse(request)

        client._opener = _SuccessOpener()
        with self.assertRaises(OpenMaicDeterministicRecoveryError) as existing:
            client.assert_recovery_absent(
                source_job_id="job-attempt-3",
                expected_recovery_id=expected_id,
                recovery_request_id="approved-deterministic-recovery-1",
            )
        self.assertEqual(existing.exception.code, "openmaic_recovery_already_claimed")

        class _RawErrorOpener:
            def __init__(self, *, url, raw):
                self.url = url
                self.raw = raw

            def open(self, _request, **_kwargs):
                raise HTTPError(
                    self.url,
                    404,
                    "controlled test response",
                    {},
                    io.BytesIO(self.raw),
                )

        client._opener = _RawErrorOpener(
            url="http://127.0.0.1:3100/api/generate-classroom/job-attempt-3/"
            "deterministic-recovery",
            raw=b"x" * (client.MAX_JSON_BYTES + 1),
        )
        with self.assertRaises(OpenMaicDeterministicRecoveryError) as oversized:
            client.assert_recovery_absent(
                source_job_id="job-attempt-3",
                expected_recovery_id=expected_id,
                recovery_request_id="approved-deterministic-recovery-1",
            )
        self.assertEqual(
            oversized.exception.code, "openmaic_recovery_absence_not_proven"
        )

        client._opener = _RawErrorOpener(
            url="http://evil.invalid/deterministic-recovery",
            raw=json.dumps(exact).encode("utf-8"),
        )
        with self.assertRaises(OpenMaicDeterministicRecoveryError) as redirected:
            client.assert_recovery_absent(
                source_job_id="job-attempt-3",
                expected_recovery_id=expected_id,
                recovery_request_id="approved-deterministic-recovery-1",
            )
        self.assertEqual(
            redirected.exception.code, "openmaic_recovery_redirect_not_allowed"
        )

        class _TimeoutOpener:
            @staticmethod
            def open(_request, **_kwargs):
                raise TimeoutError("controlled timeout")

        client._opener = _TimeoutOpener()
        with self.assertRaises(OpenMaicDeterministicRecoveryError) as timeout:
            client.assert_recovery_absent(
                source_job_id="job-attempt-3",
                expected_recovery_id=expected_id,
                recovery_request_id="approved-deterministic-recovery-1",
            )
        self.assertEqual(
            timeout.exception.code, "openmaic_recovery_absence_not_proven"
        )

    def test_health_preflight_requires_exact_enabled_source_and_pinned_policy(self):
        client = _parser_client()
        payload = {
            "success": True,
            "runtimePolicy": {
                "deterministicRecovery": {
                    "enabled": True,
                    "sourceJobId": "job-attempt-3",
                    "policyVersion": "mira-sample-deterministic-classroom.v1",
                    "canonicalSpecSha256": "b" * 64,
                    "patchSha256": "c" * 64,
                }
            },
        }
        client._request_json = lambda *_args, **_kwargs: deepcopy(payload)

        verified = client.verify_runtime_policy(source_job_id="job-attempt-3")
        self.assertTrue(verified["enabled"])

        payload["runtimePolicy"]["deterministicRecovery"]["enabled"] = False
        with self.assertRaises(OpenMaicDeterministicRecoveryError):
            client.verify_runtime_policy(source_job_id="job-attempt-3")

    def test_authenticated_source_snapshot_is_frozen_before_exact_recovery_post(self):
        source_payload = {
            "success": True,
            "jobId": "job-attempt-3",
            "status": "failed",
            "error": "structured_output_exhausted",
            "scenesGenerated": 4,
            "totalScenes": 10,
            "done": True,
            "completedAt": "2026-08-18T03:15:00.000Z",
        }
        running = _upstream_recovery("running")
        recovery_payload = {"success": True, **running.audit_receipt()}

        class _Response:
            def __init__(self, request, payload):
                self.request = request
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def geturl(self):
                return self.request.full_url

            def read(self, _limit):
                return json.dumps(self.payload).encode("utf-8")

        class _Opener:
            def __init__(self):
                self.requests = []

            def open(self, request, **_kwargs):
                self.requests.append(request)
                payload = source_payload if len(self.requests) == 1 else recovery_payload
                return _Response(request, payload)

        client = OpenMaicDeterministicRecoveryClient(
            "http://127.0.0.1:3100",
            internal_token="s" * 32,
            expected_canonical_spec_sha256="b" * 64,
            expected_patch_sha256="c" * 64,
        )
        opener = _Opener()
        client._opener = opener

        snapshot = client.get_source_snapshot(source_job_id="job-attempt-3")
        self.assertEqual(
            snapshot.job_snapshot_sha256,
            "0f6f4406f3c64b38332e4749122783124e05be9d925e3505956bc6d37dec4256",
        )
        recovery_payload["source"] = snapshot.to_audit_source()
        client.start_recovery(
            source_job_id="job-attempt-3",
            recovery_request_id="approved-deterministic-recovery-1",
            expected_source_snapshot=snapshot,
        )

        self.assertEqual(len(opener.requests), 2)
        self.assertEqual(opener.requests[0].method, "GET")
        self.assertEqual(opener.requests[1].method, "POST")
        headers = {key.casefold(): value for key, value in opener.requests[1].header_items()}
        self.assertEqual(headers["x-mira-internal-token"], "s" * 32)
        self.assertEqual(
            json.loads(opener.requests[1].data.decode("utf-8")),
            {
                "recoveryRequestId": "approved-deterministic-recovery-1",
                "expectedSource": {
                    "status": "failed",
                    "error": "structured_output_exhausted",
                    "scenesGenerated": 4,
                    "totalScenes": 10,
                },
            },
        )

    def test_failed_record_accepts_only_safe_error_object_and_partial_tts(self):
        client = _parser_client()
        record = _upstream_recovery("failed")
        payload = {"success": True, **record.audit_receipt()}

        parsed = client._recovery_from_payload(
            payload,
            expected_source_snapshot=_source_snapshot(),
            expected_recovery_id=record.recovery_id,
        )

        self.assertEqual(parsed.error["code"], "deterministic_recovery_failed")
        self.assertEqual(parsed.calls["tts"]["attempted"], 4)
        self.assertEqual(parsed.calls["tts"]["completed"], 3)

        payload["error"] = "unsafe unstructured error"
        with self.assertRaises(OpenMaicDeterministicRecoveryError):
            client._recovery_from_payload(
                payload,
                expected_source_snapshot=_source_snapshot(),
                expected_recovery_id=record.recovery_id,
            )


class OpenMaicDeterministicRecoveryFactoryTest(unittest.TestCase):
    def test_factory_pins_attestation_hashes_into_recovery_client(self):
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
            INTERNAL_API_TOKEN="i" * 32,
        )
        captured = {}

        class _RecoveryFactoryClient:
            def __init__(self, _url, **kwargs):
                captured.update(kwargs)

        class _RuntimeService:
            def __init__(self, _database_url, **kwargs):
                self.deterministic_recovery_client = kwargs[
                    "deterministic_recovery_client"
                ]

        with app.app_context(), patch.object(
            service_factory,
            "OpenMaicDeterministicRecoveryClient",
            _RecoveryFactoryClient,
        ), patch.object(
            service_factory, "OpenMaicFullRuntimeService", _RuntimeService
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
            captured["expected_canonical_spec_sha256"],
            RECOVERY_CANONICAL_SPEC_SHA256,
        )
        self.assertEqual(
            captured["expected_patch_sha256"], RECOVERY_PATCH_SHA256
        )
        self.assertEqual(captured["internal_token"], "i" * 32)


class OpenMaicDeterministicRecoveryRepositorySqlTest(unittest.TestCase):
    def test_recovery_repository_sql_parameter_contracts_are_complete(self):
        class _Cursor:
            rowcount = 1

            def __init__(self, row=None):
                self.row = row

            def fetchone(self):
                return self.row

        class _Connection:
            def __init__(self):
                self.statements = []
                self.row = {"id": "local-recovery-1"}

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
        snapshot = _source_snapshot().to_audit_source()
        source = {
            "id": "runtime-attempt-3",
            "status": "failed",
            "error_code": "openmaic_generation_failed",
            "error_message_safe": "source failure",
        }
        upstream = _upstream_recovery("running")
        repository.reserve_deterministic_recovery(
            conn,
            recovery_id="local-recovery-1",
            recovery_request_id="approved-deterministic-recovery-1",
            runtime=source,
            expected_source_job_id="job-attempt-3",
            expected_upstream_recovery_id=upstream.recovery_id,
            source_job_snapshot=snapshot,
            source_generation_contract_sha256="f" * 64,
            mode=RECOVERY_MODE,
            kind=RECOVERY_KIND,
            source_scenes_generated=4,
            source_total_scenes=10,
            tts_provider_id="qwen-tts",
            tts_model_id="qwen3-tts-flash",
            tts_voice_id="Serena",
            now=100,
        )
        repository.reserve_deterministic_recovery_redispatch(
            conn,
            recovery_id="local-recovery-1",
            runtime_id="runtime-attempt-3",
            recovery_request_id="approved-deterministic-recovery-1",
            source_upstream_job_id="job-attempt-3",
            expected_upstream_recovery_id=upstream.recovery_id,
            source_job_snapshot_sha256="a" * 64,
            source_generation_contract_sha256="f" * 64,
            now=100,
        )
        repository.attach_deterministic_recovery_receipt(
            conn,
            recovery_id="local-recovery-1",
            upstream_recovery_id=upstream.recovery_id,
            source=upstream.source,
            policy=upstream.policy,
            calls=upstream.calls,
            receipt=upstream.audit_receipt(),
            now=101,
        )
        repository.update_deterministic_recovery_observation(
            conn,
            recovery_id="local-recovery-1",
            receipt=upstream.audit_receipt(),
            tts_attempted_count=0,
            tts_completed_count=0,
            progressed=False,
            now=102,
        )
        succeeded = _upstream_recovery("succeeded")
        repository.claim_deterministic_recovery_validation(
            conn,
            recovery_id="local-recovery-1",
            artifact=succeeded.artifact,
            tts_attempted_count=10,
            tts_completed_count=10,
            receipt=succeeded.audit_receipt(),
            now=103,
        )
        repository.fail_stale_deterministic_recovery(
            conn,
            recovery_id="local-recovery-1",
            runtime_id="runtime-attempt-3",
            expected_status="recovering",
            expected_updated_at=102,
            expected_tts_attempted_count=0,
            expected_tts_completed_count=0,
            error_code="openmaic_recovery_upstream_stale",
            error_message_safe="stale",
            receipt=upstream.audit_receipt(),
            now=104,
        )
        repository.fail_deterministic_recovery(
            conn,
            recovery_id="local-recovery-1",
            runtime_id="runtime-attempt-3",
            error_code="openmaic_deterministic_recovery_failed",
            error_message_safe="failed",
            receipt=upstream.audit_receipt(),
            tts_attempted_count=0,
            tts_completed_count=0,
            now=105,
        )
        repository.mark_ready_from_deterministic_recovery(
            conn,
            recovery_id="local-recovery-1",
            runtime_id="runtime-attempt-3",
            source_upstream_job_id="job-attempt-3",
            upstream_classroom_id="recovered-classroom-1",
            feature_manifest={"verified": True},
            receipt=succeeded.audit_receipt(),
            now=106,
        )

        self.assertGreaterEqual(len(conn.statements), 12)


class OpenMaicDeterministicRecoveryRouteTest(unittest.TestCase):
    def test_internal_recovery_post_and_independent_status_get(self):
        app = Flask(__name__)
        app.register_blueprint(
            recovery_routes.internal_openmaic_runtime_bp,
            url_prefix="/internal/learning/openmaic",
        )

        class _Service:
            def __init__(self):
                self.post = None
                self.redispatch = None

            def recover_classroom(self, runtime_id, data):
                self.post = (runtime_id, data)
                return {"ok": True, "recovery": {"status": "recovering"}}

            def deterministic_recovery_status(self, runtime_id):
                return {
                    "ok": True,
                    "recovery": {"runtimeId": runtime_id, "status": "recovering"},
                }

            def redispatch_deterministic_recovery(self, runtime_id, data):
                self.redispatch = (runtime_id, data)
                return {
                    "ok": True,
                    "recovery": {"status": "recovering", "dispatchCount": 2},
                }

        class _Guard:
            @staticmethod
            def authorize(**_kwargs):
                return {"authorized": True}

        service = _Service()
        with patch.object(
            recovery_routes,
            "openmaic_full_runtime_service",
            return_value=service,
        ), patch.object(
            recovery_routes,
            "internal_request_guard",
            return_value=_Guard(),
        ):
            client = app.test_client()
            posted = client.post(
                "/internal/learning/openmaic/classrooms/runtime-attempt-3/recover",
                json=_request(),
            )
            polled = client.get(
                "/internal/learning/openmaic/classrooms/runtime-attempt-3/recovery"
            )
            redispatched = client.post(
                "/internal/learning/openmaic/classrooms/"
                "runtime-attempt-3/recovery/redispatch",
                json=_request(),
            )

        self.assertEqual(posted.status_code, 200)
        self.assertEqual(polled.status_code, 200)
        self.assertEqual(redispatched.status_code, 200)
        self.assertEqual(service.post, ("runtime-attempt-3", _request()))
        self.assertEqual(service.redispatch, ("runtime-attempt-3", _request()))
        self.assertEqual(redispatched.json["recovery"]["dispatchCount"], 2)
        self.assertEqual(polled.json["recovery"]["runtimeId"], "runtime-attempt-3")

    def test_succeeded_record_requires_qwen_no_fallback(self):
        client = _parser_client()
        record = _upstream_recovery("succeeded")
        payload = {"success": True, **record.audit_receipt()}
        payload["artifact"]["tts"]["fallbackUsed"] = True

        with self.assertRaises(OpenMaicDeterministicRecoveryError):
            client._recovery_from_payload(
                payload,
                expected_source_snapshot=_source_snapshot(),
                expected_recovery_id=record.recovery_id,
            )


if __name__ == "__main__":
    unittest.main()
