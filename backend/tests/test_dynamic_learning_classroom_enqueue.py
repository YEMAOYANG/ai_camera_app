from __future__ import annotations

import unittest

from content.primary_skill_boundaries import boundary_for
from services.dynamic_learning_course_generation_service import (
    DynamicLearningCourseGenerationService,
)
from tests.support import fresh_test_config
from tests.test_dynamic_learning_course_generation_service import (
    _FakeQuestionAdapter,
)


class DynamicLearningClassroomEnqueueTest(unittest.TestCase):
    def test_published_dynamic_course_only_enqueues_background_classroom_job(self):
        config = fresh_test_config()
        calls: list[dict] = []

        def enqueue(**kwargs):
            calls.append(dict(kwargs))
            return {
                "id": "classroom-job-1",
                "requestId": kwargs["request_id"],
                "status": "pending",
            }

        service = DynamicLearningCourseGenerationService(
            config["DATABASE_URL"],
            adapter=_FakeQuestionAdapter(),
            classroom_enqueue=enqueue,
        )
        boundary = boundary_for("primary_3", "math")
        result = service.generate(
            {
                "requestId": "dynamic-course-with-classroom-job",
                "gradeCode": "primary_3",
                "subject": "math",
                "skillId": boundary.skill_id,
            }
        )

        self.assertTrue(result.payload["ok"], result.payload)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["course_id"], result.payload["course"]["id"])
        self.assertEqual(calls[0]["course_version"], "1.0.0")
        self.assertEqual(result.payload["classroomGeneration"]["status"], "pending")
        self.assertEqual(
            result.payload["classroomGeneration"]["jobId"],
            "classroom-job-1",
        )

    def test_catalog_managed_generation_does_not_enqueue_a_second_classroom_job(self):
        config = fresh_test_config()
        calls: list[dict] = []

        def enqueue(**kwargs):
            calls.append(dict(kwargs))
            return {"id": "unexpected", "status": "pending"}

        service = DynamicLearningCourseGenerationService(
            config["DATABASE_URL"],
            adapter=_FakeQuestionAdapter(),
            classroom_enqueue=enqueue,
        )
        boundary = boundary_for("primary_3", "math")
        result = service.generate_for_skill(
            grade_code="primary_3",
            subject="math",
            skill_id=boundary.skill_id,
            attempts=1,
            request_id="dynamic-course-catalog-managed",
            enqueue_classroom=False,
        )

        self.assertTrue(result.payload["ok"], result.payload)
        self.assertEqual(calls, [])
        self.assertEqual(
            result.payload["classroomGeneration"]["status"],
            "catalog_managed",
        )


if __name__ == "__main__":
    unittest.main()
