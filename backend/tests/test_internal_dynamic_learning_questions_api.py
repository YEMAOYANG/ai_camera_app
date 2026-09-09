from __future__ import annotations

import unittest

from app import create_app
from content.primary_skill_boundaries import boundary_for
from services.dynamic_learning_course_generation_service import (
    DynamicLearningCourseGenerationService,
)
from tests.support import fresh_test_config
from tests.test_dynamic_learning_course_generation_service import (
    _FakeQuestionAdapter,
)


class InternalDynamicLearningQuestionsApiTest(unittest.TestCase):
    def setUp(self):
        self.internal_token = "dynamic-learning-token"
        self.app = create_app(
            fresh_test_config(INTERNAL_API_TOKEN=self.internal_token)
        )
        self.client = self.app.test_client()
        self.adapter = _FakeQuestionAdapter()
        self.app.extensions[
            "mira_dynamic_learning_course_generation_service"
        ] = DynamicLearningCourseGenerationService(
            self.app.config["DATABASE_URL"], adapter=self.adapter
        )
        self.headers = {
            "X-Mira-Internal-Token": self.internal_token,
            "X-Mira-Internal-Source": "learning-worker",
        }

    def test_status_and_generate_are_guarded_and_preserve_requested_target(self):
        unauthorized = self.client.get(
            "/internal/learning/content/questions/status"
        )
        self.assertEqual(unauthorized.status_code, 401, unauthorized.json)

        status = self.client.get(
            "/internal/learning/content/questions/status", headers=self.headers
        )
        self.assertEqual(status.status_code, 200, status.json)
        policy = status.json["generation"]["policy"]
        self.assertEqual(policy["questionCount"], 5)
        self.assertTrue(policy["independentSolutionRequired"])
        self.assertFalse(policy["staticQuestionsAreGenerationAuthority"])
        self.assertFalse(policy["automaticPublicationAfterValidation"])
        self.assertTrue(policy["catalogReleaseRequired"])

        boundary = boundary_for("primary_3", "math")
        generated = self.client.post(
            "/internal/learning/content/questions/generate",
            json={
                "requestId": "internal-dynamic-primary-3-math",
                "gradeCode": "primary_3",
                "subject": "math",
                "skillId": boundary.skill_id,
            },
            headers=self.headers,
        )
        self.assertEqual(generated.status_code, 200, generated.json)
        self.assertEqual(generated.json["status"], "validated")
        self.assertEqual(generated.json["course"]["gradeCode"], "primary_3")
        self.assertEqual(generated.json["course"]["subject"], "math")
        self.assertEqual(generated.json["course"]["skillId"], boundary.skill_id)
        self.assertEqual(
            generated.json["course"]["contentOrigin"], "openmaic_generated"
        )
        self.assertEqual(
            generated.json["course"]["boundaryVersion"],
            boundary.boundary_version,
        )
        self.assertIn("auditId", generated.json["internal"])


if __name__ == "__main__":
    unittest.main()
