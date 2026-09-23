from contextlib import contextmanager
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch

from content.progressive_curriculum import CURRICULUM_VERSION, all_lessons, lesson_by_id
from core.errors import ApiError
from integrations.openmaic_question_adapter import OpenMaicQuestionAdapter
from services.dynamic_learning_course_generation_service import DynamicLearningCourseGenerationService
from services.learning_curriculum_preparation_contract import build_preparation_target, build_progressive_preparation_target
from services.lesson_package_service import LessonPackageService
from services.lesson_package_validator import LessonPackageValidator, formal_runtime_teaching_brief
from services.progressive_course_generation import (
    BINDING_SCHEMA, COURSE_SCHEMA, INPUT_SCHEMA, OUTPUT_SCHEMA, VERIFY_SCHEMA,
    generation_brief, validate_progressive_course, validate_stored_progressive_course,
)


def candidate_fixture(lesson_id="ZH1A01.01"):
    brief = generation_brief(lesson_id)
    lesson = brief["lesson"]
    knowledge = lesson["introducedKnowledgeIds"]
    flow = [{"phase": "teach", "text": "先观察老师的口形，比较张开与闭合时的样子。", "knowledgeIds": knowledge, "requiresKnowledgeIds": []},
            {"phase": "example", "text": "老师示范张开嘴，再合上嘴。", "knowledgeIds": knowledge, "requiresKnowledgeIds": knowledge}]
    content = {"schemaVersion": COURSE_SCHEMA, "progressiveLesson": brief["binding"],
        "difficultyCode": "basic", "assessmentMode": lesson["assessmentMode"],
        "autoMasteryEligible": lesson["assessmentMode"] == "objective",
        "manualConfirmationRequired": lesson["assessmentMode"] != "objective",
        "estimatedMinutes": 10, "intro": "一起观察口形。", "progressiveFlow": flow, "questions": []}
    answers = {}
    if lesson["assessmentMode"] == "objective":
        for index in range(6):
            question_id = f"q{index + 1}"
            question = {"id": question_id, "type": "single_choice", "prompt": f"观察第{index + 1}次演示：老师正在张开嘴，选哪个描述？",
                "choices": [{"id": "a", "label": "张开"}, {"id": "b", "label": "闭合"}],
                "answer": "a", "hint": "想想刚才看见的变化。", "explanation": "示范中嘴巴张开了。",
                "knowledgeIds": knowledge, "evidence": {"kind": "independent_choice"}}
            content["questions"].append(question)
            flow.append({"phase": "guided" if index == 0 else "independent", "text": "根据看到的口形完成练习。",
                "knowledgeIds": knowledge, "requiresKnowledgeIds": knowledge, "questionId": question_id})
            answers[question_id] = "a"
    else:
        flow.extend([{"phase": "guided", "text": "跟随家长一起练习本课动作。", "knowledgeIds": knowledge, "requiresKnowledgeIds": knowledge},
                     {"phase": "observe", "text": "请家长观察孩子能否独立完成刚才的动作。", "knowledgeIds": knowledge, "requiresKnowledgeIds": knowledge}])
    candidate = {"gradeCode": lesson["gradeCode"], "subject": lesson["subject"], "nodeCode": lesson_id,
                 "title": lesson["title"], "objective": lesson["learningObjectives"][0], "content": content}
    verification = {"requestId": "progressive-test:verify", "lessonId": lesson_id, "binding": brief["binding"],
                    "passed": True, "issues": [], "undeclaredKnowledgeIds": [], "answers": answers}
    return brief, candidate, verification


def stored_fixture(course, report):
    return {"id": course["id"], "version": course["version"], "grade_code": course["gradeCode"],
        "subject": course["subject"], "node_code": course["nodeCode"], "title": course["title"],
        "objective": course["objective"], "content_json": json.dumps(course["content"], ensure_ascii=False),
        "content_origin": "openmaic_generated", "generator": "openmaic", "generation_request_id": "progressive-test",
        "curriculum_version": course["curriculumVersion"], "boundary_version": course["boundaryVersion"],
        "generation_content_hash": report["contentFingerprint"], "status": "validated", "quality_status": "auto_validated"}


class ProgressiveGenerationTest(unittest.TestCase):
    def test_fixed_lesson_brief_has_prerequisite_and_future_knowledge_and_basic_first(self):
        brief = generation_brief("EN1A01.02")
        self.assertEqual(brief["binding"]["schemaVersion"], BINDING_SCHEMA)
        self.assertEqual(brief["binding"]["difficultyCode"], "basic")
        self.assertIn("EN1A01.01", brief["prerequisiteLessonIds"])
        self.assertIn("EN1A01.03", brief["mustNotDependOnKnowledgeIds"])
        with self.assertRaises(ApiError): generation_brief("EN1A01.02", difficulty_code="challenge")

    def test_host_gate_and_fresh_stored_receipt_match_exact_content(self):
        brief, candidate, verification = candidate_fixture()
        course, report = validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")
        row = stored_fixture(course, report)
        self.assertEqual(validate_stored_progressive_course(row, expected_lesson_id=course["nodeCode"], validation_receipt=report), report)
        row["content_json"] = row["content_json"].replace("张开", "闭合")
        with self.assertRaises(ApiError):
            validate_stored_progressive_course(row, expected_lesson_id=course["nodeCode"], validation_receipt=report)

    def test_old_course_cannot_be_relabelled_even_with_new_lesson_content(self):
        brief, candidate, verification = candidate_fixture()
        course, report = validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")
        for field, value in (("curriculum_version", "mira.primary.2026-fall.v1"), ("id", "old-course"),
                             ("generation_request_id", "old-request"), ("node_code", "pinyin_syllables")):
            row = stored_fixture(course, report)
            row[field] = value
            with self.subTest(field=field), self.assertRaises(ApiError):
                validate_stored_progressive_course(row, expected_lesson_id=course["nodeCode"], validation_receipt=report)

    def test_untaught_dependencies_and_future_question_knowledge_are_rejected(self):
        for mutation in ("future", "practice_before_teach", "missing_teach", "duplicate_independent"):
            brief, candidate, verification = candidate_fixture()
            content = candidate["content"]
            if mutation == "future": content["questions"][0]["knowledgeIds"] = ["ZH1A01.02"]
            elif mutation == "practice_before_teach": content["progressiveFlow"].reverse()
            elif mutation == "missing_teach": content["progressiveFlow"][0]["phase"] = "example"
            else: content["questions"][2]["prompt"] = content["questions"][1]["prompt"]
            with self.subTest(mutation=mutation), self.assertRaises(ApiError):
                validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")

    def test_independent_solver_disagreement_and_unknown_evidence_fail_closed(self):
        brief, candidate, verification = candidate_fixture()
        verification["answers"]["q1"] = "b"
        with self.assertRaises(ApiError): validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")
        verification["answers"]["q1"] = "a"
        candidate["content"]["questions"][0]["evidence"]["kind"] = "model_says_correct"
        with self.assertRaises(ApiError): validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")

    def test_observed_lesson_cannot_have_questions_or_automatic_mastery(self):
        observed = next(item["lessonId"] for item in all_lessons() if item["assessmentMode"] == "observed")
        brief, candidate, verification = candidate_fixture(observed)
        _, report = validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")
        self.assertFalse(report["autoMasteryEligible"])
        candidate["content"]["autoMasteryEligible"] = True
        with self.assertRaises(ApiError): validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")

    def test_new_english_present_scope_rejects_went_and_did(self):
        lesson = next(item for item in all_lessons() if item["subject"] == "english"
            and item["assessmentMode"] == "objective" and "simple_present" in item["constraints"]["allowedGrammarCodes"]
            and "simple_past" not in item["constraints"]["allowedGrammarCodes"]
            and "independent_choice" in item["constraints"]["assessmentEvidenceKinds"])
        for text in ("I went home.", "Did he play?", "Yesterday was sunny."):
            brief, candidate, verification = candidate_fixture(lesson["lessonId"])
            candidate["content"]["progressiveFlow"][0]["text"] = text
            with self.subTest(text=text), self.assertRaises(ApiError) as error:
                validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")
            self.assertEqual(error.exception.code, "progressive_future_grammar")

    def test_new_target_preserves_runtime_and_audio_contracts_and_old_target_is_unchanged(self):
        for grade in range(1, 7):
            old = build_preparation_target(f"primary_{grade}")
            new = build_progressive_preparation_target(f"primary_{grade}")
            self.assertEqual(new["curriculumVersion"], CURRICULUM_VERSION)
            self.assertGreater(new["totalCourseCount"], old["boundaryCount"])
            self.assertEqual(new["formalAudioContracts"], old["formalAudioContracts"])
            self.assertIn("formal-runtime-teaching-brief.progressive.v1", new["fullRuntimeContractVersion"])
            self.assertTrue(all(item["difficultyCode"] == "basic" and item["variantOrdinal"] in {1, 2} for item in new["courseTargets"]))
            self.assertEqual(build_preparation_target(f"primary_{grade}"), old)

    def test_existing_dynamic_entry_runs_new_sidecar_and_persists_host_receipt_without_paid_calls(self):
        brief, candidate, verification = candidate_fixture()
        owner = object.__new__(DynamicLearningCourseGenerationService)
        owner.adapter = OpenMaicQuestionAdapter(fake_mode=True,
            generation_fake_responses=[json.dumps({"candidateCourse": candidate})],
            verification_fake_responses=[json.dumps({"verification": verification})])
        repo = Mock()
        @contextmanager
        def transaction():
            conn = Mock()
            conn.execute.return_value.fetchall.return_value = []
            yield conn
        repo.transaction.side_effect = transaction
        repo.create_or_get_job.return_value = ({"id": "job"}, True)
        repo.create_or_get_candidate.return_value = ({"id": "candidate"}, True)
        expected_course, report = validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")
        repo.stage_candidate.return_value = (stored_fixture(expected_course, report), True)
        owner.repository = repo
        owner.classroom_enqueue = Mock()
        result = owner.generate({"requestId": "progressive-test", "curriculumVersion": CURRICULUM_VERSION,
                                 "lessonId": "ZH1A01.01", "difficultyCode": "basic"}, enqueue_classroom=False)
        self.assertTrue(result.payload["ok"], result.payload)
        self.assertEqual(result.payload["status"], "validated")
        self.assertEqual(repo.create_or_get_job.call_args.kwargs["node_code"], "ZH1A01.01")
        self.assertEqual(repo.mark_candidate_validated.call_args.kwargs["validation"], report)
        owner.classroom_enqueue.assert_not_called()

    def test_tap_objects_counts_actual_shapes_without_reading_written_numbers(self):
        brief, candidate, verification = candidate_fixture("M1A01.01")
        for question in candidate["content"]["questions"]:
            question.update(type="tap_objects", prompt=f"请依次点一下这组物体。{question['id']}",
                objects=[{"id": "object-a", "shape": "circle", "color": "blue"}],
                answer=["object-a"], evidence={"kind": "count_objects"})
            question.pop("choices")
            verification["answers"][question["id"]] = ["object-a"]
        course, report = validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")
        row = stored_fixture(course, report)
        projected = LessonPackageService._public_practice_questions(row)
        self.assertEqual(projected[0]["objects"], [{"id": "object-a", "shape": "circle", "color": "blue"}])
        self.assertNotIn("answer", projected[0])
        candidate["content"]["questions"][0]["objects"].append({"id": "object-b", "shape": "square", "color": "red"})
        candidate["content"]["questions"][0]["answer"] = ["object-a", "object-b"]
        with self.assertRaises(ApiError): validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")

    def test_new_course_prepares_formal_runtime_candidate_package_with_no_answer_leak(self):
        brief, candidate, verification = candidate_fixture()
        course, receipt = validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")
        row = stored_fixture(course, receipt)
        teaching_brief, teaching_hash, source_hash = formal_runtime_teaching_brief(row)
        self.assertEqual(teaching_brief["schemaVersion"], "mira.learning.formal-runtime-teaching-brief.progressive.v1")
        self.assertEqual(len(teaching_brief["lesson"]["questions"]), 6)
        self.assertEqual(len(teaching_brief["lesson"]["teachingFlow"]["independentQuestionIds"]), 5)
        self.assertNotIn('"answer":', json.dumps(teaching_brief))
        self.assertNotIn('"evidence":', json.dumps(teaching_brief))
        self.assertEqual(LessonPackageService._boundary(row)["skillId"], row["node_code"])
        service = object.__new__(LessonPackageService)
        service.repository = Mock()
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = {"validation_json": json.dumps(receipt),
            "request_id": "progressive-test", "curriculum_version": CURRICULUM_VERSION,
            "prompt_version": "mira.learning.progressive-generation.v1"}
        @contextmanager
        def transaction(): yield conn
        service.repository.transaction.side_effect = transaction
        service.repository.decode_json.side_effect = lambda value: json.loads(value) if isinstance(value, str) else value
        service.repository.encode_json.side_effect = lambda value: json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        target = build_progressive_preparation_target("primary_1", lesson_ids=[row["node_code"]])
        authority = {**row, "build_item_id": "progressive-item", "course_id": row["id"],
            "course_version": row["version"], "attempt_ordinal": 1, "target_spec_json": json.dumps(target)}
        service.repository.get_next_formal_candidate_authority.return_value = authority
        service.repository.get_course.return_value = row
        service.repository.reserve_formal_runtime_package.return_value = ({"id": "new-package", "version": 1, "status": "candidate"}, True)
        service.validator = LessonPackageValidator()
        runtime = Mock()
        runtime.issue_candidate_generation.return_value = {"runtime": {"status": "pending"}}
        result = service.process_next_formal_candidate(runtime, preparation_plan=target)
        self.assertTrue(result.payload["ok"])
        reserved = service.repository.reserve_formal_runtime_package.call_args.kwargs["public_payload"]
        self.assertFalse(reserved["studentLaunchEligible"])
        self.assertEqual(reserved["teachingBrief"], teaching_brief)
        self.assertEqual(reserved["teachingBriefSha256"], teaching_hash)
        self.assertEqual(reserved["sourceCourseContentSha256"], source_hash)
        runtime.issue_candidate_generation.assert_called_once()

    def test_observed_brief_has_manual_observation_and_no_scored_questions(self):
        lesson_id = next(item["lessonId"] for item in all_lessons() if item["assessmentMode"] == "observed")
        brief, candidate, verification = candidate_fixture(lesson_id)
        course, receipt = validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")
        projected = formal_runtime_teaching_brief(stored_fixture(course, receipt))[0]
        self.assertEqual(projected["lesson"]["questions"], [])
        self.assertEqual(projected["lesson"]["teachingFlow"]["independentQuestionIds"], [])
        self.assertTrue(projected["lesson"]["manualConfirmationRequired"])
        self.assertTrue(projected["lesson"]["teachingFlow"]["observations"])


if __name__ == "__main__": unittest.main()
