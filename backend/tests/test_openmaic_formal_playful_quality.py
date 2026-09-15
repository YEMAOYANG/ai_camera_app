"""Frozen playful context compatibility, without Provider or database calls."""
from copy import deepcopy
from contextlib import nullcontext
import json
import os
import unittest
from unittest.mock import Mock, patch

from integrations.openmaic_formal_media import PLAYFUL_PROFESSIONAL_POLICY, REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY, generation_options
from integrations.openmaic_formal_playful import (
    PLAYFUL_LEARNING_POLICY, playful_generation_kwargs, playful_quality_context,
)
from integrations.openmaic_formal_quality import (
    professional_quality_fields, quality_sha, teaching_quality_receipt,
    validate_classroom_quality, validate_quality_manifest,
)
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from tests.test_openmaic_formal_quality import adaptive_quality_fixture
from tests.test_openmaic_formal_interaction import signed
from services.learning_media_materialization_service import FormalQwenAudioService


def playful_fixture(policy=PLAYFUL_PROFESSIONAL_POLICY):
    row, classroom = adaptive_quality_fixture()
    manifest = row["feature_manifest_json"]
    generation = manifest["generationContract"]
    generation.update(professionalCreationPolicy=deepcopy(policy),
                      generation=generation_options(policy))
    professional = manifest["professionalCreation"]
    quality = professional["teachingQuality"]
    identity = {key: quality[key] for key in (
        "snapshotSha256", "gradeBoundarySha256", "selectionPlanSha256", "teachingBriefSha256", "renderChecks")}
    # Independently mirror the Native context, not the helper under test.
    identity["playfulContextSha256"] = quality_sha({"policy": policy["playfulLearningPolicy"],
        "subject": "math", "guidedQuestionIds": ["q2", "q3"], "independentQuestionIds": ["q4", "q5"]})
    quality["review"]["inputSha256"] = quality_sha(identity)
    professional["teachingQuality"] = signed(quality)
    professional = manifest["professionalCreation"] = signed(professional)
    manifest["formalEvidence"]["professionalCreation"].update(
        teachingQuality=deepcopy(professional["teachingQuality"]), receiptSha256=professional["receiptSha256"])
    manifest["formalEvidence"]["teachingQuality"] = validate_classroom_quality(professional, generation, classroom)
    return manifest, classroom


class PlayfulQualityCompatibilityTest(unittest.TestCase):
    def test_required_3d_review_hash_binds_v2_and_cannot_reuse_v1_receipt(self):
        legacy, _ = playful_fixture()
        selected, classroom = playful_fixture(REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY)
        generation = selected["generationContract"]
        before = deepcopy(selected)
        self.assertEqual(playful_quality_context(generation)["policy"],
                         REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY["playfulLearningPolicy"])
        self.assertNotEqual(selected["professionalCreation"]["teachingQuality"]["review"]["inputSha256"],
                            legacy["professionalCreation"]["teachingQuality"]["review"]["inputSha256"])
        validate_quality_manifest(selected)
        self.assertEqual(validate_classroom_quality(selected["professionalCreation"], generation, classroom),
                         selected["formalEvidence"]["teachingQuality"])
        with self.assertRaisesRegex(ValueError, "identity drifted"):
            teaching_quality_receipt(legacy["professionalCreation"]["teachingQuality"], generation_contract=generation)
        self.assertEqual(selected, before)

    def test_required_3d_readiness_requires_explicit_native_support(self):
        client = OpenMaicFullRuntimeClient("http://native.invalid")
        payload = {"success": True, "status": "ok", "version": client.FORMAL_RUNTIME_VERSION,
            "capabilities": {key: True for key in ("formalGeneration", "professionalAgent", "webSearch", "speechAudioGeneration")},
            "runtimePolicy": {"formalGeneration": deepcopy(client.FORMAL_GENERATION_POLICY),
                "professionalResearch": deepcopy(client.FORMAL_PROFESSIONAL_RESEARCH_POLICY),
                "modelPolicy": deepcopy(client.FORMAL_PROFESSIONAL_MODEL_POLICY),
                "webSearch": {"schemaVersion": "mira.openmaic.web-search-production-config.v1",
                    "providerId": "baidu", "productionMode": "baidu_api",
                    "formalProductionConfigured": True, "verification": "configuration_only"}}}
        client._request_json = Mock(return_value=payload)
        with patch.dict(os.environ, {"MIRA_FORMAL_PLAYFUL_REQUIRE_3D": ""}):
            self.assertTrue(client.formal_generation_readiness()["ready"])
        with patch.dict(os.environ, {"MIRA_FORMAL_PLAYFUL_REQUIRE_3D": "1"}):
            self.assertFalse(client.formal_generation_readiness()["ready"])
            payload["runtimePolicy"]["formalGenerationSupportedProfessionalPolicies"] = [
                deepcopy(PLAYFUL_PROFESSIONAL_POLICY), deepcopy(REQUIRED_3D_PLAYFUL_PROFESSIONAL_POLICY)]
            self.assertTrue(client.formal_generation_readiness()["ready"])
            payload["runtimePolicy"]["formalGenerationSupportedProfessionalPolicies"][1]["playfulLearningPolicy"]["minimumThreeDScenes"] = True
            self.assertFalse(client.formal_generation_readiness()["ready"])

    def test_audio_import_reads_context_from_the_bound_runtime_without_provider_work(self):
        manifest, _ = playful_fixture()
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = {"feature_manifest_json": json.dumps(manifest)}
        repository = Mock()
        repository.transaction.return_value = nullcontext(conn)
        repository.decode_json.side_effect = lambda raw, fallback: json.loads(raw) if raw else fallback
        repository.get_formal_audio_job.return_value = {"runtime_classroom_id": "bound-runtime",
            "runtime_request_id": "original-request", "upstream_classroom_id": "original-stage"}
        client = Mock()
        client.get_generation_job_by_request_id.side_effect = RuntimeError("end this read-only fixture at receipt read")
        service = FormalQwenAudioService(repository, runtime_client=client, asset_store=Mock())
        service._terminalize = Mock(return_value={"fixtureStopped": True})
        self.assertEqual(service._process_claimed_job(build_item_id="original-item", claim_token="claim"), {"fixtureStopped": True})
        self.assertEqual(conn.execute.call_args.args, (
            "SELECT feature_manifest_json FROM learning_openmaic_runtime_classrooms WHERE id = ? LIMIT 1", ("bound-runtime",)))
        client.get_generation_job_by_request_id.assert_called_once_with("original-request", generation_contract=manifest["generationContract"])
        client.start_formal_audio_tts.assert_not_called()
        client.start_formal_audio_asr.assert_not_called()

    def test_frozen_context_binds_passed_receipt_and_final_classroom_without_mutation(self):
        manifest, classroom = playful_fixture()
        before = deepcopy(manifest)
        generation, professional = manifest["generationContract"], manifest["professionalCreation"]
        quality = professional["teachingQuality"]
        self.assertEqual(playful_quality_context(generation), {"policy": PLAYFUL_LEARNING_POLICY,
            "subject": "math", "guidedQuestionIds": ["q2", "q3"], "independentQuestionIds": ["q4", "q5"]})
        self.assertEqual(teaching_quality_receipt(quality, generation_contract=generation), quality)
        self.assertEqual(professional_quality_fields(professional, generation_contract=generation), {"teachingQuality": quality})
        self.assertEqual(validate_classroom_quality(professional, generation, classroom), manifest["formalEvidence"]["teachingQuality"])
        validate_quality_manifest(manifest)
        self.assertEqual(OpenMaicFullRuntimeClient._professional_creation_receipt_from_payload(professional,
            runtime_request_id=professional["runtimeRequestId"], classroom_id=professional["classroomId"],
            generation_contract=generation), professional)
        self.assertEqual(manifest, before)

    def test_playful_identity_cannot_be_accepted_without_frozen_authority(self):
        manifest, _ = playful_fixture()
        professional = manifest["professionalCreation"]
        with self.assertRaisesRegex(ValueError, "identity drifted"):
            teaching_quality_receipt(professional["teachingQuality"])
        with self.assertRaises(OpenMaicFullRuntimeError):
            OpenMaicFullRuntimeClient._professional_creation_receipt_from_payload(professional,
                runtime_request_id=professional["runtimeRequestId"], classroom_id=professional["classroomId"])
        forged = deepcopy(professional["teachingQuality"])
        forged["playfulContextSha256"] = "a" * 64
        with self.assertRaisesRegex(ValueError, "fields"):
            teaching_quality_receipt(signed(forged), generation_contract=manifest["generationContract"])

    def test_policy_subject_group_order_or_assessment_drift_cannot_reuse_the_review(self):
        mutations = (
            lambda g: g["professionalCreationPolicy"]["playfulLearningPolicy"].update(aiDesigned=False),
            lambda g: g["teachingBrief"]["course"].update(subject="english"),
            lambda g: g["teachingBrief"]["lesson"]["teachingFlow"]["guidedQuestionIds"].reverse(),
            lambda g: g["teachingBrief"]["lesson"]["teachingFlow"].update(independentQuestionIds=["q2", "q5"]),
            lambda g: g["teachingBrief"]["lesson"]["teachingFlow"].update(guidedQuestionIds=["unknown", "q3"]),
        )
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                manifest, _ = playful_fixture()
                generation = manifest["generationContract"]
                mutate(generation)
                generation["teachingBriefSha256"] = quality_sha(generation["teachingBrief"])
                with self.assertRaises(ValueError):
                    teaching_quality_receipt(manifest["professionalCreation"]["teachingQuality"], generation_contract=generation)

    def test_unfrozen_brief_and_missing_question_groups_fail_closed(self):
        for change in (lambda g: g.update(teachingBriefSha256="0" * 64),
                       lambda g: g["teachingBrief"]["lesson"]["teachingFlow"].pop("guidedQuestionIds")):
            manifest, _ = playful_fixture()
            generation = manifest["generationContract"]
            change(generation)
            with self.assertRaises(ValueError):
                playful_quality_context(generation)

    def test_old_receipts_remain_strict_and_no_context_is_sent_to_legacy_clients(self):
        row, _ = adaptive_quality_fixture()
        generation = row["feature_manifest_json"]["generationContract"]
        quality = row["feature_manifest_json"]["professionalCreation"]["teachingQuality"]
        self.assertIsNone(playful_quality_context(generation))
        self.assertEqual(playful_generation_kwargs(generation), {})
        self.assertEqual(teaching_quality_receipt(quality), quality)
        self.assertEqual(teaching_quality_receipt(quality, generation_contract=generation), quality)
        manifest, _ = playful_fixture()
        self.assertIs(playful_generation_kwargs(manifest["generationContract"])["generation_contract"], manifest["generationContract"])
        with self.assertRaises(ValueError):
            teaching_quality_receipt(quality, generation_contract=manifest["generationContract"])
