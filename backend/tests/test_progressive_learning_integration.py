"""Focused boundary tests; no live DB, Provider, or publication calls."""
from contextlib import contextmanager
from copy import deepcopy
import json
import unittest
from unittest.mock import Mock, patch

from core.errors import ApiError
from repositories.learning_repository import LearningRepository
from schemas.learning import question_payload
from services.learning_catalog_release_service import LearningCatalogReleaseService
from services.learning_question_evaluator import LearningQuestionEvaluator
from services.learning_service import LearningService
from services.student_learning_service import StudentLearningService
from services.progressive_learning_service import _question_fingerprint


class ProgressiveIntegrationTest(unittest.TestCase):
    def test_cosmetic_option_and_object_ids_cannot_create_new_mastery_evidence(self):
        first = {"id": "q1", "type": "single_choice", "prompt": "选出圆形",
                 "choices": [{"id": "a", "label": "圆形"}, {"id": "b", "label": "方形"}], "answer": "a"}
        renamed = {**first, "id": "new-q", "choices": [{"id": "x", "label": "方形"},
                     {"id": "y", "label": "圆形", "providerTrace": "new"}], "answer": "y"}
        self.assertEqual(_question_fingerprint(first), _question_fingerprint(renamed))
        objects = {"type": "tap_objects", "prompt": "点一点", "objects": [
            {"id": "a", "shape": "circle", "color": "red"}, {"id": "b", "shape": "square", "color": "blue"}]}
        reordered = {**objects, "objects": [{**objects["objects"][1], "id": "new1"},
                                             {**objects["objects"][0], "id": "new2"}]}
        self.assertEqual(_question_fingerprint(objects), _question_fingerprint(reordered))

    def test_student_path_cannot_read_another_child(self):
        service = object.__new__(StudentLearningService)
        context = {"principal": {"child_id": "own-child"}}
        service.student_auth_service = Mock()
        service.student_auth_service.authenticate.return_value = context
        service.learning_service = Mock()
        service._auth_adapter = Mock()
        @contextmanager
        def bind(value):
            self.assertEqual(value, context)
            yield
        service._auth_adapter.bind = bind
        service.curriculum_path("student-token", {"subject": "math", "childId": "other", "gradeCode": "primary_6"})
        service.learning_service.curriculum_path.assert_called_once_with("student-token", {
            "subject": "math", "gradeCode": "primary_6", "childId": "own-child"})

    def test_observation_confirmation_rejects_student_identity(self):
        service = object.__new__(LearningService)
        service.auth_service = Mock()
        service.auth_service.authenticate.return_value = {"student": {}, "family": {"id": "f"}}
        with self.assertRaises(ApiError) as caught:
            service.confirm_observed_lesson("student", {})
        self.assertEqual(caught.exception.code, "parent_confirmation_required")

    def test_new_question_order_and_observation_do_not_use_legacy_four_question_gate(self):
        service = object.__new__(LearningService)
        service.repository = Mock()
        service.repository.parse_json = LearningRepository.parse_json
        questions = [{"id": f"q{i}"} for i in range(6)]
        content = {"assessmentMode": "objective", "questions": list(reversed(questions)),
                   "progressiveLesson": {}, "progressiveFlow": [
                       {"phase": "guided" if i == 0 else "independent", "questionId": f"q{i}"}
                       for i in range(6)]}
        course = {"content_json": json.dumps(content)}
        self.assertEqual(service._questions(course), questions)
        content.update(assessmentMode="observed", questions=[], progressiveFlow=[{"phase": "observe"}])
        self.assertEqual(service._questions({"content_json": json.dumps(content)}), [])
        with self.assertRaises(ApiError): service._questions({"content_json": '{"questions":[]}'})

    def test_counting_requires_each_object_once_and_public_contract_has_no_answer(self):
        question = {"id": "count", "type": "tap_objects", "prompt": "点一点，每个只数一次。",
                    "objects": [{"id": "apple", "shape": "circle", "color": "red"},
                                {"id": "ball", "shape": "circle", "color": "blue"}],
                    "answer": ["apple", "ball"]}
        evaluator = LearningQuestionEvaluator()
        self.assertTrue(evaluator.evaluate(question, {"items": ["ball", "apple"]})["correct"])
        for answer in (["apple"], ["apple", "apple"], ["apple", "ball", "unknown"], "2"):
            self.assertFalse(evaluator.evaluate(question, answer)["correct"])
        malformed = deepcopy(question)
        malformed["answer"] = [{}]
        self.assertEqual(evaluator.evaluate(malformed, ["apple"])["status"], "unsupported")
        public = question_payload(question, index=0, attempt_number=1, choice_seed="session")
        self.assertEqual(public["objects"], question["objects"])
        self.assertNotIn("answer", public)

    def test_new_catalog_fixes_lesson_order_and_plans_two_basic_sets(self):
        service = object.__new__(LearningCatalogReleaseService)
        repo = service.repository = Mock()
        conn = Mock()
        @contextmanager
        def transaction(): yield conn
        repo.transaction = transaction
        repo.create_or_get_content_build.return_value = ({"id": "build", "release_id": "release"}, True)
        service._build_payload = Mock(return_value={"ok": True})
        with patch("repositories.learning_curriculum_preparation_repository.LearningCurriculumPreparationRepository") as preparations:
            preparations.return_value.reserve_plan.return_value = ({"id": "plan"}, True)
            result = service.create({"requestId": "progressive-build-test", "curriculumVersion": "mira.primary.progressive.v1",
                                     "lessonIds": ["M1A01.02", "M1A01.01"]})
        self.assertTrue(result["created"])
        self.assertEqual(result["preparationPlanId"], "plan")
        planned = preparations.return_value.reserve_plan.call_args.kwargs
        self.assertTrue(planned["library_owned"])
        self.assertIsNone(planned["family_id"])
        self.assertIsNone(planned["child_id"])
        args = repo.create_or_get_content_build.call_args.kwargs
        target = args["target_spec"]
        self.assertEqual(target["schemaVersion"], "mira.learning.preparation-target.progressive.v1")
        self.assertEqual(target["variantsPerBoundary"], 2)
        self.assertEqual(planned["target"], target)
        self.assertTrue(all(item["difficultyCode"] == "basic" for item in target["courseTargets"]))
        boundaries = repo.sync_boundaries.call_args.kwargs
        self.assertCountEqual([item["skillId"] for item in boundaries["boundaries"]], ["M1A01.01", "M1A01.02"])
        self.assertEqual(
            [item["skillId"] for item in target["courseTargets"]
             if item["skillId"] in {"M1A01.01", "M1A01.02"} and item["variantOrdinal"] == 1],
            ["M1A01.01", "M1A01.02"],
        )
        self.assertFalse(boundaries["retire_missing"])
        queued = [call.args[1] for call in conn.execute.call_args_list
                  if "INSERT INTO learning_course_supply_requests" in call.args[0]]
        self.assertEqual([(row[2], row[3]) for row in queued],
                         [("M1A01.01", 1), ("M1A01.01", 2), ("M1A01.02", 1), ("M1A01.02", 2)])
        repo.create_or_get_build.assert_not_called()

    def test_new_catalog_cannot_inject_old_publication_authority(self):
        service = object.__new__(LearningCatalogReleaseService)
        with self.assertRaises(ApiError):
            service.create({"curriculumVersion": "mira.primary.progressive.v1", "executionMode": "content_only"})

    def test_remedial_access_retains_every_formal_publication_guard(self):
        repository = LearningRepository(Mock())
        child = {"id": "child", "family_id": "family", "grade_code": "primary_6", "grade_selection_revision": 2}
        course = {"id": "progressive_count", "version": "1", "grade_code": "primary_1", "subject": "math",
                  "curriculum_version": "mira.primary.progressive.v1", "node_code": "M1A01.01"}
        conn = Mock()
        conn.execute.return_value.fetchone.side_effect = [child, course, course]
        with patch("services.progressive_learning_service.ProgressiveLearningService.binding_for_course",
                   return_value={"lesson_id": "M1A01.01"}):
            visible = repository.get_progressive_remedial_course(conn, family_id="family", child_id="child",
                grade_code="primary_6", grade_selection_revision=2, course_id=course["id"], course_version="1")
        self.assertEqual(visible, course)
        sql = conn.execute.call_args.args[0]
        self.assertIn("student_audio.asr_passed_count = student_audio.expected_segment_count", sql)
        self.assertIn("student_receipt.publication_status = 'published'", sql)
        self.assertIn("student_pointer.pointer_revision >= 1", sql)
        conn.reset_mock()
        self.assertIsNone(repository.get_progressive_remedial_course(conn, family_id="family", child_id="child",
            grade_code="primary_6", grade_selection_revision=2, course_id="legacy-course", course_version="1"))
        conn.execute.assert_not_called()

    def test_remedial_access_rejects_stale_child_grade(self):
        repository = LearningRepository(Mock())
        conn = Mock()
        conn.execute.return_value.fetchone.return_value = {"grade_code": "primary_5", "grade_selection_revision": 3}
        self.assertIsNone(repository.get_progressive_remedial_course(conn, family_id="family", child_id="child",
            grade_code="primary_6", grade_selection_revision=2, course_id="progressive_count", course_version="1"))
        self.assertEqual(conn.execute.call_count, 1)


if __name__ == "__main__": unittest.main()
