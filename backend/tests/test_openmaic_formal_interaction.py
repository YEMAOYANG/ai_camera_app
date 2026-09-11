from copy import deepcopy
import json
import unittest

from integrations.openmaic_formal_interaction import (
    PLAN_SCHEMA, RECEIPT_SCHEMA, INTERACTION_DESIGN_POLICY, interaction_design_receipt,
    validate_classroom_interaction, validate_interaction_manifest,
)
from integrations.openmaic_formal_media import (
    INTERACTIVE_PROFESSIONAL_POLICY, MULTISTATE_PROFESSIONAL_POLICY, VIDEO_PROFESSIONAL_POLICY,
    compatible_preparation_target, generation_options,
)
from integrations.openmaic_formal_quality import quality_sha, quality_snapshot, QUALITY_VIEWPORTS
from integrations.openmaic_formal_video import FORMAL_VIDEO_POLICY
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient
from services.learning_curriculum_preparation_contract import build_preparation_target, preparation_target_fingerprint
from tests.test_openmaic_formal_quality import adaptive_quality_fixture, rehash_quality


def signed(value):
    value = {k: deepcopy(v) for k, v in value.items() if k != "receiptSha256"}
    return {**value, "receiptSha256": quality_sha(value)}


def interaction_fixture(*, discussion=False):
    row, classroom = adaptive_quality_fixture()
    manifest = row["feature_manifest_json"]
    generation = manifest["generationContract"]
    generation.update(professionalCreationPolicy=deepcopy(INTERACTIVE_PROFESSIONAL_POLICY),
                      generation=generation_options(INTERACTIVE_PROFESSIONAL_POLICY))
    # Demonstration, manipulation, and independent quiz are in teaching order.
    scenes = classroom["scenes"]
    if discussion:
        scenes[0]["actions"].append({"id": "discussion-guidance", "type": "discussion", "topic": "十个一怎样合成一个十？", "prompt": "用摆积木解释十位和个位。"})
    scenes[7]["order"], scenes[5]["order"] = scenes[5]["order"], scenes[7]["order"]
    scenes[6]["order"], scenes[9]["order"] = scenes[9]["order"], scenes[6]["order"]
    objectives = [{"objectiveIndex": i,
        "demonstration": {"sceneId": scenes[0]["id"], "quote": "十个一是一个十"},
        "operation": {"sceneId": scenes[7]["id"], "controlSelector": "#quantity", "action": "range", "value": "12"},
        "feedback": {"sceneId": scenes[7]["id"], "selector": "#result", "textIncludes": "一个十两个一", "reasonQuote": "十个一是一个十"},
        "independentJudgment": {"sceneId": scenes[6]["id"], "questionId": "q4"}}
        for i in range(len(generation["gradeBoundary"]["learningObjectives"]))]
    plan = {"schemaVersion": PLAN_SCHEMA, "objectives": objectives}
    scenes[7]["content"]["html"] = '<input type="range" id="quantity"><div id="result">十个一是一个十</div>' + (
        '<script type="application/json" id="mira-interaction-plan">' + json.dumps(plan, ensure_ascii=False) + '</script>')
    professional = manifest["professionalCreation"]
    professional.update(videoGenerationEnabled=True, videoPolicyId=FORMAL_VIDEO_POLICY["policyId"])
    snapshot = quality_snapshot(classroom)
    quality = professional["teachingQuality"]
    quality["snapshotSha256"] = quality_sha(snapshot)
    quality["sceneHashes"] = [{"sceneId": s["id"], "sceneSha256": quality_sha(s)} for s in snapshot["scenes"]]
    quality["renderChecks"] = [{**hash_row, "viewport": v, "screenshotSha256": "a" * 64, "domSha256": "b" * 64,
                               "passed": True, "probeCount": 1}
                              for hash_row in quality["sceneHashes"] for v in QUALITY_VIEWPORTS]
    professional = rehash_quality(professional)
    quality = professional["teachingQuality"]
    op_hash = next(r["sceneSha256"] for r in quality["sceneHashes"] if r["sceneId"] == scenes[7]["id"])
    receipt = signed({"schemaVersion": RECEIPT_SCHEMA, "policyId": INTERACTION_DESIGN_POLICY["policyId"],
        "status": "passed", "sessionId": professional["sessionId"], "stageId": professional["classroomId"],
        "gradeBoundarySha256": generation["gradeBoundarySha256"], "snapshotSha256": quality["snapshotSha256"],
        "planSha256": quality_sha(plan), "teachingQualityReceiptSha256": quality["receiptSha256"],
        "objectives": [{**item, "checks": [{"viewport": v, "sceneSha256": op_hash,
            "screenshotSha256": "a" * 64, "domSha256": "b" * 64, "probeId": f"objective-{item['objectiveIndex']}"}
            for v in QUALITY_VIEWPORTS]} for item in objectives]})
    professional["interactionDesign"] = receipt
    professional = manifest["professionalCreation"] = signed(professional)
    manifest["formalEvidence"]["professionalCreation"].update(interactionDesign=deepcopy(receipt),
        receiptSha256=professional["receiptSha256"])
    manifest["formalEvidence"]["interactionDesign"] = validate_classroom_interaction(professional, generation, classroom)
    manifest["formalEvidence"]["requiredTeachingActions"] = [{"sceneId": scene["id"], "actionId": action["id"]}
        for scene in sorted(scenes, key=lambda value: value["order"]) for action in scene["actions"] if action["type"] == "discussion"]
    manifest["formalEvidence"]["discussionActionCount"] = len(manifest["formalEvidence"]["requiredTeachingActions"])
    return manifest, classroom


class FormalInteractionTest(unittest.TestCase):
    def test_new_policy_and_exact_published_video_target_compatibility(self):
        current = build_preparation_target("primary_1")
        self.assertEqual(current["formalRuntimePolicy"]["professionalCreationPolicy"], MULTISTATE_PROFESSIONAL_POLICY)
        old = deepcopy(current)
        old["formalRuntimePolicy"]["professionalCreationPolicy"] = deepcopy(VIDEO_PROFESSIONAL_POLICY)
        self.assertEqual(preparation_target_fingerprint(old), "e7f3d4be11e40d516d68b793682c67afe6e515b9e18bab1cd12d6649435cc0cc")
        self.assertTrue(compatible_preparation_target(old, current))
        old["formalRuntimePolicy"]["professionalCreationPolicy"]["webSearch"]["enabled"] = False
        self.assertFalse(compatible_preparation_target(old, current))

    def test_final_receipt_passes_without_claiming_student_operation(self):
        manifest, classroom = interaction_fixture()
        professional = manifest["professionalCreation"]
        validate_interaction_manifest(manifest)
        evidence = validate_classroom_interaction(professional, manifest["generationContract"], classroom)
        self.assertNotIn("studentCompleted", evidence)
        self.assertEqual(OpenMaicFullRuntimeClient._professional_creation_receipt_from_payload(professional,
            runtime_request_id=professional["runtimeRequestId"], classroom_id=professional["classroomId"]), professional)

    def test_changed_classroom_and_missing_mapping_fail(self):
        manifest, classroom = interaction_fixture()
        classroom["scenes"][0]["actions"][0]["text"] = "制作后被替换"
        with self.assertRaises(ValueError):
            validate_classroom_interaction(manifest["professionalCreation"], manifest["generationContract"], classroom)
        receipt = deepcopy(manifest["professionalCreation"]["interactionDesign"])
        receipt["objectives"][0]["feedback"]["selector"] = "#quantity"
        with self.assertRaises(ValueError):
            interaction_design_receipt(signed(receipt))

    def test_forged_probe_hash_and_guided_question_cannot_pass_even_after_resigning(self):
        for mutation in (
            lambda r: r["objectives"][0]["checks"][0].update(screenshotSha256="f" * 64),
            lambda r: r["objectives"][0]["independentJudgment"].update(questionId="q2"),
        ):
            manifest, classroom = interaction_fixture()
            pro = manifest["professionalCreation"]
            receipt = pro["interactionDesign"]
            mutation(receipt)
            receipt["planSha256"] = quality_sha({"schemaVersion": PLAN_SCHEMA,
                "objectives": [{k: v for k, v in item.items() if k != "checks"} for item in receipt["objectives"]]})
            pro["interactionDesign"] = signed(receipt)
            with self.assertRaises(ValueError):
                validate_classroom_interaction(signed(pro), manifest["generationContract"], classroom)

    def test_old_policy_does_not_require_new_receipt(self):
        row, classroom = adaptive_quality_fixture()
        manifest = row["feature_manifest_json"]
        self.assertIsNone(validate_classroom_interaction(manifest["professionalCreation"], manifest["generationContract"], classroom))
        validate_interaction_manifest(manifest)


if __name__ == "__main__":
    unittest.main()
