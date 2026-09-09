from __future__ import annotations

from copy import deepcopy
import unittest

from integrations.openmaic_formal_media import (
    LEGACY_PROFESSIONAL_POLICY, IMAGE_PROFESSIONAL_POLICY,
    INTEGRATED_PROFESSIONAL_POLICY as PROFESSIONAL_POLICY,
    compatible_preparation_target, generation_options, professional_policy, validate_media_manifest,
)
from integrations.openmaic_formal_skills import (
    FORMAL_SKILL_ORCHESTRATION_POLICY, skill_orchestration_receipt,
    validate_classroom_skills, validate_skill_manifest,
)
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from services.openmaic_full_runtime_service import OpenMaicRuntimeServiceError
from services.learning_curriculum_preparation_contract import build_preparation_target, preparation_target_fingerprint
from tests.test_formal_student_runtime_launch import (
    _formal_row, _with_receipt_sha256,
)
from tests import test_formal_student_runtime_launch as launch_fixtures
from tests.test_openmaic_formal_media import _upgrade


def integrated_row(subject="math"):
    row = _upgrade(_formal_row(subject=subject))
    manifest = row["feature_manifest_json"]
    generation = manifest["generationContract"]
    generation["professionalCreationPolicy"] = deepcopy(PROFESSIONAL_POLICY)
    generation["generation"] = generation_options(PROFESSIONAL_POLICY)
    types = ["slide"] * 5 + ["quiz"] * 2 + ["interactive"] * 3
    contexts = [{"sceneId": f"formal-scene-{i + 1}", "sceneType": kind,
                 "contentContextSha256": "a" * 64, "actionsContextSha256": "b" * 64}
                for i, kind in enumerate(types)]
    for scene, context in zip(manifest["formalEvidence"]["runtimeEventAuthority"]["scenes"], contexts):
        scene["sceneId"] = context["sceneId"]
    proof = _with_receipt_sha256({
        "schemaVersion": "mira.openmaic.skill-orchestration-receipt.v1",
        "profileId": "mira-primary-integrated.v1", "status": "succeeded",
        "skillReads": [{"skillId": skill_id, "sourceHash": "c" * 64}
                       for skill_id in FORMAL_SKILL_ORCHESTRATION_POLICY["skillIds"]],
        "referenceReads": [
            {"resourcePath": "k12-core-literacy-planning/references/core-literacy.md", "sourceHash": "d" * 64},
            {"resourcePath": "k12-core-literacy-planning/references/subjects/" +
             ("mathematics.md" if subject == "math" else "languages.md"), "sourceHash": "e" * 64},
        ],
        "sceneContexts": contexts,
    })
    professional = manifest["professionalCreation"]
    professional.pop("receiptSha256")
    professional["skillOrchestration"] = proof
    professional = manifest["professionalCreation"] = _with_receipt_sha256(professional)
    manifest["formalEvidence"]["professionalCreation"].update(
        skillOrchestration=deepcopy(proof), receiptSha256=professional["receiptSha256"])
    return row


class OpenMaicFormalSkillsTest(unittest.TestCase):
    def test_three_exact_targets_remain_valid_without_mutating_historical_identity(self):
        current = build_preparation_target("primary_1")
        for policy, digest in (
            (LEGACY_PROFESSIONAL_POLICY, "174a787e2ddbb8dd9c50e859a829bd2fe08fec71838448a8c5e5b0d2246766f1"),
            (IMAGE_PROFESSIONAL_POLICY, "48cceefd0543abe9e3bfcf2f8d640ef21b8e03503cfa3dc6ef89a0428bcef2df"),
            (PROFESSIONAL_POLICY, "7d4c0980789621cffb338e14b39c7dbc7b0d34c40013be0725c0076dad3b90a3"),
        ):
            with self.subTest(policy=policy):
                target = deepcopy(current)
                target["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(policy)
                from integrations.openmaic_formal_media import LEGACY_CONTENT_PROVIDER_PROFILE
                target["contentProviderProfileContractVersion"] = LEGACY_CONTENT_PROVIDER_PROFILE
                frozen = deepcopy(target)
                self.assertEqual(professional_policy(policy), policy)
                self.assertTrue(compatible_preparation_target(target, current))
                self.assertEqual(preparation_target_fingerprint(target), digest)
                self.assertEqual(target, frozen)
                target["subjectTargets"]["math"]["totalCourseCount"] += 1
                self.assertFalse(compatible_preparation_target(target, current))

    def test_new_and_both_historical_receipts_launch_without_rewriting(self):
        for row in (_formal_row(), _upgrade(_formal_row()), integrated_row()):
            manifest = row["feature_manifest_json"]
            frozen = deepcopy(manifest)
            pro = manifest["professionalCreation"]
            self.assertEqual(OpenMaicFullRuntimeClient._professional_creation_receipt_from_payload(
                pro, runtime_request_id=pro["runtimeRequestId"], classroom_id=pro["classroomId"]), pro)
            service = launch_fixtures.FormalStudentRuntimeLaunchTest()._service(row)
            self.assertTrue(service.create_student_launch("student-token", "session-1")["ok"])
            self.assertEqual(manifest, frozen)

    def test_missing_or_fabricated_read_shape_rejected_even_after_rehash(self):
        base = integrated_row()["feature_manifest_json"]["professionalCreation"]["skillOrchestration"]
        mutations = [
            lambda x: x["skillReads"].pop(),
            lambda x: x["skillReads"].reverse(),
            lambda x: x["skillReads"][0].update(sourceHash="c" * 16),
            lambda x: x["referenceReads"].pop(),
            lambda x: x["referenceReads"][1].update(resourcePath="../../private.md"),
            lambda x: x["referenceReads"][1].update(resourcePath=[]),
            lambda x: x["sceneContexts"][0].pop("actionsContextSha256"),
            lambda x: x["sceneContexts"].append(deepcopy(x["sceneContexts"][0])),
            lambda x: x["sceneContexts"][0].update(sceneType=[]),
            lambda x: x.update(status="pending"),
        ]
        for mutation in mutations:
            receipt = deepcopy(base)
            mutation(receipt)
            receipt.pop("receiptSha256")
            with self.assertRaises(ValueError):
                skill_orchestration_receipt(_with_receipt_sha256(receipt))
        base["receiptSha256"] = "f" * 64
        with self.assertRaises(ValueError):
            skill_orchestration_receipt(base)

    def test_every_final_scene_and_its_type_must_have_both_contexts(self):
        manifest = integrated_row()["feature_manifest_json"]
        pro, generation = manifest["professionalCreation"], manifest["generationContract"]
        scenes = [{"id": c["sceneId"], "type": c["sceneType"]}
                  for c in pro["skillOrchestration"]["sceneContexts"]]
        validate_classroom_skills(pro, generation, {"scenes": scenes})
        for changed in (scenes[:-1], scenes + [{"id": "uncovered", "type": "slide"}],
                        [{"id": "foreign", "type": "slide"}] + scenes[1:],
                        [{**scenes[0], "type": "interactive"}] + scenes[1:]):
            with self.assertRaises(ValueError):
                validate_classroom_skills(pro, generation, {"scenes": changed})

    def test_subject_reference_is_bound_to_the_locked_teaching_brief(self):
        for subject in ("math", "chinese", "english"):
            manifest = integrated_row(subject)["feature_manifest_json"]
            validate_skill_manifest(manifest)
            manifest["generationContract"]["teachingBrief"]["course"]["subject"] = "chinese" if subject == "math" else "math"
            with self.assertRaises(ValueError):
                validate_skill_manifest(manifest)

    def test_missing_mixed_or_wrong_scene_evidence_cannot_launch(self):
        mutations = [
            lambda m: m["professionalCreation"].pop("skillOrchestration"),
            lambda m: m["generationContract"].update(professionalCreationPolicy=deepcopy(IMAGE_PROFESSIONAL_POLICY)),
            lambda m: m["formalEvidence"]["runtimeEventAuthority"]["scenes"][0].update(sceneId="foreign-scene"),
            lambda m: m["formalEvidence"]["sceneDistribution"].update(slide=4),
            lambda m: m["professionalCreation"]["skillOrchestration"].update(receiptSha256="f" * 64),
            lambda m: m["formalEvidence"]["professionalCreation"].pop("skillOrchestration"),
        ]
        for mutation in mutations:
            row = integrated_row()
            mutation(row["feature_manifest_json"])
            service = launch_fixtures.FormalStudentRuntimeLaunchTest()._service(row)
            with self.assertRaises(OpenMaicRuntimeServiceError):
                service.create_student_launch("student-token", "session-1")

    def test_publication_rejects_missing_proof_copy_and_stale_parent_digest(self):
        for mutate in (
            lambda m: m["formalEvidence"]["professionalCreation"].pop("skillOrchestration"),
            lambda m: m["formalEvidence"]["professionalCreation"]["skillOrchestration"].update(status="pending"),
            lambda m: m["professionalCreation"].update(receiptSha256="f" * 64),
        ):
            manifest = integrated_row()["feature_manifest_json"]
            mutate(manifest)
            with self.assertRaises(ValueError):
                validate_media_manifest(manifest)

    def test_skill_policy_cannot_be_attached_to_historical_receipts(self):
        manifest = _upgrade(_formal_row())["feature_manifest_json"]
        manifest["generationContract"]["professionalCreationPolicy"] = deepcopy(PROFESSIONAL_POLICY)
        with self.assertRaises(ValueError):
            validate_media_manifest(manifest)
        new = integrated_row()["feature_manifest_json"]["professionalCreation"]
        for key in ("imageGenerationEnabled", "imagePolicyId"):
            new.pop(key)
        new.pop("receiptSha256")
        new = _with_receipt_sha256(new)
        with self.assertRaises(OpenMaicFullRuntimeError):
            OpenMaicFullRuntimeClient._professional_creation_receipt_from_payload(
                new, runtime_request_id=new["runtimeRequestId"], classroom_id=new["classroomId"])
