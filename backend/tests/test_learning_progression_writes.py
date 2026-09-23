from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
import json
from types import SimpleNamespace
import unittest
from unittest.mock import Mock

from content.primary_skill_boundaries import boundaries_for
from core.errors import ApiError
from repositories.learning_repository import LearningRepository
from services.learning_service import LearningService


class _SessionRepository:
    """Keep session and mastery state isolated from the application's database."""

    parse_json = staticmethod(LearningRepository.parse_json)

    def __init__(self, child, course):
        self.child = child
        self.course = course
        self.conn = object()
        self.task = {
            "id": "task-selected",
            "family_id": child["family_id"],
            "child_id": child["id"],
            "type": "learning",
            "status": "scheduled",
            "learning_course_id": course["id"],
            "learning_course_version": course["version"],
        }
        self.session = None
        self.mastery = {}
        self.get_mastery_state = Mock(side_effect=self._get_mastery_state)
        self.get_session_for_task = Mock(side_effect=self._get_session_for_task)
        self.create_or_get_session = Mock(side_effect=self._create_or_get_session)
        self.mark_task_in_progress = Mock()
        self.add_task_event = Mock()

    @contextmanager
    def transaction(self):
        yield self.conn

    def get_task(self, conn, *, family_id, task_id, for_update=False):
        if (family_id, task_id) == (self.task["family_id"], self.task["id"]):
            return deepcopy(self.task)
        return None

    def get_student_visible_course(self, conn, *, family_id, child_id,
                                   grade_code, grade_selection_revision,
                                   course_id, course_version):
        if (family_id, child_id, grade_code, course_id, course_version) == (
            self.child["family_id"], self.child["id"], self.child["grade_code"],
            self.course["id"], self.course["version"],
        ):
            return deepcopy(self.course)
        return None

    def _get_mastery_state(self, conn, *, family_id, child_id, grade_code,
                           subject, node_code):
        return deepcopy(self.mastery.get(
            (family_id, child_id, grade_code, subject, node_code)
        ))

    def _get_session_for_task(self, conn, *, family_id, task_id, for_update=False):
        if (family_id, task_id) == (self.task["family_id"], self.task["id"]):
            return deepcopy(self.session)
        return None

    def _create_or_get_session(self, conn, *, family_id, child_id, task_id,
                               course_id, course_version, now):
        if self.session is not None:
            return deepcopy(self.session), False
        self.session = {
            "id": "session-created", "family_id": family_id,
            "child_id": child_id, "task_id": task_id,
            "course_id": course_id, "course_version": course_version,
            "status": "in_progress", "current_question_index": 0,
            "correct_count": 0, "attempted_count": 0,
            "answers_json": "[]", "started_at": now,
        }
        return deepcopy(self.session), True

    def save_mastery(self, skill_id, level="mastered", **scope):
        key = (
            scope.get("family_id", self.child["family_id"]),
            scope.get("child_id", self.child["id"]),
            scope.get("grade_code", self.child["grade_code"]),
            scope.get("subject", self.course["subject"]),
            skill_id,
        )
        self.mastery[key] = {"mastery_level": level}

    def started_session(self, **changes):
        self.session = {
            "id": "session-existing", "family_id": self.child["family_id"],
            "child_id": self.child["id"], "task_id": self.task["id"],
            "course_id": self.course["id"],
            "course_version": self.course["version"],
            "status": "in_progress", "current_question_index": 1,
            "correct_count": 1, "attempted_count": 1,
            "answers_json": json.dumps([
                {"questionId": "q1", "attemptNumber": 1, "correct": True}
            ]),
            "started_at": 1000,
            **changes,
        }
        return deepcopy(self.session)


def _fixture(grade_code="primary_1"):
    child = {
        "id": "child-a", "family_id": "family-a", "grade_code": grade_code,
        "grade_selection_revision": 1,
    }
    boundaries = boundaries_for(grade_code, "math")
    course = {
        "id": "course-future", "version": "v1", "grade_code": grade_code,
        "subject": "math", "node_code": boundaries[1].skill_id,
        "title": boundaries[1].skill_title, "objective": "学习当前能力点",
        "content_json": json.dumps({"questions": [
            {"id": f"q{index}", "type": "numeric", "prompt": f"练习 {index}",
             "answer": "1"} for index in range(1, 5)
        ]}),
    }
    repository = _SessionRepository(child, course)
    service = LearningService.__new__(LearningService)
    service.repository = repository
    service.static_catalog_enabled = False
    service.auth_service = SimpleNamespace(
        authenticate=Mock(return_value={"family": {"id": child["family_id"]}})
    )
    service._ensure_catalog = Mock()
    service._lock_formal_student_child = Mock(return_value=child)
    service._assert_formal_student_release_for_locked_child = Mock()
    return service, repository, child, course, boundaries


def _start(service, repository, child):
    return service.start_session(
        "student-token", {"taskId": repository.task["id"]},
        formal_student_child_id=child["id"],
    )


class LearningProgressionWritesTest(unittest.TestCase):
    def assert_rejected_without_session_write(self, service, repository, child,
                                             code="learning_prerequisite_not_mastered"):
        with self.assertRaises(ApiError) as caught:
            _start(service, repository, child)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.code, code)
        repository.create_or_get_session.assert_not_called()
        repository.mark_task_in_progress.assert_not_called()
        repository.add_task_event.assert_not_called()

    def test_future_skill_cannot_create_a_session_in_any_primary_grade(self):
        for grade in range(1, 7):
            with self.subTest(grade=grade):
                service, repository, child, _, _ = _fixture(f"primary_{grade}")
                self.assert_rejected_without_session_write(service, repository, child)
                self.assertIsNone(repository.session)

    def test_task_status_without_a_started_session_cannot_bypass_prerequisites(self):
        for status in ("scheduled", "pending", "in_progress"):
            with self.subTest(task_status=status):
                service, repository, child, _, _ = _fixture()
                repository.task["status"] = status
                self.assert_rejected_without_session_write(service, repository, child)

    def test_mastered_prerequisite_allows_a_new_session_in_any_primary_grade(self):
        for grade in range(1, 7):
            with self.subTest(grade=grade):
                service, repository, child, course, boundaries = _fixture(f"primary_{grade}")
                repository.save_mastery(boundaries[0].skill_id)
                result = _start(service, repository, child)
                self.assertFalse(result["resumed"])
                self.assertEqual(result["session"]["courseId"], course["id"])
                self.assertEqual(result["session"]["currentQuestionIndex"], 0)
                repository.create_or_get_session.assert_called_once()
                repository.add_task_event.assert_called_once()

    def test_incomplete_prerequisite_is_not_enough_to_create_a_session(self):
        for level in ("developing", "needs_practice"):
            with self.subTest(mastery_level=level):
                service, repository, child, _, boundaries = _fixture()
                repository.save_mastery(boundaries[0].skill_id, level)
                self.assert_rejected_without_session_write(service, repository, child)

    def test_existing_exact_session_resumes_without_rewriting_its_progress(self):
        service, repository, child, course, _ = _fixture()
        before = repository.started_session()
        result = _start(service, repository, child)
        self.assertTrue(result["resumed"])
        self.assertEqual(result["session"]["id"], before["id"])
        self.assertEqual(result["session"]["courseVersion"], course["version"])
        self.assertEqual(result["session"]["currentQuestionIndex"], 1)
        self.assertEqual(result["session"]["attemptedCount"], 1)
        self.assertEqual(result["session"]["correctCount"], 1)
        self.assertEqual(result["session"]["currentQuestion"]["id"], "q2")
        self.assertEqual(repository.session, before)
        repository.add_task_event.assert_not_called()
        service._assert_formal_student_release_for_locked_child.assert_called_once()

    def test_existing_session_for_another_child_course_or_version_is_rejected(self):
        for changes in ({"child_id": "child-b"}, {"course_id": "another-course"},
                        {"course_version": "v0"}):
            with self.subTest(changes=changes):
                service, repository, child, _, _ = _fixture()
                before = repository.started_session(**changes)
                self.assert_rejected_without_session_write(
                    service, repository, child, "learning_session_course_conflict"
                )
                self.assertEqual(repository.session, before)

    def test_resuming_an_old_session_still_requires_formal_publication_authority(self):
        service, repository, child, _, _ = _fixture()
        before = repository.started_session()
        service._assert_formal_student_release_for_locked_child.side_effect = ApiError(
            "learning_classroom_release_changed", "发布状态已变化", 409
        )
        self.assert_rejected_without_session_write(
            service, repository, child, "learning_classroom_release_changed"
        )
        self.assertEqual(repository.session, before)

    def test_mastery_from_another_family_child_grade_or_subject_cannot_unlock(self):
        for scope in ({"family_id": "family-b"}, {"child_id": "child-b"},
                      {"grade_code": "primary_2"}, {"subject": "english"}):
            with self.subTest(scope=scope):
                service, repository, child, course, boundaries = _fixture()
                repository.save_mastery(boundaries[0].skill_id, **scope)
                result = service.progression_for_course(
                    repository.conn, child=child, course=course
                )
                self.assertFalse(result["canStart"])
                self.assertIn(boundaries[0].skill_id, result["blockedBySkillIds"])
                for call in repository.get_mastery_state.call_args_list:
                    self.assertEqual(call.kwargs["family_id"], child["family_id"])
                    self.assertEqual(call.kwargs["child_id"], child["id"])
                    self.assertEqual(call.kwargs["grade_code"], child["grade_code"])
                    self.assertEqual(call.kwargs["subject"], course["subject"])
                repository.save_mastery(boundaries[0].skill_id)
                self.assertTrue(service.progression_for_course(
                    repository.conn, child=child, course=course
                )["canStart"])


if __name__ == "__main__":
    unittest.main()
