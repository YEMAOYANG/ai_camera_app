from __future__ import annotations

from copy import deepcopy
import json
import unittest
from unittest.mock import Mock

from integrations.openmaic_formal_media import (
    FORMAL_IMAGE_POLICY, LEGACY_PROFESSIONAL_POLICY, IMAGE_PROFESSIONAL_POLICY, PROFESSIONAL_POLICY,
    INTEGRATED_PROFESSIONAL_POLICY,
    canonical_sha256, classroom_image_references, compatible_preparation_target, generation_options,
    media_evidence, media_receipt, policy_from_target, professional_policy,
    validate_classroom_media, validate_media_manifest,
)
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from services.learning_curriculum_preparation_contract import build_preparation_target, preparation_target_fingerprint
from services.openmaic_full_runtime_service import OpenMaicFullRuntimeService, OpenMaicRuntimeServiceError
from repositories.learning_catalog_repository import LearningCatalogRepository, LearningCatalogActivationError
from tests.test_formal_runtime_candidate_generation import _candidate_service, FINGERPRINT
from tests.test_formal_student_runtime_launch import _formal_row, _with_receipt_sha256
from tests import test_formal_student_runtime_launch as launch_fixtures


def _media(professional: dict, assets: list | None = None) -> dict:
    items = assets or []
    return _with_receipt_sha256({
        "schemaVersion": "mira.openmaic.formal-media-receipt.v1", "status": "succeeded",
        **{k: professional[k] for k in ("runtimeRequestId", "buildItemId", "classroomId", "sessionId")},
        **{k: FORMAL_IMAGE_POLICY[k] for k in ("policyId", "providerId", "modelId")},
        "imageCount": len(items), "assets": deepcopy(items),
    })


def _upgrade(row: dict, assets: list | None = None) -> dict:
    row = deepcopy(row)
    manifest = row["feature_manifest_json"]
    generation = manifest["generationContract"]
    generation["professionalCreationPolicy"] = deepcopy(IMAGE_PROFESSIONAL_POLICY)
    generation["generation"] = generation_options(IMAGE_PROFESSIONAL_POLICY)
    pro = manifest["professionalCreation"]
    pro.pop("receiptSha256")
    pro.update(imageGenerationEnabled=True, imagePolicyId=FORMAL_IMAGE_POLICY["policyId"])
    pro = manifest["professionalCreation"] = _with_receipt_sha256(pro)
    manifest["formalEvidence"]["professionalCreation"].update(
        imageGenerationEnabled=True, imagePolicyId=FORMAL_IMAGE_POLICY["policyId"],
        receiptSha256=pro["receiptSha256"],
    )
    manifest["media"] = _media(pro, assets)
    manifest["formalEvidence"]["media"] = media_evidence(manifest["media"])
    return row


def _asset() -> dict:
    digest = "a" * 64
    return {"src": f"/api/classroom-media/classroom-1/media/generated-{digest}.png",
            "sha256": digest, "mimeType": "image/png", "byteSize": 512,
            "width": 64, "height": 64, "sceneIds": ["scene-1"]}


class OpenMaicFormalMediaTest(unittest.TestCase):
    def test_new_target_changes_fingerprint_and_exact_legacy_remains_resumable(self):
        current = build_preparation_target("primary_1")
        legacy = deepcopy(current)
        from integrations.openmaic_formal_media import VIDEO_PROFESSIONAL_POLICY, LEGACY_CONTENT_PROVIDER_PROFILE
        legacy["contentProviderProfileContractVersion"] = LEGACY_CONTENT_PROVIDER_PROFILE
        legacy["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(LEGACY_PROFESSIONAL_POLICY)
        self.assertEqual(policy_from_target(current), VIDEO_PROFESSIONAL_POLICY)
        self.assertEqual(preparation_target_fingerprint(legacy), "174a787e2ddbb8dd9c50e859a829bd2fe08fec71838448a8c5e5b0d2246766f1")
        self.assertNotEqual(preparation_target_fingerprint(legacy), preparation_target_fingerprint(current))
        self.assertTrue(compatible_preparation_target(legacy, current))
        self.assertTrue(compatible_preparation_target(current, current))
        legacy["formalRuntimePolicy"]["enableWebSearch"] = False
        self.assertFalse(compatible_preparation_target(legacy, current))
        invalid = deepcopy(PROFESSIONAL_POLICY)
        invalid["image"]["enabled"] = 1
        with self.assertRaises(ValueError):
            professional_policy(invalid)

    def test_candidate_dispatch_and_resume_keep_the_persisted_policy(self):
        for policy in (LEGACY_PROFESSIONAL_POLICY, IMAGE_PROFESSIONAL_POLICY,
                       INTEGRATED_PROFESSIONAL_POLICY, PROFESSIONAL_POLICY):
            with self.subTest(image="image" in policy):
                service = _candidate_service()
                repository, client = service.repository, service.client
                repository.professional_policy = deepcopy(policy)
                kwargs = dict(build_item_id="build-item-1", course_id="candidate-course-1",
                    course_version="course-version-1", package_id="package-1", package_version=1,
                    target_fingerprint=FINGERPRINT, runtime_request_id="formal-runtime-request-1")
                service.issue_candidate_generation(**kwargs)
                dispatched = client.start_calls[0]
                self.assertEqual(dispatched["professional_creation_policy"], policy)
                self.assertIs(dispatched["enable_image_generation"], "image" in policy)
                contract = json.loads(dispatched["requirement"])
                if policy == PROFESSIONAL_POLICY:
                    from integrations.openmaic_formal_pedagogy import registered_grade_boundary
                    expected_boundary = registered_grade_boundary(grade_code="primary_1", subject="math", skill_id="number_sense_20")
                    self.assertEqual(contract["gradeBoundary"], expected_boundary)
                    self.assertEqual(contract["gradeBoundarySha256"], canonical_sha256(expected_boundary))
                else:
                    self.assertNotIn("gradeBoundary", contract)
                    self.assertNotIn("gradeBoundarySha256", contract)
                self.assertEqual(canonical_sha256(contract["teachingBrief"]), contract["teachingBriefSha256"])
                digest = service._formal_input_sha256(runtime_request_id=dispatched["runtime_request_id"],
                    generation_contract=contract, formal_contract=dispatched["formal_runtime_contract"])
                self.assertEqual(digest, client.jobs[dispatched["runtime_request_id"]].formal_input_sha256)
                service.issue_candidate_generation(**kwargs)
                self.assertEqual(len(client.start_calls), 1)

    def test_zero_image_receipt_is_required_when_image_policy_is_enabled(self):
        legacy = _formal_row()
        new = _upgrade(legacy)
        self.assertIsNone(validate_media_manifest(legacy["feature_manifest_json"]))
        self.assertEqual(validate_media_manifest(new["feature_manifest_json"])["imageCount"], 0)
        del new["feature_manifest_json"]["media"]
        with self.assertRaises(ValueError):
            validate_media_manifest(new["feature_manifest_json"])

    def test_client_sends_exact_persisted_policy_and_rejects_mixed_image_options(self):
        client = OpenMaicFullRuntimeClient("http://127.0.0.1:3100", formal_audio_internal_token="t" * 48)
        bodies = []

        def request(_method, _path, body, **_kwargs):
            bodies.append(deepcopy(body))
            return {"jobId": "job-1", "status": "running", "step": "generating_scenes", "progress": 35,
                    "runtimeRequestId": body["runtimeRequestId"],
                    "formalContractVersion": client.FORMAL_RUNTIME_CONTRACT_VERSION,
                    "formalInputSha256": client.formal_input_sha256(body)}

        client._request_json = Mock(side_effect=request)
        options = dict(requirement="persisted brief", enable_web_search=True,
            enable_video_generation=False, enable_tts=False, agent_mode="generate",
            runtime_request_id="request-1", formal_runtime_contract=client.FORMAL_RUNTIME_CLASSROOM_CONTRACT)
        for policy in (LEGACY_PROFESSIONAL_POLICY, PROFESSIONAL_POLICY):
            client.start_generation(**options, enable_image_generation="image" in policy,
                                    professional_creation_policy=policy)
            self.assertEqual(bodies[-1]["professionalCreationPolicy"], policy)
            self.assertIs(bodies[-1]["enableImageGeneration"], "image" in policy)
        self.assertNotEqual(client.formal_input_sha256(bodies[0]), client.formal_input_sha256(bodies[1]))
        with self.assertRaises(OpenMaicFullRuntimeError):
            client.start_generation(**options, enable_image_generation=False,
                                    professional_creation_policy=PROFESSIONAL_POLICY)
        self.assertEqual(len(bodies), 2)

    def test_receipt_rejects_identity_digest_shape_and_asset_tampering(self):
        professional = _upgrade(_formal_row())["feature_manifest_json"]["professionalCreation"]
        original = _media(professional, [_asset()])
        identity = {"runtime_request_id": professional["runtimeRequestId"], "classroom_id": professional["classroomId"],
                    "build_item_id": professional["buildItemId"], "session_id": professional["sessionId"]}
        self.assertEqual(media_receipt(original, **identity), original)
        changes = {
            "wrong stage": lambda x: x.update(classroomId="other-stage"),
            "wrong session": lambda x: x.update(sessionId="other-session"),
            "missing assets": lambda x: x.pop("assets"),
            "wrong count": lambda x: x.update(imageCount=0),
            "bool count": lambda x: x.update(imageCount=True),
            "wrong asset stage": lambda x: x["assets"][0].update(src="/api/classroom-media/other/media/image.png"),
            "external src": lambda x: x["assets"][0].update(src="https://example.test/image.png"),
            "filename digest": lambda x: x["assets"][0].update(sha256="b" * 64),
            "zero bytes": lambda x: x["assets"][0].update(byteSize=0),
            "duplicate scene": lambda x: x["assets"][0].update(sceneIds=["scene-1", "scene-1"]),
            "wrong mime": lambda x: x["assets"][0].update(mimeType="text/html"),
        }
        for name, mutate in changes.items():
            with self.subTest(name=name):
                invalid = deepcopy(original)
                mutate(invalid)
                invalid.pop("receiptSha256", None)
                invalid = _with_receipt_sha256(invalid)
                with self.assertRaises(ValueError):
                    media_receipt(invalid, **identity)
        tampered = deepcopy(original)
        tampered["receiptSha256"] = "f" * 64
        with self.assertRaises(ValueError):
            media_receipt(tampered, **identity)

    def test_images_bind_exactly_to_referenced_scenes_and_pass_the_media_probe(self):
        professional = _upgrade(_formal_row())["feature_manifest_json"]["professionalCreation"]
        asset = _asset()
        src = asset["src"]
        receipt = _media(professional, [asset])
        representations = [
            {"elements": [{"type": "image", "src": src}]},
            {"html": f'<img src="{src}">'},
            {"html": f'<img srcset="{src} 2x">'},
            {"html": f'<picture><source srcset="{src} 640w"></picture>'},
            {"html": f'<svg><image href="{src}" /></svg>'},
            {"html": f'<div style="background-image:url(\'{src}\')"></div>'},
        ]
        for content in representations:
            classroom = {"stage": {"id": "classroom-1"}, "scenes": [{"id": "scene-1", "content": content}]}
            probe = Mock(return_value=True)
            self.assertEqual(validate_classroom_media(receipt, classroom, probe), media_evidence(receipt))
            probe.assert_called_once_with(src)
            with self.assertRaises(ValueError):
                validate_classroom_media(receipt, classroom, lambda _: False)
        for classroom in (
            {"stage": {"id": "classroom-1"}, "scenes": [{"id": "scene-2", "content": representations[0]}]},
            {"stage": {"id": "classroom-1"}, "scenes": [{"id": "scene-1", "content": {}}]},
            {"stage": {"id": "other"}, "scenes": [{"id": "scene-1", "content": representations[0]}]},
        ):
            with self.assertRaises(ValueError):
                validate_classroom_media(receipt, classroom, lambda _: True)
        with self.assertRaises(ValueError):
            validate_classroom_media(_media(professional),
                {"stage": {"id": "classroom-1"}, "scenes": [{"id": "scene-1", "content": representations[0]}]}, lambda _: True)

    def test_srcset_url_and_descriptor_cases_match_the_runtime_parser(self):
        cases = [
            ("/small.png 320w, /large.png 640w", {"/small.png", "/large.png"}),
            ("/small.png 1x,/large.png 2x", {"/small.png", "/large.png"}),
            (", /small.png, , /large.png,", {"/small.png", "/large.png"}),
            ("data:image/png;base64,AAAA 1x, /large.png 2x", {"data:image/png;base64,AAAA", "/large.png"}),
            ("data:image/svg+xml,%3Csvg%3E,%3C/svg%3E, /large.png 2x", {"data:image/svg+xml,%3Csvg%3E,%3C/svg%3E", "/large.png"}),
            ("/image,a.png 1x, /large.png 2x", {"/image,a.png", "/large.png"}),
            ("/small.png,/large.png", {"/small.png,/large.png"}),
            ("\t/small.png\n320w,\f/large.png\r640w", {"/small.png", "/large.png"}),
            ("/small.png\u00a01x", {"/small.png\u00a01x"}),
            ("/bad.png 0w, /valid.png 200w 100h", {"/valid.png"}),
            ("/bad.png 1w 2x, /valid.png .5x", {"/valid.png"}),
            ("/bad.png 1x 2x, /valid.png 1e2x", {"/valid.png"}),
            ("/bad.png -1x, /valid.png 0x", {"/valid.png"}),
            ("/bad.png +1x, /valid.png 0x 1x", {"/valid.png"}),
            ("/bad.png 2w 2w, /valid.png 100h", {"/valid.png"}),
            ("/bad.png calc(1, 2)x, /valid.png 1x", {"/valid.png"}),
            ("/bad.png broken(1, /other.png 2x", set()),
        ]
        for srcset, expected in cases:
            with self.subTest(srcset=srcset):
                classroom = {"scenes": [{"id": "scene-1", "content": {"html": f'<img srcset="{srcset}">'}}]}
                self.assertEqual(classroom_image_references(classroom), {src: {"scene-1"} for src in expected})

    def test_responsive_image_receipt_covers_all_source_candidates_and_scenes(self):
        professional = _upgrade(_formal_row())["feature_manifest_json"]["professionalCreation"]
        small, large = _asset(), _asset()
        large.update(src="/api/classroom-media/classroom-1/media/large.png", sceneIds=["scene-1", "scene-2"])
        classroom = {"stage": {"id": "classroom-1"}, "scenes": [
            {"id": "scene-1", "content": {"html": (
                f'<picture><source srcset="{small["src"]} 320w, {large["src"]} 640w">'
                f'<img src="{small["src"]}" srcset="{large["src"]} 2x"></picture>')}},
            {"id": "scene-2", "content": {"html": f'<img srcset="{large["src"]}">'}},
        ]}
        receipt = _media(professional, [small, large])
        probe = Mock(return_value=True)
        self.assertEqual(validate_classroom_media(receipt, classroom, probe), media_evidence(receipt))
        self.assertEqual([call.args[0] for call in probe.call_args_list], [small["src"], large["src"]])
        with self.assertRaisesRegex(ValueError, "coverage mismatch"):
            validate_classroom_media(_media(professional, [small]), classroom, probe)

    def test_srcset_nonlocal_urls_remain_references_and_cannot_bypass_receipts(self):
        professional = _upgrade(_formal_row())["feature_manifest_json"]["professionalCreation"]
        asset = _asset()
        for url in ("data:image/png;base64,AAAA", "https://example.test/image,a.png"):
            with self.subTest(url=url):
                classroom = {"stage": {"id": "classroom-1"}, "scenes": [{"id": "scene-1", "content": {
                    "html": f'<source srcset="{url} 1x, {asset["src"]} 2x">'}}]}
                self.assertEqual(classroom_image_references(classroom), {url: {"scene-1"}, asset["src"]: {"scene-1"}})
                probe = Mock(return_value=True)
                with self.assertRaisesRegex(ValueError, "coverage mismatch"):
                    validate_classroom_media(_media(professional, [asset]), classroom, probe)
                probe.assert_not_called()

    def test_html_image_attributes_are_decoded_once_like_the_runtime(self):
        classroom = {"scenes": [{"id": "scene-1", "content": {"html": (
            '<img src="/main.png?a=1&amp;b=2" srcset="/retina.png?a=1&amp;amp;b=2 2x" srcset="/ignored.png 1x">'
            '<svg><image xlink:href="/svg.png?a=1&amp;b=2" /></svg>')}}]}
        self.assertEqual(classroom_image_references(classroom), {
            "/main.png?a=1&b=2": {"scene-1"},
            "/retina.png?a=1&amp;b=2": {"scene-1"},
            "/svg.png?a=1&b=2": {"scene-1"},
        })

    def test_client_parses_new_media_and_preserves_exact_legacy_receipts(self):
        client = OpenMaicFullRuntimeClient("http://127.0.0.1:3100", formal_audio_internal_token="x" * 48)
        for row in (_formal_row(), _upgrade(_formal_row())):
            manifest = row["feature_manifest_json"]
            payload = {"jobId": "job-1", "status": "succeeded", "step": "completed", "progress": 100,
                "runtimeRequestId": "runtime-request-1", "formalInputSha256": "e" * 64,
                "formalContractVersion": OpenMaicFullRuntimeClient.FORMAL_RUNTIME_CONTRACT_VERSION,
                "result": {"classroomId": "classroom-1", "scenesCount": 10, "speechActionCount": 12,
                    "professionalCreation": manifest["professionalCreation"], "research": manifest["research"]}}
            if "media" in manifest:
                payload["result"]["media"] = manifest["media"]
            job = client._job_from_payload(payload)
            self.assertEqual(job.professional_creation, manifest["professionalCreation"])
            self.assertEqual(job.media, manifest.get("media"))
            if "media" in manifest:
                del payload["result"]["media"]
                with self.assertRaises(OpenMaicFullRuntimeError) as caught:
                    client._job_from_payload(payload)
                self.assertEqual(caught.exception.code, "invalid_openmaic_media_receipt")

    def test_launch_preserves_legacy_and_rejects_new_missing_or_mismatched_media(self):
        def launch(row):
            service = launch_fixtures.FormalStudentRuntimeLaunchTest()._service(row)
            return service.create_student_launch("student-token", "session-1")
        legacy = _formal_row()
        self.assertTrue(launch(legacy)["ok"])
        new = _upgrade(legacy)
        self.assertTrue(launch(new)["ok"])
        for mutate in (
            lambda m: m.pop("media"),
            lambda m: m["formalEvidence"]["media"].update(verified=False),
            lambda m: m["media"].update(sessionId="other-session"),
            lambda m: m["generationContract"]["generation"].update(enableImageGeneration=False),
            lambda m: m["generationContract"].update(professionalCreationPolicy=deepcopy(LEGACY_PROFESSIONAL_POLICY)),
        ):
            invalid = deepcopy(new)
            mutate(invalid["feature_manifest_json"])
            with self.assertRaises(OpenMaicRuntimeServiceError):
                launch(invalid)

    def test_publication_rechecks_media_and_classroom_hash_binds_its_receipt(self):
        row = {"build_item_id": "build-item-1", "upstream_classroom_id": "classroom-1",
               "runtime_request_id": "runtime-request-1", "expected_segment_count": 12,
               "audio_state": "auto_validated", "audio_terminal_receipt_hash": "e" * 64,
               "runtime_classroom_id": "runtime-1", "upstream_job_id": "job-1",
               "audio_target_fingerprint": "a" * 64}
        row.update({key: 12 for key in ("tts_attempted_count", "tts_completed_count",
            "audio_validated_count", "asr_attempted_count", "asr_passed_count")})
        legacy = _formal_row()["feature_manifest_json"]
        self.assertEqual(len(LearningCatalogRepository.formal_artifact_execution_sha256(row, legacy)), 64)
        new = _upgrade(_formal_row())["feature_manifest_json"]
        self.assertEqual(len(LearningCatalogRepository.formal_artifact_execution_sha256(row, new)), 64)
        self.assertNotEqual(LearningCatalogRepository.formal_classroom_receipt_sha256(row, legacy),
                            LearningCatalogRepository.formal_classroom_receipt_sha256(row, new))
        missing = deepcopy(new)
        del missing["media"]
        with self.assertRaises(LearningCatalogActivationError):
            LearningCatalogRepository.formal_artifact_execution_sha256(row, missing)

    def test_early_student_gate_requires_media_only_for_the_new_policy(self):
        from repositories.formal_student_runtime_gate import current_formal_runtime_sql
        sql = current_formal_runtime_sql(runtime_alias="runtime")
        self.assertIn("'$.generationContract.professionalCreationPolicy.image') IS NULL", sql)
        self.assertIn("mira.openmaic.formal-media-receipt.v1", sql)
        self.assertIn("'$.media.classroomId')) = runtime.upstream_classroom_id", sql)
        self.assertIn("'$.formalEvidence.media.receiptSha256'", sql)


if __name__ == "__main__":
    unittest.main()
