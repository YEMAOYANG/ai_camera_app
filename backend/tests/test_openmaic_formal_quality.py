from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import unittest

from integrations.openmaic_formal_media import PROFESSIONAL_POLICY, generation_options, validate_media_manifest
from integrations.openmaic_formal_pedagogy import registered_grade_boundary
from integrations.openmaic_formal_quality import (
    QUALITY_DIMENSIONS, QUALITY_VIEWPORTS, quality_sha, quality_snapshot, quality_scene_text,
    teaching_quality_receipt, validate_classroom_quality, validate_quality_manifest, quality_canonical_json,
)
from integrations.openmaic_formal_skill_selection import select_formal_skills
from integrations.openmaic_formal_skills import validate_classroom_skills, validate_skill_manifest
from integrations.openmaic_full_runtime_client import OpenMaicFullRuntimeClient, OpenMaicFullRuntimeError
from services.openmaic_full_runtime_service import OpenMaicFullRuntimeService, OpenMaicRuntimeServiceError
from repositories.formal_student_runtime_gate import current_formal_runtime_sql
from tests.test_openmaic_formal_skills import integrated_row
from tests.test_formal_student_runtime_launch import _with_receipt_sha256
from tests import test_formal_student_runtime_launch as launch_fixtures


def adaptive_quality_fixture():
    row = integrated_row()
    manifest = row["feature_manifest_json"]
    generation = manifest["generationContract"]
    boundary = registered_grade_boundary(grade_code="primary_2", subject="math", skill_id="number_operations_100")
    row.update(course_node_code=boundary["skillId"], course_curriculum_version=boundary["curriculumVersion"],
               course_boundary_version=boundary["boundaryVersion"])
    generation.update(professionalCreationPolicy=deepcopy(PROFESSIONAL_POLICY), generation=generation_options(PROFESSIONAL_POLICY),
                      gradeBoundary=boundary, gradeBoundarySha256=quality_sha(boundary))
    brief = generation["teachingBrief"]
    brief["course"].update(skillId=boundary["skillId"], objective="；".join(boundary["learningObjectives"]))
    brief["lesson"]["teachingFlow"]["teach"].update(sayText="十个一是一个十。请比较不同数量。", keyPoints=["十个一是一个十"])
    for question in brief["lesson"]["questions"]:
        question.update(type="single_choice", skill=boundary["skillId"],
                        choices=[{"id": "a", "label": "11"}, {"id": "b", "label": "12"}])
    brief_hash = quality_sha(brief)
    generation["teachingBriefSha256"] = manifest["teachingBriefSha256"] = brief_hash
    plan = select_formal_skills(teaching_brief=brief, grade_boundary=boundary, grade_boundary_sha256=quality_sha(boundary))
    scenes = []
    types = ["slide"] * 5 + ["quiz"] * 2 + ["interactive"] * 3
    for index, kind in enumerate(types):
        content = {"text": "十个一是一个十。请比较不同数量。"}
        if kind == "interactive":
            content["html"] = '<div style="width:1000px">十个一是一个十</div>'
        if kind == "quiz":
            ids = ("q2", "q3") if index == 5 else ("q4", "q5")
            content["questions"] = [{"id": q["id"], "question": q["prompt"], "type": "single",
                "hasAnswer": False, "options": [{"value": c["id"], "label": c["label"]} for c in q["choices"]]}
                for q in brief["lesson"]["questions"] if q["id"] in ids]
        scenes.append({"id": f"formal-scene-{index + 1}", "type": kind, "title": f"第{index + 1}页",
            "order": index, "content": content,
            "actions": [{"id": f"speech-{index + 1}", "type": "speech", "text": "十个一是一个十。请比较不同数量。"}]})
    classroom = {"stage": {"id": "classroom-1", "name": "两位数学习"}, "scenes": scenes}
    contexts = [{"sceneId": s["id"], "sceneType": s["type"], "contentContextSha256": "a" * 64,
                 "actionsContextSha256": "b" * 64} for s in scenes]
    professional = manifest["professionalCreation"]
    skill = _with_receipt_sha256({"schemaVersion": "mira.openmaic.skill-orchestration-receipt.v2",
        "profileId": "mira-primary-adaptive.v2", "status": "succeeded", "selectionPlan": plan,
        "skillReads": [{"skillId": skill_id, "sourceHash": "c" * 64} for skill_id in plan["selectedSkillIds"]],
        "referenceReads": professional["skillOrchestration"]["referenceReads"], "sceneContexts": contexts})
    professional.update(skillOrchestration=skill, teachingBriefSha256=brief_hash)
    snapshot = quality_snapshot(classroom)
    scene_hashes = [{"sceneId": s["id"], "sceneSha256": quality_sha(s)} for s in snapshot["scenes"]]
    checks = [{**scene_hash, "viewport": deepcopy(viewport), "screenshotSha256": "a" * 64,
               "domSha256": "b" * 64, "passed": True, "probeCount": 1 if types[index] == "interactive" else 0}
              for index, scene_hash in enumerate(scene_hashes) for viewport in QUALITY_VIEWPORTS]
    identity = {"snapshotSha256": quality_sha(snapshot), "gradeBoundarySha256": quality_sha(boundary),
                "selectionPlanSha256": plan["planSha256"], "teachingBriefSha256": brief_hash, "renderChecks": checks}
    citation = [{"sceneId": scenes[0]["id"], "quote": "十个一是一个十"}]
    quality = _with_receipt_sha256({"schemaVersion": "mira.openmaic.teaching-quality-receipt.v1",
        "policyId": "mira-primary-quality.v1", "status": "passed", "sessionId": professional["sessionId"],
        "stageId": professional["classroomId"], **identity, "sceneHashes": scene_hashes,
        "review": {"providerId": "deepseek", "modelId": "deepseek-v4-flash", "requestIdHash": "f" * 64,
            "inputSha256": quality_sha(identity),
            "dimensions": [{"id": key, "passed": True, "evidence": deepcopy(citation)} for key in QUALITY_DIMENSIONS],
            "objectives": [{"objectiveIndex": i, "evidence": deepcopy(citation)} for i in range(len(boundary["learningObjectives"]))]}})
    professional["teachingQuality"] = quality
    professional.pop("receiptSha256")
    professional = manifest["professionalCreation"] = _with_receipt_sha256(professional)
    evidence = manifest["formalEvidence"]
    evidence["professionalCreation"].update(skillOrchestration=deepcopy(skill), teachingQuality=deepcopy(quality),
                                           receiptSha256=professional["receiptSha256"])
    evidence["runtimeEventAuthority"]["scenes"] = [{"sceneIndex": i, "sceneId": s["id"],
        "completionActionId": s["actions"][-1]["id"],
        "questionIds": [q["id"] for q in s["content"].get("questions", [])]}
        for i, s in enumerate(scenes)]
    evidence["assessmentQuestionIds"] = ["q2", "q3", "q4", "q5"]
    evidence["teachingQuality"] = validate_classroom_quality(professional, generation, classroom)
    return row, classroom


def rehash_quality(professional):
    receipt = professional["teachingQuality"]
    receipt["review"]["inputSha256"] = quality_sha({key: receipt[key] for key in (
        "snapshotSha256", "gradeBoundarySha256", "selectionPlanSha256", "teachingBriefSha256", "renderChecks")})
    receipt.pop("receiptSha256")
    professional["teachingQuality"] = _with_receipt_sha256(receipt)
    professional.pop("receiptSha256")
    return _with_receipt_sha256(professional)


class OpenMaicFormalQualityTest(unittest.TestCase):
    def test_runtime_cross_language_snapshot_text_and_review_hashes_remain_exact(self):
        fixture = json.loads(Path(__file__).with_name("fixtures").joinpath("mira_formal_quality_cross_language.json").read_text())
        snapshot = quality_snapshot(fixture["classroom"])
        expected = fixture["expected"]
        self.assertEqual(snapshot, expected["snapshot"])
        self.assertEqual(quality_canonical_json(snapshot), expected["canonicalSnapshot"])
        self.assertEqual(quality_sha(snapshot), expected["snapshotSha256"])
        self.assertEqual([{"sceneId": s["id"], "sceneSha256": quality_sha(s)} for s in snapshot["scenes"]], expected["sceneHashes"])
        self.assertEqual({s["id"]: quality_scene_text(s) for s in snapshot["scenes"]}, expected["sceneTexts"])
        self.assertEqual(quality_sha(fixture["reviewIdentity"]), expected["reviewInputSha256"])

    def test_quality_numbers_use_json_stringify_format_without_touching_old_hashes(self):
        for value, expected in ((120.0, "120"), (-0.0, "0"), (1e-7, "1e-7"), (1e-6, "0.000001"),
                                (1e20, "100000000000000000000"), (1e21, "1e+21"),
                                (1.0000000000000001e18, "1000000000000000100"), (1/3, "0.3333333333333333")):
            with self.subTest(value=value):
                self.assertEqual(quality_canonical_json(value), expected)
        for value in (float("nan"), float("inf"), float("-inf")):
            with self.assertRaises(ValueError):
                quality_sha(value)

    def test_final_classroom_review_and_v2_receipts_pass_without_mutation(self):
        row, classroom = adaptive_quality_fixture()
        manifest = row["feature_manifest_json"]
        original = deepcopy(manifest)
        professional, generation = manifest["professionalCreation"], manifest["generationContract"]
        self.assertEqual(OpenMaicFullRuntimeClient._professional_creation_receipt_from_payload(professional,
            runtime_request_id=professional["runtimeRequestId"], classroom_id=professional["classroomId"]), professional)
        validate_classroom_skills(professional, generation, classroom)
        validate_skill_manifest(manifest)
        validate_quality_manifest(manifest)
        validate_media_manifest(manifest)
        self.assertEqual(validate_classroom_quality(professional, generation, classroom), manifest["formalEvidence"]["teachingQuality"])
        self.assertEqual(manifest, original)

    def test_adaptive_student_launch_accepts_exact_evidence(self):
        row, _ = adaptive_quality_fixture()
        service = launch_fixtures.FormalStudentRuntimeLaunchTest()._service(row)
        self.assertTrue(service.create_student_launch("student-token", "session-1")["ok"])

    def test_audio_promotion_preserves_snapshot_but_teaching_edits_invalidate_it(self):
        row, classroom = adaptive_quality_fixture()
        snapshot = quality_snapshot(classroom)
        promoted = deepcopy(classroom)
        promoted["scenes"][0]["actions"][0].update(audioUrl="/audio.wav", audioSrc="x", audio={"url": "x"},
            audioDuration=3.5, duration=3500, ttsProvider="qwen", ttsModel="model")
        self.assertEqual(quality_snapshot(promoted), snapshot)
        manifest = row["feature_manifest_json"]
        validate_classroom_quality(manifest["professionalCreation"], manifest["generationContract"], promoted)
        for mutate in (lambda c: c["scenes"][0]["actions"][0].update(text="替换后的错误讲解"),
                       lambda c: c["scenes"][0]["content"].update(text="错图"),
                       lambda c: c["scenes"][-1]["content"].update(html="<p>改变交互</p>"),
                       lambda c: c["stage"].update(name="换了教学场景")):
            altered = deepcopy(promoted)
            mutate(altered)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                validate_classroom_quality(manifest["professionalCreation"], manifest["generationContract"], altered)

    def test_scene_projection_preserves_other_action_durations_and_string_order(self):
        _, classroom = adaptive_quality_fixture()
        classroom["scenes"][0]["actions"].append({"id": "wait-1", "type": "wait", "duration": 500})
        projected = quality_snapshot(classroom)["scenes"][0]
        self.assertEqual(projected["actions"][-1]["duration"], 500)
        self.assertIn("十个一是一个十", quality_scene_text(projected))

    def test_malformed_quality_receipts_fail_even_after_hashes_are_recomputed(self):
        row, _ = adaptive_quality_fixture()
        original = row["feature_manifest_json"]["professionalCreation"]
        mutations = (
            lambda q: q.update(status="failed"), lambda q: q.update(snapshotSha256="x"),
            lambda q: q["sceneHashes"].append(deepcopy(q["sceneHashes"][0])),
            lambda q: q["renderChecks"].pop(), lambda q: q["renderChecks"].reverse(),
            lambda q: q["renderChecks"][0].update(passed=1),
            lambda q: q["renderChecks"][0].update(probeCount=True),
            lambda q: q["renderChecks"][0].update(viewport={"width": 720, "height": 1280}),
            lambda q: q["review"].update(modelId="generator-model"),
            lambda q: q["review"]["dimensions"].pop(),
            lambda q: q["review"]["dimensions"][0].update(passed=False),
            lambda q: q["review"]["dimensions"][1].update(id="grade_fit"),
            lambda q: q["review"]["dimensions"][0]["evidence"][0].update(sceneId="unrelated-scene"),
            lambda q: q["review"]["objectives"][0].update(objectiveIndex=True),
        )
        for mutation in mutations:
            professional = deepcopy(original)
            mutation(professional["teachingQuality"])
            professional = rehash_quality(professional)
            with self.subTest(mutation=mutation), self.assertRaises(ValueError):
                teaching_quality_receipt(professional["teachingQuality"])

    def test_actual_payload_rejects_fabricated_quotes_missing_objective_and_dead_probe(self):
        row, classroom = adaptive_quality_fixture()
        manifest = row["feature_manifest_json"]
        for mutate in (
            lambda p: p["teachingQuality"]["review"]["dimensions"][0]["evidence"][0].update(quote="页面根本没有这句证明"),
            lambda p: p["teachingQuality"]["review"]["objectives"].pop(),
            lambda p: p["teachingQuality"]["renderChecks"][-1].update(probeCount=0),
            lambda p: p["teachingQuality"].update(selectionPlanSha256="b" * 64),
            lambda p: p["teachingQuality"].update(gradeBoundarySha256="b" * 64),
        ):
            professional = deepcopy(manifest["professionalCreation"])
            mutate(professional)
            professional = rehash_quality(professional)
            with self.subTest(mutation=mutate), self.assertRaises(ValueError):
                validate_classroom_quality(professional, manifest["generationContract"], classroom)

    def test_v2_plan_recomputed_instead_of_trusting_selection_reasons(self):
        row, classroom = adaptive_quality_fixture()
        manifest = row["feature_manifest_json"]
        pro = deepcopy(manifest["professionalCreation"])
        skill = pro["skillOrchestration"]
        plan = skill["selectionPlan"]
        plan["decisions"][0]["reasonCode"] = "generator_said_so"
        plan.pop("planSha256")
        plan = skill["selectionPlan"] = {**plan, "planSha256": quality_sha(plan)}
        skill.pop("receiptSha256")
        pro["skillOrchestration"] = _with_receipt_sha256(skill)
        pro["teachingQuality"]["selectionPlanSha256"] = plan["planSha256"]
        pro = rehash_quality(pro)
        with self.assertRaises(ValueError):
            validate_classroom_skills(pro, manifest["generationContract"], classroom)

    def test_locked_final_four_questions_reject_replacement_or_answer_leak(self):
        row, classroom = adaptive_quality_fixture()
        service = object.__new__(OpenMaicFullRuntimeService)
        generation = row["feature_manifest_json"]["generationContract"]
        service._validate_locked_formal_assessment(classroom, generation)
        for mutate in (lambda q: q.update(question="换成了更难的题目"), lambda q: q.update(id="new-question"),
                       lambda q: q.update(type="multiple"), lambda q: q["options"][0].update(label="换了选项"),
                       lambda q: q.update(hasAnswer=True, answer=["a"]), lambda q: q.update(evaluation={"answer": "a"})):
            bad = deepcopy(classroom)
            mutate(bad["scenes"][5]["content"]["questions"][0])
            with self.subTest(mutation=mutate), self.assertRaises(OpenMaicRuntimeServiceError):
                service._validate_locked_formal_assessment(bad, generation)

    def test_launch_refuses_missing_or_mismatched_quality_and_boundary_copies(self):
        for mutate in (lambda m: m["professionalCreation"].pop("teachingQuality"),
                       lambda m: m["formalEvidence"].pop("teachingQuality"),
                       lambda m: m["formalEvidence"]["teachingQuality"].update(snapshotSha256="f" * 64),
                       lambda m: m["formalEvidence"]["professionalCreation"].pop("teachingQuality"),
                       lambda m: m["generationContract"]["gradeBoundary"].update(gradeCode="primary_6"),
                       lambda m: m["formalEvidence"].update(assessmentQuestionIds=["q2", "q3", "q4", "replacement"])):
            row, _ = adaptive_quality_fixture()
            mutate(row["feature_manifest_json"])
            service = launch_fixtures.FormalStudentRuntimeLaunchTest()._service(row)
            with self.subTest(mutation=mutate), self.assertRaises(OpenMaicRuntimeServiceError):
                service.create_student_launch("student-token", "session-1")

    def test_sql_keeps_v1_and_requires_new_policy_quality_shape(self):
        sql = current_formal_runtime_sql(runtime_alias="runtime")
        for expected in ("mira-primary-integrated.v1", "mira-primary-adaptive.v2", "teachingQuality.renderChecks",
                         "teachingQuality.snapshotSha256", "teachingQuality.review.objectives", "selectionPlan.decisions"):
            self.assertIn(expected, sql)


if __name__ == "__main__":
    unittest.main()
