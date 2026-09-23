"""Frozen progressive lesson -> native runtime contracts, with no Provider calls."""
from copy import deepcopy
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from content.progressive_curriculum import CURRICULUM_VERSION, all_lessons
from content.primary_skill_boundaries import PRIMARY_SKILL_BOUNDARIES
from integrations.openmaic_formal_media import PROFESSIONAL_POLICY, PLAYFUL_PROFESSIONAL_POLICY, canonical_sha256
from integrations.openmaic_formal_pedagogy import grade_boundary_fields, registered_grade_boundary, validate_generation_grade_boundary
from integrations.openmaic_formal_playful import playful_quality_context
from services.openmaic_full_runtime_service import OpenMaicFullRuntimeService, OpenMaicRuntimeServiceError, _validate_quiz_content
from services.progressive_course_generation import progressive_runtime_teaching_brief, validate_progressive_course
from repositories.openmaic_runtime_repository import OpenMaicRuntimeRepository
from tests.test_progressive_course_generation import candidate_fixture, stored_fixture
from tests.test_formal_runtime_candidate_generation import TEACHING_BRIEF


def generation_fixture(*, observed=False, tap=False):
    lesson_id = next(item["lessonId"] for item in all_lessons() if item["assessmentMode"] == "observed") if observed else ("M1A01.01" if tap else "ZH1A01.01")
    brief, candidate, verification = candidate_fixture(lesson_id)
    if tap:
        for question in candidate["content"]["questions"]:
            question.update(type="tap_objects", prompt=f"请点一下这组物体。{question['id']}",
                objects=[{"id": "object-a", "shape": "circle", "color": "blue"}],
                answer=["object-a"], evidence={"kind": "count_objects"})
            question.pop("choices")
            verification["answers"][question["id"]] = ["object-a"]
    course, report = validate_progressive_course(candidate, brief=brief, verification=verification, request_id="progressive-test")
    row = stored_fixture(course, report)
    public, digest, _source = progressive_runtime_teaching_brief(row)
    return row, {"professionalCreationPolicy": deepcopy(PLAYFUL_PROFESSIONAL_POLICY),
        "teachingBrief": public, "teachingBriefSha256": digest,
        **grade_boundary_fields(row, PLAYFUL_PROFESSIONAL_POLICY)}


def classroom_for(expected):
    return {"scenes": [{"order": 0, "type": "quiz", "content": {"questions": [
        {"id": item["id"], "question": item["question"], "type": item["runtimeType"],
         "options": deepcopy(item["options"]), "hasAnswer": False,
         **({"sourceType": item["sourceType"], "objects": deepcopy(item["objects"])} if "objects" in item else {})}
        for item in expected]}}]}


class ProgressiveRuntimeContractTest(unittest.TestCase):
    def setUp(self):
        self.service = object.__new__(OpenMaicFullRuntimeService)

    def test_actual_new_candidate_projects_six_exact_answer_blind_questions(self):
        row, generation = generation_fixture()
        before = deepcopy(generation)
        expected = self.service._formal_runtime_assessment_contract(generation)
        self.assertEqual(len(expected), 6)
        self.assertEqual([item["id"] for item in expected], [f"q{i}" for i in range(1, 7)])
        self.assertTrue(all(set(item) == {"id", "question", "runtimeType", "options"} for item in expected))
        self.service._validate_locked_formal_assessment(classroom_for(expected), generation)
        self.assertEqual(validate_generation_grade_boundary(generation, row)["gradeBoundary"]["skillId"], "ZH1A01.01")
        context = playful_quality_context(generation)
        self.assertEqual(context["independentQuestionIds"], [f"q{i}" for i in range(2, 7)])
        self.assertEqual(context["assessmentMode"], "objective")
        self.assertEqual(generation, before)

    def test_frozen_binding_private_answers_and_wrong_question_counts_fail_closed(self):
        for mutation in (lambda g: g["teachingBrief"]["progressiveLesson"].update(lessonId="ZH1A01.02"),
                         lambda g: g["teachingBrief"]["lesson"]["questions"][0].update(answer="a"),
                         lambda g: g["teachingBrief"]["lesson"]["questions"][0].update(evidence={"kind": "independent_choice"}),
                         lambda g: g["teachingBrief"]["lesson"]["teachingFlow"]["independentQuestionIds"].pop(),
                         lambda g: g["teachingBrief"]["lesson"]["teachingFlow"].update(demoQuestionId="q1"),
                         lambda g: g["teachingBrief"]["lesson"].update(autoMasteryEligible=False)):
            _, generation = generation_fixture()
            mutation(generation)
            generation["teachingBriefSha256"] = canonical_sha256(generation["teachingBrief"])
            with self.subTest(mutation=mutation), self.assertRaises(OpenMaicRuntimeServiceError):
                self.service._formal_runtime_assessment_contract(generation)
        _, generation = generation_fixture()
        generation["teachingBriefSha256"] = "0" * 64
        with self.assertRaises(OpenMaicRuntimeServiceError): self.service._formal_runtime_assessment_contract(generation)

    def test_observed_course_has_zero_assessment_and_no_automatic_promotion(self):
        row, generation = generation_fixture(observed=True)
        self.assertEqual(self.service._formal_runtime_assessment_contract(generation), [])
        self.service._validate_locked_formal_assessment({"scenes": []}, generation)
        self.assertEqual(playful_quality_context(generation)["independentQuestionIds"], [])
        self.assertTrue(playful_quality_context(generation)["manualConfirmationRequired"])
        validate_generation_grade_boundary(generation, row)
        with self.assertRaises(OpenMaicRuntimeServiceError):
            self.service._validate_locked_formal_assessment(classroom_for([{"id": "invented", "question": "题目", "runtimeType": "short_answer", "options": []}]), generation)
        generation["teachingBrief"]["lesson"]["autoMasteryEligible"] = True
        generation["teachingBriefSha256"] = canonical_sha256(generation["teachingBrief"])
        with self.assertRaises(OpenMaicRuntimeServiceError): self.service._formal_runtime_assessment_contract(generation)
        with self.assertRaises(ValueError): playful_quality_context(generation)

    def test_tap_objects_preserves_visuals_without_number_reading_or_answer_leak(self):
        _, generation = generation_fixture(tap=True)
        expected = self.service._formal_runtime_assessment_contract(generation)
        self.assertEqual(expected[0]["options"], [{"value": "object-a", "label": "●"}])
        self.assertEqual(expected[0]["objects"], [{"id": "object-a", "shape": "circle", "color": "blue"}])
        classroom = classroom_for(expected)
        self.assertEqual(_validate_quiz_content(classroom["scenes"][0]["content"], fail=self.service._fail), 6)
        self.service._validate_locked_formal_assessment(classroom, generation)
        classroom["scenes"][0]["content"]["questions"][0]["objects"][0]["color"] = "red"
        with self.assertRaises(OpenMaicRuntimeServiceError): self.service._validate_locked_formal_assessment(classroom, generation)
        question = classroom_for(expected)["scenes"][0]["content"]["questions"][0]
        question.pop("sourceType")
        question.pop("objects")
        with self.assertRaises(OpenMaicRuntimeServiceError): _validate_quiz_content({"questions": [question]}, fail=self.service._fail)

    def test_tap_objects_rejects_unsupported_shape_color_and_higher_count(self):
        for change in (lambda q: q["objects"][0].update(shape="star"),
                       lambda q: q["objects"][0].update(color="#abcdef"),
                       lambda q: q["objects"].append({"id": "second", "shape": "square", "color": "red"})):
            _, generation = generation_fixture(tap=True)
            change(generation["teachingBrief"]["lesson"]["questions"][0])
            generation["teachingBriefSha256"] = canonical_sha256(generation["teachingBrief"])
            with self.subTest(change=change), self.assertRaises(OpenMaicRuntimeServiceError): self.service._formal_runtime_assessment_contract(generation)

    def test_all_new_boundaries_use_registry_and_same_bounded_legacy_shape(self):
        keys = set(PRIMARY_SKILL_BOUNDARIES[0].to_catalog_payload())
        for lesson in all_lessons():
            boundary = registered_grade_boundary(grade_code=lesson["gradeCode"], subject=lesson["subject"], skill_id=lesson["lessonId"])
            self.assertEqual(set(boundary), keys)
            self.assertEqual(boundary["curriculumVersion"], CURRICULUM_VERSION)
            self.assertEqual(boundary["prerequisiteSkills"], lesson["prerequisiteLessonIds"])
            self.assertLessEqual(len(boundary["excludedContent"]), 50)
        for boundary in PRIMARY_SKILL_BOUNDARIES:
            self.assertEqual(registered_grade_boundary(grade_code=boundary.grade_code, subject=boundary.subject, skill_id=boundary.skill_id), boundary.to_catalog_payload())

    def test_legacy_four_scored_question_contract_remains_unchanged(self):
        expected = self.service._formal_runtime_assessment_contract({"teachingBrief": deepcopy(TEACHING_BRIEF)})
        self.assertEqual([item["id"] for item in expected], ["q2", "q3", "q4", "q5"])
        self.service._validate_locked_formal_assessment(classroom_for(expected), {"teachingBrief": deepcopy(TEACHING_BRIEF)})
        _, generation = generation_fixture()
        generation["teachingBrief"]["schemaVersion"] = "mira.learning.formal-runtime-teaching-brief.v1"
        generation["teachingBriefSha256"] = canonical_sha256(generation["teachingBrief"])
        with self.assertRaises(ValueError): validate_generation_grade_boundary(generation)

    def test_lower_grade_launch_requires_exact_visible_fine_prerequisite(self):
        authority = {"course_id": "progressive_first", "course_version": "v1", "course_grade_code": "primary_1",
            "child_grade_code": "primary_6", "child_grade_selection_revision": 3,
            "course_curriculum_version": CURRICULUM_VERSION, "course_subject": "math", "course_node_code": "M1A01.01"}
        self.service.repository = SimpleNamespace(database=object())
        conn = object()
        with patch("repositories.learning_repository.LearningRepository.get_student_visible_course", return_value={"id": "progressive_first"}) as visible:
            self.service._require_student_course_grade(conn, authority, family_id="f", child_id="c")
            self.assertEqual(visible.call_args.kwargs, {"family_id": "f", "child_id": "c", "grade_code": "primary_6",
                "grade_selection_revision": 3, "course_id": "progressive_first", "course_version": "v1"})
            for mutation in ({"course_curriculum_version": "old"}, {"course_subject": "english"},
                             {"child_grade_code": "primary_1", "course_grade_code": "primary_6"}):
                with self.subTest(mutation=mutation), self.assertRaises(OpenMaicRuntimeServiceError):
                    self.service._require_student_course_grade(conn, {**authority, **mutation}, family_id="f", child_id="c")
            self.assertEqual(visible.call_count, 1)
            visible.return_value = None
            with self.assertRaises(OpenMaicRuntimeServiceError):
                self.service._require_student_course_grade(conn, authority, family_id="f", child_id="c")

    def test_pinned_lower_grade_binding_keeps_exact_child_and_course_identity(self):
        from tests.test_formal_student_runtime_launch import _formal_row, _Repository
        row = _formal_row()
        row.update(course_grade_code="primary_1", candidate_grade_code="primary_1", child_grade_code="primary_6",
                   course_curriculum_version=CURRICULUM_VERSION, course_node_code="M1A01.01")
        _Repository(row).bind_formal_session_to_active_release(None)
        self.assertEqual(self.service._formal_session_binding_state(row), (True, True))
        for mutation in ({"formal_binding_course_version": "wrong"}, {"formal_binding_child_id": "other"},
                         {"course_curriculum_version": "old"}, {"course_subject": "english"}):
            with self.subTest(mutation=mutation):
                self.assertEqual(self.service._formal_session_binding_state({**row, **mutation}, family_id="family-1", child_id="child-1"), (True, False))

    def test_repository_cross_grade_allowance_is_one_exact_authorized_course(self):
        for course_id, visible in (("progressive_first", {"id": "progressive_first", "version": "v1"}),
                                   ("progressive_first", None), ("legacy-first", None)):
            repo = OpenMaicRuntimeRepository(object())
            repo.get_formal_session_binding_for_update = Mock(side_effect=[None, {"learning_session_id": "s"}])
            authority = {"authority_kind": "active_pointer", "pointer_history_id": "h", "pointer_revision": 1,
                "release_id": "r", "target_fingerprint": "a" * 64, "publication_contract_version": "mira.learning.formal-publication.v1",
                "runtime_binding_contract_version": repo.CANDIDATE_BINDING_CONTRACT_VERSION, "build_item_id": "b",
                "course_id": course_id, "course_version": "v1", "package_id": "p", "package_version": 1,
                "package_content_hash": "a" * 64, "runtime_classroom_id": "r", "upstream_classroom_id": "u", "binding_grade_code": "primary_1"}
            calls = []
            def execute(sql, params=()):
                calls.append((sql, params))
                if "FROM children" in sql: row = {"grade_code": "primary_6", "grade_selection_revision": 3}
                elif "SELECT course_id, course_version" in sql: row = {"course_id": course_id, "course_version": "v1"}
                elif "SELECT 'active_pointer'" in sql: row = authority if visible else None
                else: row = None
                return SimpleNamespace(fetchone=lambda: row)
            with patch("repositories.learning_repository.LearningRepository.get_progressive_remedial_course", return_value=visible) as remedial:
                result = repo.bind_formal_session_to_active_release(SimpleNamespace(execute=execute),
                    family_id="f", child_id="c", learning_session_id="s", now=100)
                active_sql, active_params = next(call for call in calls if "SELECT 'active_pointer'" in call[0])
                self.assertIn("course.grade_code = child.grade_code OR (course.id = ? AND course.version = ?)", active_sql)
                self.assertEqual(active_params[:2], (course_id, "v1") if visible else ("", ""))
                self.assertIn("receipt.asr_roundtrip_status = 'passed'", active_sql)
                self.assertIn("audio.asr_passed_count = audio.expected_segment_count", active_sql)
                if visible:
                    self.assertEqual(result, {"learning_session_id": "s"})
                    self.assertEqual(next(params for sql, params in calls if "INSERT INTO learning_student_formal_session_bindings" in sql)[3], "primary_1")
                else: self.assertIsNone(result)
                self.assertEqual(remedial.call_count, 1 if course_id.startswith("progressive_") else 0)


if __name__ == "__main__": unittest.main()
