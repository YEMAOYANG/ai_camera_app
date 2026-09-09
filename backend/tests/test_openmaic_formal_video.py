from __future__ import annotations

from copy import deepcopy
import json
import re
import sqlite3
import unittest
from unittest.mock import Mock

from integrations.openmaic_formal_media import (
    LEGACY_PROFESSIONAL_POLICY, IMAGE_PROFESSIONAL_POLICY, INTEGRATED_PROFESSIONAL_POLICY,
    PROFESSIONAL_POLICY, VIDEO_PROFESSIONAL_POLICY, canonical_sha256, generation_options,
    professional_policy, validate_media_manifest,
)
from integrations.openmaic_formal_video import (
    FORMAL_VIDEO_POLICY, professional_video_fields, video_receipt, video_evidence,
    classroom_video_references, validate_classroom_video,
)
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from repositories.formal_student_runtime_gate import _formal_video_sql, current_formal_runtime_sql
from repositories.learning_catalog_repository import LearningCatalogRepository, LearningCatalogActivationError
from services.openmaic_full_runtime_service import OpenMaicRuntimeServiceError
from tests.test_openmaic_formal_quality import adaptive_quality_fixture
from tests.test_formal_student_runtime_launch import _with_receipt_sha256 as _sign_receipt
from tests import test_formal_student_runtime_launch as launch_fixtures
from tests.test_formal_runtime_candidate_generation import _candidate_service, FINGERPRINT


def _with_receipt_sha256(value):
    unsigned = deepcopy(value)
    unsigned.pop("receiptSha256", None)
    return _sign_receipt(unsigned)


def _video(professional, assets=None):
    items = deepcopy(assets or [])
    return _with_receipt_sha256({
        "schemaVersion": "mira.openmaic.formal-video-receipt.v1", "status": "succeeded",
        **{key: professional[key] for key in ("runtimeRequestId", "buildItemId", "classroomId", "sessionId")},
        **{key: FORMAL_VIDEO_POLICY[key] for key in ("policyId", "providerId", "modelId")},
        "videoCount": len(items), "assets": items,
    })


def video_fixture():
    row, classroom = adaptive_quality_fixture()
    manifest = row["feature_manifest_json"]
    manifest["generationContract"].update(professionalCreationPolicy=deepcopy(VIDEO_PROFESSIONAL_POLICY),
                                         generation=generation_options(VIDEO_PROFESSIONAL_POLICY))
    professional = manifest["professionalCreation"]
    professional.update(videoGenerationEnabled=True, videoPolicyId=FORMAL_VIDEO_POLICY["policyId"])
    professional = manifest["professionalCreation"] = _with_receipt_sha256(professional)
    manifest["formalEvidence"]["professionalCreation"].update(
        **professional_video_fields(professional), receiptSha256=professional["receiptSha256"])
    manifest["video"] = _video(professional)
    manifest["formalEvidence"]["video"] = video_evidence(manifest["video"])
    return row, classroom


def _asset():
    digest = "a" * 64
    return {"src": f"/api/classroom-media/classroom-1/media/generated-{digest}.mp4",
            "sha256": digest, "mimeType": "video/mp4", "byteSize": 200_000,
            "width": 1280, "height": 720, "durationMs": 5000, "sceneIds": ["scene-1"]}


class OpenMaicFormalVideoTest(unittest.TestCase):
    def test_exact_default_policy_preserves_all_four_historical_options(self):
        self.assertEqual(OpenMaicFullRuntimeClient.FORMAL_PROFESSIONAL_CREATION_POLICY, VIDEO_PROFESSIONAL_POLICY)
        self.assertEqual(OpenMaicFullRuntimeClient.FORMAL_GENERATION_POLICY["professionalCreation"]["video"], FORMAL_VIDEO_POLICY)
        self.assertIn("scene-actions", OpenMaicFullRuntimeClient.SAMPLE_STRUCTURED_SCENE_POLICY["stages"])
        for policy in (LEGACY_PROFESSIONAL_POLICY, IMAGE_PROFESSIONAL_POLICY, INTEGRATED_PROFESSIONAL_POLICY, PROFESSIONAL_POLICY):
            self.assertEqual(professional_policy(policy), policy)
            self.assertIs(generation_options(policy)["enableVideoGeneration"], False)
        self.assertIs(generation_options(VIDEO_PROFESSIONAL_POLICY)["enableVideoGeneration"], True)
        invalid = deepcopy(VIDEO_PROFESSIONAL_POLICY)
        invalid["video"]["maxCalls"] = True
        with self.assertRaises(ValueError):
            professional_policy(invalid)

    def test_dispatch_and_reentry_use_each_frozen_policy_and_input_hash_without_retry(self):
        for policy in (PROFESSIONAL_POLICY, VIDEO_PROFESSIONAL_POLICY):
            with self.subTest(video="video" in policy):
                service = _candidate_service()
                service.repository.professional_policy = deepcopy(policy)
                kwargs = dict(build_item_id="build-item-1", course_id="candidate-course-1",
                    course_version="course-version-1", package_id="package-1", package_version=1,
                    target_fingerprint=FINGERPRINT, runtime_request_id="formal-runtime-request-1")
                service.issue_candidate_generation(**kwargs)
                dispatched = service.client.start_calls[0]
                self.assertEqual(dispatched["professional_creation_policy"], policy)
                self.assertIs(dispatched["enable_video_generation"], "video" in policy)
                contract = json.loads(dispatched["requirement"])
                self.assertEqual(contract["generation"], generation_options(policy))
                self.assertEqual(service._formal_input_sha256(runtime_request_id=dispatched["runtime_request_id"],
                    generation_contract=contract, formal_contract=dispatched["formal_runtime_contract"]),
                    service.client.jobs[dispatched["runtime_request_id"]].formal_input_sha256)
                service.issue_candidate_generation(**kwargs)
                self.assertEqual(len(service.client.start_calls), 1)

    def test_real_client_builds_exact_video_input_and_rejects_mixed_flags_before_transport(self):
        client = OpenMaicFullRuntimeClient("http://127.0.0.1:3100", formal_audio_internal_token="t" * 48)
        def response(_method, _path, body, **_kwargs):
            return {"jobId": "job-1", "status": "running", "step": "generating_scenes", "progress": 20,
                "runtimeRequestId": body["runtimeRequestId"], "formalContractVersion": client.FORMAL_RUNTIME_CONTRACT_VERSION,
                "formalInputSha256": client.formal_input_sha256(body)}
        client._request_json = Mock(side_effect=response)
        options = dict(requirement="offline", enable_web_search=True, enable_image_generation=True,
            enable_tts=False, agent_mode="generate", runtime_request_id="request-1",
            formal_runtime_contract=client.FORMAL_RUNTIME_CLASSROOM_CONTRACT)
        for policy in (PROFESSIONAL_POLICY, VIDEO_PROFESSIONAL_POLICY):
            client.start_generation(**options, enable_video_generation="video" in policy, professional_creation_policy=policy)
            body = client._request_json.call_args.args[2]
            self.assertEqual(body["professionalCreationPolicy"], policy)
            self.assertIs(body["enableVideoGeneration"], "video" in policy)
            with self.assertRaises(OpenMaicFullRuntimeError):
                client.start_generation(**options, enable_video_generation="video" not in policy, professional_creation_policy=policy)
        self.assertEqual(client._request_json.call_count, 2)

    def test_health_requires_the_exact_bounded_video_contract(self):
        client = OpenMaicFullRuntimeClient("http://127.0.0.1:3100")
        healthy = {"success": True, "status": "ok", "version": client.FORMAL_RUNTIME_VERSION,
            "capabilities": {"formalGeneration": True, "professionalAgent": True, "webSearch": True, "speechAudioGeneration": True},
            "runtimePolicy": {"formalGeneration": deepcopy(client.FORMAL_GENERATION_POLICY),
                "professionalResearch": deepcopy(client.FORMAL_PROFESSIONAL_RESEARCH_POLICY),
                "modelPolicy": deepcopy(client.FORMAL_PROFESSIONAL_MODEL_POLICY)}}
        client._request_json = Mock(return_value=healthy)
        self.assertTrue(client.formal_generation_readiness()["ready"])
        client._request_json.assert_called_once_with("GET", "/api/health?scope=formal-generation")
        for key, value in (("modelId", "other"), ("maxCalls", 2), ("maxCalls", True),
                           ("durationSec", 10), ("resolution", "1080p")):
            altered = deepcopy(healthy)
            altered["runtimePolicy"]["formalGeneration"]["professionalCreation"]["video"][key] = value
            client._request_json.return_value = altered
            self.assertFalse(client.formal_generation_readiness()["ready"])
        altered = deepcopy(healthy)
        altered["runtimePolicy"]["formalGeneration"]["professionalCreation"] = deepcopy(PROFESSIONAL_POLICY)
        client._request_json.return_value = altered
        self.assertFalse(client.formal_generation_readiness()["ready"])

    def test_valid_video_and_zero_video_receipts_bind_exact_professional_identity(self):
        row, _ = video_fixture()
        professional = row["feature_manifest_json"]["professionalCreation"]
        identity = dict(runtime_request_id=professional["runtimeRequestId"], classroom_id=professional["classroomId"],
                        build_item_id=professional["buildItemId"], session_id=professional["sessionId"])
        for assets in ([], [_asset()]):
            receipt = _video(professional, assets)
            self.assertEqual(video_receipt(receipt, **identity), receipt)
        for key, value in (("classroomId", "other"), ("sessionId", "other"), ("videoCount", True),
                           ("providerId", "other"), ("modelId", "other")):
            invalid = _video(professional, [_asset()]); invalid[key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                video_receipt(_with_receipt_sha256(invalid), **identity)
        for key, value in (("src", "https://example.test/movie.mp4"), ("src", "/api/classroom-media/other/media/movie.mp4"),
                           ("sha256", "b" * 64), ("byteSize", 200 * 1024 * 1024 + 1), ("width", 1920),
                           ("height", 1080), ("durationMs", 5101), ("durationMs", 4899), ("durationMs", True),
                           ("sceneIds", []), ("mimeType", "video/webm")):
            invalid = _video(professional, [_asset()]); invalid["assets"][0][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                video_receipt(_with_receipt_sha256(invalid), **identity)

    def test_scene_reference_coverage_and_availability_cannot_be_forged(self):
        row, _ = video_fixture(); professional = row["feature_manifest_json"]["professionalCreation"]
        asset = _asset(); receipt = _video(professional, [asset]); src = asset["src"]
        for content in ({"elements": [{"type": "video", "src": src}]},
                        {"html": f'<video src="{src}"></video>'},
                        {"html": f'<video><source src="{src}" type="video/mp4"></video>'}):
            classroom = {"stage": {"id": "classroom-1"}, "scenes": [{"id": "scene-1", "content": content}]}
            self.assertEqual(classroom_video_references(classroom), {src: {"scene-1"}})
            probe = Mock(return_value=True)
            self.assertEqual(validate_classroom_video(receipt, classroom, probe), video_evidence(receipt))
            probe.assert_called_once_with(src)
            with self.assertRaisesRegex(ValueError, "unavailable"):
                validate_classroom_video(receipt, classroom, Mock(return_value=False))
            with self.assertRaisesRegex(ValueError, "coverage mismatch"):
                validate_classroom_video(_video(professional), classroom, probe)
        classroom["scenes"][0]["id"] = "scene-2"
        with self.assertRaisesRegex(ValueError, "reference mismatch"):
            validate_classroom_video(receipt, classroom, probe)
        classroom["scenes"][0]["content"] = {"html": '<audio><source src="audio.mp3"></audio>'}
        self.assertEqual(classroom_video_references(classroom), {})
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            validate_classroom_video(receipt, classroom, probe)

    def test_terminal_client_requires_video_receipt_only_for_new_policy(self):
        client = OpenMaicFullRuntimeClient("http://127.0.0.1:3100", formal_audio_internal_token="t" * 48)
        for row in (adaptive_quality_fixture()[0], video_fixture()[0]):
            manifest = row["feature_manifest_json"]
            result = {"classroomId": "classroom-1", "scenesCount": 10, "speechActionCount": 12,
                      **{key: manifest[key] for key in ("professionalCreation", "research", "media")}}
            if "video" in manifest: result["video"] = manifest["video"]
            payload = {"jobId": "job-1", "status": "succeeded", "step": "completed", "progress": 100,
                "runtimeRequestId": "runtime-request-1", "formalInputSha256": "e" * 64,
                "formalContractVersion": client.FORMAL_RUNTIME_CONTRACT_VERSION, "result": result}
            job = client._job_from_payload(payload)
            self.assertEqual(job.video, manifest.get("video"))
            self.assertEqual(job.professional_creation, manifest["professionalCreation"])
            if "video" in result:
                result.pop("video")
                with self.assertRaises(OpenMaicFullRuntimeError) as error: client._job_from_payload(payload)
                self.assertEqual(error.exception.code, "invalid_openmaic_video_receipt")
            else:
                result["video"] = video_fixture()[0]["feature_manifest_json"]["video"]
                with self.assertRaises(OpenMaicFullRuntimeError): client._job_from_payload(payload)

    def test_manifest_and_student_launch_require_exact_zero_video_evidence(self):
        row, _ = video_fixture(); manifest = row["feature_manifest_json"]
        before = deepcopy(manifest)
        validate_media_manifest(manifest)
        self.assertEqual(manifest, before)
        def launch(value):
            return launch_fixtures.FormalStudentRuntimeLaunchTest()._service(value).create_student_launch("student-token", "session-1")
        self.assertTrue(launch(row)["ok"])
        for mutate in (lambda m: m.pop("video"), lambda m: m["formalEvidence"].pop("video"),
                       lambda m: m["video"].update(sessionId="other"),
                       lambda m: m["formalEvidence"]["video"].update(verified=False),
                       lambda m: m["generationContract"]["generation"].update(enableVideoGeneration=False),
                       lambda m: m["generationContract"].update(professionalCreationPolicy=deepcopy(PROFESSIONAL_POLICY))):
            invalid = deepcopy(row); mutate(invalid["feature_manifest_json"])
            with self.subTest(mutate=mutate), self.assertRaises(ValueError): validate_media_manifest(invalid["feature_manifest_json"])
            with self.assertRaises(OpenMaicRuntimeServiceError): launch(invalid)

    def test_publication_rechecks_video_and_classroom_receipt_binds_it(self):
        manifest = video_fixture()[0]["feature_manifest_json"]
        row = {"build_item_id": "build-item-1", "upstream_classroom_id": "classroom-1",
               "runtime_request_id": "runtime-request-1", "expected_segment_count": 12,
               "audio_state": "auto_validated", "audio_terminal_receipt_hash": "e" * 64,
               "runtime_classroom_id": "runtime-1", "upstream_job_id": "job-1",
               "audio_target_fingerprint": "a" * 64}
        row.update({key: 12 for key in ("tts_attempted_count", "tts_completed_count",
            "audio_validated_count", "asr_attempted_count", "asr_passed_count")})
        self.assertEqual(len(LearningCatalogRepository.formal_artifact_execution_sha256(row, manifest)), 64)
        old = adaptive_quality_fixture()[0]["feature_manifest_json"]
        self.assertNotEqual(LearningCatalogRepository.formal_classroom_receipt_sha256(row, manifest),
                            LearningCatalogRepository.formal_classroom_receipt_sha256(row, old))
        for mutate in (lambda m: m.pop("video"), lambda m: m["formalEvidence"]["video"].update(verified=False)):
            bad = deepcopy(manifest); mutate(bad)
            with self.assertRaises(LearningCatalogActivationError):
                LearningCatalogRepository.formal_artifact_execution_sha256(row, bad)

    def test_early_video_sql_gate_executes_against_real_json_rows(self):
        conn = sqlite3.connect(":memory:")
        def extract(raw, key):
            value = json.loads(raw)
            for piece in key.removeprefix("$.").split("."):
                if not isinstance(value, dict) or piece not in value: return None
                value = value[piece]
            return json.dumps(value)
        def unquote(raw):
            if raw is None: return None
            value = json.loads(raw)
            return value if isinstance(value, str) else json.dumps(value)
        def kind(raw):
            if raw is None: return None
            value = json.loads(raw)
            return "ARRAY" if isinstance(value, list) else "INTEGER" if type(value) is int else "OTHER"
        conn.create_function("JSON_EXTRACT", 2, extract); conn.create_function("JSON_UNQUOTE", 1, unquote)
        conn.create_function("JSON_TYPE", 1, kind)
        conn.create_function("JSON_LENGTH", 1, lambda raw: len(json.loads(raw)) if raw is not None else None)
        conn.create_function("regexp", 2, lambda expr, value: bool(value and re.fullmatch(expr, value)))
        conn.execute("CREATE TABLE runtime (feature_manifest_json TEXT, request_id TEXT, candidate_build_item_id TEXT, upstream_classroom_id TEXT)")
        conn.execute("INSERT INTO runtime VALUES (?, 'runtime-request-1', 'build-item-1', 'classroom-1')", ("{}",))
        def accepted(manifest):
            conn.execute("UPDATE runtime SET feature_manifest_json = ?", (json.dumps(manifest),))
            return conn.execute(f"SELECT 1 FROM runtime WHERE {_formal_video_sql('runtime')}").fetchone() is not None
        current = video_fixture()[0]["feature_manifest_json"]
        self.assertTrue(accepted(current)); self.assertTrue(accepted(adaptive_quality_fixture()[0]["feature_manifest_json"]))
        for mutate in (lambda m: m.pop("video"), lambda m: m["video"].update(videoCount=True),
                       lambda m: m["video"].update(classroomId="other"),
                       lambda m: m["formalEvidence"]["video"].update(receiptSha256="a" * 64),
                       lambda m: m["generationContract"]["generation"].update(enableVideoGeneration=False)):
            bad = deepcopy(current); mutate(bad)
            self.assertFalse(accepted(bad))
        self.assertIn(_formal_video_sql("runtime"), current_formal_runtime_sql(runtime_alias="runtime"))
        conn.close()


if __name__ == "__main__":
    unittest.main()
